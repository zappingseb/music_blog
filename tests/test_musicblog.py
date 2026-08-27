"""Unit tests: python -m unittest discover -s tests -v"""

from __future__ import annotations

import os
import tempfile
import unittest
import unittest.mock
from pathlib import Path

from PIL import Image

from musicblog import bericht, blocks, config, images

REPO = Path(__file__).resolve().parent.parent
REFERENCE_PLAIN = REPO / "19.jpg"
REFERENCE_GREEN = REPO / "19_g.jpg"
SAMPLE = REPO / "konzerte" / "joss_stone"


class TestConfig(unittest.TestCase):
    def test_split_host_strips_scheme(self):
        self.assertEqual(config._split_host("ftp://203.0.113.10"), ("203.0.113.10", 21))
        self.assertEqual(config._split_host("ftps://example.com/"), ("example.com", 21))
        self.assertEqual(config._split_host("example.com:2121"), ("example.com", 2121))

    def test_accepts_both_dimension_spellings(self):
        """The .env mixes 'dimension_height' with 'dimensions_width'."""
        env = {
            "WP_URL": "https://example.com/", "WP_USER": "admin", "WP_PWD": "x",
            "WP_gallery_dimension_height": "194", "WP_gallery_dimensions_width": "830",
            "FTP_IP": "ftp://1.2.3.4", "FTP_USER": "u", "FTP_PWD": "p", "FTP_FOLDER": "public_html",
        }
        with unittest.mock.patch.dict(os.environ, env, clear=True):
            with tempfile.TemporaryDirectory() as tmp:
                loaded = config.load(Path(tmp) / "absent.env")
        self.assertEqual((loaded.header_width, loaded.header_height), (830, 194))
        self.assertEqual(loaded.wp_url, "https://example.com")  # trailing slash removed
        self.assertEqual(loaded.ftp_host, "1.2.3.4")
        self.assertEqual(loaded.helper_token, "")  # optional, only the helper needs it

        # Swapped spellings must work just as well.
        env["WP_gallery_dimensions_height"] = env.pop("WP_gallery_dimension_height")
        env["WP_gallery_dimension_width"] = env.pop("WP_gallery_dimensions_width")
        with unittest.mock.patch.dict(os.environ, env, clear=True):
            with tempfile.TemporaryDirectory() as tmp:
                loaded = config.load(Path(tmp) / "absent.env")
        self.assertEqual((loaded.header_width, loaded.header_height), (830, 194))

    def test_missing_key_names_both_spellings(self):
        with unittest.mock.patch.dict(os.environ, {}, clear=True):
            with tempfile.TemporaryDirectory() as tmp:
                with self.assertRaises(config.ConfigError) as caught:
                    config.load(Path(tmp) / "absent.env")
        message = str(caught.exception)
        # Every missing key is listed, not just the first one encountered.
        for key in ("WP_URL", "WP_PWD", "FTP_IP", "FTP_FOLDER"):
            self.assertIn(key, message)


