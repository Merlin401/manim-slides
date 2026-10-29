# Themes and a Deck Template

:::{note}
This is only available with Manim (not ManimGL), and it is opt-in: nothing here is
imported by `manim_slides` itself.
:::

`manim_slides.theme` gives a deck its look and its scaffolding, so a presentation only
has to say what is on its slides:

- a {class}`~manim_slides.theme.Theme`: colors, font, sizes, an optional logo and the TeX preamble;
- {class}`~manim_slides.theme.TemplateSlide`: a `Slide` with a persistent corner title, logo and
  chapter breadcrumb, that wipes between chapters;
- helpers to build slides and mobjects in the theme, and Manim's `Text`, `MathTex`, `Arrow`, ...
  with the theme's defaults.

## A deck

```python
from manim import *

from manim_slides.theme import TemplateSlide, Theme, bullet_list, set_heading, title_slide


class MyDeck(TemplateSlide):
    theme = Theme(accent="#C2410C", font="Lato")

    def construct(self):
        self.setup_progress_bar(["Idea", "Result"])
        self.play(FadeIn(title_slide("My talk", "A subtitle", "Me", "Today")))
        self.next_slide()

        self.new_clean_slide("1. Idea", [])
        bullet_list(self, set_heading(self, "What it is"), ["First point", "Second point"])
```

Render and present it as any other deck. A complete one is in
[`examples/theme_deck.py`](https://github.com/Merlin401/manim-slides/blob/main/examples/theme_deck.py).

`new_clean_slide(title, contents)` starts a chapter: the corner title and the breadcrumb advance and
the previous chapter's content is wiped out. Build the body of a chapter's first slide right after it
with {func}`~manim_slides.theme.set_heading` and {func}`~manim_slides.theme.bullet_list`,
{func}`~manim_slides.theme.figure_slide` or an animation of your own. `self.notes("- ...")` sets the
presenter notes of the slide being built.

`set_heading` marks a page and `new_clean_slide` a chapter, which is what
`manim-slides present --numbers page` and `--numbers chapter` count, see the
[GUI reference](/reference/gui).

## Replacing the look

A theme names its colors by role, not by hue:

| Field | Used for |
| --- | --- |
| `background` | the slide background |
| `text` | normal text |
| `dark` | structure: headings, block titles and bodies |
| `muted`, `light` | what should not compete: finished chapters, the breadcrumb ahead |
| `accent` | titles, bullets, alerts |
| `success` | example blocks, "good" marks |

Besides the colors a theme sets `font`, the font sizes, `logo` (an SVG, shown in the top right corner,
with `logo_height`), `tex_preamble` (added to every `Tex` and `MathTex`), `fade_in_run_time`,
`disable_ligatures` and `number_style` (by default derived from the colors and the font).

The default theme, {data}`~manim_slides.theme.DEFAULT_THEME`, is neutral: white, slate and blue, set in
Inter, without a logo. To make a theme of your own, build a `Theme`, set it as the `theme` class
attribute of your deck, and put the shared parts in a base class:

```python
class Lab(TemplateSlide):
    theme = Theme(name="lab", accent="#0F766E", logo="lab-logo.svg")
```

Manim's own classes cannot be handed a theme, so the one that is installed decides their defaults.
A `TemplateSlide` installs its theme when it is created; code that builds mobjects before any scene
exists (module-level constants of a chapter, say) can call {func}`~manim_slides.theme.install` first.
`Text` and `MarkupText` also stop using ligatures by default, which many fonts render with uneven gaps.

:::{tip}
The font has to be installed on the machine that renders. The default `Inter` is free
(OFL) and available from [Google Fonts](https://fonts.google.com/specimen/Inter); with a missing
font Pango silently falls back to another one.
:::

## API

```{eval-rst}
.. autoclass:: manim_slides.theme.Theme
    :members: numbers

.. autodata:: manim_slides.theme.DEFAULT_THEME
    :no-value:

.. autofunction:: manim_slides.theme.install

.. autofunction:: manim_slides.theme.active

.. autoclass:: manim_slides.theme.TemplateSlide
    :members:
        new_clean_slide,
        notes,
        setup_progress_bar,

.. automodule:: manim_slides.theme.helpers
    :members:
        title_slide,
        set_heading,
        bullet_list,
        bullet_item,
        figure,
        figure_slide,
        make_block,
        annotation,
        paragraph,
        takeaway_card,
        wipe_keeping,
        loop_slide,
        logo,
```
