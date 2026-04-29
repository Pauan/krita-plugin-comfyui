from PyQt6.QtCore import QObject, pyqtSignal


class UiInput:
    def __init__(self, inputs, id, index):
        self.inputs = inputs
        self.id = id
        self.index = index


    def get(self):
        value = self.inputs.values.get(self.id, None)

        if value is not None:
            try:
                return value[self.index]
            except IndexError:
                pass


    def set(self, value):
        old_value = self.inputs.values.get(self.id, None)

        if old_value is None:
            old_value = []
            self.inputs.values[self.id] = old_value

        while len(old_value) <= self.index:
            old_value.append(None)

        if old_value[self.index] != value:
            old_value[self.index] = value

            print("Saving {} {} {}".format(self.id, self.index, value))

            self.inputs.save()
            self.inputs.changed.emit()


class UiInputs(QObject):
    changed = pyqtSignal()

    def __init__(self):
        super().__init__()

        self.document = None
        self.values = {}


    def current(self):
        return self.values


    def save(self):
        if self.document is not None:
            self.document.set_key_json("krita_comfyui/ui_inputs", "krita_comfyui: Stored UI Inputs", self.values)
            print("Saving")
            print(self.values)


    def input(self, id, index):
        return UiInput(self, id, index)


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
