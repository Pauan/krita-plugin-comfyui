import json
from ..util.storage import Storage
from ..settings import LogLevel
from .graph import WorkflowGraph, WorkflowError


# Loops recursively over all the children in a layout
def all_children(children):
    for child in children:
        yield child

        children = child.get("children", None)
        if children is not None:
            yield from all_children(children)


class Workflow(Storage):
    def __init__(self, extension):
        super().__init__({})

        self.extension = extension
        self.settings = extension.settings

        self.id = ""
        self.document = None
        self.graph = None
        self.layout = None

        self.layout_ids = set()
        self.metadata = None


    def _save(self):
        if self.id != "" and self.document is not None:
            self.document.set_key_json(f"krita_comfyui/ui_inputs/{self.id}", "krita_comfyui: Stored UI Inputs", self.serialized)


    @staticmethod
    def _get_default(info):
        match info["type"]:
            case "layer_id" | "combo" | "string" | "prompt": return ""
            case "int": return 0
            case "float" | "percentage": return 0.0
            case "boolean": return True
            case "group": return False
            case "list": return []
            case _: raise RuntimeError(f"Unknown widget type {info["type"]}")


    @staticmethod
    def _get_type(info):
        match info["type"]:
            case "layer_id": return "layer_id"
            case "combo": return "combo"
            case "string": return "string"
            case "prompt": return "prompt"
            case "boolean": return "boolean"
            case "int": return "int"
            case "float" | "percentage": return "float"
            case "list": return "list"
            case "group": return "group"
            case _: raise RuntimeError(f"Unknown widget type {info["type"]}")


    def _get_metadata(self, info):
        default = info.get("default", None)

        # Explicit default always has priority.
        if default is None:
            link_to = info.get("link_to", None)

            # Get the default from the ComfyUI Node metadata
            if link_to is not None:
                metadata = self.settings.node_metadata.get(link_to["node_id"]).input(link_to["input"])
                default = metadata.info.get("default", None)

        if default is None:
            default = self._get_default(info)

        type = self._get_type(info)

        return {
            "id": f"{type}/{info["id"]}",
            "type": type,
            "default": default,
        }


    def _update_metadata(self):
        self.metadata = None
        self.layout_ids = set()

        if self.layout is not None and self.settings.node_metadata.is_loaded():
            self.metadata = {}

            # We look for every widget in the layout and set the metadata.
            for widget in all_children(self.layout):
                id = widget.get("id", None)

                if id is not None:
                    new_metadata = self._get_metadata(widget)
                    old_metadata = self.metadata.get(id, None)

                    if old_metadata is not None:
                        new_type = new_metadata["type"]
                        old_type = old_metadata["type"]
                        if old_type != new_type:
                            raise WorkflowError(f"The id \"{id}\" has two different types:\n    {old_type}\n    {new_type}")

                        new_default = new_metadata["default"]
                        old_default = old_metadata["default"]
                        if old_default != new_default:
                            raise WorkflowError(f"The id \"{id}\" has two different defaults:\n    {json.dumps(old_default)}\n    {json.dumps(new_default)}")

                    self.metadata[id] = new_metadata
                    self.layout_ids.add(new_metadata["id"])


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
                workflow = self.settings.workflows.get(self.id)

                assert workflow.id() == self.id

                # If the workflow is hidden, revert back to the default.
                if workflow.is_hidden():
                    return self.change_workflow("")

                else:
                    self.graph = workflow.graph()
                    self.layout = workflow.layout()

            self._update_metadata()
            return True

        return False


    def reload_workflow(self):
        if self.id != "":
            try:
                workflow = self.settings.workflows.get(self.id)
            except KeyError:
                workflow = None

            # If the workflow was deleted or hidden, revert back to the default.
            if workflow is None or workflow.is_hidden():
                return self.change_workflow("")

            else:
                assert workflow.id() == self.id

                new_graph = workflow.graph()
                new_layout = workflow.layout()

                if self.graph != new_graph or self.layout != new_layout:
                    self.graph = new_graph
                    self.layout = new_layout
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
            return True
        else:
            return False


    def change_document(self, document):
        if self.document != document:
            self.document = document
            self._update_serialized()
            return True

        return False


    def initialize(self, document, id):
        self.document = document
        self.change_workflow(id)


    def is_loaded(self):
        return self.layout is not None and self.metadata is not None


    def is_valid(self):
        return self.document is not None and self.id != "" and self.graph is not None and self.metadata is not None


    def run_graph(self, *, ui_values, is_live_mode, should_notify):
        if self.document is None:
            raise WorkflowError("Krita does not have an opened image")

        if self.id == "":
            raise WorkflowError("Workflow cannot be empty")

        assert self.graph is not None

        self.extension.client.execute_graph(
            # It's safe to send ui_values to another thread because it's created fresh every time.
            ui_values=ui_values,

            # It's safe to send graph to another thread because we never modify it.
            graph=self.graph,

            # This is safe because document isn't actually sent to another thread.
            document=self.document,

            # This is safe because these are primitive values.
            is_live_mode=is_live_mode,
            should_notify=should_notify,
        )
