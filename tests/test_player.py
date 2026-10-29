import re
import shutil
from collections.abc import Iterator
from pathlib import Path

import pytest
from click.testing import CliRunner
from pytestqt.qtbot import QtBot
from qtpy.QtCore import Qt
from qtpy.QtGui import QColor
from qtpy.QtMultimediaWidgets import QVideoWidget
from qtpy.QtTest import QTest
from qtpy.QtWidgets import QApplication

from manim_slides.__main__ import cli
from manim_slides.config import (
    Config,
    Keys,
    NumberStyle,
    PresentationConfig,
    SlideConfig,
)
from manim_slides.present.constants import (
    NOTES_PT,
    NOTES_PT_RANGE,
    NOTES_PT_STEP,
    clamp_notes_pt,
)
from manim_slides.present.numbered_video import NumberedVideo
from manim_slides.present.overview import Overview, thumbnail_path
from manim_slides.present.player import Player


@pytest.fixture
def player(presentation_config: PresentationConfig, qtbot: QtBot) -> Iterator[Player]:
    player = Player(Config(), [presentation_config], start_paused=True)
    qtbot.addWidget(player)
    qtbot.addWidget(player.info)
    player.info.resize(1600, 900)
    player.show(QApplication.screens())
    yield player
    player.info.timer.stop()


def press(player: Player, key: Qt.Key) -> None:
    """Press a key in the info window, as a presenter would."""
    QTest.keyClick(player.info, key)


def test_default_keys_do_not_clash() -> None:
    keys = Keys()

    assert Qt.Key.Key_O in keys.OVERVIEW.ids and Qt.Key.Key_Escape in keys.OVERVIEW.ids
    assert Qt.Key.Key_S in keys.START_TIMER.ids


def test_clamp_notes_pt() -> None:
    low, high = NOTES_PT_RANGE

    assert clamp_notes_pt(1) == low
    assert clamp_notes_pt(1000) == high
    assert clamp_notes_pt(20) == 20


@pytest.mark.parametrize("key", [Qt.Key.Key_Plus, Qt.Key.Key_Equal])
def test_notes_bigger_smaller_reset(player: Player, key: Qt.Key) -> None:
    info = player.info
    assert info.notes_pt == NOTES_PT

    press(player, key)
    assert info.notes_pt == NOTES_PT + NOTES_PT_STEP
    assert info.slide_notes.font().pointSizeF() == NOTES_PT + NOTES_PT_STEP

    press(player, Qt.Key.Key_Minus)
    press(player, Qt.Key.Key_Minus)
    assert info.notes_pt == NOTES_PT - NOTES_PT_STEP

    press(player, Qt.Key.Key_0)
    assert info.notes_pt == NOTES_PT
    assert info.slide_notes.font().pointSizeF() == NOTES_PT


def test_notes_size_is_limited(player: Player) -> None:
    for _ in range(100):
        press(player, Qt.Key.Key_Plus)
    assert player.info.notes_pt == NOTES_PT_RANGE[1]

    for _ in range(100):
        press(player, Qt.Key.Key_Minus)
    assert player.info.notes_pt == NOTES_PT_RANGE[0]


def test_notes_start_size_and_reset(
    presentation_config: PresentationConfig, qtbot: QtBot
) -> None:
    player = Player(Config(), [presentation_config], start_paused=True, notes_size=30)
    qtbot.addWidget(player)
    qtbot.addWidget(player.info)

    assert player.info.notes_pt == 30
    player.info.resize_notes(+NOTES_PT_STEP)
    player.info.resize_notes(None)
    assert player.info.notes_pt == 30
    player.info.timer.stop()


def test_clicking_the_notes_keeps_the_keys_working(player: Player) -> None:
    info = player.info
    presses: list[int] = []
    player.config.keys.NEXT.connect(lambda: presses.append(1))

    for widget in (info.notes_scroll, info.slide_notes):
        assert widget.focusPolicy() == Qt.FocusPolicy.NoFocus

    QTest.mouseClick(info.notes_scroll.viewport(), Qt.MouseButton.LeftButton)
    QTest.keyClick(QApplication.focusWidget() or info, Qt.Key.Key_Right)

    assert presses == [1]


def test_timer_waits_for_start(player: Player) -> None:
    info = player.info
    assert info.start_time is None
    assert info.elapsed_label.text() == "not started"

    press(player, Qt.Key.Key_S)

    assert info.start_time is not None
    assert re.fullmatch(r"00h00m0\ds", info.elapsed_label.text())

    first = info.start_time
    QTest.qWait(1100)
    press(player, Qt.Key.Key_S)  # restart from zero
    assert info.start_time > first
    assert info.elapsed_label.text() == "00h00m00s"


