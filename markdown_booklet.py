import asyncio
import base64
import json
import os
import re
import shlex
import shutil
import socket
import subprocess
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from pathlib import Path

import yaml
from markdown_it import MarkdownIt
from mdit_py_plugins.footnote import footnote_plugin
from pypdf import PdfReader, PdfWriter
from pypdf.generic import DecodedStreamObject, NameObject
import websockets

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
PAGEDJS_PATH = automate_booklet.BASE_DIR / "vendor" / "pagedjs-0.4.3.min.js"
FOOTNOTE_SCRIPT = """
window.PagedConfig = { auto: false };

(function () {
    var section = document.querySelector(".footnotes");
    if (!section) {
        return;
    }

    var definitions = new Map(
        Array.from(section.querySelectorAll("li[id]")).map(function (item) {
            return [item.id, item];
        })
    );
    var placed = new Set();

    document.querySelectorAll(".markdown-content .footnote-ref").forEach(
        function (reference) {
            if (reference.closest(".footnotes")) {
                return;
            }

            var link = reference.querySelector("a[href^='#fn']");
            if (!link) {
                return;
            }

            var noteId = link.getAttribute("href").slice(1);
            var definition = definitions.get(noteId);
            if (!definition) {
                throw new Error("Missing Markdown footnote definition: " + noteId);
            }

            if (placed.has(noteId)) {
                var repeat = document.createElement("sup");
                repeat.className = "markdown-footnote-repeat";
                repeat.textContent = link.textContent;
                reference.replaceWith(repeat);
                return;
            }

            var note = definition.cloneNode(true);
            note.removeAttribute("id");
            note.querySelectorAll(".footnote-backref").forEach(function (backref) {
                backref.remove();
            });

            var float = document.createElement("span");
            float.className = "markdown-footnote";
            float.id = "markdown-" + noteId;
            float.innerHTML = note.innerHTML;
            reference.replaceWith(float);
            placed.add(noteId);
        }
    );

    section.remove();
})();
"""


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
        page_content_height = "10.2in"
    else:
        page_size = "5.5in 8.5in"
        page_content_height = "7.7in"
    if not PAGEDJS_PATH.is_file():
        raise FileNotFoundError(f"Paged.js bundle not found: {PAGEDJS_PATH}")
    pagedjs_uri = PAGEDJS_PATH.as_uri()

    font_variables = "; ".join(
        f"--{language}-font-size: {size:g}pt"
        for language, size in font_sizes.items()
    )
    style_variables = (
        f"{font_variables}; --chapter-content-gap: {chapter_gap:g}pt; "
        f"--ayah-marker-font-size: {ayah_font_size:g}pt; "
        f"--markdown-content-height: {page_content_height}"
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
            margin: 0.4in;

            @footnote {{
                margin-top: 7pt;
                padding-top: 5pt;
                border-top: 1px solid #94a3b8;
            }}
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
            margin: 0 0 0.65em;
            orphans: 2;
            widows: 2;
        }}

        .markdown-content blockquote {{
            margin: 0.75em 1em;
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
            margin: 0 8pt 11pt;
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
            min-height: var(--markdown-content-height);
            margin: 0;
            display: flex;
            flex-direction: column;
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
            align-items: center;
            justify-content: flex-end;
            padding-bottom: 0;
            text-align: center;
        }}

        .markdown-content .contact-block {{
            margin-bottom: 0;
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

        .markdown-content .markdown-footnote {{
            float: footnote;
            font-size: 8.5pt;
            line-height: 1.35;
        }}

        .markdown-content .markdown-footnote::footnote-call {{
            content: "[" counter(footnote) "]";
            font-size: 0.75em;
            vertical-align: super;
        }}

        .markdown-content .markdown-footnote::footnote-marker {{
            content: counter(footnote) ". ";
            font-weight: 700;
        }}

        .markdown-content .markdown-footnote-repeat {{
            font-size: 0.75em;
            vertical-align: super;
        }}
    </style>
</head>
<body>
    <main class="booklet-container markdown-content" style="{style_variables}">
        {"".join(parts)}
    </main>
    <script>{FOOTNOTE_SCRIPT}</script>
    <script src="{automate_booklet.escape(pagedjs_uri)}"></script>
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


async def _render_with_devtools(
    browser_process: subprocess.Popen,
    port: int,
    html_uri: str,
    output_path: Path,
) -> None:
    version_url = f"http://127.0.0.1:{port}/json/version"
    startup_deadline = time.monotonic() + 15
    version = None
    while time.monotonic() < startup_deadline:
        if browser_process.poll() is not None:
            raise RuntimeError("The headless browser exited before DevTools started.")
        try:
            with urllib.request.urlopen(version_url, timeout=1) as response:
                version = json.load(response)
            break
        except (OSError, urllib.error.URLError):
            time.sleep(0.1)
    if version is None:
        raise RuntimeError("Timed out waiting for the headless browser's DevTools.")

    target_url = (
        f"http://127.0.0.1:{port}/json/new?"
        f"{urllib.parse.quote(html_uri, safe='')}"
    )
    request = urllib.request.Request(target_url, method="PUT")
    with urllib.request.urlopen(request, timeout=10) as response:
        target = json.load(response)

    async with websockets.connect(
        target["webSocketDebuggerUrl"],
        max_size=100_000_000,
        open_timeout=10,
    ) as connection:
        request_id = 0

        async def send_command(
            method: str,
            params: dict | None = None,
            timeout: int = 60,
        ) -> dict:
            nonlocal request_id
            request_id += 1
            command_id = request_id
            await connection.send(
                json.dumps(
                    {
                        "id": command_id,
                        "method": method,
                        "params": params or {},
                    }
                )
            )
            while True:
                message = json.loads(
                    await asyncio.wait_for(connection.recv(), timeout=timeout)
                )
                if message.get("id") != command_id:
                    continue
                if "error" in message:
                    raise RuntimeError(
                        f"Browser command '{method}' failed: "
                        f"{message['error'].get('message', message['error'])}"
                    )
                return message.get("result", {})

        async def evaluate(
            expression: str,
            await_promise: bool = False,
            timeout: int = 60,
        ) -> object:
            result = await send_command(
                "Runtime.evaluate",
                {
                    "expression": expression,
                    "awaitPromise": await_promise,
                    "returnByValue": True,
                    "userGesture": True,
                },
                timeout,
            )
            if "exceptionDetails" in result:
                raise RuntimeError(
                    "Browser script failed: "
                    f"{result['exceptionDetails'].get('text', 'Unknown error')}"
                )
            return result.get("result", {}).get("value")

        await send_command("Page.enable")
        await send_command("Runtime.enable")
        await send_command("Page.navigate", {"url": html_uri})

        ready_deadline = time.monotonic() + 30
        while time.monotonic() < ready_deadline:
            ready = await evaluate(
                "document.readyState === 'complete' && "
                "typeof window.PagedPolyfill !== 'undefined'"
            )
            if ready:
                break
            await asyncio.sleep(0.1)
        else:
            raise RuntimeError("The Markdown renderer did not finish loading.")

        await evaluate(
            "document.fonts.ready.then(function () { return true; })",
            await_promise=True,
            timeout=30,
        )
        page_count = await evaluate(
            "window.PagedPolyfill.preview().then(function (flow) { "
            "return flow.total; })",
            await_promise=True,
            timeout=120,
        )
        if not isinstance(page_count, int) or page_count < 1:
            raise RuntimeError("Paged.js did not produce any booklet pages.")

        rendered_page_count = await evaluate(
            "document.querySelectorAll("
            '".pagedjs_pages .pagedjs_page").length'
        )
        if rendered_page_count != page_count:
            raise RuntimeError(
                "Paged.js page count did not match its rendered page elements."
            )

        pdf = await send_command(
            "Page.printToPDF",
            {
                "printBackground": True,
                "preferCSSPageSize": True,
                "displayHeaderFooter": False,
            },
            timeout=120,
        )
        output_path.write_bytes(base64.b64decode(pdf["data"]))

    try:
        async with websockets.connect(
            version["webSocketDebuggerUrl"],
            max_size=1_000_000,
            open_timeout=5,
        ) as browser_connection:
            await browser_connection.send(
                json.dumps({"id": 1, "method": "Browser.close"})
            )
    except (OSError, websockets.exceptions.ConnectionClosed):
        pass


def _render_html_to_pdf(html_content: str, output_path: Path) -> None:
    browser = _find_pdf_browser()
    with tempfile.TemporaryDirectory(prefix="automate-wbw-") as directory:
        temporary_dir = Path(directory)
        html_path = temporary_dir / "booklet.html"
        temporary_pdf = temporary_dir / "booklet.pdf"
        profile_path = temporary_dir / "browser-profile"
        html_path.write_text(html_content, encoding="utf-8")

        with socket.socket() as port_socket:
            port_socket.bind(("127.0.0.1", 0))
            port = port_socket.getsockname()[1]

        browser_process = subprocess.Popen(
            [
                str(browser),
                "--headless",
                "--disable-gpu",
                "--no-first-run",
                "--no-default-browser-check",
                "--no-startup-window",
                "--allow-file-access-from-files",
                f"--remote-debugging-port={port}",
                f"--user-data-dir={profile_path}",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            asyncio.run(
                _render_with_devtools(
                    browser_process,
                    port,
                    html_path.as_uri(),
                    temporary_pdf,
                )
            )
        finally:
            if browser_process.poll() is None:
                browser_process.terminate()
                browser_process.wait(timeout=10)

        if not temporary_pdf.is_file() or temporary_pdf.stat().st_size == 0:
            raise RuntimeError(
                "The headless browser did not produce a Markdown booklet PDF."
            )
        if not PdfReader(str(temporary_pdf)).pages:
            raise RuntimeError("The Markdown booklet PDF contains no pages.")
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
        for side_index, (left_index, right_index) in enumerate(page_pairs):
            sheet = writer.add_blank_page(sheet_width, sheet_height)
            left_page = pages[left_index]
            right_page = pages[right_index]
            if left_page is not None:
                sheet.merge_translated_page(left_page, 0, 0)
            if right_page is not None:
                sheet.merge_translated_page(right_page, half_width, 0)
            if sheet_index == 0 and side_index == 0:
                _add_staple_marks(sheet, writer, sheet_width, sheet_height)

    writer.write(str(output_pdf))


def _add_staple_marks(page, writer, sheet_width: float, sheet_height: float) -> None:
    center_x = sheet_width / 2
    line_height = 12
    commands = ["q", "0.65 G", "0.6 w"]
    for fraction in (0.25, 0.5, 0.75):
        center_y = sheet_height * fraction
        commands.append(
            f"{center_x:g} {center_y - line_height / 2:g} m "
            f"{center_x:g} {center_y + line_height / 2:g} l S"
        )
    commands.append("Q")

    content = page.get_contents()
    existing_data = content.get_data() if content else b""
    stream = DecodedStreamObject()
    stream.set_data(existing_data + b"\n" + "\n".join(commands).encode("ascii"))
    page[NameObject("/Contents")] = writer._add_object(stream)


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
    if not webbrowser.open(OUTPUT_PDF.as_uri()):
        raise RuntimeError("The PDF was generated, but no browser could be opened.")
    return OUTPUT_PDF
