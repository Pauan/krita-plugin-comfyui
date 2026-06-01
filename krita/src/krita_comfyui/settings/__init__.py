import os
import functools
from enum import Enum
from json import dump, dumps, load, loads
from pathlib import Path
from PyQt6.QtCore import QObject, QStringListModel, pyqtSignal, pyqtSlot
from PyQt6.QtWidgets import QMessageBox
from shared import timestamp_local, Perf
from ..util.qt import BlockSignals, Thread
from ..util.storage import Storage


class Input:
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
                metadata = Node(key)
                metadata.update(option["inputs"])
                self.sub_options[key] = metadata


class Node:
    def __init__(self, node_id):
        self.node_id = node_id
        self.inputs = {}

    def update_inputs(self, inputs):
        if inputs is not None:
            for name, input in inputs.items():
                metadata = Input()

                if len(input) > 1:
                    info = input[1]
                else:
                    info = {}

                metadata.update(input[0], info)
                self.inputs[name] = metadata

    def update(self, inputs):
        self.update_inputs(inputs.get("required", None))
        self.update_inputs(inputs.get("optional", None))

    def input(self, name):
        if isinstance(name, str):
            try:
                return self.inputs[name]
            except KeyError:
                raise RuntimeError(f"Input does not exist [{self.node_id}]: {name}")

        else:
            metadata = self

            # If input is a list, then the metadata is a dynamic combo,
            # so we search for the input inside of the dynamic combo.
            for name in name:
                metadata = metadata.input(name)

            return metadata


class NodeMetadata(QObject):
    changed = pyqtSignal()
    saved = pyqtSignal(dict)

    def __init__(self, dir):
        super().__init__()

        self.dir = dir

        self.data = None
        self.cache = {}

        self.saved.connect(self.on_save)


    def save(self, data):
        self.saved.emit(data)


    def is_loaded(self):
        return self.data is not None


    def get(self, node_id):
        metadata = self.cache.get(node_id)

        if metadata is None:
            metadata = Node(node_id)

            try:
                info = self.data[node_id]
            except KeyError:
                raise RuntimeError(f"Could not find node [{node_id}]")

            metadata.update(info["input"])

            self.cache[node_id] = metadata

        return metadata


    @pyqtSlot()
    def load(self):
        with Perf("NodeMetadata.load"):
            assert self.data is None
            assert self.cache == {}

            try:
                with open(self.dir / "node_metadata.json", "r") as file:
                    self.data = load(file)
            except FileNotFoundError:
                pass

        if self.data is not None:
            self.changed.emit()


    @pyqtSlot(dict)
    def on_save(self, data):
        with Perf("NodeMetadata.save"):
            self.data = data
            self.cache = {}

            with open(self.dir / "node_metadata.json", "w") as file:
                dump(data, file, indent=2)

        assert self.data is not None
        self.changed.emit()


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


    def _get_default(self, id: str):
        return self.defaults[id]


    def _save(self):
        with open(self.path, "w") as file:
            dump(self._serialized, file, indent=2)


class Workflow:
    def __init__(self, file, is_hidden):
        self.file = file
        self._is_hidden = is_hidden

    def id(self):
        return self.file["id"]

    def icon(self):
        return self.file["icon"]

    def name(self):
        return self.file["name"]

    def global_widgets(self):
        return self.file.get("global_widgets", [])

    def document_widgets(self):
        return self.file.get("document_widgets", [])

    def graph(self):
        return self.file["graph"]

    def is_hidden(self):
        return self._is_hidden.get()


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

        # TODO emit changed whenever the is_hidden changes
        #self.settings.add_listener(lambda: self.changed.emit())
        self.order.add_listener(lambda: self.changed.emit())


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
        for id in self.order.default():
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
        return Workflow(file, self.settings.dict(id).value("is_hidden", bool, default=False))


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


@functools.total_ordering
class DanbooruTagSorter:
    def __init__(self, name, post_count, is_alias):
        self.name = name
        self.post_count = post_count
        self.is_alias = is_alias
        self.lowercase = name.casefold()

    def cmp(self, other):
        # Higher post count is sorted first
        if self.post_count < other.post_count:
            return 1
        elif other.post_count < self.post_count:
            return -1

        # Non-aliases are sorted before aliases
        if self.is_alias and not other.is_alias:
            return 1
        elif other.is_alias and not self.is_alias:
            return -1

        # Sorted alphabetically
        if self.lowercase < other.lowercase:
            return -1
        elif other.lowercase < self.lowercase:
            return 1

        return 0

    def __eq__(self, other):
        return self.cmp(other) == 0

    def __lt__(self, other):
        return self.cmp(other) < 0


