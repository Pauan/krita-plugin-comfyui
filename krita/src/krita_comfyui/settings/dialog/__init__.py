from typing import TYPE_CHECKING, Any, cast
from PyQt6.QtCore import QUrl, QSize
from PyQt6.QtGui import QDesktopServices, QGuiApplication, QCursor
from PyQt6.QtWidgets import (
    QWidget,
    QDialog,
    QListWidgetItem,
)

from ...util.qt import MessageBox, LayoutManager
from ...util.storage import Storage
from .. import Settings, Workflows
from .bundles import SettingsBundles

if TYPE_CHECKING:
    from ...extension import ComfyUIExtension


class SettingsPresets(QWidget):
    def __init__(self, presets: Storage) -> None:
        super().__init__()

        self.presets = presets

    def on_changed(self) -> None:
        pass

    def on_show(self) -> None:
        pass


class SettingsWorkflows(QWidget):
    def __init__(self, workflows: Workflows) -> None:
        super().__init__()

        self.workflows = workflows

    def on_changed(self) -> None:
        pass

    def on_show(self) -> None:
        pass


class SettingsDialog(QDialog):
    tab_widgets: list[SettingsBundles | SettingsPresets | SettingsWorkflows]

    def __init__(self, extension: "ComfyUIExtension", settings: Settings) -> None:
        super().__init__()

        self.extension = extension
        self.settings = settings
        self.snapshot: tuple[Any, ...] | None = None

        self.setWindowTitle("Configure Krita ComfyUI")

        self.layout_manager = LayoutManager(self)

        self.tab_widgets = []

        with self.layout_manager.row() as row:
            with row.list() as list:
                self.tab_list = list
                self.tab_list.setFixedWidth(120)
                self.tab_list.currentRowChanged.connect(self.change_menu)

            with row.column() as column:
                with column.stack() as stack:
                    self.stack = stack

                    with stack.widget(SettingsBundles(self.extension, self.settings.bundles)) as widget:
                        self.tab_widgets.append(widget)
                        self.add_menu_tab("Bundles")

                    with stack.widget(SettingsPresets(self.settings.presets)) as widget:
                        self.tab_widgets.append(widget)
                        self.add_menu_tab("Presets")

                    with stack.widget(SettingsWorkflows(self.settings.workflows)) as widget:
                        self.tab_widgets.append(widget)
                        self.add_menu_tab("Workflows")

                with column.row() as row:
                    with row.button(text="Restore Defaults", icon=Krita.icon("document-revert")) as button:
                        button.clicked.connect(self.restore_defaults)

                    row.stretch()

                    with row.button(text="Ok", icon=Krita.icon("dialog-ok")) as button:
                        button.clicked.connect(self.close)

                    with row.button(text="Cancel", icon=Krita.icon("dialog-cancel-16")) as button:
                        button.clicked.connect(self.cancel)

        self.tab_list.setCurrentRow(0)


    def add_menu_tab(self, name: str) -> None:
        item = QListWidgetItem(name)
        item.setSizeHint(QSize(112, 24))
        self.tab_list.addItem(item)


    def show(self) -> None:
        self.snapshot = self.settings.snapshot()

        size = QSize(1280, 720)

        screen = QGuiApplication.screenAt(QCursor.pos())

        if screen is not None:
            screen_size = screen.availableSize()

            screen_ratio = screen_size.height() / screen_size.width()

            # Match the same aspect ratio as the user's screen
            size.setHeight(round(size.width() * screen_ratio))

            # Make sure that we leave a bit of a gap around the dialog
            size = size.boundedTo(screen_size * 0.8)

        self.setMinimumSize(size)

        current = cast(SettingsBundles | SettingsPresets | SettingsWorkflows | None, self.stack.current_widget())

        if current is not None:
            current.on_show()

        super().show()


    def cancel(self) -> None:
        assert self.snapshot is not None

        if MessageBox.question(self, "Cancel all changes?"):
            try:
                self.settings.restore_snapshot(self.snapshot)
            finally:
                self.snapshot = None

            for widget in self.tab_widgets:
                widget.on_changed()

            self.close()


    def restore_defaults(self) -> None:
        if MessageBox.question(self, "Are you sure you want to restore all defaults?\n\nThis will delete all your bundles, presets, and workflows!\n\nThis cannot be undone!"):
            self.settings.restore_defaults()

            for widget in self.tab_widgets:
                widget.on_changed()


    def change_menu(self, index: int) -> None:
        self.stack.set_current_index(index)
        current = cast(SettingsBundles | SettingsPresets | SettingsWorkflows, self.stack.current_widget())
        current.on_show()


    def open_settings_folder(self) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.settings.dir)))
