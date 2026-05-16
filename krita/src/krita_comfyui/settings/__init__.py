import os
import functools
from json import dump, dumps, load, loads
from pathlib import Path
from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtWidgets import QMessageBox
from ..util.storage import Storage, Metadata


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


class SettingsFile(Storage):
    def __init__(self, path, defaults):
        super().__init__(self._load(path))
        self.path = path
        self.defaults = defaults


    @staticmethod
    def _load(path):
        try:
            with open(path, "r") as file:
                return load(file)
        except FileNotFoundError:
            return {}


    def _metadata(self, key, default):
        if default is None:
            default = self.defaults.get(key, None)

        return Metadata(key, default)


    def _save(self):
        with open(self.path, "w") as file:
            dump(self.serialized, file, indent=2)


class Workflows(QObject):
    changed = pyqtSignal(str)

    def __init__(self, parent, folder, defaults):
        super().__init__(parent)

        os.makedirs(folder, exist_ok=True)

        self.folder = folder
        self.defaults = defaults
        self.files = self._load(folder)


    @staticmethod
    def _load(folder):
        files = {}

        for filename in os.listdir(folder):
            key = Path(filename).stem

            with open(folder / filename, "r") as file:
                files[key] = load(file)

        return files


    def get_all(self):
        return sorted(
            list(self.defaults.values()) + list(self.files.values()),
            key=WorkflowCmp,
        )


    def get(self, filename):
        try:
            return self.defaults[filename]
        except KeyError:
            return self.files[filename]


    def set(self, filename, value):
        assert not filename in self.defaults

        try:
            should_save = self.files[filename] != value
        except KeyError:
            should_save = True

        if should_save:
            self.files[filename] = value

            with open(self.folder / (filename + ".json"), "w") as file:
                dump(value, file, indent=2)

            self.changed.emit(filename)


    def remove(self, filename):
        del self.files[filename]

        try:
            os.remove(self.folder / (filename + ".json"))
        except FileNotFoundError:
            pass

        self.changed.emit(filename)


    def clear(self):
        if self.files != {}:
            for filename in self.files.keys():
                self.remove(filename)
            assert self.files == {}
            return True
        return False


    def snapshot(self):
        snapshots = {}

        for filename, value in self.files.items():
            snapshots[filename] = loads(dumps(value))

        return snapshots


    def restore_snapshot(self, snapshots):
        for filename in self.files.keys():
            if not filename in snapshots:
                self.remove(filename)

        for filename, snapshot in snapshots.items():
            self.set(filename, snapshot)

        assert self.files == snapshots


@functools.total_ordering
class WorkflowCmp:
    def __init__(self, workflow):
        self.is_default = workflow.get("is_default", False)
        self.before = workflow.get("before", None)
        self.name = workflow["name"].casefold()
        self.id = workflow["id"]

    def cmp(self, other):
        if self.is_default and not other.is_default:
            return -1
        elif other.is_default and not self.is_default:
            return 1

        if self.before is not None and self.before == other.id:
            return -1
        elif other.before is not None and other.before == self.id:
            return 1

        if self.name < other.name:
            return -1
        elif other.name < self.name:
            return 1

        if self.id < other.id:
            return -1
        elif other.id < self.id:
            return 1

        return 0

    def __eq__(self, other):
        return self.cmp(other) == 0

    def __lt__(self, other):
        return self.cmp(other) < 0


def load_default_file(filename):
    folder = Path(__file__).parent / "defaults"

    try:
        with open(folder / filename, "r") as file:
            return load(file)
    except FileNotFoundError:
        return {}


def load_default_folder(folder):
    folder = Path(__file__).parent / "defaults" / folder

    defaults = {}

    for filename in os.listdir(folder):
        key = Path(filename).stem

        with open(folder / filename, "r") as file:
            defaults[key] = load(file)

    return defaults


class Settings(QObject):
    node_metadata_changed = pyqtSignal()

    default_settings = load_default_file("settings.json")
    default_bundles = load_default_file("bundles.json")
    default_presets = load_default_file("presets.json")
    default_workflows = load_default_folder("workflows")

    def __init__(self, parent):
        super().__init__(parent)

        self.dir = Path(Krita.getAppDataLocation()) / "krita_comfyui"

        self.node_metadata = None
        self.cached_node_metadata = {}

        self.settings = SettingsFile(self.dir / "settings.json", self.default_settings)
        self.bundles = SettingsFile(self.dir / "bundles.json", self.default_bundles)
        self.presets = SettingsFile(self.dir / "presets.json", self.default_presets)
        self.workflows = Workflows(self, self.dir / "workflows", self.default_workflows)

        self.load_node_metadata()


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
                self.settings.clear()
                self.bundles.clear()
                self.presets.clear()
                self.workflows.clear()
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
