import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pypdf import PdfReader, PdfWriter

import automate_booklet
import markdown_booklet


SAMPLE_TEMPLATE = (
    automate_booklet.TEMPLATE_DIR / "bida1_sample.md"
)


class MarkdownBookletTests(unittest.TestCase):
    def test_markdown_frontmatter_blocks_and_footnotes_render(self) -> None:
        html = markdown_booklet.render_markdown_html(SAMPLE_TEMPLATE, "letter")

        self.assertIn("<h1>Introduction</h1>", html)
        self.assertIn("<blockquote>", html)
        self.assertIn('class="footnotes-list"', html)
        self.assertIn('class="markdown-pagebreak"', html)
        self.assertIn('class="markdown-special markdown-cover"', html)
        self.assertIn('class="markdown-special markdown-contact"', html)
        self.assertIn("Markdown booklet sample", html)
        self.assertIn("break-before: page", html)
        self.assertIn("orphans: 2", html)
        self.assertIn("widows: 2", html)
        self.assertIn("--arabic-font-size: 16pt", html)
        for selector in (
            ".markdown-content .hadith-line",
            ".markdown-content .word-card",
            ".markdown-content .ayah-ending",
            ".markdown-content blockquote",
        ):
            self.assertIn(selector, html)
        self.assertIn("break-inside: avoid", html)

    def test_wbw_shortcode_uses_json_boundaries_without_header(self) -> None:
        markup = markdown_booklet._render_wbw_shortcode(
            {
                "source": "bida1.json",
                "start_at": "مَنْ",
                "end_at": "رَدٌّ",
            },
            ("en", "ur"),
            {},
        )

        self.assertIn("مَنْ", markup)
        self.assertIn("رَدٌّ", markup)
        self.assertEqual(markup.count("فَهُوَ"), 1)
        self.assertNotIn("chapter-header", markup)

    def test_wbw_shortcode_can_render_optional_chapter_header(self) -> None:
        markup = markdown_booklet._render_wbw_shortcode(
            {
                "source": "bida1.json",
                "title_en": "The Hadith",
                "title_ar": "الحديث",
                "compact_header": "true",
            },
            ("en", "ur"),
            {},
        )

        self.assertIn('class="chapter-header subsection-header"', markup)
        self.assertIn("The Hadith", markup)

    def test_cover_and_contact_shortcodes_render_special_pages(self) -> None:
        rendered = markdown_booklet._render_markdown_body(
            '{{cover title_ar="غلاف" title_en="Cover"}}\n\n'
            '{{contact name="A Reader" phone="000" email="reader@example.com"}}',
            ("en", "ur"),
            {},
        )

        self.assertIn('class="markdown-special markdown-cover"', rendered)
        self.assertIn('class="markdown-special markdown-contact"', rendered)
        self.assertIn("A Reader", rendered)

    def test_standard_and_imposed_pdf_layouts(self) -> None:
        def fake_html_to_pdf(html: str, destination: Path) -> None:
            if "size: 8.5in 11in" in html:
                page_size = (8.5 * 72, 11 * 72)
            else:
                self.assertIn("size: 5.5in 8.5in", html)
                page_size = (5.5 * 72, 8.5 * 72)
            writer = PdfWriter()
            for _ in range(5):
                writer.add_blank_page(*page_size)
            writer.write(str(destination))

        with tempfile.TemporaryDirectory() as temporary_directory:
            for layout, expected_count, expected_size in (
                ("standard", 5, (8.5 * 72, 11 * 72)),
                ("imposed", 4, (11 * 72, 8.5 * 72)),
            ):
                with self.subTest(layout=layout):
                    output_path = Path(temporary_directory) / f"{layout}.pdf"
                    with (
                        patch.object(markdown_booklet, "OUTPUT_PDF", output_path),
                        patch.object(
                            markdown_booklet,
                            "_render_html_to_pdf",
                            side_effect=fake_html_to_pdf,
                        ),
                    ):
                        automate_booklet.main(
                            [
                                SAMPLE_TEMPLATE.name,
                                "--layout",
                                layout,
                            ]
                        )

                    reader = PdfReader(str(output_path))
                    self.assertEqual(len(reader.pages), expected_count)
                    for page in reader.pages:
                        self.assertAlmostEqual(
                            float(page.mediabox.width),
                            expected_size[0],
                        )
                        self.assertAlmostEqual(
                            float(page.mediabox.height),
                            expected_size[1],
                        )


if __name__ == "__main__":
    unittest.main()
