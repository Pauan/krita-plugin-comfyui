# MIT License
#
# Copyright (c) 2019 Martin Fitzpatrick
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

from typing import Any

from PyQt6.QtCore import (
    Qt, QSize, QPoint, QPointF, QRectF,
    QEasingCurve, QPropertyAnimation, QSequentialAnimationGroup,
    pyqtProperty)  # pyright: ignore[reportAttributeAccessIssue, reportUnknownVariableType]

from PyQt6.QtWidgets import QCheckBox, QSizePolicy, QWidget
from PyQt6.QtGui import QColor, QBrush, QPaintEvent, QPen, QPainter


class Toggle(QCheckBox):

    _transparent_pen = QPen(Qt.GlobalColor.transparent)
    _light_grey_pen = QPen(Qt.GlobalColor.lightGray)

    def __init__(self,
        parent: QWidget | None = None,
        bar_color: Qt.GlobalColor | QColor = Qt.GlobalColor.gray,
        checked_color: str = "#00B0FF",
        handle_color: Qt.GlobalColor | QColor = Qt.GlobalColor.white,
        ) -> None:
        super().__init__(parent)

        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

        # Save our properties on the object via self, so we can access them later
        # in the paintEvent.
        self._bar_brush = QBrush(bar_color)
        self._bar_checked_brush = QBrush(QColor(checked_color).lighter())

        self._handle_brush = QBrush(handle_color)
        self._handle_checked_brush = QBrush(QColor(checked_color))

        # Setup the rest of the widget.

        self.setContentsMargins(4, 0, 6, 0)
        self._handle_position: float = 0

        self.stateChanged.connect(self.handle_state_change)

    def sizeHint(self) -> QSize:
        return QSize(52, 32)

    def hitButton(self, pos: QPoint) -> bool:
        return self.contentsRect().contains(pos)

    def paintEvent(self, a0: QPaintEvent | None) -> None:

        contRect = self.contentsRect()
        height = contRect.height() - 10
        handleRadius = round(0.5 * height)

        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        p.setPen(self._transparent_pen)
        barRect = QRectF(
            0,
            0,
            contRect.width() - handleRadius,
            height - 4
        )
        barRect.moveCenter(contRect.center().toPointF())
        rounding = barRect.height() / 2

        # the handle will move along this line
        trailLength = contRect.width() - 2 * handleRadius
        xPos = contRect.x() + handleRadius + trailLength * self._handle_position

        if self.isChecked():
            p.setBrush(self._bar_checked_brush)
            p.drawRoundedRect(barRect, rounding, rounding)
            p.setBrush(self._handle_checked_brush)

        else:
            p.setBrush(self._bar_brush)
            p.drawRoundedRect(barRect, rounding, rounding)
            p.setPen(self._light_grey_pen)
            p.setBrush(self._handle_brush)

        p.drawEllipse(
            QPointF(xPos, barRect.center().y()),
            handleRadius, handleRadius)

        p.end()

    def handle_state_change(self, value: int) -> None:
        self._handle_position = 1 if value else 0

    @pyqtProperty(int)  # pyright: ignore[reportUntypedFunctionDecorator, reportUnknownVariableType]
    def handle_position(self) -> float:  # pyright: ignore[reportRedeclaration]
        return self._handle_position

    @handle_position.setter  # pyright: ignore[reportFunctionMemberAccess]
    def handle_position(self, pos: float) -> None:
        """change the property
        we need to trigger QWidget.update() method, either by:
            1- calling it here [ what we're doing ].
            2- connecting the QPropertyAnimation.valueChanged() signal to it.
        """
        self._handle_position = pos
        self.update()

    @pyqtProperty(int)  # pyright: ignore[reportUntypedFunctionDecorator, reportUnknownVariableType]
    def pulse_radius(self) -> float:  # pyright: ignore[reportRedeclaration]
        return self._pulse_radius

    @pulse_radius.setter  # pyright: ignore[reportFunctionMemberAccess]
    def pulse_radius(self, pos: float) -> None:
        self._pulse_radius = pos
        self.update()


class AnimatedToggle(Toggle):

    _transparent_pen = QPen(Qt.GlobalColor.transparent)
    _light_grey_pen = QPen(Qt.GlobalColor.lightGray)

    def __init__(self, *args: Any, pulse_unchecked_color: str = "#44999999",
        pulse_checked_color: str = "#4400B0EE", **kwargs: Any) -> None:

        self._pulse_radius: float = 0

        super().__init__(*args, **kwargs)

        self.animation = QPropertyAnimation(self, b"handle_position", self)
        self.animation.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self.animation.setDuration(200)  # time in ms

        self.pulse_anim = QPropertyAnimation(self, b"pulse_radius", self)
        self.pulse_anim.setDuration(350)  # time in ms
        self.pulse_anim.setStartValue(10)
        self.pulse_anim.setEndValue(20)

        self.animations_group = QSequentialAnimationGroup()
        self.animations_group.addAnimation(self.animation)
        self.animations_group.addAnimation(self.pulse_anim)

        self._pulse_unchecked_animation = QBrush(QColor(pulse_unchecked_color))
        self._pulse_checked_animation = QBrush(QColor(pulse_checked_color))


    def handle_state_change(self, value: int) -> None:
        self.animations_group.stop()
        if value:
            self.animation.setEndValue(1)
        else:
            self.animation.setEndValue(0)
        self.animations_group.start()

    def paintEvent(self, a0: QPaintEvent | None) -> None:

        contRect = self.contentsRect()
        handleRadius = round(0.24 * contRect.height())

        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        p.setPen(self._transparent_pen)
        barRect = QRectF(
            0, 0,
            contRect.width() - handleRadius, 0.40 * contRect.height()
        )
        barRect.moveCenter(contRect.center().toPointF())
        rounding = barRect.height() / 2

        # the handle will move along this line
        trailLength = contRect.width() - 2 * handleRadius

        xPos = contRect.x() + handleRadius + trailLength * self._handle_position

        if self.pulse_anim.state() == QPropertyAnimation.State.Running:
            p.setBrush(
                self._pulse_checked_animation if
                self.isChecked() else self._pulse_unchecked_animation)
            p.drawEllipse(QPointF(xPos, barRect.center().y()),
                          self._pulse_radius, self._pulse_radius)

        if self.isChecked():
            p.setBrush(self._bar_checked_brush)
            p.drawRoundedRect(barRect, rounding, rounding)
            p.setBrush(self._handle_checked_brush)

        else:
            p.setBrush(self._bar_brush)
            p.drawRoundedRect(barRect, rounding, rounding)
            p.setPen(self._light_grey_pen)
            p.setBrush(self._handle_brush)

        p.drawEllipse(
            QPointF(xPos, barRect.center().y()),
            handleRadius, handleRadius)

        p.end()
