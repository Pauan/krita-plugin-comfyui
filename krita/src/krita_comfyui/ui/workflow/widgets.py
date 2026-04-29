from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox,
)


class UiLayerId(QComboBox):
    def __init__(self, input, tooltip=None):
        super().__init__()

        self.input = input

        #self.setEditable(True)
        self.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.setDuplicatesEnabled(True)

        self.activated.connect(self.on_changed)

        if tooltip is not None:
            self.setToolTip(tooltip)


    def on_changed(self):
        selected = self.selected()

        if selected is None:
            selected = ""

        self.input.set(selected)


    def add(self, text, data, icon=None):
        if icon is None:
            self.addItem(text, data)
        else:
            self.addItem(icon, text, data)


    def reset(self):
        value = self.input.get()

        if value is None or value == "":
            index = 0
        else:
            index = self.findData(value, flags=Qt.MatchFlag.MatchExactly)

        if self.currentIndex() != index:
            self.setCurrentIndex(index)


    def separator(self):
        self.insertSeparator(self.count())


    def selected(self):
        return self.currentData()
