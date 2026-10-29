from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from qtpy.QtCore import Qt, QTimer, QUrl, Signal, Slot
from qtpy.QtGui import QCloseEvent, QColor, QIcon, QKeyEvent, QPixmap, QScreen
from qtpy.QtMultimedia import QAudioOutput, QMediaPlayer, QVideoFrame
from qtpy.QtMultimediaWidgets import QVideoWidget
from qtpy.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ..config import Config, PresentationConfig, SlideConfig, SlideType
from ..logger import logger
from ..numbering import NumberMode, slide_number
from ..resources import *
from .constants import (
    NOTES_PT,
    NOTES_PT_STEP,
    PREVIEW_WIDTH,
    clamp_notes_pt,
)
from .numbered_video import NumberedVideo
from .overview import Overview, thumbnail_path
from .widgets import AspectBox

WINDOW_NAME = "Manim Slides"


class Info(QWidget):
    key_press_event: Signal = Signal(QKeyEvent)
    close_event: Signal = Signal(QCloseEvent)

    def __init__(
        self,
        *,
        aspect_ratio_mode: Qt.AspectRatioMode,
        screen: QScreen | None,
        resolution: tuple[int, int] = (1920, 1080),
        notes_pt: float = NOTES_PT,
    ) -> None:
        super().__init__()

        if screen:
            self.setScreen(screen)
            self.move(screen.geometry().topLeft())

        ratio = resolution[0] / resolution[1]

        def media_box(video_widget: QVideoWidget, image_label: QLabel) -> AspectBox:
            """Video widget and image label stacked in a box of the slides' aspect ratio."""
            container = QWidget()
            container_layout = QVBoxLayout(container)
            container_layout.setContentsMargins(0, 0, 0, 0)
            container_layout.addWidget(video_widget)
            image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            image_label.setScaledContents(False)
            image_label.setMinimumSize(1, 1)
            image_label.hide()
            container_layout.addWidget(image_label)
            return AspectBox(container, ratio)

        def heading(text: str) -> QLabel:
            title = QLabel(text)
            font = title.font()
            font.setPointSize(10)
            font.setBold(True)
            title.setFont(font)
            title.setStyleSheet("color: #777;")
            return title

        def readout(caption: str, value: QLabel, size: int) -> QWidget:
            """Stack a small caption above its live value."""
            font = value.font()
            font.setPointSize(size)
            font.setBold(True)
            value.setFont(font)
            value.setAlignment(
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
            )
            box = QWidget()
            column = QVBoxLayout(box)
            column.setContentsMargins(0, 0, 0, 0)
            column.setSpacing(0)
            column.addWidget(heading(caption))
            column.addWidget(value)
            return box

        # Current slide view

        self.main_video_widget = QVideoWidget()
        self.main_video_widget.setAspectRatioMode(aspect_ratio_mode)
        self.video_sink = self.main_video_widget.videoSink()
        self.main_image_label = QLabel()
        current_box = media_box(self.main_video_widget, self.main_image_label)

        # Next slide preview

        self.next_video_widget = QVideoWidget()
        self.next_video_widget.setAspectRatioMode(aspect_ratio_mode)
        self.next_media_player = QMediaPlayer()
        self.next_media_player.setVideoOutput(self.next_video_widget)
        self.next_media_player.setLoops(-1)
        self.next_image_label = QLabel()
        preview_box = media_box(self.next_video_widget, self.next_image_label)
        preview_box.setFixedWidth(PREVIEW_WIDTH)

        # Slide information

        self.scene_label = QLabel()
        self.slide_label = QLabel()
        self.time_label = QLabel()
        self.elapsed_label = QLabel()
        self.start_time: datetime | None = None
        self.scene_box = readout("Scene", self.scene_label, 11)
        status = QVBoxLayout()
        status.addWidget(self.scene_box)
        status.addWidget(readout("Slide", self.slide_label, 16))
        status.addWidget(
            readout("Elapsed (start / restart key)", self.elapsed_label, 16)
        )
        status.addWidget(readout("Time", self.time_label, 11))
        status.addStretch(1)

        self.timer = QTimer()
        self.timer.start(250)  # so a restart shows up at once
        self.timer.timeout.connect(self.update_time)
        self.update_time()

        # Notes: they get the whole right column, in a scroll area that never takes
        # the keyboard focus, so a click on it does not stop the keys from working.

        self.slide_notes = QLabel()
        self.slide_notes.setWordWrap(True)
        self.slide_notes.setTextFormat(Qt.TextFormat.MarkdownText)
        self.slide_notes.setAlignment(
            Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft
        )
        self.slide_notes.setMargin(8)
        self.slide_notes.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.notes_scroll = QScrollArea()
        self.notes_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.notes_scroll.setWidgetResizable(True)
        self.notes_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.notes_scroll.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.notes_scroll.setWidget(self.slide_notes)
        self.initial_notes_pt = clamp_notes_pt(notes_pt)
        self.notes_pt = self.initial_notes_pt
        self._apply_notes_size()

        # Layout: the current slide takes the left column, with the next slide and
        # the status readouts under it, and everything stretches with the window.

        preview_column = QVBoxLayout()
        preview_column.addWidget(heading("Next slide"))
        preview_column.addWidget(preview_box)
        preview_column.addStretch(1)
        below = QHBoxLayout()
        below.addLayout(preview_column)
        below.addSpacing(24)
        below.addLayout(status)
        below.addStretch(1)

        left = QVBoxLayout()
        left.addWidget(heading("Current slide"))
        left.addWidget(current_box)
        left.addSpacing(12)
        left.addLayout(below)
        left.addStretch(1)
        right = QVBoxLayout()
        right.addWidget(heading("Notes"))
        right.addWidget(self.notes_scroll, 1)

        row = QHBoxLayout(self)
        row.setContentsMargins(24, 16, 24, 16)
        row.setSpacing(32)
        row.addLayout(left, 5)
        row.addLayout(right, 4)

    def _apply_notes_size(self) -> None:
        font = self.slide_notes.font()
        font.setPointSizeF(self.notes_pt)
        self.slide_notes.setFont(font)

    @Slot()
    def resize_notes(self, delta: float | None) -> None:
        """Change the size of the notes by ``delta`` points, or reset it if :data:`None`."""
        if delta is None:
            self.notes_pt = self.initial_notes_pt
        else:
            self.notes_pt = clamp_notes_pt(self.notes_pt + delta)
        self._apply_notes_size()

    @Slot()
    def start_timer(self) -> None:
        """Start the elapsed timer, or restart it from zero."""
        self.start_time = datetime.now(tz=timezone.utc).astimezone()
        self.update_time()

    @Slot()
    def update_time(self) -> None:
        now = datetime.now(tz=timezone.utc).astimezone()
        self.time_label.setText(now.strftime("%Y/%m/%d %H:%M:%S"))
        if self.start_time is None:
            self.elapsed_label.setText("not started")
            return
        hours, seconds = divmod(int((now - self.start_time).total_seconds()), 3600)
        minutes, seconds = divmod(seconds, 60)
        self.elapsed_label.setText(f"{hours:02d}h{minutes:02d}m{seconds:02d}s")

    @Slot()
    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        self.close_event.emit(event)

    @Slot()
    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        self.key_press_event.emit(event)


