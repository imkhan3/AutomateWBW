import argparse
import json
import math
import webbrowser
from html import escape
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
JSON_DIR = BASE_DIR / "jsons"
TEMPLATE_DIR = BASE_DIR / "book_templates"
OUTPUT_FILE = BASE_DIR / "booklet.html"
SHARED_WORD_STYLES = (BASE_DIR / "shared_word_styles.css").read_text(
    encoding="utf-8"
)
PAGE_STYLES = {
    "imposed": "@page { size: 11in 8.5in; margin: 0; }",
    "letter": "@page { size: 8.5in 11in; margin: 0; }",
    "half-letter": "@page { size: 5.5in 8.5in; margin: 0; }",
}
DEFAULT_FONT_SIZES_PT = {"arabic": 15, "english": 7.5, "urdu": 9}
DEFAULT_CHAPTER_CONTENT_GAP_PT = 20
DEFAULT_AYAH_MARKER_FONT_SIZE_PT = 28
DEFAULT_LANGUAGES = ("en", "ur")
LANGUAGE_CLASSES = {
    "en": "english",
    "ur": "urdu",
    "tr": "turkish",
    "yo": "yoruba",
}

STYLES = """
body {
    margin: 0;
    padding: 0;
    background: #cbd5e1;
    font-family: 'Inter', sans-serif;
    -webkit-print-color-adjust: exact;
}

.booklet-container {
    width: 11in;
    margin: 20px auto;
}

.sheet {
    position: relative;
    background: white;
    box-sizing: border-box;
    width: 11in;
    height: 8.5in;
    margin-bottom: 24px;
    box-shadow: 0 4px 14px rgba(0,0,0,0.15);
    display: flex;
    flex-direction: row;
    page-break-after: always;
    break-after: page;
    overflow: hidden;
}

.staple-marks {
    position: absolute;
    top: calc(15% - 0.09in);
    bottom: calc(15% - 0.09in);
    left: 50%;
    z-index: 1;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: space-between;
    width: 0;
    pointer-events: none;
    transform: translateX(-50%);
    -webkit-print-color-adjust: exact;
    print-color-adjust: exact;
}

.staple-marks span {
    display: block;
    width: 0;
    height: 0.18in;
    border-left: 0.6pt solid #9ca3af;
}

.half-page {
    box-sizing: border-box;
    width: 5.5in;
    height: 8.5in;
    padding: 0.35in 0.45in;
    display: flex;
    flex-direction: column;
    overflow: hidden;
}

.page-section {
    display: flex;
    flex: 0 0 auto;
    flex-direction: column;
}

.page-section + .page-section {
    margin-top: 10pt;
}

.cover-page {
    align-items: center;
    justify-content: center;
    text-align: center;
}

.contact-page {
    justify-content: flex-end;
}

.contact-block {
    margin-bottom: 16pt;
    color: #475569;
    font-size: 8pt;
    line-height: 1.6;
}

.contact-block p {
    margin: 0;
}

.contact-name {
    color: #0f172a;
    font-weight: 600;
    margin-bottom: 2pt !important;
}

.cover-content {
    width: 100%;
    border: 1.5px solid #0f172a;
    padding: 44pt 20pt;
    box-sizing: border-box;
}

.cover-title-ar {
    font-size: 24pt;
    line-height: 1.5;
    color: #0f172a;
    margin: 0 0 16pt;
}

.cover-title {
    font-size: 23pt;
    font-weight: 700;
    letter-spacing: 0.05em;
    line-height: 1.3;
    color: #0f172a;
    margin: 0;
}

.cover-subtitle {
    font-size: 12pt;
    color: #475569;
    margin: 10pt 0 0;
}

.cover-divider {
    width: 44pt;
    border-top: 1.5px solid #0f172a;
    margin: 22pt auto;
}

.cover-languages {
    font-size: 8.5pt;
    font-weight: 600;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: #475569;
    margin: 0;
}

.chapter-header {
    text-align: center;
    border-bottom: 1.5px solid #0f172a;
    padding: 6pt 0 8pt;
    margin-bottom: 20pt;
}

.title-ar {
    font-size: 19pt;
    margin: 0;
    line-height: 1.35;
    color: #0f172a;
}

.title-en {
    font-size: 8.5pt;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    margin: 4pt 0 0;
    line-height: 1.3;
    color: #475569;
}

.subsection-header {
    padding: 3pt 0 5pt;
    margin-bottom: 10pt;
}

.subsection-header .title-ar {
    font-size: 15pt;
    line-height: 1.2;
}

.subsection-header .title-en {
    font-size: 7.5pt;
    margin-top: 2pt;
}

.chapter-content {
    display: flex;
    flex-direction: column;
    gap: var(--chapter-content-gap);
    justify-content: flex-start;
}

.hadith-line {
    display: flex;
    flex-wrap: wrap;
    justify-content: flex-start;
    row-gap: 28pt;
    column-gap: 16pt;
    direction: rtl;
}

.word-card {
    min-width: 30pt;
    break-inside: avoid;
}

.arabic {
    font-size: var(--arabic-font-size);
    color: #000;
    line-height: 1.3;
    margin-bottom: 5pt;
}

.english,
.turkish,
.yoruba {
    font-size: var(--english-font-size);
    color: #334155;
    direction: ltr;
    line-height: 1.25;
    margin-bottom: 5pt;
}

.urdu {
    font-size: var(--urdu-font-size);
    color: #000;
    line-height: 1.8;
}

.ayah-ending {
    position: relative;
    align-items: center;
    margin-left: 4pt;
    break-inside: avoid;
}

.verse-ayah {
    position: absolute;
    right: calc(100% + 10pt);
    top: 50%;
    transform: translateY(-50%);
}

.verse-ayah,
.ayah-spacer {
    font-family: 'Scheherazade', serif;
    font-size: var(--ayah-marker-font-size);
    color: #000;
    direction: rtl;
    white-space: nowrap;
}

.ayah-spacer {
    flex: 0 0 auto;
    visibility: hidden;
    unicode-bidi: isolate;
    margin-top: -6pt;
}

.print-btn {
    position: fixed;
    z-index: 1000;
    bottom: 24px;
    right: 24px;
    background: #0f172a;
    color: white;
    padding: 12px 24px;
    font-weight: 600;
    border-radius: 50px;
    border: none;
    cursor: pointer;
    box-shadow: 0 4px 14px rgba(0,0,0,0.25);
}

@media print {
    body {
        background: white;
    }

    .booklet-container {
        margin: 0;
        width: 11in;
    }

    .sheet {
        margin: 0;
        box-shadow: none;
    }

    .print-btn {
        display: none !important;
    }
}
"""