def test_timer_starts_when_leaving_the_first_slide(player: Player) -> None:
    assert player.current_slide_index == 0
    assert player.info.start_time is None

    player.load_next_slide()

    assert player.current_slide_index == 1
    assert player.info.start_time is not None


def test_status_labels(player: Player) -> None:
    count = player.current_slides_count

    assert player.info.slide_label.text() == f"1/{count}"
    assert player.info.scene_box.isHidden()  # a single scene needs no counter

    player.load_next_slide()
    assert player.info.slide_label.text() == f"2/{count}"


def test_info_layout_gives_the_notes_room(player: Player) -> None:
    info = player.info

    assert info.notes_scroll.width() > 500
    assert info.main_video_widget.width() > 700


def test_overview_navigation(player: Player, qtbot: QtBot) -> None:
    count = player.current_slides_count
    assert not player.overview_open

    press(player, Qt.Key.Key_O)

    assert player.overview_open
    assert len(player.overview.pixmaps) == count
    assert player.overview.selected == player.current_slide_index == 0

    press(player, Qt.Key.Key_Right)
    press(player, Qt.Key.Key_Right)
    assert player.overview.selected == 2
    assert player.current_slide_index == 0  # nothing jumps before Enter

    press(player, Qt.Key.Key_End)
    assert player.overview.selected == count - 1

    press(player, Qt.Key.Key_Escape)  # closes and stays where it was
    assert not player.overview_open
    assert player.current_slide_index == 0

    press(player, Qt.Key.Key_O)
    press(player, Qt.Key.Key_Down)
    press(player, Qt.Key.Key_Return)  # jumps
    assert not player.overview_open
    assert player.current_slide_index == min(4, count - 1)


def test_overview_digits_jump_to_a_slide_number(player: Player) -> None:
    press(player, Qt.Key.Key_O)
    press(player, Qt.Key.Key_3)
    press(player, Qt.Key.Key_Return)

    assert not player.overview_open
    assert player.current_slide_index == 2


def test_overview_swallows_the_notes_keys(player: Player) -> None:
    press(player, Qt.Key.Key_O)
    press(player, Qt.Key.Key_0)  # a digit for the jump, not "reset the notes"
    press(player, Qt.Key.Key_S)

    assert player.overview.typed == "0"
    assert player.info.start_time is None


def test_overview_jump_on_the_current_slide_just_closes(player: Player) -> None:
    press(player, Qt.Key.Key_O)
    press(player, Qt.Key.Key_Return)

    assert not player.overview_open
    assert player.current_slide_index == 0


def test_overview_widget_keys_and_clicks(qtbot: QtBot) -> None:
    overview = Overview()
    qtbot.addWidget(overview)
    overview.resize(1000, 700)
    overview.set_slides([None] * 10, current=2, aspect=9 / 16)

    assert overview.selected == overview.current == 2

    overview.handle_key(Qt.Key.Key_Down)
    assert overview.selected == 6

    overview.handle_key(Qt.Key.Key_Home)
    assert overview.selected == 0

    overview.handle_key(Qt.Key.Key_9)
    overview.handle_key(Qt.Key.Key_9)
    overview.handle_key(Qt.Key.Key_Backspace)
    with qtbot.waitSignal(overview.jump_requested) as blocker:
        overview.handle_key(Qt.Key.Key_Return)
    assert blocker.args == [8]  # "9" is the ninth slide

    rect = overview._tile_rect(5)
    with qtbot.waitSignal(overview.jump_requested) as blocker:
        QTest.mouseClick(
            overview,
            Qt.MouseButton.LeftButton,
            pos=rect.center().toPoint(),
        )
    assert blocker.args == [5]

    with qtbot.waitSignal(overview.close_requested):
        overview.handle_key(Qt.Key.Key_Escape)


def test_thumbnails_are_made_once(tmp_path: Path, video_file: Path) -> None:
    clip = tmp_path / "files" / "Scene" / "clip.mp4"
    clip.parent.mkdir(parents=True)
    shutil.copy(video_file, clip)
    slide = SlideConfig(file=clip, rev_file=clip)

    thumb = thumbnail_path(slide)

    assert thumb == clip.parent / ".thumbs" / "clip.png"
    assert thumb.exists()
    mtime = thumb.stat().st_mtime_ns

    assert thumbnail_path(slide) == thumb
    assert thumb.stat().st_mtime_ns == mtime  # up to date, not made again


