import contextlib
from PyQt6.QtCore import QObject, pyqtSignal
from .graph import WorkflowGraph, WorkflowError


def all_children(children):
    for child in children:
        yield child

        children = child.get("children", None)
        if children is not None:
            yield from all_children(children)


# Removes None from the end of the list
def remove_none(values):
    for index in reversed(range(0, len(values))):
        if values[index] is None:
            values.pop()
        else:
            break


class UiInput:
    def __init__(self, root, id, index, default, value):
        self.root = root
        self.id = id
        self.index = index
        self.default = default
        self.value = value


    def format_tooltip(self, tooltip):
        if tooltip is None:
            return f"[{self.id}]"
        else:
            return f"[{self.id}]: {tooltip}"


    # This does not adjust the index of other inputs.
    def move_up(self):
        assert self.index > 0

        if self.root is not None:
            # Move the value in the inputs
            values = self.root.inputs[self.id]
            values.insert(self.index - 1, values.pop(self.index))

            # Move the value in the serialized
            values = self.root.serialized.get(self.id, None)

            if values is not None:
                if len(values) > (self.index - 1):
                    while len(values) <= self.index:
                        values.append(None)

                    values.insert(self.index - 1, values.pop(self.index))

                    remove_none(values)

                    if len(values) == 0:
                        del self.root.serialized[self.id]

                    self.root.save()

            self.index -= 1


    # This does not adjust the index of other inputs.
    def move_down(self):
        if self.root is not None:
            # Move the value in the inputs
            values = self.root.inputs[self.id]
            values.insert(self.index + 1, values.pop(self.index))

            # Move the value in the serialized
            values = self.root.serialized.get(self.id, None)

            if values is not None:
                if len(values) > self.index:
                    while len(values) <= (self.index + 1):
                        values.append(None)

                    values.insert(self.index + 1, values.pop(self.index))

                    remove_none(values)

                    if len(values) == 0:
                        del self.root.serialized[self.id]

                    self.root.save()

            self.index += 1


    # This does not adjust the index of other inputs.
    def remove(self):
        if self.root is not None:
            # Remove the value in the inputs
            values = self.root.inputs[self.id]
            del values[self.index]

            # Remove the value in the serialized
            values = self.root.serialized.get(self.id, None)

            if values is not None:
                if len(values) > self.index:
                    del values[self.index]

                    remove_none(values)

                    if len(values) == 0:
                        del self.root.serialized[self.id]

                    self.root.save()

            self.root = None


    def get(self):
        return self.value


    def set(self, value):
        assert value is not None

        if self.value != value:
            self.value = value

            if self.root is not None:
                # Set the value in the inputs
                values = self.root.inputs[self.id]
                values[self.index] = self.value

                # Set the value in the serialized
                values = self.root.serialized.get(self.id, None)

                if values is None:
                    values = []
                    self.root.serialized[self.id] = values

                while len(values) <= self.index:
                    values.append(None)

                values[self.index] = self.value

                print(f"Saving {self.id} {self.index} {self.value}")

                self.root.save()


    def reset_to_default(self):
        self.value = self.default

        if self.root is not None:
            # Set the value in the inputs
            values = self.root.inputs[self.id]
            values[self.index] = self.value

            # Set the value in the serialized
            values = self.root.serialized.get(self.id, None)

            if values is not None:
                if len(values) > self.index:
                    values[self.index] = None

                    remove_none(values)

                    if len(values) == 0:
                        del self.root.serialized[self.id]

                    self.root.save()


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

            with self.root.batch_save():
                yield self.inputs


    # This does not adjust the index of other inputs.
    def move_all_up(self):
        # We move the inputs with the lowest index first, so that way it doesn't harm the other indexes.
        with self.process_inputs(lowest_first=True) as inputs:
            for input in inputs:
                input.move_up()


    # This does not adjust the index of other inputs.
    def move_all_down(self):
        # We move the inputs with the highest index first, so that way it doesn't harm the other indexes.
        with self.process_inputs(lowest_first=False) as inputs:
            for input in inputs:
                input.move_down()


    # This does not adjust the index of other inputs.
    def remove_all(self):
        # We remove the inputs with the highest index first, so that way it doesn't harm the other indexes.
        with self.process_inputs(lowest_first=False) as inputs:
            for input in inputs:
                input.remove()


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


