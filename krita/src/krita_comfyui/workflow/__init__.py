from PyQt6.QtCore import QObject, pyqtSignal
from .graph import WorkflowGraph, WorkflowError


# Loops recursively over all the children in a layout
def all_children(children):
    for child in children:
        yield child

        children = child.get("children", None)
        if children is not None:
            yield from all_children(children)


class Input:
    def __init__(self, root, serialized, id):
        metadata = root.metadata[id]
        assert metadata.type != "list"
        id = metadata.get_full_id(id)

        default = metadata.default
        value = serialized.get(id, default)

        assert default is not None
        assert value is not None

        self.root = root
        self.serialized = serialized
        self.id = id
        self.default = default
        self.value = value
        self.listeners = []


    def add_listener(self, f):
        self.listeners.append(f)

    def notify_listeners(self):
        for listener in self.listeners:
            listener()


    def format_tooltip(self, tooltip):
        if tooltip is None:
            return f"[{self.id}]"
        else:
            return f"[{self.id}]\n{tooltip}"


    def get(self):
        return self.value


    def set(self, value):
        assert value is not None

        old_value = self.value

        self.value = value

        try:
            # We only save if the new value is different from the old value.
            should_save = self.serialized[self.id] != value
        except KeyError:
            should_save = True

        if should_save:
            self.serialized[self.id] = value
            self.root.save()

        if old_value != self.value:
            self.notify_listeners()


    def reset_to_default(self):
        old_value = self.value

        self.value = self.default

        try:
            del self.serialized[self.id]
        except KeyError:
            # Don't save if the key doesn't exist.
            return

        self.root.save()

        if old_value != self.value:
            self.notify_listeners()


class InputListChild:
    def __init__(self, root, serialized):
        self.root = root
        self.serialized = serialized
        self.inputs = {}

    # TODO this doesn't reset the inputs when the root's metadata changes
    def input(self, id):
        try:
            return self.inputs[id]
        except KeyError:
            input = Input(self.root, self.serialized, id)
            self.inputs[id] = input
            return input

    def input_list(self, id):
        return InputList(self.root, self.serialized, id)


class InputList:
    def __init__(self, root, serialized, id):
        metadata = root.metadata[id]
        assert metadata.type == "list"
        id = metadata.get_full_id(id)

        self.root = root
        self.serialized = serialized
        self.id = id
        self.children = serialized.get(id, [])


    def iter_children(self):
        for child in self.children:
            yield InputListChild(self.root, child)


    def move(self, old_index, new_index):
        assert old_index != new_index
        assert new_index >= 0
        assert new_index < len(self.children)

        self.children.insert(new_index, self.children.pop(old_index))
        assert self.serialized[self.id] is self.children
        self.root.save()


    def remove(self, index):
        del self.children[index]

        assert self.serialized[self.id] is self.children

        if len(self.children) == 0:
            del self.serialized[self.id]

        self.root.save()


    def add(self):
        self.children.append({})
        self.serialized[self.id] = self.children
        self.root.save()


class Metadata:
    def __init__(self, default, type):
        self.default = default
        self.type = type

    def get_full_id(self, id):
        return f"{self.type}/{id}"


