"""
Building blocks for slides, drawn in the installed theme.

Helpers that take a ``scene`` build a whole slide (or part of one) and animate it;
the others return mobjects. All of them take their colors, font and sizes from the
installed theme, see :class:`~manim_slides.theme.Theme`.
"""

from typing import Any

from manim import (
    BOLD,
    DOWN,
    LEFT,
    NORMAL,
    ORIGIN,
    RIGHT,
    Group,
    ImageMobject,
    RoundedRectangle,
    SVGMobject,
    VGroup,
)

from .core import active
from .wrappers import Dot, Text

__all__ = [
    "annotation",
    "bullet_item",
    "bullet_list",
    "figure",
    "figure_slide",
    "logo",
    "loop_slide",
    "make_block",
    "paragraph",
    "set_heading",
    "takeaway_card",
    "title_slide",
    "wipe_keeping",
]


def title_slide(
    title: str, subtitle: str = "", author: str = "", date: str = ""
) -> VGroup:
    """Return a title slide: the title in the accent color, subtitle, author and date."""
    theme = active()
    group = VGroup()
    title_mob = Text(
        title,
        color=theme.accent,
        font=theme.font,
        weight=BOLD,
        font_size=theme.title_font_size,
    )
    group.add(title_mob)
    if subtitle:
        subtitle_mob = Text(subtitle, font=theme.font, font_size=theme.body_font_size)
        subtitle_mob.next_to(title_mob, DOWN, buff=0.4)
        group.add(subtitle_mob)
    if author:
        author_mob = Text(author, font=theme.font, weight=BOLD, font_size=24)
        author_mob.next_to(group, DOWN, buff=1.0)
        group.add(author_mob)
    if date:
        date_mob = Text(date, font=theme.font, font_size=18)
        date_mob.next_to(group, DOWN, buff=0.2)
        group.add(date_mob)
    group.move_to(ORIGIN)
    return group


def bullet_item(text: str, level: int = 0) -> VGroup:
    """Return a bulleted text item: accent bullet, indented by ``level``."""
    theme = active()
    dot = Dot(color=theme.accent, radius=0.06)
    label = Text(text, font=theme.font, font_size=theme.body_font_size)
    label.next_to(dot, RIGHT, buff=0.25)
    group = VGroup(dot, label)
    group.shift(RIGHT * level * 0.6)
    return group


def paragraph(
    *strings: str, alignment: Any = LEFT, direction: Any = DOWN, **kwargs: Any
) -> VGroup:
    """Return a stack of aligned ``Text`` lines (no bullets), for prose, captions and the like."""
    theme = active()
    kwargs.setdefault("font", theme.font)
    kwargs.setdefault("font_size", theme.body_font_size)
    texts = VGroup(*[Text(s, **kwargs) for s in strings]).arrange(direction)
    if len(strings) > 1:
        for text in texts[1:]:
            text.align_to(texts[0], direction=alignment)
    return texts


def make_block(
    label: str,
    width: float = 3,
    height: float = 1,
    color: Any = None,
    font_size: float = 24,
) -> VGroup:
    """Return a rounded box with a centered label, for architecture and pipeline diagrams."""
    theme = active()
    color = color or theme.dark
    box = RoundedRectangle(
        width=width,
        height=height,
        corner_radius=0.15,
        stroke_color=color,
        fill_color=color,
        fill_opacity=0.12,
    )
    # A single Text with an embedded "\n" left-justifies its lines against each
    # other; building one line per Text and arranging them centers each line's
    # width against the others instead.
    label_mob = (
        VGroup(
            *[
                Text(line, font=theme.font, font_size=font_size)
                for line in label.split("\n")
            ]
        )
        .arrange(DOWN, buff=0.05)
        .move_to(box)
    )
    return VGroup(box, label_mob)


def logo(height: float = 1) -> SVGMobject:
    """Return the logo of the installed theme, scaled to ``height``. The caller positions it."""
    theme = active()
    if theme.logo is None:
        raise ValueError(f"The theme {theme.name!r} has no logo")
    return SVGMobject(str(theme.logo)).scale_to_fit_height(height)


def set_heading(scene: Any, text: str) -> Text:
    """
    Build and position the sub-heading of a slide, just below the corner title.

    The heading distinguishes sub-topics within one chapter. Every content helper
    (:func:`bullet_list`, :func:`figure_slide`) takes an already built heading rather
    than a string: build it here first, then hand it to whichever content helper shows
    next (or wipe it in yourself for a custom slide). That keeps the heading decoupled
    from the content.

    Each call also starts a new page for ``--numbers page``, so call it once per page.
    """
    theme = active()
    blank = not text.strip()  # Text(" ") has no points and breaks next_to()
    heading = Text(
        "I" if blank else text,
        font=theme.font,
        weight=BOLD,
        font_size=32,
        color=theme.dark,
        fill_opacity=0 if blank else 1,
    )
    heading.next_to(scene.slide_title, DOWN, buff=0.3).align_to(scene.slide_title, LEFT)
    if hasattr(scene, "start_page"):
        scene.start_page()
    return heading


