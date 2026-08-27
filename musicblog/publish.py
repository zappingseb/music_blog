"""CLI: turn a konzerte/<folder>/ into a WordPress draft with its NextGEN gallery.

    python -m musicblog.publish konzerte/joss_stone
    python -m musicblog.publish check
    python -m musicblog.publish install-helper
    python -m musicblog.publish crop konzerte/joss_stone

The step order is forced by the header filenames: they are named after the post
ID, which only exists once the draft has been created.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import secrets
import sys
from pathlib import Path, PurePosixPath

from . import bericht, blocks, cropper, ftpsync, images, ngg, theme, wp
from .config import (ARTICLES_DIR, HELPER_PATH, PLUGIN_DIR, REQUIRED_TAGS, Config,
                     ConfigError)
from . import config as config_module

STATE_FILENAME = ".published.json"
BUILD_DIRNAME = ".build"
DEFAULT_GALLERY_BASEDIR = "wp-content/gallery"
PLUGIN_LOCAL = "server/sew-claude-music"
PLUGIN_REMOTE = PLUGIN_DIR


# --------------------------------------------------------------------------- #
# small helpers
# --------------------------------------------------------------------------- #
def step(message: str) -> None:
    print(f"==> {message}", flush=True)


def detail(message: str) -> None:
    print(f"    {message}", flush=True)


def human_bytes(count: int) -> str:
    value = float(count)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} GB"


def load_state(folder: Path) -> dict:
    path = folder / STATE_FILENAME
    if path.is_file():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            detail(f"ignoring unreadable {path.name}")
    return {}


def save_state(folder: Path, state: dict) -> None:
    state["updated_at"] = dt.datetime.now().isoformat(timespec="seconds")
    (folder / STATE_FILENAME).write_text(
        json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def parse_crop(raw: str) -> images.Box:
    parts = [piece.strip() for piece in raw.replace(" ", ",").split(",") if piece.strip()]
    if len(parts) != 4:
        raise argparse.ArgumentTypeError("--crop expects x,y,w,h")
    try:
        left, top, width, height = (int(piece) for piece in parts)
    except ValueError:
        raise argparse.ArgumentTypeError("--crop values must be integers") from None
    return (left, top, left + width, top + height)


# --------------------------------------------------------------------------- #
# commands
# --------------------------------------------------------------------------- #
def cmd_check(args: argparse.Namespace) -> int:
    results: list[tuple[str, bool, str]] = []

    try:
        config = config_module.load()
        results.append(("config (.env)", True, f"{config.wp_url}, header {config.header_width}x{config.header_height}"))
    except ConfigError as exc:
        print(f"[FAIL] config (.env): {exc}")
        return 1

    if not config.helper_token:
        results.append((
            "NGG_HELPER_TOKEN", False,
            f"not set in .env -- add: NGG_HELPER_TOKEN={secrets.token_urlsafe(32)}",
        ))

    try:
        user = wp.Client(config).whoami()
        results.append(("WordPress REST", True, f"authenticated as {user.get('slug')} (id {user.get('id')})"))
    except Exception as exc:
        results.append(("WordPress REST", False, str(exc)))

    try:
        with ftpsync.connect(config) as uploader:
            mode = "FTPS" if uploader.secure else "plain FTP (server refused FTPS data channel)"
            articles = PurePosixPath(DEFAULT_GALLERY_BASEDIR) / ARTICLES_DIR
            results.append(("FTP login", True, f"{mode} as {config.ftp_user}"))
            results.append((
                "WordPress docroot", uploader.exists("wp-load.php"),
                f"{uploader.root} (FTP_FOLDER={config.ftp_folder!r} used as a hint)",
            ))
            results.append((
                f"{articles}/", uploader.exists(articles),
                "found" if uploader.exists(articles) else "missing -- it will be created on first publish",
            ))
    except Exception as exc:
        results.append(("FTP login", False, str(exc)))

    try:
        info = ngg.Helper(config).ping()
        results.append((
            "NextGEN helper", True,
            f"WP {info.get('wp_version')}, NGG {info.get('ngg_version')}, "
            f"nggAdmin={info.get('ngg_admin')}, basedir {info.get('gallery_basedir')}",
        ))
    except Exception as exc:
        results.append(("NextGEN helper", False, str(exc)))

    print()
    for name, ok, message in results:
        print(f"[{'OK' if ok else 'FAIL'}] {name}: {message}")
    failures = [name for name, ok, _ in results if not ok]
    print()
    if failures:
        print(f"{len(failures)} check(s) failed: {', '.join(failures)}")
        return 1
    print("all checks passed")
    return 0


def _resolve_crop(args, report, title_picture: Path, config: Config, state: dict) -> images.Box:
    target = (config.header_width, config.header_height)
    if args.crop:
        detail(f"crop from --crop: {args.crop}")
        return images.clamp_box(args.crop, images.load_rgb(title_picture).size)
    saved = state.get("crop")
    if args.no_browser:
        size = images.load_rgb(title_picture).size
        if saved:
            # Never silently discard a crop that was chosen by hand.
            box = images.clamp_box(tuple(saved), size)
            detail(f"reusing the saved crop from {STATE_FILENAME}: {box}")
        else:
            box = images.default_crop_box(size, config.header_aspect)
            detail(f"crop centred automatically (--no-browser): {box}")
        return box
    return cropper.choose_crop(
        title_picture,
        target,
        green=config.green,
        initial=tuple(saved) if saved else None,
        label=f"{report.title} ({title_picture.name})",
    )


def _build_headers(source: Path, box: images.Box, post_id: int, config: Config, build_dir: Path) -> tuple[Path, Path]:
    target = (config.header_width, config.header_height)
    header = images.crop_and_resize(images.load_rgb(source), box, target)
    plain = images.save_jpeg(header, build_dir / f"{post_id}.jpg", quality=90)
    green = images.save_jpeg(images.green_duotone(header, config.green), build_dir / f"{post_id}_g.jpg", quality=90)
    return plain, green


def cmd_crop(args: argparse.Namespace) -> int:
    """Open the crop UI on its own and write the two header variants locally."""
    config = config_module.load()
    folder = Path(args.folder)
    report = bericht.load(folder)
    title_picture = images.find_title_picture(report.folder)
    state = load_state(report.folder)
    box = _resolve_crop(args, report, title_picture, config, state)
    out_dir = Path(args.out) if args.out else report.folder / BUILD_DIRNAME
    plain, green = _build_headers(title_picture, box, "header", config, out_dir)
    step(f"crop {box}")
    detail(f"{plain} ({human_bytes(plain.stat().st_size)})")
    detail(f"{green} ({human_bytes(green.stat().st_size)})")
    state["crop"] = list(box)
    save_state(report.folder, state)
    return 0


def _articles_dir(basedir: str = DEFAULT_GALLERY_BASEDIR) -> PurePosixPath:
    return PurePosixPath(basedir) / ARTICLES_DIR


def cmd_regreen(args: argparse.Namespace) -> int:
    """Rebuild <post_id>_g.jpg from <post_id>.jpg on the server.

    Also handles the case this was written for: a _g file that is simply a copy
    of the colour image, so the post has no green state at all.
    """
    import ftplib

    config = config_module.load()
    work = Path(args.dest)
    remote_dir = _articles_dir(args.gallery_basedir or DEFAULT_GALLERY_BASEDIR)

    with ftpsync.connect(config) as uploader:
        present = {
            entry.rsplit("/", 1)[-1]: None for entry in uploader.listdir(remote_dir)
        }

        if args.scan:
            # Byte-identical files have identical sizes, so a cheap LIST is
            # enough to spot copied _g files -- no downloads needed.
            sizes: dict[str, int] = {}
            lines: list[str] = []
            uploader.ftp.retrlines(f"LIST {uploader.resolve(remote_dir)}", lines.append)
            for line in lines:
                parts = line.split(maxsplit=8)
                if len(parts) >= 9 and parts[8].endswith(".jpg"):
                    sizes[parts[8]] = int(parts[4])

            ids = sorted(
                {name[:-4] for name in sizes if not name.endswith("_g.jpg")},
                key=lambda value: (len(value), value),
            )
            copied, missing = [], []
            for post_id in ids:
                plain, green = f"{post_id}.jpg", f"{post_id}_g.jpg"
                if green not in sizes:
                    missing.append(post_id)
                elif sizes[plain] == sizes[green]:
                    copied.append(post_id)
            # Only numeric names are post headers; the folder also holds
            # unrelated assets (worldmap.jpg, burger.jpg, ...) that never had a
            # green variant and do not need one.
            missing_posts = [value for value in missing if value.isdigit()]
            other_assets = [value for value in missing if not value.isdigit()]

            step(f"{len(ids)} file(s) in {remote_dir}, {len([i for i in ids if i.isdigit()])} of them post headers")
            detail(f"_g same size as colour (likely a plain copy): {len(copied)}"
                   + (f" -> {', '.join(copied)}" if copied else ""))
            detail(f"_g missing for a post header: {len(missing_posts)}"
                   + (f" -> {', '.join(missing_posts)}" if missing_posts else ""))
            detail(f"_g missing for non-post assets (ignore): {len(other_assets)}")
            if copied or missing_posts:
                detail(f"rebuild with: regreen {' '.join(copied + missing_posts)}")
            return 0

        for post_id in args.post_ids:
            plain, green = f"{post_id}.jpg", f"{post_id}_g.jpg"
            if plain not in present:
                detail(f"{plain} not on the server -- skipped")
                continue
            step(f"post {post_id}")
            work.mkdir(parents=True, exist_ok=True)

            local_plain = work / plain
            with local_plain.open("wb") as handle:
                uploader.ftp.retrbinary(
                    f"RETR {uploader.resolve(remote_dir / plain)}", handle.write, blocksize=1 << 16
                )
            source = images.load_rgb(local_plain)
            detail(f"downloaded {plain} ({source.width}x{source.height}, {human_bytes(local_plain.stat().st_size)})")

            if green in present:
                backup = work / "old" / green
                backup.parent.mkdir(parents=True, exist_ok=True)
                with backup.open("wb") as handle:
                    uploader.ftp.retrbinary(
                        f"RETR {uploader.resolve(remote_dir / green)}", handle.write, blocksize=1 << 16
                    )
                old = images.load_rgb(backup)
                red, grn, blu = images.mean_channels(old)
                identical = images.file_digest(backup) == images.file_digest(local_plain)
                verdict = "green" if images.looks_green(old) else "NOT GREEN"
                detail(
                    f"existing {green}: {old.width}x{old.height}, "
                    f"R={red:.0f} G={grn:.0f} B={blu:.0f} -> {verdict}"
                    + (" (byte-identical copy of the colour image)" if identical else "")
                )
                detail(f"backed up to {backup}")

            built = images.save_jpeg(
                images.green_duotone(source, config.green), work / green, quality=args.quality
            )
            detail(f"rebuilt {green} ({human_bytes(built.stat().st_size)})")

            if args.no_upload:
                detail("--no-upload: nothing sent")
                continue
            uploader.upload(built, remote_dir / green)
            detail(f"uploaded -> {remote_dir / green}")
    return 0


def _site_healthy(config: Config) -> tuple[bool, str]:
    """Fetch a page and look for the markers a fatal PHP error leaves behind."""
    import requests

    try:
        response = requests.get(f"{config.wp_url}/?tag=konzert", timeout=60)
    except requests.RequestException as exc:
        return False, f"unreachable: {exc}"
    markers = [
        marker
        for marker in ("Fatal error", "Parse error", "There has been a critical error")
        if marker in response.text
    ]
    if response.status_code != 200 or markers:
        return False, f"HTTP {response.status_code}, markers {markers}"
    return True, f"HTTP {response.status_code}"


def cmd_plugin_push(args: argparse.Namespace) -> int:
    """Deploy the SEW-CLAUDE-MUSIC plugin, rolling back if the site breaks.

    An active plugin with a syntax error takes the whole site down, so the
    previous remote copy is kept and restored on failure.
    """
    config = config_module.load()
    local_root = Path(args.source)
    files = sorted(
        path
        for path in local_root.rglob("*")
        if path.is_file() and not path.name.startswith(".")
    )
    if not files:
        raise FileNotFoundError(f"no files to push in {local_root}")

    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_dir = local_root.parent / ".remote-backup" / stamp
    remote_root = PurePosixPath(args.remote)

    step(f"pushing {len(files)} file(s) to {remote_root}")
    with ftpsync.connect(config) as uploader:
        saved: list[tuple[Path, PurePosixPath]] = []
        for path in files:
            relative = path.relative_to(local_root).as_posix()
            target = remote_root / relative
            if uploader.exists(target):
                copy = backup_dir / relative
                copy.parent.mkdir(parents=True, exist_ok=True)
                with copy.open("wb") as handle:
                    uploader.ftp.retrbinary(
                        f"RETR {uploader.resolve(target)}", handle.write, blocksize=1 << 16
                    )
                saved.append((copy, target))
            # Files carrying the token placeholder are rendered on the way up,
            # so the secret never sits in the repo.
            payload = path.read_bytes()
            if ngg.TOKEN_PLACEHOLDER.encode() in payload:
                rendered = ngg.render_helper(config.helper_token, path)
                uploader.upload_bytes(rendered, target)
                detail(f"{relative} ({human_bytes(len(rendered))}, token eingesetzt)")
            else:
                uploader.upload(path, target)
                detail(f"{relative} ({human_bytes(len(payload))})")

        healthy, message = _site_healthy(config)
        if healthy:
            step(f"site healthy ({message})")
            if saved:
                detail(f"previous version backed up to {backup_dir}")
            try:
                info = ngg.Helper(config).ping()
                detail(f"import endpoint: WP {info.get('wp_version')}, NGG {info.get('ngg_version')}, "
                       f"nggAdmin={info.get('ngg_admin')}")
            except ngg.NggError as exc:
                detail(f"import endpoint NOT reachable: {exc}")
                return 1
            return 0

        step(f"site BROKEN ({message}) -- rolling back")
        for copy, target in saved:
            uploader.upload(copy, target)
            detail(f"restored {target}")
        if not saved:
            detail("nothing to restore; delete the plugin folder over FTP to recover")
        healthy, message = _site_healthy(config)
        detail(f"after rollback: {'healthy' if healthy else 'STILL BROKEN'} ({message})")
        return 1


def cmd_theme_pull(args: argparse.Namespace) -> int:
    config = config_module.load()
    destination = Path(args.dest)
    step(f"pulling {theme.remote_root(args.theme)} -> {destination}/")
    with ftpsync.connect(config) as uploader:
        detail(f"connected via {'FTPS' if uploader.secure else 'plain FTP'}, root {uploader.root}")
        count = [0]

        def progress(path: Path, size: int) -> None:
            count[0] += 1
            if count[0] % 25 == 0:
                detail(f"{count[0]} files ...")

        files, written = theme.pull(
            uploader, destination, theme=args.theme, on_file=progress
        )
    step(f"{files} file(s), {human_bytes(written)}")
    detail(f"local copy: {destination}")
    return 0


def cmd_theme_push(args: argparse.Namespace) -> int:
    config = config_module.load()
    local_root = Path(args.dest)
    step(f"pushing {len(args.paths)} file(s) to {theme.remote_root(args.theme)}")
    with ftpsync.connect(config) as uploader:
        results = theme.push(uploader, args.paths, local_root, theme=args.theme)
    for relative, backup in results:
        detail(f"{relative}  (backup: {backup if backup else 'none - file was new'})")
    step("done")
    return 0


def cmd_dates(args: argparse.Namespace) -> int:
    """Report each photo's EXIF timestamp and the concert date derived from them."""
    folder = Path(args.folder)
    if not folder.is_dir():
        raise FileNotFoundError(f"not a directory: {folder}")

    candidates = images.find_gallery_images(folder)
    try:
        candidates.append(images.find_title_picture(folder))
    except FileNotFoundError:
        pass
    if not candidates:
        detail(f"no images found below {folder}")
        return 1

    step(f"{len(candidates)} image(s) in {folder}")
    for path in sorted(candidates, key=lambda p: (images.shot_at(p), p.name)):
        stamp = images.shot_at(path) or "(no EXIF)"
        detail(f"{stamp:22} {path.relative_to(folder)}")

    derived = images.concert_date(candidates)
    if derived is None:
        step("no usable EXIF timestamps -- the date has to be given by hand")
        return 1
    step(f"concert date: {derived.isoformat()}")
    detail(f"for bericht.md:  - date: {derived.isoformat()}")
    return 0


