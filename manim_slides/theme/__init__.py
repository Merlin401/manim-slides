"""
Themes and a deck template for Manim Slides (Manim only).

This package is opt-in: it is not imported by ``manim_slides`` itself. It gives a deck

- a :class:`Theme` (colors, font, sizes, logo, TeX preamble) and :func:`install`;
- :class:`TemplateSlide`, a scene with a persistent corner title, logo and chapter
  breadcrumb, that wipes between chapters;
- helpers to build slides and mobjects in the installed theme (:func:`set_heading`,
  :func:`bullet_list`, :func:`make_block`, ...);
- Manim's ``Text``, ``MathTex``, ``Arrow``, ... with the theme's defaults.

Typical use::

    from manim import *
    from manim_slides.theme import *


    class MyDeck(TemplateSlide):
        theme = Theme(accent="#C2410C", font="Lato")

        def construct(self):
            self.setup_progress_bar(["Intro", "Method"])
            self.play(FadeIn(title_slide("My talk", author="Me")))
            ...

See :class:`Theme` for what can be changed, and ``examples/theme_deck.py`` for a deck.
"""

from .core import DEFAULT_THEME, Theme, active, install
from .helpers import (
    annotation,
    bullet_item,
    bullet_list,
    figure,
    figure_slide,
    logo,
    loop_slide,
    make_block,
    paragraph,
    set_heading,
    takeaway_card,
    title_slide,
    wipe_keeping,
)
from .template import TemplateSlide
from .wrappers import (
    Angle,
    Arrow,
    Brace,
    Dot,
    FadeIn,
    Line,
    MarkupText,
    MathTex,
    Tex,
    Text,
)

__all__ = [
    "DEFAULT_THEME",
    "Angle",
    "Arrow",
    "Brace",
    "Dot",
    "FadeIn",
    "Line",
    "MarkupText",
    "MathTex",
    "TemplateSlide",
    "Tex",
    "Text",
    "Theme",
    "active",
    "annotation",
    "bullet_item",
    "bullet_list",
    "figure",
    "figure_slide",
    "install",
    "logo",
    "loop_slide",
    "make_block",
    "paragraph",
    "set_heading",
    "takeaway_card",
    "title_slide",
    "wipe_keeping",
]
