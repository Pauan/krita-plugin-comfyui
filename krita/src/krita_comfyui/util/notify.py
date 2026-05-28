import desktop_notifier
import asyncio
from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot


async def notify(notifier: desktop_notifier.DesktopNotifier, message: str):
    await notifier.send(
        title="Krita ComfyUI",
        message=message,
        urgency=desktop_notifier.Urgency.Low,
    )


class NotifyWorker(QObject):
    message = pyqtSignal(str)

    def __init__(self):
        super().__init__()

        self.notifier = None
        self.message.connect(self.on_message)

    @pyqtSlot(str)
    def on_message(self, message: str):
        if self.notifier is None:
            self.notifier = desktop_notifier.DesktopNotifier(
                app_name="Krita ComfyUI",
                app_icon=None,
            )

        asyncio.run(notify(self.notifier, message))
