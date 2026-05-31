import json
import contextlib
from shared import JSON
from weakref import WeakValueDictionary
from typing import Self, Iterable, overload, cast
from collections.abc import Callable


class Listener[A: JSON]:
    def __init__(self, item: "Item[A]", listener: Callable[[A, A], None]):
        self._item = item
        self._listener = listener

    def stop(self):
        self._item.remove_listener(self._listener)


class Item[A: JSON]:
    def __init__(self, parent: "DictBase", id: str, default: A):
        is_default = False

        try:
            value = parent.serialized[id]

            if not isinstance(value, type(default)):
                raise TypeError(f"{id} must be of type {type(default)}")

        except KeyError:
            value = default
            is_default = True

        self.id = id
        self.default = default
        self.is_default = is_default

        self._value = value

        self._parent = parent
        self._listeners: list[Callable[[A, A], None]] = []


    @classmethod
    def from_serialized(cls, parent: "DictBase", id: str, default: A) -> Self:
        return cls(parent, id, default)


    def add_listener(self, f: Callable[[A, A], None]) -> Listener[A]:
        self._listeners.append(f)
        return Listener(self, f)

    def remove_listener(self, f: Callable[[A, A], None]):
        self._listeners.remove(f)


    def notify_listeners(self, old_value: A):
        new_value = self._value

        if old_value != new_value:
            for listener in self._listeners:
                listener(old_value, new_value)


    def with_value(self, f: Callable[[A], None]) -> Listener[A]:
        def on_change(old: A, new: A):
            assert self._value == new
            f(new)
        f(self._value)
        return self.add_listener(on_change)


    def disconnect(self):
        self._parent = None


    def get(self) -> A:
        return self._value


    def set(self, value: A, *, save: bool=True, notify_listeners: bool=True):
        assert self._parent is not None

        old_value = self._value

        self._value = value
        self.is_default = False

        if save:
            try:
                # We only save if the new value is different from the old value.
                should_save = self._parent.serialized[self.id] != value
            except KeyError:
                should_save = True

            self._parent.ensure_exists()
            self._parent.serialized[self.id] = value

            if should_save:
                self._parent.root.save()

        if notify_listeners:
            self.notify_listeners(old_value)


    def reset_to_default(self, *, save: bool=True, notify_listeners: bool=True):
        assert self._parent is not None

        should_save = save and not self.is_default

        old_value = self._value

        self._value = self.default
        self.is_default = True

        if should_save:
            del self._parent.serialized[self.id]
            self._parent.root.save()

        if notify_listeners:
            self.notify_listeners(old_value)


    def change_default(self, new_default: A):
        assert self._parent is not None

        self.default = new_default

        if self.is_default:
            self.reset_to_default(save=False)


class DictBase:
    def __init__(self, root: "Storage", serialized: dict[str, JSON]):
        self.root = root
        self.serialized = serialized
        self.items: WeakValueDictionary[str, Item[JSON]] = WeakValueDictionary({})


    def ensure_exists(self):
        pass


    @overload
    def _make_item[A: JSON](self, id: str, default: A | None, item_class: type[Item[JSON]]) -> Item[A]: ...

    @overload
    def _make_item(self, id: str, default: dict[str, JSON], item_class: type["ItemDict"]) -> "ItemDict": ...

    @overload
    def _make_item(self, id: str, default: list[dict[str, JSON]], item_class: type["ItemList"]) -> "ItemList": ...

    def _make_item(self, id, default, cache: bool, item_class):
        if cache:
            try:
                return self.items[id]

            except KeyError:
                if default is None:
                    default = self.root._get_default(id)

                item = item_class.from_serialized(self, id, default)
                self.items[id] = item
                return item

        else:
            if default is None:
                default = self.root._get_default(id)

            return item_class.from_serialized(self, id, default)


    def get[A: JSON](self, id: str, *, default: A | None=None) -> A:
        try:
            return cast(A, self.serialized[id])
        except KeyError:
            if default is None:
                return self.root._get_default(id)
            else:
                return default


    def keys(self) -> Iterable[str]:
        return self.serialized.keys()

    def item[A: JSON](self, id: str, *, default: A | None=None, cache=True) -> Item[A]:
        return self._make_item(id, default, cache, self.root.ITEM_CLASS)

    def item_dict(self, id: str, *, default: dict[str, JSON]={}, cache=True) -> "ItemDict":
        return self._make_item(id, default, cache, self.root.ITEM_DICT_CLASS)

    def item_list(self, id: str, *, default: list[dict[str, JSON]]=[], cache=True) -> "ItemList":
        return self._make_item(id, default, cache, self.root.ITEM_LIST_CLASS)


