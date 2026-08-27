"""Parse a ``bericht.md`` concert report.

The format is not YAML frontmatter -- it is plain Markdown where the first
heading is the title and metadata lives in a bullet list before the next
heading::

    # Joss Stone live Tollwood Muenchen

    - date: 2026-07-13

    # Bericht

    Wow, toll.

The separator heading (``# Bericht``) is dropped; everything after it is the
post body.
"""

from __future__ import annotations

import datetime as dt
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

BERICHT_FILENAME = "bericht.md"

_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
_META_BULLET = re.compile(r"^[-*+]\s+([A-Za-z_][\w -]*)\s*:\s*(.*)$")

#: Headings that merely introduce the body and should not appear in the post.
_SEPARATOR_HEADINGS = {"bericht", "report", "text", "inhalt", "content"}

#: German transliterations applied before ASCII folding, so that "Muenchen" is
#: produced rather than "Munchen".
_TRANSLITERATE = {
    "ä": "ae", "ö": "oe", "ü": "ue", "Ä": "ae", "Ö": "oe", "Ü": "ue",
    "ß": "ss", "æ": "ae", "ø": "oe", "å": "aa", "đ": "d", "ł": "l", "&": " und ",
}

_DATE_FORMATS = (
    "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M",
    "%Y-%m-%d", "%d.%m.%Y %H:%M", "%d.%m.%Y",
)


class BerichtError(ValueError):
    """The report file is missing or cannot be parsed."""


def slugify(text: str) -> str:
    """German-aware slug: 'Joss Stone live Tollwood München' -> 'joss-stone-live-tollwood-muenchen'."""
    for source, target in _TRANSLITERATE.items():
        text = text.replace(source, target)
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii").lower()
    return re.sub(r"-{2,}", "-", re.sub(r"[^a-z0-9]+", "-", text)).strip("-")


def parse_date(raw: str) -> dt.datetime:
    value = raw.strip()
    for fmt in _DATE_FORMATS:
        try:
            return dt.datetime.strptime(value, fmt)
        except ValueError:
            continue
    raise BerichtError(f"unrecognised date {raw!r} (expected e.g. 2026-07-13 or 2026-07-13 20:00)")


@dataclass
class Bericht:
    path: Path
    title: str
    date: dt.datetime
    body: str
    metadata: dict[str, str] = field(default_factory=dict)

    @property
    def folder(self) -> Path:
        return self.path.parent

    @property
    def slug(self) -> str:
        return self.metadata.get("slug") or slugify(self.title)

    @property
    def extra_tags(self) -> list[str]:
        """Additional tags from a ``- tags: a, b`` bullet (the required ones are always added)."""
        raw = self.metadata.get("tags", "")
        return [tag.strip() for tag in raw.split(",") if tag.strip()]

    @property
    def wp_date(self) -> str:
        """Site-local ISO 8601 as the WP REST API expects it (no timezone suffix)."""
        return self.date.strftime("%Y-%m-%dT%H:%M:%S")


def parse(text: str, path: Path | None = None) -> Bericht:
    lines = text.splitlines()
    path = path or Path(BERICHT_FILENAME)

    index, title = 0, None
    while index < len(lines):
        match = _HEADING.match(lines[index])
        index += 1
        if match:
            title = match.group(2).strip()
            break
    if not title:
        raise BerichtError(f"{path}: no '# Title' heading found")

    metadata: dict[str, str] = {}
    while index < len(lines) and not _HEADING.match(lines[index]):
        bullet = _META_BULLET.match(lines[index].strip())
        if bullet:
            metadata[bullet.group(1).strip().lower()] = bullet.group(2).strip()
        index += 1

    # Drop a separator heading such as "# Bericht"; a real content heading stays.
    if index < len(lines):
        heading = _HEADING.match(lines[index])
        if heading and heading.group(2).strip().lower().rstrip(":") in _SEPARATOR_HEADINGS:
            index += 1

    if "date" not in metadata:
        raise BerichtError(f"{path}: missing '- date: YYYY-MM-DD' bullet")

    return Bericht(
        path=path,
        title=metadata.get("title", title),
        date=parse_date(metadata["date"]),
        body="\n".join(lines[index:]).strip("\n"),
        metadata=metadata,
    )


def load(folder: Path) -> Bericht:
    path = folder / BERICHT_FILENAME if folder.is_dir() else folder
    if not path.is_file():
        raise BerichtError(f"no {BERICHT_FILENAME} in {folder}")
    return parse(path.read_text(encoding="utf-8"), path)