class TestBericht(unittest.TestCase):
    def test_parses_the_sample_format(self):
        report = bericht.parse(
            "# Joss Stone live Tollwood München\n\n- date: 2026-07-13\n\n# Bericht\n\nWow, toll.\n"
        )
        self.assertEqual(report.title, "Joss Stone live Tollwood München")
        self.assertEqual(report.wp_date, "2026-07-13T00:00:00")
        self.assertEqual(report.body, "Wow, toll.")
        self.assertEqual(report.slug, "joss-stone-live-tollwood-muenchen")

    def test_keeps_a_real_content_heading(self):
        report = bericht.parse("# T\n\n- date: 2026-01-02\n\n## Setlist\n\n1. Song\n")
        self.assertTrue(report.body.startswith("## Setlist"))

    def test_extra_metadata(self):
        report = bericht.parse(
            "# T\n\n- date: 13.07.2026 20:30\n- tags: tollwood, soul\n- slug: custom-slug\n\n# Bericht\n\nx\n"
        )
        self.assertEqual(report.wp_date, "2026-07-13T20:30:00")
        self.assertEqual(report.extra_tags, ["tollwood", "soul"])
        self.assertEqual(report.slug, "custom-slug")

    def test_missing_date_and_title_are_errors(self):
        with self.assertRaises(bericht.BerichtError):
            bericht.parse("# T\n\nno date bullet\n")
        with self.assertRaises(bericht.BerichtError):
            bericht.parse("just prose, no heading\n")
        with self.assertRaises(bericht.BerichtError):
            bericht.parse("# T\n\n- date: not-a-date\n")

    def test_slugify_transliterates_german(self):
        self.assertEqual(bericht.slugify("Größe & Spaß in Köln"), "groesse-und-spass-in-koeln")
        self.assertEqual(bericht.slugify("AC/DC -- München!"), "ac-dc-muenchen")

    @unittest.skipUnless(SAMPLE.is_dir(), "sample concert folder absent")
    def test_loads_the_real_sample(self):
        report = bericht.load(SAMPLE)
        self.assertEqual(report.slug, "joss-stone-live-tollwood-muenchen")


class TestBlocks(unittest.TestCase):
    def test_paragraph_and_heading(self):
        out = blocks.render("Hallo **Welt**\n\n## Setlist\n")
        self.assertIn("<!-- wp:paragraph -->", out)
        self.assertIn("<strong>Welt</strong>", out)
        self.assertIn('<h2 class="wp-block-heading">Setlist</h2>', out)

    def test_h1_is_demoted_because_the_title_owns_h1(self):
        out = blocks.render("# Zwischentitel\n")
        self.assertIn("<h2", out)
        self.assertNotIn("<h1", out)

    def test_lists_get_list_item_blocks(self):
        out = blocks.render("1. eins\n2. zwei\n")
        self.assertIn('<!-- wp:list {"ordered":true} -->', out)
        self.assertEqual(out.count("<!-- wp:list-item -->"), 2)

    def test_unknown_html_falls_back_to_wp_html(self):
        out = blocks.render('<div class="x">raw</div>\n')
        self.assertIn("<!-- wp:html -->", out)
        self.assertIn('<div class="x">raw</div>', out)

    def test_empty_body(self):
        self.assertEqual(blocks.render("   \n"), "")

    def test_shortcode_is_appended_once_and_is_idempotent(self):
        body = blocks.render("Text\n")
        once = blocks.set_gallery_shortcode(body, 12)
        twice = blocks.set_gallery_shortcode(once, 12)
        self.assertEqual(once, twice)
        self.assertEqual(twice.count("[ngg"), 1)
        self.assertTrue(twice.rstrip().endswith("<!-- /wp:shortcode -->"))

    def test_shortcode_id_is_replaced_not_duplicated(self):
        body = blocks.set_gallery_shortcode(blocks.render("Text\n"), 12)
        updated = blocks.set_gallery_shortcode(body, 34)
        self.assertEqual(updated.count("[ngg"), 1)
        self.assertIn('ids="34"', updated)
        self.assertIn("<!-- wp:paragraph -->", updated)  # body survived


