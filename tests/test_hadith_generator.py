import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock, patch

from hadith_generator import _select_languages, create_hadith_json
from html_generator import generate_html
from languages.language_catalog import load_language_options


class LanguageCatalogTests(unittest.TestCase):
    def test_discovers_new_language_metadata_files(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            languages_dir = Path(temporary_directory)
            (languages_dir / "language_fr.json").write_text(
                json.dumps({"code": "fr", "name": "French"}),
                encoding="utf-8",
            )

            self.assertEqual(
                load_language_options(languages_dir),
                (("en", "English"), ("fr", "French")),
            )

    def test_includes_urdu_from_language_folder(self) -> None:
        language_codes = {
            code for code, _ in load_language_options()
        }

        self.assertIn("ur", language_codes)

    def test_enter_selects_english_only(self) -> None:
        with patch("builtins.input", return_value=""):
            selected = _select_languages((("en", "English"), ("ur", "Urdu")))

        self.assertEqual(selected, (("en", "English"),))


class HadithGenerationTests(unittest.TestCase):
    def test_requests_only_selected_languages_and_saves_them(self) -> None:
        response_text = json.dumps(
            {"words": [{"ar": "بِسْمِ", "en": "in the name", "fr": "au nom"}]}
        )
        create_interaction = Mock(
            return_value=SimpleNamespace(output_text=response_text)
        )
        fake_google = ModuleType("google")
        fake_google.genai = SimpleNamespace(
            Client=lambda **_: SimpleNamespace(
                interactions=SimpleNamespace(create=create_interaction)
            )
        )
        language_options = (
            ("en", "English"),
            ("fr", "French"),
            ("ur", "Urdu"),
        )

        with tempfile.TemporaryDirectory() as temporary_directory:
            with (
                patch("builtins.input", side_effect=["1", "بِسْمِ", ""]),
                patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}),
                patch.dict(sys.modules, {"google": fake_google}),
            ):
                output_path = create_hadith_json(
                    Path(temporary_directory),
                    language_options,
                )

            saved_words = json.loads(output_path.read_text(encoding="utf-8"))
            schema = create_interaction.call_args.kwargs["response_format"]["schema"]

        self.assertEqual(
            saved_words,
            [{"ar": "بِسْمِ", "en": "in the name", "fr": "au nom"}],
        )
        self.assertEqual(
            schema["properties"]["words"]["items"]["anyOf"][0]["required"],
            ["ar", "en", "fr"],
        )

    def test_html_controls_default_to_english_and_accept_new_languages(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            output_path = Path(temporary_directory) / "output.html"
            with patch("html_generator.webbrowser.open"):
                generate_html(
                    [{"ar": "كلمة", "en": "word", "fr": "mot"}],
                    "test.json",
                    output_path,
                    (("en", "English"), ("fr", "French")),
                )

            html = output_path.read_text(encoding="utf-8")

        self.assertIn('value="en" checked', html)
        self.assertIn('value="fr"', html)
        self.assertIn('class="translation language-fr"', html)
        self.assertNotIn('value="fr" checked', html)


if __name__ == "__main__":
    unittest.main()
