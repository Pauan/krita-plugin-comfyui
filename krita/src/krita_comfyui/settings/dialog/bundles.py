import re
import functools
from dataclasses import dataclass
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import QWidget, QLineEdit, QTreeWidget, QTreeWidgetItem, QAbstractItemView, QHeaderView, QInputDialog, QMessageBox
from ...util.qt import LayoutManager
from ...workflow.ui import UiPrompt
from shared import Perf


@functools.total_ordering
class TreeItem(QTreeWidgetItem):
    def __init__(self, parent, is_folder, name):
        super().__init__(parent)
        self.setText(0, name)
        self.is_folder = is_folder
        self.cmp = (0 if is_folder else 1, name)

    def __eq__(self, other):
        return self.cmp == other.cmp

    def __lt__(self, other):
        return self.cmp < other.cmp


    def filter(self, regex):
        visible = False

        length = self.childCount()

        assert length > 0

        for index in range(length):
            if self.child(index).filter(regex):
                visible = True

        if visible:
            self.setExpanded(True)

        self.setHidden(not visible)
        return visible


    def show_all(self):
        length = self.childCount()

        assert length > 0

        for index in range(length):
            self.child(index).show_all()

        self.setExpanded(False)
        self.setHidden(False)


class TreeLeaf(TreeItem):
    def __init__(self, parent, name, info):
        super().__init__(parent, False, name)
        self.info = info

    def filter(self, regex):
        visible = regex.search(self.info.key) is not None
        self.setHidden(not visible)
        return visible

    def show_all(self):
        self.setHidden(False)


class Tree:
    def __init__(self, tree):
        self.tree = tree
        self.children = {}


    def clear(self):
        self.children = {}
        self.tree.clear()


    def sort(self):
        self.tree.sortItems(0, Qt.SortOrder.AscendingOrder)


    def filter(self, regex):
        for index in range(self.tree.topLevelItemCount()):
            self.tree.topLevelItem(index).filter(regex)


    def show_all(self):
        for index in range(self.tree.topLevelItemCount()):
            self.tree.topLevelItem(index).show_all()


    def make_path(self, path):
        parent = self

        for name in path:
            parent = parent.subfolder(name)

        return parent.tree


    def subfolder(self, name):
        try:
            return self.children[name]

        except KeyError:
            child = Folder(self, name)
            self.children[name] = child
            return child


class Folder(Tree):
    def __init__(self, parent, name):
        item = TreeItem(parent.tree, True, name)
        super().__init__(item)


@dataclass
class BundleInfo:
    key: str
    info: dict


class BundleName(QWidget):
    def __init__(self, root, text):
        super().__init__()

        self.root = root
        self.text = text

        self.layout_manager = LayoutManager(self)

        with self.layout_manager.row() as row:
            with row.tool_button(icon=Krita.icon("edit-rename"), tooltip="Change name") as button:
                button.clicked.connect(self.update_name)

            row.spacer(6)

            with row.label(text=text, tooltip="Bundle name") as label:
                pass

            row.stretch()

            with row.tool_button(icon=Krita.icon("window-close"), tooltip="Delete bundle") as button:
                button.clicked.connect(self.delete_bundle)


    def update_name(self):
        old_name = self.text

        new_name = self.root.bundle_name_dialog(old_name)

        if new_name is not None:
            self.root.rename_bundle(old_name, new_name)


    def delete_bundle(self):
        reply = QMessageBox.question(
            self,
            f"Delete {self.text}",
            "Are you sure you want to delete the bundle?",
        )

        if reply == QMessageBox.StandardButton.Yes:
            self.root.delete_bundle(self.text)


