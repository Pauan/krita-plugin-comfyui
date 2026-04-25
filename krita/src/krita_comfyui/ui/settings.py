class SettingsDialog(QDialog):
    def __init__(self, parent):
        super().__init__(parent)

        self.setWindowTitle("Configure Krita ComfyUI")
        self.setMinimumSize(QSize(960, 480))

        if screen := QGuiApplication.screenAt(QCursor.pos()):
            size = screen.availableSize()
            min_w = min(size.width(), QFontMetrics(self.font()).horizontalAdvance("M") * 100)
            self.resize(QSize(min_w, int(size.height() * 0.8)))

        layout = QHBoxLayout()
        self.setLayout(layout)

        self.connection = ConnectionSettings(server)
        self.styles = StylePresets(server)
        self.diffusion = DiffusionSettings()
        self.interface = InterfaceSettings()
        self.performance = PerformanceSettings()
        self.about = AboutSettings()

        self._stack = QStackedWidget(self)
        self._list = QListWidget(self)
        self._list.setFixedWidth(120)

        def create_list_item(text: str, widget: QWidget):
            item = QListWidgetItem(text, self._list)
            item.setSizeHint(QSize(112, 24))
            self._stack.addWidget(widget)

        create_list_item(_("Connection"), self.connection)
        create_list_item(_("Styles"), self.styles)
        create_list_item(_("Diffusion"), self.diffusion)
        create_list_item(_("Interface"), self.interface)
        create_list_item(_("Performance"), self.performance)
        create_list_item(_("Plugin"), self.about)

        self._list.setCurrentRow(0)
        self._list.currentRowChanged.connect(self._change_page)
        layout.addWidget(self._list)

        inner = QVBoxLayout()
        layout.addLayout(inner)
        inner.addWidget(self._stack)
        inner.addSpacing(6)

        self._restore_button = QPushButton(_("Restore Defaults"), self)
        self._restore_button.clicked.connect(self.restore_defaults)

        version_label = QLabel(_("Plugin version") + f": {__version__}", self)
        version_label.setStyleSheet(f"font-style:italic; color: {grey};")

        anchor = _("Open Settings folder")
        self._open_folder_link = QLabel(f"<a href='file://{util.user_data_dir}'>{anchor}</a>", self)
        self._open_folder_link.linkActivated.connect(self._open_settings_folder)
        self._open_folder_link.setToolTip(str(util.user_data_dir))

        self._close_button = QPushButton(_("Ok"), self)
        self._close_button.clicked.connect(self._close)

        button_layout = QHBoxLayout()
        button_layout.addWidget(self._restore_button)
        button_layout.addStretch()
        button_layout.addWidget(version_label)
        button_layout.addStretch()
        button_layout.addWidget(self._open_folder_link)
        button_layout.addSpacing(8)
        button_layout.addWidget(self._close_button)
        inner.addLayout(button_layout)

        root.connection.state_changed.connect(self._update_connection)
        root.connection.models_changed.connect(self.styles.update_model_lists)

    def show(self):
        super().show()
        self.close_button.setFocus()

    def _change_page(self, index):
        self._stack.setCurrentIndex(index)

    def _update_connection(self):
        self.connection.update_server_status()
        if root.connection.state is ConnectionState.connected:
            self.interface.update_translation(root.connection.client)
            self.performance.update_client_info()

    def _open_settings_folder(self):
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(util.user_data_dir)))
