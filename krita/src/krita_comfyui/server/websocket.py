import json
from enum import Enum, auto

from PyQt6.QtCore import QObject, QTimer, QUrl, pyqtSignal, pyqtSlot
from PyQt6.QtWebSockets import QWebSocket
from PyQt6.QtNetwork import QAbstractSocket


class ConnectState(Enum):
    Disconnected = auto()
    Connecting = auto()
    Connected = auto()

class WebsocketClient(QObject):
    messages = pyqtSignal(dict)
    error = pyqtSignal(str)
    state_changed = pyqtSignal(ConnectState)

    def __init__(self, parent: QObject, url: str, reconnect_delay: int) -> None:
        super().__init__(parent)

        self.state = ConnectState.Disconnected
        self.should_connect = False

        self.url = url
        self.reconnect_delay = reconnect_delay

        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self._open_connection)

        self.client = QWebSocket(url)
        self.client.setParent(self)
        self.client.errorOccurred.connect(self.on_error)
        self.client.textMessageReceived.connect(self.on_text_message)
        self.client.connected.connect(self.on_connected)
        self.client.disconnected.connect(self.on_disconnected)

    def _change_state(self, state: ConnectState) -> None:
        if self.state != state:
            self.state = state
            self.state_changed.emit(self.state)

    # WebSocket is connected and active
    def is_ready(self) -> bool:
        return self.should_connect and self.state == ConnectState.Connected

    @pyqtSlot()
    def _open_connection(self) -> None:
        if self.should_connect and self.state == ConnectState.Disconnected:
            self.client.open(QUrl(self.url))
            self._change_state(ConnectState.Connecting)

    def connect(self) -> None:
        if not self.should_connect:
            self.should_connect = True
            self._open_connection()

    def disconnect(self) -> None:  # pyright: ignore[reportIncompatibleMethodOverride]
        if self.should_connect:
            self.should_connect = False
            self.timer.stop()
            self.client.close()
            self._change_state(ConnectState.Disconnected)

    @pyqtSlot()
    def on_connected(self) -> None:
        if self.should_connect:
            assert self.state != ConnectState.Connected
            self._change_state(ConnectState.Connected)
        else:
            assert self.state == ConnectState.Disconnected

    @pyqtSlot()
    def on_disconnected(self) -> None:
        if self.should_connect:
            self.timer.start(self.reconnect_delay)
        self._change_state(ConnectState.Disconnected)

    @pyqtSlot(QAbstractSocket.SocketError)
    def on_error(self, error: QAbstractSocket.SocketError) -> None:
        self.error.emit(self.client.errorString())

    @pyqtSlot(str)
    def on_text_message(self, message: str) -> None:
        if self.is_ready():
            self.messages.emit(json.loads(message))
