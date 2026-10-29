import json
from pathlib import Path

import pytest
from click.testing import CliRunner
from manim import Circle, FadeIn, Rotate

from manim_slides.config import PresentationConfig
from manim_slides.render import render
from manim_slides.slide.manim import Slide
from manim_slides.slide.progress import (
    env_enabled,
    partial_render,
    read_render_seconds,
)


class ThreeSeconds(Slide):
    def construct(self) -> None:
        circle = Circle()
        self.play(FadeIn(circle, run_time=1))
        self.next_slide()
        self.play(Rotate(circle, 1.0, run_time=2))


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in ("MANIM_PROGRESS", "MANIM_PROGRESS_PRECOUNT", "MANIM_PROGRESS_CACHE"):
        monkeypatch.delenv(var, raising=False)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, True),
        ("1", True),
        ("yes", True),
        ("0", False),
        ("False", False),
        ("", False),
    ],
)
def test_env_enabled(
    monkeypatch: pytest.MonkeyPatch, value: str | None, expected: bool
) -> None:
    if value is not None:
        monkeypatch.setenv("MANIM_X", value)

    assert env_enabled("MANIM_X") is expected


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        ('{"render_seconds": 12.5}', 12.5),
        ('{"render_seconds": 7}', 7.0),
        ('{"render_seconds": 0}', None),
        ('{"render_seconds": -1}', None),
        ('{"render_seconds": "12"}', None),
        ('{"render_seconds": null}', None),
        ('{"slides": []}', None),
        ("[1, 2]", None),
        ("not json", None),
    ],
)
def test_read_render_seconds(
    tmp_path: Path, content: str, expected: float | None
) -> None:
    path = tmp_path / "Scene.json"
    path.write_text(content)

    assert read_render_seconds(path) == expected


def test_read_render_seconds_of_a_missing_file(tmp_path: Path) -> None:
    assert read_render_seconds(tmp_path / "missing.json") is None


def test_partial_render_follows_the_manim_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from manim import config

    assert not partial_render()

    monkeypatch.setitem(config, "from_animation_number", 2)
    assert partial_render()

    monkeypatch.setitem(config, "from_animation_number", 0)
    monkeypatch.setitem(config, "upto_animation_number", 3)
    assert partial_render()


def test_bar_uses_the_stored_length(tmp_path: Path) -> None:
    scene = ThreeSeconds(output_folder=tmp_path)

    scene._progress_start(42.0)
    try:
        assert scene._bar is not None
        assert scene._bar.total == 42.0
        assert scene._bar.unit == "vs"
    finally:
        scene._progress_stop()

    assert scene._bar is None


def test_pre_count_matches_the_scene(tmp_path: Path) -> None:
    scene = ThreeSeconds(output_folder=tmp_path)

    scene._progress_start(None)
    try:
        assert scene._bar is not None
        assert scene._bar.total == pytest.approx(3.0)
    finally:
        scene._progress_stop()

    assert not scene.is_precount


def test_pre_count_can_be_turned_off(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MANIM_PROGRESS_PRECOUNT", "0")
    scene = ThreeSeconds(output_folder=tmp_path)

    scene._progress_start(None)
    try:
        assert scene._bar is not None
        assert scene._bar.total is None
    finally:
        scene._progress_stop()


def test_no_bar_when_turned_off(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MANIM_PROGRESS", "0")
    scene = ThreeSeconds(output_folder=tmp_path)

    scene._progress_start(10.0)

    assert scene._bar is None


def test_a_dry_run_does_not_open_a_bar(tmp_path: Path) -> None:
    scene = ThreeSeconds(output_folder=tmp_path)
    scene._precounting = True

    scene._progress_start(10.0)

    assert scene._bar is None


class BrokenPreCount(ThreeSeconds):
    def construct(self) -> None:
        if self.is_precount:
            raise RuntimeError("only fails in the dry run")
        super().construct()


def test_a_broken_pre_count_does_not_stop_the_render(tmp_path: Path) -> None:
    scene = BrokenPreCount(output_folder=tmp_path)

    scene._progress_start(None)
    try:
        assert scene._bar is not None
        assert scene._bar.total is None  # no total, but a bar and no error
    finally:
        scene._progress_stop()


@pytest.fixture
def tiny_file(tmp_path_factory: pytest.TempPathFactory) -> Path:
    path = tmp_path_factory.mktemp("scenes") / "tiny.py"
    path.write_text(
        "from manim import *\n"
        "from manim_slides import Slide\n\n\n"
        "class Tiny(Slide):\n"
        "    def construct(self):\n"
        "        circle = Circle()\n"
        "        self.play(FadeIn(circle, run_time=1))\n"
        "        self.next_slide()\n"
        "        self.play(Rotate(circle, 1.0, run_time=2))\n"
        "        self.next_slide()\n"
        "        self.play(FadeOut(circle, run_time=1))\n"
    )
    return path


def render_tiny(
    tiny_file: Path, *extra: str, env: dict[str, str] | None = None
) -> None:
    results = CliRunner().invoke(
        render, ["--CE", *extra, str(tiny_file), "Tiny", "-ql"], env=env
    )

    assert results.exit_code == 0, results


def stored(tmp_dir: str) -> float | None:
    return json.loads((Path(tmp_dir) / "slides" / "Tiny.json").read_text())[
        "render_seconds"
    ]


def test_render_stores_the_video_length(tiny_file: Path) -> None:
    runner = CliRunner()

    with runner.isolated_filesystem() as tmp_dir:
        render_tiny(tiny_file)

        assert stored(tmp_dir) == pytest.approx(4.0)
        config = PresentationConfig.from_file(Path(tmp_dir) / "slides" / "Tiny.json")
        assert config.render_seconds == pytest.approx(4.0)


def test_render_stores_the_length_without_the_bar(tiny_file: Path) -> None:
    runner = CliRunner()

    with runner.isolated_filesystem() as tmp_dir:
        render_tiny(tiny_file, env={"MANIM_PROGRESS": "0"})

        assert stored(tmp_dir) == pytest.approx(4.0)


def test_a_partial_render_keeps_the_stored_length(tiny_file: Path) -> None:
    runner = CliRunner()

    with runner.isolated_filesystem() as tmp_dir:
        render_tiny(tiny_file)
        render_tiny(tiny_file)  # cached, the same length again
        assert stored(tmp_dir) == pytest.approx(4.0)

        results = runner.invoke(
            render, ["--CE", str(tiny_file), "Tiny", "-ql", "-n", "0,1"]
        )
        assert results.exit_code == 0, results

        assert stored(tmp_dir) == pytest.approx(4.0)  # not the 2 s of the subset


def test_progress_cache_off_keeps_the_stored_length(tiny_file: Path) -> None:
    runner = CliRunner()

    with runner.isolated_filesystem() as tmp_dir:
        render_tiny(tiny_file)
        path = Path(tmp_dir) / "slides" / "Tiny.json"
        data = json.loads(path.read_text())
        data["render_seconds"] = 123.0
        path.write_text(json.dumps(data))

        render_tiny(tiny_file, env={"MANIM_PROGRESS_CACHE": "0"})
        assert stored(tmp_dir) == 123.0

        render_tiny(tiny_file)  # a complete render corrects it
        assert stored(tmp_dir) == pytest.approx(4.0)


def test_old_json_without_the_length_still_loads(slides_folder: Path) -> None:
    config = PresentationConfig.from_file(slides_folder / "BasicSlide.json")

    assert config.render_seconds is None
