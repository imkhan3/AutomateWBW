import json
import os
import re
import shlex
import shutil
import subprocess
import tempfile
from pathlib import Path

import yaml
from markdown_it import MarkdownIt
from mdit_py_plugins.footnote import footnote_plugin
from pypdf import PdfReader, PdfWriter

import automate_booklet

OUTPUT_PDF = automate_booklet.BASE_DIR / "booklet.pdf"
FRONTMATTER_PATTERN = re.compile(
    r"\A(?:\ufeff)?---[ \t]*\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|$)",
    re.DOTALL,
)
FENCE_PATTERN = re.compile(r"^[ \t]{0,3}(`{3,}|~{3,})")
SHORTCODE_PATTERN = re.compile(
    r"^[ \t]*\{\{\s*(wbw|cover|contact)\b(.*?)\}\}[ \t]*$"
)
PAGEBREAK_PATTERN = re.compile(r"^[ \t]*<!--\s*pagebreak\s*-->[ \t]*$", re.I)
MARKDOWN_PARSER = MarkdownIt("commonmark").use(footnote_plugin)


def _read_markdown_template(template_path: Path) -> tuple[dict, str]:
    source = template_path.read_text(encoding="utf-8")
    frontmatter_match = FRONTMATTER_PATTERN.match(source)
    if not frontmatter_match:
        return {}, source

    try:
        frontmatter = yaml.safe_load(frontmatter_match.group(1)) or {}
    except yaml.YAMLError as exc:
        raise ValueError(
            f"Invalid YAML frontmatter in '{template_path.name}': {exc}"
        ) from exc
    if not isinstance(frontmatter, dict):
        raise ValueError("Markdown frontmatter must be a YAML object.")
    return frontmatter, source[frontmatter_match.end() :]


def _parse_shortcode_attributes(source: str) -> dict[str, str]:
    try:
        parts = shlex.split(source)
    except ValueError as exc:
        raise ValueError(f"Invalid shortcode attributes: {exc}") from exc

    attributes = {}
    for part in parts:
        key, separator, value = part.partition("=")
        if not separator or not key or not value:
            raise ValueError(f"Invalid shortcode attribute: {part!r}.")
        if key in attributes:
            raise ValueError(f"Duplicate shortcode attribute: {key!r}.")
        attributes[key] = value
    return attributes


def _parse_boundary(value: str) -> dict:
    if value.startswith("{"):
        try:
            boundary = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON word boundary: {value!r}.") from exc
        if not isinstance(boundary, dict):
            raise ValueError("A JSON word boundary must be an object.")
        return boundary
    return {"word": value}


def _render_wbw_shortcode(
    attributes: dict[str, str],
    languages: tuple[str, ...],
    source_cache: dict[str, list[dict]],
) -> str:
    allowed_attributes = {
        "source",
        "start_at",
        "start_after",
        "end_at",
        "end_before",
        "start_ayah_num",
        "title_en",
        "title_ar",
        "compact_header",
    }
    unknown_attributes = set(attributes) - allowed_attributes
    if unknown_attributes:
        raise ValueError(
            f"Unknown WBW shortcode attributes: {', '.join(sorted(unknown_attributes))}."
        )

    source_name = attributes.get("source")
    if not source_name:
        raise ValueError("A WBW shortcode must include source=\"filename.json\".")

    section = {"source": source_name}
    for key in ("start_at", "start_after", "end_at", "end_before"):
        if key in attributes:
            section[key] = _parse_boundary(attributes[key])
    if "start_ayah_num" in attributes:
        try:
            section["start_ayah_num"] = int(attributes["start_ayah_num"])
        except ValueError as exc:
            raise ValueError("start_ayah_num must be a positive integer.") from exc

    title_keys = ("title_en", "title_ar")
    title_presence = [key in attributes for key in title_keys]
    if any(title_presence) and not all(title_presence):
        raise ValueError("WBW chapter headers require both title_en and title_ar.")

    compact_header = attributes.get("compact_header", "false").lower()
    if compact_header not in {"true", "false"}:
        raise ValueError("compact_header must be true or false.")

    words = automate_booklet._load_source(source_name, source_cache)
    selected_words = automate_booklet._select_words(words, section, source_name)
    if not selected_words:
        raise ValueError(f"Section for '{source_name}' selected no entries.")

    start_ayah_num = section.get("start_ayah_num", 1)
    if start_ayah_num < 1:
        raise ValueError("start_ayah_num must be a positive integer.")

    header_html = ""
    if all(title_presence):
        header_class = (
            "chapter-header subsection-header"
            if compact_header == "true"
            else "chapter-header"
        )
        header_html = f"""
        <header class="{header_class}">
            <h2 class="title-ar">{automate_booklet._text(attributes['title_ar'], 'title_ar')}</h2>
            <h3 class="title-en">{automate_booklet._text(attributes['title_en'], 'title_en')}</h3>
        </header>
        """

    return f"""
    <div class="page-section markdown-wbw-block">
        {header_html}
        <div class="chapter-content">
            {automate_booklet._render_content(
                selected_words,
                start_ayah_num,
                languages,
            )}
        </div>
    </div>
    """


