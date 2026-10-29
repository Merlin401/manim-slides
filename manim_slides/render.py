"""
Alias command to either
``manim render [OPTIONS] [ARGS]...`` or
``manimgl -w [OPTIONS] [ARGS]...``.

This is especially useful for two reasons:

1. You can are sure to execute the rendering command with the same Python environment
   as for ``manim-slides``.
2. You can pass options to the config.
"""

import os
import subprocess
import sys

import click

from .defaults import REVERSE_ENVVAR


@click.command(
    context_settings={
        "ignore_unknown_options": True,
        "allow_extra_args": True,
        "help_option_names": ("-h",),
    },
    options_metavar="[-h] [--CE|--GL] [--reverse|--no-reverse]",
)
@click.option(
    "--CE",
    is_flag=True,
    envvar="MANIM_RENDERER",
    show_envvar=True,
    help="If set, use Manim Community Edition (CE) renderer. "
    "If this or ``--GL`` is not set, defaults to CE renderer.",
)
@click.option(
    "--GL",
    is_flag=True,
    envvar="MANIMGL_RENDERER",
    show_envvar=True,
    help="If set, use ManimGL renderer.",
)
@click.option(
    "--reverse/--no-reverse",
    default=None,
    help="Also generate the reversed animations, which only the presenter's "
    "REVERSE key plays (off by default, they cost render time and disk space). "
    f"Overrides {REVERSE_ENVVAR} and goes before the renderer arguments. "
    "A scene that sets ``skip_reversing`` itself ignores it.",
)
@click.argument("args", metavar="[RENDERER_ARGS]...", nargs=-1, type=click.UNPROCESSED)
def render(ce: bool, gl: bool, reverse: bool | None, args: tuple[str, ...]) -> None:
    """
    Render SCENE(s) from the input FILE, using the specified renderer.

    Use ``manim-slides render --help`` to see help information for
    a specific renderer.
    """
    if ce and gl:
        raise click.UsageError("You cannot specify both --CE and --GL renderers.")
    env = dict(os.environ)
    if reverse is not None:
        env[REVERSE_ENVVAR] = "1" if reverse else "0"
    if gl:
        completed = subprocess.run(
            [sys.executable, "-m", "manimlib", "-w", *args], check=False, env=env
        )
    else:
        completed = subprocess.run(
            [sys.executable, "-m", "manim", "render", *args], check=False, env=env
        )
    sys.exit(completed.returncode)
