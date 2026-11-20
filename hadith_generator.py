import json
import os
from pathlib import Path


def create_hadith_json(json_dir: Path) -> Path:
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

    filename_index = 1
    while True:
        output_json = json_dir / f"new_hadith_{filename_index}.json"
        if not output_json.exists():
            break
        filename_index += 1

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
    prompt = f"""Translate this Arabic Hadith word by word.
Return a JSON object with a "words" array. Include one object per Arabic word/token,
in the same order. Each word object must have these string keys:
- "ar": the Arabic word with accurate harakat/tashkeel
- "en": its context-aware English translation
- "ur": its context-aware Urdu translation
Preserve the original text and meaning; keep attached particles with their words.
Add an {{"ayah": true}} marker at the end of each Quranic ayah. Do not number it.
Add an {{"line_break": true}} object for a standalone line break when needed.
Do not include ayah objects for text without identifiable ayah boundaries.

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
                                    "properties": {
                                        "ar": {"type": "string"},
                                        "en": {"type": "string"},
                                        "ur": {"type": "string"},
                                    },
                                    "required": ["ar", "en", "ur"],
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
        if any(
            key not in item or not isinstance(item[key], str) or not item[key].strip()
            for key in ("ar", "en", "ur")
        ):
            raise ValueError(
                f"Gemini result item {index} must contain non-empty ar, en, and ur strings."
            )
        words.append({key: item[key].strip() for key in ("ar", "en", "ur")})

    with output_json.open("x", encoding="utf-8") as file:
        json.dump(words, file, ensure_ascii=False, indent=2)

    print(f"Saved generated Hadith to {output_json}.")
    return output_json
