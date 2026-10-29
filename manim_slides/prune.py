"""
Delete stale files from the rendered slides and from Manim's media cache.

Clips in ``slides/files/<Scene>/`` are named by a hash of their content, so every
edit that changes a slide leaves the old clip behind. A clip is stale when the
scene's ``slides/<Scene>.json`` no longer references it (neither as ``file`` nor as
``rev_file``) and it has not been used for :data:`GRACE_DAYS`.
Stale thumbnails in ``.thumbs/`` go with their clips.

Manim's own cache in ``media/`` (partial clips per animation, text renders) is handled
by ``--media``. Its partial clips are what make re-renders fast, so they get a grace
period too: a clip is only deleted once the latest render of its scene no longer lists
it (``partial_movie_file_list.txt``) *and* it has not been used for
:data:`GRACE_DAYS`. Rendering touches the clips it uses, which resets their clock. The
grace period keeps a deck with chapters switched off for a while (or a subset render)
from losing the cached clips of the others.

``manim-slides present`` prunes the presented scenes on exit and ``manim-slides
render`` (Manim only) prunes ``media/`` after a complete render, unless
``MANIM_PRUNE`` is set to ``0`` (or ``--no-prune`` is given when presenting).
Presenting and rendering mark the clips they use as used.
"""

import os
import re
import shutil
import time
from collections.abc import Iterable
from pathlib import Path

import click

from .commons import folder_path_option, verbosity_option
from .config import PresentationConfig
from .logger import logger

GRACE_DAYS = 7.0
QUALITY_DAYS = 60.0
TEXT_DAYS = 60.0

PRUNE_ENVVAR = "MANIM_PRUNE"


def prune_enabled() -> bool:
    """Whether pruning is allowed, i.e., ``MANIM_PRUNE`` is not ``0`` / ``false``."""
    return os.environ.get(PRUNE_ENVVAR, "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "",
    )


def _days_since(timestamp: float) -> float:
    return (time.time() - timestamp) / 86400


def _size_mb(nbytes: int) -> str:
    return f"{nbytes / 1e6:.0f} MB"


def _remove(paths: Iterable[Path], dry_run: bool) -> tuple[int, int]:
    paths = list(paths)
    freed = sum(p.stat().st_size for p in paths)
    if not dry_run:
        for path in paths:
            path.unlink()
    return len(paths), freed


def prune_folder(
    folder: Path,
    keep: set[str],
    grace_days: float = GRACE_DAYS,
    touch: bool = False,
    dry_run: bool = False,
) -> tuple[int, int]:
    """
    Prune a ``slides/files/<Scene>/`` directory.

    Files that are not in ``keep`` and have gone unused for ``grace_days`` are removed,
    so clips of chapters switched off for a short while survive, and so are the
    ``.thumbs`` entries of clips that are gone.

    :param folder: The ``slides/files/<Scene>`` directory.
    :param keep: File names that are still referenced.
    :param grace_days: Days a file must have been unused before it can go.
    :param touch: Mark the kept clips as used now.
    :param dry_run: Only count, do not delete.
    :return: The number of files removed and the bytes freed.
    """
    if folder.parent.name != "files":
        raise ValueError(
            f"Refusing to prune {folder}: not a slides/files/<Scene> folder"
        )
    now = time.time()
    stale: list[Path] = []
    alive: set[str] = set()
    for path in folder.iterdir():
        if not path.is_file():
            continue
        if path.name in keep:
            alive.add(path.stem)
            if touch and not dry_run:
                os.utime(path, (now, now))
        elif _days_since(path.stat().st_mtime) > grace_days:
            stale.append(path)
        else:
            alive.add(path.stem)
    thumbs = folder / ".thumbs"
    if thumbs.is_dir():
        stale += [p for p in thumbs.iterdir() if p.is_file() and p.stem not in alive]
    return _remove(stale, dry_run)


