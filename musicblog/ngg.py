"""Client for the ``ngg-helper.php`` endpoint installed in the WordPress root."""

from __future__ import annotations

from pathlib import Path

import requests

from .config import HELPER_FILENAME, REPO_ROOT, Config


def _suggest_token() -> str:
    import secrets

    return secrets.token_urlsafe(32)

HELPER_TEMPLATE = REPO_ROOT / "server" / "sew-claude-music" / "ngg-helper.php"
TOKEN_PLACEHOLDER = "@@TOKEN@@"
TIMEOUT = 180  # thumbnail generation for a full gallery is not fast


class NggError(RuntimeError):
    """The helper was unreachable or reported a failure."""


def render_helper(token: str, template: Path | None = None) -> bytes:
    """Fill the token into the PHP template, ready to upload."""
    source = (template or HELPER_TEMPLATE).read_text(encoding="utf-8")
    occurrences = source.count(TOKEN_PLACEHOLDER)
    if occurrences != 1:
        # More than one and the secret would also land in a comment or in the
        # "not installed yet" guard, which then always trips.
        raise NggError(
            f"expected {TOKEN_PLACEHOLDER} exactly once in the helper template, found {occurrences}"
        )
    if len(token) < 16:
        raise NggError("NGG_HELPER_TOKEN is too short; use at least 16 characters")
    return source.replace(TOKEN_PLACEHOLDER, token).encode("utf-8")


class Helper:
    def __init__(self, config: Config, *, timeout: int = TIMEOUT) -> None:
        self.url = config.helper_url
        self.token = config.helper_token
        self.timeout = timeout

    def _call(self, method: str, params: dict) -> dict:
        if not self.token:
            raise NggError(
                "NGG_HELPER_TOKEN is not set in .env -- add a random secret, e.g.\n"
                "  NGG_HELPER_TOKEN=" + _suggest_token() + "\n"
                "then run: python -m musicblog.publish plugin-push"
            )
        payload = {**params, "token": self.token}
        try:
            response = requests.request(
                method,
                self.url,
                data=payload if method == "POST" else None,
                params=payload if method != "POST" else {"action": params.get("action", "ping")},
                headers={"X-NGG-Token": self.token},
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise NggError(f"cannot reach the helper at {self.url}: {exc}") from exc

        try:
            body = response.json()
        except ValueError:
            text = response.text
            # A PHP error page can also mention wp-content, so rule that out
            # before concluding the file is simply absent.
            php_error = any(
                marker in text
                for marker in ("Fatal error", "Parse error", "Warning:", "Uncaught",
                               "Stack trace", "thrown", "Exception")
            )
            # A missing file is served as WordPress's own 404 page, which this
            # theme returns with HTTP 200 -- so the status code alone is no help.
            looks_like_wordpress = not php_error and "wp-content" in text[:2000]
            if response.status_code == 404 or looks_like_wordpress:
                raise NggError(
                    f"{HELPER_FILENAME} is not installed at {self.url}\n"
                    "run: python -m musicblog.publish plugin-push"
                ) from None
            import re as _re

            stripped = _re.sub(r"<[^>]+>", " ", text)
            stripped = _re.sub(r"\s+", " ", stripped).strip()
            raise NggError(
                f"helper at {self.url} returned {response.status_code} non-JSON:\n"
                f"{stripped[:600]}"
            ) from None
        if not body.get("ok"):
            notes = body.get("notes")
            detail = f"\nnotes: {notes}" if notes else ""
            raise NggError(f"helper error ({response.status_code}): {body.get('error')}{detail}")
        return body

    def ping(self) -> dict:
        return self._call("GET", {"action": "ping"})

    def info(self) -> dict:
        return self._call("GET", {"action": "info"})

    def gallery_basedir(self) -> str:
        """NextGEN's own gallery directory, so the FTP path is never hardcoded."""
        return self.info()["gallery_basedir"].strip("/")

    def import_gallery(self, folder: str, title: str) -> dict:
        return self._call("POST", {"action": "import", "folder": folder, "title": title})

    def generate_thumbnails(self, folder: str) -> dict:
        """Rebuild the static admin thumbnails for an already-imported gallery."""
        return self._call("POST", {"action": "thumbnails", "folder": folder})
