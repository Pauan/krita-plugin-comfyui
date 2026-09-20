from __future__ import annotations

import re
import functools
from dataclasses import dataclass
from typing import cast
from collections.abc import Iterable
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import QDialog, QDialogButtonBox, QMenu, QToolButton, QWidget, QLineEdit, QTreeWidget, QTreeWidgetItem, QAbstractItemView, QHeaderView, QInputDialog
from ...util.qt import MessageBox, LayoutManager
from ...util.krita import Image
from ...workflow.ui import UiPrompt
from ...util.storage import Storage, Dict
from ...server import CivitaiInfo
from ...extension import ComfyUIExtension


@functools.total_ordering
class TreeItem(QTreeWidgetItem):
    def __init__(self, parent: QTreeWidget | QTreeWidgetItem | None, is_folder: bool, name: str) -> None:
        super().__init__(parent)
        self.setText(0, name)
        self.is_folder = is_folder
        self.cmp = (0 if is_folder else 1, name.casefold())

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, TreeItem):
            return NotImplemented
        return self.cmp == other.cmp

    def __lt__(self, other: QTreeWidgetItem) -> bool:
        assert isinstance(other, TreeItem)
        return self.cmp < other.cmp


    def filter(self, regex: re.Pattern[str]) -> bool:
        visible = False

        length = self.childCount()

        assert length > 0

        for index in range(length):
            if cast(TreeItem, self.child(index)).filter(regex):
                visible = True

        if visible:
            self.setExpanded(True)

        self.setHidden(not visible)
        return visible


    def show_all(self) -> None:
        length = self.childCount()

        assert length > 0

        for index in range(length):
            cast(TreeItem, self.child(index)).show_all()

        self.setExpanded(False)
        self.setHidden(False)


class TreeLeaf(TreeItem):
    def __init__(self, parent: QTreeWidget | QTreeWidgetItem | None, name: str, info: BundleInfo) -> None:
        super().__init__(parent, False, name)
        self.info = info

    def filter(self, regex: re.Pattern[str]) -> bool:
        visible = regex.search(self.info.key) is not None
        self.setHidden(not visible)
        return visible

    def show_all(self) -> None:
        self.setHidden(False)


class Tree:
    def __init__(self, tree: QTreeWidget | QTreeWidgetItem) -> None:
        self.tree = tree
        self.children: dict[str, Folder] = {}


    def clear(self) -> None:
        self.children = {}
        cast(QTreeWidget, self.tree).clear()


    def sort(self) -> None:
        cast(QTreeWidget, self.tree).sortItems(0, Qt.SortOrder.AscendingOrder)


    def filter(self, regex: re.Pattern[str]) -> None:
        tree = cast(QTreeWidget, self.tree)

        for index in range(tree.topLevelItemCount()):
            cast(TreeItem, tree.topLevelItem(index)).filter(regex)


    def show_all(self) -> None:
        tree = cast(QTreeWidget, self.tree)

        for index in range(tree.topLevelItemCount()):
            cast(TreeItem, tree.topLevelItem(index)).show_all()


    def make_path(self, path: Iterable[str]) -> QTreeWidget | QTreeWidgetItem:
        parent: Tree = self

        for name in path:
            parent = parent.subfolder(name)

        return parent.tree


    def subfolder(self, name: str) -> Folder:
        try:
            return self.children[name]

        except KeyError:
            child = Folder(self, name)
            self.children[name] = child
            return child


class Folder(Tree):
    def __init__(self, parent: Tree, name: str) -> None:
        item = TreeItem(parent.tree, True, name)
        super().__init__(item)


class LoadingDialog(QDialog):
    def __init__(self, parent: QWidget | None, extension: ComfyUIExtension) -> None:
        super().__init__(parent)

        self.extension = extension

        self.layout_manager = LayoutManager(self)

        self.setModal(True)

        with self.layout_manager.column() as column:
            column.set_padding(left=10, top=10, right=10, bottom=10)

            column.label(text="Loading lora... please be patient.")

            column.spacer(10)

            with column.widget(QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)) as buttons:
                buttons.rejected.connect(self.on_cancel)


    def on_cancel(self) -> None:
        self.extension.client.cancel_download_civitai()
        self.reject()


@dataclass
class BundleInfo:
    key: str
    info: Dict


