---
name: konzertbericht
description: Schreibt eine fertige bericht.md für einen Konzertbericht auf engel-wolf.com – auf Deutsch in Sebastians eigenem Schreibstil, mit der englischen Übersetzung kursiv darunter. Nimmt frei diktierte Notizen (Band, Venue, Vorband, Lieblingsmomente, Urteil), bestimmt den Ordner selbst und liest das Konzertdatum aus den EXIF-Daten der Fotos, legt konzerte/<ordner>/bericht.md im richtigen Format an. **Trigger immer** wenn Sebastian "schreib einen Konzertbericht", "Konzertbericht für ...", "mach mir den Bericht", "bericht.md schreiben", "ich war auf einem Konzert", "write a concert report", "fill the bericht" oder ähnliches sagt – besonders im Voice-Mode, wo er einfach frei über den Abend erzählt. Auch nutzen wenn er nur einen Bandnamen plus Eindrücke nennt und offensichtlich einen Bericht daraus will.
---

# Konzertbericht schreiben

Verwandelt frei diktierte Notizen in eine fertige `konzerte/<ordner>/bericht.md` — im
Format, das `musicblog.publish` erwartet, und in Sebastians Schreibstil.

**Diese Skill veröffentlicht nichts.** Sie schreibt nur die Datei. Das Publizieren macht
danach `python -m musicblog.publish` (siehe Schritt 6).

## Schritt 1 — Stil laden

**Zuerst `references/stil.md` neben dieser Datei lesen.** Dort steht die aus 13 echten
Posts abgeleitete Stilanalyse mit wörtlichen Zitaten: Titelmuster, Länge, Aufbau,
Kernvokabular, Schlussformeln, und was ausdrücklich nicht gemacht wird. Ohne diese Datei
wird der Text generisch — sie ist der eigentliche Kern der Skill.

## Schritt 2 — Ordner bestimmen

In dieser Reihenfolge:

1. Nennt Sebastian einen Ordner ("für joss_stone"), den nehmen.
2. Sonst `konzerte/*/` durchsehen: gibt es genau **einen** Ordner ohne `bericht.md`, ist
   das der gemeinte (er hat gerade die Fotos reingelegt). Nimm den und sag es ihm.
3. Sonst neuen Ordner aus dem Bandnamen: **kleingeschrieben, Unterstriche**, wie das
   bestehende `konzerte/joss_stone/` — also `konzerte/hot_8_brass_band/`,
   `konzerte/the_xx/`. Ordner anlegen.

Gibt es dort schon eine `bericht.md`, **nicht stillschweigend überschreiben** — kurz
sagen, dass sie existiert, und fragen: überschreiben oder überarbeiten?

## Schritt 3 — Datum aus den Fotos lesen

Das Datum ist Pflicht (der Parser bricht sonst ab), aber **fast nie eine Rückfrage wert** —
die Handyfotos tragen es im EXIF. Dafür gibt es einen fertigen Befehl:

```bash
.venv/bin/python -m musicblog.publish dates konzerte/<ordner>
```

Der listet jedes Bild mit seinem Aufnahmezeitpunkt und gibt am Ende das Konzertdatum
fertig zum Einsetzen aus:

```
==> concert date: 2026-07-13
    for bericht.md:  - date: 2026-07-13
```

Fotos nach Mitternacht werden dabei korrekt dem Abend davor zugerechnet (Zeitstempel
werden vor der Datumsbildung um 5 Stunden zurückgeschoben), und ein einzelnes verirrtes
Foto von einem anderen Tag überstimmt die Mehrheit nicht.

Reihenfolge insgesamt:

1. Nennt Sebastian ein Datum ("13. Juli", "letzten Freitag"), gilt **seine** Angabe —
   relative Angaben gegen das heutige Datum auflösen.
2. Sonst `publish dates` benutzen. Das ist der Normalfall.
3. Nur wenn der Befehl `no usable EXIF timestamps` meldet (oder noch keine Fotos im Ordner
   liegen): nachfragen.

Weicht ein genanntes Datum stark vom EXIF-Datum ab, kurz darauf hinweisen statt still eins
von beiden zu nehmen.

## Schritt 4 — Fakten sammeln

Aus dem Diktat herausziehen: **Band, Venue, Stadt, Vorband, was musikalisch auffiel,
Publikum, Lieblingsmoment/Anekdote, Gesamturteil.**

Im Voice-Mode ist das Diktat unsortiert und unvollständig — das ist normal. **Nicht
durchfragen.** Fehlt etwas Nicht-Kritisches (Vorband, Setlist-Details), einfach weglassen;
ein kurzer Bericht ist stiltreu. Nur wenn **Band oder Venue** fehlen, in *einer* gebündelten
Rückfrage nachfassen.

