# music_blog

Publishes a concert report to [engel-wolf.com](https://engel-wolf.com) — WordPress post,
NextGEN gallery and both header images — with one command.

Given a folder like `konzerte/joss_stone/` containing `bericht.md`, a `title_picture.jpg`
and the concert photos, it creates a **draft** post with the report as native Gutenberg
blocks, tagged `konzert` + `konzertbericht`, uploads the gallery, registers it with
NextGEN, and puts the two header variants in place.

```bash
.venv/bin/python -m musicblog.publish konzerte/joss_stone
```

## Where to go

| | |
|---|---|
| [Installation](Installation) | venv, `.env` keys, the WordPress plugin, `check` |
| [Write a Konzertbericht](Write-a-Konzertbericht) | the `bericht.md` format, dictating it by voice, videos, tags |
| [Publish a Konzertbericht](Publish-a-Konzertbericht) | the six steps from empty folder to finished draft |
| [Other functionalities](Other-functionalities) | crop UI, EXIF dates, rebuilding green headers, theme pull/push |
| [Technical Know-How](Technical-Know-How) | how the pieces fit, and the host's quirks |

## The two things worth knowing up front

**Nothing goes live unattended.** `publish` always creates a *draft*. You read it, fix what
needs fixing, and press publish yourself.

**The order of operations is not arbitrary.** The header images are named after the post ID
(`<post_id>.jpg` and `<post_id>_g.jpg`), and that ID only exists once the draft has been
created. So: draft first, then headers, then gallery, then the shortcode.
