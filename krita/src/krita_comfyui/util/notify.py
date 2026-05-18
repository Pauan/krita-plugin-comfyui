import desktop_notifier
import asyncio
from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot


async def notify(notifier, message):
    await notifier.send(
        title="Krita ComfyUI",
        message=message,
        urgency=desktop_notifier.Urgency.Low,
    )


class NotifyWorker(QObject):
    message = pyqtSignal(str)

    notifier = desktop_notifier.DesktopNotifier(
        app_name="Krita ComfyUI",
        app_icon=None,
    )

    def __init__(self):
        super().__init__()
        self.message.connect(self.on_message)

    @pyqtSlot(str)
    def on_message(self, message):
        asyncio.run(notify(self.notifier, message))
