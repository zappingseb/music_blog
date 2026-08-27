"""Minimal WordPress REST client for drafting posts and resolving tags.

Authentication is HTTP Basic with an Application Password (Users -> Profile ->
Application Passwords). A rejected credential fails loudly rather than being
retried, because the usual cause is that ``WP_PWD`` holds the account login
password, which the REST API deliberately does not accept.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

import requests
from requests.auth import HTTPBasicAuth

from .config import Config

TIMEOUT = 60


class WordPressError(RuntimeError):
    """The REST API refused a request."""


class AuthError(WordPressError):
    """Credentials were rejected."""


class Client:
    """REST client that works with or without pretty permalinks.

    ``/wp-json/`` only resolves when pretty permalinks are enabled; otherwise
    WordPress serves the theme's 404 page with HTTP 200. The ``?rest_route=``
    form always works, so it is tried first and the path form is kept as a
    fallback for installs where a plugin blocks the query form.
    """

    STYLES = ("query", "pretty")

    def __init__(self, config: Config, *, timeout: int = TIMEOUT) -> None:
        self.wp_url = config.wp_url
        self.timeout = timeout
        self.session = requests.Session()
        self.session.auth = HTTPBasicAuth(config.wp_user, config.wp_password)
        self.session.headers["User-Agent"] = "music_blog-publisher/1.0"
        self._user = config.wp_user
        self._style: str | None = None

    # -- plumbing --------------------------------------------------------
    def _send(self, style: str, method: str, path: str, params: dict | None, json_body: Any):
        query = dict(params or {})
        if style == "query":
            url = f"{self.wp_url}/"
            query["rest_route"] = f"/wp/v2{path}"
        else:
            url = f"{self.wp_url}/wp-json/wp/v2{path}"
        return self.session.request(
            method, url, params=query, json=json_body, timeout=self.timeout
        )

    def _call(self, method: str, path: str, *, params: dict | None = None, json: Any = None) -> Any:
        styles = (self._style,) if self._style else self.STYLES
        last_response = None
        for style in styles:
            response = self._send(style, method, path, params, json)
            last_response = response

            if response.status_code in (401, 403):
                raise AuthError(
                    f"WordPress rejected the credentials for {self._user!r} "
                    f"({response.status_code} on {method} {path}).\n"
                    "WP_PWD must be an Application Password, not the login password.\n"
                    "Create one at: wp-admin -> Users -> Profile -> Application Passwords."
                )
            if not response.content:
                self._style = style
                return None

            try:
                body = response.json()
            except ValueError:
                # HTML back means this route form is not served; try the other.
                continue

            if not response.ok:
                message = body.get("message", response.text[:300]) if isinstance(body, dict) else response.text[:300]
                raise WordPressError(f"{method} {path} -> {response.status_code}: {message}")
            self._style = style
            return body

        detail = ""
        if last_response is not None:
            detail = (
                f" (HTTP {last_response.status_code}, "
                f"content-type {last_response.headers.get('content-type', '?')})"
            )
        raise WordPressError(
            f"the WordPress REST API at {self.wp_url} did not return JSON for {method} {path}{detail}.\n"
            "Neither /wp-json/ nor ?rest_route= is served -- is the REST API disabled by a plugin?"
        )

    # -- api -------------------------------------------------------------
    def whoami(self) -> dict:
        return self._call("GET", "/users/me", params={"context": "edit"})

    def tag_id(self, name: str) -> int:
        """Find a tag by exact name or slug, creating it if absent."""
        for candidate in self._call("GET", "/tags", params={"search": name, "per_page": 100}):
            if name.lower() in (candidate["name"].lower(), candidate["slug"].lower()):
                return candidate["id"]
        try:
            return self._call("POST", "/tags", json={"name": name})["id"]
        except WordPressError as exc:
            # A parallel create loses the race; the error carries the winner's id.
            if "term_exists" in str(exc):
                for candidate in self._call("GET", "/tags", params={"search": name, "per_page": 100}):
                    if name.lower() in (candidate["name"].lower(), candidate["slug"].lower()):
                        return candidate["id"]
            raise

    def tag_ids(self, names: list[str]) -> list[int]:
        seen: dict[int, None] = {}
        for name in names:
            seen[self.tag_id(name)] = None
        return list(seen)

    def find_post_by_slug(self, slug: str) -> dict | None:
        posts = self._call(
            "GET",
            "/posts",
            params={"slug": slug, "status": "draft,publish,future,pending,private", "context": "edit"},
        )
        return posts[0] if posts else None

    def get_post(self, post_id: int) -> dict:
        return self._call("GET", f"/posts/{post_id}", params={"context": "edit"})

    def create_post(
        self,
        *,
        title: str,
        content: str,
        date: str | dt.datetime,
        slug: str,
        tags: list[int],
        status: str = "draft",
    ) -> dict:
        if isinstance(date, dt.datetime):
            date = date.strftime("%Y-%m-%dT%H:%M:%S")
        return self._call(
            "POST",
            "/posts",
            json={
                "title": title,
                "content": content,
                "date": date,
                "slug": slug,
                "status": status,
                "tags": tags,
            },
        )

    def update_post(self, post_id: int, **fields) -> dict:
        return self._call("POST", f"/posts/{post_id}", json=fields)

    def edit_url(self, config: Config, post_id: int) -> str:
        return f"{config.wp_url}/wp-admin/post.php?post={post_id}&action=edit"