class Workflow(QObject):
    def __init__(self, settings):
        super().__init__()

        self.settings = settings
        self.inputs = {}

        self.id = ""
        self.document = None
        self.graph = None
        self.layout = None

        self.serialized = {}
        self.defaults = {}
        self.metadata = {}


    # This doesn't reset any of the Inputs
    def clear(self):
        self.serialized = {}
        self.inputs = {}
        self.save()


    def input(self, id):
        try:
            return self.inputs[id]
        except KeyError:
            input = Input(self, self.serialized, id)
            self.inputs[id] = input
            return input

    def input_list(self, id):
        return InputList(self, self.serialized, id)


    def save_workflow_id(self):
        assert self.document is not None
        assert self.id is not None
        self.document.set_key_str("krita_comfyui/workflow_id", "krita_comfyui: Workflow ID", self.id)


    def save(self):
        if self.id != "" and self.document is not None:
            self.document.set_key_json(f"krita_comfyui/ui_inputs/{self.id}", "krita_comfyui: Stored UI Inputs", self.serialized)

            # This is for the case where you open a new document which doesn't have
            # a workflow_id, so it reuses the old workflow_id.
            #
            # In that case we want to save the workflow_id to the new document.
            self.save_workflow_id()


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
                case "boolean": return True
                case "group": return False
                case "list": return []
                case _: raise RuntimeError(f"Unknown widget type {widget["type"]}")

        assert default is not None
        return default


    def get_type_for_widget(self, widget):
        match widget["type"]:
            case "layer_id": return "layer_id"
            case "combo": return "combo"
            case "string": return "string"
            case "boolean": return "boolean"
            case "int": return "int"
            case "float" | "percentage": return "float"
            case "list": return "list"
            case "group": return "group"
            case _: raise RuntimeError(f"Unknown widget type {widget["type"]}")


    def update_metadata(self):
        self.metadata = {}
        self.defaults = {}
        self.inputs = {}

        if self.layout is not None:
            # We look for every widget in the layout and get the default.
            for widget in all_children(self.layout):
                id = widget.get("id", None)

                if id is not None:
                    metadata = Metadata(
                        self.get_default_for_widget(widget),
                        self.get_type_for_widget(widget),
                    )

                    self.metadata[id] = metadata
                    self.defaults[metadata.get_full_id(id)] = metadata.default


    def update_serialized(self):
        assert self.id is not None

        self.inputs = {}

        if self.id == "":
            self.serialized = {}

        elif self.document is None:
            self.serialized = {}

        else:
            self.serialized = self.document.get_key_json(f"krita_comfyui/ui_inputs/{self.id}", {})


    def reload_workflow(self):
        if self.id != "":
            try:
                info = self.settings.workflows.get(self.id)
            except KeyError:
                info = None

            # If the workflow was deleted, revert back to the default.
            if info is None:
                return self.change_workflow("")

            else:
                assert info["id"] == self.id
                self.graph = info["graph"]
                self.layout = info["layout"]
                self.update_metadata()
                return True

        return False


    def update_workflow(self, id):
        assert id is not None
        assert isinstance(id, str)

        if self.id != id:
            self.id = id

            if self.id == "":
                self.graph = None
                self.layout = None

            else:
                info = self.settings.workflows.get(self.id)
                assert info["id"] == self.id

                self.graph = info["graph"]
                self.layout = info["layout"]

            self.update_metadata()
            return True

        return False


    def change_metadata(self):
        self.update_metadata()
        return True


    def change_workflow(self, id):
        if self.update_workflow(id):
            self.update_serialized()
            self.save_workflow_id()
            return True
        else:
            self.save_workflow_id()
            return False


    def change_document(self, document):
        if self.document != document:
            self.document = document

            if True:
                if self.document is None:
                    id = ""
                else:
                    id = self.document.get_key_str("krita_comfyui/workflow_id", "")

                self.update_workflow(id)

            else:
                if self.document is not None:
                    id = self.document.get_key_str("krita_comfyui/workflow_id", None)

                    # If the document doesn't have a stored workflow_id,
                    # then we just keep using the existing workflow_id.
                    if id is not None:
                        self.update_workflow(id)

            # We always have to update serialized even if the ID is the same.
            self.update_serialized()
            return True

        return False


    def is_valid(self):
        return self.document is not None and self.id != "" and self.graph is not None


    def get_defaults(self):
        return self.defaults


    def to_graph(self, ui_values, defaults):
        if self.document is None:
            raise WorkflowError("Krita does not have an opened image")

        if self.id == "":
            raise WorkflowError("Workflow cannot be empty")

        assert self.graph is not None

        seed = WorkflowGraph.random_seed()

        import json
        print("Running graph")
        print(json.dumps(ui_values, indent=2))
        print("")
        print(json.dumps(defaults, indent=2))
        print("")

        return WorkflowGraph(
            document=self.document,
            json=self.graph,
            seed=seed,
            ui_values=ui_values,
            defaults=defaults,
        ).evaluate()
