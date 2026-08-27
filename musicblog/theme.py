"""Pull the live WordPress theme down over FTP and push single files back.

The theme on engel-wolf.com is a heavily customised Twenty Eleven that only
exists on the server, so editing it means fetching it first. Pushing is
deliberately file-by-file and takes a backup of the remote copy first -- this
writes into a live site.
"""

from __future__ import annotations

import datetime as dt
import ftplib
from pathlib import Path, PurePosixPath

from .ftpsync import Uploader

DEFAULT_THEME = "twentyeleven"
THEMES_DIR = "wp-content/themes"
BACKUP_DIRNAME = ".remote-backup"

#: Never pull these down -- noise that would only pollute the local copy.
SKIP_NAMES = {".", "..", ".DS_Store", "__MACOSX"}


class ThemeError(RuntimeError):
    """Pulling or pushing the theme failed."""


def remote_root(theme: str = DEFAULT_THEME) -> PurePosixPath:
    return PurePosixPath(THEMES_DIR) / theme


def _entries(uploader: Uploader, path: PurePosixPath) -> list[tuple[str, bool, int]]:
    """List a remote directory as ``(name, is_dir, size)`` using raw LIST output."""
    lines: list[str] = []
    try:
        uploader.ftp.retrlines(f"LIST {uploader.resolve(path)}", lines.append)
    except ftplib.all_errors as exc:
        raise ThemeError(f"cannot list {path}: {exc}") from exc

    found = []
    for line in lines:
        parts = line.split(maxsplit=8)
        if len(parts) < 9:
            continue
        permissions, size, name = parts[0], parts[4], parts[8]
        if name in SKIP_NAMES:
            continue
        found.append((name, permissions.startswith("d"), int(size)))
    return found


def pull(
    uploader: Uploader,
    destination: Path,
    *,
    theme: str = DEFAULT_THEME,
    on_file=None,
) -> tuple[int, int]:
    """Download the whole theme into ``destination``. Returns (files, bytes)."""
    root = remote_root(theme)
    if not uploader.exists(root):
        raise ThemeError(f"no theme at {root} on the server")

    files = written = 0

    def walk(remote: PurePosixPath, local: Path) -> None:
        nonlocal files, written
        local.mkdir(parents=True, exist_ok=True)
        for name, is_dir, size in _entries(uploader, remote):
            child_remote, child_local = remote / name, local / name
            if is_dir:
                walk(child_remote, child_local)
                continue
            try:
                with child_local.open("wb") as handle:
                    uploader.ftp.retrbinary(
                        f"RETR {uploader.resolve(child_remote)}", handle.write, blocksize=1 << 16
                    )
            except ftplib.all_errors as exc:
                child_local.unlink(missing_ok=True)
                raise ThemeError(f"cannot download {child_remote}: {exc}") from exc
            files += 1
            written += size
            if on_file:
                on_file(child_local, size)

    walk(root, destination)
    return files, written


def backup_remote(
    uploader: Uploader,
    relative: str,
    local_root: Path,
    *,
    theme: str = DEFAULT_THEME,
    stamp: str | None = None,
) -> Path | None:
    """Copy the current remote version of one file into the local backup dir."""
    remote = remote_root(theme) / relative
    if not uploader.exists(remote):
        return None
    stamp = stamp or dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    target = local_root / BACKUP_DIRNAME / stamp / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        with target.open("wb") as handle:
            uploader.ftp.retrbinary(
                f"RETR {uploader.resolve(remote)}", handle.write, blocksize=1 << 16
            )
    except ftplib.all_errors as exc:
        target.unlink(missing_ok=True)
        raise ThemeError(f"cannot back up {remote}: {exc}") from exc
    return target


def push(
    uploader: Uploader,
    relative_paths: list[str],
    local_root: Path,
    *,
    theme: str = DEFAULT_THEME,
    on_file=None,
) -> list[tuple[str, Path | None]]:
    """Upload the named files, backing up each remote original first.

    Returns ``(relative_path, backup_path_or_None)`` per file.
    """
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    results = []
    for relative in relative_paths:
        local = local_root / relative
        if not local.is_file():
            raise ThemeError(f"no such local file: {local}")
        backup = backup_remote(uploader, relative, local_root, theme=theme, stamp=stamp)
        uploader.upload(local, remote_root(theme) / relative)
        results.append((relative, backup))
        if on_file:
            on_file(relative, backup)
    return results
