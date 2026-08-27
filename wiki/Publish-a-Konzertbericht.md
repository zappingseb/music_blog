# Publish a Konzertbericht

Start to finish, the way it actually goes.

## 1. Make the folder, drop the photos in

Folder name: **lowercase with underscores**, like the ones already there
(`konzerte/joss_stone/`, `konzerte/moop_mama/`).

```
konzerte/<band_name>/
├── title_picture.jpg        # the shot you want as the header
└── Camera Uploads/          # the gallery photos - any subfolder name, any nesting
    └── *.jpg
```

**Copy** the header shot to `title_picture.jpg`, do not move it. The pipeline skips any
gallery photo that is byte-identical to the title picture, so it will not appear twice in
the gallery. The dry run tells you which ones it skipped.

Anything under a dot-directory is ignored, so the generated `.build/` folder never gets
picked up as gallery material on a re-run.

## 2. Write `bericht.md`

By hand or dictated — see [Write a Konzertbericht](Write-a-Konzertbericht).

## 3. Sanity-check the date

```bash
.venv/bin/python -m musicblog.publish dates konzerte/<folder>
```

```
==> 8 image(s) in konzerte/joss_stone
    2026:07:13 20:24:10    Camera Uploads/2026-07-13 20.24.10.jpg
    ...
==> concert date: 2026-07-13
    for bericht.md:  - date: 2026-07-13
```

Photos taken after midnight are counted toward the evening the gig started (timestamps are
shifted back 5 hours before the date is taken), and one stray photo from another day does
not outvote the majority.

## 4. Dry run — touches nothing

```bash
.venv/bin/python -m musicblog.publish konzerte/<folder> --dry-run
```

Shows the parsed title, date, slug and tags, which photos are in, which were skipped as
duplicates of the title picture, the crop it would use *and where that crop comes from*,
and the rendered Gutenberg body. No uploads, no API calls.

## 5. Publish

```bash
.venv/bin/python -m musicblog.publish konzerte/<folder>
```

The crop UI opens in your browser. The box is locked to the header aspect ratio (830×194),
both variants preview live as you drag, and arrow keys nudge it. Press **"Diesen Ausschnitt
verwenden"** and the pipeline finishes in the terminal.

What happens, in this order, because the header filenames need the post ID:

1. draft created → **post ID**
2. `<post_id>.jpg` and `<post_id>_g.jpg` rendered and uploaded to
   `wp-content/gallery/articles/`
3. photos downscaled (default max 2048 px, quality 85, GPS stripped) and uploaded to
   `wp-content/gallery/<slug>/`
4. gallery registered with NextGEN, thumbnails generated
5. `[ngg …]` shortcode appended to the draft
6. edit URL printed

Useful flags:

```bash
--crop 0,706,4080,954     # skip the UI, use this rectangle
--no-browser              # skip the UI; reuses a saved crop, else centre-crops
--max-dim 2048            # longest edge for uploaded photos (0 = keep original)
--quality 85              # JPEG quality for the gallery
--no-strip-exif           # keep EXIF including GPS
--status draft            # draft (default), publish, future, pending, private
```

## 6. In wp-admin: read it, tag it, publish it

The draft is created with the date from `bericht.md`, so publishing puts it in the right
place chronologically.

**Add the venue and city tags** if they are not already in `bericht.md` — see the end of
[Write a Konzertbericht](Write-a-Konzertbericht) for why that matters more than it looks.

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
| `0 pictures successfully added` | normal on a re-run — it means nothing was *new*, not that nothing is registered |
| gallery admin shows broken thumbnails | thumbnails were not generated; the import action does this, or run it alone |
