<?php
/**
 * Plugin Name:       SEW-CLAUDE-MUSIC
 * Plugin URI:        https://github.com/zappingseb/music_blog
 * Description:       Aller eigene Server-Code für den Musik-Blog, an einer Stelle. (1) ngg-helper.php in diesem Ordner ist der Endpunkt, den das Python-Publish-Script aufruft, um NextGEN-Galerien zu registrieren und Thumbnails zu erzeugen -- ohne ihn schlägt jedes Veröffentlichen fehl. (2) Repariert YARPPs Keyword-Erkennung: deutsche Stoppwörter raus, Code und Shortcodes raus. Ohne diesen Fix liefert YARPP für jeden Post wieder dieselben paar sehr langen Reise-Posts als "related". NICHT deaktivieren.
 * Version:           2.0.0
 * Author:            Sebastian Engel-Wolf
 * License:           GPL-2.0-or-later
 * Requires at least: 5.5
 *
 * Quelle: https://github.com/zappingseb/music_blog -> server/sew-claude-music/
 * Änderungen dort machen und mit "python -m musicblog.publish plugin-push"
 * deployen, nicht direkt auf dem Server editieren -- der nächste Deploy
 * überschreibt das sonst.
 *
 * ---------------------------------------------------------------------------
 * INVENTAR: aller eigene Server-Code für diesen Blog steckt in DIESEM Ordner
 * ---------------------------------------------------------------------------
 * wp-content/plugins/sew-claude-music/
 *   |
 *   |-- sew-claude-music.php   <- diese Datei. Der YARPP-Keyword-Fix (unten).
 *   |
 *   `-- ngg-helper.php         <- der Endpunkt für das Python-Publish-Script.
 *                                 Aktionen: ping, info, import, thumbnails
 *                                 + nur lesende Diagnose: yarpp, yarpp_related,
 *                                   yarpp_keywords, fulltext
 *                                 Auth: Shared Secret, NGG_HELPER_TOKEN in der
 *                                 .env des Repos.
 *
 * Quelle für beides: https://github.com/zappingseb/music_blog
 *                    dort im Ordner server/sew-claude-music/
 * Deploy für beides: python -m musicblog.publish plugin-push
 *   (setzt den Token in ngg-helper.php ein, prüft danach die Live-Seite und
 *    rollt bei einem Fatal Error automatisch zurück)
 *
 * Warum ngg-helper.php eine direkt aufgerufene Datei ist und keine
 * register_rest_route()-Route: WP_ADMIN muss VOR wp-load.php definiert sein,
 * sonst registriert NextGEN seine Framework-Module nicht und
 * C_Gallery_Storage::generate_thumbnail() stirbt mit "Class
 * C_Frame_Event_Publisher not found". Ein Plugin-Hook läuft dafür zu spät --
 * NextGEN wird alphabetisch vor diesem Plugin geladen. Deshalb bootstrapped die
 * Datei WordPress selbst.
 *
 * Konsequenz: ngg-helper.php funktioniert auch, wenn dieses Plugin deaktiviert
 * ist -- die Datei wird ja direkt per URL aufgerufen. Deaktivieren schaltet also
 * nur den YARPP-Fix ab, nicht das Veröffentlichen. Löschen des Ordners bricht
 * beides.
 */

if (!defined('ABSPATH')) {
    exit;
}

define('SEW_CLAUDE_MUSIC_VERSION', '1.0.0');

