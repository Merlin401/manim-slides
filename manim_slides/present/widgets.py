"""Small Qt widgets shared by the presenter windows."""

from qtpy.QtCore import QSize
from qtpy.QtGui import QResizeEvent
from qtpy.QtWidgets import QSizePolicy, QWidget


class AspectBox(QWidget):
    """
    Host one child at a fixed aspect ratio.

    The box asks the layout for exactly ``width / ratio`` of height, so no
    letterbox space is left over to waste.
    """

    def __init__(self, child: QWidget, ratio: float) -> None:
        super().__init__()
        self.ratio = ratio
        self.child = child
        child.setParent(self)
        policy = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        policy.setHeightForWidth(True)
        self.setSizePolicy(policy)
        self.setMinimumSize(1, 1)

    def hasHeightForWidth(self) -> bool:  # noqa: N802
        return True

    def heightForWidth(self, width: int) -> int:  # noqa: N802
        return int(width / self.ratio)

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(640, int(640 / self.ratio))

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802
        fit_width = min(self.width(), int(self.height() * self.ratio))
        self.child.setGeometry(0, 0, fit_width, int(fit_width / self.ratio))