LETTER_PAGE_STYLES = """
.booklet-container {
    width: 8.5in;
}

.half-page {
    width: 8.5in;
    height: 11in;
    margin: 0 auto 24px;
    box-shadow: 0 4px 14px rgba(0,0,0,0.15);
}

.half-page:not(:last-child) {
    page-break-after: always;
    break-after: page;
}

@media print {
    .booklet-container {
        margin: 0;
        width: 8.5in;
    }

    .half-page {
        margin: 0;
        box-shadow: none;
    }
}
"""

HALF_LETTER_PAGE_STYLES = """
.booklet-container {
    width: 5.5in;
}

.half-page {
    width: 5.5in;
    height: 8.5in;
    margin: 0 auto 24px;
    box-shadow: 0 4px 14px rgba(0,0,0,0.15);
}

.half-page:not(:last-child) {
    page-break-after: always;
    break-after: page;
}

@media print {
    .booklet-container {
        margin: 0;
        width: 5.5in;
    }

    .half-page {
        margin: 0;
        box-shadow: none;
    }
}
"""


def _text(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"'{field_name}' must be a string.")
    return escape(value)


def _template_languages(template: dict) -> tuple[str, ...]:
    languages = template.get("languages", list(DEFAULT_LANGUAGES))
    if not isinstance(languages, list):
        raise ValueError("'languages' must be an array of language codes.")
    if any(not isinstance(language, str) for language in languages):
        raise ValueError("Each language must be a language code string.")
    if len(set(languages)) != len(languages):
        raise ValueError("'languages' cannot contain duplicate language codes.")
    unsupported_languages = set(languages) - set(LANGUAGE_CLASSES)
    if unsupported_languages:
        raise ValueError(
            f"Unsupported languages: {', '.join(sorted(unsupported_languages))}."
        )
    return tuple(languages)