def _render_special_page(kind: str, values: dict[str, str]) -> str:
    if kind == "cover":
        page_fields = ("title_ar", "title_en", "subtitle", "languages")
    else:
        page_fields = ("name", "phone", "email")

    page_spec = {"type": kind}
    for field in page_fields:
        value = values.get(field, "")
        if not isinstance(value, str):
            raise ValueError(f"'{field}' in a {kind} page must be a string.")
        page_spec[field] = value

    page_html = automate_booklet._render_page(page_spec, {})
    return f'<div class="markdown-special markdown-{kind}">{page_html}</div>'


def _render_shortcode(
    kind: str,
    attributes: dict[str, str],
    languages: tuple[str, ...],
    source_cache: dict[str, list[dict]],
) -> str:
    if kind == "wbw":
        return _render_wbw_shortcode(attributes, languages, source_cache)

    allowed_attributes = (
        {"title_ar", "title_en", "subtitle", "languages"}
        if kind == "cover"
        else {"name", "phone", "email"}
    )
    unknown_attributes = set(attributes) - allowed_attributes
    if unknown_attributes:
        raise ValueError(
            f"Unknown {kind} shortcode attributes: "
            f"{', '.join(sorted(unknown_attributes))}."
        )
    return _render_special_page(kind, attributes)


def _render_markdown_body(
    source: str,
    languages: tuple[str, ...],
    source_cache: dict[str, list[dict]],
) -> str:
    replacements = {}
    processed_lines = []
    fence_character = None
    fence_length = 0
    marker_prefix = "BOOKLETBLOCKTOKEN"
    while marker_prefix in source:
        marker_prefix += "X"
    marker_index = 0

    def add_replacement(markup: str) -> None:
        nonlocal marker_index
        marker = f"{marker_prefix}{marker_index:04d}END"
        marker_index += 1
        replacements[marker] = markup
        processed_lines.extend(("", marker, ""))

    for line in source.splitlines():
        fence_match = FENCE_PATTERN.match(line)
        if fence_character is not None:
            if (
                fence_match
                and fence_match.group(1)[0] == fence_character
                and len(fence_match.group(1)) >= fence_length
            ):
                fence_character = None
            processed_lines.append(line)
            continue
        if fence_match:
            fence_character = fence_match.group(1)[0]
            fence_length = len(fence_match.group(1))
            processed_lines.append(line)
            continue

        if PAGEBREAK_PATTERN.fullmatch(line):
            add_replacement('<div class="markdown-pagebreak"></div>')
            continue

        shortcode_match = SHORTCODE_PATTERN.fullmatch(line)
        if shortcode_match:
            kind, attribute_source = shortcode_match.groups()
            attributes = _parse_shortcode_attributes(attribute_source)
            add_replacement(
                _render_shortcode(kind, attributes, languages, source_cache)
            )
            continue

        processed_lines.append(line)

    rendered = MARKDOWN_PARSER.render("\n".join(processed_lines))
    for marker, markup in replacements.items():
        rendered = rendered.replace(f"<p>{marker}</p>", markup)
    return rendered


