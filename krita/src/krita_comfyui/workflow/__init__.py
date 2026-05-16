from ..util.storage import Storage, Metadata
from .graph import WorkflowGraph, WorkflowError


# Loops recursively over all the children in a layout
def all_children(children):
    for child in children:
        yield child

        children = child.get("children", None)
        if children is not None:
            yield from all_children(children)


class Workflow(Storage):
    def __init__(self, settings):
        super().__init__({})

        self.settings = settings

        self.id = ""
        self.document = None
        self.graph = None
        self.layout = None

        self.defaults = {}
        self.metadata = {}


    def _full_id(type, id):
        return f"{type}/{id}"


    def _metadata(self, id, default):
        metadata = self.metadata[id]

        if default is None:
            default = metadata["default"]

        type = metadata["type"]

        return Metadata(Workflow._full_id(type, id), default)


    def _save(self):
        if self.id != "" and self.document is not None:
            self.document.set_key_json(f"krita_comfyui/ui_inputs/{self.id}", "krita_comfyui: Stored UI Inputs", self.serialized)

        # This is for the case where you open a new document which doesn't have
        # a workflow_id, so it reuses the old workflow_id.
        #
        # In that case we want to save the workflow_id to the new document.
        self._save_workflow_id()


    def _save_workflow_id(self):
        assert self.id is not None

        if self.document is not None:
            self.document.set_key_str("krita_comfyui/workflow_id", "krita_comfyui: Workflow ID", self.id)


    def _get_default_for_widget(self, widget):
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


    def _get_type_for_widget(self, widget):
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


    def _update_metadata(self):
        self.metadata = {}
        self.defaults = {}

        if self.layout is not None:
            # We look for every widget in the layout and get the default.
            for widget in all_children(self.layout):
                id = widget.get("id", None)

                if id is not None:
                    if id in self.metadata:
                        raise WorkflowError(f"The id \"{id}\" is used multiple times.")

                    default = self._get_default_for_widget(widget)
                    type = self._get_type_for_widget(widget)

                    metadata = {
                        "default": default,
                        "type": type,
                    }

                    full_id = Workflow._full_id(type, id)

                    assert not full_id in self.defaults

                    self.metadata[id] = metadata
                    self.defaults[full_id] = default


    def _update_serialized(self):
        assert self.id is not None

        if self.id == "" or self.document is None:
            self.replace_serialized({})
        else:
            self.replace_serialized(self.document.get_key_json(f"krita_comfyui/ui_inputs/{self.id}", {}))


    def _update_workflow(self, id):
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

            self._update_metadata()
            return True

        return False


    def reload_workflow(self, id):
        if self.id == id and self.id != "":
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
                self._update_metadata()
                self.disconnect_items()
                return True

        return False


    def change_metadata(self):
        self._update_metadata()
        self.disconnect_items()
        return True


    def change_workflow(self, id):
        if self._update_workflow(id):
            self._update_serialized()
            self._save_workflow_id()
            return True
        else:
            self._save_workflow_id()
            return False


    def change_document(self, document):
        if self.document != document:
            self.document = document

            if True:
                if self.document is None:
                    id = ""
                else:
                    id = self.document.get_key_str("krita_comfyui/workflow_id", "")

                self._update_workflow(id)

            else:
                if self.document is not None:
                    id = self.document.get_key_str("krita_comfyui/workflow_id", None)

                    # If the document doesn't have a stored workflow_id,
                    # then we just keep using the existing workflow_id.
                    if id is not None:
                        self._update_workflow(id)

            # We always have to update serialized even if the ID is the same.
            self._update_serialized()
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
