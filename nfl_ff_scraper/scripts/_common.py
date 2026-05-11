"""
Shared helpers: HTTP session, file I/O, parsing utilities.
Imported by every scraper script.
"""

import json
import os
import re
import sys
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

# Add parent dir so `import config` works when scripts/ runs scripts directly
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config  # noqa: E402


BASE = "https://fantasy.nfl.com"


def make_session() -> requests.Session:
    """Build a requests.Session pre-loaded with your auth cookies + UA."""
    if not config.COOKIE_STRING or "PASTE_YOUR_COOKIE_STRING" in config.COOKIE_STRING:
        raise RuntimeError(
            "You haven't set COOKIE_STRING in config.py yet. "
            "See README.md → 'Getting Your Cookies'."
        )

    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": config.USER_AGENT,
            "Cookie": config.COOKIE_STRING,
            "Accept": (
                "text/html,application/xhtml+xml,application/xml;q=0.9,"
                "image/avif,image/webp,*/*;q=0.8"
            ),
            "Accept-Language": "en-US,en;q=0.5",
        }
    )
    return session


def polite_get(session: requests.Session, url: str, **kwargs) -> requests.Response:
    """GET with built-in delay + basic error handling."""
    time.sleep(config.REQUEST_DELAY_SECONDS)
    resp = session.get(url, timeout=30, **kwargs)
    if resp.status_code == 401 or resp.status_code == 403:
        raise RuntimeError(
            f"Got HTTP {resp.status_code} for {url}. "
            "Your cookies probably expired — log into NFL.com again and "
            "re-copy your cookie string into config.py."
        )
    if resp.status_code >= 400:
        raise RuntimeError(f"HTTP {resp.status_code} for {url}")
    # NFL.com sometimes serves a login redirect page with status 200 if
    # your session is dead. Detect that:
    if "id_signin" in resp.text and "id_username" in resp.text:
        raise RuntimeError(
            f"Got the NFL.com login page for {url}. "
            "Cookies are invalid or expired."
        )
    return resp


def ensure_dirs(*paths) -> None:
    for p in paths:
        Path(p).mkdir(parents=True, exist_ok=True)


def output_path(*parts) -> Path:
    """Build a path under the configured OUTPUT_DIR."""
    base = Path(__file__).resolve().parent.parent / config.OUTPUT_DIR
    return base.joinpath(*parts)


def save_json(data, path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def save_csv(rows: list[dict], path, fieldnames: list[str] | None = None) -> None:
    """Write a list of dicts as CSV. If no rows, writes nothing."""
    import csv

    if not rows:
        print(f"  [skip CSV] no rows for {path}")
        return
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if fieldnames is None:
        # Union of all keys, preserving first-seen order
        seen = []
        for row in rows:
            for k in row.keys():
                if k not in seen:
                    seen.append(k)
        fieldnames = seen
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def save_raw_html(html: str, *parts) -> None:
    if not config.SAVE_RAW_HTML:
        return
    path = output_path("_raw_html", *parts)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)


def soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "html.parser")


def parse_float(s: str | None) -> float | None:
    if s is None:
        return None
    s = s.strip().replace(",", "")
    if s in ("", "-", "--", "BYE"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def parse_int(s: str | None) -> int | None:
    v = parse_float(s)
    return int(v) if v is not None else None


def clean_text(s: str | None) -> str:
    if s is None:
        return ""
    return re.sub(r"\s+", " ", s).strip()
