"""Image work: header crop/resize, the green duotone, and gallery downscaling.

The green variant (``<post_id>_g.jpg``) is *not* an alpha blend. Measured across
all 161,020 pixels of the reference pair ``19.jpg`` -> ``19_g.jpg``, the output
hue is pinned near 90 degrees, HSL lightness is preserved and chroma tapers at
both ends purely because of clipping. That is a duotone/colorize of the
lightness channel, implemented here as three 256-entry lookup tables so no
numpy dependency is needed.
"""

from __future__ import annotations

import datetime as dt
import hashlib
from collections import Counter
from pathlib import Path

from PIL import Image, ImageChops, ImageOps

from .config import TITLE_PICTURE_STEM, GreenDuotone

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png"}

_GPS_IFD = 0x8825
_ORIENTATION = 0x0112
_EXIF_IFD = 0x8769
_DATETIME_ORIGINAL = 0x9003

Box = tuple[int, int, int, int]  # left, top, right, bottom


# --------------------------------------------------------------------------- #
# discovery
# --------------------------------------------------------------------------- #
def file_digest(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def find_title_picture(folder: Path) -> Path:
    for candidate in sorted(folder.iterdir()):
        if candidate.is_file() and candidate.stem.lower() == TITLE_PICTURE_STEM:
            return candidate
    raise FileNotFoundError(f"no {TITLE_PICTURE_STEM}.* in {folder}")


def shot_at(path: Path) -> str:
    """EXIF DateTimeOriginal ("YYYY:MM:DD HH:MM:SS"), or "" if absent.

    Used to order the gallery chronologically and to derive the concert date.
    """
    try:
        with Image.open(path) as image:
            taken = image.getexif().get_ifd(_EXIF_IFD).get(_DATETIME_ORIGINAL)
        if taken:
            return str(taken)
    except (OSError, ValueError):
        pass
    return ""


#: A shot at 01:30 belongs to the concert that started the previous evening, so
#: timestamps are shifted back by this much before their date is taken.
NIGHT_SHIFT = dt.timedelta(hours=5)


def parse_exif_datetime(raw: str) -> dt.datetime | None:
    """Parse an EXIF timestamp ("2026:07:13 20:24:10")."""
    for fmt in ("%Y:%m:%d %H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return dt.datetime.strptime(raw.strip(), fmt)
        except ValueError:
            continue
    return None


def concert_date(paths) -> dt.date | None:
    """Derive the concert date from the photos' EXIF timestamps.

    Returns the most common "concert night" -- timestamps are shifted back by
    :data:`NIGHT_SHIFT` first, so photos taken after midnight still count toward
    the evening the gig started. Ties go to the earlier date. ``None`` if no
    photo carries a usable timestamp.
    """
    nights: Counter[dt.date] = Counter()
    for path in paths:
        stamp = parse_exif_datetime(shot_at(path))
        if stamp:
            nights[(stamp - NIGHT_SHIFT).date()] += 1
    if not nights:
        return None
    # Highest count wins; on a tie prefer the earlier night.
    return max(nights.items(), key=lambda item: (item[1], -item[0].toordinal()))[0]


def find_gallery_images(folder: Path, *, skip_digests: set[str] | None = None) -> list[Path]:
    """Every image below ``folder`` except the title picture and its duplicates."""
    skip_digests = skip_digests or set()
    found = [
        path
        for path in folder.rglob("*")
        if path.is_file()
        and path.suffix.lower() in IMAGE_SUFFIXES
        and path.stem.lower() != TITLE_PICTURE_STEM
        # Skips dotfiles and anything under a dot-directory such as .build/.
        and not any(part.startswith(".") for part in path.relative_to(folder).parts)
    ]
    kept = [path for path in found if file_digest(path) not in skip_digests]
    # Chronological where EXIF allows it, filename otherwise.
    return sorted(kept, key=lambda path: (shot_at(path), path.name.lower()))


# --------------------------------------------------------------------------- #
# loading / geometry
# --------------------------------------------------------------------------- #
def load_rgb(path: Path) -> Image.Image:
    """Open an image with EXIF rotation applied, as RGB."""
    with Image.open(path) as opened:
        image = ImageOps.exif_transpose(opened)
        return image.convert("RGB") if image.mode != "RGB" else image.copy()


def default_crop_box(size: tuple[int, int], aspect: float) -> Box:
    """Widest box of the target aspect ratio, centred on the upper third."""
    width, height = size
    box_width, box_height = width, round(width / aspect)
    if box_height > height:
        box_height, box_width = height, round(height * aspect)
    left = (width - box_width) // 2
    top = (height - box_height) // 3
    return (left, top, left + box_width, top + box_height)


def clamp_box(box: Box, size: tuple[int, int]) -> Box:
    """Keep a crop box inside the image and at least one pixel in each direction."""
    width, height = size
    left, top, right, bottom = (round(value) for value in box)
    left, top = max(0, min(left, width - 1)), max(0, min(top, height - 1))
    right, bottom = min(width, max(right, left + 1)), min(height, max(bottom, top + 1))
    return (left, top, right, bottom)


def crop_and_resize(image: Image.Image, box: Box, size: tuple[int, int]) -> Image.Image:
    """Crop first, then resize -- phone photos are far larger than the target."""
    return image.crop(clamp_box(box, image.size)).resize(size, Image.LANCZOS)


# --------------------------------------------------------------------------- #
# the green variant
# --------------------------------------------------------------------------- #
def hsl_lightness(image: Image.Image) -> Image.Image:
    """(max(R,G,B) + min(R,G,B)) / 2 as an 8-bit L image."""
    red, green, blue = image.convert("RGB").split()
    brightest = ImageChops.lighter(ImageChops.lighter(red, green), blue)
    darkest = ImageChops.darker(ImageChops.darker(red, green), blue)
    return ImageChops.blend(brightest, darkest, 0.5)


def _ramp(slope: float, offset: float) -> list[int]:
    return [min(255, max(0, round(slope * value + offset))) for value in range(256)]


def green_duotone(image: Image.Image, green: GreenDuotone | None = None) -> Image.Image:
    """Apply the theme's green filter: colorize the lightness channel."""
    green = green or GreenDuotone()
    gray = hsl_lightness(image)
    return Image.merge(
        "RGB",
        (
            gray.point(_ramp(*green.r)),
            gray.point(_ramp(*green.g)),
            gray.point(_ramp(*green.b)),
        ),
    )


def mean_channels(image: Image.Image) -> tuple[float, float, float]:
    """Mean R, G, B via the histogram -- no per-pixel Python loop."""
    image = image.convert("RGB")
    histogram = image.histogram()
    total = image.width * image.height
    means = []
    for band in range(3):
        counts = histogram[band * 256 : (band + 1) * 256]
        means.append(sum(value * count for value, count in enumerate(counts)) / total)
    return tuple(means)


def looks_green(image: Image.Image) -> bool:
    """True if green dominates both other channels, i.e. the duotone was applied.

    Catches a _g file that is really just a copy of the colour original, even
    when it was re-encoded and so has a different file size.
    """
    red, green, blue = mean_channels(image)
    return green > red and green > blue


def mean_abs_error(first: Image.Image, second: Image.Image) -> float:
    """Mean absolute per-channel difference, used to validate the duotone."""
    if first.size != second.size:
        raise ValueError(f"size mismatch: {first.size} vs {second.size}")
    left, right = first.convert("RGB").tobytes(), second.convert("RGB").tobytes()
    return sum(abs(a - b) for a, b in zip(left, right)) / len(left)


# --------------------------------------------------------------------------- #
# saving
# --------------------------------------------------------------------------- #
def _exif_bytes(image: Image.Image, strip: bool) -> bytes | None:
    """EXIF for re-encoding, minus location data and a now-baked-in orientation."""
    if strip:
        return None
    exif = image.getexif()
    for tag in (_GPS_IFD, _ORIENTATION):
        if tag in exif:
            del exif[tag]
    return exif.tobytes() if len(exif) else None


def save_jpeg(image: Image.Image, path: Path, *, quality: int = 90, exif: bytes | None = None) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    kwargs = {"quality": quality, "optimize": True, "progressive": True, "subsampling": 0}
    if exif:
        kwargs["exif"] = exif
    image.save(path, "JPEG", **kwargs)
    return path


def prepare_gallery_image(
    source: Path,
    destination: Path,
    *,
    max_dim: int = 2048,
    quality: int = 85,
    strip_exif: bool = True,
) -> Path:
    """Downscale a phone photo for upload, dropping GPS coordinates by default."""
    with Image.open(source) as opened:
        image = ImageOps.exif_transpose(opened)
        exif = _exif_bytes(image, strip_exif)
        if image.mode not in {"RGB", "L"}:
            image = image.convert("RGB")
        if max_dim and max(image.size) > max_dim:
            image.thumbnail((max_dim, max_dim), Image.LANCZOS)
        return save_jpeg(image, destination, quality=quality, exif=exif)