class TestEmbeds(unittest.TestCase):
    URL = "https://www.youtube.com/watch?v=AIaQpH-ageY"

    def test_bare_url_on_its_own_line_becomes_an_embed(self):
        out = blocks.render(f"Davor.\n\n{self.URL}\n\nDanach.")
        self.assertIn("<!-- wp:embed ", out)
        self.assertIn('"providerNameSlug":"youtube"', out)
        self.assertIn('"type":"video"', out)
        self.assertIn('"responsive":true', out)
        self.assertIn("wp-embed-aspect-16-9", out)
        self.assertIn("is-provider-youtube", out)
        self.assertIn(self.URL, out)
        # The surrounding prose is untouched.
        self.assertEqual(out.count("<!-- wp:paragraph -->"), 2)

    def test_short_and_angle_bracket_forms(self):
        for markdown_text in ("https://youtu.be/AIaQpH-ageY", f"<{self.URL}>"):
            self.assertIn("<!-- wp:embed ", blocks.render(markdown_text), markdown_text)

    def test_url_inside_a_sentence_stays_text(self):
        out = blocks.render(f"Schaut mal {self.URL} an.")
        self.assertNotIn("wp:embed", out)
        self.assertIn("<!-- wp:paragraph -->", out)

    def test_unsupported_host_stays_a_paragraph(self):
        out = blocks.render("https://engel-wolf.com/irgendwas")
        self.assertNotIn("wp:embed", out)
        self.assertIn("<!-- wp:paragraph -->", out)

    def test_provider_matching_covers_subdomains_and_www(self):
        for url, slug in [
            ("https://youtube.com/watch?v=x", "youtube"),
            ("https://www.youtube.com/watch?v=x", "youtube"),
            ("https://m.youtube.com/watch?v=x", "youtube"),
            ("https://youtu.be/x", "youtube"),
            ("https://vimeo.com/123", "vimeo"),
            ("https://open.spotify.com/track/x", "spotify"),
            ("https://soundcloud.com/a/b", "soundcloud"),
            ("https://artist.bandcamp.com/album/x", "bandcamp"),
        ]:
            match = blocks.embed_provider(url)
            self.assertIsNotNone(match, url)
            self.assertEqual(match[0], slug, url)
        self.assertIsNone(blocks.embed_provider("https://example.com/x"))
        self.assertIsNone(blocks.embed_block("https://example.com/x"))

    def test_non_video_providers_get_no_aspect_ratio(self):
        out = blocks.embed_block("https://open.spotify.com/track/x")
        self.assertIn('"type":"rich"', out)
        self.assertNotIn("wp-embed-aspect", out)

    def test_raw_iframe_still_passes_through_as_html(self):
        out = blocks.render('<iframe src="https://www.youtube.com/embed/x"></iframe>')
        self.assertIn("<!-- wp:html -->", out)
        self.assertIn("<iframe", out)

    def test_gallery_shortcode_appends_after_an_embed(self):
        body = blocks.render(f"Text.\n\n{self.URL}")
        final = blocks.set_gallery_shortcode(body, 104)
        self.assertEqual(final.count("[ngg"), 1)
        self.assertIn("<!-- wp:embed ", final)
        self.assertEqual(final, blocks.set_gallery_shortcode(final, 104))


class TestGeometry(unittest.TestCase):
    def test_default_box_matches_the_target_ratio(self):
        aspect = 830 / 194
        left, top, right, bottom = images.default_crop_box((4080, 3072), aspect)
        self.assertEqual((left, right), (0, 4080))  # full width fits
        self.assertAlmostEqual((right - left) / (bottom - top), aspect, places=2)
        self.assertGreaterEqual(top, 0)
        self.assertLessEqual(bottom, 3072)

    def test_default_box_falls_back_to_full_height(self):
        """When full width would overflow the image, height becomes the constraint."""
        left, top, right, bottom = images.default_crop_box((400, 100), 0.5)
        self.assertEqual((top, bottom), (0, 100))  # height maxed out
        self.assertEqual(right - left, 50)
        self.assertAlmostEqual((right - left) / (bottom - top), 0.5, places=2)

    def test_clamp_keeps_the_box_inside_the_image(self):
        self.assertEqual(images.clamp_box((-50, -50, 5000, 5000), (100, 80)), (0, 0, 100, 80))
        left, top, right, bottom = images.clamp_box((99, 79, 99, 79), (100, 80))
        self.assertGreater(right, left)
        self.assertGreater(bottom, top)

    def test_crop_and_resize_hits_the_exact_target(self):
        source = Image.new("RGB", (4080, 3072), (10, 20, 30))
        out = images.crop_and_resize(source, (0, 706, 4080, 1660), (830, 194))
        self.assertEqual(out.size, (830, 194))


