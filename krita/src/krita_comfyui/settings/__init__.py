import os
from json import dump, dumps, load, loads
from pathlib import Path
from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtWidgets import QMessageBox


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

    def update_inputs(self, inputs):
        if inputs is not None:
            for name, input in inputs.items():
                metadata = InputMetadata()

                if len(input) > 1:
                    info = input[1]
                else:
                    info = {}

                metadata.update(input[0], info)
                self.inputs[name] = metadata

    def update(self, inputs):
        self.exists = True
        self.update_inputs(inputs.get("required", None))
        self.update_inputs(inputs.get("optional", None))

    def input(self, name):
        if isinstance(name, str):
            if self.exists:
                try:
                    return self.inputs[name]
                except KeyError:
                    raise RuntimeError(f"Input does not exist [{self.node_id}]: {name}")
            else:
                return InputMetadata()

        else:
            metadata = self

            # If input is a list, then the metadata is a dynamic combo,
            # so we search for the input inside of the dynamic combo.
            for name in name:
                metadata = metadata.input(name)

            return metadata


class Snapshot:
    def __init__(self, settings, workflows):
        self.settings = settings
        self.workflows = workflows


class Settings(QObject):
    node_metadata_changed = pyqtSignal()
    settings_changed = pyqtSignal()


    default_settings = {

    }


    def __init__(self, parent):
        super().__init__(parent)

        self.dir = Path(Krita.getAppDataLocation()) / "krita_comfyui"

        self.settings = self.load_settings()

        self.node_metadata = None
        self.cached_node_metadata = {}

        self.workflows_dir = self.dir / "workflows"

        os.makedirs(self.workflows_dir, exist_ok=True)

        self.workflows = {}

        self.load_node_metadata()


    # Creates a deep copy of the settings
    def snapshot(self):
        return Snapshot(loads(dumps(self.settings)), self.workflows)


    def restore_snapshot(self, snapshot):
        self.settings = snapshot.settings
        self.save_settings()


    def restore_defaults(self):
        reply = QMessageBox.question(
            self,
            "Restore defaults",
            "Are you sure you want to restore all defaults?\n\nThis will delete your bundles, presets, and workflows!",
        )

        if reply == QMessageBox.StandardButton.Yes:
            self.settings = self.default_settings()
            self.save_settings()


    def load_settings(self):
        try:
            with open(self.dir / "settings.json", "r") as file:
                return load(file)
        except FileNotFoundError:
            return {}


    def save_settings(self):
        with open(self.dir / "settings.json", "w") as file:
            dump(self.settings, file, indent=2)

        self.settings_changed.emit()


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


    def workflow_path(self, id):
        return self.workflows_dir / (id + ".json")


    def load_workflow(self, id):
        workflow = self.workflows.get(id, None)

        if workflow is None:
            with open(self.workflow_path(id), "r") as file:
                workflow = load(file)

            self.workflows[id] = workflow

        return workflow


    def load_all_workflows(self):
        for id in os.listdir(self.workflows_dir):
            self.load_workflow(Path(id).stem)

        def sort_workflow(x):
            return (x.get("order", 0), x["name"].casefold(), x["id"])

        return sorted(self.workflows.values(), key=sort_workflow)


    def save_workflow(self, id, json):
        with open(self.workflow_path(id), "w") as file:
            dump(json, file, indent=2)
