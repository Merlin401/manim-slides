"""
Slide numbers, as ``k / N``, for the presenter.

Three things can be counted, picked with ``manim-slides present --numbers MODE``
(or the ``slide_numbers`` class attribute of a scene):

``slide``
    Every slide, as in the info window.
``page``
    Slides that start a page (:meth:`BaseSlide.start_page`), so the click steps
    within a page do not count.
``chapter``
    Slides that start a chapter (:meth:`BaseSlide.start_chapter`).

A deck that marks chapters has no number before its first chapter (a title slide,
say). In ``page`` and ``chapter`` mode there is none before the first marker either.
"""

from collections.abc import Sequence
from typing import Literal, TypeAlias

from .config import BaseSlideConfig

NumberMode: TypeAlias = Literal["slide", "page", "chapter"]

NUMBER_MODES: tuple[NumberMode, ...] = ("slide", "page", "chapter")
NUMBERS_ENVVAR = "MANIM_SLIDE_NUMBERS"

_ON = {"1", "true", "yes", "on"}
_OFF = {"", "0", "false", "no", "off", "none"}


def parse_number_mode(value: str | bool | None) -> NumberMode | None:
    """
    Turn a user-given value into a number mode, or :data:`None` for no numbers.

    ``1`` / ``true`` / ``yes`` / ``on`` mean ``slide``; ``0`` / ``false`` / ``no`` /
    ``off`` / ``none`` and the empty string mean no numbers.

    :raises ValueError: If the value is none of the above nor a mode.
    """
    if value is None:
        return None
    text = str(value).strip().lower()
    if text in _OFF:
        return None
    if text in _ON or text == "total":
        return "slide"
    if text in NUMBER_MODES:
        return text  # type: ignore[return-value]
    raise ValueError(
        f"Unknown slide number mode {value!r}: use one of {', '.join(NUMBER_MODES)}, or off"
    )


def number_flip_ms(duration_ms: int, delay_ms: int, reverse: bool) -> int:
    """
    Return the time in a clip, in ms, at which the slide number changes.

    A slide's clip starts with the animation that leads from the previous page to this
    one, so the number changes ``delay_ms`` into it, to match what is on screen.
    A reversed clip plays that animation last, so the number changes ``delay_ms`` before
    its end. A clip shorter than the delay changes it at its end (or start, reversed).
    """
    delay = min(max(delay_ms, 0), duration_ms)
    return max(duration_ms - delay, 0) if reverse else delay


def slide_number(
    slides: Sequence[BaseSlideConfig], index: int, mode: NumberMode
) -> tuple[int, int] | None:
    """
    Return ``(k, N)`` for the slide at ``index``, or :data:`None` if it has no number.

    :param slides: The slides of a presentation, in order.
    :param index: Zero-based index of the slide shown.
    :param mode: What to count.
    """
    if mode == "slide":
        chapters = [i for i, s in enumerate(slides) if s.chapter_start]
        if chapters and index < chapters[0]:
            return None
        return index + 1, len(slides)

    marker = "page_start" if mode == "page" else "chapter_start"
    marks = [getattr(s, marker) for s in slides]
    total = sum(marks)
    current = sum(marks[: index + 1])
    if current == 0:
        return None
    return current, total
