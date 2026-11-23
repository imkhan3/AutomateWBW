import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import automate_booklet


class BookletTemplateTests(unittest.TestCase):
    def test_selects_letter_page_without_asking_about_imposition(self) -> None:
        with patch("builtins.input", return_value="1") as read_input:
            layout = automate_booklet.select_layout()

        self.assertEqual(layout, "letter")
        read_input.assert_called_once()

    def test_selects_half_letter_original_order(self) -> None:
        with patch("builtins.input", side_effect=["2", "1"]):
            layout = automate_booklet.select_layout()

        self.assertEqual(layout, "half-letter")

    def test_selects_half_letter_imposition(self) -> None:
        with patch("builtins.input", side_effect=["2", "2"]):
            layout = automate_booklet.select_layout()

        self.assertEqual(layout, "imposed")

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

    def test_half_letter_modes_use_the_selected_page_layout(self) -> None:
        template_path = automate_booklet.TEMPLATE_DIR / "salah_booklet.json"
        with tempfile.TemporaryDirectory() as temporary_directory:
            for layout, page_rule, has_sheet_wrapper in (
                ("half-letter", "5.5in 8.5in", False),
                ("imposed", "11in 8.5in", True),
            ):
                with self.subTest(layout=layout):
                    output_path = Path(temporary_directory) / f"{layout}.html"
                    with (
                        patch.object(automate_booklet, "OUTPUT_FILE", output_path),
                        patch("automate_booklet.webbrowser.open", return_value=True),
                    ):
                        automate_booklet.generate_booklet(template_path, layout)

                    generated_html = output_path.read_text(encoding="utf-8")
                    self.assertIn(f"size: {page_rule}", generated_html)
                    self.assertEqual(
                        '<div class="sheet">' in generated_html,
                        has_sheet_wrapper,
                    )


if __name__ == "__main__":
    unittest.main()
