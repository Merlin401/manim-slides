"""
Manim classes that default to the installed theme.

Manim's ``Text``, ``Line`` and the like are white by default, which is invisible on a white
background, and every equation would need the TeX preamble passed in. These wrappers fill
those defaults from the installed theme and can still be overridden in each call.

Import them after ``from manim import *`` so they replace Manim's own::

    from manim import *
    from manim_slides.theme import Arrow, FadeIn, MathTex, Text

They are functions, not classes: ``isinstance(x, Text)`` needs ``manim.Text``.
"""

from typing import Any

import manim

from .core import active
from .core import tex_template as _tex_template

__all__ = [
    "Angle",
    "Arrow",
    "Brace",
    "Dot",
    "FadeIn",
    "Line",
    "MarkupText",
    "MathTex",
    "Tex",
    "Text",
]


def _text_colored(cls: Any) -> Any:
    def wrapper(*args: Any, color: Any = None, **kwargs: Any) -> Any:
        return cls(*args, color=active().text if color is None else color, **kwargs)

    wrapper.__name__ = cls.__name__
    wrapper.__doc__ = f"{cls.__name__} in the text color of the installed theme."
    return wrapper


def _tex_defaults(cls: Any) -> Any:
    def wrapper(
        *args: Any, color: Any = None, tex_template: Any = None, **kwargs: Any
    ) -> Any:
        theme = active()
        return cls(
            *args,
            color=theme.text if color is None else color,
            tex_template=(
                _tex_template(theme.tex_preamble)
                if tex_template is None
                else tex_template
            ),
            **kwargs,
        )

    wrapper.__name__ = cls.__name__
    wrapper.__doc__ = f"{cls.__name__} in the text color and with the TeX preamble of the installed theme."
    return wrapper


Text = _text_colored(manim.Text)
MarkupText = _text_colored(manim.MarkupText)
Line = _text_colored(manim.Line)
Dot = _text_colored(manim.Dot)
Brace = _text_colored(manim.Brace)
Arrow = _text_colored(manim.Arrow)
Angle = _text_colored(manim.Angle)
Tex = _tex_defaults(manim.Tex)
MathTex = _tex_defaults(manim.MathTex)


def FadeIn(*args: Any, run_time: float | None = None, **kwargs: Any) -> Any:  # noqa: N802
    """FadeIn that runs as long as the installed theme says, a bit quicker than Manim's."""
    return manim.FadeIn(
        *args,
        run_time=active().fade_in_run_time if run_time is None else run_time,
        **kwargs,
    )
