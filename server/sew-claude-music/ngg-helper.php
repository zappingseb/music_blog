<?php
/**
 * NextGEN Gallery import helper for the music_blog publisher.
 *
 * NextGEN keeps galleries in its own tables (ngg_gallery / ngg_pictures), so
 * FTP-ing photos into wp-content/gallery/<slug>/ is not enough -- the plugin has
 * to be told about them. This endpoint bootstraps WordPress and calls NextGEN's
 * own importer, so images register exactly as they would via the admin UI.
 *
 * Teil des Plugins SEW-CLAUDE-MUSIC. Liegt in
 *   wp-content/plugins/sew-claude-music/ngg-helper.php
 * Deploy: python -m musicblog.publish plugin-push
 * Der Token-Platzhalter unten wird dabei durch NGG_HELPER_TOKEN aus der .env ersetzt.
 *
 * Warum eine direkt aufgerufene Datei und keine register_rest_route()-Route:
 * WP_ADMIN muss VOR wp-load.php definiert sein, sonst registriert NextGEN seine
 * Framework-Module nicht und C_Gallery_Storage::generate_thumbnail() stirbt mit
 * "Class C_Frame_Event_Publisher not found". Ein Plugin laedt zu spaet dafuer --
 * NextGEN wird alphabetisch vorher geladen.
 */

define('NGG_HELPER_TOKEN', '@@TOKEN@@');

// NextGEN only registers its framework and storage modules when it believes it
// is in an admin request, and that decision is made while plugins load -- so the
// constant has to be defined before wp-load.php, not after.
if (!defined('WP_ADMIN')) {
    define('WP_ADMIN', true);
}
if (!defined('WP_NETWORK_ADMIN')) {
    define('WP_NETWORK_ADMIN', false);
}
if (!defined('WP_USER_ADMIN')) {
    define('WP_USER_ADMIN', false);
}

// This file lives inside the plugin folder, so walk up until wp-load.php turns
// up. Robust against the plugin being moved or renamed.
$sew_wp_load = null;
$sew_dir     = __DIR__;
for ($sew_i = 0; $sew_i < 6; $sew_i++) {
    if (file_exists($sew_dir . '/wp-load.php')) {
        $sew_wp_load = $sew_dir . '/wp-load.php';
        break;
    }
    $sew_parent = dirname($sew_dir);
    if ($sew_parent === $sew_dir) {
        break;
    }
    $sew_dir = $sew_parent;
}
if ($sew_wp_load === null) {
    http_response_code(500);
    header('Content-Type: application/json; charset=utf-8');
    echo json_encode(array('ok' => false, 'error' => 'wp-load.php not found above ' . __DIR__));
    exit;
}
require_once $sew_wp_load;

header('Content-Type: application/json; charset=utf-8');
header('X-Robots-Tag: noindex, nofollow');

// NextGEN throws plain Exceptions that would otherwise render as an HTML page.
set_exception_handler(function ($exc) {
    http_response_code(500);
    echo json_encode(array(
        'ok'    => false,
        'error' => get_class($exc) . ': ' . $exc->getMessage(),
        'where' => basename($exc->getFile()) . ':' . $exc->getLine(),
    ));
    exit;
});

function helper_fail($message, $status = 400, $extra = array()) {
    http_response_code($status);
    echo json_encode(array_merge(array('ok' => false, 'error' => $message), $extra));
    exit;
}

function helper_ok($payload = array()) {
    echo json_encode(array_merge(array('ok' => true), $payload));
    exit;
}

/** Constant-time token check; the token may arrive as a header or a POST field. */
function helper_authorise() {
    $sent = '';
    if (isset($_SERVER['HTTP_X_NGG_TOKEN'])) {
        $sent = $_SERVER['HTTP_X_NGG_TOKEN'];
    } elseif (isset($_REQUEST['token'])) {
        $sent = $_REQUEST['token'];
    }
    $placeholder = '@' . '@TOKEN' . '@@';
    if (NGG_HELPER_TOKEN === $placeholder || strlen(NGG_HELPER_TOKEN) < 16) {
        helper_fail('helper installed without a token', 500);
    }
    if (!is_string($sent) || !hash_equals(NGG_HELPER_TOKEN, $sent)) {
        helper_fail('forbidden', 403);
    }
}

