"""A base scene for a deck with persistent chrome: corner title, logo and chapter breadcrumb."""

from typing import Any, ClassVar

from manim import (
    BOLD,
    DOWN,
    LEFT,
    RIGHT,
    UL,
    UR,
    MovingCameraScene,
    Transform,
    VGroup,
)

from ..config import NumberStyle
from ..slide.manim import Slide
from .core import DEFAULT_THEME, Theme, install
from .helpers import logo
from .wrappers import FadeIn, Text

__all__ = ["TemplateSlide"]


class TemplateSlide(Slide, MovingCameraScene):
    """
    Base scene for a full deck: open with :func:`~manim_slides.theme.title_slide`, then run
    :meth:`new_clean_slide` per chapter to wipe between them while a persistent title, logo
    and chapter breadcrumb stay in the corners.

    It combines with ``MovingCameraScene``, so ``self.camera.frame`` zoom and pan work.
    The look comes from the class attribute :attr:`theme`, which is installed when the scene
    is created::

        class MyDeck(TemplateSlide):
            theme = Theme(accent="#C2410C")

    The slide number is not part of the frames: the presenter draws it
    (``manim-slides present --numbers slide|page|chapter``), styled by the theme.
    :func:`~manim_slides.theme.set_heading` marks a page and :meth:`new_clean_slide` a chapter.
    """

    theme: ClassVar[Theme] = DEFAULT_THEME

    @property
    def number_style(self) -> NumberStyle:  # ty: ignore[invalid-method-override]
        """The look of the slide number, from the theme unless a subclass sets its own."""
        return self.theme.numbers()

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        install(self.theme)
        super().__init__(*args, **kwargs)
        self.wait_time_between_slides = 0.10
        theme = self.theme

        # slide_title starts as real, non-empty text: Text("") has no points, which breaks
        # to_corner() and cascades into wrong positions for anything placed relative to it later.
        self.slide_title = Text(
            "Contents",
            font=theme.font,
            weight=BOLD,
            font_size=theme.frametitle_font_size,
            color=theme.accent,
        ).to_corner(UL, buff=0.6)
        self.logo = (
            logo(theme.logo_height).to_corner(UR, buff=0.4) if theme.logo else None
        )

        # The logo is visible immediately (including behind the title slide). The title
        # stays unadded until the first new_clean_slide() call puts it on screen, see
        # _chrome_shown below.
        canvas = {}
        if self.logo is not None:
            self.add(self.logo)
            canvas["logo"] = self.logo
        self.add_to_canvas(**canvas, slide_title=self.slide_title)
        self._chrome_shown = False

        # Chapter breadcrumb: opt-in via setup_progress_bar(); stays None (a no-op
        # everywhere it is checked) for any scene that never calls it.
        self._progress_items: VGroup | None = None
        self._progress_index = -1

    def setup_progress_bar(self, chapter_labels: list[str]) -> None:
        """
        Prepare the breadcrumb shown at the bottom of every slide once the deck gets going.

        There is one short label per chapter, in presentation order. Past chapters read
        muted (done), the current one in the accent color, upcoming ones light.
        :meth:`new_clean_slide` advances it every time a chapter's title goes up, on the
        assumption that it is called exactly once per chapter, in ``chapter_labels`` order.

        Call this once from ``construct()``, before the chapter-building loop. It only
        builds and registers the mobject (added to the canvas so ``wipe()`` never touches
        it); it fades in together with the title on the first :meth:`new_clean_slide` call,
        so it does not show up over the title slide.
        """
        theme = self.theme
        self._progress_items = VGroup(
            *[
                Text(label, font=theme.font, font_size=15, color=theme.light)
                for label in chapter_labels
            ]
        ).arrange(RIGHT, buff=0.45)
        self._progress_items.to_edge(DOWN, buff=0.15)
        self.add_to_canvas(progress_bar=self._progress_items)

    def _progress_bar_initial_colors(self) -> None:
        """
        Color the breadcrumb for chapter 0.

        This is a plain ``set_color()``, not ``.animate``, since the colors must already be
        right the moment the bar fades in on the first :meth:`new_clean_slide` call.
        """
        if self._progress_items is None:
            return
        self._progress_index = 0
        for i, label in enumerate(self._progress_items):
            label.set_color(self.theme.accent if i == 0 else self.theme.light)

    def _progress_bar_advance_animation(self) -> list[Any]:
        """Advance the breadcrumb to the next chapter, as animations for :meth:`new_clean_slide`."""
        if self._progress_items is None:
            return []
        theme = self.theme
        self._progress_index += 1
        anims = []
        for i, label in enumerate(self._progress_items):
            if i < self._progress_index:
                color = theme.muted
            elif i == self._progress_index:
                color = theme.accent
            else:
                color = theme.light
            anims.append(label.animate.set_color(color))
        return anims

    def notes(self, text: str) -> None:
        """
        Set the presenter notes (Markdown bullets) of the slide being built.

        Call it before building the slide's content, before a ``figure_slide()`` or
        ``bullet_list()`` call or the first ``play()`` of a hand-built slide.
        ``next_slide(notes=...)`` cannot do this: it attaches to the slide that *follows*
        the call, so with the "animate, then ``next_slide()``" pattern the notes would end
        up one slide late. This sets them on the open slide instead, leaving ``loop`` and
        ``auto_next`` untouched.
        """
        self._base_slide_config.notes = text

    def next_slide_title_animation(self, title: str) -> Transform:
        """Return the morph of the corner title into ``title``."""
        theme = self.theme
        return Transform(
            self.slide_title,
            Text(
                title,
                font=theme.font,
                weight=BOLD,
                font_size=theme.frametitle_font_size,
                color=theme.accent,
            )
            .move_to(self.slide_title)
            .align_to(self.slide_title, LEFT),
        )

    def new_clean_slide(self, title: str, contents: Any = None) -> None:
        """
        Wipe out the current chapter's mobjects and bring in the next one's, updating the title.

        This also marks a chapter start for the presenter's slide numbers. ``contents`` may be
        empty or omitted, e.g. for a chapter whose body is built afterwards with
        ``set_heading()`` and ``bullet_list()``, ``figure_slide()`` or a custom animation:
        this only moves the chrome (corner title, breadcrumb) and never builds a body itself.

        The very first call is special-cased: ``Transform()`` would need to start from the
        "Contents" placeholder, which was never shown, so ``play()`` would pop it onto the
        screen just to morph it, flashing "Contents" for a frame. So the first title appears
        directly (no morph) instead.
        """
        theme = self.theme
        self.start_chapter()
        current = self.mobjects_without_canvas
        future = contents if contents else []
        # Wipe() is an AnimationGroup and play()-ing one with zero sub-animations raises, which
        # is only true when both sides are empty, e.g. the very first chapter of the deck
        # calling this with no contents (nothing has been added to the scene yet besides the
        # chrome, so current is empty too).
        wipe = (
            self.wipe(current, future, return_animation=True)
            if (current or future)
            else None
        )

        if not self._chrome_shown:
            self._chrome_shown = True
            self.slide_title = (
                Text(
                    title,
                    font=theme.font,
                    weight=BOLD,
                    font_size=theme.frametitle_font_size,
                    color=theme.accent,
                )
                .move_to(self.slide_title)
                .align_to(self.slide_title, LEFT)
            )
            self.add_to_canvas(slide_title=self.slide_title)
            self._progress_bar_initial_colors()
            # FadeIn(a, b) wraps its arguments in an anonymous Group and adds that Group to the
            # scene, not the individual mobjects. Since the canvas tracks the individual
            # objects, mobjects_without_canvas would then wrongly treat that Group as
            # disposable content on the next wipe(), fading the title back out. Separate
            # FadeIn calls add each mobject to the scene directly instead.
            fade_ins = [FadeIn(self.slide_title)]
            if self._progress_items is not None:
                fade_ins.append(FadeIn(self._progress_items))
            self.play(*fade_ins, *([wipe] if wipe else []))
        else:
            self.play(
                self.next_slide_title_animation(title),
                *([wipe] if wipe else []),
                *self._progress_bar_advance_animation(),
            )
