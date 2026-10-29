import shutil
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import manim
import pytest
from click.testing import CliRunner
from manim import VGroup, config
from pydantic import ValidationError

from manim_slides.config import NumberStyle, PresentationConfig
from manim_slides.render import render
from manim_slides.theme import (
    DEFAULT_THEME,
    Angle,
    Arrow,
    Brace,
    Dot,
    FadeIn,
    Line,
    MarkupText,
    TemplateSlide,
    Text,
    Theme,
    active,
    annotation,
    bullet_item,
    bullet_list,
    figure,
    figure_slide,
    install,
    logo,
    loop_slide,
    make_block,
    paragraph,
    set_heading,
    takeaway_card,
    title_slide,
    wipe_keeping,
)

RED = Theme(
    name="orange", accent="#C2410C", text="#000000", dark="#404040", font="DejaVu Sans"
)


@pytest.fixture(autouse=True)
def default_theme() -> Iterator[None]:
    """Every test starts from, and leaves, the default theme."""
    install(DEFAULT_THEME)
    yield
    install(DEFAULT_THEME)


def hex_of(mobject: Any) -> str:
    """Return the color of a mobject, read from its first glyph or stroke (a ``Text`` keeps it there)."""
    leaf = mobject.family_members_with_points()[0]
    return leaf.color.to_hex().upper()


# ----------------------------------------------------------------------------- the theme


def test_default_theme_is_neutral() -> None:
    assert DEFAULT_THEME.name == "clean"
    assert DEFAULT_THEME.logo is None
    assert DEFAULT_THEME.font == "Inter"
    assert DEFAULT_THEME.background == "#FFFFFF"


def test_theme_is_validated_and_frozen() -> None:
    with pytest.raises(ValidationError):
        Theme(accent="red")
    with pytest.raises(ValidationError):
        Theme(accent="#12345")
    with pytest.raises(ValidationError):
        DEFAULT_THEME.accent = "#000000"  # type: ignore[misc]


def test_numbers_come_from_the_colors_and_font() -> None:
    style = RED.numbers()

    assert style.color.as_hex() == "#404040"
    assert style.total_color.as_hex() == RED.muted.lower()
    assert style.font == "DejaVu Sans"
    assert style.delay == 0.5


def test_numbers_can_be_set_by_the_theme() -> None:
    own = NumberStyle(size=0.05)

    assert Theme(number_style=own).numbers() is own


def test_install_sets_the_active_theme_and_the_background() -> None:
    assert active() is DEFAULT_THEME

    install(RED)

    assert active() is RED
    assert config.background_color.to_hex().upper() == DEFAULT_THEME.background.upper()
    install(Theme(background="#101010"))
    assert config.background_color.to_hex().upper() == "#101010"


def test_ligatures_follow_the_installed_theme() -> None:
    install(DEFAULT_THEME)
    assert manim.Text("ft").disable_ligatures is True
    assert manim.MarkupText("ft").disable_ligatures is True

    install(Theme(disable_ligatures=False))
    assert manim.Text("ft").disable_ligatures is False

    install(DEFAULT_THEME)
    assert manim.Text("ft", disable_ligatures=False).disable_ligatures is False

    patched = manim.Text.__init__
    install(DEFAULT_THEME)
    assert manim.Text.__init__ is patched  # patched once, not once per install


# ----------------------------------------------------------------------------- manim defaults


def test_wrappers_default_to_the_text_color_of_the_theme() -> None:
    install(RED)

    for make in (
        lambda **k: Text("a", **k),
        lambda **k: MarkupText("a", **k),
        lambda **k: Line(**k),
        lambda **k: Dot(**k),
        lambda **k: Arrow(**k),
        lambda **k: Brace(manim.Square(), **k),
        lambda **k: Angle(Line(), Line(manim.UP, manim.UP * 2), **k),
    ):
        assert hex_of(make()) == "#000000"
        assert hex_of(make(color="#00FF00")) == "#00FF00"

    install(Theme(text="#222222"))
    assert hex_of(Text("a")) == "#222222"


@pytest.mark.skipif(shutil.which("latex") is None, reason="needs LaTeX")
def test_tex_wrappers_use_the_preamble_of_the_theme() -> None:
    from manim_slides.theme import MathTex, Tex

    install(Theme(tex_preamble="\\usepackage{amsmath}\n\\newcommand{\\foo}{FOO}\n"))

    assert "\\newcommand{\\foo}" in MathTex("x").tex_template.preamble
    assert hex_of(MathTex("x")) == active().text.upper()
    assert "\\newcommand{\\foo}" in Tex("x").tex_template.preamble

    other = manim.TexTemplate()
    assert MathTex("x", tex_template=other).tex_template is other


