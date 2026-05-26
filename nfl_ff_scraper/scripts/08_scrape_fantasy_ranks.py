"""
08 — Scrape end-of-season fantasy rankings from FantasyPros.

Produces four scoring profiles (every PPR × passing-TD combination):
  - ppr_6pt   Full PPR (1 pt/catch) + 6 pts/passing TD
  - half_4pt  Half PPR (0.5 pt/catch) + 4 pts/passing TD (FantasyPros default for QB)
  - ppr_4pt   Full PPR (1 pt/catch) + 4 pts/passing TD
  - half_6pt  Half PPR (0.5 pt/catch) + 6 pts/passing TD

For each, RB/WR/TE use the matching FantasyPros scoring page. QB uses the PPR page
(QB FPTS are identical across PPR/HALF/STD on FantasyPros) and we adjust passing TDs:
  *_6pt:  FantasyPros default is 4pt → add 2*passing_TDs to reach 6pt
  *_4pt:  FantasyPros default is 4pt → no adjustment

URL pattern:
  https://www.fantasypros.com/nfl/stats/{pos}.php?year={year}&scoring={SCORING}&range=full

Outputs (per profile):
  output/fantasy_ranks/{profile}/{season}.json
  output/_raw_html/{season}/fp_{pos}_{scoring}.html
  ../../data/fantasy_ranks/{profile}/{season}.json

Backward-compat: the legacy flat path `data/fantasy_ranks/{season}.json` is also
written (mirrors the ppr_6pt profile) so the original pams_site draft page keeps
working without changes.
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
SEASONS       = [2015, 2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025]
POSITIONS     = ["qb", "rb", "wr", "te"]
SITE_DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "fantasy_ranks"

# Each profile picks a FantasyPros scoring param for RB/WR/TE and a passing-TD
# adjustment for QB. QB pages are scraped with scoring=PPR (FantasyPros returns
# the same FPTS for QB regardless of PPR/HALF/STD; we use one URL to share cache).
PROFILES = {
    "ppr_6pt":  {"flex_scoring": "PPR",  "qb_pass_td_bonus": 2.0},  # full PPR, +2/passing TD → 6pt
    "half_4pt": {"flex_scoring": "HALF", "qb_pass_td_bonus": 0.0},  # half PPR, FP default 4pt
    "ppr_4pt":  {"flex_scoring": "PPR",  "qb_pass_td_bonus": 0.0},  # full PPR, FP default 4pt
    "half_6pt": {"flex_scoring": "HALF", "qb_pass_td_bonus": 2.0},  # half PPR, +2/passing TD → 6pt
}

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

def fetch_position(season: int, pos: str, scoring: str) -> str:
    cache_path = output_path("_raw_html", str(season), f"fp_{pos}_{scoring.lower()}.html")

    if cache_path.exists():
        html = cache_path.read_text(encoding="utf-8")
        print(f"    {pos.upper()} [{scoring}]: cached ({cache_path.stat().st_size:,} bytes)")
        return html

    url = (
        f"https://www.fantasypros.com/nfl/stats/{pos}.php"
        f"?year={season}&scoring={scoring}&range=full"
    )
    print(f"    {pos.upper()} [{scoring}]: fetching {url}")
    time.sleep(2)
    try:
        resp = requests.get(url, headers=HEADERS, timeout=20)
        resp.raise_for_status()
    except Exception as e:
        print(f"    {pos.upper()} [{scoring}]: ✗ {e}")
        return ""
    html = resp.text
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(html, encoding="utf-8")
    return html


# ══════════════════════════════════════════════════════════════════════════════
#  Parser
# ══════════════════════════════════════════════════════════════════════════════

def parse_fp_table(html: str, position: str, qb_pass_td_bonus: float) -> list:
    if not html:
        return []
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

    # For QBs: find the first "TD" column (passing TDs) to apply pt adjustment
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

        # FPTS from FantasyPros for the requested scoring
        fpts_raw = cells[fpts_idx].get_text(strip=True).replace(",", "")
        try:
            fpts = float(fpts_raw)
        except ValueError:
            continue
        if fpts <= 0:
            continue

        # QB passing-TD adjustment
        if position == "QB" and td_idx is not None and qb_pass_td_bonus != 0.0:
            try:
                pass_tds = float(cells[td_idx].get_text(strip=True))
                fpts = round(fpts + qb_pass_td_bonus * pass_tds, 2)
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

def scrape_season(season: int, profile_name: str) -> list:
    profile = PROFILES[profile_name]
    all_players = []
    for pos in POSITIONS:
        # QBs always come from the PPR page (cache shared across profiles); the
        # passing-TD bonus differentiates the profiles. Flex positions use the
        # profile's own scoring page.
        scoring = "PPR" if pos == "qb" else profile["flex_scoring"]
        html = fetch_position(season, pos, scoring)
        players = parse_fp_table(html, pos.upper(), profile["qb_pass_td_bonus"])
        print(f"      → {len(players)} {pos.upper()} players")
        all_players.extend(players)

    all_players.sort(key=lambda p: p["fpts"], reverse=True)
    for i, p in enumerate(all_players):
        p["rank"] = i + 1

    return all_players


def main():
    print("=" * 70)
    print("08 — Fantasy Rankings Scraper (FantasyPros · 4 scoring profiles)")
    print("=" * 70)

    SITE_DATA_DIR.mkdir(parents=True, exist_ok=True)

    for profile_name in PROFILES:
        print(f"\n{'#' * 60}")
        print(f"  Profile: {profile_name}")
        print(f"{'#' * 60}")

        for season in SEASONS:
            print(f"\n  ── {season} ──")
            players = scrape_season(season, profile_name)
            if not players:
                print(f"  [skip] No data for {season}")
                continue

            print(f"  Total: {len(players)} players ranked")
            data = {"year": season, "profile": profile_name, "players": players}

            out = output_path("fantasy_ranks", profile_name, f"{season}.json")
            save_json(data, out)
            print(f"  ✓ Scraper output → {out}")

            site_out = SITE_DATA_DIR / profile_name / f"{season}.json"
            save_json(data, site_out)
            print(f"  ✓ Site data      → {site_out}")

            # Backward-compat: keep the flat ppr_6pt copy so the original
            # pams_site draft page continues to work without code changes.
            if profile_name == "ppr_6pt":
                flat = SITE_DATA_DIR / f"{season}.json"
                save_json(data, flat)
                print(f"  ✓ Legacy flat    → {flat}")

    print("\n" + "=" * 70)
    print("Done.")
    print("=" * 70)


if __name__ == "__main__":
    main()