/** NextGEN's configured gallery directory, relative to the WordPress root. */
function helper_gallery_basedir() {
    if (class_exists('C_NextGen_Settings')) {
        $settings = C_NextGen_Settings::get_instance();
        if (!empty($settings->gallerypath)) {
            return trim(str_replace('\\', '/', $settings->gallerypath), '/');
        }
    }
    return 'wp-content/gallery';
}

/** The legacy nggAdmin class is only auto-loaded in admin context. */
function helper_load_ngg_admin() {
    if (class_exists('nggAdmin')) {
        return true;
    }
    $candidates = array(
        WP_PLUGIN_DIR . '/nextgen-gallery/products/photocrati_nextgen/modules/ngglegacy/admin/functions.php',
    );
    foreach ((array) glob(WP_PLUGIN_DIR . '/*/products/photocrati_nextgen/modules/ngglegacy/admin/functions.php') as $match) {
        $candidates[] = $match;
    }
    foreach ($candidates as $path) {
        if (file_exists($path)) {
            foreach (array('file.php', 'image.php', 'media.php') as $include) {
                require_once ABSPATH . 'wp-admin/includes/' . $include;
            }
            require_once $path;
            if (class_exists('nggAdmin')) {
                return true;
            }
        }
    }
    return false;
}

function helper_ngg_version() {
    if (defined('NGG_PLUGIN_VERSION')) {
        return NGG_PLUGIN_VERSION;
    }
    if (class_exists('C_NextGEN_Bootstrap') && defined('NGG_PLUGIN_BASENAME')) {
        return 'unknown (bootstrap present)';
    }
    return null;
}

/** Sanitise a gallery folder name: no traversal, no surprises. */
function helper_clean_folder($raw) {
    $folder = basename(trim((string) $raw, "/ \t\n\r"));
    if ($folder === '' || !preg_match('/^[A-Za-z0-9][A-Za-z0-9._-]*$/', $folder)) {
        helper_fail('invalid folder name: ' . $raw);
    }
    return $folder;
}

function helper_find_gallery($folder) {
    if (!class_exists('C_Gallery_Mapper')) {
        return null;
    }
    $mapper = C_Gallery_Mapper::get_instance();
    foreach ((array) $mapper->find_all() as $gallery) {
        $name = isset($gallery->name) ? $gallery->name : '';
        $path = isset($gallery->path) ? rtrim(str_replace('\\', '/', $gallery->path), '/') : '';
        if ($name === $folder || substr($path, -strlen('/' . $folder)) === '/' . $folder) {
            return $gallery;
        }
    }
    return null;
}

function helper_count_images($gallery_id) {
    global $wpdb;
    return (int) $wpdb->get_var($wpdb->prepare(
        "SELECT COUNT(*) FROM {$wpdb->prefix}ngg_pictures WHERE galleryid = %d",
        $gallery_id
    ));
}

/** Image files actually sitting in the gallery directory. */
function helper_disk_files($abspath) {
    $files = array();
    foreach ((array) glob($abspath . '/*') as $path) {
        if (is_file($path) && preg_match('/\.(jpe?g|png|gif)$/i', $path)) {
            $files[] = basename($path);
        }
    }
    return $files;
}

global $wpdb;

/**
 * Generate the static admin thumbnails (thumbs/thumbs_<file>.jpg).
 *
 * nggAdmin::import_gallery() registers the database rows but does not build
 * thumbnails, so the gallery admin shows broken images until this runs.
 */
