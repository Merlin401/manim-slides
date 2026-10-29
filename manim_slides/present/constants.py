"""Presenter settings that do not need Qt, so the CLI can use them without importing it."""

NOTES_PT = 18.0  # default size of the presenter notes, in points
NOTES_PT_RANGE = (10.0, 60.0)
NOTES_PT_STEP = 2.0
NOTES_PT_ENVVAR = "MANIM_NOTES_PT"
PREVIEW_WIDTH = 400  # px, the next-slide preview stays small so the notes get the room


def clamp_notes_pt(points: float) -> float:
    """Limit a notes size to :data:`NOTES_PT_RANGE`."""
    low, high = NOTES_PT_RANGE
    return min(max(points, low), high)