def annotation(
    text: str,
    ref: Any,
    direction: Any = DOWN,
    buff: float = 0.15,
    font_size: float = 16,
    color: Any = None,
    weight: Any = NORMAL,
    align: Any = LEFT,
    **kwargs: Any,
) -> Text:
    """
    Return a small caption or label placed next to ``ref`` and aligned to one of its edges.

    It is the pattern for figure captions, diagram callouts and bold labels (pass
    ``weight=BOLD`` and a color for those). ``align=None`` leaves the label centered on
    ``ref`` instead of aligned to an edge.
    """
    theme = active()
    label = Text(
        text,
        font=theme.font,
        font_size=font_size,
        color=color or theme.dark,
        weight=weight,
        **kwargs,
    )
    label.next_to(ref, direction, buff=buff)
    if align is not None:
        label.align_to(ref, align)
    return label


def figure(
    path: Any,
    caption: str = "",
    width: float | None = None,
    height: float | None = None,
    font_size: float = 20,
) -> Group:
    """
    Return a PNG figure with an optional caption below it.

    Manim cannot load PDFs, so convert those to PNG first. The result is a ``Group``,
    not a ``VGroup``, because ``ImageMobject`` is not a ``VMobject``.
    """
    theme = active()
    img = ImageMobject(str(path))
    if width is not None:
        img.scale_to_fit_width(width)
    elif height is not None:
        img.scale_to_fit_height(height)
    if not caption.strip():
        return Group(img)
    cap = Text(caption, font=theme.font, font_size=font_size, color=theme.dark)
    cap.next_to(img, DOWN, buff=0.15)
    return Group(img, cap)


def figure_slide(
    scene: Any,
    heading: Any,
    path: Any,
    caption: str = "",
    width: float | None = None,
    height: float | None = None,
    align: str = "left",
    auto_next: bool = False,
) -> Group:
    """
    Wipe in ``heading`` (see :func:`set_heading`) with a figure below it, and end the slide.

    ``align`` is ``"left"`` (under the heading) or ``"center"`` (for figures too wide to sit
    flush left). ``auto_next`` is for when a following slide needs to flow into this one
    without a click, see :func:`loop_slide`. Returns the figure, so a caller can add more
    content to it afterwards.
    """
    fig = figure(path, caption=caption, width=width, height=height)
    fig.next_to(heading, DOWN, buff=0.4)
    if align == "left":
        fig.align_to(heading, LEFT)
    elif align == "center":
        fig.set_x(0)
    else:
        raise ValueError(f"align must be 'left' or 'center', got {align!r}")

    scene.wipe(scene.mobjects_without_canvas, [heading, fig])
    scene.next_slide(auto_next=auto_next)
    return fig


def takeaway_card(
    big: str, lines: str, width: float = 3.9, height: float = 2.6, color: Any = None
) -> VGroup:
    """Return a card with one large figure or word on top and a short caption (one line per row)."""
    theme = active()
    color = color or theme.accent
    box = RoundedRectangle(
        width=width,
        height=height,
        corner_radius=0.2,
        stroke_color=color,
        stroke_width=2.5,
        fill_color=color,
        fill_opacity=0.08,
    )
    big_mob = Text(big, font=theme.font, font_size=44, weight=BOLD, color=color)
    # A long headline shrinks to fit inside the card instead of running over its edge.
    if big_mob.width > width - 0.7:
        big_mob.scale_to_fit_width(width - 0.7)
    caption = VGroup(
        *[
            Text(line, font=theme.font, font_size=20, color=theme.dark)
            for line in lines.split("\n")
        ]
    ).arrange(DOWN, buff=0.08)
    content = VGroup(big_mob, caption).arrange(DOWN, buff=0.35).move_to(box)
    return VGroup(box, content)


def bullet_list(scene: Any, heading: Any, items_text: list[str]) -> VGroup:
    """
    Wipe in ``heading`` with a bulleted list below it, and end the slide.

    It is the common case of a slide with no custom animation, whether that is the first
    slide of a chapter or a bullet-only beat within one. For the first slide of a chapter,
    call ``scene.new_clean_slide(TITLE, [])`` first to move the corner title and the
    breadcrumb, then :func:`set_heading` and this. Returns the bullet items.
    """
    items = VGroup(*[bullet_item(text) for text in items_text])
    items.arrange(DOWN, aligned_edge=LEFT, buff=0.35)
    items.next_to(heading, DOWN, buff=0.8).align_to(heading, LEFT)

    scene.wipe(scene.mobjects_without_canvas, [heading, items])
    scene.next_slide()
    return items


def wipe_keeping(scene: Any, keep: Any, future: Any) -> None:
    """
    Wipe new content in while ``keep`` (one mobject, or a list) stays on screen untouched.

    A mobject on both the outgoing and the incoming side of one wipe would fade out and back
    in, corrupting its position, so it is left out of the outgoing side.
    """
    keep_set = keep if isinstance(keep, list | tuple | VGroup | Group) else [keep]
    current = [m for m in scene.mobjects_without_canvas if m not in keep_set]
    scene.wipe(current, future)


def loop_slide(scene: Any, **kwargs: Any) -> None:
    """
    Start a slide that repeats until the presenter advances: ``next_slide(loop=True, ...)``.

    It guards against the one easy mistake: ``auto_next`` does not combine with ``loop``.
    A looping slide never reaches the end of its media, so there is nothing for
    ``auto_next`` to trigger from. To make *entering* the loop automatic instead, put
    ``auto_next=True`` on the ``next_slide()`` call that starts the slide right before it:
    a slide's forward auto-advance is controlled by the call that started it, not the one
    that ends it.
    """
    assert "auto_next" not in kwargs, (
        "auto_next doesn't combine with loop=True, put it on the next_slide() that "
        "starts the slide before this one, see loop_slide()'s docstring"
    )
    scene.next_slide(loop=True, **kwargs)
