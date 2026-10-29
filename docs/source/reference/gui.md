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
