import json
import os
import time
from pathlib import Path

import pytest
from click.testing import CliRunner

from manim_slides.__main__ import cli
from manim_slides.config import PresentationConfig
from manim_slides.prune import (
    prune_after_render,
    prune_config,
    prune_enabled,
    prune_folder,
    prune_media,
    prune_partials,
    prune_presented,
)

DAY = 86400


def age(path: Path, days: float) -> Path:
    """Pretend ``path`` was last used ``days`` ago."""
    then = time.time() - days * DAY
    os.utime(path, (then, then))
    return path


def make(path: Path, size: int = 10, days: float = 0) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x" * size)
    return age(path, days)


def make_scene(root: Path, name: str = "Scene", clips: int = 2) -> Path:
    """Write ``root/<name>.json`` with ``clips`` slides, whose files exist."""
    files = root / "files" / name
    slides = []
    for i in range(clips):
        file = make(files / f"c{i}.mp4")
        rev = make(files / f"c{i}_reversed.mp4")
        slides.append(
            {
                "file": str(file.relative_to(root.parent)),
                "rev_file": str(rev.relative_to(root.parent)),
            }
        )
    path = root / f"{name}.json"
    path.write_text(json.dumps({"slides": slides}))
    return path


@pytest.fixture
def slides(tmp_path: Path) -> Path:
    return tmp_path / "slides"


def test_prune_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MANIM_PRUNE", raising=False)
    assert prune_enabled()
    for value in ("0", "false", "No", ""):
        monkeypatch.setenv("MANIM_PRUNE", value)
        assert not prune_enabled()
    monkeypatch.setenv("MANIM_PRUNE", "1")
    assert prune_enabled()


def test_prune_folder_respects_grace(slides: Path) -> None:
    make_scene(slides)
    folder = slides / "files" / "Scene"
    old = make(folder / "old.mp4", days=30)
    recent = make(folder / "recent.mp4", days=2)

    keep = {
        "c0.mp4",
        "c0_reversed.mp4",
    }  # c1 is unreferenced too, but unused for 0 days

    assert prune_folder(folder, keep, grace_days=7, dry_run=True) == (1, 10)
    assert old.exists()

    assert prune_folder(folder, keep, grace_days=7) == (1, 10)
    assert not old.exists()
    assert recent.exists() and (folder / "c1.mp4").exists()

    assert prune_folder(folder, keep, grace_days=0)[0] == 3  # recent, c1, c1_reversed


def test_prune_folder_only_files_folders(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="slides/files"):
        prune_folder(tmp_path, set())


def test_prune_folder_touch_and_thumbs(slides: Path) -> None:
    folder = slides / "files" / "Scene"
    kept = make(folder / "kept.mp4", days=30)
    gone = make(folder / "gone.mp4", days=30)
    thumb_kept = make(folder / ".thumbs" / "kept.png")
    thumb_gone = make(folder / ".thumbs" / "gone.png")

    count, _ = prune_folder(folder, {"kept.mp4"}, grace_days=7, touch=True)

    assert count == 2  # gone.mp4 and its thumbnail
    assert not gone.exists() and not thumb_gone.exists()
    assert thumb_kept.exists()
    assert time.time() - kept.stat().st_mtime < DAY  # touched


def test_prune_config_keeps_referenced_files(slides: Path) -> None:
    json_path = make_scene(slides, clips=3)
    folder = slides / "files" / "Scene"
    stale = make(folder / "stale.mp4", days=30)
    config = PresentationConfig.from_file(json_path)

    count, _ = prune_config(config, grace_days=7)

    assert count == 1
    assert not stale.exists()
    assert len(list(folder.glob("c*.mp4"))) == 6  # file and rev_file of each slide


def test_prune_partials(tmp_path: Path) -> None:
    partial = tmp_path / "partial_movie_files" / "Scene"
    listed = make(partial / "a.mp4", days=30)
    unlisted_old = make(partial / "b.mp4", days=30)
    unlisted_new = make(partial / "c.mp4", days=1)
    (partial / "partial_movie_file_list.txt").write_text(f"file 'file:{listed}'\n")

    count, _ = prune_partials(partial, touch=True)

    assert count == 1
    assert listed.exists() and unlisted_new.exists()
    assert not unlisted_old.exists()
    assert time.time() - listed.stat().st_mtime < DAY


def test_prune_partials_empty_list_removes_nothing(tmp_path: Path) -> None:
    clip = make(tmp_path / "a.mp4", days=100)
    (tmp_path / "partial_movie_file_list.txt").write_text("")

    assert prune_partials(tmp_path) == (0, 0)
    assert clip.exists()