class Workflow(QObject):
    def __init__(self, settings):
        super().__init__()

        self.settings = settings

        self.disable_save = None

        self.id = ""
        self.document = None
        self.graph = None
        self.layout = None

        self.serialized = {}
        self.defaults = {}
        self.inputs = {}


    def input(self, id, index):
        default = self.defaults[id]

        values = self.inputs[id]

        while len(values) <= index:
            values.append(default)

        return UiInput(self, id, index, default, values[index])


    def sub_inputs(self):
        return UiSubInputs(self, None)


    # Batches multiple save operations into a single save
    @contextlib.contextmanager
    def batch_save(self):
        disable_save = self.disable_save

        self.disable_save = 0

        try:
            yield
        finally:
            # A save happened
            if self.disable_save > 0:
                self.disable_save = None
                self.save()

            self.disable_save = disable_save


    def save_workflow_id(self):
        assert self.document is not None
        assert self.id is not None
        self.document.set_key_str("krita_comfyui/workflow_id", "krita_comfyui: Workflow ID", self.id)


    def save(self):
        if self.disable_save is None:
            if self.id != "" and self.document is not None:
                print("Saving")
                print(self.serialized)
                self.document.set_key_json(f"krita_comfyui/ui_inputs/{self.id}", "krita_comfyui: Stored UI Inputs", self.serialized)
                self.save_workflow_id()

        else:
            self.disable_save += 1


    def get_default_for_widget(self, widget):
        default = widget.get("default", None)

        # Widget default always has highest priority
        if default is None:
            link_to = widget.get("link_to", None)

            # Get the default from the ComfyUI Node metadata
            if link_to is not None:
                metadata = self.settings.get_node_metadata(link_to["node_id"]).input(link_to["input"])
                default = metadata.info.get("default", None)

        # If there is no default, pick a suitable default
        if default is None:
            match widget["type"]:
                case "layer_id" | "combo" | "string": return ""
                case "int": return 0
                case "float" | "percentage": return 0.0
                case "group": return True
                case "list": return 0
                case _: raise RuntimeError(f"Unknown widget type {widget["type"]}")

        assert default is not None
        return default


    def update_inputs(self):
        self.defaults = {}
        self.inputs = {}

        if self.layout is not None:
            # We look for every widget in the layout and get the default.
            for widget in all_children(self.layout):
                id = widget.get("id", None)

                if id is not None:
                    # Make sure that the inputs always exists.
                    self.inputs[id] = []
                    self.defaults[id] = self.get_default_for_widget(widget)

        # Load the serialized values.
        for key, values in self.serialized.items():
            default = self.defaults.get(key, None)

            # If the serialized JSON has excess keys they are ignored.
            if default is not None:
                # Replace None with the default value.
                self.inputs[key] = [(default if value is None else value) for value in values]


    def update_workflow(self):
        if self.id == "":
            self.serialized = {}
            self.graph = None
            self.layout = None

        else:
            if self.document is None:
                self.serialized = {}
            else:
                self.serialized = self.document.get_key_json(f"krita_comfyui/ui_inputs/{self.id}", {})

            info = self.settings.load_workflow(self.id)
            assert info["id"] == self.id

            self.graph = info["graph"]
            self.layout = info["layout"]

        self.update_inputs()


    def change_metadata(self):
        self.update_inputs()
        return True


    def change_workflow(self, id):
        assert id is not None
        assert isinstance(id, str)

        if self.id != id:
            self.id = id

            self.update_workflow()
            self.save_workflow_id()
            return True

        return False


    def change_document(self, document):
        if self.document != document:
            self.document = document

            if True:
                if self.document is None:
                    self.id = ""
                else:
                    self.id = self.document.get_key_str("krita_comfyui/workflow_id", "")

            else:
                if self.document is not None:
                    id = self.document.get_key_str("krita_comfyui/workflow_id", None)

                    # If the document doesn't have a stored workflow_id,
                    # then we just keep using the existing workflow_id.
                    if id is not None:
                        self.id = id

            self.update_workflow()
            return True

        return False


    def is_valid(self):
        return self.document is not None and self.id != "" and self.graph is not None


    def to_graph(self):
        if self.document is None:
            raise WorkflowError("Krita does not have an opened image")

        if self.id == "":
            raise WorkflowError("Workflow cannot be empty")

        assert self.graph is not None

        seed = WorkflowGraph.random_seed()

        print("Running graph")
        print(self.inputs)

        return WorkflowGraph(
            document=self.document,
            json=self.graph,
            seed=seed,
            ui_values=self.inputs,
        ).evaluate()