class SettingsBundles(QWidget):
    def __init__(self, extension, bundles):
        super().__init__()

        self.extension = extension
        self.bundles = bundles

        self.widgets = []
        self.selected_bundle = None

        self.layout_manager = LayoutManager(self)

        with self.layout_manager.row() as row:
            row.set_padding(left=10, top=10, right=10, bottom=10)

            with row.column() as column:
                with column.row() as top:
                    with top.tool_button(icon=Krita.icon("list-add"), tooltip="Make new bundle...") as button:
                        button.clicked.connect(self.new_bundle)

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
                    tree.header().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
                    tree.header().setStretchLastSection(False)
                    tree.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

                    tree.itemActivated.connect(self.on_item_clicked)

                    self.tree = Tree(tree)

            row.spacer(6)

            with row.column(stretch=1) as column:
                self.bundle_info = column

        self.update_tree()


    @staticmethod
    def process_bundle_name(name):
        return re.sub(r"/{2,}", "/", re.sub(r"\s*/\s*", "/", name))


    def make_parents(self, path):
        parent = Folder(self.tree, path[0])

        for name in path[1:]:
            parent = parent.make_child(name)

        return parent


    def update_bundle(self):
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
                tooltip="Prompt for the bundle",
                autocomplete=True,
                placeholder="Prompt...",
                background_color=None,
                min_lines=None,
                max_lines=None,
                auto_resize=False,
            ), stretch=1) as widget:
                self.widgets.append(widget)


    def on_item_clicked(self, item, column):
        if item is not None:
            if item.is_folder:
                item.setExpanded(not item.isExpanded())
                self.selected_bundle = None
            else:
                self.selected_bundle = item.info
        else:
            self.selected_bundle = None

        self.update_bundle()


    def bundle_name_dialog(self, initial):
        text, ok = QInputDialog.getText(self,
            "Bundle name",
            "Use / to put the bundle into a subfolder",
            text=initial,
        )

        if ok:
            text = text.strip()

            if text == "":
                QMessageBox.critical(self, "Invalid bundle name", "Bundle name cannot be empty")

            elif text[0] == "/":
                QMessageBox.critical(self, "Invalid bundle name", "Bundle name cannot start with /")

            elif text[-1] == "/":
                QMessageBox.critical(self, "Invalid bundle name", "Bundle name cannot end with /")

            else:
                return self.process_bundle_name(text)


    def rename_bundle(self, old_name, new_name):
        bundle = self.bundles.root.value(old_name, dict, default={})

        self.bundles.root.value(new_name, dict, default={}).set(bundle.get())

        bundle.remove()

        if self.selected_bundle is not None and self.selected_bundle.key == old_name:
            self.selected_bundle = BundleInfo(new_name, self.bundles.root.dict(new_name))
            self.update_bundle()

        self.update_tree()


    def delete_bundle(self, name):
        self.bundles.root.value(name, dict, default={}).remove()

        if self.selected_bundle is not None and self.selected_bundle.key == name:
            self.selected_bundle = None
            self.update_bundle()

        self.update_tree()


    def new_bundle(self):
        name = self.bundle_name_dialog("")

        if name is not None:
            self.bundles.root.value(name, dict, default={}).set({
                "prompt": ""
            })

            self.selected_bundle = BundleInfo(name, self.bundles.root.dict(name))
            self.update_bundle()
            self.update_tree()


    # TODO make this more efficient by using QSortFilterProxyModel
    def search_bundles(self):
        text = self.search_box.text().strip()

        if text == "":
            self.tree.show_all()

        else:
            text = self.process_bundle_name(text)

            compiled = re.compile(".*/.*".join([re.escape(x) for x in text.split("/")]), re.IGNORECASE)

            self.tree.filter(compiled)


    def update_tree(self):
        self.tree.clear()

        root = self.bundles.root

        for key in root.get().keys():
            path = key.split("/")

            parent = self.tree.make_path(path[:-1])

            child = TreeLeaf(
                parent=parent,
                name=path[-1],
                info=BundleInfo(key, root.dict(key)),
            )

            if self.selected_bundle is not None and self.selected_bundle.key == key:
                child.setSelected(True)
                self.tree.tree.scrollToItem(child, QAbstractItemView.ScrollHint.PositionAtCenter)

        self.tree.sort()


    def on_show(self):
        #self.update_tree()

        self.search_box.setFocus()