function helper_thumb_settings() {
    $width = 120;
    $height = 90;
    $crop = true;
    if (class_exists('C_NextGen_Settings')) {
        $settings = C_NextGen_Settings::get_instance();
        if (!empty($settings->thumbwidth)) {
            $width = (int) $settings->thumbwidth;
        }
        if (!empty($settings->thumbheight)) {
            $height = (int) $settings->thumbheight;
        }
        if (isset($settings->thumbfix)) {
            $crop = (bool) $settings->thumbfix;
        }
    }
    return array($width, $height, $crop);
}

/** Write thumbs/thumbs_<file> directly, bypassing NextGEN's storage module. */
function helper_thumb_fallback($abspath, $filename) {
    list($width, $height, $crop) = helper_thumb_settings();
    $source = $abspath . '/' . $filename;
    if (!is_file($source)) {
        return 'source missing';
    }
    $dir = $abspath . '/thumbs';
    if (!is_dir($dir) && !wp_mkdir_p($dir)) {
        return 'cannot create thumbs/';
    }
    $editor = wp_get_image_editor($source);
    if (is_wp_error($editor)) {
        return 'editor: ' . $editor->get_error_message();
    }
    $resized = $editor->resize($width, $height, $crop);
    if (is_wp_error($resized)) {
        return 'resize: ' . $resized->get_error_message();
    }
    $saved = $editor->save($dir . '/thumbs_' . $filename);
    if (is_wp_error($saved)) {
        return 'save: ' . $saved->get_error_message();
    }
    return true;
}

function helper_generate_thumbnails($gallery_id) {
    global $wpdb;
    $rows = $wpdb->get_results($wpdb->prepare(
        "SELECT pid, filename FROM {$wpdb->prefix}ngg_pictures WHERE galleryid = %d ORDER BY pid",
        $gallery_id
    ));
    $gallery = $wpdb->get_row($wpdb->prepare(
        "SELECT path FROM {$wpdb->prefix}ngg_gallery WHERE gid = %d", $gallery_id
    ));
    $abspath = rtrim(ABSPATH, '/') . '/' . trim($gallery ? $gallery->path : '', '/');

    list($tw, $th, $crop) = helper_thumb_settings();
    $result = array(
        'total' => count($rows), 'generated' => 0, 'via_storage' => 0,
        'via_fallback' => 0, 'failed' => array(),
        'size' => $tw . 'x' . $th . ($crop ? ' (cropped)' : ' (fit)'),
    );

    $storage = class_exists('C_Gallery_Storage') ? C_Gallery_Storage::get_instance() : null;
    foreach ($rows as $row) {
        $pid = (int) $row->pid;
        $ok = false;
        $why = '';
        if ($storage) {
            ob_start();
            try {
                $ok = (bool) $storage->generate_thumbnail($pid);
            } catch (Throwable $exc) {
                $ok = false;
                $why = $exc->getMessage();
            }
            ob_end_clean();
            if ($ok) {
                $result['generated']++;
                $result['via_storage']++;
                continue;
            }
        }
        // NextGEN's storage module is not usable here; write the thumbnail directly.
        $fallback = helper_thumb_fallback($abspath, $row->filename);
        if ($fallback === true) {
            $result['generated']++;
            $result['via_fallback']++;
        } else {
            $result['failed'][] = $pid . ': ' . $fallback . ($why ? ' (storage: ' . $why . ')' : '');
        }
    }
    return $result;
}

helper_authorise();

$action = isset($_REQUEST['action']) ? $_REQUEST['action'] : 'ping';
$basedir = helper_gallery_basedir();

if ($action === 'ping' || $action === 'info') {
    helper_ok(array(
        'wp_version'      => get_bloginfo('version'),
        'ngg_version'     => helper_ngg_version(),
        'ngg_admin'       => helper_load_ngg_admin(),
        'gallery_basedir' => $basedir,
        'gallery_abspath' => rtrim(ABSPATH, '/') . '/' . $basedir,
        'abspath'         => ABSPATH,
        'php_version'     => PHP_VERSION,
        'thumb_settings'  => helper_thumb_settings(),
    ));
}