class TestGreenDuotone(unittest.TestCase):
    def test_lightness_is_max_plus_min_over_two(self):
        source = Image.new("RGB", (1, 1), (200, 100, 50))
        self.assertEqual(images.hsl_lightness(source).getpixel((0, 0)), 125)

    def test_output_is_green_dominant_and_preserves_size(self):
        source = Image.new("RGB", (8, 8), (128, 128, 128))
        out = images.green_duotone(source)
        red, green, blue = out.getpixel((0, 0))
        self.assertEqual(out.size, (8, 8))
        self.assertGreater(green, red)
        self.assertGreater(red, blue)

    def test_extremes_clip_rather_than_wrap(self):
        for colour in ((0, 0, 0), (255, 255, 255)):
            for channel in images.green_duotone(Image.new("RGB", (2, 2), colour)).getpixel((0, 0)):
                self.assertGreaterEqual(channel, 0)
                self.assertLessEqual(channel, 255)

    @unittest.skipUnless(
        REFERENCE_PLAIN.is_file() and REFERENCE_GREEN.is_file(),
        "reference pair 19.jpg / 19_g.jpg not present (both are gitignored)",
    )
    def test_matches_the_theme_reference_pair(self):
        """The one piece of this pipeline with a ground truth to check against."""
        plain = images.load_rgb(REFERENCE_PLAIN)
        expected = images.load_rgb(REFERENCE_GREEN)
        error = images.mean_abs_error(images.green_duotone(plain), expected)
        self.assertLess(error, 5.0, f"green duotone drifted: {error:.3f}/255 mean abs error")

    def test_mean_channels_and_looks_green(self):
        self.assertEqual(images.mean_channels(Image.new("RGB", (4, 4), (10, 20, 30))), (10.0, 20.0, 30.0))
        self.assertTrue(images.looks_green(images.green_duotone(Image.new("RGB", (4, 4), (128, 128, 128)))))
        # A _g file that is really a copy of the colour original is not green.
        self.assertFalse(images.looks_green(Image.new("RGB", (4, 4), (200, 40, 90))))

    def test_looks_green_on_the_reference_pair(self):
        if not (REFERENCE_PLAIN.is_file() and REFERENCE_GREEN.is_file()):
            self.skipTest("reference pair not present")
        self.assertTrue(images.looks_green(images.load_rgb(REFERENCE_GREEN)))
        self.assertFalse(images.looks_green(images.load_rgb(REFERENCE_PLAIN)))

    def test_mean_abs_error_rejects_size_mismatch(self):
        with self.assertRaises(ValueError):
            images.mean_abs_error(Image.new("RGB", (2, 2)), Image.new("RGB", (3, 3)))