def cmd_publish(args: argparse.Namespace) -> int:
    config = config_module.load()
    folder = Path(args.folder)

    # ---- 1. parse -------------------------------------------------------
    report = bericht.load(folder)
    folder = report.folder
    state = load_state(folder)
    tags = list(REQUIRED_TAGS) + [tag for tag in report.extra_tags if tag not in REQUIRED_TAGS]
    body = blocks.render(report.body)

    step(f"{report.title}")
    detail(f"date  : {report.wp_date}")
    detail(f"slug  : {report.slug}")
    detail(f"tags  : {', '.join(tags)}")
    detail(f"status: {args.status}")

    # ---- 2. images ------------------------------------------------------
    title_picture = images.find_title_picture(folder)
    every_photo = images.find_gallery_images(folder)
    gallery_files = images.find_gallery_images(
        folder, skip_digests={images.file_digest(title_picture)}
    )
    duplicates = [path for path in every_photo if path not in gallery_files]

    step(f"{len(gallery_files)} gallery photo(s), header from {title_picture.name}")
    for path in gallery_files:
        detail(f"{path.relative_to(folder)} ({human_bytes(path.stat().st_size)})")
    for path in duplicates:
        # Identical to the title picture, so it would appear twice in the gallery.
        detail(f"skipped, same file as {title_picture.name}: {path.relative_to(folder)}")
    if not gallery_files:
        detail("no gallery photos found -- the post will have no gallery")

    if args.dry_run:
        # Report the crop the real run would actually use, saved crop included.
        size = images.load_rgb(title_picture).size
        saved = state.get("crop")
        if args.crop:
            box, source = args.crop, "--crop"
        elif saved:
            box, source = tuple(saved), STATE_FILENAME
        else:
            box, source = images.default_crop_box(size, config.header_aspect), "auto-centred"
        step("dry run -- nothing will be uploaded or created")
        detail(f"crop would be {images.clamp_box(box, size)} (from {source})")
        if not args.crop and not saved:
            detail("the crop UI would open; this is the fallback if you skip it")
        detail(f"headers would go to <basedir>/{ARTICLES_DIR}/<post_id>.jpg and _g.jpg")
        detail(f"gallery would go to <basedir>/{report.slug}/")
        print("\n---- post body ----")
        print(blocks.set_gallery_shortcode(body, 0))
        print("---- end body ----")
        return 0

    # ---- 3. crop --------------------------------------------------------
    box = _resolve_crop(args, report, title_picture, config, state)
    state["crop"] = list(box)

    # ---- 4. create or find the draft ------------------------------------
    client = wp.Client(config)
    user = client.whoami()
    detail(f"WordPress: authenticated as {user.get('slug')}")
    tag_ids = client.tag_ids(tags)

    post = None
    if state.get("post_id"):
        try:
            post = client.get_post(int(state["post_id"]))
        except wp.WordPressError:
            detail(f"post {state['post_id']} from {STATE_FILENAME} is gone; looking up by slug")
    if post is None:
        post = client.find_post_by_slug(report.slug)

    if post:
        post_id = int(post["id"])
        step(f"updating existing post {post_id}")
        client.update_post(
            post_id, title=report.title, content=body, date=report.wp_date, tags=tag_ids
        )
    else:
        step("creating draft")
        post = client.create_post(
            title=report.title,
            content=body,
            date=report.wp_date,
            slug=report.slug,
            tags=tag_ids,
            status=args.status,
        )
        post_id = int(post["id"])
        detail(f"post id {post_id}")
    state["post_id"] = post_id
    state["slug"] = report.slug
    save_state(folder, state)

    # ---- 5. build the header variants -----------------------------------
    build_dir = folder / BUILD_DIRNAME
    step(f"rendering headers {config.header_width}x{config.header_height}")
    plain, green = _build_headers(title_picture, box, post_id, config, build_dir)
    detail(f"{plain.name} ({human_bytes(plain.stat().st_size)})")
    detail(f"{green.name} ({human_bytes(green.stat().st_size)})")

    # ---- 6. downscale the gallery photos --------------------------------
    prepared: list[Path] = []
    if gallery_files:
        step(f"preparing gallery photos (max {args.max_dim}px, quality {args.quality})")
        gallery_build = build_dir / "gallery"
        for source in gallery_files:
            destination = gallery_build / f"{images.file_digest(source)[:8]}-{source.name}"
            prepared.append(
                images.prepare_gallery_image(
                    source,
                    destination,
                    max_dim=args.max_dim,
                    quality=args.quality,
                    strip_exif=not args.no_strip_exif,
                )
            )
            detail(f"{destination.name} ({human_bytes(destination.stat().st_size)})")

    # ---- 7. work out where things live on the server ---------------------
    helper = ngg.Helper(config)
    basedir = args.gallery_basedir
    if not basedir:
        try:
            basedir = helper.gallery_basedir()
        except ngg.NggError as exc:
            detail(f"helper unavailable ({exc}); falling back to {DEFAULT_GALLERY_BASEDIR}")
            basedir = DEFAULT_GALLERY_BASEDIR
    remote_base = PurePosixPath(basedir)
    detail(f"gallery basedir: {remote_base}")

    # ---- 8. upload ------------------------------------------------------
    step("uploading over FTP")
    with ftpsync.connect(config) as uploader:
        detail(f"connected via {'FTPS' if uploader.secure else 'plain FTP'}")
        for local in (plain, green):
            target = uploader.upload(local, remote_base / ARTICLES_DIR / local.name)
            detail(f"{target}")
        for local in prepared:
            # NextGEN indexes by filename, so keep the original names remotely.
            original = local.name.split("-", 1)[1]
            uploader.upload(local, remote_base / report.slug / original)
        if prepared:
            detail(f"{len(prepared)} photo(s) -> {remote_base / report.slug}/")

    # ---- 9. register the gallery ----------------------------------------
    gallery_id = state.get("gallery_id")
    if prepared:
        step("registering the gallery with NextGEN")
        result = helper.import_gallery(report.slug, report.title)
        gallery_id = int(result["gallery_id"])
        detail(f"gallery id {gallery_id}, {result.get('images')} image(s) registered")
        thumbs = result.get("thumbnails") or {}
        if thumbs:
            detail(
                f"thumbnails: {thumbs.get('generated')}/{thumbs.get('total')} at {thumbs.get('size')}"
                + (f" -- FAILED: {thumbs['failed']}" if thumbs.get("failed") else "")
            )
        state["gallery_id"] = gallery_id
        save_state(folder, state)

    # ---- 10. attach the shortcode ---------------------------------------
    if gallery_id:
        step("attaching the gallery shortcode to the post")
        client.update_post(post_id, content=blocks.set_gallery_shortcode(body, int(gallery_id)))

    save_state(folder, state)
    print()
    step("done")
    detail(f"edit: {client.edit_url(config, post_id)}")
    detail(f"header: {config.wp_url}/{remote_base}/{ARTICLES_DIR}/{post_id}.jpg")
    return 0


