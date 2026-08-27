# Installation

## 1. Python environment

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

Needs Pillow, requests, python-dotenv, Flask and Markdown. On Python 3.14 that means
Pillow ≥ 11.3 for the prebuilt wheels.

## 2. `.env`

Start from the template in the repo:

```bash
cp .env.example .env
```

`.env.example` lists every key with a comment on what it is for; `.env` itself is
gitignored. The keys, exactly as they are named:

```
WP_URL=https://engel-wolf.com
WP_USER=<wp user>
WP_PWD=<application password>

WP_gallery_dimension_height=194
WP_gallery_dimensions_width=830

FTP_IP=ftp://<server ip>
FTP_USER=<ftp user>
FTP_PWD=<ftp password>
FTP_FOLDER=public_html

NGG_HELPER_TOKEN=<a long random secret>
```

Two things about this file are load-bearing:

**The dimension keys are spelled inconsistently** — `WP_gallery_dimension_height`
(singular) but `WP_gallery_dimensions_width` (plural). That is how they already were, so
`config.py` accepts both spellings for both keys rather than renaming them.

**`WP_PWD` has to be an Application Password**, not the login password. WordPress rejects
the account password over the REST API by design. Create one at *wp-admin → Users →
Profile → Application Passwords*. If it is wrong, `check` says so immediately instead of
failing halfway through a publish.

`FTP_FOLDER` is treated as a *hint*, not a path — see
[Technical Know-How](Technical-Know-How) for why.

## 3. The WordPress plugin

All server-side code lives in one plugin, **SEW-CLAUDE-MUSIC**. Deploy it:

```bash
.venv/bin/python -m musicblog.publish plugin-push
```

That uploads both files, substitutes `NGG_HELPER_TOKEN` into the import endpoint on the way
up (so the secret is never in the repo), checks the live site for fatal-error markers and
**rolls back automatically** if the site broke.

Then activate it once at *wp-admin → Plugins*. Details:
[The plugin](Technical-Plugin).

Without this plugin, publishing fails — the gallery can never be registered.

## 4. Verify

```bash
.venv/bin/python -m musicblog.publish check
```

```
[OK] config (.env): https://engel-wolf.com, header 830x194
[OK] WordPress REST: authenticated as <wp user> (id 1)
[OK] FTP login: plain FTP (server refused FTPS data channel) as <ftp user>
[OK] WordPress docroot: /domains/engel-wolf.com/public_html
[OK] wp-content/gallery/articles/: found
[OK] NextGEN helper: WP 6.4.7, NGG 3.35, nggAdmin=True, basedir wp-content/gallery
```

The checks run in the order things tend to break, so the first `[FAIL]` tells you where it
stopped. Every missing `.env` key is reported at once rather than one per run.

## 5. Tests

```bash
.venv/bin/python -m unittest discover -s tests -t .
```

Two of them are skipped unless `19.jpg` and `19_g.jpg` are present in the repo root —
those are the theme's reference header pair, and they are the only ground truth for the
green-variant maths.
