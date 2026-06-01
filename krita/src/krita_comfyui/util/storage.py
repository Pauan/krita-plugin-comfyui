import json
import contextlib
from shared import JSON
from typing import Protocol
from collections.abc import Callable


class Listener(Protocol):
    def stop(self):
        ...


class LeafListener(Listener):
    def __init__(self, storage: "Storage", path: tuple[str | int, ...], receiver: Callable[[], None]):
        self._storage = storage
        self._path = path
        self._receiver = receiver

    def stop(self):
        self._storage.remove_listener(self._path, self._receiver)


class PathLeaf[A](Protocol):
    _storage: "Storage"

    _path: tuple[str | int, ...]

    def get(self) -> A:
        ...

    def add_listener(self, f: Callable[[], None]) -> Listener:
        self._storage.add_listener(self._path, f)
        return LeafListener(self._storage, self._path, f)

    def with_value(self, f: Callable[[A], None]):
        f(self.get())
        return self.add_listener(lambda: f(self.get()))

    def map[B](self, f: Callable[[A], "PathValue[B]"]) -> "Map[A, B]":
        return Map(self._storage, self, f)


class PathValue[A](PathLeaf[A]):
    def key(self) -> str:
        ...

    def default(self) -> A:
        ...

    def set(self, value: A) -> bool:
        ...

    def remove(self) -> bool:
        ...


class Path[A](PathLeaf[A]):
    def _ensure_exists(self) -> A:
        ...

    def _remove(self):
        ...


class MapListener[A, B](Listener):
    def __init__(self, map: "Map[A, B]", receiver: Callable[[], None]):
        self._map = map
        self._receiver = receiver

    def stop(self):
        self._map.remove_listener(self._receiver)


class Map[A, B](PathValue[B]):
    def __init__(self, storage: "Storage", parent: PathLeaf[A], map: Callable[[A], PathValue[B]]):
        self._storage = storage
        self._parent = parent
        self._map = map

        self._listeners: list[Callable[[], None]] = []
        self._listener: Listener | None = None

        self._value = map(parent.get())
        self._path = self._value._path

        self._parent_listener = parent.add_listener(self._update)


    def stop(self):
        self._parent_listener.stop()

        self._listeners.clear()

        if self._listener is not None:
            self._listener.stop()
            self._listener = None


    def _emit(self):
        for listener in self._listeners:
            listener()


    def _update(self):
        self._value = self._map(self._parent.get())
        self._path = self._value._path

        if self._listener is not None:
            self._listener.stop()
            self._listener = self._value.add_listener(self._emit)

        self._emit()


    def key(self) -> str:
        return self._value.key()

    def default(self) -> B:
        return self._value.default()

    def get(self) -> B:
        return self._value.get()

    def set(self, value: B):
        return self._value.set(value)

    def remove(self):
        return self._value.remove()


    def add_listener(self, f: Callable[[], None]) -> Listener:
        if self._listener is None:
            self._listener = self._value.add_listener(self._emit)

        self._listeners.append(f)
        return MapListener(self, f)


    def remove_listener(self, f: Callable[[], None]):
        self._listeners.remove(f)

        if len(self._listeners) == 0:
            if self._listener is not None:
                self._listener.stop()
                self._listener = None


class PathDict(Path[dict[str, JSON]]):
    def dict(self, key: str, *, optional: bool=True) -> "Dict":
        return Dict(self._storage, self, key, optional)

    def list(self, key: str, *, optional: bool=True) -> "List":
        return List(self._storage, self, key, optional)

    def value[A: JSON](self, key: str, cls: type[A], *, default: A | None=None) -> "Value[A]":
        return Value(self._storage, self, key, cls, default)


class Root(PathDict):
    _path: tuple[str | int, ...] = tuple()

    def __init__(self, storage: "Storage"):
        self._storage = storage

    def get(self) -> dict[str, JSON]:
        return self._storage._serialized # pyright: ignore [reportPrivateUsage]

    def _ensure_exists(self) -> dict[str, JSON]:
        return self._storage._serialized # pyright: ignore [reportPrivateUsage]

    def _remove(self):
        assert len(self._storage._serialized) == 0 # pyright: ignore [reportPrivateUsage]