class Player(QMainWindow):
    presentation_changed: Signal = Signal()
    slide_changed: Signal = Signal()

    def __init__(
        self,
        config: Config,
        presentation_configs: list[PresentationConfig],
        *,
        start_paused: bool = False,
        full_screen: bool = False,
        skip_all: bool = False,
        exit_after_last_slide: bool = False,
        hide_mouse: bool = False,
        aspect_ratio_mode: Qt.AspectRatioMode = Qt.AspectRatioMode.KeepAspectRatio,
        presentation_index: int = 0,
        slide_index: int = 0,
        screen: QScreen | None = None,
        playback_rate: float = 1.0,
        next_terminates_loop: bool = False,
        hide_info_window: bool = False,
        info_window_screen: QScreen | None = None,
        notes_size: float = NOTES_PT,
        numbers: NumberMode | Literal["off"] | None = None,
    ):
        super().__init__()

        # Wizard's config

        self.config = config

        # Presentation configs

        self.presentation_configs = presentation_configs
        self.__current_presentation_index = 0
        self.__current_slide_index = 0

        self.current_presentation_index = presentation_index
        self.current_slide_index = slide_index

        self.__current_file: Path = self.current_slide_config.file

        self.__playing_reversed_slide = False

        self.__prev_pos = -1
        self.__termination_requested = False
        self.__termination_achieved = False

        # Widgets

        if screen:
            self.setScreen(screen)
            self.move(screen.geometry().topLeft())

        if full_screen:
            self.setWindowState(Qt.WindowState.WindowFullScreen)
        else:
            w, h = self.current_presentation_config.resolution
            geometry = self.geometry()
            geometry.setWidth(w)
            geometry.setHeight(h)
            self.setGeometry(geometry)

        if hide_mouse:
            self.setCursor(Qt.CursorShape.BlankCursor)

        self.setWindowTitle(WINDOW_NAME)
        self.icon = QIcon(":/icon.png")
        self.setWindowIcon(self.icon)

        self.frame = QVideoFrame()

        self.audio_output = QAudioOutput()
        # The slide number is drawn by a graphics view, which costs more than the plain
        # video widget, so that is only used when a number is asked for.
        self.numbers = numbers
        if numbers not in (None, "off") or any(c.numbers for c in presentation_configs):
            config_ = self.current_presentation_config
            self.video_widget: QVideoWidget | NumberedVideo = NumberedVideo(
                config_.resolution,
                QColor(config_.background_color.as_hex()),
                aspect_ratio_mode,
                config_.number_style,
            )
            self.video_output = self.video_widget.video_item
        else:
            self.video_widget = QVideoWidget()
            self.video_widget.setAspectRatioMode(aspect_ratio_mode)
            self.video_output = self.video_widget
        self.video_sink = self.video_widget.videoSink()

        self.image_label = QLabel(self)
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setScaledContents(False)
        w, h = self.current_presentation_config.resolution
        self.image_label.setMinimumSize(w, h)

        # Use QStackedWidget to switch between video and image without layout recalculation
        self.media_stack = QStackedWidget()
        self.media_stack.addWidget(self.video_widget)
        self.media_stack.addWidget(self.image_label)
        self.media_stack.setCurrentWidget(self.video_widget)

        self.setCentralWidget(self.media_stack)

        self.media_player = QMediaPlayer(self)
        self.media_player.setAudioOutput(self.audio_output)
        self.media_player.setVideoOutput(self.video_output)
        self.playback_rate = playback_rate

        self.presentation_changed.connect(self.presentation_changed_callback)
        self.slide_changed.connect(self.slide_changed_callback)

        self.info = Info(
            aspect_ratio_mode=aspect_ratio_mode,
            screen=info_window_screen,
            resolution=self.current_presentation_config.resolution,
            notes_pt=notes_size,
        )
        self.info.close_event.connect(self.closeEvent)
        self.info.key_press_event.connect(self.keyPressEvent)

        # The overview is one more page of the media stack: the video widget renders on
        # its own native surface, so a plain overlay on top of it would never show up.
        self._thumbs: dict[int, list[QPixmap | None]] = {}
        self._was_playing = False
        self._page_before_overview: QWidget | None = None
        self.overview = Overview(self)
        self.media_stack.addWidget(self.overview)
        self.overview.jump_requested.connect(self.jump_to)
        self.overview.close_requested.connect(self.close_overview)
        self._thumbnails()  # build the cache now rather than at the first key press
        self.video_sink.videoFrameChanged.connect(self.frame_changed)
        self.hide_info_window = hide_info_window

        # Connecting key callbacks

        self.config.keys.QUIT.connect(self.close)
        self.config.keys.PLAY_PAUSE.connect(self.play_pause)
        self.config.keys.NEXT.connect(self.next)
        self.config.keys.PREVIOUS.connect(self.previous)
        self.config.keys.REVERSE.connect(self.reverse)
        self.config.keys.REPLAY.connect(self.replay)
        self.config.keys.FULL_SCREEN.connect(self.full_screen)
        self.config.keys.HIDE_MOUSE.connect(self.hide_mouse)
        self.config.keys.OVERVIEW.connect(self.open_overview)
        self.config.keys.NOTES_BIGGER.connect(
            lambda: self.info.resize_notes(NOTES_PT_STEP)
        )
        self.config.keys.NOTES_SMALLER.connect(
            lambda: self.info.resize_notes(-NOTES_PT_STEP)
        )
        self.config.keys.NOTES_RESET.connect(lambda: self.info.resize_notes(None))
        self.config.keys.START_TIMER.connect(self.info.start_timer)

        self.dispatch = self.config.keys.dispatch_key_function()

        # Misc

        self.exit_after_last_slide = exit_after_last_slide
        self.next_terminates_loop = next_terminates_loop

        # Setting-up everything

        if skip_all:

            def media_status_changed(status: QMediaPlayer.MediaStatus) -> None:
                self.media_player.setLoops(1)  # Otherwise looping slides never end
                if status == QMediaPlayer.MediaStatus.EndOfMedia:
                    self.load_next_slide()

            self.media_player.mediaStatusChanged.connect(media_status_changed)

        else:

            def media_status_changed(status: QMediaPlayer.MediaStatus) -> None:
                if (
                    status == QMediaPlayer.MediaStatus.EndOfMedia
                    and self.current_slide_config.auto_next
                ):
                    self.load_next_slide()

            self.media_player.mediaStatusChanged.connect(media_status_changed)

        if next_terminates_loop:

            def on_position_changed(position: int) -> None:
                # non-monotonicity in the position, when occurring outside of the loading of a new slide, indicates looping
                if self.__termination_requested and self.__prev_pos > position:
                    if self.current_slide_config.auto_next:
                        self.load_next_slide()
                    else:
                        self.media_player.setPosition(self.media_player.duration())
                        self.media_player.pause()
                        self.__termination_achieved = True
                self.__prev_pos = position

            self.media_player.positionChanged.connect(on_position_changed)

        if self.current_slide_config.loop:
            self.media_player.setLoops(-1)

        self.load_current_media(start_paused=start_paused)

        self.presentation_changed.emit()
        self.slide_changed.emit()

    """
    Properties
    """

    @property
    def presentations_count(self) -> int:
        return len(self.presentation_configs)

    @property
    def current_presentation_index(self) -> int:
        return self.__current_presentation_index

    @current_presentation_index.setter
    def current_presentation_index(self, index: int) -> None:
        if 0 <= index < self.presentations_count:
            self.__current_presentation_index = index
        elif -self.presentations_count <= index < 0:
            self.__current_presentation_index = index + self.presentations_count
        else:
            logger.warning(f"Could not set presentation index to {index}.")
            return

        self.presentation_changed.emit()

    @property
    def current_presentation_config(self) -> PresentationConfig:
        return self.presentation_configs[self.current_presentation_index]

    @property
    def current_slides_count(self) -> int:
        return len(self.current_presentation_config.slides)

    @property
    def current_slide_index(self) -> int:
        return self.__current_slide_index

    @current_slide_index.setter
    def current_slide_index(self, index: int) -> None:
        if 0 <= index < self.current_slides_count:
            self.__current_slide_index = index
        elif -self.current_slides_count <= index < 0:
            self.__current_slide_index = index + self.current_slides_count
        else:
            logger.warning(f"Could not set slide index to {index}.")
            return

        self.slide_changed.emit()

    @property
    def current_slide_config(self) -> SlideConfig:
        return self.current_presentation_config.slides[self.current_slide_index]

    @property
    def current_file(self) -> Path:
        return self.__current_file

    @current_file.setter
    def current_file(self, file: Path) -> None:
        self.__current_file = file

    @property
    def previous_slide_config(self) -> SlideConfig | None:
        if self.current_slide_index > 0:
            return self.current_presentation_config.slides[self.current_slide_index - 1]
        elif self.current_presentation_index > 0:
            return self.presentation_configs[
                self.current_presentation_index - 1
            ].slides[-1]
        else:
            return None

    @property
    def next_slide_config(self) -> SlideConfig | None:
        if self.playing_reversed_slide:
            return self.current_slide_config
        elif self.current_slide_index < self.current_slides_count - 1:
            return self.presentation_configs[self.current_presentation_index].slides[
                self.current_slide_index + 1
            ]
        elif self.current_presentation_index < self.presentations_count - 1:
            return self.presentation_configs[
                self.current_presentation_index + 1
            ].slides[0]
        else:
            return None

    @property
    def next_file(self) -> Path | None:
        if slide_config := self.next_slide_config:
            return slide_config.file

        return None

    @property
    def playing_reversed_slide(self) -> bool:
        return self.__playing_reversed_slide

    @playing_reversed_slide.setter
    def playing_reversed_slide(self, playing_reversed_slide: bool) -> None:
        self.__playing_reversed_slide = playing_reversed_slide

    """
    Loading slides
    """

    def load_current_media(self, start_paused: bool = False) -> None:
        url = QUrl.fromLocalFile(str(self.current_file.resolve(strict=True)))
        if self.current_slide_config.type == SlideType.Video or (
            self.current_slide_config.type == SlideType.Image
            and self.current_file.suffix.lower() == ".gif"
        ):
            self.media_player.setSource(url)

            self.media_stack.setCurrentWidget(self.video_widget)
            self.info.main_image_label.hide()
            self.info.main_video_widget.show()

            if self.playing_reversed_slide:
                self.media_player.setPlaybackRate(
                    self.current_slide_config.reversed_playback_rate
                    * self.playback_rate
                )
            else:
                self.media_player.setPlaybackRate(
                    self.current_slide_config.playback_rate * self.playback_rate
                )

            if start_paused:
                self.media_player.pause()
            else:
                self.media_player.play()
        else:
            w, _ = self.current_presentation_config.resolution
            pixmap = QPixmap(url.toLocalFile())
            scaled_pixmap = pixmap.scaledToWidth(w)
            self.image_label.setPixmap(scaled_pixmap)
            self.info.main_image_label.setPixmap(scaled_pixmap)

            self.media_player.stop()

            self.media_stack.setCurrentWidget(self.image_label)
            self.info.main_image_label.show()
            self.info.main_video_widget.hide()

    def load_current_slide(self) -> None:
        slide_config = self.current_slide_config
        if self.playing_reversed_slide:
            self.current_file = slide_config.rev_file
        else:
            self.current_file = slide_config.file

        if slide_config.loop:
            self.media_player.setLoops(-1)
        else:
            self.media_player.setLoops(1)

        self.__prev_pos = -1
        self.__termination_requested = False
        self.__termination_achieved = False

        self.load_current_media()

    def load_previous_slide(self) -> None:
        if self.current_slide_index > 0:
            self.current_slide_index -= 1
        elif self.current_presentation_index > 0:
            self.current_presentation_index -= 1
            self.current_slide_index = self.current_slides_count - 1
        else:
            logger.info("No previous slide.")
            return

        self.load_current_slide()

    def load_next_slide(self) -> None:
        if self.playing_reversed_slide:
            self.playing_reversed_slide = False
            self.preview_next_slide()  # Slide number did not change, but next did
        elif self.current_slide_index < self.current_slides_count - 1:
            self.current_slide_index += 1
        elif self.current_presentation_index < self.presentations_count - 1:
            self.current_presentation_index += 1
            self.current_slide_index = 0
        elif self.exit_after_last_slide:
            self.close()
            return
        else:
            logger.info("No more slide to play.")
            return

        self.load_current_slide()

    """
    Key callbacks and slots
    """

    @Slot()
    def presentation_changed_callback(self) -> None:
        index = self.current_presentation_index
        count = self.presentations_count
        self.info.scene_label.setText(f"{index + 1}/{count}")
        self.info.scene_box.setVisible(count > 1)

    @Slot()
    def slide_changed_callback(self) -> None:
        index = self.current_slide_index
        count = self.current_slides_count
        self.info.slide_label.setText(f"{index + 1}/{count}")
        self.info.slide_notes.setText(self.current_slide_config.notes)
        if self.info.start_time is None and index > 0:
            self.info.start_timer()  # the talk has started
        self.update_number()
        self.preview_next_slide()

    @property
    def number_mode(self) -> NumberMode | None:
        """What the slide number counts: the option, else the scene's own default."""
        if self.numbers == "off":
            return None
        return self.numbers or self.current_presentation_config.numbers

    def update_number(self) -> None:
        """Show the number of the current slide, if numbers are on."""
        if not isinstance(self.video_widget, NumberedVideo):
            return
        mode = self.number_mode
        self.video_widget.set_number(
            slide_number(
                self.current_presentation_config.slides, self.current_slide_index, mode
            )
            if mode
            else None
        )

    def _thumbnails(self) -> list[QPixmap | None]:
        index = self.current_presentation_index
        if index not in self._thumbs:
            slides = self.current_presentation_config.slides
            with ThreadPoolExecutor() as pool:
                paths = list(pool.map(thumbnail_path, slides))
            self._thumbs[index] = [QPixmap(str(p)) if p else None for p in paths]
        return self._thumbs[index]

    @property
    def overview_open(self) -> bool:
        return self.media_stack.currentWidget() is self.overview

    @Slot()
    def open_overview(self) -> None:
        """Pause and show a grid of all slides, to jump to one of them."""
        if self.overview_open:
            return
        state = self.media_player.playbackState()
        self._was_playing = state == QMediaPlayer.PlaybackState.PlayingState
        self.media_player.pause()
        w, h = self.current_presentation_config.resolution
        self._page_before_overview = self.media_stack.currentWidget()
        self.media_stack.setCurrentWidget(self.overview)
        self.overview.set_slides(self._thumbnails(), self.current_slide_index, h / w)

    def _leave_overview(self) -> None:
        """Switch back to the page shown before the overview opened."""
        if self._page_before_overview is not None:
            self.media_stack.setCurrentWidget(self._page_before_overview)
        if self._page_before_overview is self.video_widget:
            self.video_sink.setVideoFrame(self.frame)  # repaint the paused frame

    @Slot()
    def close_overview(self) -> None:
        self._leave_overview()
        if self._was_playing:
            self.media_player.play()

    @Slot(int)
    def jump_to(self, index: int) -> None:
        """Leave the overview and play the slide of the current presentation at ``index``."""
        if index == self.current_slide_index:
            self.close_overview()
            return
        self._leave_overview()
        self.playing_reversed_slide = False
        self.current_slide_index = index
        self.load_current_slide()

    def preview_next_slide(self) -> None:
        if slide_config := self.next_slide_config:
            url = QUrl.fromLocalFile(str(slide_config.file.resolve(strict=True)))
            if self.next_slide_config.type == SlideType.Video:
                self.info.next_video_widget.show()
                self.info.next_image_label.hide()
                self.info.next_media_player.setSource(url)
                self.info.next_media_player.play()
            else:
                self.info.next_video_widget.hide()
                self.info.next_image_label.show()
                self.info.next_media_player.stop()
                w, _ = self.current_presentation_config.resolution
                pixmap = QPixmap(url.toLocalFile())
                scaled_pixmap = pixmap.scaledToWidth(w)
                self.info.next_image_label.setPixmap(scaled_pixmap)

    def show(  # ty: ignore[invalid-method-override]
        self, screens: list[QScreen]
    ) -> None:
        """Screens is necessary to prevent the info window from being shown on the same screen as the main window (especially in full screen mode)."""
        super().show()

        if not self.hide_info_window:
            if len(screens) > 1 and self.isFullScreen():
                self.ensure_different_screens(screens)

            if self.isFullScreen():
                self.info.showFullScreen()
            else:
                self.info.show()

            if (
                len(screens) > 1 and self.info.screen() == self.screen()
            ):  # It is better when Qt assigns the location, but if it fails to, this is a fallback
                self.ensure_different_screens(screens)

    def ensure_different_screens(self, screens: list[QScreen]) -> None:
        target_screen = screens[1] if self.screen() == screens[0] else screens[0]
        self.info.setScreen(target_screen)
        self.info.move(target_screen.geometry().topLeft())

    @Slot()
    def close(self) -> None:
        logger.info("Closing gracefully...")
        self.info.close()
        super().close()

    @Slot()
    def next(self) -> None:
        if (
            self.media_player.playbackState() == QMediaPlayer.PlaybackState.PausedState
            and not self.__termination_achieved
        ):
            self.media_player.play()
        elif (
            self.next_terminates_loop
            and self.media_player.loops() != 1
            and not self.__termination_achieved
        ):
            self.__termination_requested = True
        else:
            self.load_next_slide()

    @Slot()
    def previous(self) -> None:
        """Go back one slide, playing its reversed clip if there is one."""
        previous = self.previous_slide_config
        self.playing_reversed_slide = (
            previous is not None and previous.rev_file != previous.file
        )
        self.load_previous_slide()

    @Slot()
    def reverse(self) -> None:
        """Go back one slide, playing its reversed clip (the slide itself if it has none)."""
        self.playing_reversed_slide = self.previous_slide_config is not None
        self.load_previous_slide()

    @Slot()
    def replay(self) -> None:
        self.__prev_pos = -1
        self.__termination_requested = False
        self.__termination_achieved = False
        self.media_player.setPosition(0)
        self.media_player.play()

    @Slot()
    def play_pause(self) -> None:
        state = self.media_player.playbackState()
        if (
            state == QMediaPlayer.PlaybackState.PausedState
            and not self.__termination_achieved
        ):
            self.media_player.play()
        elif state == QMediaPlayer.PlaybackState.PlayingState:
            self.media_player.pause()

    @Slot()
    def full_screen(self) -> None:
        if self.windowState() == Qt.WindowState.WindowFullScreen:
            self.setWindowState(Qt.WindowState.WindowNoState)
            self.info.setWindowState(Qt.WindowState.WindowNoState)
        else:
            self.setWindowState(Qt.WindowState.WindowFullScreen)
            self.info.setWindowState(Qt.WindowState.WindowFullScreen)

    @Slot()
    def hide_mouse(self) -> None:
        if self.cursor().shape() == Qt.CursorShape.BlankCursor:
            self.setCursor(Qt.CursorShape.ArrowCursor)
        else:
            self.setCursor(Qt.CursorShape.BlankCursor)

    def frame_changed(self, frame: QVideoFrame) -> None:
        """
        Slot to handle possibly invalid frames.

        This slot cannot be decorated with ``@Slot`` as
        the video sinks are handled in different threads.

        As of Qt>=6.5.3, the last frame of every video is "flushed",
        resulting in a short black screen between each slide.

        To avoid this issue, we check every frame, and avoid playing
        invalid ones.

        References
        ----------
        1. https://github.com/jeertmans/manim-slides/issues/293
        2. https://github.com/jeertmans/manim-slides/pull/464

        :param frame: The most recent frame.

        """
        if frame.isValid():
            self.frame = frame
        else:
            self.video_sink.setVideoFrame(self.frame)  # Reuse previous frame

        self.info.video_sink.setVideoFrame(self.frame)

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        self.close()

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        key = event.key()
        if self.overview_open:
            self.overview.handle_key(key)
        else:
            self.dispatch(key)
        event.accept()
