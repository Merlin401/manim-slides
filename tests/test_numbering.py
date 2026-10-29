import shutil
from pathlib import Path

import pytest
from click.testing import CliRunner
from pydantic import ValidationError

from manim_slides.__main__ import cli
from manim_slides.config import BaseSlideConfig, NumberStyle, PresentationConfig
from manim_slides.numbering import parse_number_mode, slide_number
from manim_slides.slide.base import BaseSlide
from manim_slides.slide.manim import Slide as CESlide
from manim_slides.slide.manimlib import Slide as GLSlide


def slides(*marks: str) -> list[BaseSlideConfig]:
    """One slide per mark: any of ``p`` (starts a page) and ``c`` (starts a chapter)."""
    return [
        BaseSlideConfig(page_start="p" in mark, chapter_start="c" in mark)
        for mark in marks
    ]


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, None),
        ("", None),
        ("0", None),
        ("off", None),
        ("None", None),
        (False, None),
        ("1", "slide"),
        ("true", "slide"),
        (True, "slide"),
        ("total", "slide"),
        ("slide", "slide"),
        (" Page ", "page"),
        ("chapter", "chapter"),
    ],
)
def test_parse_number_mode(value: str | bool | None, expected: str | None) -> None:
    assert parse_number_mode(value) == expected


def test_parse_number_mode_rejects_unknown() -> None:
    with pytest.raises(ValueError, match="Unknown slide number mode"):
        parse_number_mode("sections")


def test_slide_mode_without_markers_counts_every_slide() -> None:
    deck = slides("", "", "")

    assert [slide_number(deck, i, "slide") for i in range(3)] == [
        (1, 3),
        (2, 3),
        (3, 3),
    ]


def test_slide_mode_hides_the_number_before_the_first_chapter() -> None:
    deck = slides("", "cp", "", "p")

    assert [slide_number(deck, i, "slide") for i in range(4)] == [
        None,
        (2, 4),
        (3, 4),
        (4, 4),
    ]


def test_page_mode_counts_pages_not_steps() -> None:
    deck = slides("", "cp", "", "", "p", "", "p")

    assert [slide_number(deck, i, "page") for i in range(7)] == [
        None,
        (1, 3),
        (1, 3),
        (1, 3),
        (2, 3),
        (2, 3),
        (3, 3),
    ]


def test_chapter_mode_counts_chapters() -> None:
    deck = slides("", "cp", "p", "cp", "", "cp")

    assert [slide_number(deck, i, "chapter") for i in range(6)] == [
        None,
        (1, 3),
        (1, 3),
        (2, 3),
        (2, 3),
        (3, 3),
    ]


def test_page_mode_without_any_page_has_no_number() -> None:
    assert slide_number(slides("", ""), 1, "page") is None


def test_markers_default_to_off_and_round_trip(tmp_path: Path) -> None:
    config = BaseSlideConfig()
    assert not config.page_start and not config.chapter_start

    assert BaseSlideConfig(page_start=True).model_dump()["page_start"] is True


def test_old_presentation_configs_still_load(slides_folder: Path) -> None:
    config = PresentationConfig.from_file(slides_folder / "BasicSlide.json")

    assert config.numbers is None
    assert config.number_style == NumberStyle()
    assert not any(s.page_start or s.chapter_start for s in config.slides)


def test_number_style_is_validated() -> None:
    assert NumberStyle(size=0.05).size == 0.05

    for bad in ({"size": 0}, {"size": 2}, {"right": 1.0}, {"bottom": -0.1}):
        with pytest.raises(ValidationError):
            NumberStyle(**bad)


@pytest.mark.parametrize("klass", [CESlide, GLSlide])
def test_start_page_and_chapter_mark_the_open_slide(
    klass: type[BaseSlide],
) -> None:
    slide = klass.__new__(klass)
    slide._base_slide_config = BaseSlideConfig()

    slide.start_page()
    slide.start_chapter()

    assert slide._base_slide_config.page_start
    assert slide._base_slide_config.chapter_start


@pytest.mark.parametrize("renderer", ["--CE", "--GL"])
def test_render_writes_markers_and_style(
    renderer: str, slides_file: Path, manimgl_config: Path
) -> None:
    from manim_slides.render import render

    runner = CliRunner()

    with runner.isolated_filesystem() as tmp_dir:
        shutil.copy(manimgl_config, tmp_dir)
        results = runner.invoke(
            render, [renderer, str(slides_file), "NumberedSlide", "-ql"]
        )

        assert results.exit_code == 0, results

        config = PresentationConfig.from_file(
            (Path(tmp_dir) / "slides" / "NumberedSlide.json").resolve(strict=True)
        )

    assert config.numbers == "page"
    assert config.number_style.size == 0.05
    assert config.number_style.right == 0.1
    assert [(s.page_start, s.chapter_start) for s in config.slides] == [
        (True, True),
        (False, False),
        (True, False),
        (True, True),
    ]
    assert slide_number(config.slides, 2, "page") == (2, 3)
    assert slide_number(config.slides, 3, "chapter") == (2, 2)


def test_present_numbers_option() -> None:
    runner = CliRunner()

    out = runner.invoke(cli, ["-S", "present", "--help"])
    assert "--numbers MODE" in out.stdout
    assert "MANIM_SLIDE_NUMBERS" in out.stdout

    out = runner.invoke(cli, ["-S", "present", "--numbers", "sections"])
    assert out.exit_code == 2
    assert "Unknown slide number mode" in out.output