class TestConcertDate(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.folder = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)

    def _photo(self, name: str, taken: str | None) -> Path:
        path = self.folder / name
        image = Image.new("RGB", (16, 12), (7, 8, 9))
        kwargs = {}
        if taken:
            exif = image.getexif()
            exif.get_ifd(0x8769)[0x9003] = taken  # ExifIFD / DateTimeOriginal
            kwargs["exif"] = exif.tobytes()
        image.save(path, "JPEG", **kwargs)
        return path

    def test_parse_exif_datetime(self):
        self.assertEqual(
            images.parse_exif_datetime("2026:07:13 20:24:10"),
            __import__("datetime").datetime(2026, 7, 13, 20, 24, 10),
        )
        self.assertIsNone(images.parse_exif_datetime("nonsense"))

    def test_shot_at_reads_the_tag_back(self):
        path = self._photo("a.jpg", "2026:07:13 20:24:10")
        self.assertEqual(images.shot_at(path), "2026:07:13 20:24:10")

    def test_evening_photos(self):
        paths = [self._photo("a.jpg", "2026:07:13 20:24:10"),
                 self._photo("b.jpg", "2026:07:13 21:41:59")]
        self.assertEqual(images.concert_date(paths).isoformat(), "2026-07-13")

    def test_after_midnight_counts_toward_the_previous_evening(self):
        """A shot at 01:30 belongs to the gig that started the night before."""
        paths = [self._photo("a.jpg", "2026:07:13 23:50:00"),
                 self._photo("b.jpg", "2026:07:14 00:20:00"),
                 self._photo("c.jpg", "2026:07:14 01:30:00")]
        self.assertEqual(images.concert_date(paths).isoformat(), "2026-07-13")

    def test_all_photos_after_midnight(self):
        paths = [self._photo("a.jpg", "2026:07:14 00:10:00"),
                 self._photo("b.jpg", "2026:07:14 01:05:00")]
        self.assertEqual(images.concert_date(paths).isoformat(), "2026-07-13")

    def test_majority_night_wins_over_a_stray_photo(self):
        paths = [self._photo("a.jpg", "2026:07:13 20:00:00"),
                 self._photo("b.jpg", "2026:07:13 21:00:00"),
                 self._photo("stray.jpg", "2026:06:01 12:00:00")]
        self.assertEqual(images.concert_date(paths).isoformat(), "2026-07-13")

    def test_tie_prefers_the_earlier_night(self):
        paths = [self._photo("a.jpg", "2026:07:13 20:00:00"),
                 self._photo("b.jpg", "2026:07:20 20:00:00")]
        self.assertEqual(images.concert_date(paths).isoformat(), "2026-07-13")

    def test_no_exif_returns_none(self):
        self.assertIsNone(images.concert_date([self._photo("a.jpg", None)]))
        self.assertIsNone(images.concert_date([]))


class TestDiscoveryAndPreparation(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.folder = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)

    def _write(self, relative: str, colour=(1, 2, 3), size=(60, 40)) -> Path:
        path = self.folder / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", size, colour).save(path, "JPEG", quality=95)
        return path

    def test_excludes_title_picture_its_duplicates_and_dot_dirs(self):
        title = self._write("title_picture.jpg", (9, 9, 9))
        duplicate = self.folder / "Camera Uploads" / "same.jpg"
        duplicate.parent.mkdir(parents=True, exist_ok=True)
        duplicate.write_bytes(title.read_bytes())          # byte-identical copy
        keeper = self._write("Camera Uploads/other.jpg", (4, 5, 6))
        self._write(".build/999.jpg")                       # generated header, must not resurface
        self._write(".build/gallery/x.jpg")

        found = images.find_gallery_images(
            self.folder, skip_digests={images.file_digest(title)}
        )
        self.assertEqual([path.name for path in found], [keeper.name])

    def test_without_skip_digests_the_duplicate_is_kept(self):
        title = self._write("title_picture.jpg", (9, 9, 9))
        duplicate = self.folder / "copy.jpg"
        duplicate.write_bytes(title.read_bytes())
        self.assertEqual([p.name for p in images.find_gallery_images(self.folder)], ["copy.jpg"])

    def test_find_title_picture_is_extension_agnostic(self):
        self._write("title_picture.jpg")
        self.assertEqual(images.find_title_picture(self.folder).name, "title_picture.jpg")

    def test_find_title_picture_raises_when_absent(self):
        with self.assertRaises(FileNotFoundError):
            images.find_title_picture(self.folder)

    def test_prepare_downscales_and_drops_gps(self):
        source = self._write("big.jpg", size=(4080, 3072))
        out = images.prepare_gallery_image(source, self.folder / "out" / "big.jpg", max_dim=2048)
        with Image.open(out) as prepared:
            self.assertEqual(max(prepared.size), 2048)
            self.assertNotIn(0x8825, prepared.getexif())
        self.assertLess(out.stat().st_size, source.stat().st_size)

    def test_prepare_does_not_upscale_small_images(self):
        source = self._write("small.jpg", size=(300, 200))
        out = images.prepare_gallery_image(source, self.folder / "out" / "small.jpg", max_dim=2048)
        with Image.open(out) as prepared:
            self.assertEqual(prepared.size, (300, 200))


if __name__ == "__main__":
    unittest.main()
