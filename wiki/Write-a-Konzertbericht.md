# Write a Konzertbericht

## The `bericht.md` format

No YAML front matter. The first heading is the title, metadata is a bullet list before the
next heading, and `# Bericht` is a separator that does not end up in the post.

```markdown
# Joss Stone live - Tollwood München

- date: 2026-07-13

# Bericht

Es gibt Menschen, die betreten eine Bühne und der Raum gehört ihnen.

Mega anstrengend. Mega geil. Ohne Frage nochmal.

*Some people walk onto a stage and the room is simply theirs.*

*Seriously exhausting. Seriously great. Would do it again, no question.*
```

| Field | |
|---|---|
| First `#` heading | the post title. Pattern: `Band live - Venue - Stadt`, festivals drop `live` |
| `- date:` | **required.** `YYYY-MM-DD`, or `2026-07-13 20:30`, or `13.07.2026` |
| `- tags:` | optional, comma-separated. Added to the two mandatory ones |
| `- slug:` | optional, overrides the slug derived from the title |
| `# Bericht` | separator, dropped. Any *other* heading is kept as content |

Do **not** put `konzert` / `konzertbericht` in `- tags:` — the pipeline adds those itself.

The body is rendered into native Gutenberg blocks, so the draft opens as editable blocks
rather than one Classic block.

## German first, English in italics

The report is written in German, with the English translation in italics directly
underneath — paragraph for paragraph, same count, same order.

Each English paragraph gets its **own** `*…*`. Markdown italics do not span blank lines, so
one pair of asterisks around the whole block does not work.

Also: **one paragraph per line.** The renderer has `nl2br` enabled, so a line break inside
a paragraph becomes a visible `<br>` in the post. Separate paragraphs with a blank line
only.

## Dictating it instead

The `konzertbericht` skill writes the file for you. Say something like:

> "schreib einen Konzertbericht — ich war bei den Hot 8 im Conrad Sohm, die Vorband war
> gut, und dann kam Sexual Healing und der Typ hat sein Shirt ausgezogen …"

It will:

1. Work out the target folder — a `konzerte/*/` folder that has photos but no `bericht.md`
   is assumed to be the one you mean; otherwise it creates `konzerte/<band_name>/`.
2. Work out the date, from what you said or from the photos' EXIF, so it usually does not
   have to ask.
3. Write the body in your own style and show it for correction.

The style guide lives in `.claude/skills/konzertbericht/references/stil.md` and is derived
from 13 real `Konzert`-tagged posts with verbatim quotes: the title patterns, the 150–350
word target, the signature "Lieblingsmoment" anecdote, the vocabulary (`geil`, `fett`,
`steil gehen`, `sehr sehr großartig`), the short verdict endings (`Läuft`), and the
instruction to keep criticism blunt rather than smoothing it into PR copy.

## Videos

A YouTube, Vimeo, Spotify, SoundCloud or Bandcamp URL **alone on its own line** becomes a
real Gutenberg `wp:embed` block:

```markdown
Wie das in einer großen Halle aussieht, hier live aus dem Circus Krone:

https://www.youtube.com/watch?v=AIaQpH-ageY
```

This matters because a bare URL would otherwise be rendered as `<p>https://…</p>`, and
WordPress's own auto-embed only fires on a URL that is a whole *line* of the content — the
`<p>` wrapper stops it, so you would get visible link text and no player.

The same URL **inside a sentence** deliberately stays text. So never write
"schaut mal &lt;URL&gt; an" if you want a player. A hand-written `<iframe>` still works too
and passes through as `wp:html`.

Unknown hosts stay paragraphs rather than being guessed at. The provider list is in
`blocks.EMBED_PROVIDERS`.

## Tag the venue and the city

The pipeline only sets `konzert` + `konzertbericht`. **Add the venue and city yourself** —
`Muffathalle`, `München`, `Tollwood` — either in `bericht.md`:

```markdown
- tags: Muffathalle, München
```

or in wp-admin afterwards.

This is not cosmetic. YARPP's "related posts" leans on tag overlap, and the thinly-tagged
newer posts are exactly the ones that find no sensible relatives. A `Muffathalle` tag
already exists with 9 posts on it. See [YARPP keyword fix](Technical-YARPP-Fix).
