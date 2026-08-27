# Technical Know-How

How the pieces fit, and the things about this particular host that had to be discovered
rather than assumed.

| | |
|---|---|
| [The plugin](Technical-Plugin) | SEW-CLAUDE-MUSIC, deploy and rollback |
| [NGG import endpoint](Technical-NGG-Helper) | why it is a directly-called file and not a REST route |
| [YARPP keyword fix](Technical-YARPP-Fix) | the stop-word bug and what it did to "related posts" |

## The green header variant

`<post_id>_g.jpg` is **not** an alpha blend. Measured across all 161,020 pixels of the
theme's reference pair `19.jpg` → `19_g.jpg`: the output hue is pinned near 90°, HSL
lightness is preserved, and chroma tapers at both ends purely because of clipping.
Constant-alpha, multiply and gamma-correct blends all fail — an affine blend fit demands
impossible overlay values of G=434, B=−227.

It is a duotone of the lightness channel:

```
gray = (max(R,G,B) + min(R,G,B)) / 2
R' = clip(0.9114 * gray + 12.96)
G' = clip(0.8951 * gray + 38.13)
B' = clip(0.9303 * gray - 14.37)
```

Mean absolute error **4.31/255**. It cannot be exact — EXIF shows the reference pair was
made by hand in Photoshop CS6 in 2013, same `DerivedFrom` DocumentID. The coefficients live
in `config.py::GreenDuotone`, and the implementation uses three 256-entry lookup tables so
no numpy is needed.

## Notes on this host

All of these are handled automatically. They are written down because they contradict what
you would reasonably assume.

**The FTP login does not land in the docroot.** It lands in `/`, and the real docroot is
`/domains/engel-wolf.com/public_html`. `FTP_FOLDER=public_html` is therefore treated as a
*hint*: the code probes the usual layouts for the directory that actually contains
`wp-load.php`.

**FTPS logs in but refuses every TLS data connection.** Login succeeds, then listings and
uploads die with "connection reset" — even with TLS session reuse, which is the usual fix.
So the data channel is proven after login and the code falls back to plain FTP. `check`
reports which mode is in use.

**`SIZE` is refused outright**, with "SIZE not allowed in ASCII mode" even after `TYPE I`.
Existence checks therefore list the parent directory instead of asking about the entry.

**Pretty permalinks are off**, so `/wp-json/` returns the theme's page with HTTP 200 rather
than a 404. The REST client uses `?rest_route=` and falls back to the path form.

**The database prefix is `wp_mailwolf_`.** The install carries the mail-wolf.de history —
there is a `hostinger-migrator-import-log.txt` in the FTP root. That is why long travel
posts from that era sit in the same post table as the concert reports, which matters for
[YARPP](Technical-YARPP-Fix).

## Overview images in the theme

The archive and tag pages build each entry from two layers: the green `_g.jpg` as a CSS
`background` on `div.eintrag`, and the colour `.jpg` as an `<img>` with `opacity: 0` on top,
faded in on `:hover`.

Two consequences:

- Phones have no hover, so the colour image would never appear. A scroll-driven "sliding
  window" in `footer.php` colours the entry nearest the middle of the viewport instead. It
  toggles a **class**, not an inline style — an inline `opacity` would beat the desktop
  `:hover` rule and break it.
- `.eintrag` had `background-size: cover` with no `background-position`, so below 830 px the
  background was cropped from its left edge. Hence "left-aligned and not scaling" on mobile.
  Now `50% 50%` plus `max-width: 830px` and auto margins.

`#eintraege` (the content column, note the plural) is capped at 830 px on single posts via
a `standardpost` class that `single.php` only adds to non-`technical` posts. Without it,
`.tech div#eintraege { width: 100% }` from `styles-tech.css` wins over
`#eintraege { width: 830px }` in `style.css` on specificity, and the column grows with the
Bootstrap container past ~1024 px viewport width.
