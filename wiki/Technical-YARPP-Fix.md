# YARPP keyword fix

Lives in `sew-claude-music.php`. Fixes the reason every concert report used to show the same
handful of "related posts".

## The symptom

Every post — Joss Stone, Hot 8, Lizzo, QOTSA — got the same four related posts:

```
weLyon - eine kulinarische Reise
Zürich, Basel, Colmar
Deutschlandreise von mail-wolf.de
we Santa Barbara California Trip
```

Travel posts from the mail-wolf.de era, with scores of 90–240 where a genuinely related
concert scored ~70.

## What it was not

- **Not the template.** `yarpp-template-thumbs.php` correctly iterates `$related_query`.
- **Not the FULLTEXT index.** `yarpp_title` and `yarpp_content` exist and are current —
  searching `Tollwood` returns the 2026 Joss Stone post first.
- **Not markup pollution in the corpus**, which was the first guess. YARPP's
  `extract_keywords()` runs `strip_tags()`, so Gutenberg block comments never become search
  terms.

## What it was

YARPP picks its stop-word list from the **deprecated `WPLANG` constant**
(`classes/YARPP_Cache.php` → `extract_keywords()`):

| | |
|---|---|
| `WPLANG` defined | **no** |
| `get_locale()` | `en_US` |
| `lang/words-de_DE.php` ships with YARPP | yes |
| actually loaded | **`lang/words-en_US.php`** |

So German filler words were never removed. The real extracted keywords, pulled out of the
protected `body_keywords()` method by reflection:

| Post | keywords |
|---|---|
| **1186** weLyon, before | `die und der wir das man es ist auf mit ein hier auch zu den kann eine dem für einen` |
| **4964** Joss Stone, before | `und sie die der ist das im es raum publikum songs ein super tollwood room crowd eine start dabei konzert` |

Twenty out of twenty terms for weLyon were stop words — not one content word. A query made
of words that appear in every German text matches everything, and MySQL's relevance ranking
then simply favours the longest document. The five posts that always won are the five
longest on the blog: weLyon is 58,666 characters (~11,700 words) against 136–590 words for a
concert report.

## The fix

Two filters, both gated on YARPP's public `discovering_keywords()` method so they only run
during keyword extraction and never change what visitors see.

**1. `yarpp_keywords_overused_words`** — loads YARPP's own `lang/words-de_DE.php` and merges
it into the list actually used. Reuses the plugin's curated list rather than inventing one.

**2. `the_content` at priority 5** — strips `<pre>`, `<code>`, `<kbd>`, `<samp>` blocks and
removes shortcodes. Priority 5 runs *before* `do_shortcode` (11), so shortcodes are removed
rather than expanded — otherwise NextGEN gallery filenames and SyntaxHighlighter output
(i.e. source code) become keywords.

Afterwards:

| Post | keywords |
|---|---|
| **1186** weLyon | `hier uns sehr lyon allerdings de einmal direkt sollte stadt restaurant einige dort wirklich tag bus rue la essen finden` |
| **4964** Joss Stone | `raum publikum songs super tollwood room crowd start dabei konzert richtig bühne joss stone natürlich beeindruckend direkt hippie` |
| **4988** Curtis Harding | `cool curtis harding songs richtig gut band macht mir ganz ticket muffathalle soul pop alles dude spaß album live vibe` |

And the results:

| Post | related |
|---|---|
| Joss Stone | **Jamie Cullum live Tollwood** (same venue), Curtis Harding, Adam Green |
| Hot 8 | **Labrassbanda** (brass band), **Hot 8 Brassband Hansa39** (same band, earlier gig) |
| weLyon | **5 Tage Lyon**, Zürich/Basel/Colmar, Burger Diary, Straßburg |

## Settings that also matter

Set in *wp-admin → Settings → YARPP → Relatedness options*. The dropdown values map to
`0` = *do not consider*, `1` = *consider*, `3` = *consider with extra weight*.

Current: `{"title": 3, "body": 1, "tax": {"post_tag": 1}}` with
`require_tax: {post_tag: 1}` and threshold 3.

`require_tax` — *"require at least one tag"* — is what keeps unrelated posts out of the
candidate pool entirely. Only 5 of 219 published posts have no tags at all, so it costs
almost nothing.

**A UI limitation:** for tags, *"require at least one tag"* and *"consider with extra
weight"* are the same dropdown, so you cannot have both from the interface. Setting
`weight.tax.post_tag = 3` alongside `require_tax` needs to be done programmatically.

## What this does not solve

YARPP ranks overall similarity, not venue. Curtis Harding still gets only one of the eight
Muffathalle posts near the top, with "Alben des Jahres" list posts in between — those are
genuinely music-similar, just not what you were looking for. Setting *Bodies* to *do not
consider* makes venue and title decisive and returned 6/6 Muffathalle posts in testing, at
the cost of relatedness resting entirely on titles and tags.