if ($action === 'yarpp') {
    // Read-only diagnostics for Yet Another Related Posts Plugin. YARPP scores
    // relatedness using MySQL FULLTEXT indexes it adds to wp_posts; if those
    // are missing its title/body weights silently contribute nothing and the
    // same handful of posts come back for every reference.
    $post_id = isset($_REQUEST['post']) ? (int) $_REQUEST['post'] : 0;
    $out = array();
    $out['yarpp_version'] = defined('YARPP_VERSION') ? YARPP_VERSION
        : (class_exists('YARPP') ? 'class present, version constant missing' : null);
    $out['settings'] = get_option('yarpp');

    $indexes = $wpdb->get_results("SHOW INDEX FROM {$wpdb->posts}", ARRAY_A);
    $fulltext = array();
    foreach ((array) $indexes as $row) {
        if (isset($row['Index_type']) && strtoupper($row['Index_type']) === 'FULLTEXT') {
            $fulltext[$row['Key_name']][] = $row['Column_name'];
        }
    }
    $out['fulltext_indexes'] = $fulltext;

    $status = $wpdb->get_row("SHOW TABLE STATUS LIKE '{$wpdb->posts}'", ARRAY_A);
    $out['posts_engine'] = $status ? $status['Engine'] : null;
    $out['mysql_version'] = $wpdb->get_var('SELECT VERSION()');

    $cache = $wpdb->prefix . 'yarpp_related_cache';
    $out['cache_table'] = $wpdb->get_var($wpdb->prepare('SHOW TABLES LIKE %s', $cache)) ? $cache : 'MISSING';
    if ($out['cache_table'] !== 'MISSING') {
        $out['cache_rows'] = (int) $wpdb->get_var("SELECT COUNT(*) FROM $cache");
        $out['cache_references'] = (int) $wpdb->get_var("SELECT COUNT(DISTINCT reference_ID) FROM $cache");
        $out['cache_score_stats'] = $wpdb->get_row(
            "SELECT MIN(score) AS min_score, MAX(score) AS max_score, ROUND(AVG(score),3) AS avg_score FROM $cache",
            ARRAY_A
        );
        // If a few post IDs are returned for nearly every reference, that is
        // exactly the "always the same related posts" symptom.
        $out['most_returned'] = $wpdb->get_results(
            "SELECT c.ID, COUNT(*) AS times, p.post_title
               FROM $cache c LEFT JOIN {$wpdb->posts} p ON p.ID = c.ID
              WHERE c.ID > 0 GROUP BY c.ID, p.post_title ORDER BY times DESC LIMIT 10",
            ARRAY_A
        );
        if ($post_id) {
            $out['cache_for_post'] = $wpdb->get_results($wpdb->prepare(
                "SELECT c.ID, c.score, p.post_title FROM $cache c
                   LEFT JOIN {$wpdb->posts} p ON p.ID = c.ID
                  WHERE c.reference_ID = %d ORDER BY c.score DESC LIMIT 12", $post_id
            ), ARRAY_A);
        }
    }
    helper_ok($out);
}

