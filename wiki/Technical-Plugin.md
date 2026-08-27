# The plugin: SEW-CLAUDE-MUSIC

All custom server-side code lives in **one** plugin, so it stays findable.

```
wp-content/plugins/sew-claude-music/
├── sew-claude-music.php   # the YARPP keyword fix
└── ngg-helper.php         # the endpoint the publish pipeline calls
```

- Source: this repo, `server/sew-claude-music/`
- Plugin URI points back at the repo, so *"Visit plugin site"* in wp-admin gets you to the
  source
- Deploy: `python -m musicblog.publish plugin-push`

## Deploying

```bash
.venv/bin/python -m musicblog.publish plugin-push
```

```
==> pushing 2 file(s) to wp-content/plugins/sew-claude-music
    ngg-helper.php (24.1 KB, token eingesetzt)
    sew-claude-music.php (6.8 KB)
==> site healthy (HTTP 200)
    previous version backed up to server/.remote-backup/20260827-140005
    import endpoint: WP 6.4.7, NGG 3.35, nggAdmin=True
```

Three things it does beyond uploading:

1. **Substitutes `NGG_HELPER_TOKEN`** into any file containing the `@@TOKEN@@` placeholder,
   so the secret is never committed. The renderer asserts the placeholder appears exactly
   **once** — it used to appear twice, and the second occurrence was inside the guard that
   checks whether the token was substituted, so install-time replacement rewrote the guard's
   own sentinel and the helper always reported itself as uninstalled.
2. **Checks the live site** for `Fatal error` / `Parse error` markers afterwards.
3. **Rolls back** to the previous remote version if the site broke. An *active* plugin with
   a syntax error white-screens the whole site, so this is not optional.

Backups land in `server/.remote-backup/<timestamp>/`, which is gitignored.

**Never edit the files on the server.** The next `plugin-push` overwrites them without
asking.

## What deactivating does

| | |
|---|---|
| Deactivate the plugin | the YARPP fix stops working; publishing keeps working |
| Delete the folder | both break |

Publishing survives deactivation because `ngg-helper.php` is called directly by URL, not
through WordPress's plugin system — see [NGG import endpoint](Technical-NGG-Helper).

## Why not a mu-plugin

It started as one (`wp-content/mu-plugins/`) because must-use plugins load first and cannot
be accidentally deactivated. That was moved into a normal plugin on purpose: a mu-plugin
only shows up under a separate "Must-Use" tab, has no deactivate link, and is exactly the
kind of thing you cannot find again two years later.

Worth knowing if you ever go back: WordPress loads only `.php` files sitting **directly** in
`mu-plugins/`. Files in subdirectories are silently ignored.
