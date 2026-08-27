# NGG import endpoint

`wp-content/plugins/sew-claude-music/ngg-helper.php` — the endpoint the Python pipeline
calls to register galleries with NextGEN.

## Why it exists

NextGEN keeps galleries in its own tables (`ngg_gallery` / `ngg_pictures`). FTP-ing photos
into `wp-content/gallery/<slug>/` does **not** register them — the plugin has to be told.
So the endpoint bootstraps WordPress and calls NextGEN's own importer, which means the
images end up registered exactly as they would through the admin UI.

## Why it is a plain file and not a REST route

`register_rest_route()` would be the idiomatic choice, and it would let the existing
Application Password replace the shared token. It does not work here.

**`WP_ADMIN` has to be defined before `wp-load.php` runs.** NextGEN only registers its
framework and storage modules when it believes it is handling an admin request, and that
decision is made while plugins load. Define it afterwards and
`C_Gallery_Storage::generate_thumbnail()` dies with:

```
Class "C_Frame_Event_Publisher" not found
```

which is exactly what happened on the first attempt, for all six images. A plugin hook runs
too late — NextGEN loads before `sew-claude-music` alphabetically. So the file bootstraps
WordPress itself, defining the constant first, and walks up the directory tree to find
`wp-load.php` so it survives being moved.

## Auth

A shared secret, `NGG_HELPER_TOKEN` in `.env`, compared with `hash_equals`. Accepted as an
`X-NGG-Token` header or a `token` parameter. `plugin-push` substitutes it at deploy time.

## Actions

| Action | |
|---|---|
| `ping` | WP version, NGG version, whether `nggAdmin` loaded, gallery basedir, thumbnail settings |
| `info` | NextGEN's configured gallery directory, so the FTP path is discovered rather than hardcoded |
| `import` | register a folder as a gallery, then generate thumbnails |
| `thumbnails` | regenerate thumbnails for an already-imported gallery |

Read-only diagnostics, kept from debugging the "related posts" problem: `yarpp`,
`yarpp_related`, `yarpp_keywords`, `fulltext`.

## Things that bit, and are now handled

**`import_gallery()` echoes HTML.** It prints `N pictures successfully added` before the
endpoint's own output, which corrupted the JSON response. The call is wrapped in
`ob_start()` / `ob_get_clean()` and the captured text is returned as a diagnostic note.

**`0 pictures successfully added` is normal on a re-run.** It means nothing was *new*, not
that nothing is registered. The endpoint now counts rows before and after instead of
trusting the message — the original diagnosis was wrong for exactly this reason.

**The mapper rejects plain arrays** with `E_InvalidEntityException`. Entities are built via
`C_Gallery_Mapper::create()`, with an `stdClass` cast as fallback.

**Thumbnails are a separate step.** `nggAdmin::import_gallery()` writes the database rows
but not `thumbs/thumbs_<file>.jpg`, so the gallery admin shows broken images until
`C_Gallery_Storage::generate_thumbnail()` runs per picture. The endpoint does this on every
import, and falls back to writing thumbnails with WordPress's own image editor at NextGEN's
configured size if the storage module is ever unusable.

**Image counting.** Counting via `C_Image_Mapper::find_all()` returned every image on the
blog (1497). It now counts `ngg_pictures WHERE galleryid = %d`.

## Uploaded files

Photos are uploaded under their original names, so NextGEN indexes them as expected.
NextGEN also leaves a `*_backup` file next to each photo — that is normal and the older
galleries have them too.
