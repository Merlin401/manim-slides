"""A video display that can draw the slide number (``k / N``) over the video."""

from qtpy.QtCore import QRectF, QSizeF, Qt
from qtpy.QtGui import QBrush, QColor, QFont, QPainter, QResizeEvent
from qtpy.QtMultimedia import QVideoSink
from qtpy.QtMultimediaWidgets import QGraphicsVideoItem
from qtpy.QtWidgets import (
    QFrame,
    QGraphicsScene,
    QGraphicsSimpleTextItem,
    QGraphicsView,
)

from ..config import NumberStyle

NUMBER_Z_INDEX = 10  # above the video item


class NumberedVideo(QGraphicsView):
    """
    Video in a graphics view, with the slide number as items on top of it.

    A plain widget laid over a :class:`~qtpy.QtMultimediaWidgets.QVideoWidget` never
    shows up, because the video widget renders on its own native surface, so the number
    needs to be a part of the same scene as the video. The scene has the size of the
    slides and is scaled to fit the view, so the number keeps its place and proportions
    at any window size.

    Use :attr:`video_item` as the video output of a media player.
    """

    def __init__(
        self,
        resolution: tuple[int, int],
        background: QColor,
        aspect_ratio_mode: Qt.AspectRatioMode,
        style: NumberStyle,
    ) -> None:
        super().__init__()
        self.style = style
        self.aspect_ratio_mode = aspect_ratio_mode
        width, height = resolution
        self._scene = QGraphicsScene(0, 0, width, height)
        self.setScene(self._scene)

        self.video_item = QGraphicsVideoItem()
        self.video_item.setSize(QSizeF(width, height))
        self.video_item.setAspectRatioMode(aspect_ratio_mode)
        self._scene.addItem(self.video_item)

        self._number = QGraphicsSimpleTextItem()
        self._total = QGraphicsSimpleTextItem()
        for item, color, size in (
            (self._number, style.color, style.size),
            (self._total, style.total_color, style.total_size),
        ):
            font = QFont(style.font) if style.font else QFont()
            font.setPixelSize(max(1, round(size * height)))
            item.setFont(font)
            item.setBrush(QBrush(QColor(color.as_hex())))
            item.setZValue(NUMBER_Z_INDEX)
            item.hide()
            self._scene.addItem(item)

        self.setBackgroundBrush(QBrush(background))
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)  # keys stay with the player window
        self.setInteractive(False)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

    def videoSink(self) -> QVideoSink:  # noqa: N802
        """Return the sink of the video, like :class:`QVideoWidget` does."""
        return self.video_item.videoSink()

    def set_number(self, number: tuple[int, int] | None) -> None:
        """Show ``k / N``, or nothing if ``number`` is :data:`None`."""
        if number is None:
            self._number.hide()
            self._total.hide()
            return
        k, total = number
        self._number.setText(str(k))
        self._total.setText(f"/ {total}")
        self._place()
        self._number.show()
        self._total.show()

    @property
    def number_text(self) -> str:
        """The text shown, empty if there is none."""
        if not self._number.isVisible():
            return ""
        return f"{self._number.text()} {self._total.text()}"

    def _place(self) -> None:
        """Right-align ``k / N`` at the style's margin, vertically centred on its line."""
        rect = self._scene.sceneRect()
        right = rect.right() - self.style.right * rect.width()
        middle = rect.bottom() - self.style.bottom * rect.height()
        total = self._total.boundingRect()
        number = self._number.boundingRect()
        gap = 0.25 * number.height() * 0.3
        self._total.setPos(right - total.width(), middle - total.height() / 2)
        self._number.setPos(
            right - total.width() - gap - number.width(), middle - number.height() / 2
        )

    def _fit(self) -> None:
        self.fitInView(QRectF(self._scene.sceneRect()), self.aspect_ratio_mode)

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._fit()

    def showEvent(self, event: object) -> None:  # noqa: N802
        super().showEvent(event)  # ty: ignore[invalid-argument-type]
        self._fit()
