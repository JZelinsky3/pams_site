"""
Rebrand pass — replaces all 'Milk Society / PAMS' strings with 'Lakeside League / LSL'
in every .html and .js file under demo/.  Idempotent.
"""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent

# Order matters — longer/more-specific strings first so they don't get partially eaten.
REPLACEMENTS = [
    # Specific phrases
    ("PA Milk Society · All-Time Series Records", "Lakeside League · All-Time Series Records"),
    ("PA MILK SOCIETY · VOL. 02",                  "THE LAKESIDE LEAGUE · VOL. II"),
    ("PA MILK SOCIETY",                            "THE LAKESIDE LEAGUE"),
    ("PA Milk Society",                            "The Lakeside League"),

    # Footer + tickers + nav title fragments
    ("The Milk <em>Society.</em>",                 "The Lakeside <em>League.</em>"),
    ("The Milk<br>\n        <em>Society.</em>",    "The Lakeside<br>\n        <em>League.</em>"),
    ("Milk <em>Society.</em>",                     "Lakeside <em>League.</em>"),

    # Plain text
    ("THE MILK SOCIETY",                           "THE LAKESIDE LEAGUE"),
    ("The Milk Society",                           "The Lakeside League"),
    ("the Milk Society",                           "the Lakeside League"),
    ("Milk Society",                               "Lakeside League"),

    # Abbreviation
    ("PAMS · Fantasy Football",                    "LSL · Fantasy Football"),
    ("· PAMS ·",                                   "· LSL ·"),
    ("· <em>PAMS</em> ·",                          "· <em>LSL</em> ·"),
    ("PAMS · CHAMPION",                            "LSL · CHAMPION"),
    ("★ PAMS",                                     "★ LSL"),

    # Society → managers (only in copy)
    ("the society",                                "the league"),
    ("The society",                                "The league"),

    # Ticker / hero blurbs referencing PAMS-specific numbers — replaced separately in the
    # records array on index.html (it's pulled from data/record_book.json now).
]

# Per-file targeted replacements
PER_FILE = {
    # index.html — replace the hardcoded ticker stats so they don't read "200.6 · CHRIS"
    "index.html": [
        ("SINGLE-WEEK RECORD: 200.6 · CHRIS",  "ALL-TIME RECORDS · UPDATED WEEKLY"),
        ("LONGEST STREAK: 8W · JOEY",          "TWELVE MANAGERS · ONE LEAGUE"),
        ("17 MANAGERS · 12 CURRENT",           "17 MANAGERS · 12 CURRENT"),
        ("SEVEN SEASONS · 689 GAMES",          "SEVEN SEASONS · 644 GAMES"),
        ("Seven seasons of champions",         "Seven seasons of champions"),
        ("2019 — 2025 · 689 MATCHUPS · 17 MANAGERS", "2019 — 2025 · 644 MATCHUPS · 17 MANAGERS"),
        ("EST. 2019",                          "EST. 2019"),
    ],
    "standings.html": [
        ("689 MATCHUPS · 6 DIFFERENT CHAMPIONS", "644 MATCHUPS · 6 DIFFERENT CHAMPIONS"),
        ("SEVENTEEN MANAGERS",                   "SEVENTEEN MANAGERS"),
        ("<div class=\"total-value\">689</div>", "<div class=\"total-value\">644</div>"),
        ("<div class=\"total-value\">$3,440</div>", "<div class=\"total-value\">$2,520</div>"),
    ],
}

# nav.js — replace the hardcoded title HTML (it appears twice in two ternary branches)
NAV_JS_REPLACEMENTS = [
    ("'<div class=\"nav-title\" id=\"' + titleId + '\">The Milk <em>Society.</em></div>'",
     "'<div class=\"nav-title\" id=\"' + titleId + '\">The Lakeside <em>League.</em></div>'"),
    ("'<a class=\"nav-title\" id=\"' + titleId + '\" href=\"' + titleHref + '\">The Milk <em>Society.</em></a>'",
     "'<a class=\"nav-title\" id=\"' + titleId + '\" href=\"' + titleHref + '\">The Lakeside <em>League.</em></a>'"),
    ("var chapter     = nav.dataset.chapter   || 'PA MILK SOCIETY';",
     "var chapter     = nav.dataset.chapter   || 'THE LAKESIDE LEAGUE';"),
]

def process(path):
    text = path.read_text()
    orig = text
    for old, new in REPLACEMENTS:
        text = text.replace(old, new)
    if path.name in PER_FILE:
        for old, new in PER_FILE[path.name]:
            text = text.replace(old, new)
    if path.name == "nav.js":
        for old, new in NAV_JS_REPLACEMENTS:
            text = text.replace(old, new)
    if text != orig:
        path.write_text(text)
        return True
    return False

count = 0
for root, dirs, files in os.walk(ROOT):
    # Skip .git, output dirs, etc.
    dirs[:] = [d for d in dirs if not d.startswith('.') and d != '__pycache__']
    for f in files:
        if f.endswith(('.html', '.js')) and f not in ('_gen_demo_data.py', '_rebrand.py'):
            if process(Path(root) / f):
                count += 1
                print(f"  ✓ {Path(root, f).relative_to(ROOT)}")
print(f"\nRebranded {count} files.")