class Dict(PathDict):
    def __init__(self, storage: "Storage", parent: Path[dict[str, JSON]], key: str, optional: bool):
        self._storage = storage
        self._parent = parent
        self._key = key
        self._optional = optional
        self._path = (*parent._path, key)


    def get(self) -> dict[str, JSON]:
        parent = self._parent.get()

        try:
            out = parent[self._key]

            if not isinstance(out, dict):
                raise TypeError(f"{self._key} is not a dict")

            return out

        except KeyError:
            if self._optional:
                return {}
            else:
                raise


    def _ensure_exists(self) -> dict[str, JSON]:
        parent = self._parent._ensure_exists()

        try:
            out = parent[self._key]

            if not isinstance(out, dict):
                raise TypeError(f"{self._key} is not a dict")

            return out

        except KeyError:
            default: dict[str, JSON] = {}
            parent[self._key] = default
            return default


    def _remove(self):
        parent = self._parent.get()

        try:
            value = parent.pop(self._key)
            assert isinstance(value, dict)
            assert len(value) == 0
            changed = True

        except KeyError:
            changed = False

        if changed and len(parent) == 0:
            self._parent._remove()


class List(Path[list[JSON]]):
    def __init__(self, storage: "Storage", parent: Path[dict[str, JSON]], key: str, optional: bool):
        self._storage = storage
        self._parent = parent
        self._key = key
        self._optional = optional
        self._path = (*parent._path, key)


    def get(self) -> list[JSON]:
        parent = self._parent.get()

        try:
            out = parent[self._key]

            if not isinstance(out, list):
                raise TypeError(f"{self._key} is not a list")

            return out

        except KeyError:
            if self._optional:
                return []
            else:
                raise


    def _ensure_exists(self) -> list[JSON]:
        parent = self._parent._ensure_exists()

        try:
            out = parent[self._key]

            if not isinstance(out, list):
                raise TypeError(f"{self._key} is not a list")

            return out

        except KeyError:
            default: list[JSON] = []
            parent[self._key] = default
            return default


    def _remove(self):
        parent = self._parent.get()

        try:
            value = parent.pop(self._key)
            assert isinstance(value, list)
            assert len(value) == 0
            changed = True

        except KeyError:
            changed = False

        if changed and len(parent) == 0:
            self._parent._remove()


    def append(self, value: dict[str, JSON]):
        list = self._ensure_exists()
        list.append(value)
        self._storage.on_changed(self._path)


    def remove(self, index: int):
        assert index >= 0

        list = self.get()

        assert index < len(list)

        value = list.pop(index)

        if len(list) == 0:
            self._remove()

        self._storage.on_changed(self._path)
        return value


    def move(self, old_index: int, new_index: int):
        assert old_index != new_index
        assert old_index >= 0
        assert new_index >= 0

        list = self.get()

        assert old_index < len(list)
        assert new_index < len(list)

        list.insert(new_index, list.pop(old_index))

        self._storage.on_changed(self._path)


    def index(self, index: int):
        return Index(self._storage, self, index)


class Index(PathDict):
    def __init__(self, storage: "Storage", parent: Path[list[JSON]], index: int):
        self._storage = storage
        self._parent = parent
        self._index = index
        self._path = (*parent._path, index)


    def get(self) -> dict[str, JSON]:
        parent = self._parent.get()
        out = parent[self._index]

        if not isinstance(out, dict):
            raise TypeError(f"{self._index} is not a dict")

        return out


    def _ensure_exists(self) -> dict[str, JSON]:
        parent = self._parent._ensure_exists()

        #for _ in range(len(parent), self.index + 1):
            #parent.append({})

        out = parent[self._index]

        if not isinstance(out, dict):
            raise TypeError(f"{self._index} is not a dict")

        return out


    def _remove(self):
        pass


