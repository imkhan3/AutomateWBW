import json
import re
from pathlib import Path

LANGUAGES_DIR = Path(__file__).resolve().parent
LANGUAGE_CODE_PATTERN = re.compile(r"[a-z]{2,3}\Z")


def load_language_options(
    languages_dir: Path = LANGUAGES_DIR,
) -> tuple[tuple[str, str], ...]:
    options = [("en", "English")]
    seen_codes = {"en"}

    for language_file in sorted(languages_dir.glob("language_*.json")):
        with language_file.open("r", encoding="utf-8") as file:
            language = json.load(file)
        if not isinstance(language, dict):
            raise ValueError(f"'{language_file.name}' must contain a JSON object.")

        code = language.get("code")
        name = language.get("name")
        if not isinstance(code, str) or not LANGUAGE_CODE_PATTERN.fullmatch(code):
            raise ValueError(
                f"'{language_file.name}' must contain a lowercase 2- or 3-letter code."
            )
        if not isinstance(name, str) or not name.strip():
            raise ValueError(f"'{language_file.name}' must contain a non-empty name.")
        if code in seen_codes:
            raise ValueError(
                f"Duplicate language code '{code}' in '{language_file.name}'."
            )

        seen_codes.add(code)
        options.append((code, name.strip()))

    return tuple(
        sorted(options, key=lambda option: (option[0] != "en", option[1].casefold()))
    )
