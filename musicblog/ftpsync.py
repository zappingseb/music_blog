"""FTP uploads.

``FTP_IP`` is a bare IP address, so credentials would otherwise cross the wire
in cleartext: an explicit FTPS session is attempted first and only falls back to
plain FTP if the server refuses AUTH TLS.
"""

from __future__ import annotations

import ftplib
from contextlib import contextmanager
from pathlib import Path, PurePosixPath

from .config import Config


class FTPError(RuntimeError):
    """Connecting to or writing over FTP failed."""


class _SessionReusingFTP_TLS(ftplib.FTP_TLS):
    """FTPS that reuses the control connection's TLS session for data transfers.

    Many servers (ProFTPD/vsftpd with ``SSLOptions UseImplicitSSL`` style
    hardening) refuse a data connection that negotiates a fresh TLS session.
    Python's ftplib does not reuse the session, so directory listings and
    uploads fail with "Connection reset by peer" or "425 Unable to build data
    connection" even though login succeeded.
    """

    def ntransfercmd(self, cmd, rest=None):
        conn, size = ftplib.FTP.ntransfercmd(self, cmd, rest)
        if self._prot_p:
            conn = self.context.wrap_socket(
                conn, server_hostname=self.host, session=self.sock.session
            )
        return conn, size


class Uploader:
    """Thin wrapper adding recursive mkdir and progress-friendly uploads."""

    def __init__(self, connection: ftplib.FTP, root: str, *, secure: bool) -> None:
        self.ftp = connection
        self.root = PurePosixPath("/") / root.strip("/") if root.strip("/") else PurePosixPath("/")
        self.secure = secure
        self._known_dirs: set[str] = set()

    def resolve(self, remote: str | PurePosixPath) -> PurePosixPath:
        """Interpret a path relative to FTP_FOLDER unless it is already absolute."""
        remote = PurePosixPath(remote)
        return remote if remote.is_absolute() else self.root / remote

    def exists(self, remote: str | PurePosixPath) -> bool:
        """True if the path is present.

        SIZE is refused outright by some servers ("SIZE not allowed in ASCII
        mode" even after TYPE I), so this lists the parent directory rather than
        asking about the entry directly.
        """
        target = self.resolve(remote)
        try:
            self.ftp.cwd(str(target))
            return True
        except ftplib.all_errors:
            pass
        return target.name in _basenames(self.ftp, str(target.parent))

    def ensure_dir(self, remote: str | PurePosixPath) -> PurePosixPath:
        """Create a remote directory and any missing parents."""
        target = self.resolve(remote)
        for depth in range(1, len(target.parts)):
            candidate = PurePosixPath(*target.parts[: depth + 1])
            key = str(candidate)
            if key in self._known_dirs:
                continue
            try:
                self.ftp.mkd(key)
            except ftplib.error_perm as exc:
                # 550 also covers "exists", which is the common and fine case.
                if not str(exc).startswith(("550", "521")):
                    raise FTPError(f"cannot create {key}: {exc}") from exc
            self._known_dirs.add(key)
        return target

    def upload(self, local: Path, remote: str | PurePosixPath) -> PurePosixPath:
        target = self.resolve(remote)
        self.ensure_dir(target.parent)
        with local.open("rb") as handle:
            self.ftp.storbinary(f"STOR {target}", handle, blocksize=1 << 16)
        return target

    def upload_bytes(self, payload: bytes, remote: str | PurePosixPath) -> PurePosixPath:
        import io

        target = self.resolve(remote)
        self.ensure_dir(target.parent)
        self.ftp.storbinary(f"STOR {target}", io.BytesIO(payload), blocksize=1 << 16)
        return target

    def listdir(self, remote: str | PurePosixPath) -> list[str]:
        try:
            return self.ftp.nlst(str(self.resolve(remote)))
        except ftplib.error_perm:
            return []


def _basenames(connection: ftplib.FTP, path: str) -> set[str]:
    try:
        return {entry.rsplit("/", 1)[-1] for entry in connection.nlst(path)}
    except ftplib.all_errors:
        return set()


def _data_channel_works(connection: ftplib.FTP) -> bool:
    """Some servers accept an FTPS login but refuse every TLS data connection."""
    try:
        connection.nlst("/")
        return True
    except ftplib.all_errors:
        return False


def detect_docroot(connection: ftplib.FTP, configured: str) -> str:
    """Find the directory holding wp-load.php.

    ``FTP_FOLDER=public_html`` is not resolvable from the login root on hosts
    that use a ``/domains/<domain>/public_html`` layout, so the configured value
    is treated as a hint and the usual locations are probed for a real
    WordPress install.
    """
    hint = configured.strip("/")
    candidates: list[str] = []
    if hint:
        candidates += [f"/{hint}", f"/domains/{hint}"]
    for entry in sorted(_basenames(connection, "/domains")):
        if entry not in {".", ".."}:
            candidates.append(f"/domains/{entry}/{hint or 'public_html'}")
            candidates.append(f"/domains/{entry}/public_html")
    candidates += ["/public_html", "/htdocs", "/www", "/"]

    seen: set[str] = set()
    for candidate in candidates:
        candidate = "/" + candidate.strip("/") if candidate.strip("/") else "/"
        if candidate in seen:
            continue
        seen.add(candidate)
        if "wp-load.php" in _basenames(connection, candidate):
            return candidate
    return f"/{hint}" if hint else "/"


def _login(config: Config, *, secure: bool) -> ftplib.FTP:
    connection = _SessionReusingFTP_TLS() if secure else ftplib.FTP()
    connection.encoding = "utf-8"
    connection.connect(config.ftp_host, config.ftp_port, timeout=60)
    connection.login(config.ftp_user, config.ftp_password)
    if secure:
        connection.prot_p()  # encrypt the data channel too, not just the control channel
    connection.set_pasv(True)
    return connection


@contextmanager
def connect(config: Config, *, prefer_tls: bool = True):
    """Yield an :class:`Uploader`, preferring FTPS and falling back to plain FTP."""
    connection, secure, tls_error = None, False, None
    if prefer_tls:
        try:
            candidate = _login(config, secure=True)
        except ftplib.all_errors as exc:
            tls_error = exc
        else:
            # An FTPS login can succeed while every data transfer is refused;
            # prove the data channel before committing to it.
            if _data_channel_works(candidate):
                connection, secure = candidate, True
            else:
                tls_error = "server accepted the FTPS login but refused the data channel"
                try:
                    candidate.close()
                except Exception:
                    pass
    if connection is None:
        try:
            connection = _login(config, secure=False)
        except ftplib.all_errors as exc:
            hint = f" (FTPS also failed: {tls_error})" if tls_error else ""
            raise FTPError(f"cannot log in to {config.ftp_host}:{config.ftp_port}: {exc}{hint}") from exc
    try:
        root = detect_docroot(connection, config.ftp_folder)
        yield Uploader(connection, root, secure=secure)
    finally:
        try:
            connection.quit()
        except Exception:
            connection.close()