class Value[A: JSON](PathValue[A]):
    def __init__(self, storage: "Storage", parent: Path[dict[str, JSON]], key: str, cls: type[A], default: A | None):
        self._storage = storage
        self._parent = parent
        self._key = key
        self._cls = cls
        self._default = default
        self._path = (*parent._path, key)


    def key(self) -> str:
        return self._key


    def default(self) -> A:
        if self._default is None:
            default = self._storage._get_default(self._key) # pyright: ignore [reportPrivateUsage]
            assert isinstance(default, self._cls)
            return default
        else:
            return self._default


    def get(self) -> A:
        parent = self._parent.get()

        try:
            out = parent[self._key]

            if not isinstance(out, self._cls):
                raise TypeError(f"{self._key} is not a {self._cls.__name__}")

            return out

        except KeyError:
            return self.default()


    def set(self, value: A):
        parent = self._parent._ensure_exists() # pyright: ignore [reportPrivateUsage]

        try:
            changed = parent[self._key] != value
        except KeyError:
            changed = True

        if changed:
            parent[self._key] = value
            self._storage.on_changed(self._path)

        return changed


    def remove(self):
        parent = self._parent.get()

        try:
            del parent[self._key]
            changed = True
        except KeyError:
            changed = False

        if changed:
            if len(parent) == 0:
                self._parent._remove() # pyright: ignore [reportPrivateUsage]

            self._storage.on_changed(self._path)

        return changed


class SaveState:
    def __init__(self):
        self.enabled = True
        self.delayed = False
        self.did_save = False


    def try_save(self) -> bool:
        if self.enabled:
            if self.delayed:
                self.did_save = True
            else:
                return True
        return False


    def start_delay(self) -> bool:
        delayed = self.delayed
        self.delayed = True
        return delayed


    def end_delay(self, delayed: bool) -> bool:
        # If we attempted to save, then now it's time to actually save.
        if self.enabled and self.did_save:
            self.did_save = False
            # We restore the old state before we save, so that way if
            # delay_save is nested, it will wait until the outer-most
            # delay_save is finished before saving.
            self.delayed = delayed
            return True
        else:
            self.delayed = delayed
            return False


class Storage:
    def __init__(self, serialized: dict[str, JSON]):
        self.root = Root(self)

        self._save_state = SaveState()
        self._serialized = serialized
        self._listeners: dict[tuple[str | int, ...], list[Callable[[], None]]] = {}


    # These methods are intended to be overwritten by subclasses
    def _get_default[A](self, key: str) -> JSON:
        raise ValueError("default must be provided")

    def _save(self):
        pass


    def save(self):
        if self._save_state.try_save():
            self._save()


    @contextlib.contextmanager
    def delay_save(self):
        delayed = self._save_state.start_delay()
        try:
            yield
        finally:
            if self._save_state.end_delay(delayed):
                self.save()


    def replace_serialized(self, new_serialized: dict[str, JSON], *, notify_listeners: bool=True):
        if self._serialized != new_serialized:
            self._serialized = new_serialized

            self.save()

            if notify_listeners:
                for listeners in self._listeners.values():
                    for listener in listeners:
                        listener()

            return True

        return False


    def snapshot(self) -> dict[str, JSON]:
        return json.loads(json.dumps(self._serialized))


    def restore_snapshot(self, snapshot: dict[str, JSON], *, notify_listeners: bool=True) -> bool:
        return self.replace_serialized(snapshot, notify_listeners=notify_listeners)


    def on_changed(self, path: tuple[str | int, ...]):
        self.save()

        try:
            listeners = self._listeners[path]
        except KeyError:
            return

        for listener in listeners:
            listener()


    def add_listener(self, path: tuple[str | int, ...], f: Callable[[], None]):
        try:
            listeners = self._listeners[path]
        except KeyError:
            listeners = self._listeners[path] = []

        listeners.append(f)


    def remove_listener(self, path: tuple[str | int, ...], f: Callable[[], None]):
        try:
            listeners = self._listeners[path]
        except KeyError:
            return

        try:
            listeners.remove(f)
        except ValueError:
            return

        if len(listeners) == 0:
            del self._listeners[path]