def _font_sizes_pt(template: dict) -> dict[str, int | float]:
    configured_sizes = template.get("font_sizes_pt", {})
    if not isinstance(configured_sizes, dict):
        raise ValueError("'font_sizes_pt' must be an object.")
    unknown_sizes = set(configured_sizes) - set(DEFAULT_FONT_SIZES_PT)
    if unknown_sizes:
        raise ValueError(
            f"Unsupported font size keys: {', '.join(sorted(unknown_sizes))}."
        )

    sizes = {}
    for language, default_size in DEFAULT_FONT_SIZES_PT.items():
        size = configured_sizes.get(language, default_size)
        if (
            isinstance(size, bool)
            or not isinstance(size, (int, float))
            or not math.isfinite(size)
            or size <= 0
        ):
            raise ValueError(
                f"Font size for '{language}' must be a positive number of points."
            )
        sizes[language] = size
    return sizes


def _chapter_content_gap_pt(template: dict) -> int | float:
    gap = template.get("chapter_content_gap_pt", DEFAULT_CHAPTER_CONTENT_GAP_PT)
    if (
        isinstance(gap, bool)
        or not isinstance(gap, (int, float))
        or not math.isfinite(gap)
        or gap < 0
    ):
        raise ValueError(
            "'chapter_content_gap_pt' must be a non-negative number of points."
        )
    return gap


def _ayah_marker_font_size_pt(template: dict) -> int | float:
    size = template.get(
        "ayah_marker_font_size_pt", DEFAULT_AYAH_MARKER_FONT_SIZE_PT
    )
    if (
        isinstance(size, bool)
        or not isinstance(size, (int, float))
        or not math.isfinite(size)
        or size <= 0
    ):
        raise ValueError(
            "'ayah_marker_font_size_pt' must be a positive number of points."
        )
    return size


def _find_boundary(words: list[dict], boundary: dict, source_name: str) -> int:
    if not isinstance(boundary, dict):
        raise ValueError(f"Page boundary for '{source_name}' must be an object.")

    if "ayah" in boundary and set(boundary) == {"ayah"}:
        target = boundary["ayah"]
        if isinstance(target, bool) or not isinstance(target, int) or target < 1:
            raise ValueError("Ayah boundaries must use a positive integer.")
        ayah_count = 0
        for index, item in enumerate(words):
            if "ayah" in item:
                ayah_count += 1
                if ayah_count == target:
                    return index
        raise ValueError(
            f"Ayah {target} was not found in '{source_name}'."
        )

    if "word" in boundary and set(boundary).issubset({"word", "occurrence"}):
        target_word = boundary["word"]
        occurrence = boundary.get("occurrence", 1)
        if not isinstance(target_word, str) or not target_word:
            raise ValueError("Arabic word boundaries must use a non-empty word.")
        if (
            isinstance(occurrence, bool)
            or not isinstance(occurrence, int)
            or occurrence < 1
        ):
            raise ValueError("Word boundary occurrence must be a positive integer.")

        matches = [
            index
            for index, item in enumerate(words)
            if item.get("ar") == target_word
        ]
        if len(matches) < occurrence:
            raise ValueError(
                f"Arabic word '{target_word}' occurrence {occurrence} "
                f"was not found in '{source_name}'."
            )
        return matches[occurrence - 1]

    raise ValueError(
        "A page boundary must be either {'ayah': number} or "
        "{'word': 'Arabic text', 'occurrence': number}."
    )


def _select_words(words: list[dict], section: dict, source_name: str) -> list[dict]:
    starts = [key for key in ("start_at", "start_after") if key in section]
    ends = [key for key in ("end_at", "end_before") if key in section]
    if len(starts) > 1 or len(ends) > 1:
        raise ValueError(
            f"Section for '{source_name}' may specify only one start and one end."
        )

    start_index = 0
    end_index = len(words)
    if starts:
        start_index = _find_boundary(words, section[starts[0]], source_name)
        if starts[0] == "start_after":
            start_index += 1
    if ends:
        end_index = _find_boundary(words, section[ends[0]], source_name)
        if ends[0] == "end_at":
            end_index += 1

    if start_index > end_index:
        raise ValueError(f"Page boundaries are out of order for '{source_name}'.")
    return words[start_index:end_index]


def _load_source(source_name: str, cache: dict[str, list[dict]]) -> list[dict]:
    if not isinstance(source_name, str) or not source_name:
        raise ValueError("Each content section must specify a source JSON file.")
    source_path = (JSON_DIR / source_name).resolve()
    try:
        source_path.relative_to(JSON_DIR.resolve())
    except ValueError as exc:
        raise ValueError("Source JSON files must be inside the jsons directory.") from exc

    if source_name not in cache:
        with source_path.open("r", encoding="utf-8") as file:
            source_words = json.load(file)
        if not isinstance(source_words, list) or not all(
            isinstance(item, dict) for item in source_words
        ):
            raise ValueError(f"'{source_name}' must contain an array of JSON objects.")
        cache[source_name] = source_words
    return cache[source_name]


