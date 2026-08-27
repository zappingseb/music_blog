"""Configuration loaded from .env.

Two quirks of the existing .env are handled here rather than by renaming keys:
the width key is spelled ``WP_gallery_dimensions_width`` (plural) while the
height key is ``WP_gallery_dimension_height`` (singular), and ``FTP_IP`` carries
an ``ftp://`` scheme prefix that ftplib does not want.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent

#: Tags every music post must carry.
REQUIRED_TAGS = ("konzert", "konzertbericht")

#: Basename (without extension) of the picture used for the post header.
TITLE_PICTURE_STEM = "title_picture"

#: Directory under the gallery basedir that holds the ``<post_id>.jpg`` headers.
ARTICLES_DIR = "articles"

#: Everything server-side lives in one plugin so it stays findable.
PLUGIN_SLUG = "sew-claude-music"
PLUGIN_DIR = f"wp-content/plugins/{PLUGIN_SLUG}"

#: The import endpoint, relative to the WordPress root.
HELPER_FILENAME = "ngg-helper.php"
HELPER_PATH = f"{PLUGIN_DIR}/{HELPER_FILENAME}"


class ConfigError(RuntimeError):
    """A required setting is missing or malformed."""


@dataclass(frozen=True)
class GreenDuotone:
    """Per-channel affine ramp applied to HSL lightness.

    Fitted against the reference pair ``19.jpg`` -> ``19_g.jpg`` over all
    161,020 pixels (mean absolute error 4.31/255). The reference pair was
    hand-made in Photoshop, so no closed form matches it exactly; these
    coefficients are the best simple reproduction.
    """

    r: tuple[float, float] = (0.9114, 12.96)
    g: tuple[float, float] = (0.8951, 38.13)
    b: tuple[float, float] = (0.9303, -14.37)


@dataclass(frozen=True)
class Config:
    wp_url: str
    wp_user: str
    wp_password: str
    header_width: int
    header_height: int
    ftp_host: str
    ftp_port: int
    ftp_user: str
    ftp_password: str
    ftp_folder: str
    helper_token: str
    green: GreenDuotone = field(default_factory=GreenDuotone)

    @property
    def header_aspect(self) -> float:
        return self.header_width / self.header_height

    @property
    def helper_url(self) -> str:
        return f"{self.wp_url}/{HELPER_PATH}"


def _require(key: str, *aliases: str) -> str:
    for name in (key, *aliases):
        value = os.environ.get(name)
        if value and value.strip():
            return value.strip()
    spellings = " / ".join((key, *aliases))
    raise ConfigError(f"missing required key in .env: {spellings}")


def _optional(key: str, *aliases: str, default: str = "") -> str:
    try:
        return _require(key, *aliases)
    except ConfigError:
        return default


def _split_host(raw: str) -> tuple[str, int]:
    """Turn ``ftp://203.0.113.10`` or ``host:2121`` into ``(host, port)``."""
    host = raw.strip()
    for scheme in ("ftps://", "ftp://"):
        if host.lower().startswith(scheme):
            host = host[len(scheme) :]
            break
    host = host.rstrip("/")
    port = 21
    # Guard against IPv6 literals, which legitimately contain colons.
    if ":" in host and not host.startswith("["):
        host, _, tail = host.rpartition(":")
        try:
            port = int(tail)
        except ValueError:
            host = f"{host}:{tail}"
    return host, port


def load(env_file: Path | None = None) -> Config:
    """Read .env (without clobbering already-exported variables) into a Config.

    Every missing key is reported at once rather than one per run.
    """
    path = Path(env_file) if env_file else REPO_ROOT / ".env"
    load_dotenv(path, override=False)

    missing: list[str] = []

    def need(key: str, *aliases: str, cast=str):
        try:
            return cast(_require(key, *aliases))
        except ConfigError as exc:
            missing.append(str(exc).split(": ", 1)[1])
            return None
        except ValueError:
            missing.append(f"{key} (must be an integer)")
            return None

    values = {
        "wp_url": need("WP_URL"),
        "wp_user": need("WP_USER"),
        "wp_password": need("WP_PWD", "WP_PASSWORD"),
        "width": need("WP_gallery_dimensions_width", "WP_gallery_dimension_width", cast=int),
        "height": need("WP_gallery_dimension_height", "WP_gallery_dimensions_height", cast=int),
        "ftp_ip": need("FTP_IP", "FTP_HOST"),
        "ftp_user": need("FTP_USER"),
        "ftp_password": need("FTP_PWD", "FTP_PASSWORD"),
        "ftp_folder": need("FTP_FOLDER"),
    }
    if missing:
        joined = "\n  - ".join(missing)
        hint = ""
        if not path.is_file():
            hint = f"\n\n{path} does not exist."
            template = REPO_ROOT / ".env.example"
            if template.is_file():
                hint += f" Start from the template:\n  cp {template.name} {path.name}"
        raise ConfigError(f"missing or invalid keys in .env:\n  - {joined}{hint}")

    host, port = _split_host(values["ftp_ip"])
    return Config(
        wp_url=values["wp_url"].rstrip("/"),
        wp_user=values["wp_user"],
        wp_password=values["wp_password"],
        header_width=values["width"],
        header_height=values["height"],
        ftp_host=host,
        ftp_port=port,
        ftp_user=values["ftp_user"],
        ftp_password=values["ftp_password"],
        ftp_folder=values["ftp_folder"].strip("/"),
        # Only the helper itself needs this, so a dry run works without it.
        helper_token=_optional("NGG_HELPER_TOKEN"),
    )
