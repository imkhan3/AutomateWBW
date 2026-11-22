import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import automate_booklet


class BookletTemplateTests(unittest.TestCase):
    def test_root_template_directory_generates_booklet(self) -> None:
        self.assertEqual(
            automate_booklet.TEMPLATE_DIR,
            automate_booklet.BASE_DIR / "book_templates",
        )

        with tempfile.TemporaryDirectory() as temporary_directory:
            output_path = Path(temporary_directory) / "booklet.html"
            with (
                patch.object(automate_booklet, "OUTPUT_FILE", output_path),
                patch("automate_booklet.webbrowser.open", return_value=True),
            ):
                automate_booklet.main(
                    ["salah_booklet.json", "--layout", "standard"]
                )

            self.assertTrue(output_path.is_file())
            generated_html = output_path.read_text(encoding="utf-8")
            self.assertIn(
                "<title>Word by Word Booklet Spreads (8.5x11)</title>",
                generated_html,
            )
            self.assertEqual(generated_html.count("@page {"), 1)
            self.assertIn(".cover-title-ar", generated_html)


if __name__ == "__main__":
    unittest.main()