def test_fade_in_run_time_follows_the_theme() -> None:
    mob = manim.Square()

    assert FadeIn(mob).run_time == pytest.approx(0.67)
    assert FadeIn(mob, run_time=2).run_time == 2

    install(Theme(fade_in_run_time=0.2))
    assert FadeIn(mob).run_time == pytest.approx(0.2)


# ----------------------------------------------------------------------------- helpers


class FakeScene:
    """The little a helper needs from a scene, recording what it is asked to do."""

    def __init__(self) -> None:
        self.slide_title = manim.Square().to_corner(manim.UL)
        self.mobjects_without_canvas: list[Any] = []
        self.calls: list[tuple[str, Any]] = []
        self.pages = 0

    def start_page(self) -> None:
        self.pages += 1

    def wipe(self, current: Any, future: Any) -> None:
        self.calls.append(("wipe", (current, future)))

    def next_slide(self, **kwargs: Any) -> None:
        self.calls.append(("next_slide", kwargs))


def test_title_slide_uses_the_accent_color_and_font() -> None:
    install(RED)

    group = title_slide("Title", "Sub", "Me", "Today")

    assert len(group) == 4
    assert hex_of(group[0]) == "#C2410C"
    assert all(hex_of(text) == "#000000" for text in group[1:])
    assert len(title_slide("Only a title")) == 1


def test_bullet_item_and_paragraph() -> None:
    install(RED)

    dot, label = bullet_item("point", level=1)
    assert hex_of(dot) == "#C2410C"
    assert label.get_left()[0] > dot.get_right()[0]
    assert bullet_item("p", level=2).get_center()[0] > bullet_item("p").get_center()[0]

    lines = paragraph("one", "two long line")
    assert len(lines) == 2
    assert lines[0].get_left()[0] == pytest.approx(lines[1].get_left()[0])
    assert lines[1].get_center()[1] < lines[0].get_center()[1]


def test_make_block_centers_one_text_per_line() -> None:
    install(RED)

    box, label = make_block("first\nsecond", width=4, height=2)

    assert len(label) == 2
    assert hex_of(box) == "#404040"
    assert box.width == pytest.approx(4)
    assert label.get_center() == pytest.approx(box.get_center())
    assert hex_of(make_block("a", color="#00FF00")[0]) == "#00FF00"


def test_annotation_is_placed_next_to_its_reference() -> None:
    ref = manim.Square()

    below = annotation("caption", ref)
    assert below.get_top()[1] < ref.get_bottom()[1]
    assert below.get_left()[0] == pytest.approx(ref.get_left()[0])
    assert hex_of(below) == active().dark.upper()

    centered = annotation("caption", ref, align=None)
    assert centered.get_center()[0] == pytest.approx(ref.get_center()[0])

    assert hex_of(annotation("c", ref, color="#00FF00")) == "#00FF00"


def test_set_heading_sits_under_the_title_and_starts_a_page() -> None:
    scene = FakeScene()

    heading = set_heading(scene, "Topic")

    assert heading.get_top()[1] < scene.slide_title.get_bottom()[1]
    assert heading.get_left()[0] == pytest.approx(scene.slide_title.get_left()[0])
    assert scene.pages == 1

    blank = set_heading(scene, "  ")
    assert (
        blank.family_members_with_points()
    )  # invisible, but has points to position by
    assert scene.pages == 2


def png(path: Path) -> Path:
    from PIL import Image

    Image.new("RGB", (40, 20), "white").save(path)
    return path


def test_figure_with_and_without_a_caption(tmp_path: Path) -> None:
    path = png(tmp_path / "f.png")

    assert len(figure(path)) == 1
    assert len(figure(path, caption="  ")) == 1

    fig = figure(path, caption="Caption", width=4)
    assert len(fig) == 2
    assert fig[0].width == pytest.approx(4)
    assert fig[1].get_top()[1] < fig[0].get_bottom()[1]
    assert figure(path, height=2)[0].height == pytest.approx(2)


def test_figure_slide_wipes_in_and_ends_the_slide(tmp_path: Path) -> None:
    scene, path = FakeScene(), png(tmp_path / "f.png")
    heading = set_heading(scene, "T")

    fig = figure_slide(scene, heading, path, caption="c", auto_next=True)

    assert scene.calls[0][0] == "wipe" and scene.calls[0][1][1] == [heading, fig]
    assert scene.calls[1] == ("next_slide", {"auto_next": True})
    assert fig.get_left()[0] == pytest.approx(heading.get_left()[0])

    centered = figure_slide(scene, heading, path, align="center")
    assert centered.get_center()[0] == pytest.approx(0)

    with pytest.raises(ValueError, match="align must be"):
        figure_slide(scene, heading, path, align="right")


def test_bullet_list_wipes_in_the_items() -> None:
    scene = FakeScene()
    heading = set_heading(scene, "T")

    items = bullet_list(scene, heading, ["a", "b", "c"])

    assert len(items) == 3
    assert items[1].get_center()[1] < items[0].get_center()[1]
    assert items.get_left()[0] == pytest.approx(heading.get_left()[0])
    assert scene.calls[0][1][1] == [heading, items]
    assert scene.calls[1] == ("next_slide", {})


