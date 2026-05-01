from PyQt6.QtCore import QObject, pyqtSignal


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


    def remove(self):
        if self.root is not None:
            value = self.root.values.get(self.id, None)

            if value is not None:
                if len(value) > self.index:
                    del value[self.index]

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
        if self.root is not None:
            old_value = self.root.values.get(self.id, None)

            if old_value is None:
                old_value = []
                self.root.values[self.id] = old_value

            while len(old_value) <= self.index:
                old_value.append(None)

            if old_value[self.index] != value:
                old_value[self.index] = value

                print(f"Saving {self.id} {self.index} {value}")

                self.root.save()
                return True

        return False


class UiSubInputs:
    def __init__(self, root, parent):
        self.root = root
        self.parent = parent
        self.inputs = []


    def remove_all(self):
        if len(self.inputs) > 0:
            # We sort the inputs so that the largest index is first,
            # so that way the indexes will remain intact when removing.
            self.inputs.sort(key=lambda x: x.index, reverse=True)

            print([x.index for x in self.inputs])

            changed = False
            enable_save = self.root.enable_save

            try:
                self.root.enable_save = False

                for input in self.inputs:
                    if input.remove():
                        changed = True

            finally:
                self.root.enable_save = enable_save

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
