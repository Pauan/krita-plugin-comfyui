from ..util.qt import LayoutManager

from PyQt6.QtCore import QUrl, QSize
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (
    QWidget,
    QDialog,
    QListWidgetItem,
)


class SettingsPresets(QWidget):
    def __init__(self, presets):
        super().__init__()

        self.presets = presets


class SettingsWorkflows(QWidget):
    def __init__(self, workflows):
        super().__init__()

        self.workflows = workflows


class SettingsBundles(QWidget):
    def __init__(self, bundles):
        super().__init__()

        self.bundles = bundles


class SettingsDialog(QDialog):
    def __init__(self, settings):
        super().__init__()

        self.settings = settings
        self.snapshot = None

        self.setWindowTitle("Configure Krita ComfyUI")
        self.setMinimumSize(QSize(640, 480))

        self.layout_manager = LayoutManager(self)

        with self.layout_manager.row() as row:
            with row.list() as list:
                self.tab_list = list
                self.tab_list.setFixedWidth(120)
                self.tab_list.setCurrentRow(0)
                self.tab_list.currentRowChanged.connect(self.change_menu)

            with row.column() as column:
                with column.stack() as stack:
                    self.stack = stack

                    with stack.widget(SettingsBundles(self.settings.bundles)):
                        self.add_menu_tab("Bundles")

                    with stack.widget(SettingsPresets(self.settings.presets)):
                        self.add_menu_tab("Presets")

                    with stack.widget(SettingsWorkflows(self.settings.workflows)):
                        self.add_menu_tab("Workflows")

                    stack.set_current_index(0)

                with column.row() as row:
                    with row.button(text="Restore Defaults", icon=Krita.icon("document-revert")) as button:
                        button.clicked.connect(self.restore_defaults)

                    row.stretch()

                    with row.button(text="Ok", icon=Krita.icon("dialog-ok")) as button:
                        button.clicked.connect(self.close)

                    with row.button(text="Cancel", icon=Krita.icon("dialog-cancel-16")) as button:
                        button.clicked.connect(self.cancel)


    def add_menu_tab(self, name):
        item = QListWidgetItem(name)
        item.setSizeHint(QSize(112, 24))
        self.tab_list.addItem(item)


    def show(self):
        super().show()
        self.snapshot = self.settings.snapshot()


    def cancel(self):
        assert self.snapshot is not None
        try:
            self.settings.restore_snapshot(self.snapshot)
        finally:
            self.snapshot = None
        self.close()


    def restore_defaults(self):
        self.settings.restore_defaults()


    def change_menu(self, index):
        self.stack.set_current_index(index)


    def open_settings_folder(self):
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.settings.dir)))