def build_media(media: Path) -> dict[str, Path]:
    video = media / "videos" / "mod"
    partial = video / "1080p60" / "partial_movie_files" / "Scene"
    listed = make(partial / "a.mp4", days=1)
    (partial / "partial_movie_file_list.txt").write_text(f"file '{listed}'\n")
    return {
        "listed": listed,
        "stale": make(partial / "z.mp4", days=30),
        "movie": make(video / "1080p60" / "Scene.mp4"),
        "old_quality": make(video / "480p15" / "Scene.mp4", days=90),
        "old_text": age(make(media / "texts" / "t.svg"), 90),
        "new_text": make(media / "texts" / "u.svg"),
    }


def test_prune_media_and_after_render(tmp_path: Path) -> None:
    media = tmp_path / "media"
    paths = build_media(media)

    preview = prune_media(media, dry_run=True)

    assert all(p.exists() for p in paths.values())
    assert preview["partial clips"][0] == 1

    prune_media(media)

    assert paths["listed"].exists() and paths["new_text"].exists()
    for name in ("stale", "movie", "old_text"):
        assert not paths[name].exists()
    assert not paths["old_quality"].parent.exists()  # the whole quality folder


def test_prune_after_render_touches_clips(tmp_path: Path) -> None:
    slides = tmp_path / "slides"
    json_path = make_scene(slides)
    for clip in (slides / "files" / "Scene").glob("*.mp4"):
        age(clip, 30)
    media = tmp_path / "media"
    paths = build_media(media)
    age(paths["listed"], 30)
    partial = paths["listed"].parent

    removed = prune_after_render(partial, media, json_path)

    assert removed["partial clips"][0] == 1
    assert time.time() - paths["listed"].stat().st_mtime < DAY
    assert all(
        time.time() - clip.stat().st_mtime < DAY
        for clip in (slides / "files" / "Scene").glob("*.mp4")
    )


def test_prune_presented_never_raises(slides: Path) -> None:
    json_path = make_scene(slides)
    stale = make(slides / "files" / "Scene" / "old.mp4", days=30)
    config = PresentationConfig.from_file(json_path)

    assert prune_presented([config]) == (1, 10)
    assert not stale.exists()

    other = PresentationConfig.from_file(make_scene(slides, "Other"))
    config.slides += other.slides  # clips in two folders: refused, but not raised
    assert prune_presented([config]) == (0, 0)


def test_cli_prune(slides: Path) -> None:
    make_scene(slides)
    make_scene(slides, "Other")
    stale = make(slides / "files" / "Scene" / "old.mp4", days=30)
    runner = CliRunner()

    out = runner.invoke(
        cli, ["-S", "prune", "--folder", str(slides), "--dry-run", "Scene"]
    )

    assert out.exit_code == 0
    assert "Scene: would remove 1 stale files" in out.stdout
    assert "Other" not in out.stdout
    assert stale.exists()

    out = runner.invoke(cli, ["-S", "prune", "--folder", str(slides)])

    assert out.exit_code == 0
    assert "Scene: removed 1 stale files" in out.stdout
    assert "Other: removed 0 stale files" in out.stdout
    assert not stale.exists()


def test_cli_prune_grace_days_and_missing_scene(slides: Path) -> None:
    make_scene(slides)
    recent = make(slides / "files" / "Scene" / "new.mp4", days=1)
    runner = CliRunner()

    runner.invoke(cli, ["-S", "prune", "--folder", str(slides)])
    assert recent.exists()

    runner.invoke(cli, ["-S", "prune", "--folder", str(slides), "--grace-days", "0"])
    assert not recent.exists()

    out = runner.invoke(cli, ["-S", "prune", "--folder", str(slides), "Missing"])
    assert out.exit_code == 1


def test_cli_prune_media(slides: Path, tmp_path: Path) -> None:
    make_scene(slides)
    media = tmp_path / "media"
    paths = build_media(media)

    out = CliRunner().invoke(
        cli,
        ["-S", "prune", "--folder", str(slides), "--media", "--media-dir", str(media)],
    )

    assert out.exit_code == 0, out.output
    assert "media/partial clips: removed 1 files" in out.stdout
    assert not paths["stale"].exists()


def test_cli_prune_empty_folder(tmp_path: Path) -> None:
    out = CliRunner().invoke(cli, ["-S", "prune", "--folder", str(tmp_path)])

    assert out.exit_code != 0
    assert "No slide configs" in out.output


def test_present_has_prune_option() -> None:
    out = CliRunner().invoke(cli, ["-S", "present", "--help"])

    assert "--prune / --no-prune" in out.stdout
    assert "MANIM_PRUNE" in out.stdout
