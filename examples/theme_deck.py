"""
A small deck with the theme package: a title slide and two chapters.

Render and present it with::

    manim-slides render examples/theme_deck.py ThemeDeck -ql
    manim-slides present ThemeDeck --numbers page

Change the look by editing the theme, e.g., ``Theme(accent="#C2410C", font="Lato")``.
"""

from itertools import pairwise

from manim import *

from manim_slides.theme import (
    Arrow,
    FadeIn,
    TemplateSlide,
    Text,
    Theme,
    annotation,
    bullet_list,
    make_block,
    set_heading,
    takeaway_card,
    title_slide,
)


class ThemeDeck(TemplateSlide):
    theme = Theme()  # the neutral default; see Theme for what can be changed

    def construct(self):
        self.setup_progress_bar(["Idea", "Result"])

        title = title_slide(
            "A small deck", "Made with manim_slides.theme", "Your name", "Today"
        )
        self.play(FadeIn(title))
        self.next_slide()

        # Chapter 1: bullets, then a hand-built slide
        self.new_clean_slide("1. Idea", [])
        bullet_list(
            self,
            set_heading(self, "What it is"),
            ["One theme sets colors, font and sizes", "Helpers build the slides"],
        )

        heading = set_heading(self, "How it fits together")
        blocks = VGroup(
            *[make_block(label, width=2.6) for label in ("Theme", "Helpers", "Deck")]
        )
        blocks.arrange(RIGHT, buff=0.9).next_to(heading, DOWN, buff=1.0)
        arrows = VGroup(
            *[Arrow(a.get_right(), b.get_left(), buff=0.1) for a, b in pairwise(blocks)]
        )
        note = annotation("every box is a make_block()", blocks, DOWN, buff=0.5)
        self.notes("- Explain the three boxes\n- The arrows are themed too")
        self.wipe(self.mobjects_without_canvas, [heading, blocks])
        self.play(
            LaggedStart(*[GrowArrow(a) for a in arrows], lag_ratio=0.5), FadeIn(note)
        )
        self.next_slide()

        # Chapter 2: a take-away card
        self.new_clean_slide("2. Result", [])
        heading = set_heading(self, "In one number")
        card = takeaway_card("3x", "less code in\nthe project").next_to(
            heading, DOWN, buff=0.8
        )
        card.align_to(heading, LEFT)
        self.wipe(self.mobjects_without_canvas, [heading, card])
        self.next_slide()

        self.play(FadeIn(Text("Thank you", font=self.theme.font, font_size=40)))
