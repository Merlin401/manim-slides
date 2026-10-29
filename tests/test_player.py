import re
import shutil
from collections.abc import Iterator
from pathlib import Path

import pytest
from click.testing import CliRunner
from pytestqt.qtbot import QtBot
from qtpy.QtCore import QEvent, Qt, QUrl
from qtpy.QtGui import QColor
from qtpy.QtMultimedia import QMediaPlayer
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

PLAYERS: list[Player] = []


def new_player(
    qtbot: QtBot, presentations: list[PresentationConfig], **kwargs: object
) -> Player:
    """Build a paused player, which is shut down again after the test."""
    player = Player(Config(), presentations, start_paused=True, **kwargs)
    qtbot.addWidget(player)
    qtbot.addWidget(player.info)
    PLAYERS.append(player)
    return player


@pytest.fixture(autouse=True)
def shut_down_players() -> Iterator[None]:
    """
    Stop the media players before Qt deletes them.

    Deleting a media player that is still decoding can crash Qt later on, in a test
    that runs an event loop, so each test shuts its players down by itself and lets
    the widgets that pytest-qt closed be deleted now, not during a later loop.
    """
    yield
    while PLAYERS:
        player = PLAYERS.pop()
        player.info.timer.stop()
        for media_player in (player.media_player, player.info.next_media_player):
            media_player.stop()
            media_player.setSource(QUrl())
    QApplication.processEvents()
    QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    QApplication.processEvents()


@pytest.fixture
def player(presentation_config: PresentationConfig, qtbot: QtBot) -> Iterator[Player]:
    player = new_player(qtbot, [presentation_config])
    player.info.resize(1600, 900)
    player.show(QApplication.screens())
    yield player


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
    player = new_player(qtbot, [presentation_config], notes_size=30)

    assert player.info.notes_pt == 30
    player.info.resize_notes(+NOTES_PT_STEP)
    player.info.resize_notes(None)
    assert player.info.notes_pt == 30


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
    player = new_player(qtbot, [presentation_config], **kwargs)
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
    assert (
        player.video_widget.number_text == f"1 / {count}"
    )  # until the animation is half way
    player.flip_number()
    assert player.video_widget.number_text == f"2 / {count}"

    player.load_previous_slide()  # played forwards: the same, back to the first slide
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
    assert video.number_text == ""  # first chapter and page: it waits for the animation
    player.flip_number()
    assert video.number_text == "1 / 2"

    player.load_next_slide()  # same page: nothing to wait for
    assert video.number_text == "1 / 2"

    player.load_next_slide()
    assert video.number_text == "1 / 2"
    player.flip_number()
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


def without_reversed(config: PresentationConfig, *indices: int) -> PresentationConfig:
    """Copy of a config where the slides at ``indices`` (all if none) have no reversed clip."""
    slides = [
        s.model_copy(update={"rev_file": s.file}) if not indices or i in indices else s
        for i, s in enumerate(config.slides)
    ]
    return config.model_copy(update={"slides": slides})


def at_slide(player: Player, index: int) -> None:
    player.current_slide_index = index
    player.load_current_slide()


def test_previous_plays_the_reversed_clip_when_there_is_one(
    presentation_config: PresentationConfig, qtbot: QtBot
) -> None:
    slides = presentation_config.slides
    assert slides[1].rev_file != slides[1].file  # the test data has reversed clips
    player = make_player(presentation_config, qtbot)
    at_slide(player, 2)

    press(player, Qt.Key.Key_Left)

    assert player.current_slide_index == 1
    assert player.playing_reversed_slide
    assert player.current_file == slides[1].rev_file


def test_previous_plays_forwards_without_reversed_clips(
    presentation_config: PresentationConfig, qtbot: QtBot
) -> None:
    config = without_reversed(presentation_config)
    player = make_player(config, qtbot)
    at_slide(player, 2)

    press(player, Qt.Key.Key_Left)

    assert player.current_slide_index == 1
    assert not player.playing_reversed_slide
    assert player.current_file == config.slides[1].file


def test_previous_looks_at_the_slide_it_goes_back_to(
    presentation_config: PresentationConfig, qtbot: QtBot
) -> None:
    config = without_reversed(presentation_config, 1)  # only slide 1 has none
    player = make_player(config, qtbot)
    at_slide(player, 3)

    press(player, Qt.Key.Key_Left)  # back to slide 2, which has one
    assert player.current_slide_index == 2
    assert player.playing_reversed_slide
    assert player.current_file == config.slides[2].rev_file

    press(player, Qt.Key.Key_Left)  # back to slide 1, which has none
    assert player.current_slide_index == 1
    assert not player.playing_reversed_slide
    assert player.current_file == config.slides[1].file


