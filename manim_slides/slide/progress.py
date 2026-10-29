"""
Overall render progress bar for Manim scenes (Manim only, not ManimGL).

Manim only shows a short-lived bar per ``play()`` / ``wait()``.
:class:`RenderProgressMixin` adds one bar over the whole scene (video seconds done /
total, rate, ETA) and hides the per-animation ones.

The seconds are those of the animations Manim steps through. A ``wait()`` on a still
frame costs nothing to render, so it is not counted.

The total is found in one of two ways:

1. From the last complete render: the video length is stored as ``render_seconds`` in
   ``slides/<Scene>.json``. It is in seconds of video, so it serves every quality and
   frame rate. A partial render keeps the stored value.
2. By a pre-count, only when there is no stored value yet: ``construct()`` is run
   once with rendering skipped and the run times are summed. This is exact but builds
   the slides an extra time. A scene with side effects in ``construct()`` can check
   :attr:`~RenderProgressMixin.is_precount` (stdout is muted during the pre-count).

Environment variables:

``MANIM_PROGRESS=0``
    No overall bar, Manim's own bars stay.
``MANIM_PROGRESS_PRECOUNT=0``
    Never pre-count (no percentage until a complete render stored the length).
``MANIM_PROGRESS_CACHE=0``
    Keep the stored length as it is. Set it when rendering a subset of a scene.
"""

import contextlib
import json
import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import click
from manim import Scene, config
from tqdm import tqdm

from ..logger import logger

PROGRESS_ENVVAR = "MANIM_PROGRESS"
PRECOUNT_ENVVAR = "MANIM_PROGRESS_PRECOUNT"
CACHE_ENVVAR = "MANIM_PROGRESS_CACHE"


def env_enabled(var: str) -> bool:
    """Whether an environment variable is not ``0`` / ``false`` / ``no`` / empty (default on)."""
    return os.environ.get(var, "1").strip().lower() not in ("0", "false", "no", "")


def read_render_seconds(json_path: Path) -> float | None:
    """
    Read the stored video length of the last complete render of a scene.

    The file is read as plain JSON: it may point to clips that are gone, which
    :class:`~manim_slides.config.PresentationConfig` would reject.

    :return: The length in seconds, or :data:`None` if there is none.
    """
    try:
        seconds = json.loads(json_path.read_text()).get("render_seconds")
    except (OSError, ValueError, AttributeError):
        return None
    if isinstance(seconds, int | float) and seconds > 0:
        return float(seconds)
    return None


def partial_render() -> bool:
    """Whether Manim renders only some animations (``-n``), so not the whole scene."""
    upto = config["upto_animation_number"]  # -1 or inf when unset
    return bool(config["from_animation_number"] > 0 or 0 <= upto < float("inf"))


def _seconds(run_time: float, n_iterations: int | None) -> float:
    return (
        0.0 if n_iterations is not None else float(run_time)
    )  # wait_until() is open-ended


class _Tracked:
    """Wrap Manim's per-animation iterator and feed the overall bar (in seconds)."""

    def __init__(self, inner: Any, bar: tqdm, start: float, end: float) -> None:
        self._inner, self._bar, self._start, self._end = inner, bar, start, end
        self._done, self._closed = 0.0, False

    def __iter__(self) -> Iterator[Any]:
        step = 1 / config["frame_rate"]
        for t in self._inner:
            yield t
            # never overshoot the run time
            self._done = min(self._done + step, self._end - self._start)
            self._bar.update(self._start + self._done - self._bar.n)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._inner.close()
        # skipped / cached animations yield a single step; count the rest here
        self._bar.n = (
            self._end
        )  # same float sum as the total, so it ends at exactly 100%
        self._bar.update(0)


class RenderProgressMixin:
    """Mixin for a Manim scene that counts the video seconds it plays and can show them."""

    _precounting = False
    _bar: tqdm | None = None
    _seconds_total = 0.0
    _precounted: float | None = None
    _old_bar_mode: str = "display"

    @property
    def is_precount(self) -> bool:
        """Whether ``construct()`` runs for the length only (nothing is rendered)."""
        return self._precounting

    # --- Manim hooks ---------------------------------------------------------

    def setup(self) -> None:
        super().setup()  # ty: ignore[unresolved-attribute]
        if self._precounting:
            renderer: Any = self.renderer  # ty: ignore[unresolved-attribute]
            renderer._original_skipping_status = True
            renderer.skip_animations = True
            renderer.scene_finished = lambda scene: None  # write no movie file

    def get_time_progression(
        self,
        run_time: float,
        description: str,
        n_iterations: int | None = None,
        **kwargs: Any,
    ) -> Any:
        inner = super().get_time_progression(  # ty: ignore[unresolved-attribute]
            run_time, description, n_iterations, **kwargs
        )
        start = self._seconds_total
        self._seconds_total += _seconds(run_time, n_iterations)
        if self._bar is None:
            return inner
        self._bar.set_postfix_str(description[:45], refresh=False)
        return _Tracked(inner, self._bar, start, self._seconds_total)

    # --- the bar -------------------------------------------------------------

    def _progress_start(self, stored_seconds: float | None) -> None:
        """Open the overall bar, if enabled. ``stored_seconds`` is the last known length."""
        if self._precounting or not env_enabled(PROGRESS_ENVVAR):
            return
        total = stored_seconds or self._precount_total()
        self._old_bar_mode = config["progress_bar"]
        config["progress_bar"] = "none"
        # "vs" = video seconds, so the rate reads "17vs/s" (video seconds per real second)
        # or "0.5s/vs" (real seconds per video second) instead of an ambiguous "s/s".
        self._bar = tqdm(
            total=total,
            desc=type(self).__name__,
            unit="vs",
            unit_scale=True,
            dynamic_ncols=True,
        )

    def _progress_stop(self) -> None:
        """Close the overall bar, so manim-slides' own bars can show for what follows."""
        if self._bar is not None:
            self._bar.close()
            self._bar = None
            config["progress_bar"] = self._old_bar_mode

    def _precount_total(self) -> float | None:
        """Video seconds of the whole scene from a dry run, or :data:`None` if disabled or failed."""
        if not env_enabled(PRECOUNT_ENVVAR):
            return None
        try:
            return self._precount()
        except Exception as e:  # noqa: BLE001  # a broken pre-count must not stop the render
            logger.warning(f"Pre-count failed ({e!r}); no total for the progress bar")
            return None

    def _precount(self) -> float:
        """
        Run ``construct()`` once with rendering skipped and return the video seconds.

        The result is kept for the rest of this render.
        """
        if self._precounted is None:
            click.echo("Counting animations...", err=True)
            dry = type(self)()
            dry._precounting = True
            level = logger.level
            logger.setLevel("ERROR")  # silence "Played N animations"
            try:
                # e.g. per-click debug prints
                with contextlib.redirect_stdout(open(os.devnull, "w")):
                    Scene.render(dry)
            finally:
                logger.setLevel(level)
            self._precounted = dry._seconds_total
        return self._precounted
