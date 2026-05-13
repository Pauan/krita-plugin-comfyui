import os
import contextlib
from enum import Enum, auto
from json import dump, dumps, load, loads
from pathlib import Path
from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtWidgets import QMessageBox


class InputMetadata:
    def __init__(self):
        self.info = {}
        self.sub_options = {}

    def input(self, name):
        try:
            return self.sub_options[name]
        except KeyError:
            raise RuntimeError(f"Dynamic option {name} does not exist")

    def update(self, node_type, info):
        self.info = info

        if not "options" in self.info:
            # Old school combo nodes
            if isinstance(node_type, list):
                self.info["options"] = node_type

        if node_type == "COMFY_DYNAMICCOMBO_V3":
            for option in info["options"]:
                key = option["key"]
                metadata = NodeMetadata(key)
                metadata.update(option["inputs"])
                self.sub_options[key] = metadata


class NodeMetadata:
    def __init__(self, node_id):
        self.exists = False
        self.node_id = node_id
        self.inputs = {}

    def update_inputs(self, inputs):
        if inputs is not None:
            for name, input in inputs.items():
                metadata = InputMetadata()

                if len(input) > 1:
                    info = input[1]
                else:
                    info = {}

                metadata.update(input[0], info)
                self.inputs[name] = metadata

    def update(self, inputs):
        self.exists = True
        self.update_inputs(inputs.get("required", None))
        self.update_inputs(inputs.get("optional", None))

    def input(self, name):
        if isinstance(name, str):
            if self.exists:
                try:
                    return self.inputs[name]
                except KeyError:
                    raise RuntimeError(f"Input does not exist [{self.node_id}]: {name}")
            else:
                return InputMetadata()

        else:
            metadata = self

            # If input is a list, then the metadata is a dynamic combo,
            # so we search for the input inside of the dynamic combo.
            for name in name:
                metadata = metadata.input(name)

            return metadata


class SaveState(Enum):
    SHOULD_SAVE = auto()
    DELAY_SAVE = auto()
    DID_SAVE = auto()


class KeyValue(QObject):
    changed = pyqtSignal()

    def __init__(self, parent, defaults):
        super().__init__(parent)

        self.save_state = SaveState.SHOULD_SAVE
        self.dict = {}
        self.defaults = defaults


    @contextlib.contextmanager
    def delay_save(self):
        save_state = self.save_state

        self.save_state = SaveState.DELAY_SAVE

        try:
            yield

        finally:
            if self.save_state == SaveState.DID_SAVE:
                self.save_state = save_state
                self.save()
            else:
                self.save_state = save_state


    def save(self):
        if self.save_state == SaveState.SHOULD_SAVE:
            self.changed.emit()
        else:
            self.save_state = SaveState.DID_SAVE


    def get(self, key):
        try:
            return self.dict[key]
        except KeyError:
            return self.defaults[key]


    def set(self, key, value):
        try:
            changed = (self.dict[key] != value)
        except KeyError:
            changed = True

        if changed:
            self.dict[key] = value
            self.save()

        return changed


    def remove(self, key):
        try:
            del self.dict[key]
        except KeyError:
            return False

        self.save()
        return True


    def restore_defaults(self):
        if self.dict != {}:
            self.dict = {}
            self.save()
            return True
        else:
            return False


    def snapshot(self):
        return loads(dumps(self.dict))


    def restore_snapshot(self, snapshot):
        if self.dict != snapshot:
            self.dict = snapshot
            self.save()


class KeyValueFile(KeyValue):
    def __init__(self, parent, path, defaults):
        super().__init__(parent, defaults)
        self.path = path


    def load(self):
        assert self.dict == {}

        try:
            with open(self.path, "r") as file:
                self.dict = load(file)
        except FileNotFoundError:
            pass


    def save(self):
        with open(self.path, "w") as file:
            dump(self.dict, file, indent=2)

        super().save()