def test_takeaway_card_shrinks_a_long_headline() -> None:
    install(RED)

    short = takeaway_card("3x", "line one\nline two")
    long = takeaway_card("A very long headline indeed", "caption")

    assert hex_of(short[0]) == "#C2410C"
    assert short[1][0].width <= short[0].width
    assert long[1][0].width <= long[0].width - 0.7 + 1e-6
    assert hex_of(takeaway_card("x", "y", color="#00FF00")[0]) == "#00FF00"


def test_wipe_keeping_leaves_the_kept_mobjects_out() -> None:
    scene = FakeScene()
    a, b, c = manim.Dot(), manim.Dot(), manim.Dot()
    scene.mobjects_without_canvas = [a, b, c]

    wipe_keeping(scene, b, ["new"])
    wipe_keeping(scene, [a, c], ["new"])
    wipe_keeping(scene, VGroup(a), ["new"])

    assert [call[1][0] for call in scene.calls] == [[a, c], [b], [b, c]]


def test_loop_slide_refuses_auto_next() -> None:
    scene = FakeScene()

    loop_slide(scene, notes="n")
    assert scene.calls == [("next_slide", {"loop": True, "notes": "n"})]

    with pytest.raises(AssertionError, match="auto_next"):
        loop_slide(scene, auto_next=True)


def test_logo_needs_one_in_the_theme(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="no logo"):
        logo()

    svg = tmp_path / "logo.svg"
    svg.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="40" height="20">'
        '<rect width="40" height="20"/></svg>'
    )
    install(Theme(logo=svg))

    assert logo(2).height == pytest.approx(2)


# ----------------------------------------------------------------------------- the template


class Plain(TemplateSlide):
    pass


def test_template_without_a_logo(tmp_path: Path) -> None:
    scene = Plain(output_folder=tmp_path)

    assert scene.logo is None
    assert scene.slide_title.text == "Contents"
    assert scene.number_style == DEFAULT_THEME.numbers()
    assert scene._progress_items is None


def test_template_installs_its_theme_and_shows_the_logo(tmp_path: Path) -> None:
    svg = tmp_path / "logo.svg"
    svg.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="40" height="20">'
        '<rect width="40" height="20"/></svg>'
    )

    class Branded(TemplateSlide):
        theme = Theme(name="branded", logo=svg, logo_height=0.5, accent="#C2410C")

    scene = Branded(output_folder=tmp_path)

    assert active() is Branded.theme
    assert scene.logo is not None
    assert scene.logo.height == pytest.approx(0.5)
    assert scene.logo.get_corner(manim.UR)[0] < config.frame_x_radius
    assert hex_of(scene.slide_title) == "#C2410C"
    assert scene.logo in scene.mobjects


def test_template_number_style_can_be_overridden_by_a_subclass(tmp_path: Path) -> None:
    own = NumberStyle(size=0.05)

    class Own(TemplateSlide):
        number_style = own  # type: ignore[assignment]

    assert Own(output_folder=tmp_path).number_style is own


def test_breadcrumb_colors_follow_the_theme(tmp_path: Path) -> None:
    class Crumbs(TemplateSlide):
        theme = RED

    scene = Crumbs(output_folder=tmp_path)
    scene.setup_progress_bar(["a", "b", "c"])
    scene._progress_bar_initial_colors()

    assert [hex_of(label) for label in scene._progress_items] == [
        "#C2410C",
        RED.light.upper(),
        RED.light.upper(),
    ]
    scene._progress_bar_advance_animation()
    scene._progress_bar_advance_animation()
    assert scene._progress_index == 2


def test_notes_are_set_on_the_open_slide(tmp_path: Path) -> None:
    scene = Plain(output_folder=tmp_path)

    scene.notes("- a point")

    assert scene._base_slide_config.notes == "- a point"


@pytest.mark.parametrize("renderer", ["--CE"])
def test_example_deck_renders(renderer: str, project_folder: Path) -> None:
    deck = project_folder / "examples" / "theme_deck.py"
    runner = CliRunner()

    with runner.isolated_filesystem() as tmp_dir:
        results = runner.invoke(render, [renderer, str(deck), "ThemeDeck", "-ql"])
        assert results.exit_code == 0, results

        config_ = PresentationConfig.from_file(
            (Path(tmp_dir) / "slides" / "ThemeDeck.json").resolve(strict=True)
        )

    assert config_.number_style == DEFAULT_THEME.numbers()
    assert sum(s.chapter_start for s in config_.slides) == 2
    assert sum(s.page_start for s in config_.slides) == 3
    assert not config_.slides[0].chapter_start  # the title slide has no number
    assert config_.background_color.as_hex() == "#fff"
