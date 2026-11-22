import argparse
import json
import os
import tempfile
from pathlib import Path

if __package__:
    from .language_catalog import load_language_options
else:
    from language_catalog import load_language_options

BASE_DIR = Path(__file__).resolve().parents[1]
JSON_DIR = BASE_DIR / "jsons"
MODEL = "gemini-3.1-flash-lite"
LANGUAGES = {
    code: name for code, name in load_language_options() if code != "en"
}


def _resolve_source_file(argument: str) -> Path:
    requested_path = Path(argument).expanduser()
    if not requested_path.is_absolute():
        requested_path = JSON_DIR / requested_path
    source_path = requested_path.resolve()

    if source_path.parent != JSON_DIR.resolve():
        raise ValueError("Choose a word-by-word JSON file directly inside 'jsons'.")
    if source_path.suffix.lower() != ".json":
        raise ValueError("The source file must have a .json extension.")
    if not source_path.is_file():
        raise FileNotFoundError(f"Source JSON file not found: {source_path}")
    return source_path


def _select_source_file() -> Path:
    source_files = sorted(JSON_DIR.glob("*.json"))
    if not source_files:
        raise FileNotFoundError(f"No word-by-word JSON files found in '{JSON_DIR}'.")

    print("Available word-by-word JSON files:")
    for index, source_file in enumerate(source_files, start=1):
        print(f"  {index}. {source_file.name}")

    try:
        choice = input("Select a file by number or filename: ").strip()
    except EOFError as exc:
        raise ValueError("A source JSON file must be selected.") from exc

    if choice.isdigit():
        selected_index = int(choice) - 1
        if 0 <= selected_index < len(source_files):
            return source_files[selected_index]
        raise ValueError("Selected file number is out of range.")
    if not choice:
        raise ValueError("A source JSON file must be selected.")
    return _resolve_source_file(choice)


def _word_entries(
    words: list[dict[str, object]], language_code: str
) -> tuple[list[tuple[dict[str, object], str]], str]:
    entries = []
    passage_lines = []
    current_line = []

    for index, item in enumerate(words, start=1):
        if "line_break" in item:
            if current_line:
                passage_lines.append(" ".join(current_line))
                current_line = []
            continue
        if "ayah_spacer" in item:
            continue
        if "ayah" in item:
            current_line.append("۝")
            continue

        arabic = item.get("ar")
        if not isinstance(arabic, str) or not arabic.strip():
            raise ValueError(
                f"Word entry {index} must contain a non-empty Arabic 'ar' string."
            )
        if language_code in item and not isinstance(item[language_code], str):
            raise ValueError(
                f"Word entry {index} has a non-string '{language_code}' value."
            )
        entries.append((item, arabic))
        current_line.append(arabic)

    if current_line:
        passage_lines.append(" ".join(current_line))
    if not entries:
        raise ValueError("The source JSON contains no Arabic word entries.")

    return entries, "\n".join(passage_lines)


def _has_translation(item: dict[str, object], language_code: str) -> bool:
    value = item.get(language_code)
    if value is not None and not isinstance(value, str):
        raise ValueError(f"Existing '{language_code}' translations must be strings.")
    return isinstance(value, str) and bool(value.strip())


def _request_translations(
    entries: list[tuple[dict[str, object], str]],
    arabic_text: str,
    language_code: str,
) -> list[str]:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "Set the GEMINI_API_KEY environment variable before translating."
        )

    try:
        from google import genai
    except ImportError as exc:
        raise RuntimeError(
            "Install the Gemini SDK with: python -m pip install -r requirements.txt"
        ) from exc

    language_name = LANGUAGES[language_code]
    token_list = "\n".join(
        f"{index}. {arabic}" for index, (_, arabic) in enumerate(entries, start=1)
    )
    prompt = f"""Translate every Arabic token below into {language_name}, word by word.
Use the complete passage for context, but return one concise translation for each
listed token in exactly the same order. Keep the translations natural in {language_name}.
Do not return Arabic, English, Urdu, commentary, or extra entries.
Return a JSON object with a "translations" array containing exactly
{len(entries)} non-empty strings.

Complete Arabic passage:
{arabic_text}

Tokens to translate in order:
{token_list}"""

    client = genai.Client(api_key=api_key)
    response = client.interactions.create(
        model=MODEL,
        input=prompt,
        response_format={
            "type": "text",
            "mime_type": "application/json",
            "schema": {
                "type": "object",
                "properties": {
                    "translations": {
                        "type": "array",
                        "items": {"type": "string"},
                    }
                },
                "required": ["translations"],
            },
        },
    )
    if not response.output_text:
        raise ValueError(f"Gemini returned an empty {language_name} translation.")
    try:
        result = json.loads(response.output_text)
    except json.JSONDecodeError as exc:
        raise ValueError("Gemini returned invalid JSON translations.") from exc

    if not isinstance(result, dict):
        raise ValueError("Gemini must return a JSON object containing translations.")
    translations = result.get("translations")
    if not isinstance(translations, list) or len(translations) != len(entries):
        raise ValueError(
            f"Gemini must return exactly {len(entries)} ordered translations."
        )
    if any(not isinstance(value, str) or not value.strip() for value in translations):
        raise ValueError("Gemini translations must all be non-empty strings.")
    return [value.strip() for value in translations]


def _save_words(source_path: Path, words: list[dict[str, object]]) -> None:
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=source_path.parent,
            prefix=f".{source_path.name}.",
            suffix=".tmp",
            delete=False,
        ) as file:
            temporary_path = Path(file.name)
            json.dump(words, file, ensure_ascii=False, indent=2)
            file.write("\n")
        os.replace(temporary_path, source_path)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()


def translate_file(source_path: Path, language_code: str) -> None:
    if language_code not in LANGUAGES:
        raise ValueError(f"Unsupported translation language: {language_code!r}.")

    with source_path.open("r", encoding="utf-8") as file:
        words = json.load(file)
    if not isinstance(words, list) or not all(isinstance(item, dict) for item in words):
        raise ValueError(f"'{source_path.name}' must contain an array of JSON objects.")

    entries, arabic_text = _word_entries(words, language_code)
    missing_entries = [
        item for item, _ in entries if not _has_translation(item, language_code)
    ]
    if not missing_entries:
        print(f"'{source_path.name}' already has complete {LANGUAGES[language_code]}.")
        return

    translations = _request_translations(entries, arabic_text, language_code)
    for (item, _), translation in zip(entries, translations):
        if not _has_translation(item, language_code):
            item[language_code] = translation

    _save_words(source_path, words)
    print(
        f"Added {LANGUAGES[language_code]} to {len(missing_entries)} word entries "
        f"in '{source_path.name}'. Arabic and existing translations were preserved."
    )


def run_for_language(language_code: str, argv: list[str] | None = None) -> None:
    if language_code not in LANGUAGES:
        raise ValueError(f"Unsupported translation language: {language_code!r}.")
    parser = argparse.ArgumentParser(
        description=f"Add {LANGUAGES[language_code]} translations to a word-by-word JSON."
    )
    parser.add_argument(
        "source",
        nargs="?",
        help="JSON filename in jsons (omit to choose interactively)",
    )
    arguments = parser.parse_args(argv)
    source_path = (
        _resolve_source_file(arguments.source)
        if arguments.source
        else _select_source_file()
    )
    translate_file(source_path, language_code)