def _render_content(
    words: list[dict],
    start_ayah_num: int = 1,
    languages: tuple[str, ...] = DEFAULT_LANGUAGES,
) -> str:
    lines_html = []
    current_line = []
    ayah_count = start_ayah_num - 1
    index = 0

    while index < len(words):
        item = words[index]
        if "line_break" in item:
            if current_line:
                lines_html.append("\n".join(current_line))
                current_line = []
            index += 1
            continue
        if "ayah_spacer" in item:
            ayah_number = str(ayah_count).translate(
                str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩")
            )
            current_line.append(
                f'<span class="ayah-spacer" aria-hidden="true">۝{ayah_number}</span>'
            )
            index += 1
            continue

        translation_html = "\n".join(
            f'<div class="{LANGUAGE_CLASSES[language]}">'
            f"{escape(str(item.get(language, '')))}</div>"
            for language in languages
            if item.get(language) not in (None, "")
        )
        word_card = f"""
        <div class="word-card">
            <div class="arabic">{escape(str(item.get('ar', '')))}</div>
            {translation_html}
        </div>
        """

        next_index = index + 1
        while next_index < len(words) and "line_break" in words[next_index]:
            next_index += 1

        if next_index < len(words) and "ayah" in words[next_index]:
            ayah_count += 1
            ayah_number = str(ayah_count).translate(
                str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩")
            )
            current_line.append(f"""
            <div class="ayah-ending">
                {word_card}
                <div class="verse-ayah">۝{ayah_number}</div>
            </div>
            """)
            index = next_index + 1
            continue

        current_line.append(word_card)
        index += 1

    if current_line:
        lines_html.append("\n".join(current_line))

    return "\n".join(
        f'<div class="hadith-line">\n{line}\n</div>' for line in lines_html
    )


def _render_content_page(
    page: dict,
    cache: dict[str, list[dict]],
    languages: tuple[str, ...] = DEFAULT_LANGUAGES,
) -> str:
    sections = page.get("sections")
    if not isinstance(sections, list) or not sections:
        raise ValueError("Content pages must contain a non-empty sections array.")

    rendered_sections = []
    for section in sections:
        if not isinstance(section, dict):
            raise ValueError("Each page section must be a JSON object.")
        source_name = section.get("source")
        words = _load_source(source_name, cache)
        selected_words = _select_words(words, section, source_name)
        if not selected_words:
            raise ValueError(f"Section for '{source_name}' selected no entries.")

        title_en = _text(section.get("title_en"), "title_en")
        title_ar = _text(section.get("title_ar"), "title_ar")
        start_ayah_num = section.get("start_ayah_num", 1)
        if (
            isinstance(start_ayah_num, bool)
            or not isinstance(start_ayah_num, int)
            or start_ayah_num < 1
        ):
            raise ValueError("start_ayah_num must be a positive integer.")
        compact_header = section.get("compact_header", False)
        if not isinstance(compact_header, bool):
            raise ValueError("compact_header must be true or false.")

        header_class = (
            "chapter-header subsection-header"
            if compact_header
            else "chapter-header"
        )
        rendered_sections.append(f"""
        <div class="page-section">
            <header class="{header_class}">
                <h2 class="title-ar">{title_ar}</h2>
                <h3 class="title-en">{title_en}</h3>
            </header>
            <div class="chapter-content">
                {_render_content(selected_words, start_ayah_num, languages)}
            </div>
        </div>
        """)

    return '<div class="half-page">\n' + "\n".join(rendered_sections) + "\n</div>"


