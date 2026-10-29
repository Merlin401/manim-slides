# Graphical User Interface

Manim Slides' graphical user interface (GUI) is the *de facto* way to present slides.

If you do not specify one of the commands listed in the
[CLI reference](/reference/cli),
Manim Slides will use **present** by default, which launches a GUI window,
playing your scene(s) like so:

```bash
manim-slides [present] [SCENES]...
```

Some optional parameters can be specified and can be listed with:

```bash
manim-slides present --help
```

:::{note}
All the `SCENES` must be in the same folder (`--folder DIRECTORY`), which
defaults to `./slides`. If you rendered your animations without changing
directory, you should not worry about that :-)
:::

## The Info Window

On a second screen (or with `--show-info-window`), an info window shows the current
slide, a small preview of the next one, the slide counter, the clock, an elapsed
timer and the presenter notes. Its layout stretches with the window, and the notes
take the whole right column.

The default keys, all of which can be changed (see below), are:

| Key | Action |
| --- | --- |
| `+` / `-` | Make the presenter notes bigger / smaller |
| `0` | Reset the size of the notes |
| `S` | Start the elapsed timer, or restart it from zero |
| `O` or `Esc` | Open the slide overview |

The notes start at `--notes-size` points (or the `MANIM_NOTES_PT` environment
variable), 18 by default.

The elapsed timer waits until you press `S`, or until the presentation first moves
off the first slide, so you can set up long before the talk.

The **overview** pauses the video and shows the last frame of every slide in a grid.
The arrow keys move the highlight, `Enter` jumps to the highlighted slide, digits
followed by `Enter` jump to a slide number, a click on a tile jumps too, and `O` or
`Esc` closes the grid and resumes. The thumbnails are cached in a `.thumbs` folder
next to the slide clips.

## Slide Numbers

The player can draw the slide number, as `k / N`, over the slides:

```bash
manim-slides present --numbers MODE MyScene
```

where `MODE` is one of:

- `slide`: every slide;
- `page`: slides that start a page, so the click steps within a page do not count;
- `chapter`: slides that start a chapter;
- `off`: no number.

The same can be set with the environment variable `MANIM_SLIDE_NUMBERS` (`1` means `slide`), and
a scene can pick a default with the class attribute `slide_numbers = "page"`. The option wins.

Pages and chapters are marked in the scene, on the slide being built, with
`self.start_page()` and `self.start_chapter()`, or on the slide that follows a
`next_slide()` with `next_slide(page_start=True)` and `next_slide(chapter_start=True)`.
A scene that marks chapters shows no number before its first chapter, e.g., on a title slide.

The class attribute `number_style` (a {class}`~manim_slides.config.NumberStyle`) sets
the colors, font, size and position, all relative to the slide:

```python
from manim_slides import Slide
from manim_slides.config import NumberStyle


class Presentation(Slide):
    slide_numbers = "page"
    number_style = NumberStyle(color="#404040", size=0.03, right=0.04, bottom=0.04)
```

:::{note}
The number is not part of the rendered clips, so it can be switched on, off and changed
without rendering again. It needs a graphics view instead of the plain video widget, which
is only used when numbers are on. It is not drawn on image slides nor in exports.
:::

## Configuration File

It is possible to configure Manim Slides via a configuration file, even though
this feature is currently limited. You may initialize the default configuration
file with:

```bash
manim-slides init
```

:::{warning}
Note that, by default, Manim Slides will use default key bindings that are
platform-dependent. If you decide to overwrite those with a config file, you may
encounter some problems from platform to platform.
:::

## Configuring Key Bindings

If you wish to use other key bindings than the defaults, you can run the
configuration wizard with:

```bash
manim-slides wizard
```

A similar window to the image below will pop up and prompt to change keys.

```{eval-rst}
.. image:: ../_static/wizard_light.png
    :width: 300px
    :align: center
    :class: only-light
    :alt: Manim Slide Wizard
```

```{eval-rst}
.. image:: ../_static/wizard_dark.png
    :width: 300px
    :align: center
    :class: only-dark
    :alt: Manim Slide Wizard
```

:::{note}
Even though it is not currently supported through the GUI, you can select
multiple key binding for the same action by modifying the config file.
:::
