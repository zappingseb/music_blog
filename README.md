# music_blog

Publishes a concert report to [engel-wolf.com](https://engel-wolf.com) — WordPress post,
NextGEN gallery and both header images — with one command.

**📖 [Full user guide in the wiki](https://github.com/zappingseb/music_blog/wiki)**

| | |
|---|---|
| [Installation](https://github.com/zappingseb/music_blog/wiki/Installation) | venv, `.env` keys, the WordPress plugin, `check` |
| [Write a Konzertbericht](https://github.com/zappingseb/music_blog/wiki/Write-a-Konzertbericht) | the `bericht.md` format, dictating it by voice, videos, tags |
| [Publish a Konzertbericht](https://github.com/zappingseb/music_blog/wiki/Publish-a-Konzertbericht) | the six steps from empty folder to finished draft |
| [Other functionalities](https://github.com/zappingseb/music_blog/wiki/Other-functionalities) | crop UI, EXIF dates, rebuilding green headers, theme pull/push |
| [Technical Know-How](https://github.com/zappingseb/music_blog/wiki/Technical-Know-How) | the plugin, the NGG endpoint, the YARPP fix, host quirks |

## Quick start

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env                                           # then fill it in

.venv/bin/python -m musicblog.publish check                    # is everything reachable?
.venv/bin/python -m musicblog.publish konzerte/joss_stone      # crop UI, then a draft
```

Given a folder with `bericht.md`, a `title_picture.jpg` and the concert photos, `publish`
creates a **draft** post with the report as native Gutenberg blocks, tagged `konzert` +
`konzertbericht`, uploads the gallery, registers it with NextGEN, and puts the two header
variants in place. Nothing goes live unattended.

## Layout

```
konzerte/<band_name>/           input: bericht.md, title_picture.jpg, photos   (gitignored)
musicblog/                      the pipeline
  config.py                     .env loading, both dimension spellings, green coefficients
  bericht.py                    parse title/metadata/body, German-aware slugify
  blocks.py                     Markdown -> Gutenberg blocks, oEmbed detection
  images.py                     crop/resize, green duotone, EXIF dates, downscaling
  cropper.py                    the Flask crop UI
  wp.py / ftpsync.py / ngg.py   WordPress REST, FTP, the import endpoint
  theme.py                      pull/push the live theme
  publish.py                    CLI and pipeline
server/sew-claude-music/        the WordPress plugin (deployed with plugin-push)
theme/                          the live theme, pulled over FTP                (gitignored)
wiki/                           the user guide, mirrored to the GitHub wiki by Actions
tests/
```

## Tests

```bash
.venv/bin/python -m unittest discover -s tests -t .
```

## Editing the wiki

The wiki pages are **generated from `wiki/` in this repo** by
`.github/workflows/wiki.yml`. Edit them here and push; editing in the GitHub wiki UI gets
overwritten on the next sync.
