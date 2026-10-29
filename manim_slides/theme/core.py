"""
The look of a deck: a :class:`Theme`, and the one that is installed.

A theme holds the colors, the font, the sizes, an optional logo and the TeX preamble
that :class:`~manim_slides.theme.TemplateSlide` and the helpers of this package use.
Replace the look of a deck by giving its scene another theme::

    class MyDeck(TemplateSlide):
        theme = Theme(accent="#C2410C", font="Lato")

Colors are named by their role, not by their hue: ``accent`` is what stands out
(titles, bullets, alerts), ``dark`` is for structure (headings, block titles),
``text`` for normal text, ``muted`` and ``light`` for what should not compete.

Manim's own classes cannot be handed a theme, so the one that is installed (by a
:class:`~manim_slides.theme.TemplateSlide` when it is created, or by :func:`install`)
sets their defaults, see :mod:`manim_slides.theme.wrappers`.
"""

from functools import cache
from pathlib import Path
from typing import Annotated

from manim import MarkupText, Text, TexTemplate, config
from pydantic import BaseModel, ConfigDict, StringConstraints

from ..config import NumberStyle

__all__ = ["DEFAULT_THEME", "Theme", "active", "install"]

HexColor = Annotated[str, StringConstraints(pattern=r"^#[0-9a-fA-F]{6}$")]


class Theme(BaseModel):
    """Colors, font, sizes, logo and TeX preamble of a deck."""

    model_config = ConfigDict(frozen=True)

    name: str = "clean"

    background: HexColor = "#FFFFFF"
    text: HexColor = "#111827"  # normal text
    dark: HexColor = "#374151"  # structure: headings, block titles and bodies
    muted: HexColor = "#6B7280"  # emphasis that should not be as heavy as dark
    light: HexColor = "#D1D5DB"  # what is not reached yet, dividers
    accent: HexColor = "#2563EB"  # titles, bullets, alerts
    success: HexColor = "#15803D"  # example blocks, "good" marks

    font: str = "Inter"
    title_font_size: float = 44
    frametitle_font_size: float = 40
    body_font_size: float = 28
    # Ligatures ("ft", "ti", ...) of many fonts come out with uneven gaps once Pango
    # outlines them, so Text and MarkupText default to no ligatures
    disable_ligatures: bool = True

    logo: Path | None = None  # an SVG, shown in the top right corner
    logo_height: float = 1.0
    tex_preamble: str = "\\usepackage{amsmath}\n\\usepackage{amssymb}\n"
    fade_in_run_time: float = 0.67  # about a third quicker than Manim's second

    number_style: NumberStyle | None = None  # None: derived from the colors and font

    def numbers(self) -> NumberStyle:
        """Return how the presenter draws the slide number: small, in the bottom right."""
        if self.number_style is not None:
            return self.number_style
        return NumberStyle(
            color=self.dark,
            total_color=self.muted,
            font=self.font,
            size=0.029,
            total_size=0.022,
            right=0.0316,
            bottom=0.034,
            delay=0.5,  # half of a wipe's second, so the number changes while it runs
        )


DEFAULT_THEME = Theme()

_active: Theme = DEFAULT_THEME


def active() -> Theme:
    """Return the installed theme."""
    return _active


@cache
def tex_template(preamble: str) -> TexTemplate:
    """Return the default TeX template with ``preamble`` added."""
    template = TexTemplate()
    template.add_to_preamble(preamble)
    return template


def _no_ligatures_by_default(text_cls: type) -> None:
    """Patch ``text_cls`` once, so the installed theme decides (also for raw Manim ``Text``)."""
    init = text_cls.__init__
    if getattr(init, "_manim_slides_theme", False):
        return

    def patched(self: object, *args: object, **kwargs: object) -> None:
        if active().disable_ligatures:
            kwargs.setdefault("disable_ligatures", True)
        init(self, *args, **kwargs)

    patched._manim_slides_theme = True  # type: ignore[attr-defined]
    text_cls.__init__ = patched  # type: ignore[method-assign]


def install(theme: Theme) -> Theme:
    """
    Install ``theme``: it becomes the one the helpers and defaults use.

    This sets the background color of the scene and, once, patches Manim's ``Text`` and
    ``MarkupText`` so the installed theme decides whether they use ligatures.
    """
    global _active
    _active = theme
    config.background_color = theme.background
    _no_ligatures_by_default(Text)
    _no_ligatures_by_default(MarkupText)
    return theme
