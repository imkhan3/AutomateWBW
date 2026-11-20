import json
import webbrowser
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
JSON_DIR = BASE_DIR / "jsons"
OUTPUT_FILE = BASE_DIR / "booklet.html"

BOOKLET_ORDER = [
    {"file": "sana.json", "title_en": "Al-Thana (Opening)", "title_ar": "دعاء الاستفتاح"},
    {"file": "fatiha.json", "title_en": "Surah Al-Fatihah", "title_ar": "سورة الفاتحة"},
    {"file": "movements.json", "title_en": "Ruku & Sujood", "title_ar": "أذكار الركوع والسجود"},
    {"file": "tashahhud.json", "title_en": "At-Tashahhud", "title_ar": "التشهد"},
    {"file": "durood.json", "title_en": "Durood Ibrahim", "title_ar": "الصلاة الإبراهيمية"},
    {"file": "nas.json", "title_en": "Surah An-Nas", "title_ar": "سورة الناس"},
    {"file": "falaq.json", "title_en": "Surah Al-Falaq", "title_ar": "سورة الفلق"},
    {"file": "iklas.json", "title_en": "Surah Al-Ikhlas", "title_ar": "سورة الإخلاص"}
]

def render_content(words: list, start_ayah_num: int = 1) -> str:
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

        word_card = f"""
        <div class="word-card">
            <div class="arabic">{item.get('ar', '')}</div>
            <div class="english">{item.get('en', '')}</div>
            <div class="urdu">{item.get('ur', '')}</div>
        </div>
        """

        next_index = index + 1
        while next_index < len(words) and "line_break" in words[next_index]:
            next_index += 1

        if next_index < len(words) and "ayah" in words[next_index]:
            ayah_count += 1
            ayah_number = str(ayah_count).translate(str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩"))
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

    if current_line:
        lines_html.append("\n".join(current_line))

    body_html = "\n".join(f'<div class="hadith-line">\n{line}\n</div>' for line in lines_html)
    return body_html


def render_page_content(sections: list[tuple[list, str, str, int, bool]]) -> str:
    section_html = ""
    for words, title_en, title_ar, start_ayah_num, compact_header in sections:
        header_class = "chapter-header subsection-header" if compact_header else "chapter-header"
        section_html += f"""
        <div class="page-section">
            <header class="{header_class}">
                <h2 class="title-ar">{title_ar}</h2>
                <h3 class="title-en">{title_en}</h3>
            </header>
            <div class="chapter-content">
                {render_content(words, start_ayah_num)}
            </div>
        </div>
        """
    return f'<div class="half-page">{section_html}</div>'


def render_single_section(words: list, title_en: str, title_ar: str, start_ayah_num: int = 1) -> str:
    return render_page_content([(words, title_en, title_ar, start_ayah_num, False)])


def main():
    pages = []

    # Page 1: Front Cover
    pages.append("""
    <div class="half-page cover-page">
        <div class="cover-content">
            <h2 class="cover-title-ar">الصلاة والمعوّذات</h2>
            <h1 class="cover-title">Salah &amp;<br />The Three Quls</h1>
            <p class="cover-subtitle">Word-by-Word Guide</p>
            <div class="cover-divider"></div>
            <p class="cover-languages">Arabic · English · Urdu</p>
        </div>
    </div>
    """)

    tashahhud_durood_combined = False
    for entry in BOOKLET_ORDER:
        path = JSON_DIR / entry["file"]
        if not path.exists():
            continue
        if entry["file"] == "durood.json" and tashahhud_durood_combined:
            continue
        with open(path, "r", encoding="utf-8") as f:
            words = json.load(f)

        # Fatihah split across 2 pages
        if entry["file"] == "fatiha.json":
            ayah_counter = 0
            split_idx = len(words)
            for i, w in enumerate(words):
                if w.get("ayah"):
                    ayah_counter += 1
                    if ayah_counter == 4:
                        split_idx = i + 1
                        break
            
            pages.append(render_single_section(words[:split_idx], "Surah Al-Fatihah", "سورة الفاتحة", start_ayah_num=1))
            pages.append(render_single_section(words[split_idx:], "Surah Al-Fatihah (Cont.)", "سورة الفاتحة (تابع)", start_ayah_num=5))
            continue

        # Tashahhud + Durood layout
        if entry["file"] == "tashahhud.json":
            durood_path = JSON_DIR / "durood.json"
            if durood_path.exists():
                with durood_path.open("r", encoding="utf-8") as f:
                    durood_words = json.load(f)

                tashahhud_split = next((i for i, item in enumerate(words) if item.get("ar") == "وَأَشْهَدُ"), None)
                durood_split = next((i for i, item in enumerate(durood_words) if item.get("en") == "Indeed You"), None)

                pages.append(render_single_section(words[:tashahhud_split], "At-Tashahhud", "التشهد"))
                pages.append(render_page_content([
                    (words[tashahhud_split:], "At-Tashahhud (Cont.)", "التشهد (تابع)", 1, False),
                    (durood_words[:durood_split], "Durood Ibrahim", "الصلاة الإبراهيمية", 1, True),
                ]))
                pages.append(render_single_section(durood_words[durood_split:], "Durood Ibrahim (Cont.)", "الصلاة الإبراهيمية (تابع)"))
                tashahhud_durood_combined = True
                continue

        pages.append(render_single_section(words, entry["title_en"], entry["title_ar"]))

    # Page 12: Contact back cover
    pages.append("""
    <div class="half-page cover-page contact-page">
        <div class="contact-block">
            <p class="contact-name">Imran Khan</p>
            <p>Phone: 832-971-2153</p>
            <p>Email: imrank150221@gmail.com</p>
        </div>
    </div>
    """)

    # Saddle-stitch Imposition Map (1-based page numbers):
    # Sheet 1: Front (12, 1), Back (2, 11)   <- GLOSSY COVER SHEET
    # Sheet 2: Front (10, 3), Back (4, 9)    <- REGULAR PAPER
    # Sheet 3: Front (8, 5),  Back (6, 7)    <- REGULAR PAPER
    imposition_pairs = [
        (12, 1),   # Sheet 1 Front (Cover outside)
        (2, 11),   # Sheet 1 Back  (Cover inside)
        (10, 3),   # Sheet 2 Front
        (4, 9),    # Sheet 2 Back
        (8, 5),    # Sheet 3 Front
        (6, 7),    # Sheet 3 Back  (Center spread)
    ]

    sheets_html = ""
    for idx, (left_p, right_p) in enumerate(imposition_pairs):
        sheet_num = (idx // 2) + 1
        side = "Front" if idx % 2 == 0 else "Back"
        left_content = pages[left_p - 1]
        right_content = pages[right_p - 1]
        sheets_html += f"""
        <!-- Sheet {sheet_num} ({side}): Pages {left_p} & {right_p} -->
        <div class="sheet">
            {left_content}
            {right_content}
        </div>
        """

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Word by Word Booklet Spreads (8.5x11)</title>
    <link href="https://fonts.googleapis.com/css2?family=Amiri:wght@400;700&family=Noto+Nastaliq+Urdu:wght@400;700&family=Inter:wght@400;600;700&display=swap" rel="stylesheet">
    <style>
        /* PHYSICAL SHEET GEOMETRY (Letter Landscape 11in x 8.5in) */
        @page {{
            size: 11in 8.5in;
            margin: 0;
        }}

        body {{
            margin: 0;
            padding: 0;
            background: #cbd5e1;
            font-family: 'Inter', sans-serif;
            -webkit-print-color-adjust: exact;
        }}

        .booklet-container {{
            width: 11in;
            margin: 20px auto;
        }}

        .sheet {{
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
        }}

        /* Each half is an exact 5.5in x 8.5in booklet page */
        .half-page {{
            box-sizing: border-box;
            width: 5.5in;
            height: 8.5in;
            padding: 0.35in 0.45in;
            display: flex;
            flex-direction: column;
            overflow: hidden;
        }}

        .page-section {{
            display: flex;
            flex: 0 0 auto;
            flex-direction: column;
        }}

        .page-section + .page-section {{
            margin-top: 10pt;
        }}

        .cover-page {{
            align-items: center;
            justify-content: center;
            text-align: center;
        }}

        .contact-page {{
            justify-content: flex-end;
        }}

        .contact-block {{
            margin-bottom: 16pt;
            color: #475569;
            font-size: 8pt;
            line-height: 1.6;
        }}

        .contact-block p {{
            margin: 0;
        }}

        .contact-name {{
            color: #0f172a;
            font-weight: 600;
            margin-bottom: 2pt !important;
        }}

        .cover-content {{
            width: 100%;
            border: 1.5px solid #0f172a;
            padding: 44pt 20pt;
            box-sizing: border-box;
        }}

        .cover-title-ar {{
            font-family: 'Amiri', serif;
            font-size: 24pt;
            line-height: 1.5;
            color: #0f172a;
            margin: 0 0 16pt;
        }}

        .cover-title {{
            font-size: 23pt;
            font-weight: 700;
            letter-spacing: 0.05em;
            line-height: 1.3;
            color: #0f172a;
            margin: 0;
        }}

        .cover-subtitle {{
            font-size: 12pt;
            color: #475569;
            margin: 10pt 0 0;
        }}

        .cover-divider {{
            width: 44pt;
            border-top: 1.5px solid #0f172a;
            margin: 22pt auto;
        }}

        .cover-languages {{
            font-size: 8.5pt;
            font-weight: 600;
            letter-spacing: 0.12em;
            text-transform: uppercase;
            color: #475569;
            margin: 0;
        }}

        /* Header Styling */
        .chapter-header {{
            text-align: center;
            border-bottom: 1.5px solid #0f172a;
            padding: 6pt 0 8pt;
            margin-bottom: 20pt;
        }}
        .title-ar {{
            font-family: 'Amiri', serif;
            font-size: 19pt;
            margin: 0;
            line-height: 1.35;
            color: #0f172a;
        }}
        .title-en {{
            font-size: 8.5pt;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.08em;
            margin: 4pt 0 0;
            line-height: 1.3;
            color: #475569;
        }}

        .subsection-header {{
            padding: 3pt 0 5pt;
            margin-bottom: 10pt;
        }}

        .subsection-header .title-ar {{
            font-size: 15pt;
            line-height: 1.2;
        }}

        .subsection-header .title-en {{
            font-size: 7.5pt;
            margin-top: 2pt;
        }}

        /* Content Layout */
        .chapter-content {{
            display: flex;
            flex-direction: column;
            gap: 20pt;
            justify-content: flex-start;
        }}

        .hadith-line {{
            display: flex;
            flex-wrap: wrap;
            justify-content: flex-start;
            row-gap: 28pt;
            column-gap: 16pt;
            direction: rtl;
        }}

        /* Word Cards */
        .word-card {{
            display: flex;
            flex-direction: column;
            align-items: center;
            text-align: center;
            min-width: 30pt;
            break-inside: avoid;
        }}

        .arabic {{
            font-family: 'Amiri', serif;
            font-size: 15pt;
            color: #000;
            line-height: 1.3;
            margin-bottom: 5pt;
        }}

        .english {{
            font-size: 7.5pt;
            color: #334155;
            direction: ltr;
            line-height: 1.25;
            margin-bottom: 5pt;
        }}

        .urdu {{
            font-family: 'Noto Nastaliq Urdu', serif;
            font-size: 9pt;
            color: #000;
            line-height: 1.8;
        }}

        .ayah-ending {{
            display: flex;
            align-items: center;
            gap: 10pt;
            margin-left: 4pt;
            direction: rtl;
            break-inside: avoid;
        }}

        .verse-ayah {{
            align-self: center;
            font-family: 'Scheherazade', serif;
            font-size: 28pt;
            color: #000;
            direction: rtl;
            unicode-bidi: isolate;
            margin-top: -6pt;
        }}

        /* Print Settings */
        @media print {{
            body {{
                background: white;
            }}
            .booklet-container {{
                margin: 0;
                width: 11in;
            }}
            .sheet {{
                box-sizing: border-box;
                width: 11in;
                height: 8.5in;
                margin: 0;
                box-shadow: none;
            }}
            .print-btn {{
                display: none !important;
            }}
        }}

        .print-btn {{
            position: fixed;
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
        }}
    </style>
</head>
<body>

<button class="print-btn" onclick="window.print()">Print / Save Booklet PDF</button>

<div class="booklet-container">
    {sheets_html}
</div>

</body>
</html>
"""
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(html_content)

    print("Generated 8.5x11 booklet spreads successfully!")
    webbrowser.open(OUTPUT_FILE.as_uri())

if __name__ == "__main__":
    main()