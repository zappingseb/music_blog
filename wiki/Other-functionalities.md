# Other functionalities

Everything is a subcommand of `python -m musicblog.publish`. The `publish` verb is optional
— `publish konzerte/x` and `konzerte/x` are the same thing.

```
publish          create or update the post (default)
crop             only choose a crop and write the headers locally
dates            show photo EXIF timestamps and the derived concert date
regreen          rebuild <post_id>_g.jpg from <post_id>.jpg on the server
theme-pull       download the live theme over FTP
theme-push       upload named theme files, backing up the remote originals first
plugin-push      deploy the SEW-CLAUDE-MUSIC plugin (rolls back if the site breaks)
check            verify .env, WordPress, FTP and the helper
install-helper   alias for plugin-push
```

## Crop only

```bash
.venv/bin/python -m musicblog.publish crop konzerte/joss_stone
```

Opens the crop UI and writes `header.jpg` + `header_g.jpg` into the folder's `.build/`
directory without touching WordPress. Useful for trying framings. The chosen rectangle is
saved to `.published.json`, so a later `publish` picks it up.

## Rebuilding a green header

```bash
.venv/bin/python -m musicblog.publish regreen 4885          # rebuild + upload
.venv/bin/python -m musicblog.publish regreen 4885 --no-upload
.venv/bin/python -m musicblog.publish regreen --scan        # find broken pairs
```

`regreen` downloads `<post_id>.jpg`, regenerates the green variant from it, backs up the
old remote file into `headers/old/`, and uploads. It reports what the old file actually was:

```
existing 4885_g.jpg: 1968x453, R=131 G=85 B=81 -> NOT GREEN (byte-identical copy of the colour image)
```

`--scan` checks all header pairs **without downloading anything** — byte-identical files
have identical sizes, and that is already in the FTP listing:

```
==> 211 file(s) in wp-content/gallery/articles, 185 of them post headers
    _g same size as colour (likely a plain copy): 1 -> 4916
    _g missing for a post header: 2 -> 1082, 1089
    _g missing for non-post assets (ignore): 26
```

**The scan has a blind spot worth knowing:** it only catches exact copies. A `_g` that was
re-encoded but is stylistically wrong — for example the colour photo with a semi-transparent
green wash over it instead of a proper duotone — passes the size check and still looks
green by average colour. Post 4930 was exactly that case and had to be found by eye.

## Working on the theme

```bash
.venv/bin/python -m musicblog.publish theme-pull
.venv/bin/python -m musicblog.publish theme-push style.css footer.php
```

`theme-pull` downloads the whole live theme (245 files, 5.5 MB) into `theme/`, which is
gitignored. `theme-push` uploads only the files you name and copies each remote original
into `theme/.remote-backup/<timestamp>/` first.

Push is deliberately file-by-file. This writes into a live site.

## Deploying the plugin

```bash
.venv/bin/python -m musicblog.publish plugin-push
```

See [The plugin](Technical-Plugin).

## Tests

```bash
.venv/bin/python -m unittest discover -s tests -t .
```

Covers the `bericht.md` parser, German-aware slugify, the Gutenberg renderer, embeds, crop
geometry, the green duotone, EXIF date derivation including the after-midnight case, and
photo discovery/deduplication.

The one test with real ground truth compares a freshly generated green variant against the
theme's own `19_g.jpg` and asserts the mean absolute error stays under 5/255 — currently
**4.305**. It skips if that reference pair is not in the repo root.
