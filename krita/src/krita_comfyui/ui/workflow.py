from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox,
)


class UiLayerId(QComboBox):
    def __init__(self, inputs, index, id, tooltip=None):
        super().__init__()

        self.ui_inputs = inputs
        self.ui_index = index
        self.ui_id = id

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

        self.ui_inputs.set(self.ui_id, self.ui_index, selected)


    def add(self, text, data, icon=None):
        if icon is None:
            self.addItem(text, data)
        else:
            self.addItem(icon, text, data)


    def reset(self):
        value = self.ui_inputs.get(self.ui_id, self.ui_index)

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