def _render_page(
    page: dict,
    cache: dict[str, list[dict]],
    languages: tuple[str, ...] = DEFAULT_LANGUAGES,
) -> str:
    page_type = page.get("type", "content")
    if page_type == "content":
        return _render_content_page(page, cache, languages)
    if page_type == "blank":
        return '<div class="half-page"></div>'
    if page_type == "cover":
        cover_title = page.get("title_en")
        if not isinstance(cover_title, str):
            raise ValueError("Cover title_en must be a string.")
        title_lines = "<br />".join(
            _text(line, "cover title line") for line in cover_title.splitlines()
        )
        return f"""
        <div class="half-page cover-page">
            <div class="cover-content">
                <h2 class="cover-title-ar">{_text(page.get("title_ar"), "title_ar")}</h2>
                <h1 class="cover-title">{title_lines}</h1>
                <p class="cover-subtitle">{_text(page.get("subtitle"), "subtitle")}</p>
                <div class="cover-divider"></div>
                <p class="cover-languages">{_text(page.get("languages"), "languages")}</p>
            </div>
        </div>
        """
    if page_type == "contact":
        return f"""
        <div class="half-page cover-page contact-page">
            <div class="contact-block">
                <p class="contact-name">{_text(page.get("name"), "name")}</p>
                <p>Phone: {_text(page.get("phone"), "phone")}</p>
                <p>Email: {_text(page.get("email"), "email")}</p>
            </div>
        </div>
        """
    raise ValueError(f"Unknown page type: {page_type!r}.")


def _impose_pages(pages: list[str]) -> str:
    if not pages:
        raise ValueError("The template must define at least one page.")

    sheet_page_count = math.ceil(len(pages) / 4) * 4
    padded_pages = pages + [
        '<div class="half-page"></div>' for _ in range(sheet_page_count - len(pages))
    ]

    sheets_html = []
    sheet_count = sheet_page_count // 4
    for sheet_index in range(sheet_count):
        page_pairs = (
            (sheet_page_count - 2 * sheet_index, 1 + 2 * sheet_index),
            (2 + 2 * sheet_index, sheet_page_count - 1 - 2 * sheet_index),
        )
        for side_index, (left_page_num, right_page_num) in enumerate(page_pairs):
            side = "Front" if side_index == 0 else "Back"
            sheet_num = sheet_index + 1
            staple_marks = (
                '<div class="staple-marks" aria-hidden="true">'
                "<span></span><span></span><span></span></div>"
                if sheet_index == 0 and side_index == 0
                else ""
            )
            sheets_html.append(f"""
        <!-- Sheet {sheet_num} ({side}): Pages {left_page_num} & {right_page_num} -->
        <div class="sheet">
            {padded_pages[left_page_num - 1]}
            {padded_pages[right_page_num - 1]}
        {staple_marks}
        </div>
            """)
    return "\n".join(sheets_html)


def _resolve_template_path(argument: str) -> Path:
    requested_path = Path(argument).expanduser()
    if requested_path.is_absolute():
        template_path = requested_path.resolve()
    else:
        from_project = (BASE_DIR / requested_path).resolve()
        if from_project.is_file():
            template_path = from_project
        else:
            template_path = (TEMPLATE_DIR / requested_path.name).resolve()

    try:
        template_path.relative_to(TEMPLATE_DIR.resolve())
    except ValueError as exc:
        raise ValueError(
            f"Template files must be located in '{TEMPLATE_DIR}'."
        ) from exc
    if template_path.suffix.lower() not in {".json", ".md"}:
        raise ValueError("The template file must have a .json or .md extension.")
    if not template_path.is_file():
        raise FileNotFoundError(f"Template file not found: {template_path}")
    return template_path


def select_template() -> Path:
    template_files = sorted(
        [*TEMPLATE_DIR.glob("*.json"), *TEMPLATE_DIR.glob("*.md")]
    )
    if not template_files:
        raise FileNotFoundError(
            f"No JSON or Markdown templates found in '{TEMPLATE_DIR}'."
        )

    print("Available booklet templates:")
    for index, template_path in enumerate(template_files, start=1):
        print(f"  {index}. {template_path.name}")

    default_template = next(
        (path for path in template_files if path.name == "salah_booklet.json"),
        template_files[0],
    )
    try:
        choice = input(
            f"Select a template by number or filename "
            f"[default: {default_template.name}]: "
        ).strip()
    except EOFError:
        choice = ""

    if not choice:
        return default_template
    if choice.isdigit():
        selected_index = int(choice) - 1
        if 0 <= selected_index < len(template_files):
            return template_files[selected_index]
        raise ValueError("Selected template number is out of range.")
    return _resolve_template_path(choice)


