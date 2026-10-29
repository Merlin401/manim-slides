"""
Slide overview: a grid with the last frame of every slide.

The player shows it on a key press (``OVERVIEW``, by default ``O`` or ``Esc``) while
the video pauses. Arrow keys move the highlight, ``Enter`` jumps to that slide, digits
followed by ``Enter`` jump to a slide number, and a click on a tile jumps too.
"""

import math
from pathlib import Path

from qtpy.QtCore import QPointF, QRectF, Qt, Signal
from qtpy.QtGui import (
    QColor,
    QFont,
    QMouseEvent,
    QPainter,
    QPaintEvent,
    QPen,
    QPixmap,
    QWheelEvent,
)
from qtpy.QtWidgets import QWidget

from ..config import SlideConfig, SlideType
from ..logger import logger

COLUMNS = 4
MARGIN = 28
GAP = 18
THUMB_WIDTH = 480  # px, cached thumbnails are scaled down to this
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".bmp"}

BACKGROUND = QColor("#262626")
TILE_EMPTY = QColor("#404040")
ACCENT = QColor("#E6002E")
BADGE = QColor(0, 0, 0, 190)


def _last_frame_png(src: Path, dst: Path) -> None:
    """Write the final frame of the video ``src`` to ``dst`` as a PNG, using PyAV."""
    import av

    with av.open(str(src)) as container:
        if container.duration:
            duration = container.duration / av.time_base
            if duration > 0.5:
                container.seek(int((duration - 0.5) * av.time_base))
        last = None
        for frame in container.decode(video=0):
            last = frame
    if last is None:
        return
    image = last.to_image()
    image.thumbnail((THUMB_WIDTH, THUMB_WIDTH))
    dst.parent.mkdir(exist_ok=True)
    image.save(dst)


def thumbnail_path(slide_config: SlideConfig) -> Path | None:
    """
    Return the path of an up-to-date thumbnail of a slide.

    It is created if missing or older than the slide clip, and cached in a ``.thumbs``
    folder next to the clips. Returns :data:`None` if it cannot be made.
    """
    src = Path(slide_config.file)
    if slide_config.type == SlideType.Image and src.suffix.lower() in IMAGE_SUFFIXES:
        return src
    dst = src.parent / ".thumbs" / f"{src.stem}.png"
    try:
        if not dst.exists() or dst.stat().st_mtime < src.stat().st_mtime:
            _last_frame_png(src, dst)
        return dst if dst.exists() else None
    except Exception as e:  # noqa: BLE001
        logger.warning(f"No thumbnail for {src.name}: {e}")
        return None


