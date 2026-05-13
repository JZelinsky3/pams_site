"""
08 — Scrape end-of-season fantasy rankings from FantasyPros.

Scoring: Full PPR (1 pt/catch) + 6 pts/passing TD.
  - RB/WR/TE: FantasyPros PPR (scoring=PPR) is used directly.
  - QB: FantasyPros PPR + 2 extra pts per passing TD
         (their default is 4 pts/passing TD; we want 6).

URL pattern:
  https://www.fantasypros.com/nfl/stats/{pos}.php?year={year}&scoring=PPR&range=full

Outputs:
  output/fantasy_ranks/{season}.json
  output/_raw_html/{season}/fp_{pos}_ppr.html    (per-position PPR cache)
  ../../data/fantasy_ranks/{season}.json

Each player record:
  {
    "rank":        int,    # overall rank by adjusted FPTS
    "player_name": str,
    "team":        str,
    "position":    str,   # QB / RB / WR / TE
    "fpts":        float, # PPR + 6pt passing TD adjusted
  }
"""

import re
import sys
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from _common import output_path, save_json

# ── Constants ────────────────────────────────────────────────────────────────
SEASONS       = [2019, 2020, 2021, 2022, 2023, 2024, 2025]
POSITIONS     = ["qb", "rb", "wr", "te"]
SITE_DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "fantasy_ranks"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


# ══════════════════════════════════════════════════════════════════════════════
#  Fetch + cache
# ══════════════════════════════════════════════════════════════════════════════

def fetch_position(season: int, pos: str) -> list:
    cache_path = output_path("_raw_html", str(season), f"fp_{pos}_ppr.html")

    if cache_path.exists():
        html = cache_path.read_text(encoding="utf-8")
        print(f"    {pos.upper()}: cached ({cache_path.stat().st_size:,} bytes)")
    else:
        url = (
            f"https://www.fantasypros.com/nfl/stats/{pos}.php"
            f"?year={season}&scoring=PPR&range=full"
        )
        print(f"    {pos.upper()}: fetching {url}")
        time.sleep(2)
        try:
            resp = requests.get(url, headers=HEADERS, timeout=20)
            resp.raise_for_status()
        except Exception as e:
            print(f"    {pos.upper()}: ✗ {e}")
            return []
        html = resp.text
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(html, encoding="utf-8")

    return parse_fp_table(html, pos.upper())


# ══════════════════════════════════════════════════════════════════════════════
#  Parser
# ══════════════════════════════════════════════════════════════════════════════

def parse_fp_table(html: str, position: str) -> list:
    page  = BeautifulSoup(html, "html.parser")
    table = page.find("table", id="data")
    if not table:
        print(f"    ✗ No #data table for {position}")
        return []

    # Resolve column indices from last header row
    thead = table.find("thead")
    header_row = thead.find_all("tr")[-1]
    headers = [th.get_text(strip=True) for th in header_row.find_all("th")]

    fpts_idx = next(
        (i for i, h in enumerate(headers) if h == "FPTS" and "/" not in h),
        None
    )
    if fpts_idx is None:
        print(f"    ✗ FPTS column not found for {position}")
        return []

    # For QBs: find the first "TD" column (passing TDs) to apply 6-pt adjustment
    td_idx = None
    if position == "QB":
        td_idx = next((i for i, h in enumerate(headers) if h == "TD"), None)

    tbody = table.find("tbody")
    if not tbody:
        return []

    players = []
    for row in tbody.find_all("tr"):
        cells = row.find_all("td")
        if len(cells) <= fpts_idx:
            continue

        # Player: "Saquon Barkley(PHI)"
        raw_name = cells[1].get_text(strip=True)
        m = re.match(r"^(.+?)\s*\(([A-Z]{2,4})\)\s*$", raw_name)
        if m:
            player_name = m.group(1).strip()
            team        = m.group(2)
        else:
            player_name = raw_name
            team        = ""

        # FPTS (PPR)
        fpts_raw = cells[fpts_idx].get_text(strip=True).replace(",", "")
        try:
            fpts = float(fpts_raw)
        except ValueError:
            continue
        if fpts <= 0:
            continue

        # QB 6-pt passing TD adjustment (+2 pts per passing TD)
        if position == "QB" and td_idx is not None:
            try:
                pass_tds = float(cells[td_idx].get_text(strip=True))
                fpts = round(fpts + 2 * pass_tds, 2)
            except (ValueError, IndexError):
                pass

        players.append({
            "player_name": player_name,
            "team":        team,
            "position":    position,
            "fpts":        fpts,
        })

    return players


# ══════════════════════════════════════════════════════════════════════════════
#  Main
# ══════════════════════════════════════════════════════════════════════════════

def scrape_season(season: int) -> list:
    all_players = []
    for pos in POSITIONS:
        players = fetch_position(season, pos)
        print(f"      → {len(players)} {pos.upper()} players")
        all_players.extend(players)

    all_players.sort(key=lambda p: p["fpts"], reverse=True)
    for i, p in enumerate(all_players):
        p["rank"] = i + 1

    return all_players


def main():
    print("=" * 70)
    print("08 — Fantasy Rankings Scraper (FantasyPros · Full PPR + 6pt Pass TD)")
    print("=" * 70)

    SITE_DATA_DIR.mkdir(parents=True, exist_ok=True)

    for season in SEASONS:
        print(f"\n{'─'*60}")
        print(f"  Season {season}")
        print(f"{'─'*60}")

        players = scrape_season(season)
        if not players:
            print(f"  [skip] No data for {season}")
            continue

        print(f"  Total: {len(players)} players ranked")

        data = {"year": season, "players": players}

        out = output_path("fantasy_ranks", f"{season}.json")
        save_json(data, out)
        print(f"  ✓ Scraper output → {out}")

        site_out = SITE_DATA_DIR / f"{season}.json"
        save_json(data, site_out)
        print(f"  ✓ Site data      → {site_out}")

    print("\n" + "=" * 70)
    print("Done.")
    print("=" * 70)


if __name__ == "__main__":
    main()