def select_layout() -> str:
    print("Select finished page size:")
    print("  1. 8.5 x 11 inches")
    print("  2. 5.5 x 8.5 inches")
    try:
        choice = input("Choose 1 or 2 [default: 2]: ").strip().lower()
    except EOFError:
        choice = ""

    if choice in {"1", "8.5x11", "letter"}:
        return "letter"
    if choice not in {"", "2", "5.5x8.5", "half-letter"}:
        raise ValueError("Select 1 for 8.5 x 11 or 2 for 5.5 x 8.5 inches.")

    print("Select page order for 5.5 x 8.5 inch pages:")
    print("  1. Original order, one page per sheet")
    print(
        "  2. Imposed for booklet printing, two pages per side "
        "(pads to a multiple of 4)"
    )
    try:
        order_choice = input("Choose 1 or 2 [default: 2]: ").strip().lower()
    except EOFError:
        order_choice = ""

    if order_choice in {"", "2", "imposed"}:
        return "imposed"
    if order_choice in {"1", "original", "sequence"}:
        return "half-letter"
    raise ValueError("Select 1 for original order or 2 for imposed printing.")


def generate_booklet(template_path: Path, layout: str = "imposed") -> Path:
    if layout == "standard":
        layout = "letter"
    if layout not in {"letter", "half-letter", "imposed"}:
        raise ValueError(
            "Layout must be 'letter', 'half-letter', or 'imposed'."
        )
    if template_path.suffix.lower() == ".md":
        from markdown_booklet import generate_markdown_booklet

        return generate_markdown_booklet(template_path, layout)
    if template_path.suffix.lower() != ".json":
        raise ValueError("The template file must have a .json or .md extension.")

    with template_path.open("r", encoding="utf-8") as file:
        template = json.load(file)
    if not isinstance(template, dict):
        raise ValueError("The template root must be a JSON object.")
    page_specs = template.get("pages")
    if not isinstance(page_specs, list) or not page_specs:
        raise ValueError("The template must contain a non-empty pages array.")

    source_cache: dict[str, list[dict]] = {}
    languages = _template_languages(template)
    pages = []
    for page_spec in page_specs:
        if not isinstance(page_spec, dict):
            raise ValueError("Each page definition must be a JSON object.")
        pages.append(_render_page(page_spec, source_cache, languages))

    title = _text(
        template.get("document_title", "Word by Word Booklet Spreads (8.5x11)"),
        "document_title",
    )
    font_sizes = _font_sizes_pt(template)
    font_size_style = "; ".join(
        f"--{language}-font-size: {size:g}pt"
        for language, size in font_sizes.items()
    )
    chapter_content_gap = _chapter_content_gap_pt(template)
    style_variables = (
        f"{font_size_style}; --chapter-content-gap: {chapter_content_gap:g}pt"
        f"; --ayah-marker-font-size: "
        f"{_ayah_marker_font_size_pt(template):g}pt"
    )
    if layout == "imposed":
        page_layout_html = _impose_pages(pages)
        layout_styles = STYLES
    elif layout == "letter":
        page_layout_html = "\n".join(pages)
        layout_styles = STYLES + LETTER_PAGE_STYLES
    else:
        page_layout_html = "\n".join(pages)
        layout_styles = STYLES + HALF_LETTER_PAGE_STYLES
    layout_styles = (
        f"{SHARED_WORD_STYLES}\n{PAGE_STYLES[layout]}\n{layout_styles}"
    )
    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>{title}</title>
    <link href="https://fonts.googleapis.com/css2?family=Amiri:wght@400;700&family=Noto+Nastaliq+Urdu:wght@400;700&family=Inter:wght@400;600;700&display=swap" rel="stylesheet">
    <style>{layout_styles}</style>
</head>
<body>
<button class="print-btn" onclick="window.print()">Print / Save Booklet PDF</button>
<div class="booklet-container" style="{style_variables}">
{page_layout_html}
</div>
</body>
</html>
"""
    with OUTPUT_FILE.open("w", encoding="utf-8") as file:
        file.write(html_content)

    print(f"Generated booklet from {template_path.name}: {OUTPUT_FILE}")
    if not webbrowser.open(OUTPUT_FILE.as_uri()):
        raise RuntimeError("The booklet was generated, but no browser could be opened.")
    return OUTPUT_FILE


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Generate a booklet from a JSON or Markdown template."
    )
    parser.add_argument(
        "template",
        nargs="?",
        help="Template JSON or Markdown filename in book_templates or its path",
    )
    parser.add_argument(
        "--layout",
        choices=("standard", "letter", "half-letter", "imposed"),
        help="Page size and order (skips the interactive layout prompts)",
    )
    arguments = parser.parse_args(argv)
    layout = arguments.layout or select_layout()
    template_path = (
        _resolve_template_path(arguments.template)
        if arguments.template
        else select_template()
    )
    generate_booklet(template_path, layout)


if __name__ == "__main__":
    main()