class Overview(QWidget):
    """Full-window grid of slide thumbnails, painted by hand (no child widgets)."""

    jump_requested = Signal(int)
    close_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)  # keys stay with the player window
        self.setMouseTracking(True)
        self.pixmaps: list[QPixmap | None] = []
        self.aspect = 9 / 16
        self.selected = 0
        self.current = 0
        self.offset = 0.0  # scroll position in px
        self.typed = ""  # digits typed for a "go to slide N" jump

    def set_slides(
        self, pixmaps: list[QPixmap | None], current: int, aspect: float
    ) -> None:
        self.pixmaps = pixmaps
        self.aspect = aspect
        self.current = self.selected = current
        self.typed = ""
        self.offset = 0.0
        self._scroll_to_selected()
        self.update()

    # layout

    def _tile_size(self) -> tuple[float, float]:
        width = (self.width() - 2 * MARGIN - (COLUMNS - 1) * GAP) / COLUMNS
        return width, width * self.aspect

    def _tile_rect(self, i: int) -> QRectF:
        w, h = self._tile_size()
        row, col = divmod(i, COLUMNS)
        return QRectF(
            MARGIN + col * (w + GAP), MARGIN + row * (h + GAP) - self.offset, w, h
        )

    def _content_height(self) -> float:
        _, h = self._tile_size()
        rows = math.ceil(len(self.pixmaps) / COLUMNS)
        return 2 * MARGIN + rows * h + (rows - 1) * GAP

    def _clamp_offset(self) -> None:
        self.offset = max(0.0, min(self.offset, self._content_height() - self.height()))

    def _scroll_to_selected(self) -> None:
        rect = self._tile_rect(self.selected)
        if rect.top() < MARGIN:
            self.offset += rect.top() - MARGIN
        elif rect.bottom() > self.height() - MARGIN:
            self.offset += rect.bottom() - (self.height() - MARGIN)
        self._clamp_offset()

    def _tile_at(self, pos: QPointF) -> int | None:
        for i in range(len(self.pixmaps)):
            if self._tile_rect(i).contains(pos):
                return i
        return None

    # painting

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        p.fillRect(self.rect(), BACKGROUND)
        p.setFont(QFont("Liberation Sans", 11, QFont.Weight.Bold))

        for i, pixmap in enumerate(self.pixmaps):
            rect = self._tile_rect(i)
            if rect.bottom() < 0 or rect.top() > self.height():
                continue
            if pixmap is not None:
                p.drawPixmap(rect, pixmap, QRectF(pixmap.rect()))
            else:
                p.fillRect(rect, TILE_EMPTY)

            if i == self.selected:
                p.setPen(QPen(ACCENT, 5))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawRect(rect.adjusted(-2, -2, 2, 2))

            label = str(i + 1) + ("  ·  now" if i == self.current else "")
            badge_w = 14 + p.fontMetrics().horizontalAdvance(label)
            badge = QRectF(rect.left() + 6, rect.bottom() - 26, badge_w, 20)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(ACCENT if i == self.selected else BADGE)
            p.drawRoundedRect(badge, 4, 4)
            p.setPen(QColor("white"))
            p.drawText(badge, Qt.AlignmentFlag.AlignCenter, label)

        if self.typed:
            box = QRectF(self.width() / 2 - 90, 6, 180, 26)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(ACCENT)
            p.drawRoundedRect(box, 5, 5)
            p.setPen(QColor("white"))
            p.drawText(box, Qt.AlignmentFlag.AlignCenter, f"Go to slide: {self.typed}")

    # input

    def _move(self, delta: int) -> None:
        self.selected = max(0, min(len(self.pixmaps) - 1, self.selected + delta))
        self.typed = ""
        self._scroll_to_selected()
        self.update()

    def handle_key(self, key: int) -> None:
        """React to a key press while the overview is open."""
        rows_per_page = max(1, int(self.height() // (self._tile_size()[1] + GAP)))
        moves = {
            Qt.Key.Key_Left: -1,
            Qt.Key.Key_Right: 1,
            Qt.Key.Key_Up: -COLUMNS,
            Qt.Key.Key_Down: COLUMNS,
            Qt.Key.Key_PageUp: -COLUMNS * rows_per_page,
            Qt.Key.Key_PageDown: COLUMNS * rows_per_page,
            Qt.Key.Key_Home: -len(self.pixmaps),
            Qt.Key.Key_End: len(self.pixmaps),
        }
        if key in moves:
            self._move(moves[key])
        elif key in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            if self.typed:
                self.selected = max(0, min(len(self.pixmaps) - 1, int(self.typed) - 1))
            self.jump_requested.emit(self.selected)
        elif Qt.Key.Key_0 <= key <= Qt.Key.Key_9:
            self.typed = (self.typed + chr(key))[-3:]
            self.update()
        elif key == Qt.Key.Key_Backspace:
            self.typed = self.typed[:-1]
            self.update()
        elif key in (Qt.Key.Key_Escape, Qt.Key.Key_O):
            self.close_requested.emit()

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        i = self._tile_at(event.position())
        if i is not None:
            self.jump_requested.emit(i)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        i = self._tile_at(event.position())
        if i is not None and i != self.selected:
            self.selected = i
            self.typed = ""
            self.update()

    def wheelEvent(self, event: QWheelEvent) -> None:  # noqa: N802
        self.offset -= event.angleDelta().y() / 2
        self._clamp_offset()
        self.update()