def test_next_after_a_reversed_previous_replays_that_slide(
    presentation_config: PresentationConfig, qtbot: QtBot
) -> None:
    player = make_player(presentation_config, qtbot)
    at_slide(player, 2)
    press(player, Qt.Key.Key_Left)

    player.load_next_slide()

    assert player.current_slide_index == 1  # as with REVERSE: played again, forwards
    assert not player.playing_reversed_slide
    assert player.current_file == presentation_config.slides[1].file


def test_previous_on_the_first_slide_does_nothing(
    presentation_config: PresentationConfig, qtbot: QtBot
) -> None:
    player = make_player(presentation_config, qtbot)
    assert player.current_slide_index == 0

    press(player, Qt.Key.Key_Left)
    assert player.current_slide_index == 0
    assert not player.playing_reversed_slide

    press(player, Qt.Key.Key_V)  # REVERSE, too, must not leave a reversed state behind
    assert not player.playing_reversed_slide

    player.load_next_slide()
    assert player.current_slide_index == 1


def test_reverse_key_still_plays_the_reversed_clip(
    presentation_config: PresentationConfig, qtbot: QtBot
) -> None:
    player = make_player(presentation_config, qtbot)
    at_slide(player, 2)

    press(player, Qt.Key.Key_V)

    assert player.current_slide_index == 1
    assert player.playing_reversed_slide
    assert player.current_file == presentation_config.slides[1].rev_file


def test_previous_goes_back_across_presentations(
    presentation_config: PresentationConfig, qtbot: QtBot
) -> None:
    other = without_reversed(presentation_config)
    player = new_player(qtbot, [presentation_config, other], presentation_index=1)
    player.info.timer.stop()
    assert player.current_slide_index == 0

    assert player.previous_slide_config == presentation_config.slides[-1]

    press(player, Qt.Key.Key_Left)

    assert player.current_presentation_index == 0
    assert player.current_slide_index == player.current_slides_count - 1
    assert player.playing_reversed_slide  # the first presentation has reversed clips


def numbered_player(
    config: PresentationConfig,
    qtbot: QtBot,
    monkeypatch: pytest.MonkeyPatch,
    **kwargs: object,
) -> Player:
    player = make_player(config, qtbot, numbers="slide", **kwargs)
    monkeypatch.setattr(player, "_media_duration", lambda: 3000)
    return player