# --------------------------------------------------------------------------- #
# argument parsing
# --------------------------------------------------------------------------- #
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m musicblog.publish",
        description="Publish a concert report to WordPress with its NextGEN gallery.",
    )
    subparsers = parser.add_subparsers(dest="command")

    def add_crop_options(sub: argparse.ArgumentParser) -> None:
        sub.add_argument("folder", help="konzerte/<folder> containing bericht.md")
        sub.add_argument("--crop", type=parse_crop, metavar="X,Y,W,H",
                         help="skip the crop UI and use this rectangle")
        sub.add_argument("--no-browser", action="store_true",
                         help="never open the crop UI; centre-crop automatically")

    publish_parser = subparsers.add_parser("publish", help="create or update the post (default)")
    add_crop_options(publish_parser)
    publish_parser.add_argument("--status", default="draft",
                                choices=["draft", "publish", "future", "pending", "private"])
    publish_parser.add_argument("--max-dim", type=int, default=2048,
                                help="longest edge for uploaded gallery photos (0 = keep original)")
    publish_parser.add_argument("--quality", type=int, default=85, help="JPEG quality for gallery photos")
    publish_parser.add_argument("--no-strip-exif", action="store_true",
                                help="keep EXIF on gallery photos (GPS included)")
    publish_parser.add_argument("--gallery-basedir", default=None,
                                help=f"override NextGEN's gallery dir (default: ask the helper, else {DEFAULT_GALLERY_BASEDIR})")
    publish_parser.add_argument("--dry-run", action="store_true",
                                help="parse and report only; no uploads, no API calls")
    publish_parser.set_defaults(func=cmd_publish)

    crop_parser = subparsers.add_parser("crop", help="only choose a crop and write the headers locally")
    add_crop_options(crop_parser)
    crop_parser.add_argument("--out", default=None, help="directory for the two header files")
    crop_parser.set_defaults(func=cmd_crop)

    dates_parser = subparsers.add_parser(
        "dates", help="show photo EXIF timestamps and the derived concert date"
    )
    dates_parser.add_argument("folder", help="konzerte/<folder> containing the photos")
    dates_parser.set_defaults(func=cmd_dates)

    regreen_parser = subparsers.add_parser(
        "regreen", help="rebuild <post_id>_g.jpg from <post_id>.jpg on the server"
    )
    regreen_parser.add_argument("post_ids", nargs="*", help="post ids, e.g. 4885")
    regreen_parser.add_argument("--scan", action="store_true",
                                help="only report pairs whose _g is missing or looks like a copy")
    regreen_parser.add_argument("--dest", default="headers", help="local working directory")
    regreen_parser.add_argument("--quality", type=int, default=90)
    regreen_parser.add_argument("--gallery-basedir", default=None)
    regreen_parser.add_argument("--no-upload", action="store_true", help="build locally only")
    regreen_parser.set_defaults(func=cmd_regreen)

    plugin_parser = subparsers.add_parser(
        "plugin-push", help="deploy the SEW-CLAUDE-MUSIC plugin (rolls back if the site breaks)"
    )
    plugin_parser.add_argument("--source", default=PLUGIN_LOCAL)
    plugin_parser.add_argument("--remote", default=PLUGIN_REMOTE)
    plugin_parser.set_defaults(func=cmd_plugin_push)

    pull_parser = subparsers.add_parser("theme-pull", help="download the live theme over FTP")
    pull_parser.add_argument("--theme", default=theme.DEFAULT_THEME)
    pull_parser.add_argument("--dest", default="theme", help="local directory (default: theme)")
    pull_parser.set_defaults(func=cmd_theme_pull)

    push_parser = subparsers.add_parser(
        "theme-push", help="upload named theme files, backing up the remote originals first"
    )
    push_parser.add_argument("paths", nargs="+", help="paths relative to the local theme dir")
    push_parser.add_argument("--theme", default=theme.DEFAULT_THEME)
    push_parser.add_argument("--dest", default="theme")
    push_parser.set_defaults(func=cmd_theme_push)

    check_parser = subparsers.add_parser("check", help="verify .env, WordPress, FTP and the helper")
    check_parser.set_defaults(func=cmd_check)

    install_parser = subparsers.add_parser(
        "install-helper", help="alias for plugin-push (the helper now ships inside the plugin)"
    )
    install_parser.add_argument("--source", default=PLUGIN_LOCAL)
    install_parser.add_argument("--remote", default=PLUGIN_REMOTE)
    install_parser.set_defaults(func=cmd_plugin_push)

    return parser


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    known = {"publish", "crop", "dates", "regreen", "theme-pull", "theme-push",
             "plugin-push", "check", "install-helper"}
    # Allow the common form: `python -m musicblog.publish konzerte/joss_stone`
    if argv and argv[0] not in known and not argv[0].startswith("-"):
        argv.insert(0, "publish")

    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return 2
    try:
        return args.func(args)
    except (ConfigError, bericht.BerichtError, ftpsync.FTPError, ngg.NggError, theme.ThemeError,
            wp.WordPressError, cropper.CropCancelled, FileNotFoundError) as exc:
        print(f"\nerror: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\naborted", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
