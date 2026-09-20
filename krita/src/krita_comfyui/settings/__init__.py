import os
import contextlib
import functools
from enum import Enum
from typing import Any, cast, overload
from collections.abc import Callable, Sequence
from json import dump, dumps, load, loads
from pathlib import Path
from PyQt6.QtCore import QObject, QStringListModel, pyqtSignal, pyqtSlot
from shared import timestamp_local, Perf
from ..util.qt import BlockSignals, Thread
from ..util.storage import Storage, PathValue, Dict, Map
from shared import JSON


class Input:
    def __init__(self) -> None:
        self.info: dict[str, Any] = {}
        self.sub_options: dict[str, Node] = {}

    def input(self, name: str) -> "Node":
        try:
            return self.sub_options[name]
        except KeyError:
            raise RuntimeError(f"Dynamic option {name} does not exist")

    def update(self, node_type: Any, info: dict[str, Any]) -> None:
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
    def __init__(self, node_id: str) -> None:
        self.node_id = node_id
        self.inputs: dict[str, Input] = {}

    def update_inputs(self, inputs: dict[str, Any] | None) -> None:
        if inputs is not None:
            for name, input in inputs.items():
                metadata = Input()

                if len(input) > 1:
                    info: dict[str, Any] = input[1]
                else:
                    info = {}

                metadata.update(input[0], info)
                self.inputs[name] = metadata

    def update(self, inputs: dict[str, Any]) -> None:
        self.update_inputs(inputs.get("required", None))
        self.update_inputs(inputs.get("optional", None))

    @overload
    def input(self, name: str) -> Input: ...
    @overload
    def input(self, name: Sequence[str]) -> Any: ...
    def input(self, name: str | Sequence[str]) -> Any:
        if isinstance(name, str):
            try:
                return self.inputs[name]
            except KeyError:
                raise RuntimeError(f"Input does not exist [{self.node_id}]: {name}")

        else:
            metadata: Any = self

            # If input is a list, then the metadata is a dynamic combo,
            # so we search for the input inside of the dynamic combo.
            for name in name:
                metadata = metadata.input(name)

            return metadata


class NodeMetadata(QObject):
    changed = pyqtSignal()
    saved = pyqtSignal(dict)

    def __init__(self, dir: Path) -> None:
        super().__init__()

        self.dir = dir

        self.data: dict[str, Any] | None = None
        self.cache: dict[str, Node] = {}

        self.saved.connect(self.on_save)


    def save(self, data: dict[str, Any]) -> None:
        self.saved.emit(data)


    def is_loaded(self) -> bool:
        return self.data is not None


    def get(self, node_id: str) -> Node:
        metadata = self.cache.get(node_id)

        if metadata is None:
            metadata = Node(node_id)

            assert self.data is not None

            try:
                info = self.data[node_id]
            except KeyError:
                raise RuntimeError(f"Could not find node [{node_id}]")

            metadata.update(info["input"])

            self.cache[node_id] = metadata

        return metadata


    @pyqtSlot()
    def load(self) -> None:
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
    def on_save(self, data: dict[str, Any]) -> None:
        with Perf("NodeMetadata.save"):
            self.data = data
            self.cache = {}

            with open(self.dir / "node_metadata.json", "w") as file:
                dump(data, file, indent=2)

        assert self.data is not None
        self.changed.emit()


class SettingsFile(Storage):
    def __init__(self, path: Path, defaults: dict[str, Any]) -> None:
        super().__init__(self._load(path))
        self.path = path
        self.defaults = defaults


    @staticmethod
    def _load(path: Path) -> dict[str, Any]:
        try:
            with open(path, "r") as file:
                return load(file)
        except FileNotFoundError:
            return {}


    def _get_default(self, key: str) -> Any:
        return self.defaults[key]


    def _save(self) -> None:
        with open(self.path, "w") as file:
            dump(self._serialized, file, indent=2)


