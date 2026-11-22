import json
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
JSON_DIR = BASE_DIR / "jsons"


def _request_output_path(json_dir: Path) -> Path:
    try:
        filename = input(
            "Enter a filename for the new Hadith JSON (with or without .json): "
        ).strip()
    except EOFError as exc:
        raise ValueError("A filename must be entered for the new Hadith JSON.") from exc

    if not filename:
        raise ValueError("A filename must be entered for the new Hadith JSON.")
    if (
        Path(filename).name != filename
        or any(character in filename for character in '<>:"/\\|?*')
        or any(ord(character) < 32 for character in filename)
        or filename.endswith((" ", "."))
    ):
        raise ValueError("Enter a valid filename without a directory path.")

    suffix = Path(filename).suffix
    if suffix and suffix.lower() != ".json":
        raise ValueError("The Hadith filename must use the .json extension.")
    if not suffix:
        filename += ".json"

    output_json = json_dir / filename
    if output_json.exists():
        raise FileExistsError(f"'{output_json.name}' already exists.")
    return output_json


def _select_languages(
    language_options: tuple[tuple[str, str], ...],
) -> tuple[tuple[str, str], ...]:
    additional_options = tuple(
        (code, name) for code, name in language_options if code != "en"
    )
    print("English is always included. Select any additional languages:")
    for index, (_, name) in enumerate(additional_options, start=1):
        print(f"  {index}. {name}")
    print("  Press Enter for English only.")

    try:
        choice = input("Additional languages (comma-separated numbers): ").strip()
    except EOFError:
        choice = ""

    if not choice:
        return (("en", "English"),)

    selected_indices = []
    for value in choice.split(","):
        value = value.strip()
        if not value.isdigit():
            raise ValueError("Enter language numbers separated by commas.")
        selected_index = int(value) - 1
        if not 0 <= selected_index < len(additional_options):
            raise ValueError("Selected language number is out of range.")
        if selected_index not in selected_indices:
            selected_indices.append(selected_index)

    selected = [("en", "English")]
    selected.extend(additional_options[index] for index in selected_indices)
    return tuple(selected)


def create_hadith_json(
    json_dir: Path,
    language_options: tuple[tuple[str, str], ...],
) -> Path:
    output_json = _request_output_path(json_dir)
    selected_languages = _select_languages(language_options)
    translation_codes = [code for code, _ in selected_languages]
    translation_names = [name for _, name in selected_languages]

    print("Paste the Arabic text now, then enter a blank line when finished:")
    arabic_lines = []
    while True:
        try:
            line = input()
        except EOFError:
            break
        if not line.strip():
            break
        arabic_lines.append(line)

    arabic_text = "\n".join(arabic_lines).strip()
    if not arabic_text:
        raise ValueError("Arabic text cannot be empty.")

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "Set the GEMINI_API_KEY environment variable before creating a Hadith."
        )

    try:
        from google import genai
    except ImportError as exc:
        raise RuntimeError(
            "Install the Gemini SDK with: python -m pip install -r requirements.txt"
        ) from exc

    client = genai.Client(api_key=api_key)
    language_fields = "\n".join(
        f'- "{code}": its context-aware {name} translation'
        for code, name in selected_languages
    )
    properties = {"ar": {"type": "string"}}
    properties.update({code: {"type": "string"} for code in translation_codes})
    required_fields = ["ar", *translation_codes]
    prompt = f"""Translate this Arabic Hadith word by word.
Return a JSON object with a "words" array. Include one object per Arabic word/token,
in the same order. Each word object must have these string keys:
- "ar": the Arabic word with accurate harakat/tashkeel
{language_fields}
Preserve the original text and meaning; keep attached particles with their words.
Add an {{"ayah": true}} marker at the end of each Quranic ayah. Do not number it.
Add an {{"line_break": true}} object for a standalone line break when needed.
Do not include ayah objects for text without identifiable ayah boundaries.
English is required. Translate into: {", ".join(translation_names)}.
Do not include translations in any other language.

Arabic text:
{arabic_text}"""

    response = client.interactions.create(
        model="gemini-3.1-flash-lite",
        input=prompt,
        response_format={
            "type": "text",
            "mime_type": "application/json",
            "schema": {
                "type": "object",
                "properties": {
                    "words": {
                        "type": "array",
                        "items": {
                            "anyOf": [
                                {
                                    "type": "object",
                                    "properties": properties,
                                    "required": required_fields,
                                },
                                {
                                    "type": "object",
                                    "properties": {
                                        "ayah": {
                                            "type": "boolean",
                                            "enum": [True],
                                        }
                                    },
                                    "required": ["ayah"],
                                },
                                {
                                    "type": "object",
                                    "properties": {
                                        "line_break": {
                                            "type": "boolean",
                                            "enum": [True],
                                        }
                                    },
                                    "required": ["line_break"],
                                },
                            ]
                        },
                    }
                },
                "required": ["words"],
            },
        },
    )
    if not response.output_text:
        raise ValueError("Gemini returned an empty response for the Hadith.")
    try:
        generated_result = json.loads(response.output_text)
    except json.JSONDecodeError as exc:
        raise ValueError("Gemini returned invalid JSON for the Hadith.") from exc

    if not isinstance(generated_result, dict):
        raise ValueError("Gemini must return a JSON object containing words.")
    generated_words = generated_result.get("words")
    if not isinstance(generated_words, list) or not generated_words:
        raise ValueError("Gemini must return a non-empty words array.")

    words = []
    for index, item in enumerate(generated_words, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"Gemini result item {index} must be a JSON object.")
        if "line_break" in item:
            if item["line_break"] is not True:
                raise ValueError(
                    f"Gemini result item {index} must set line_break to true."
                )
            words.append({"line_break": True})
            continue
        if "ayah" in item:
            if item["ayah"] is not True:
                raise ValueError(
                    f"Gemini result item {index} must set ayah to true."
                )
            words.append({"ayah": True})
            continue
        word_fields = ["ar", *translation_codes]
        if any(
            key not in item or not isinstance(item[key], str) or not item[key].strip()
            for key in word_fields
        ):
            raise ValueError(
                f"Gemini result item {index} must contain non-empty "
                f"{', '.join(word_fields)} strings."
            )
        words.append({key: item[key].strip() for key in word_fields})

    with output_json.open("x", encoding="utf-8") as file:
        json.dump(words, file, ensure_ascii=False, indent=2)

    print(f"Saved generated Hadith to {output_json}.")
    return output_json


def main() -> None:
    from languages.language_catalog import load_language_options

    JSON_DIR.mkdir(parents=True, exist_ok=True)
    create_hadith_json(JSON_DIR, load_language_options())


if __name__ == "__main__":
    main()
