import json
from enum import Enum, auto

from PyQt6.QtCore import QObject, QTimer, pyqtSignal, pyqtSlot
from websockets.sync.client import connect
from ..util.qt import Thread


class ConnectState(Enum):
    Disconnected = auto()
    Connecting = auto()
    Connected = auto()


class WebsocketWorker(QObject):
    on_message = pyqtSignal(str)
    on_error = pyqtSignal(str)
    connected = pyqtSignal()
    disconnected = pyqtSignal()

    def __init__(self, url: str):
        super().__init__()
        self.url = url

    @pyqtSlot()
    def connect(self):
        try:
            ws = connect(self.url, max_size=None)

            self.connected.emit()

            for message in ws:
                if isinstance(message, str):
                    self.on_message.emit(message)

        except Exception as e:
            self.on_error.emit(str(e))

        self.disconnected.emit()


class WebsocketClient(QObject):
    messages = pyqtSignal(dict)
    error = pyqtSignal(str)
    state_changed = pyqtSignal(ConnectState)

    def __init__(self, parent: QObject, url: str, reconnect_delay: int) -> None:
        super().__init__(parent)

        self.worker: WebsocketWorker | None = None
        self.worker_thread: Thread | None = None

        self.state = ConnectState.Disconnected
        self.should_connect = False

        self.url = url
        self.reconnect_delay = reconnect_delay

        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self._open_connection)

    def _change_state(self, state: ConnectState) -> None:
        if self.state != state:
            self.state = state
            self.state_changed.emit(self.state)

    # WebSocket is connected and active
    @pyqtSlot()
    def is_ready(self) -> bool:
        return self.should_connect and self.state == ConnectState.Connected

    @pyqtSlot()
    def _open_connection(self) -> None:
        if self.should_connect and self.state == ConnectState.Disconnected:
            assert self.worker is None
            assert self.worker_thread is None

            self.worker = WebsocketWorker(self.url)
            self.worker.on_error.connect(self.on_error)
            self.worker.on_message.connect(self.on_text_message)
            self.worker.connected.connect(self.on_connected)
            self.worker.disconnected.connect(self.on_disconnected)

            self.worker_thread = Thread(self)
            self.worker_thread.started.connect(self.worker.connect)
            self.worker_thread.move(self.worker)
            self.worker_thread.start()

            self._change_state(ConnectState.Connecting)

    def connect(self) -> None:
        if not self.should_connect:
            self.should_connect = True
            self._open_connection()

    def _stop_thread(self):
        if self.worker_thread is not None:
            # TODO move this into extension.py somehow
            with self.worker_thread.stop():
                pass

        self.worker_thread = None
        self.worker = None

    @pyqtSlot()
    def disconnect(self) -> None:  # pyright: ignore[reportIncompatibleMethodOverride]
        if self.should_connect:
            self.should_connect = False
            self.timer.stop()

            self._stop_thread()
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
        self._stop_thread()
        if self.should_connect:
            self.timer.start(self.reconnect_delay)
        self._change_state(ConnectState.Disconnected)

    @pyqtSlot(str)
    def on_error(self, error: str) -> None:
        self.error.emit(error)

    @pyqtSlot(str)
    def on_text_message(self, message: str) -> None:
        if self.is_ready():
            self.messages.emit(json.loads(message))