class Workflow:
    def __init__(self, file: dict[str, Any], is_hidden: PathValue[bool]) -> None:
        self.file = file
        self._is_hidden = is_hidden

    def id(self) -> str:
        return self.file["id"]

    def icon(self) -> str:
        return self.file["icon"]

    def name(self) -> str:
        return self.file["name"]

    def global_widgets(self) -> list[dict[str, Any]]:
        return self.file.get("global_widgets", [])

    def document_widgets(self) -> list[dict[str, Any]]:
        return self.file.get("document_widgets", [])

    def graph(self) -> dict[str, Any]:
        return self.file["graph"]

    def is_hidden(self) -> bool:
        return self._is_hidden.get()


class Workflows(QObject):
    changed = pyqtSignal()

    def __init__(self, parent: QObject | None, settings: Dict, order: PathValue[list[JSON]], folder: Path, defaults: dict[str, Any]) -> None:
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
    def _load(folder: Path) -> dict[str, dict[str, Any]]:
        files: dict[str, dict[str, Any]] = {}

        for filename in os.listdir(folder):
            id = Path(filename).stem

            with open(folder / filename, "r") as file:
                files[id] = load(file)

        return files


    def _process_order(self) -> None:
        new_order: list[str] = []
        seen: set[str] = set()
        last_default = 0

        for id in cast(list[str], self.order.get()):
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
        for id in cast(list[str], self.order.default()):
            if not id in seen:
                new_order.insert(last_default, id)
                seen.add(id)
                last_default += 1

        for id in self.defaults.keys():
            assert id in seen

        def sort_files(file: tuple[str, dict[str, Any]]) -> tuple[str, str]:
            value = file[1]
            return (value["name"].casefold(), value["id"])

        # Adds user workflows that aren't in the order.
        for id, _ in sorted(self.files.items(), key=sort_files):
            if not id in seen:
                new_order.append(id)

        self.order.set(cast(list[JSON], new_order))


    def _get_file(self, id: str) -> dict[str, Any]:
        try:
            return self.defaults[id]
        except KeyError:
            return self.files[id]


    def get_all(self) -> list[Workflow]:
        return [self.get(id) for id in cast(list[str], self.order.get())]


    def get(self, id: str) -> Workflow:
        file = self._get_file(id)
        return Workflow(file, self.settings.dict(id).value("is_hidden", bool, default=False))


    def set(self, id: str, value: dict[str, Any]) -> bool:
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


    def remove(self, id: str) -> bool:
        del self.files[id]

        try:
            os.remove(self.folder / (id + ".json"))
        except FileNotFoundError:
            pass

        self.changed.emit()
        return True


    def clear(self) -> bool:
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


    def snapshot(self) -> dict[str, dict[str, Any]]:
        snapshots: dict[str, dict[str, Any]] = {}

        for id, value in self.files.items():
            snapshots[id] = loads(dumps(value))

        return snapshots


    def restore_snapshot(self, snapshots: dict[str, dict[str, Any]]) -> None:
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


def load_default_file(filename: str) -> dict[str, Any]:
    folder = Path(__file__).parent / "defaults"

    try:
        with open(folder / filename, "r") as file:
            return load(file)
    except FileNotFoundError:
        return {}


def load_default_folder(folder_name: str) -> dict[str, Any]:
    folder = Path(__file__).parent / "defaults" / folder_name

    defaults: dict[str, Any] = {}

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
    def order(value: str) -> int:
        match value:
            case "none": return 0
            case "error": return 1
            case "warn": return 2
            case "info": return 3
            case "debug": return 4
            case "trace": return 5
            case _: raise ValueError(f"Invalid log level: {value}")

    def matches(self, value: str) -> bool:
        return LogLevel.order(self.value) <= LogLevel.order(value)


@functools.total_ordering
class DanbooruTagSorter:
    def __init__(self, name: str, post_count: int, is_alias: bool) -> None:
        self.name = name
        self.post_count = post_count
        self.is_alias = is_alias
        self.lowercase = name.casefold()

    def cmp(self, other: "DanbooruTagSorter") -> int:
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

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, DanbooruTagSorter):
            return NotImplemented
        return self.cmp(other) == 0

    def __lt__(self, other: "DanbooruTagSorter") -> bool:
        return self.cmp(other) < 0


