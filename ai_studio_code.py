import json
from pathlib import Path

from hadith_generator import create_hadith_json
from html_generator import generate_html

BASE_DIR = Path(__file__).resolve().parent
JSON_DIR = BASE_DIR / "jsons"


def prepare_json_directory() -> None:
    JSON_DIR.mkdir(parents=True, exist_ok=True)

    legacy_data_file = BASE_DIR / "data.json"
    if legacy_data_file.exists() and not any(JSON_DIR.glob("*.json")):
        legacy_data_file.replace(JSON_DIR / "falaq.json")


def select_json_file(json_dir: Path) -> Path:
    json_files = sorted(json_dir.glob("*.json"))

    print("Available JSON files:")
    for index, file_path in enumerate(json_files, start=1):
        print(f"  {index}. {file_path.name}")
    print("  0. Create new Hadith from Arabic text")

    try:
        choice = input(
            "Select a file by number or type the filename [default: falaq.json]: "
        ).strip()
    except EOFError:
        choice = ""

    if choice == "0":
        return create_hadith_json(json_dir)
    if choice == "":
        return json_dir / "falaq.json"
    if choice.isdigit():
        selected_index = int(choice) - 1
        if 0 <= selected_index < len(json_files):
            return json_files[selected_index]
        raise ValueError("Selected number is out of range.")

    selected_file = json_dir / choice
    if not selected_file.exists():
        raise FileNotFoundError(
            f"'{selected_file.name}' was not found in '{json_dir}'."
        )
    return selected_file


def main() -> None:
    prepare_json_directory()
    selected_file = select_json_file(JSON_DIR)

    with selected_file.open("r", encoding="utf-8") as file:
        words = json.load(file)

    generate_html(words, selected_file.name, BASE_DIR / "output.html")


if __name__ == "__main__":
    main()