/* ===========================================================================
 * YARPP: Keyword-Erkennung reparieren
 * ---------------------------------------------------------------------------
 * Problem 1 -- deutsche Stoppwörter werden nie entfernt.
 *
 *   YARPP wählt seine Stoppwortliste in classes/YARPP_Cache.php ->
 *   extract_keywords() über die längst abgeschaffte Konstante WPLANG. Die ist
 *   hier nicht definiert und get_locale() liefert en_US, also lädt YARPP
 *   lang/words-en_US.php -- obwohl lang/words-de_DE.php im Plugin mitgeliefert
 *   wird. Deutsche Füllwörter bleiben damit in den Suchbegriffen. Gemessen für
 *   Post 1186 ("weLyon"), vorher:
 *
 *       die und der wir das man es ist auf mit ein hier auch zu den kann eine
 *
 *   20 von 20 Begriffen waren Füllwörter, kein einziges Inhaltswort. Eine
 *   Suchanfrage aus Wörtern, die in jedem deutschen Text stehen, matcht alles --
 *   und MySQLs Relevanz-Ranking bevorzugt dann einfach das längste Dokument.
 *   Deshalb kamen für jeden Konzertbericht dieselben fünf sehr langen
 *   Reise-Posts als "related" heraus.
 *
 * Problem 2 -- Code und Shortcode-Ausgabe landen in den Keywords.
 *
 *   YARPP schickt den Body vor dem Tokenisieren durch
 *   apply_filters('the_content', ...). Dabei werden Shortcodes expandiert, also
 *   wandern NextGEN-Galerie-Markup und der Output von SyntaxHighlighter
 *   Evolved (= Quellcode) in die Suchbegriffe.
 *
 * YARPP markiert die Keyword-Phase mit der öffentlichen Methode
 * discovering_keywords(), deshalb greifen die Filter unten ausschließlich dort
 * und ändern nichts an dem, was Besucher sehen.
 * ======================================================================== */

if (!function_exists('sew_claude_music_yarpp_discovering')) {
    /** True, solange YARPP Keywords extrahiert und keine Seite rendert. */
    function sew_claude_music_yarpp_discovering() {
        global $yarpp;
        if (!isset($yarpp) || !is_object($yarpp)) {
            return false;
        }
        // Das Flag sitzt auf dem gerade benutzten Cache-Objekt. $active_cache
        // ist private, deshalb beide öffentlichen prüfen.
        foreach (array('cache', 'cache_bypass') as $property) {
            if (!empty($yarpp->$property) && is_object($yarpp->$property)
                && method_exists($yarpp->$property, 'discovering_keywords')
                && $yarpp->$property->discovering_keywords()) {
                return true;
            }
        }
        return false;
    }
}

/**
 * YARPPs eigene deutsche Stoppwortliste in die tatsächlich benutzte mischen.
 */
add_filter('yarpp_keywords_overused_words', function ($words) {
    static $german = null;

    if ($german === null) {
        $german = array();
        if (defined('YARPP_DIR')) {
            $file = YARPP_DIR . '/lang/words-de_DE.php';
            if (is_readable($file)) {
                $overusedwords = array();
                include_once $file;   // setzt $overusedwords
                if (!empty($overusedwords) && is_array($overusedwords)) {
                    $german = $overusedwords;
                }
            }
        }
    }

    if (empty($german)) {
        return $words;
    }
    return array_values(array_unique(array_merge((array) $words, $german)));
});

/**
 * Code-Blöcke und Shortcode-Ausgabe aus den Keywords heraushalten.
 *
 * Priorität 5 läuft vor do_shortcode (11), Shortcodes werden also entfernt statt
 * expandiert -- sonst würden Galerie-Dateinamen und hervorgehobener Quellcode zu
 * Suchbegriffen.
 */
add_filter('the_content', function ($content) {
    if (!sew_claude_music_yarpp_discovering()) {
        return $content;
    }
    $stripped = preg_replace('#<(pre|code|kbd|samp)\b[^>]*>.*?</\1>#is', ' ', $content);
    if ($stripped !== null) {
        $content = $stripped;
    }
    if (function_exists('strip_shortcodes')) {
        $content = strip_shortcodes($content);
    }
    return $content;
}, 5);

/**
 * SEW About -- server-side rendered landing page.
 *
 * Source of truth is the aboutengelwolfcom repo (plugin/about/), deployed into
 * this plugin's about/ subdirectory by its own `npm run publish`. Guarded so the
 * plugin stays healthy whether or not that module is present.
 */
if (file_exists(__DIR__ . '/about/bootstrap.php')) {
    require_once __DIR__ . '/about/bootstrap.php';
}