def render_markdown_html(template_path: Path, layout: str) -> str:
    if layout == "standard":
        layout = "letter"
    if layout not in {"letter", "half-letter", "imposed"}:
        raise ValueError("Markdown layout must be standard, half-letter, or imposed.")

    frontmatter, markdown_source = _read_markdown_template(template_path)
    languages = automate_booklet._template_languages(frontmatter)
    font_sizes = automate_booklet._font_sizes_pt(frontmatter)
    chapter_gap = automate_booklet._chapter_content_gap_pt(frontmatter)
    ayah_font_size = automate_booklet._ayah_marker_font_size_pt(frontmatter)
    source_cache: dict[str, list[dict]] = {}

    if layout == "letter":
        page_size = "8.5in 11in"
        page_height = "11in"
    else:
        page_size = "5.5in 8.5in"
        page_height = "8.5in"

    font_variables = "; ".join(
        f"--{language}-font-size: {size:g}pt"
        for language, size in font_sizes.items()
    )
    style_variables = (
        f"{font_variables}; --chapter-content-gap: {chapter_gap:g}pt; "
        f"--ayah-marker-font-size: {ayah_font_size:g}pt; "
        f"--markdown-page-height: {page_height}"
    )

    parts = []
    for kind in ("cover",):
        if kind in frontmatter:
            values = frontmatter[kind]
            if not isinstance(values, dict):
                raise ValueError(f"'{kind}' frontmatter must be a YAML object.")
            parts.append(
                _render_special_page(
                    kind,
                    values,
                )
            )

    parts.append(
        _render_markdown_body(markdown_source, languages, source_cache)
    )
    if "contact" in frontmatter:
        values = frontmatter["contact"]
        if not isinstance(values, dict):
            raise ValueError("'contact' frontmatter must be a YAML object.")
        parts.append(_render_special_page("contact", values))

    document_title = frontmatter.get(
        "title",
        frontmatter.get("document_title", template_path.stem),
    )
    if not isinstance(document_title, str):
        raise ValueError("Markdown 'title' frontmatter must be a string.")

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <title>{automate_booklet.escape(document_title)}</title>
    <link href="https://fonts.googleapis.com/css2?family=Amiri:wght@400;700&family=Noto+Nastaliq+Urdu:wght@400;700&family=Inter:wght@400;500;700&display=swap" rel="stylesheet">
    <style>
        {automate_booklet.SHARED_WORD_STYLES}

        @page {{
            size: {page_size};
            margin: 0.6in 0.55in;
        }}

        html, body {{
            margin: 0;
            padding: 0;
        }}

        body {{
            color: #0f172a;
            font-family: 'Inter', sans-serif;
            font-size: 11pt;
            line-height: 1.55;
        }}

        .markdown-content {{
            box-sizing: border-box;
            width: auto;
            margin: 0;
        }}

        .markdown-content h1,
        .markdown-content h2,
        .markdown-content h3,
        .markdown-content h4,
        .markdown-content h5,
        .markdown-content h6,
        .markdown-content .chapter-header {{
            break-after: avoid;
            page-break-after: avoid;
        }}

        .markdown-content .chapter-header {{
            margin-bottom: 16pt;
            padding: 6pt 0 8pt;
            border-bottom: 1.5px solid #0f172a;
            text-align: center;
        }}

        .markdown-content .title-ar {{
            margin: 0;
            color: #0f172a;
            font-size: 19pt;
            line-height: 1.35;
        }}

        .markdown-content .title-en {{
            margin: 4pt 0 0;
            color: #475569;
            font-size: 8.5pt;
            font-weight: 700;
            letter-spacing: 0.08em;
            line-height: 1.3;
            text-transform: uppercase;
        }}

        .markdown-content .subsection-header {{
            margin-bottom: 10pt;
            padding: 3pt 0 5pt;
        }}

        .markdown-content .subsection-header .title-ar {{
            font-size: 15pt;
            line-height: 1.2;
        }}

        .markdown-content .subsection-header .title-en {{
            margin-top: 2pt;
            font-size: 7.5pt;
        }}

        .markdown-content .chapter-content {{
            display: block;
            margin-bottom: var(--chapter-content-gap);
        }}

        .markdown-content p {{
            orphans: 2;
            widows: 2;
        }}

        .markdown-content blockquote {{
            margin: 1em 1.5em;
            padding-left: 1em;
            border-left: 3px solid #94a3b8;
            break-inside: avoid;
            page-break-inside: avoid;
        }}

        .markdown-content .hadith-line {{
            display: block;
            direction: rtl;
            margin: 0 0 18pt;
            text-align: right;
            break-inside: avoid;
            page-break-inside: avoid;
        }}

        .markdown-content .word-card {{
            display: inline-block;
            vertical-align: top;
            min-width: 30pt;
            margin: 0 8pt 7pt;
            break-inside: avoid;
            page-break-inside: avoid;
        }}

        .markdown-content .arabic {{
            font-size: var(--arabic-font-size);
            line-height: 1.6;
        }}

        .markdown-content .english,
        .markdown-content .turkish,
        .markdown-content .yoruba {{
            direction: ltr;
            font-size: var(--english-font-size);
            line-height: 1.25;
        }}

        .markdown-content .urdu {{
            direction: rtl;
            font-size: var(--urdu-font-size);
            line-height: 1.8;
        }}

        .markdown-content .ayah-ending {{
            display: inline-block;
            position: relative;
            vertical-align: top;
            break-inside: avoid;
            page-break-inside: avoid;
        }}

        .markdown-content .ayah-spacer {{
            visibility: hidden;
            unicode-bidi: isolate;
        }}

        .markdown-content .verse-ayah,
        .markdown-content .ayah-spacer {{
            color: #000;
            direction: rtl;
            font-family: 'Scheherazade', 'Amiri', serif;
            font-size: var(--ayah-marker-font-size);
            white-space: nowrap;
        }}

        .markdown-content .markdown-special .half-page {{
            box-sizing: border-box;
            width: auto;
            height: auto;
            min-height: calc(var(--markdown-page-height) - 1.2in);
            margin: 0;
            overflow: visible;
        }}

        .markdown-content .cover-page {{
            display: flex;
            align-items: center;
            justify-content: center;
            text-align: center;
        }}

        .markdown-content .cover-content {{
            box-sizing: border-box;
            width: 100%;
            padding: 44pt 20pt;
            border: 1.5px solid #0f172a;
        }}

        .markdown-content .cover-title-ar {{
            margin: 0 0 16pt;
            color: #0f172a;
            font-size: 24pt;
            line-height: 1.5;
        }}

        .markdown-content .cover-title {{
            margin: 0;
            color: #0f172a;
            font-size: 23pt;
            font-weight: 700;
            letter-spacing: 0.05em;
            line-height: 1.3;
        }}

        .markdown-content .cover-subtitle {{
            margin: 10pt 0 0;
            color: #475569;
            font-size: 12pt;
        }}

        .markdown-content .cover-divider {{
            width: 44pt;
            margin: 22pt auto;
            border-top: 1.5px solid #0f172a;
        }}

        .markdown-content .cover-languages {{
            margin: 0;
            color: #475569;
            font-size: 8.5pt;
            font-weight: 600;
            letter-spacing: 0.12em;
            text-transform: uppercase;
        }}

        .markdown-content .contact-page {{
            justify-content: flex-end;
        }}

        .markdown-content .contact-block {{
            margin-bottom: 16pt;
            color: #475569;
            font-size: 8pt;
            line-height: 1.6;
        }}

        .markdown-content .contact-block p {{
            margin: 0;
        }}

        .markdown-content .contact-name {{
            margin-bottom: 2pt !important;
            color: #0f172a;
            font-weight: 600;
        }}

        .markdown-cover {{
            break-after: page;
            page-break-after: always;
        }}

        .markdown-contact {{
            break-before: page;
            page-break-before: always;
        }}

        .markdown-pagebreak {{
            break-before: page;
            page-break-before: always;
        }}

        .markdown-content .footnotes {{
            margin-top: 2em;
            border-top: 1px solid #94a3b8;
            font-size: 0.9em;
        }}

        .markdown-content .footnote-ref {{
            font-size: 0.75em;
            vertical-align: super;
        }}
    </style>
