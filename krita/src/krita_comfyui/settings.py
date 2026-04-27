import os
from json import dump, load
from pathlib import Path
from PyQt6.QtCore import QObject, pyqtSignal


class Settings(QObject):
    def __init__(self, parent):
        super().__init__(parent)

        self.dir = Path(Krita.getAppDataLocation()) / "krita_comfyui"

        self.workflows_dir = self.dir / "workflows"

        self.workflows = {}


    def setup(self):
        os.makedirs(self.workflows_dir, exist_ok=True)


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
        for name in os.listdir(self.workflows_dir):
            print(name)
            #self.load_workflow(name)


    def save_workflow(self, name, json):
        with open(self.workflow_path(name), "w") as file:
            dump(json, file, indent=2)