def test_number_changes_part_way_into_the_clip(
    presentation_config: PresentationConfig,
    qtbot: QtBot,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    player = numbered_player(presentation_config, qtbot, monkeypatch)
    count = player.current_slides_count
    player.load_next_slide()  # the default delay is 0.5 s

    player.number_position_changed(0)
    player.number_position_changed(499)
    assert player.video_widget.number_text == f"1 / {count}"

    player.number_position_changed(500)
    assert player.video_widget.number_text == f"2 / {count}"

    player.number_position_changed(900)  # changes once
    assert not player._number_flip_pending


def test_number_waits_for_the_clip_to_be_known(
    presentation_config: PresentationConfig,
    qtbot: QtBot,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    player = numbered_player(presentation_config, qtbot, monkeypatch)
    monkeypatch.setattr(player, "_media_duration", lambda: 0)
    count = player.current_slides_count
    player.load_next_slide()

    player.number_position_changed(5000)

    assert player.video_widget.number_text == f"1 / {count}"


def test_reversed_clip_changes_the_number_near_its_end(
    presentation_config: PresentationConfig,
    qtbot: QtBot,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    player = numbered_player(presentation_config, qtbot, monkeypatch)
    count = player.current_slides_count
    at_slide(player, 2)
    player.flip_number()
    assert player.video_widget.number_text == f"3 / {count}"

    press(player, Qt.Key.Key_Left)  # plays the reversed clip of slide 2 (index 1)
    assert player.playing_reversed_slide
    assert player.video_widget.number_text == f"2 / {count}"  # what is on screen

    player.number_position_changed(2499)
    assert player.video_widget.number_text == f"2 / {count}"

    player.number_position_changed(2500)  # 3000 ms clip, 500 ms before its end
    assert player.video_widget.number_text == f"1 / {count}"


def test_number_changes_at_the_end_of_the_clip_at_the_latest(
    presentation_config: PresentationConfig,
    qtbot: QtBot,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    player = numbered_player(presentation_config, qtbot, monkeypatch)
    count = player.current_slides_count
    player.load_next_slide()

    player.number_media_status_changed(QMediaPlayer.MediaStatus.LoadedMedia)
    assert player.video_widget.number_text == f"1 / {count}"

    player.number_media_status_changed(QMediaPlayer.MediaStatus.EndOfMedia)
    assert player.video_widget.number_text == f"2 / {count}"


def test_number_delay_zero_changes_at_once(
    presentation_config: PresentationConfig,
    qtbot: QtBot,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = presentation_config.model_copy(
        update={"number_style": NumberStyle(delay=0)}
    )
    player = numbered_player(config, qtbot, monkeypatch)
    count = player.current_slides_count

    player.load_next_slide()

    assert player.video_widget.number_text == f"2 / {count}"
    assert not player._number_flip_pending


def test_number_jumps_straight_to_the_first_slide(
    presentation_config: PresentationConfig,
    qtbot: QtBot,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    player = numbered_player(presentation_config, qtbot, monkeypatch)

    assert not player._number_flip_pending  # nothing leads to the first slide
    assert player.video_widget.number_text.startswith("1 / ")


# BasicSlide: slides 0, 2 and 3 are plain, slide 1 loops. (index 0 is the first slide)


def wait_until_finished(player: Player, qtbot: QtBot) -> None:
    """Wait for the player to be paused on the last frame of the clip it loaded."""
    media = player.media_player
    qtbot.waitUntil(
        lambda: (
            media.duration() > 0
            and media.position() >= media.duration() - 5
            and media.playbackState() == QMediaPlayer.PlaybackState.PausedState
        ),
        timeout=5000,
    )


def finished(player: Player) -> bool:
    return player._Player__termination_achieved  # ty: ignore[unresolved-attribute]


def test_previous_without_reversed_clips_shows_the_slide_finished(
    presentation_config: PresentationConfig, qtbot: QtBot
) -> None:
    player = make_player(without_reversed(presentation_config), qtbot)
    at_slide(player, 3)

    press(player, Qt.Key.Key_Left)

    assert player.current_slide_index == 2
    assert not player.playing_reversed_slide
    assert finished(player)
    wait_until_finished(player, qtbot)


def test_the_last_frame_is_what_is_shown(
    presentation_config: PresentationConfig, qtbot: QtBot
) -> None:
    import av
    import numpy as np
    from qtpy.QtGui import QImage

    config = without_reversed(presentation_config)
    player = make_player(config, qtbot)
    at_slide(player, 3)
    press(player, Qt.Key.Key_Left)
    wait_until_finished(player, qtbot)
    qtbot.waitUntil(lambda: player.frame.isValid(), timeout=5000)

    with av.open(str(config.slides[2].file)) as container:
        *_, last = container.decode(video=0)
    expected = last.to_ndarray(format="rgb24")
    image = player.frame.toImage().convertToFormat(QImage.Format.Format_RGB888)
    pixels = image.constBits()
    if hasattr(pixels, "setsize"):  # PyQt6 needs to be told how big the buffer is
        pixels.setsize(image.sizeInBytes())
    shown = np.frombuffer(pixels, np.uint8)
    shown = shown.reshape(image.height(), image.bytesPerLine())
    shown = shown[:, : image.width() * 3].reshape(image.height(), image.width(), 3)

    assert shown.shape == expected.shape
    assert np.abs(shown.astype(int) - expected.astype(int)).mean() < 1


def test_next_after_skipping_to_the_end_goes_on(
    presentation_config: PresentationConfig, qtbot: QtBot
) -> None:
    player = make_player(without_reversed(presentation_config), qtbot)
    at_slide(player, 3)
    press(player, Qt.Key.Key_Left)
    assert player.current_slide_index == 2

    press(player, Qt.Key.Key_Right)  # at once, even before the clip is loaded

    assert player.current_slide_index == 3
    assert not finished(player)  # slide 3 plays, as always


def test_pause_key_does_not_restart_a_finished_slide(
    presentation_config: PresentationConfig, qtbot: QtBot
) -> None:
    player = make_player(without_reversed(presentation_config), qtbot)
    at_slide(player, 3)
    press(player, Qt.Key.Key_Left)
    wait_until_finished(player, qtbot)

    press(player, Qt.Key.Key_Space)

    assert player.media_player.playbackState() == QMediaPlayer.PlaybackState.PausedState


def test_replay_plays_a_finished_slide_again(
    presentation_config: PresentationConfig, qtbot: QtBot
) -> None:
    player = make_player(without_reversed(presentation_config), qtbot)
    at_slide(player, 3)
    press(player, Qt.Key.Key_Left)
    wait_until_finished(player, qtbot)

    press(player, Qt.Key.Key_R)

    qtbot.waitUntil(
        lambda: (
            player.media_player.playbackState()
            == QMediaPlayer.PlaybackState.PlayingState
        ),
        timeout=5000,
    )


def test_previous_still_plays_a_looping_slide(
    presentation_config: PresentationConfig, qtbot: QtBot
) -> None:
    player = make_player(without_reversed(presentation_config), qtbot)
    at_slide(player, 2)
    assert player.current_presentation_config.slides[1].loop

    press(player, Qt.Key.Key_Left)

    assert player.current_slide_index == 1
    assert not finished(player)
    assert not player._end_seek_pending


def test_previous_with_a_reversed_clip_still_plays_it(
    presentation_config: PresentationConfig, qtbot: QtBot
) -> None:
    player = make_player(presentation_config, qtbot)
    at_slide(player, 3)

    press(player, Qt.Key.Key_Left)

    assert player.playing_reversed_slide
    assert not finished(player)
    assert not player._end_seek_pending


def test_reverse_key_plays_from_the_start_too(
    presentation_config: PresentationConfig, qtbot: QtBot
) -> None:
    player = make_player(without_reversed(presentation_config), qtbot)
    at_slide(player, 3)

    press(player, Qt.Key.Key_V)  # an explicit request to play it back

    assert player.current_slide_index == 2
    assert not finished(player)


def test_overview_jump_shows_the_slide_finished(
    presentation_config: PresentationConfig, qtbot: QtBot
) -> None:
    player = make_player(presentation_config, qtbot)

    press(player, Qt.Key.Key_O)
    press(player, Qt.Key.Key_4)
    press(player, Qt.Key.Key_Return)

    assert player.current_slide_index == 3
    assert finished(player)
    wait_until_finished(player, qtbot)


def test_overview_jump_to_a_looping_slide_plays_it(
    presentation_config: PresentationConfig, qtbot: QtBot
) -> None:
    player = make_player(presentation_config, qtbot)

    press(player, Qt.Key.Key_O)
    press(player, Qt.Key.Key_2)
    press(player, Qt.Key.Key_Return)

    assert player.current_slide_index == 1
    assert not finished(player)


def test_skipping_can_be_turned_off(
    presentation_config: PresentationConfig, qtbot: QtBot
) -> None:
    player = new_player(
        qtbot, [without_reversed(presentation_config)], skip_to_end=False
    )
    player.info.timer.stop()
    at_slide(player, 3)

    press(player, Qt.Key.Key_Left)
    assert not finished(player)

    press(player, Qt.Key.Key_O)
    press(player, Qt.Key.Key_4)
    press(player, Qt.Key.Key_Return)
    assert player.current_slide_index == 3
    assert not finished(player)


def test_going_back_from_the_first_slide_leaves_no_request_behind(
    presentation_config: PresentationConfig, qtbot: QtBot
) -> None:
    player = make_player(without_reversed(presentation_config), qtbot)
    assert player.current_slide_index == 0

    press(player, Qt.Key.Key_Left)  # nothing to go back to
    player.load_next_slide()  # so this must play, not show the slide finished

    assert player.current_slide_index == 1
    assert not finished(player)


def test_number_is_final_when_a_slide_is_shown_finished(
    presentation_config: PresentationConfig,
    qtbot: QtBot,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    player = numbered_player(without_reversed(presentation_config), qtbot, monkeypatch)
    count = player.current_slides_count
    at_slide(player, 3)
    player.flip_number()
    assert player.video_widget.number_text == f"4 / {count}"

    press(player, Qt.Key.Key_Left)

    assert player.video_widget.number_text == f"3 / {count}"  # no change to wait for
    assert not player._number_flip_pending


def test_present_skip_to_end_option() -> None:
    out = CliRunner().invoke(cli, ["-S", "present", "--help"])

    assert "--skip-to-end / --no-skip-to-end" in out.stdout