def prune_config(
    config: PresentationConfig,
    grace_days: float = GRACE_DAYS,
    touch: bool = False,
    dry_run: bool = False,
) -> tuple[int, int]:
    """Prune the clip folder a loaded presentation config points at."""
    keep: set[str] = set()
    folders: set[Path] = set()
    for slide in config.slides:
        for path in (slide.file, slide.rev_file):
            if path:
                keep.add(Path(path).name)
                folders.add(Path(path).parent)
    if len(folders) != 1:
        raise ValueError(
            f"Expected the clips in one folder, found {sorted(map(str, folders))}"
        )
    folder = folders.pop()
    if not folder.is_dir():
        return 0, 0
    return prune_folder(folder, keep, grace_days, touch, dry_run)


def prune_json(
    json_path: Path,
    grace_days: float = GRACE_DAYS,
    touch: bool = False,
    dry_run: bool = False,
) -> tuple[int, int]:
    """Prune the clips of the scene described by a ``slides/<Scene>.json`` file."""
    return prune_config(
        PresentationConfig.from_file(json_path), grace_days, touch, dry_run
    )


def prune_partials(
    partial_dir: Path,
    grace_days: float = GRACE_DAYS,
    touch: bool = False,
    dry_run: bool = False,
) -> tuple[int, int]:
    """
    Prune one ``media/videos/<module>/<quality>/partial_movie_files/<Scene>/`` folder.

    Clips missing from its ``partial_movie_file_list.txt`` and unused for
    ``grace_days`` are removed. ``touch`` marks the listed clips as used now (done
    right after a full render). An empty or missing list never prunes anything.
    """
    list_file = partial_dir / "partial_movie_file_list.txt"
    if not list_file.is_file():
        return 0, 0
    listed = {
        Path(name).name
        for name in re.findall(r"file '(?:file:)?(.*?)'", list_file.read_text())
    }
    if not listed:
        return 0, 0
    now = time.time()
    stale = []
    for clip in partial_dir.iterdir():
        if not clip.is_file() or clip.suffix != ".mp4":
            continue
        if clip.name in listed:
            if touch and not dry_run:
                os.utime(clip, (now, now))
        elif _days_since(clip.stat().st_mtime) > grace_days:
            stale.append(clip)
    return _remove(stale, dry_run)


def prune_scene_movies(videos_dir: Path, dry_run: bool = False) -> tuple[int, int]:
    """
    Prune the concatenated ``<Scene>.mp4`` that Manim writes in every quality folder.

    Manim Slides builds its clips from the partial files, not from these.
    """
    return _remove(videos_dir.glob("*/*/*.mp4"), dry_run)


def prune_old_quality_dirs(
    videos_dir: Path, days: float = QUALITY_DAYS, dry_run: bool = False
) -> tuple[int, int]:
    """Remove whole ``media/videos/<module>/<quality>/`` folders unused for ``days``."""
    count = freed = 0
    for quality_dir in videos_dir.glob("*/*"):
        if not quality_dir.is_dir():
            continue
        files = [
            Path(root) / f for root, _, names in os.walk(quality_dir) for f in names
        ]
        newest = max((f.stat().st_mtime for f in files), default=0)
        if _days_since(newest) > days:
            count += len(files)
            freed += sum(f.stat().st_size for f in files)
            if not dry_run:
                shutil.rmtree(quality_dir)
    return count, freed


def prune_text_cache(
    media_dir: Path, days: float = TEXT_DAYS, dry_run: bool = False
) -> tuple[int, int]:
    """
    Prune cached ``Text`` / ``Tex`` renders unused for ``days``.

    Uses the later of access and modification time.
    """
    stale = []
    for name in ("texts", "Tex"):
        for path in (media_dir / name).glob("*"):
            if path.is_file():
                stat = path.stat()
                if _days_since(max(stat.st_atime, stat.st_mtime)) > days:
                    stale.append(path)
    return _remove(stale, dry_run)


def prune_media(
    media_dir: Path,
    grace_days: float = GRACE_DAYS,
    quality_days: float = QUALITY_DAYS,
    text_days: float = TEXT_DAYS,
    dry_run: bool = False,
) -> dict[str, tuple[int, int]]:
    """Prune a whole ``media/`` folder, as ``{what: (files removed, bytes)}``."""
    videos = media_dir / "videos"
    count = freed = 0
    for partial_dir in videos.glob("*/*/partial_movie_files/*"):
        if partial_dir.is_dir():
            n, size = prune_partials(partial_dir, grace_days, dry_run=dry_run)
            count, freed = count + n, freed + size
    return {
        "partial clips": (count, freed),
        "scene movies": prune_scene_movies(videos, dry_run),
        "old quality folders": prune_old_quality_dirs(videos, quality_days, dry_run),
        "text cache": prune_text_cache(media_dir, text_days, dry_run),
    }