class ItemDict(DictBase):
    def __init__(self, parent, id, value):
        super().__init__(parent.root, value)
        self.id = id
        self.parent = parent


    def ensure_exists(self):
        self.parent.ensure_exists()

        if not self.id in self.parent.serialized:
            self.parent.serialized[self.id] = self.serialized


    @classmethod
    def from_serialized(cls, parent: DictBase, id: str, default: dict[str, JSON]) -> Self:
        assert isinstance(default, dict)

        try:
            value = parent.serialized[id]

            if not isinstance(value, dict):
                raise TypeError(f"{id} must be a dict")

        except KeyError:
            value = default

        return cls(parent, id, value)


    def disconnect(self):
        try:
            for item in self.items.values():
                item.disconnect()
        finally:
            self.root = None


class ItemList:
    def __init__(self, root: "Storage", serialized: dict[str, JSON], id: str, values: list[dict[str, JSON]]):
        self.root = root
        self.serialized = serialized
        self.id = id
        self.values = values
        self.items: list[ItemDict] = [ItemDict(self.root, value) for value in values]


    @classmethod
    def from_serialized(cls, parent: DictBase, id: str, default: list[dict[str, JSON]]) -> Self:
        assert isinstance(default, list)

        try:
            values = parent.serialized[id]

            if not isinstance(values, list):
                raise TypeError(f"{id} must be a list")

        except KeyError:
            values = default

        return cls(parent.root, parent.serialized, id, cast(list[dict[str, JSON]], values))


    def disconnect(self):
        try:
            for item in self.items:
                item.disconnect()
        finally:
            self.root = None


    def move(self, old_index: int, new_index: int):
        assert self.root is not None

        assert old_index != new_index
        assert new_index >= 0
        assert new_index < len(self.values)

        assert self.serialized[self.id] is self.values

        self.items.insert(new_index, self.items.pop(old_index))
        self.values.insert(new_index, self.values.pop(old_index))

        self.root.save()


    def remove(self, index: int):
        assert self.root is not None

        item = self.items.pop(index)
        item.disconnect()

        assert self.serialized[self.id] is self.values
        del self.values[index]

        if len(self.values) == 0:
            del self.serialized[self.id]

        self.root.save()


    def append(self, value: dict[str, JSON]) -> ItemDict:
        assert self.root is not None

        item = ItemDict(self.root, value)

        self.values.append(value)
        self.items.append(item)

        self.serialized[self.id] = cast(JSON, self.values)
        self.root.save()

        return item


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


class Storage(DictBase):
    # These attributes are intended to be overwritten by subclasses
    ITEM_CLASS: type[Item[JSON]] = Item
    ITEM_DICT_CLASS: type[ItemDict] = ItemDict
    ITEM_LIST_CLASS: type[ItemList] = ItemList

    # These methods are intended to be overwritten by subclasses
    def _get_default(self, id: str) -> JSON:
        raise ValueError("default must be provided")

    def _save(self):
        pass


    def __init__(self, serialized: dict[str, JSON]):
        super().__init__(self, serialized)
        self.save_state = SaveState()


    @contextlib.contextmanager
    def delay_save(self):
        delayed = self.save_state.start_delay()
        try:
            yield
        finally:
            if self.save_state.end_delay(delayed):
                self.save()


    def stop(self):
        self.disconnect_items()
        self.root = None
        self.items = cast(WeakValueDictionary[str, Item[JSON]], None)
        self.serialized = None
        self.save_state.enabled = False


    def save(self):
        if self.save_state.try_save():
            self._save()


    def disconnect_items(self):
        try:
            for item in self.items.values():
                item.disconnect()
        finally:
            self.items.clear()


    def replace_serialized(self, new_serialized: dict[str, JSON]):
        self.serialized = new_serialized
        self.disconnect_items()


    def clear(self) -> bool:
        if self.serialized != {}:
            self.replace_serialized({})
            self.save()
            return True
        return False


    def snapshot(self) -> dict[str, JSON]:
        return json.loads(json.dumps(self.serialized))


    def restore_snapshot(self, snapshot: dict[str, JSON]) -> bool:
        if self.serialized != snapshot:
            self.replace_serialized(snapshot)
            self.save()
            return True
        return False
