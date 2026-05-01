import os
from json import dump, load
from pathlib import Path
from PyQt6.QtCore import QObject, pyqtSignal


class InputMetadata:
    def __init__(self):
        self.info = {}
        self.sub_options = {}

    def input(self, name):
        try:
            return self.sub_options[name]
        except KeyError:
            raise RuntimeError(f"Dynamic option {name} does not exist")

    def update(self, node_type, info):
        self.info = info

        if not "options" in self.info:
            # Old school combo nodes
            if isinstance(node_type, list):
                self.info["options"] = node_type

        if node_type == "COMFY_DYNAMICCOMBO_V3":
            for option in info["options"]:
                key = option["key"]
                metadata = NodeMetadata(key)
                metadata.update(option["inputs"])
                self.sub_options[key] = metadata


class NodeMetadata:
    def __init__(self, node_id):
        self.exists = False
        self.node_id = node_id
        self.inputs = {}

    def update(self, inputs):
        self.exists = True

        for name, input in inputs.get("required", {}).items():
            self.inputs[name] = InputMetadata()
            self.inputs[name].update(input[0], input[1])

        for name, input in inputs.get("optional", {}).items():
            self.inputs[name] = InputMetadata()
            self.inputs[name].update(input[0], input[1])

    def input(self, name):
        if self.exists:
            try:
                return self.inputs[name]
            except KeyError:
                raise RuntimeError(f"Input does not exist [{self.node_id}]: {name}")
        else:
            return InputMetadata()


class Settings(QObject):
    node_metadata_changed = pyqtSignal()


    def __init__(self, parent):
        super().__init__(parent)

        self.dir = Path(Krita.getAppDataLocation()) / "krita_comfyui"

        self.node_metadata = None
        self.cached_node_metadata = {}

        self.workflows_dir = self.dir / "workflows"

        os.makedirs(self.workflows_dir, exist_ok=True)

        self.all_workflows = set(Path(path).stem for path in os.listdir(self.workflows_dir))

        print(self.all_workflows)

        self.workflows = {}

        self.load_node_metadata()


    def get_node_metadata(self, node_id):
        metadata = self.cached_node_metadata.get(node_id)

        if metadata is None:
            metadata = NodeMetadata(node_id)

            if self.node_metadata is not None:
                try:
                    info = self.node_metadata[node_id]
                except KeyError:
                    raise RuntimeError(f"Could not find node [{node_id}]")

                metadata.update(info["input"])

            self.cached_node_metadata[node_id] = metadata

        return metadata


    def load_node_metadata(self):
        assert self.node_metadata is None

        try:
            with open(self.dir / "node_metadata.json", "r") as file:
                self.node_metadata = load(file)
        except FileNotFoundError:
            pass

        self.cached_node_metadata = {}


    def save_node_metadata(self, metadata):
        self.node_metadata = metadata
        self.cached_node_metadata = {}

        with open(self.dir / "node_metadata.json", "w") as file:
            dump(metadata, file, indent=2)

        self.node_metadata_changed.emit()


    def workflow_path(self, name):
        return self.workflows_dir / (name + ".json")


    def load_workflow(self, name):
        workflow = self.workflows.get(name, None)

        if workflow is None:
            with open(self.workflow_path(name), "r") as file:
                workflow = load(file)

            self.workflows[name] = workflow

        return workflow


    def load_workflows(self):
        for name in self.all_workflows:
            self.load_workflow(name)


    def save_workflow(self, name, json):
        with open(self.workflow_path(name), "w") as file:
            dump(json, file, indent=2)

        self.all_workflows.add(name)
