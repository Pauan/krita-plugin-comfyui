import contextlib
from PyQt6.QtCore import QObject, pyqtSignal


# Removes None from the end of the list
def prune(values):
    for index in reversed(range(0, len(values))):
        if values[index] is None:
            values.pop()
        else:
            break


class UiInput:
    def __init__(self, root, id, index):
        self.root = root
        self.id = id
        self.index = index


    def format_tooltip(self, tooltip):
        if tooltip is None:
            return f"[{self.id}]"
        else:
            return f"[{self.id}]: {tooltip}"


    # This does not adjust the index of other inputs.
    def move_up(self):
        assert self.index > 0

        if self.root is not None:
            values = self.root.values.get(self.id, None)

            if values is not None:
                if len(values) > (self.index - 1):
                    while len(values) <= self.index:
                        values.append(None)

                    value = values.pop(self.index)
                    self.index -= 1
                    values.insert(self.index, value)

                    prune(values)

                    self.root.save()
                    return True

        return False


    # This does not adjust the index of other inputs.
    def move_down(self):
        if self.root is not None:
            values = self.root.values.get(self.id, None)

            if values is not None:
                if len(values) > self.index:
                    while len(values) <= (self.index + 1):
                        values.append(None)

                    value = values.pop(self.index)
                    self.index += 1
                    values.insert(self.index, value)

                    prune(values)

                    self.root.save()
                    return True

        return False


    # This does not adjust the index of other inputs.
    def remove(self):
        if self.root is not None:
            values = self.root.values.get(self.id, None)

            if values is not None:
                if len(values) > self.index:
                    del values[self.index]

                    prune(values)

                    root = self.root
                    self.root = None

                    root.save()
                    return True

        return False


    def get(self, default=None):
        if self.root is None:
            return default

        else:
            value = self.root.values.get(self.id, None)

            if value is not None:
                try:
                    value = value[self.index]
                except IndexError:
                    return default

            if value is None:
                return default
            else:
                return value


    def set(self, value):
        assert value is not None

        if self.root is not None:
            old_values = self.root.values.get(self.id, None)

            if old_values is None:
                old_values = []
                self.root.values[self.id] = old_values

            while len(old_values) <= self.index:
                old_values.append(None)

            if old_values[self.index] != value:
                old_values[self.index] = value

                print(f"Saving {self.id} {self.index} {value}")

                self.root.save()
                return True

        return False


class UiSubInputs:
    def __init__(self, root, parent):
        self.root = root
        self.parent = parent
        self.inputs = []


    @contextlib.contextmanager
    def process_inputs(self, lowest_first):
        if len(self.inputs) > 0:
            # We sort the inputs by index, so that way if there are multiple inputs
            # with the same id, they will be processed in the correct order.
            self.inputs.sort(key=lambda x: x.index, reverse=not lowest_first)

            with self.root.disable_save():
                yield self.inputs


    # This does not adjust the index of other inputs.
    def move_all_up(self):
        changed = False

        # We move the inputs with the lowest index first, so that way it doesn't harm the other indexes.
        with self.process_inputs(lowest_first=True) as inputs:
            for input in inputs:
                if input.move_up():
                    changed = True

        if changed:
            self.root.save()


    # This does not adjust the index of other inputs.
    def move_all_down(self):
        changed = False

        # We move the inputs with the highest index first, so that way it doesn't harm the other indexes.
        with self.process_inputs(lowest_first=False) as inputs:
            for input in inputs:
                if input.move_down():
                    changed = True

        if changed:
            self.root.save()


    # This does not adjust the index of other inputs.
    def remove_all(self):
        changed = False

        # We remove the inputs with the highest index first, so that way it doesn't harm the other indexes.
        with self.process_inputs(lowest_first=False) as inputs:
            for input in inputs:
                if input.remove():
                    changed = True

        if changed:
            self.root.save()


    def sub_inputs(self):
        return UiSubInputs(self.root, self)


    def input(self, id, index):
        input = self.root.input(id, index)

        self.inputs.append(input)

        parent = self.parent

        while parent is not None:
            parent.inputs.append(input)
            parent = parent.parent

        return input


class UiInputs(QObject):
    changed = pyqtSignal()

    def __init__(self):
        super().__init__()

        self.enable_save = True
        self.document = None
        self.values = {}


    def current(self):
        return self.values


    def clear(self):
        # If values isn't empty...
        if not bool(self.values):
            self.values = {}
            self.save()


    @contextlib.contextmanager
    def disable_save(self):
        enable_save = self.enable_save

        try:
            self.enable_save = False
            yield
        finally:
            self.enable_save = enable_save


    def save(self):
        saved = False

        if self.enable_save:
            if self.document is not None:
                self.document.set_key_json("krita_comfyui/ui_inputs", "krita_comfyui: Stored UI Inputs", self.values)
                print("Saving")
                print(self.values)
                saved = True

            self.changed.emit()

        return saved


    def input(self, id, index):
        return UiInput(self, id, index)


    def sub_inputs(self):
        return UiSubInputs(self, None)


    def load_document(self, document):
        self.document = document

        if self.document is not None:
            self.values = self.document.get_key_json("krita_comfyui/ui_inputs")

            print("Loading")
            print(self.values)

            if self.values is None:
                self.values = {}

        else:
            self.values = {}

        self.changed.emit()
