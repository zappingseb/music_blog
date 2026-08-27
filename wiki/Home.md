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

## The process

```
1. create the folder            ┐
2. drop the photos in,          │  Write a Konzertbericht
   rename one to title_picture.*│
3. write the report             ┘
4. publish                         Publish a Konzertbericht
```

## Where to go

| | |
|---|---|
| [Installation](Installation) | venv, `.env` keys, the WordPress plugin, `check` |
| [Write a Konzertbericht](Write-a-Konzertbericht) | **steps 1–3:** folder, photos, and the report — by hand or dictated |
| [Publish a Konzertbericht](Publish-a-Konzertbericht) | **step 4:** dry run, crop UI, and what lands where |
| [Other functionalities](Other-functionalities) | crop UI alone, EXIF dates, rebuilding green headers, theme pull/push |
| [Technical Know-How](Technical-Know-How) | how the pieces fit, and the host's quirks |

## The two things worth knowing up front

**Nothing goes live unattended.** `publish` always creates a *draft*. You read it, fix what
needs fixing, and press publish yourself.

**The order of operations is not arbitrary.** The header images are named after the post ID
(`<post_id>.jpg` and `<post_id>_g.jpg`), and that ID only exists once the draft has been
created. So: draft first, then headers, then gallery, then the shortcode.
