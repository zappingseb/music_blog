# Publish a Konzertbericht

Step 4 of four. Steps 1 to 3 — create the folder, drop the photos in, write the report —
are on [Write a Konzertbericht](Write-a-Konzertbericht).

So you have this:

```
konzerte/<band_name>/
├── bericht.md
├── title_picture.jpg
└── Camera Uploads/*.jpg
```

## Dry run first — touches nothing

```bash
.venv/bin/python -m musicblog.publish konzerte/<folder> --dry-run
```

```
==> Joss Stone live - Tollwood München
    date  : 2026-07-13T00:00:00
    slug  : joss-stone-live-tollwood-muenchen
    tags  : konzert, konzertbericht
    status: draft
==> 6 gallery photo(s), header from title_picture.jpg
    Camera Uploads/2026-07-13 20.24.10.jpg (1.4 MB)
    ...
    skipped, same file as title_picture.jpg: Camera Uploads/2026-07-13 21.05.28.jpg
==> dry run -- nothing will be uploaded or created
    crop would be (0, 1241, 4080, 2195) (from .published.json)
```

Shows the parsed title, date, slug and tags, which photos are in, which were skipped as
copies of the title picture, the crop it would use *and where that crop comes from*, and the
rendered Gutenberg body. No uploads, no API calls.

If the date is wrong, fix `- date:` in `bericht.md`. If a photo is missing, check it is not
sitting in a dot-directory.

## Publish

```bash
.venv/bin/python -m musicblog.publish konzerte/<folder>
```

The crop UI opens in your browser. The box is locked to the header aspect ratio (830×194),
both variants preview live as you drag, and arrow keys nudge it. Press **"Diesen Ausschnitt
verwenden"** and the pipeline finishes in the terminal.

### What happens, in this order

The order is forced by the header filenames — they are named after the post ID, and that ID
does not exist until the draft does.

1. draft created → **post ID**
2. `<post_id>.jpg` and `<post_id>_g.jpg` rendered and uploaded to
   `wp-content/gallery/articles/`
3. photos downscaled (default max 2048 px, quality 85, GPS stripped) and uploaded to
   `wp-content/gallery/<slug>/`
4. gallery registered with NextGEN, thumbnails generated
5. `[ngg …]` shortcode appended to the draft
6. edit URL printed

### Useful flags

```bash
--crop 0,706,4080,954     # skip the UI, use this rectangle
--no-browser              # skip the UI; reuses a saved crop, else centre-crops
--max-dim 2048            # longest edge for uploaded photos (0 = keep original)
--quality 85              # JPEG quality for the gallery
--no-strip-exif           # keep EXIF including GPS
--status draft            # draft (default), publish, future, pending, private
```

## Then in wp-admin

The draft carries the date from `bericht.md`, so publishing puts it in the right place
chronologically.

1. Read it. Fix whatever the skill got wrong.
2. **Add the venue and city tags** if they are not already in `bericht.md` — see
   [Tag the venue and the city](Write-a-Konzertbericht#tag-the-venue-and-the-city).
3. Press publish.

## Re-running is safe

`konzerte/<folder>/.published.json` remembers the post ID, gallery ID and crop, so running
`publish` again on the same folder **updates** instead of creating a second post. Re-run
after editing `bericht.md`, or to re-pick the crop. The gallery shortcode is replaced, not
duplicated.

`--no-browser` reuses the saved crop rather than reverting to a centre crop, so a re-run
never silently throws away framing you chose by hand.

## If something goes wrong

```bash
.venv/bin/python -m musicblog.publish check
```

Verifies `.env`, WordPress auth, FTP login, the docroot, the articles folder and the import
endpoint — in that order, so the first `[FAIL]` tells you where it stopped.

| Symptom | Likely cause |
|---|---|
| `WordPress rejected the credentials` | `WP_PWD` is the login password, not an Application Password |
| `ngg-helper.php is not installed` | run `plugin-push` |
| `missing '- date: YYYY-MM-DD' bullet` | the metadata bullet is missing or misspelled |
| `no title_picture.* in ...` | the header shot is not named `title_picture` |
| `0 pictures successfully added` | normal on a re-run — nothing was *new*, not nothing registered |
| gallery admin shows broken thumbnails | thumbnails were not generated; the import action does this, or run it alone |