def test_thumbnail_of_a_broken_clip_is_none(tmp_path: Path) -> None:
    clip = tmp_path / "files" / "Scene" / "clip.mp4"
    clip.parent.mkdir(parents=True)
    clip.write_bytes(b"not a video")

    assert thumbnail_path(SlideConfig(file=clip, rev_file=clip)) is None


def test_present_notes_size_option() -> None:
    runner = CliRunner()

    out = runner.invoke(cli, ["-S", "present", "--help"])
    assert "--notes-size POINTS" in out.stdout
    assert "MANIM_NOTES_PT" in out.stdout

    out = runner.invoke(cli, ["-S", "present", "--notes-size", "5"])
    assert out.exit_code == 2
    assert "not in the range" in out.output


def make_player(
    presentation_config: PresentationConfig, qtbot: QtBot, **kwargs: object
) -> Player:
    player = Player(Config(), [presentation_config], start_paused=True, **kwargs)
    qtbot.addWidget(player)
    qtbot.addWidget(player.info)
    player.info.timer.stop()
    return player


def test_no_numbers_keeps_the_plain_video_widget(
    presentation_config: PresentationConfig, qtbot: QtBot
) -> None:
    player = make_player(presentation_config, qtbot)

    assert isinstance(player.video_widget, QVideoWidget)
    assert player.number_mode is None


def test_numbers_off_overrides_the_scene(
    presentation_config: PresentationConfig, qtbot: QtBot
) -> None:
    config = presentation_config.model_copy(update={"numbers": "slide"})

    player = make_player(config, qtbot, numbers="off")

    assert player.number_mode is None
    assert player.video_widget.number_text == ""  # type: ignore[union-attr]


def test_slide_numbers_follow_the_slides(
    presentation_config: PresentationConfig, qtbot: QtBot
) -> None:
    player = make_player(presentation_config, qtbot, numbers="slide")
    count = player.current_slides_count

    assert isinstance(player.video_widget, NumberedVideo)
    assert player.video_widget.number_text == f"1 / {count}"

    player.load_next_slide()
    assert player.video_widget.number_text == f"2 / {count}"

    player.load_previous_slide()
    assert player.video_widget.number_text == f"1 / {count}"


def test_the_scene_decides_without_the_option(
    presentation_config: PresentationConfig, qtbot: QtBot
) -> None:
    slides = [s.model_copy() for s in presentation_config.slides]
    for i, slide in enumerate(slides):
        slide.page_start = i in (1, 3)
        slide.chapter_start = i == 1
    config = presentation_config.model_copy(
        update={"slides": slides, "numbers": "page"}
    )

    player = make_player(config, qtbot)
    video = player.video_widget
    assert isinstance(video, NumberedVideo)
    assert video.number_text == ""  # before the first chapter / page

    player.load_next_slide()
    assert video.number_text == "1 / 2"
    player.load_next_slide()
    assert video.number_text == "1 / 2"
    player.load_next_slide()
    assert video.number_text == "2 / 2"

    player.numbers = "chapter"
    player.update_number()
    assert video.number_text == "1 / 1"


def test_number_is_drawn_in_the_corner_with_the_scenes_style(qtbot: QtBot) -> None:
    style = NumberStyle(right=0.1, bottom=0.2)
    video = NumberedVideo(
        (1000, 500), QColor("black"), Qt.AspectRatioMode.KeepAspectRatio, style
    )
    qtbot.addWidget(video)
    video.set_number((7, 33))

    number, total = video._number, video._total
    right_edge = total.pos().x() + total.boundingRect().width()
    middle = total.pos().y() + total.boundingRect().height() / 2

    assert right_edge == pytest.approx(900)  # 10 % in from the right
    assert middle == pytest.approx(400)  # 20 % up from the bottom
    assert number.pos().x() + number.boundingRect().width() < total.pos().x()
    assert number.zValue() > video.video_item.zValue()

    video.set_number(None)
    assert video.number_text == ""


def test_number_font_scales_with_the_slide_height(qtbot: QtBot) -> None:
    small = NumberedVideo(
        (1000, 500), QColor("black"), Qt.AspectRatioMode.KeepAspectRatio, NumberStyle()
    )
    large = NumberedVideo(
        (2000, 1000), QColor("black"), Qt.AspectRatioMode.KeepAspectRatio, NumberStyle()
    )
    qtbot.addWidget(small)
    qtbot.addWidget(large)

    assert large._number.font().pixelSize() == 2 * small._number.font().pixelSize()


def test_clicking_the_numbered_video_keeps_the_keys_working(
    presentation_config: PresentationConfig, qtbot: QtBot
) -> None:
    player = make_player(presentation_config, qtbot, numbers="slide")

    assert player.video_widget.focusPolicy() == Qt.FocusPolicy.NoFocus