class DanbooruTags(QObject):
    changed = pyqtSignal()
    saved = pyqtSignal(dict)

    def __init__(self, dir, settings):
        super().__init__()

        self.dir = dir
        self.settings = settings
        self.tags = {}
        self.model = QStringListModel(parent=self)

        self.saved.connect(self.on_save)


    def get(self, name, default):
        return self.tags.get(name, default)


    def save(self, tags):
        self.saved.emit(tags)


    @pyqtSlot()
    def load(self):
        with Perf("DanbooruTags.load"):
            try:
                with open(self.dir / "danbooru_tags.json", "r") as file:
                    self.tags = load(file)
            except FileNotFoundError:
                self.tags = {}

        self.update()


    @pyqtSlot(dict)
    def on_save(self, tags):
        with Perf("DanbooruTags.save"):
            self.tags = tags

            with open(self.dir / "danbooru_tags.json", "w") as file:
                dump(tags, file, indent=2)

        self.update()


    def update(self):
        with Perf("DanbooruTags.update"):
            minimum_posts = self.settings.root.value("danbooru_minimum_posts", int).get()
            minimum_characters = self.settings.root.value("autocomplete_minimum_characters", int).get()

            tags = []

            for name, tag in self.tags.items():
                if len(name) >= minimum_characters:
                    alias = tag.get("alias_for", None)

                    if alias is not None:
                        # If the alias is a subset of the parent, we skip it.
                        # This removes unnecessary aliases like 4girl -> 4girls and 1girls -> 1girl
                        if alias.startswith(name) or (alias in name):
                            continue

                        name = f"{name}  ➜  {alias}"
                        is_alias = True
                        post_count = self.tags[alias]["post_count"]
                    else:
                        is_alias = False
                        post_count = tag["post_count"]

                    if post_count >= minimum_posts:
                        tags.append(DanbooruTagSorter(name, post_count, is_alias))

            tags.sort()

            self.model.setStringList([tag.name for tag in tags])

        self.changed.emit()


class Settings(QObject):
    default_settings = load_default_file("settings.json")
    default_bundles = load_default_file("bundles.json")
    default_presets = load_default_file("presets.json")
    default_workflows = load_default_folder("workflows")

    def __init__(self, parent):
        super().__init__(parent)

        self.dir = Path(Krita.getAppDataLocation()) / "krita_comfyui"

        os.makedirs(self.dir, exist_ok=True)

        with Perf("Loading settings"):
            self.settings = SettingsFile(self.dir / "settings.json", self.default_settings)

        with Perf("Loading bundles"):
            self.bundles = SettingsFile(self.dir / "bundles.json", self.default_bundles)

        with Perf("Loading presets"):
            self.presets = SettingsFile(self.dir / "presets.json", self.default_presets)

        with Perf("Loading workflows"):
            self.workflows = Workflows(
                self,
                settings=self.settings.root.dict("workflows"),
                order=self.settings.root.value("workflow_order", list),
                folder=self.dir / "workflows",
                defaults=self.default_workflows,
            )

        self.node_metadata = NodeMetadata(self.dir)
        self.danbooru_tags = DanbooruTags(self.dir, self.settings)

        self.logging_level = self.settings.root.value("logging_level", str)

        self.thread = Thread(self)

        self.thread.move(self.node_metadata)
        self.thread.started.connect(self.node_metadata.load)

        self.thread.move(self.danbooru_tags)
        self.thread.started.connect(self.danbooru_tags.load)

        self.thread.start()


    def with_selected_workflow(self, f):
        return self.settings.root.value("selected_workflow", str).map(lambda x: f(self.settings.root.dict("workflows").dict(x)))


    def cleanup(self):
        return self.thread.stop()


    def clear_log(self):
        with Perf("clear_log"):
            # Deletes the log file
            with open(self.dir / "debug.log", "w") as file:
                pass

    def log_str(self, str, *, level):
        if level.matches(self.logging_level.get()):
            with open(self.dir / "debug.log", "a") as file:
                time = timestamp_local()
                file.write(f"[{time} {level.name}] {str}")
                file.write("\n\n")

    def log_json(self, json, *, level, label=None):
        if level.matches(self.logging_level.get()):
            with open(self.dir / "debug.log", "a") as file:
                time = timestamp_local()
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
                self.settings.replace_serialized({})
                self.bundles.replace_serialized({})
                self.presets.replace_serialized({})
                self.workflows.replace_serialized({})
            except:
                self.restore_snapshot(snapshot)
                raise
