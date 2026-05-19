import os
import functools
from enum import Enum
from json import dump, dumps, load, loads
from pathlib import Path
from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtWidgets import QMessageBox
from ..util import timestamp
from ..util.qt import BlockSignals
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


class Workflow:
    def __init__(self, settings, file):
        self.settings = settings
        self.file = file

    def id(self):
        return self.file["id"]

    def icon(self):
        return self.file["icon"]

    def name(self):
        return self.file["name"]

    def layout(self):
        return self.file["layout"]

    def graph(self):
        return self.file["graph"]

    def is_hidden(self):
        return self.settings.get("hidden", False)


class Workflows(QObject):
    changed = pyqtSignal()

    def __init__(self, parent, settings, order, folder, defaults):
        super().__init__(parent)

        os.makedirs(folder, exist_ok=True)

        self.settings = settings
        self.order = order
        self.folder = folder
        self.defaults = defaults
        self.files = self._load(folder)

        self._process_order()

        self.settings.add_listener(lambda old, new: self.changed.emit())
        self.order.add_listener(lambda old, new: self.changed.emit())


    @staticmethod
    def _load(folder):
        files = {}

        for filename in os.listdir(folder):
            id = Path(filename).stem

            with open(folder / filename, "r") as file:
                files[id] = load(file)

        return files


    def _process_order(self):
        new_order = []
        seen = set()
        last_default = 0

        for id in self.order.get():
            # Removes duplicate IDs.
            if not id in seen:
                try:
                    workflow = self._get_file(id)
                    new_order.append(id)
                    seen.add(id)

                    if workflow.get("is_default", False):
                        last_default = len(new_order)

                # Removes any IDs that don't exist.
                except KeyError:
                    pass

        # Adds default workflows that aren't in the order.
        for id in self.order.default:
            if not id in seen:
                new_order.insert(last_default, id)
                seen.add(id)
                last_default += 1

        for id in self.defaults.keys():
            assert id in seen

        def sort_files(file):
            value = file[1]
            return (value["name"].casefold(), value["id"])

        # Adds user workflows that aren't in the order.
        for id, _ in sorted(self.files.items(), key=sort_files):
            if not id in seen:
                new_order.append(id)

        self.order.set(new_order)


    def _get_file(self, id):
        try:
            return self.defaults[id]
        except KeyError:
            return self.files[id]


    def get_all(self):
        return [self.get(id) for id in self.order.get()]


    def get(self, id):
        file = self._get_file(id)
        settings = self.settings.get()
        return Workflow(settings.get(id, {}), file)


    def set(self, id, value):
        assert not id in self.defaults

        try:
            should_save = self.files[id] != value
        except KeyError:
            should_save = True

        if should_save:
            self.files[id] = value

            with open(self.folder / (id + ".json"), "w") as file:
                dump(value, file, indent=2)

            self.changed.emit()
            return True

        return False


    def remove(self, id):
        del self.files[id]

        try:
            os.remove(self.folder / (id + ".json"))
        except FileNotFoundError:
            pass

        self.changed.emit()
        return True


    def clear(self):
        if self.files != {}:
            changed = False

            with BlockSignals(self):
                for id in self.files.keys():
                    if self.remove(id):
                        changed = True

            assert self.files == {}

            if changed:
                self.changed.emit()

            return True
        return False


    def snapshot(self):
        snapshots = {}

        for id, value in self.files.items():
            snapshots[id] = loads(dumps(value))

        return snapshots


    def restore_snapshot(self, snapshots):
        changed = False

        with BlockSignals(self):
            for id in self.files.keys():
                if not id in snapshots:
                    if self.remove(id):
                        changed = True

            for id, snapshot in snapshots.items():
                if self.set(id, snapshot):
                    changed = True

        assert self.files == snapshots

        if changed:
            self.changed.emit()


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
        id = Path(filename).stem

        with open(folder / filename, "r") as file:
            defaults[id] = load(file)

    return defaults


# TODO use StrEnum when ComfyUI upgrades to Python 3.11+
class LogLevel(Enum):
    NONE = "none"
    ERROR = "error"
    WARN = "warn"
    INFO = "info"
    DEBUG = "debug"
    TRACE = "trace"

    @staticmethod
    def order(value):
        match value:
            case "none": return 0
            case "error": return 1
            case "warn": return 2
            case "info": return 3
            case "debug": return 4
            case "trace": return 5

    def matches(self, value):
        return LogLevel.order(self.value) <= LogLevel.order(value)


class Settings(QObject):
    node_metadata_changed = pyqtSignal()

    default_settings = load_default_file("settings.json")
    default_bundles = load_default_file("bundles.json")
    default_presets = load_default_file("presets.json")
    default_workflows = load_default_folder("workflows")

    def __init__(self, parent):
        super().__init__(parent)

        self.dir = Path(Krita.getAppDataLocation()) / "krita_comfyui"

        os.makedirs(self.dir, exist_ok=True)

        self.node_metadata = None
        self.cached_node_metadata = {}

        self.settings = SettingsFile(self.dir / "settings.json", self.default_settings)
        self.bundles = SettingsFile(self.dir / "bundles.json", self.default_bundles)
        self.presets = SettingsFile(self.dir / "presets.json", self.default_presets)

        self.workflows = Workflows(
            self,
            settings=self.settings.item("workflows"),
            order=self.settings.item("workflow_order"),
            folder=self.dir / "workflows",
            defaults=self.default_workflows,
        )

        self.logging_level = self.settings.item("logging_level")

        self.load_node_metadata()


    def clear_log(self):
        # Deletes the log file
        with open(self.dir / "debug.log", "w") as file:
            pass

    def log_str(self, str, *, level):
        if level.matches(self.logging_level.get()):
            with open(self.dir / "debug.log", "a") as file:
                time = timestamp()
                file.write(f"[{time} {level.name}] {str}")
                file.write("\n\n")

    def log_json(self, json, *, level, label=None):
        if level.matches(self.logging_level.get()):
            with open(self.dir / "debug.log", "a") as file:
                time = timestamp()
                if label is None:
                    file.write(f"[{time} {level.name}] ")
                else:
                    file.write(f"[{time} {level.name}] {label}: ")
                dump(json, file, indent=2)
                file.write("\n\n")


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
