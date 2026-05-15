import json
import contextlib
from enum import Enum, auto


class Listener:
    def __init__(self, item, listener):
        self.item = item
        self.listener = listener

    def stop(self):
        self.item.listeners.remove(self.listener)


class Item:
    def __init__(self, root, serialized, id, default):
        is_default = False

        try:
            value = serialized[id]
        except KeyError:
            value = default
            is_default = True

        self.root = root
        self.serialized = serialized
        self.id = id
        self.default = default
        self.is_default = is_default
        self.value = value
        self.listeners = []


    @classmethod
    def from_serialized(cls, root, serialized, id, default):
        return cls(root, serialized, id, default)


    def add_listener(self, f):
        self.listeners.append(f)
        return Listener(self, f)


    def notify_listeners(self):
        for listener in self.listeners:
            listener()


    def disconnect(self):
        self.root = None


    def get(self):
        return self.value


    def set(self, value, *, save=True, notify_listeners=True):
        assert self.root is not None

        old_value = self.value

        self.value = value
        self.is_default = False

        if save:
            try:
                # We only save if the new value is different from the old value.
                should_save = self.serialized[self.id] != value
            except KeyError:
                should_save = True

            self.serialized[self.id] = value

            if should_save:
                self.root.save()

        if notify_listeners and old_value != self.value:
            self.notify_listeners()


    def reset_to_default(self, *, save=True, notify_listeners=True):
        assert self.root is not None

        should_save = save and not self.is_default

        old_value = self.value

        self.value = self.default
        self.is_default = True

        if should_save:
            del self.serialized[self.id]
            self.root.save()

        if notify_listeners and old_value != self.value:
            self.notify_listeners()


    def change_default(self, new_default):
        assert self.root is not None

        self.default = new_default

        if self.is_default:
            self.reset_to_default(save=False)


class DictBase:
    def __init__(self, root, serialized):
        self.root = root
        self.serialized = serialized
        self.items = {}


    def _make_item(self, id, default, item_class):
        metadata = self.root._metadata(id, default)
        id = metadata.get_id()

        try:
            return self.items[id]

        except KeyError:
            item = item_class.from_serialized(self.root, self.serialized, id, metadata.get_default())
            self.items[id] = item
            return item


    def item(self, id, *, default=None):
        return self._make_item(id, default, self.root.ITEM_CLASS)

    def item_dict(self, id, *, default=None):
        return self._make_item(id, default, self.root.ITEM_DICT_CLASS)

    def item_list(self, id, *, default=None):
        return self._make_item(id, default, self.root.ITEM_LIST_CLASS)


class ItemDict(DictBase):
    @classmethod
    def from_serialized(cls, root, serialized, id, default):
        if default is None:
            default = {}

        try:
            value = serialized[id]
        except KeyError:
            value = default

        assert isinstance(value, dict)
        assert isinstance(default, dict)

        return cls(root, value)


    def disconnect(self):
        try:
            for item in self.items.values():
                item.disconnect()
        finally:
            self.root = None


class ItemList:
    def __init__(self, root, serialized, id, values):
        self.root = root
        self.serialized = serialized
        self.id = id
        self.values = values
        self.items = [ItemDict(self.root, value) for value in values]


    @classmethod
    def from_serialized(cls, root, serialized, id, default):
        if default is None:
            default = []

        try:
            values = serialized[id]
        except KeyError:
            values = default

        assert isinstance(values, list)
        assert isinstance(default, list)

        return cls(root, serialized, id, values)


    def disconnect(self):
        try:
            for item in self.items:
                item.disconnect()
        finally:
            self.root = None


    def move(self, old_index, new_index):
        assert self.root is not None

        assert old_index != new_index
        assert new_index >= 0
        assert new_index < len(self.values)

        assert self.serialized[self.id] is self.values

        self.items.insert(new_index, self.items.pop(old_index))
        self.values.insert(new_index, self.values.pop(old_index))

        self.root.save()


    def remove(self, index):
        assert self.root is not None

        item = self.items.pop(index)
        item.disconnect()

        assert self.serialized[self.id] is self.values
        del self.values[index]

        if len(self.values) == 0:
            del self.serialized[self.id]

        self.root.save()


    def append(self, value):
        item = ItemDict(self.root, value)

        self.values.append(value)
        self.items.append(item)

        self.serialized[self.id] = self.values
        self.root.save()

        return item


class Metadata:
    def __init__(self, id, default):
        self.id = id
        self.default = default

    def get_id(self):
        return self.id

    def get_default(self):
        return self.default


class SaveState(Enum):
    SHOULD_SAVE = auto()
    DELAY_SAVE = auto()
    DID_SAVE = auto()


class Storage(DictBase):
    # These attributes are intended to be overwritten by subclasses
    ITEM_CLASS = Item
    ITEM_DICT_CLASS = ItemDict
    ITEM_LIST_CLASS = ItemList

    # These methods are intended to be overwritten by subclasses
    def _metadata(self, id, default):
        return Metadata(id, default)

    def _save(self):
        pass


    def __init__(self, serialized):
        super().__init__(self, serialized)
        self.save_state = SaveState.SHOULD_SAVE


    @contextlib.contextmanager
    def delay_save(self):
        save_state = self.save_state

        # This temporarily stops it from saving.
        self.save_state = SaveState.DELAY_SAVE

        try:
            yield
        finally:
            # If we attempted to save, then now it's time to actually save.
            if self.save_state == SaveState.DID_SAVE:
                # We restore the old state before we save, so that way if
                # delay_save is nested, it will wait until the outer-most
                # delay_save is finished before saving.
                self.save_state = save_state
                self.save()
            else:
                self.save_state = save_state


    def save(self):
        if self.save_state == SaveState.SHOULD_SAVE:
            self._save()
        else:
            self.save_state = SaveState.DID_SAVE


    def disconnect_items(self):
        try:
            for item in self.items.values():
                item.disconnect()
        finally:
            self.items = {}


    def replace_serialized(self, new_serialized):
        self.serialized = new_serialized
        self.disconnect_items()


    def clear(self):
        if self.serialized != {}:
            self.replace_serialized({})
            self.save()
            return True
        return False


    def snapshot(self):
        return json.loads(json.dumps(self.serialized))


    def restore_snapshot(self, snapshot):
        if self.serialized != snapshot:
            self.replace_serialized(snapshot)
            self.save()
            return True
        return False