</head>
<body>
    <main class="booklet-container markdown-content" style="{style_variables}">
        {"".join(parts)}
    </main>
</body>
</html>
"""


def _find_pdf_browser() -> Path:
    candidates = []
    for command in (
        "msedge",
        "msedge.exe",
        "chrome",
        "chrome.exe",
        "chromium",
        "chromium-browser",
        "google-chrome",
    ):
        executable = shutil.which(command)
        if executable:
            candidates.append(Path(executable))

    if os.name == "nt":
        for program_files in (
            os.environ.get("ProgramFiles(x86)"),
            os.environ.get("ProgramFiles"),
        ):
            if not program_files:
                continue
            root = Path(program_files)
            candidates.extend(
                (
                    root / "Microsoft" / "Edge" / "Application" / "msedge.exe",
                    root / "Google" / "Chrome" / "Application" / "chrome.exe",
                )
            )

    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise RuntimeError(
        "Markdown PDF generation requires Microsoft Edge, Google Chrome, "
        "or Chromium in headless mode."
    )


def _render_html_to_pdf(html_content: str, output_path: Path) -> None:
    browser = _find_pdf_browser()
    with tempfile.TemporaryDirectory(prefix="automate-wbw-") as directory:
        temporary_dir = Path(directory)
        html_path = temporary_dir / "booklet.html"
        temporary_pdf = temporary_dir / "booklet.pdf"
        profile_path = temporary_dir / "browser-profile"
        html_path.write_text(html_content, encoding="utf-8")

        result = subprocess.run(
            [
                str(browser),
                "--headless",
                "--disable-gpu",
                "--no-first-run",
                "--no-default-browser-check",
                "--no-pdf-header-footer",
                "--virtual-time-budget=10000",
                f"--user-data-dir={profile_path}",
                f"--print-to-pdf={temporary_pdf}",
                html_path.as_uri(),
            ],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        if result.returncode:
            raise RuntimeError(
                f"Headless browser PDF rendering failed: {result.stderr.strip()}"
            )
        if not temporary_pdf.is_file() or temporary_pdf.stat().st_size == 0:
            raise RuntimeError(
                "The headless browser did not produce a Markdown booklet PDF."
            )
        shutil.copyfile(temporary_pdf, output_path)


def _impose_pdf(source_pdf: Path, output_pdf: Path) -> None:
    reader = PdfReader(str(source_pdf))
    if not reader.pages:
        raise ValueError("The half-letter PDF contains no pages.")

    padded_count = ((len(reader.pages) + 3) // 4) * 4
    pages = [*reader.pages, *([None] * (padded_count - len(reader.pages)))]
    writer = PdfWriter()
    sheet_width = 11 * 72
    sheet_height = 8.5 * 72
    half_width = sheet_width / 2

    for sheet_index in range(padded_count // 4):
        page_pairs = (
            (padded_count - 1 - 2 * sheet_index, 2 * sheet_index),
            (2 * sheet_index + 1, padded_count - 2 - 2 * sheet_index),
        )
        for left_index, right_index in page_pairs:
            sheet = writer.add_blank_page(sheet_width, sheet_height)
            left_page = pages[left_index]
            right_page = pages[right_index]
            if left_page is not None:
                sheet.merge_translated_page(left_page, 0, 0)
            if right_page is not None:
                sheet.merge_translated_page(right_page, half_width, 0)

    writer.write(str(output_pdf))


def generate_markdown_booklet(template_path: Path, layout: str) -> Path:
    if layout == "standard":
        layout = "letter"
    if layout not in {"letter", "half-letter", "imposed"}:
        raise ValueError("Markdown layout must be standard, half-letter, or imposed.")

    html_content = render_markdown_html(template_path, layout)
    if layout == "imposed":
        with tempfile.TemporaryDirectory(prefix="automate-wbw-impose-") as directory:
            source_pdf = Path(directory) / "half-letter.pdf"
            _render_html_to_pdf(html_content, source_pdf)
            _impose_pdf(source_pdf, OUTPUT_PDF)
    else:
        _render_html_to_pdf(html_content, OUTPUT_PDF)

    print(f"Generated Markdown booklet PDF from {template_path.name}: {OUTPUT_PDF}")
    return OUTPUT_PDF