class KeyValueFolder(KeyValue):
    def __init__(self, parent, folder, defaults):
        super().__init__(parent, defaults)
        self.folder = folder
        os.makedirs(self.folder, exist_ok=True)


    def load(self):
        assert self.dict == {}

        for filename in os.listdir(self.folder):
            key = Path(filename).stem

            with open(self.folder / filename, "r") as file:
                self.dict[key] = load(file)


    def set(self, key, value):
        with self.delay_save():
            if super().set(key, value):
                with open(self.folder / (key + ".json"), "w") as file:
                    dump(value, file, indent=2)
                return True
            return False


    def remove(self, key):
        with self.delay_save():
            if super().remove(key):
                os.remove(self.folder / (key + ".json"))
                return True
            return False


    def restore_defaults(self):
        with self.delay_save():
            if super().restore_defaults():
                for filename in os.listdir(self.folder):
                    os.remove(filename)
                return True
            return False


    def restore_snapshot(self, snapshot):
        with self.delay_save():
            for key in self.dict.keys():
                if not key in snapshot:
                    self.remove(key)

            for key, value in snapshot.items():
                self.set(key, value)

            assert self.dict == snapshot


class Settings(QObject):
    node_metadata_changed = pyqtSignal()

    default_settings = {}
    default_presets = {}
    default_workflows = {}

    def __init__(self, parent):
        super().__init__(parent)

        self.dir = Path(Krita.getAppDataLocation()) / "krita_comfyui"

        self.node_metadata = None
        self.cached_node_metadata = {}

        self.settings = KeyValueFile(self, self.dir / "settings.json", self.default_settings)
        self.bundles = KeyValueFile(self, self.dir / "bundles.json", {})
        self.presets = KeyValueFile(self, self.dir / "presets.json", self.default_presets)
        self.workflows = KeyValueFolder(self, self.dir / "workflows", self.default_workflows)

        self.settings.load()
        self.bundles.load()
        self.presets.load()
        self.workflows.load()

        self.load_node_metadata()


    def get_all_workflows(self):
        def sort_workflow(x):
            return (x.get("order", 0), x["name"].casefold(), x["id"])

        return sorted(list(self.workflows.defaults.values()) + list(self.workflows.dict.values()), key=sort_workflow)


    def snapshot(self):
        return (
            self.settings.snapshot(),
            self.bundles.snapshot(),
            self.presets.snapshot(),
            self.workflows.snapshot(),
        )


    def restore_snapshot(self, snapshot):
        self.settings.restore_snapshot(snapshot[0])
        self.bundles.restore_snapshot(snapshot[1])
        self.presets.restore_snapshot(snapshot[2])
        self.workflows.restore_snapshot(snapshot[3])


    def restore_defaults(self):
        reply = QMessageBox.question(
            self,
            "Restore defaults",
            "Are you sure you want to restore all defaults?\n\nThis will delete all your bundles, presets, and workflows!\n\nThis cannot be undone!",
        )

        if reply == QMessageBox.StandardButton.Yes:
            snapshot = self.snapshot()

            try:
                self.settings.restore_defaults()
                self.bundles.restore_defaults()
                self.presets.restore_defaults()
                self.workflows.restore_defaults()
            except:
                self.restore_snapshot(snapshot)
                raise


    def get_node_metadata(self, node_id):
        metadata = self.cached_node_metadata.get(node_id)

        if metadata is None:
            metadata = NodeMetadata(node_id)

            if self.node_metadata is not None:
                try:
                    info = self.node_metadata[node_id]
                except KeyError:
                    raise RuntimeError(f"Could not find node [{node_id}]")

                metadata.update(info["input"])

            self.cached_node_metadata[node_id] = metadata

        return metadata


    def load_node_metadata(self):
        assert self.node_metadata is None

        try:
            with open(self.dir / "node_metadata.json", "r") as file:
                self.node_metadata = load(file)
        except FileNotFoundError:
            pass

        self.cached_node_metadata = {}


    def save_node_metadata(self, metadata):
        self.node_metadata = metadata
        self.cached_node_metadata = {}

        with open(self.dir / "node_metadata.json", "w") as file:
            dump(metadata, file, indent=2)

        self.node_metadata_changed.emit()