if ($action === 'yarpp_related') {
    // Recompute YARPP relatedness for specific posts, bypassing the cache, so
    // "always the same related posts" can be confirmed or ruled out.
    $ids = array_filter(array_map('intval', explode(',', isset($_REQUEST['posts']) ? $_REQUEST['posts'] : '')));
    $limit = isset($_REQUEST['limit']) ? (int) $_REQUEST['limit'] : 5;
    $yarpp = isset($GLOBALS['yarpp']) && is_object($GLOBALS['yarpp']) ? $GLOBALS['yarpp'] : null;

    $out = array(
        'have_function' => function_exists('yarpp_get_related'),
        'have_object'   => (bool) $yarpp,
        'total_published' => (int) $wpdb->get_var(
            "SELECT COUNT(*) FROM {$wpdb->posts} WHERE post_type='post' AND post_status='publish'"),
        'results' => array(),
    );

    foreach ($ids as $id) {
        if ($yarpp && isset($yarpp->cache) && method_exists($yarpp->cache, 'clear')) {
            try { $yarpp->cache->clear($id); } catch (Throwable $e) {}
        }
        $row = array(
            'title'      => get_the_title($id),
            'word_count' => str_word_count(wp_strip_all_tags(get_post_field('post_content', $id))),
            'tags'       => wp_get_post_tags($id, array('fields' => 'names')),
            'related'    => array(),
        );
        // Optional overrides so a proposed configuration can be tried out
        // without touching the stored YARPP settings.
        $args = array('limit' => $limit, 'post_type' => array('post'));
        if (isset($_REQUEST['tag_weight'])) {
            $args['weight'] = array(
                'title' => isset($_REQUEST['title_weight']) ? (int) $_REQUEST['title_weight'] : 1,
                'body'  => isset($_REQUEST['body_weight'])  ? (int) $_REQUEST['body_weight']  : 1,
                'tax'   => array('post_tag' => (int) $_REQUEST['tag_weight']),
            );
        }
        if (!empty($_REQUEST['require_tag'])) {
            $args['require_tax'] = array('post_tag' => (int) $_REQUEST['require_tag']);
        }
        try {
            $related = function_exists('yarpp_get_related')
                ? yarpp_get_related($args, $id)
                : array();
            foreach ((array) $related as $r) {
                $row['related'][] = array(
                    'ID'    => $r->ID,
                    'title' => $r->post_title,
                    'score' => isset($r->score) ? $r->score : null,
                );
            }
        } catch (Throwable $e) {
            $row['error'] = get_class($e) . ': ' . $e->getMessage();
        }
        $out['results'][$id] = $row;
    }
    helper_ok($out);
}