def prune_after_render(
    partial_dir: Path, media_dir: Path, slides_json: Path | None = None
) -> dict[str, tuple[int, int]]:
    """
    Prune after a scene has rendered completely.

    Marks the clips it used as fresh (the partial clips, and the ``slides/files`` ones
    its ``slides/<Scene>.json`` lists), then prunes this scene's stale partial clips
    and the media-wide leftovers.
    """
    if slides_json is not None and slides_json.is_file():
        # touch only, remove nothing
        prune_json(slides_json, grace_days=float("inf"), touch=True)
    videos = media_dir / "videos"
    return {
        "partial clips": prune_partials(partial_dir, touch=True),
        "scene movies": prune_scene_movies(videos),
        "old quality folders": prune_old_quality_dirs(videos),
        "text cache": prune_text_cache(media_dir),
    }


def prune_presented(
    configs: Iterable[PresentationConfig], touch: bool = True
) -> tuple[int, int]:
    """
    Prune the clips of the scenes that were just presented.

    Never raises: pruning must not turn a finished talk into an error.
    """
    count = freed = 0
    for config in configs:
        try:
            n, size = prune_config(config, touch=touch)
        except (OSError, ValueError) as e:
            logger.warning(f"Pruning the slide clips failed: {e!r}")
            continue
        count, freed = count + n, freed + size
    if count:
        logger.info(f"Pruned {count} stale slide files ({_size_mb(freed)})")
    return count, freed


@click.command()
@click.argument("scenes", nargs=-1)
@folder_path_option
@click.option("--dry-run", is_flag=True, help="Only report what would be removed.")
@click.option("--media", is_flag=True, help="Also prune Manim's cache in media/.")
@click.option(
    "--media-dir",
    metavar="DIRECTORY",
    default=Path("media"),
    type=click.Path(file_okay=False, path_type=Path),
    help="Set Manim's media folder.",
    show_default=True,
)
@click.option(
    "--grace-days",
    type=click.FloatRange(min=0),
    default=GRACE_DAYS,
    show_default=True,
    help="Days an unreferenced clip must have gone unused before it is removed.",
)
@click.option(
    "--quality-days",
    type=click.FloatRange(min=0),
    default=QUALITY_DAYS,
    show_default=True,
    help="Days after which an untouched media/ quality folder is removed.",
)
@click.option(
    "--text-days",
    type=click.FloatRange(min=0),
    default=TEXT_DAYS,
    show_default=True,
    help="Days after which an unused cached text render is removed.",
)
@click.help_option("-h", "--help")
@verbosity_option
def prune(
    scenes: tuple[str, ...],
    folder: Path,
    dry_run: bool,
    media: bool,
    media_dir: Path,
    grace_days: float,
    quality_days: float,
    text_days: float,
) -> None:
    """
    Remove stale clips of SCENE(s) (default: every scene in the folder).

    A clip is stale when its scene's JSON no longer references it and it has gone
    unused for the grace period. Use ``--grace-days 0`` to remove all of them
    at once, and ``--dry-run`` to preview.
    """
    verb = "would remove" if dry_run else "removed"
    jsons = (
        [folder / f"{name}.json" for name in scenes]
        if scenes
        else sorted(folder.glob("*.json"))
    )
    if not jsons:
        raise click.ClickException(f"No slide configs found in {folder}/")
    failed = False
    for path in jsons:
        if not path.exists():
            click.secho(f"{path}: not found", fg="red", err=True)
            failed = True
            continue
        count, freed = prune_json(path, grace_days, dry_run=dry_run)
        click.echo(f"{path.stem}: {verb} {count} stale files ({_size_mb(freed)})")
    if media:
        removed = prune_media(media_dir, grace_days, quality_days, text_days, dry_run)
        for what, (count, freed) in removed.items():
            click.echo(f"media/{what}: {verb} {count} files ({_size_mb(freed)})")
    if failed:
        raise SystemExit(1)
