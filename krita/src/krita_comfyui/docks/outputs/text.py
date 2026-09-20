from typing import Any, cast
from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import (
    QMenu,
    QSizePolicy,
    QWidget,
)
from shared import JSON
from ...util.krita import Document, DocumentManager
from ...util.qt import MessageBox, LayoutManager


class TextWidget(QWidget):
    def __init__(self, document: DocumentManager) -> None:
        super().__init__()

        self.document = document
        self.document.document_changed.connect(self.load_texts)

        self.texts: list[dict[str, Any]] = []

        self.text_menus: list[QAction] = []

        self.menu = QMenu(self)
        self.text_menus.append(cast(QAction, self.menu.addAction(Krita.icon("deletelayer"), "Delete all texts", self.clear_text)))

        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self.show_context_menu)

        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)

        self.layout_manager = LayoutManager(self)

        self.setStyleSheet("""
            QGroupBox {
                text-decoration: underline;
                font-weight: bold;
            }

            QGroupBox::title {
                subcontrol-position: top left;
                subcontrol-origin: border;
                margin-left: 8px;
                margin-top: 6px;
            }
        """)

        with self.layout_manager.column() as column:
            with column.scroll(max_height=200) as scroll:
                widget = QWidget()
                layout = LayoutManager(widget)

                with layout.column() as column:
                    self.column = column

                scroll.setWidget(widget)

        self.load_texts()


    def show_context_menu(self, pos: QPoint) -> None:
        has_text = len(self.texts) > 0

        for menu in self.text_menus:
            menu.setEnabled(has_text)

        self.menu.exec(self.mapToGlobal(pos))


    def load_texts(self) -> None:
        document = self.document.current()

        if document is not None:
            texts = cast(list[dict[str, Any]], document.get_key_json("krita_comfyui/output_texts", []))
        else:
            texts = []

        self.display_text(texts)


    def display_text(self, texts: list[dict[str, Any]]) -> None:
        self.texts = texts

        self.column.clear()

        if len(texts) == 0:
            self.setVisible(False)

        else:
            for text in texts:
                with self.column.group(title=text["name"]) as group:
                    layout = LayoutManager(group)

                    with layout.column() as column:
                        column.set_padding(left=8, right=8, bottom=6)

                        with column.label(text=text["text"], selectable=True) as label:
                            label.setWordWrap(True)

            self.setVisible(True)


    def clear_text(self) -> None:
        if MessageBox.question(self, "Are you sure you want to delete all output texts?"):
            self.set_text(self.document.current(), [])


    def set_text(self, document: Document | None, texts: list[dict[str, Any]]) -> None:
        if document is not None:
            if len(texts) == 0:
                document.remove_key("krita_comfyui/output_texts")
            else:
                document.set_key_json("krita_comfyui/output_texts", "krita_comfyui: Output Texts", cast(JSON, texts))

        if self.document.is_equal(document):
            self.display_text(texts)