class BundleName(QWidget):
    def __init__(self, root: SettingsBundles, text: str) -> None:
        super().__init__()

        self.root = root
        self.text = text

        self.layout_manager = LayoutManager(self)

        with self.layout_manager.row() as row:
            with row.tool_button(icon=Krita.icon("edit-rename"), tooltip="Change name") as button:
                button.clicked.connect(self.update_name)

            row.spacer(6)

            with row.label(text=text, tooltip="Bundle name", selectable=True):
                pass

            row.stretch()

            with row.tool_button(icon=Krita.icon("window-close"), tooltip="Delete bundle") as button:
                button.clicked.connect(self.delete_bundle)


    def update_name(self) -> None:
        old_name = self.text

        new_name = self.root.bundle_name_dialog(old_name)

        if new_name is not None:
            self.root.rename_bundle(old_name, new_name)


    def delete_bundle(self) -> None:
        if MessageBox.question(self, f"Are you sure you want to delete the \"{self.text}\" bundle?"):
            self.root.delete_bundle(self.text)


class SettingsBundles(QWidget):
    def __init__(self, extension: ComfyUIExtension, bundles: Storage) -> None:
        super().__init__()

        self.extension = extension
        self.extension.client.civitai_finished.connect(self.on_civitai_finished)

        self.bundles = bundles

        self.widgets: list[UiPrompt] = []
        self.selected_bundle: BundleInfo | None = None

        self.loading_dialog = LoadingDialog(self, self.extension)

        self.layout_manager = LayoutManager(self)

        with self.layout_manager.row() as row:
            row.set_padding(left=10, top=10, right=10, bottom=10)

            with row.column(stretch=1) as column:
                with column.row() as top:
                    with top.tool_button(icon=Krita.icon("settings-button"), tooltip="Bundle menu...") as button:
                        self.menu = QMenu(self)

                        self.menu.addAction(Krita.icon("list-add"), "New bundle", self.new_bundle)
                        self.menu.addSeparator()
                        self.menu.addAction(Image.load_icon("civitai-color.svg"), "Download Civitai Lora", self.new_civitai_lora)

                        button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
                        button.setMenu(self.menu)

                    with top.widget(QLineEdit()) as search:
                        self.search_timer = QTimer(self)
                        self.search_timer.setSingleShot(True)
                        self.search_timer.setInterval(100)
                        self.search_timer.timeout.connect(self.search_bundles)

                        self.search_box = search
                        search.setToolTip("Search for a bundle.")
                        search.setPlaceholderText("Search...")
                        search.textEdited.connect(self.search_timer.start)

                column.spacer(3)

                with column.widget(QTreeWidget()) as tree:
                    tree.setColumnCount(1)
                    tree.setSortingEnabled(False)
                    tree.setHeaderHidden(True)
                    header = tree.header()
                    assert header is not None
                    header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
                    header.setStretchLastSection(False)
                    tree.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

                    tree.itemActivated.connect(self.on_item_clicked)

                    self.tree = Tree(tree)

            row.spacer(6)

            with row.column(stretch=1) as column:
                self.bundle_info = column

        self.update_tree()


    @staticmethod
    def process_bundle_name(name: str) -> str:
        return re.sub(r"/{2,}", "/", re.sub(r"\s*/\s*", "/", name))


    #def make_parents(self, path: list[str]) -> Folder:
    #    parent = Folder(self.tree, path[0])
    #
    #    for name in path[1:]:
    #        parent = parent.make_child(name)
    #
    #    return parent


    def update_bundle(self) -> None:
        # Cleanup the old widgets.
        for widget in self.widgets:
            widget.inputs.stop()

        self.widgets.clear()

        self.bundle_info.clear()

        if self.selected_bundle is not None:
            key = self.selected_bundle.key
            info = self.selected_bundle.info

            self.bundle_info.widget(BundleName(self, key))

            with self.bundle_info.widget(UiPrompt(
                value=info.value("prompt", str, default=""),
                is_default=False,
                settings=self.extension.settings,
                visible_if=[],
                enabled_if=[],
                tooltip=None,
                autocomplete=True,
                placeholder="Prompt...",
                background_color=None,
                min_lines=None,
                max_lines=None,
                auto_resize=False,
            ), stretch=1) as widget:
                self.widgets.append(widget)


    def on_item_clicked(self, item: QTreeWidgetItem | None, column: int) -> None:
        if item is not None:
            assert isinstance(item, TreeItem)

            if item.is_folder:
                item.setExpanded(not item.isExpanded())
                self.selected_bundle = None
            else:
                assert isinstance(item, TreeLeaf)
                self.selected_bundle = item.info
        else:
            self.selected_bundle = None

        self.update_bundle()


    def bundle_name_dialog(self, initial: str) -> str | None:
        text, ok = QInputDialog.getText(self,
            "Krita Plugin ComfyUI",
            "Bundle name.\n\nUse / to put the bundle into a subfolder.\n",
            text=initial,
        )

        if ok:
            text = text.strip()

            if text == "":
                MessageBox.error(self, text="Invalid bundle name", information="Bundle name cannot be empty")

            elif text[0] == "/":
                MessageBox.error(self, text="Invalid bundle name", information="Bundle name cannot start with /")

            elif text[-1] == "/":
                MessageBox.error(self, text="Invalid bundle name", information="Bundle name cannot end with /")

            else:
                return self.process_bundle_name(text)


    def rename_bundle(self, old_name: str, new_name: str) -> None:
        bundle = self.bundles.root.value(old_name, dict, default={})

        self.bundles.root.value(new_name, dict, default={}).set(bundle.get())

        bundle.remove()

        if self.selected_bundle is not None and self.selected_bundle.key == old_name:
            self.selected_bundle = BundleInfo(new_name, self.bundles.root.dict(new_name))
            self.update_bundle()

        self.update_tree()


    def delete_bundle(self, name: str) -> None:
        self.bundles.root.value(name, dict, default={}).remove()

        if self.selected_bundle is not None and self.selected_bundle.key == name:
            self.selected_bundle = None
            self.update_bundle()

        self.update_tree()


    def make_bundle(self, name: str, prompt: str) -> None:
        if name in self.bundles.root.get():
            MessageBox.error(self, text=f"Bundle \"{name}\" already exists.")

        else:
            self.bundles.root.value(name, dict, default={}).set({
                "prompt": prompt
            })

            self.selected_bundle = BundleInfo(name, self.bundles.root.dict(name))
            self.update_bundle()
            self.update_tree()


    def new_bundle(self) -> None:
        name = self.bundle_name_dialog("")

        if name is not None:
            self.make_bundle(name, "")


    def new_civitai_lora(self) -> None:
        folder = self.extension.settings.settings.root.value("comfyui_lora_folder", str).get()

        if folder == "":
            MessageBox.error(self, text="You must set a ComfyUI Lora folder in the settings.")
            return

        api_key = self.extension.settings.settings.root.value("civitai_api_key", str).get()

        if api_key == "":
            MessageBox.error(self,
                text="You must set a Civitai API key in the settings.",
                information="You can create an API key at this URL:<br /><a href='https://civitai.com/user/account'>https://civitai.com/user/account</a>",
                rich_text=True,
            )
            return

        url, ok = QInputDialog.getText(self,
            "Krita ComfyUI Plugin",
            "Enter the Civitai URL for the Lora:\n",
            text="",
        )

        if not ok:
            return

        parsed = re.search(r"^(.+)/models/([0-9]+)/([^\/?#]+)", url)

        if parsed is None:
            MessageBox.error(self, text=f"<p>Invalid URL:<br /><a href='{url}'>{url}</a></p><p>Example URL:<br />https://civitai.com/models/2540444/anima-highresaesthetic-boost?modelVersionId=2855073</p>", rich_text=True)
            return

        host = parsed.group(1)
        id = int(parsed.group(2))
        slug = parsed.group(3)

        version_id = re.search(r"modelVersionId=([0-9]+)", url)
        if version_id is not None:
            version_id = int(version_id.group(1))

        self.extension.client.download_civitai_lora(
            api_key=api_key,
            folder=folder,
            host=host,
            id=id,
            slug=slug,
            version_id=version_id,
        )

        self.loading_dialog.show()


    def on_civitai_finished(self, info: CivitaiInfo) -> None:
        if info.error is None:
            self.make_bundle(info.bundle_name(), info.to_prompt())
            self.loading_dialog.close()
            MessageBox.info(self, text="Lora finished loading!")

        else:
            self.loading_dialog.close()
            MessageBox.from_exception(self, info.error)


    # TODO make this more efficient by using QSortFilterProxyModel
    def search_bundles(self) -> None:
        text = self.search_box.text().strip()

        if text == "":
            self.tree.show_all()

        else:
            text = self.process_bundle_name(text)

            compiled = re.compile(".*/.*".join([re.escape(x) for x in text.split("/")]), re.IGNORECASE)

            self.tree.filter(compiled)


    def update_tree(self) -> None:
        self.tree.clear()

        root = self.bundles.root

        selected_item: TreeLeaf | None = None

        for key in root.get().keys():
            path = key.split("/")

            parent = self.tree.make_path(path[:-1])

            child = TreeLeaf(
                parent=parent,
                name=path[-1],
                info=BundleInfo(key, root.dict(key)),
            )

            if self.selected_bundle is not None and self.selected_bundle.key == key:
                selected_item = child

        self.tree.sort()

        self.search_bundles()

        if selected_item is None:
            self.selected_bundle = None
        else:
            selected_item.setSelected(True)
            cast(QTreeWidget, self.tree.tree).scrollToItem(selected_item, QAbstractItemView.ScrollHint.EnsureVisible)


    def on_changed(self) -> None:
        self.update_tree()


    def on_show(self) -> None:
        self.search_box.setFocus()