if ($action === 'fulltext') {
    // Probe the FULLTEXT indexes YARPP relies on, directly. If a term that
    // clearly appears in recent posts returns only old ones, the index is not
    // covering the newer rows and YARPP's body/title weights are worthless.
    $term = isset($_REQUEST['term']) ? (string) $_REQUEST['term'] : 'Konzert';
    $out = array('term' => $term);

    $out['content_matches'] = $wpdb->get_results($wpdb->prepare(
        "SELECT ID, post_title, post_date,
                MATCH(post_content) AGAINST (%s) AS score,
                CHAR_LENGTH(post_content) AS chars
           FROM {$wpdb->posts}
          WHERE post_type='post' AND post_status='publish'
            AND MATCH(post_content) AGAINST (%s) > 0
          ORDER BY score DESC LIMIT 10", $term, $term), ARRAY_A);

    $out['title_matches'] = $wpdb->get_results($wpdb->prepare(
        "SELECT ID, post_title, MATCH(post_title) AGAINST (%s) AS score
           FROM {$wpdb->posts}
          WHERE post_type='post' AND post_status='publish'
            AND MATCH(post_title) AGAINST (%s) > 0
          ORDER BY score DESC LIMIT 10", $term, $term), ARRAY_A);

    // Plain LIKE for comparison: how many posts really contain the term?
    $out['like_count'] = (int) $wpdb->get_var($wpdb->prepare(
        "SELECT COUNT(*) FROM {$wpdb->posts}
          WHERE post_type='post' AND post_status='publish' AND post_content LIKE %s",
        '%' . $wpdb->esc_like($term) . '%'));

    // The posts that dominate every result: how big are they?
    $ids = isset($_REQUEST['sizes']) ? array_filter(array_map('intval', explode(',', $_REQUEST['sizes']))) : array();
    if ($ids) {
        $in = implode(',', $ids);
        $out['sizes'] = $wpdb->get_results(
            "SELECT ID, post_title, post_date, CHAR_LENGTH(post_content) AS chars,
                    ROUND(CHAR_LENGTH(post_content)/5) AS approx_words
               FROM {$wpdb->posts} WHERE ID IN ($in)", ARRAY_A);
    }
    $out['newest_indexed_guess'] = $wpdb->get_var(
        "SELECT MAX(post_date) FROM {$wpdb->posts} WHERE post_type='post' AND post_status='publish'");
    helper_ok($out);
}

if ($action === 'yarpp_keywords') {
    // Ground truth: what does YARPP actually search for? title_keywords() and
    // body_keywords() are protected, so reach them via reflection rather than
    // guessing from the source.
    $ids = array_filter(array_map('intval', explode(',', isset($_REQUEST['posts']) ? $_REQUEST['posts'] : '')));
    $yarpp = isset($GLOBALS['yarpp']) && is_object($GLOBALS['yarpp']) ? $GLOBALS['yarpp'] : null;
    $out = array(
        'wplang_defined' => defined('WPLANG') ? (string) WPLANG : false,
        'get_locale'     => get_locale(),
        'stopword_file_for_de' => defined('YARPP_DIR')
            ? (file_exists(YARPP_DIR . '/lang/words-de_DE.php') ? 'vorhanden' : 'fehlt') : 'YARPP_DIR unbekannt',
        'stopword_file_used'   => defined('YARPP_DIR')
            ? (file_exists(YARPP_DIR . '/lang/words-en_US.php') ? 'words-en_US.php (Fallback)' : 'keine') : '?',
    );
    if (!$yarpp || !isset($yarpp->cache)) {
        helper_fail('YARPP cache object not reachable', 500, $out);
    }
    $ref = new ReflectionClass($yarpp->cache);
    foreach (array('title_keywords', 'body_keywords') as $method) {
        if (!$ref->hasMethod($method)) { $out['missing_method'][] = $method; }
    }
    foreach ($ids as $id) {
        $row = array();
        foreach (array('title_keywords', 'body_keywords') as $method) {
            try {
                $m = $ref->getMethod($method);
                $m->setAccessible(true);
                $row[$method] = $m->invoke($yarpp->cache, $id, 20);
            } catch (Throwable $e) {
                $row[$method] = 'ERROR: ' . $e->getMessage();
            }
        }
        $out['posts'][$id] = $row;
    }
    helper_ok($out);
}

if ($action === 'thumbnails') {
    $folder = helper_clean_folder(isset($_REQUEST['folder']) ? $_REQUEST['folder'] : '');
    if (!helper_load_ngg_admin()) {
        helper_fail('NextGEN Gallery not found (nggAdmin unavailable)', 500);
    }
    $gallery = helper_find_gallery($folder);
    if (!$gallery) {
        helper_fail('no gallery registered for folder ' . $folder, 404);
    }
    helper_ok(array(
        'gallery_id' => (int) $gallery->gid,
        'thumbnails' => helper_generate_thumbnails((int) $gallery->gid),
    ));
}

if ($action !== 'import') {
    helper_fail('unknown action: ' . $action);
}

$method = isset($_SERVER['REQUEST_METHOD']) ? strtoupper($_SERVER['REQUEST_METHOD']) : 'GET';
if ($method !== 'POST') {
    helper_fail('import requires POST', 405);
}

$folder = helper_clean_folder(isset($_REQUEST['folder']) ? $_REQUEST['folder'] : '');
$title  = isset($_REQUEST['title']) && $_REQUEST['title'] !== '' ? (string) $_REQUEST['title'] : $folder;
$relpath = $basedir . '/' . $folder;
$abspath = rtrim(ABSPATH, '/') . '/' . $relpath;

if (!is_dir($abspath)) {
    helper_fail('gallery folder not found on disk: ' . $relpath, 404);
}
if (!helper_load_ngg_admin()) {
    helper_fail('NextGEN Gallery not found (nggAdmin unavailable)', 500,
        array('ngg_version' => helper_ngg_version()));
}

$notes = array();
$gallery = helper_find_gallery($folder);
$gallery_id = $gallery ? (int) $gallery->gid : 0;

if ($gallery_id) {
    $notes[] = 'reused existing gallery';
} elseif (class_exists('C_Gallery_Mapper')) {
    // Create the record up front so the id is known even if the importer
    // returns something falsy. The mapper rejects plain arrays
    // (E_InvalidEntityException), so build an entity via create() and fall back
    // to an stdClass cast on versions without it.
    $mapper = C_Gallery_Mapper::get_instance();
    $properties = array(
        'title'      => $title,
        'name'       => $folder,
        'path'       => $relpath,
        'author'     => get_current_user_id(),
        'previewpic' => 0,
    );
    if (method_exists($mapper, 'create')) {
        $entity = $mapper->create($properties);
        $notes[] = 'built entity via C_Gallery_Mapper::create()';
    } else {
        $entity = (object) $properties;
        $notes[] = 'built entity via stdClass cast';
    }
    $created = $mapper->save($entity);
    if (is_object($created)) {
        $gallery_id = (int) $created->gid;
    } elseif (is_numeric($created)) {
        $gallery_id = (int) $created;
    } elseif (is_object($entity) && !empty($entity->gid)) {
        $gallery_id = (int) $entity->gid;
    } else {
        $gallery_id = 0;
    }
    if (!$gallery_id) {
        helper_fail('could not create gallery record for ' . $folder, 500);
    }
    $notes[] = 'created gallery record';
}

// import_gallery() has taken both relative and absolute paths across NextGEN
// versions, so try both and keep whichever reports success.
$notes[] = 'disk files: ' . implode(', ', helper_disk_files($abspath));
$notes[] = 'registered before import: ' . helper_count_images($gallery_id);

// NextGEN has taken the bare folder name, an ABSPATH-relative path and an
// absolute path across versions, so try each and keep whichever registers rows.
$imported = false;
foreach (array($folder, $relpath, $abspath) as $candidate) {
    $before = helper_count_images($gallery_id);
    ob_start();  // import_gallery() echoes its own HTML status markup
    try {
        $result = nggAdmin::import_gallery($candidate, $gallery_id ?: null);
        $echoed = trim(preg_replace('/\s+/', ' ', strip_tags(ob_get_clean())));
    } catch (Throwable $exc) {
        ob_end_clean();
        $notes[] = 'import_gallery(' . $candidate . ') threw: ' . $exc->getMessage();
        continue;
    }
    $after = helper_count_images($gallery_id);
    $notes[] = 'import_gallery(' . $candidate . ') -> ' . var_export($result, true)
        . ' | rows ' . $before . '->' . $after
        . ' | echoed: ' . ($echoed === '' ? '(nothing)' : $echoed)
        . ($wpdb->last_error ? ' | db error: ' . $wpdb->last_error : '');
    if ($after > $before) {
        $imported = true;
        if (is_numeric($result)) {
            $gallery_id = (int) $result;
        }
        break;
    }
}

if (!$gallery_id) {
    $found = helper_find_gallery($folder);
    $gallery_id = $found ? (int) $found->gid : 0;
}
if (!$gallery_id) {
    helper_fail('import failed for ' . $relpath, 500, array('notes' => $notes));
}

$count = helper_count_images($gallery_id);
if (!$imported && !$count) {
    helper_fail('gallery ' . $gallery_id . ' has no registered images', 500, array('notes' => $notes));
}

$thumbnails = helper_generate_thumbnails($gallery_id);

helper_ok(array(
    'gallery_id' => $gallery_id,
    'folder'     => $folder,
    'path'       => $relpath,
    'images'     => $count,
    'thumbnails' => $thumbnails,
    'notes'      => $notes,
));
