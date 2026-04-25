import os
from json import dump, load
from pathlib import Path
from PyQt6.QtCore import QObject, pyqtSignal


class Settings(QObject):
    def __init__(self, parent):
        super().__init__(parent)

        self.dir = Path(Krita.getAppDataLocation()) / "krita_comfyui"

        self.workflows_dir = self.dir / "workflows"

        os.makedirs(self.workflows_dir)

        self.workflows = self.load_workflows()

        print(self.dir)
        print(self.workflows_dir)


    def load_workflow(self, name):
        with open(self.workflows_dir / (name + ".json"), "r") as file:
            return load(file)


    def load_workflows(self):
        workflows = {}

        for name in os.listdir(self.workflows_dir):
            print(name)

        return workflows


    def save_workflow(self, name, json):
        with open(self.workflows_dir / (name + ".json"), "w") as file:
            file.write(dump(json, file, indent=2))