**Nichts dazuerfinden** — keine Songtitel, Bandmitglieder, Zugaben oder Zahlen, die nicht
aus dem Diktat kommen. Lieber 80 Wörter als erfundene Details.

Enthält das Diktat Kritik ("Sound war mies", "Vorband hat genervt"), kommt sie so in den
Text. Er schreibt keine PR-Texte.

## Schritt 5 — bericht.md schreiben

Der Bericht wird **immer auf Deutsch** geschrieben. Direkt darunter kommt die **englische
Übersetzung kursiv**. Keine Rückfrage nach der Sprache, kein Modus — immer so.

Exaktes Format — der Parser (`musicblog/bericht.py`) liest es so:

```markdown
# Hot 8 Brass Band live - Conrad Sohm Dornbirn

- date: 2026-07-13

# Bericht

Für die Hot 8 Brass Band fährt man auch mal von München nach Dornbirn.

Nach fünf Songs der erste Höhepunkt. Herrlicher Unsinn, bestes Konzertformat.

Mega anstrengend. Mega geil. Ohne Frage nochmal.

*You'll happily drive from Munich to Dornbirn for the Hot 8 Brass Band.*

*The first high point came after five songs. Glorious nonsense, best concert format there is.*

*Seriously exhausting. Seriously great. Would do it again, no question.*
```

Regeln dazu:

- **Erste Überschrift = Titel.** Muster aus `stil.md` einhalten
  (`Band live - Venue - Stadt`, Festivals ohne `live`). Titel bleibt deutsch.
- **`- date:`** als `YYYY-MM-DD`. Uhrzeit nur wenn sie wirklich gemeint ist
  (`2026-07-13 20:30`). `13.07.2026` geht auch.
- **`# Bericht`** ist ein Trenner und landet nicht im Post — immer so schreiben.
- **Kursiv absatzweise:** jeder englische Absatz einzeln in `*…*`. Markdown-Kursiv geht
  **nicht** über Leerzeilen hinweg — ein `*` um den ganzen Block funktioniert nicht.
  `<em>…</em>` geht auch, `*…*` ist kürzer und rendert identisch.
- **Kein `## English`, keine Trennlinie, keine Überschrift** vor dem englischen Teil. Er
  steht einfach kursiv unter dem deutschen.
- Die Übersetzung folgt **Absatz für Absatz** dem deutschen Text (gleiche Anzahl, gleiche
  Reihenfolge), ist aber keine Wort-für-Wort-Übersetzung: dieselbe begeisterte
  Umgangssprache auf Englisch (siehe „Englische Fassung" in `stil.md`). Band-, Venue- und
  Songnamen bleiben unverändert.
- **Videos: URL allein auf eine Zeile.** Eine YouTube-, Vimeo-, Spotify-, SoundCloud- oder
  Bandcamp-URL, die als einziger Inhalt auf einer eigenen Zeile steht, wird automatisch zu
  einem echten `wp:embed`-Block. Steht dieselbe URL mitten in einem Satz, bleibt sie Text —
  also nie „schaut mal <URL> an" schreiben, wenn ein Player gewollt ist. Davor gehört ein
  kurzer Einleitungssatz, so macht er das auch (Lizzo: `hier mal ein kleiner Ausschnitt vom
  Glastonbury:`). Ein fertiges `<iframe>` funktioniert weiterhin und landet als `wp:html`.
- **Jeder Absatz auf einer Zeile.** Der Markdown-Renderer hat `nl2br` aktiv, ein
  Zeilenumbruch mitten im Absatz wird also zu einem sichtbaren `<br>` im Post. Absätze
  werden ausschließlich durch eine Leerzeile getrennt.
- Optional, nur wenn Sebastian es sagt: `- tags: tollwood, soul` (Zusatz-Tags) oder
  `- slug: eigener-slug`. **`konzert` und `konzertbericht` nicht eintragen** — die setzt
  die Pipeline automatisch.
- Im deutschen Bericht **keine Überschriften** (Absätze tragen den Text). Ausnahme:
  Festival mit vielen Bands, dann ein Absatz pro Band.

## Schritt 6 — Rückmeldung

Kurz melden:

1. Pfad der geschriebenen Datei, Titel, Datum (und woher es kam: Diktat oder EXIF),
   Wortzahl des deutschen Teils.
2. Den fertigen Bericht im Chat zeigen, damit er direkt korrigieren kann.
3. Was noch fehlt, damit publiziert werden kann:
   - `title_picture.jpg` im Ordner (Quelle fürs Header-Bild)
   - die Konzertfotos im Ordner (Unterordner sind erlaubt)
4. Der nächste Befehl:

   ```bash
   .venv/bin/python -m musicblog.publish konzerte/<ordner>
   ```

   Das öffnet die Crop-UI im Browser und legt danach den **Entwurf** an — nichts geht
   ungeprüft online.

Nicht selbst publizieren, außer er sagt es ausdrücklich.
