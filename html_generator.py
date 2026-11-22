from html import escape
import webbrowser
from pathlib import Path

DEFAULT_LANGUAGE_OPTIONS = (
    ("en", "English"),
    ("ur", "Urdu"),
    ("tr", "Turkish"),
    ("yo", "Yoruba"),
)
LANGUAGE_CLASSES = {
    "en": "english",
    "ur": "urdu",
    "tr": "turkish",
    "yo": "yoruba",
}
DEFAULT_SELECTED_LANGUAGES = {"en"}
SHARED_WORD_STYLES = Path(__file__).with_name("shared_word_styles.css").read_text(
    encoding="utf-8"
)


def generate_html(
    words: list[dict[str, str | int | bool]],
    source_name: str,
    output_file: Path,
    language_options: tuple[tuple[str, str], ...] = DEFAULT_LANGUAGE_OPTIONS,
) -> None:
    language_codes = [code for code, _ in language_options]
    if len(set(language_codes)) != len(language_codes):
        raise ValueError("Language options cannot contain duplicate codes.")

    lines_html = []
    current_line = []
    ayah_count = 0
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
            index += 1
            continue
        if "ayah" in item:
            raise ValueError("An ayah marker must follow a word.")

        translation_html = []
        for language, _ in language_options:
            value = item.get(language, "")
            if value is None or value == "":
                continue
            hidden = "" if language in DEFAULT_SELECTED_LANGUAGES else " hidden"
            language_class = LANGUAGE_CLASSES.get(language, f"language-{language}")
            translation_html.append(
                f'<div class="translation {language_class}" '
                f'data-language="{language}"{hidden}>'
                f"{escape(str(value))}</div>"
            )

        word_card = f"""
    <div class="word-card">
        <div class="arabic">{escape(str(item.get('ar', '')))}</div>
        {"".join(translation_html)}
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
            lines_html.append("\n".join(current_line))
            current_line = []
            index = next_index + 1
            continue

        current_line.append(word_card)
        index += 1

    if current_line or not lines_html:
        lines_html.append("\n".join(current_line))

    cards_html = "\n".join(
        f'<div class="hadith-line">\n{line}\n</div>' for line in lines_html
    )
    language_controls = "\n".join(
        f'<label><input class="language-toggle" type="checkbox" '
        f'value="{escape(code, quote=True)}"'
        f'{" checked" if code in DEFAULT_SELECTED_LANGUAGES else ""}>'
        f" {escape(label)}</label>"
        for code, label in language_options
    )

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Word by Word Template</title>
    <!-- Google Fonts for Classical Arabic and Urdu Nastaliq -->
    <link href="https://fonts.googleapis.com/css2?family=Amiri:wght@400;700&family=Noto+Nastaliq+Urdu:wght@400;700&family=Inter:wght@400;500&display=swap" rel="stylesheet">
    <script src="https://cdnjs.cloudflare.com/ajax/libs/html2canvas/1.4.1/html2canvas.min.js"></script>
    <style>
        {SHARED_WORD_STYLES}

        @page {{
            margin: 0;
        }}
        body {{
            font-family: 'Inter', sans-serif;
            background-color: white;
            display: flex;
            justify-content: center;
            padding: 40px 20px;
        }}

        .page-sheet {{
            background: white;
            padding: 40px;
            box-shadow: 0 4px 15px rgba(0,0,0,0.05);
            border-radius: 8px;
        }}

        .hadith-container {{
            margin-top: 10rem;
            display: flex;
            flex-direction: column;
            gap: 8rem;
        }}

        .hadith-line {{
            display: flex;
            flex-wrap: wrap;
            justify-content: flex-start;
            gap: 8rem 5rem; /* Row and column spacing */
            direction: rtl;
        }}

        .word-card {{
            min-width: 60px;
        }}

        .language-controls {{
            display: flex;
            justify-content: center;
            flex-wrap: wrap;
            gap: 16px;
            margin: 20px 0;
        }}

        .language-controls label {{
            display: flex;
            align-items: center;
            gap: 6px;
            cursor: pointer;
        }}

        .ayah-ending {{
            align-items: center;
            gap: 2rem;
            flex-shrink: 0;
        }}

        .verse-ayah {{
            align-self: center;
            font-family: 'Scheherazade', 'Amiri', serif;
            font-size: 80px;
            color: #1a1a1a;
            direction: rtl;
            unicode-bidi: isolate;
        }}

        .arabic {{
            font-size: 42px;
            color: #1a1a1a;
            margin-bottom: 6px;
        }}

        .translation {{
            font-size: 19px;
            color: #444;
            direction: ltr;
            margin-bottom: 8px;
        }}

        .urdu {{
            font-size: 26px;
            color: #111;
            line-height: 2.1; /* Nastaliq requires extra height */
            direction: rtl;
        }}

        .download-btn {{
            margin-top: 7rem;
            padding: 12px 24px;
            background-color: #0f172a;
            color: white;
            border-radius: 8px;
            font-size: 16px;
            font-weight: 600;
            cursor: pointer;
            transition: background-color 0.2s ease;
        }}

        .download-btn:hover {{
            background-color: #1e293b;
        }}

        /* Print styling for direct PDF export */
        @media print {{
            body {{ background: white; padding: 0; }}
            .page-sheet {{
                box-shadow: none;
                width: calc(100% - 48px);
                padding: 0 24px;
                margin: 0 auto;
            }}
            .download-btn, .language-controls {{ display: none; }}
        }}
    </style>
    <script>
        document.addEventListener('DOMContentLoaded', () => {{
            document.querySelectorAll('.language-toggle').forEach(checkbox => {{
                checkbox.addEventListener('change', () => {{
                    document.querySelectorAll(
                        '.translation[data-language="' + checkbox.value + '"]'
                    ).forEach(line => {{
                        line.hidden = !checkbox.checked;
                    }});
                }});
            }});
        }});

        function printPdf() {{
            var el = document.querySelector('.page-sheet');
            var controls = document.querySelector('.language-controls');
            var originalDisplay = controls.style.display;
            controls.style.display = 'none';
            var rect = el.getBoundingClientRect();
            var width = rect.width + 48;
            var height = rect.height + 24;
            controls.style.display = originalDisplay;

            var style = document.createElement('style');
            style.textContent = '@page {{ size: ' + width + 'px ' + height + 'px; margin: 0 24px; }}';
            document.head.appendChild(style);

            setTimeout(() => {{
                window.print();
                setTimeout(() => style.remove(), 500);
            }}, 100);
        }}

        async function downloadPng() {{
            const sheet = document.querySelector('.page-sheet');
            const buttons = sheet.querySelectorAll(
                '.download-btn, .language-controls'
            );
            const originalDisplays = Array.from(buttons, button => button.style.display);
            await document.fonts.ready;
            buttons.forEach(button => {{ button.style.display = 'none'; }});

            try {{
                const canvas = await html2canvas(sheet, {{ scale: 3 }});
                const link = document.createElement('a');
                link.download = document.title + '.png';
                link.href = canvas.toDataURL('image/png');
                link.click();
            }} finally {{
                buttons.forEach((button, index) => {{
                    button.style.display = originalDisplays[index];
                }});
            }}
        }}
    </script>
</head>
<body>

<div class="page-sheet">
    <div class="language-controls" aria-label="Translation languages">
        {language_controls}
    </div>
    <div class="hadith-container">
        {cards_html}
    </div>
    <div style="text-align: center;">
        <button class="download-btn" onclick="printPdf()">Download PDF</button>
        <button class="download-btn" onclick="downloadPng()">Download Image</button>
    </div>
</div>

</body>
</html>
"""

    with output_file.open("w", encoding="utf-8") as file:
        file.write(html_content)

    print(f"Generated output.html successfully from {source_name}.")
    webbrowser.open(output_file.as_uri())