class DanbooruTags(QObject):
    changed = pyqtSignal()
    saved = pyqtSignal(dict)

    def __init__(self, dir: Path, settings: Storage) -> None:
        super().__init__()

        self.dir = dir
        self.settings = settings
        self.tags: dict[str, Any] = {}
        self.model = QStringListModel(parent=self)

        self.saved.connect(self.on_save)


    def get[A](self, name: str, default: A) -> Any | A:
        return self.tags.get(name, default)


    def save(self, tags: dict[str, Any]) -> None:
        self.saved.emit(tags)


    @pyqtSlot()
    def load(self) -> None:
        with Perf("DanbooruTags.load"):
            try:
                with open(self.dir / "danbooru_tags.json", "r") as file:
                    self.tags = load(file)
            except FileNotFoundError:
                self.tags = {}

        self.update()


    @pyqtSlot(dict)
    def on_save(self, tags: dict[str, Any]) -> None:
        with Perf("DanbooruTags.save"):
            self.tags = tags

            with open(self.dir / "danbooru_tags.json", "w") as file:
                dump(tags, file, indent=2)

        self.update()


    def update(self) -> None:
        with Perf("DanbooruTags.update"):
            minimum_posts = self.settings.root.value("danbooru_minimum_posts", int).get()
            minimum_characters = self.settings.root.value("autocomplete_minimum_characters", int).get()

            tags: list[DanbooruTagSorter] = []

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

    def __init__(self, parent: QObject | None) -> None:
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

        self.worker_thread = Thread(self)

        self.worker_thread.move(self.node_metadata)
        self.worker_thread.started.connect(self.node_metadata.load)

        self.worker_thread.move(self.danbooru_tags)
        self.worker_thread.started.connect(self.danbooru_tags.load)

        self.worker_thread.start()


    def with_selected_workflow[A](self, f: Callable[[Dict], PathValue[A]]) -> Map[str, A]:
        return self.settings.root.value("selected_workflow", str).map(lambda x: f(self.settings.root.dict("workflows").dict(x)))


    def cleanup(self) -> contextlib.AbstractContextManager[None]:
        return self.worker_thread.stop()


    def clear_log(self) -> None:
        with Perf("clear_log"):
            # Deletes the log file
            with open(self.dir / "debug.log", "w"):
                pass

    def log_str(self, str: str, *, level: LogLevel) -> None:
        if level.matches(self.logging_level.get()):
            with open(self.dir / "debug.log", "a") as file:
                time = timestamp_local()
                file.write(f"[{time} {level.name}] {str}")
                file.write("\n\n")

    def log_json(self, json: Any, *, level: LogLevel, label: str | None = None) -> None:
        if level.matches(self.logging_level.get()):
            with open(self.dir / "debug.log", "a") as file:
                time = timestamp_local()
                if label is None:
                    file.write(f"[{time} {level.name}] ")
                else:
                    file.write(f"[{time} {level.name}] {label}: ")
                dump(json, file, indent=2)
                file.write("\n\n")


    def snapshot(self) -> tuple[dict[str, JSON], dict[str, JSON], dict[str, JSON], dict[str, dict[str, Any]]]:
        return (
            self.settings.snapshot(),
            self.bundles.snapshot(),
            self.presets.snapshot(),
            self.workflows.snapshot(),
        )


    def restore_snapshot(self, snapshot: tuple[dict[str, JSON], dict[str, JSON], dict[str, JSON], dict[str, dict[str, Any]]]) -> None:
        self.settings.restore_snapshot(snapshot[0])
        self.bundles.restore_snapshot(snapshot[1])
        self.presets.restore_snapshot(snapshot[2])
        self.workflows.restore_snapshot(snapshot[3])


    def restore_defaults(self) -> None:
        snapshot = self.snapshot()

        try:
            self.settings.replace_serialized({})
            self.bundles.replace_serialized({})
            self.presets.replace_serialized({})
            self.workflows.clear()
        except:
            self.restore_snapshot(snapshot)
            raise
