"""
07 — Scrape draft results for all seasons.

NFL.com historical pages (2019–2025):
  URL: /league/{id}/history/{year}/draftresults?draftResultsDetail=0&draftResultsTab=round&draftResultsType=results
  The default page only shows Round 1; draftResultsDetail=0 loads ALL rounds.

Sleeper API (2026+) — uses requests so Mac SSL certs aren't an issue:
  GET https://api.sleeper.app/v1/league/{sleeper_league_id}/drafts
  GET https://api.sleeper.app/v1/draft/{draft_id}/picks

Outputs:
  output/drafts/{season}.json
  output/_raw_html/{season}/draft_results.html  (NFL.com seasons only)
  ../../data/drafts/{season}.json               (pams site data dir)
"""

import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from _common import (
    BASE,
    config,
    make_session,
    output_path,
    polite_get,
    save_json,
    save_raw_html,
    soup,
    clean_text,
)

# ── Constants ────────────────────────────────────────────────────────────────
SLEEPER_LEAGUE_ID = "1304235036874149888"
SLEEPER_API       = "https://api.sleeper.app/v1"

NFL_SEASONS     = [2019, 2020, 2021, 2022, 2023, 2024, 2025]
SLEEPER_SEASONS = [2026]

SITE_DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "drafts"


# ══════════════════════════════════════════════════════════════════════════════
#  NFL.com
# ══════════════════════════════════════════════════════════════════════════════

def scrape_nfl_draft(session, season: int) -> list:
    """
    Parse draft picks for one NFL.com season.

    If draft_results_all.html is already cached for this season, reparse it
    without making any HTTP requests (saves cookies + time).
    Otherwise, fetch the all-rounds page:
      /league/{id}/history/{year}/draftresults
        ?draftResultsDetail=0&draftResultsTab=round&draftResultsType=results
    """
    cache_path = output_path("_raw_html", str(season), "draft_results_all.html")

    if cache_path.exists():
        print(f"  ✓ Using cached HTML ({cache_path.stat().st_size:,} bytes) — no request needed")
        html = cache_path.read_text(encoding="utf-8")
    else:
        url = (
            f"{BASE}/league/{config.LEAGUE_ID}/history/{season}/draftresults"
            "?draftResultsDetail=0&draftResultsTab=round&draftResultsType=results"
        )
        print(f"  Fetching: {url}")
        try:
            resp = polite_get(session, url)
        except Exception as e:
            print(f"  ✗ Request failed: {e}")
            return []
        html = resp.text
        save_raw_html(html, str(season), "draft_results_all.html")
        print(f"  ✓ Saved raw HTML ({len(html):,} bytes)")

    picks = parse_nfl_draft_html(html, season)
    print(f"  → Parsed {len(picks)} picks")
    return picks


def parse_nfl_draft_html(html: str, season: int) -> list:
    """
    Parse NFL.com draft results HTML (all-rounds view).

    Actual structure: each round is its own <div class="wrap"> inside
    <div class="results">.  My first attempt only found the FIRST wrap;
    the fix is to iterate ALL wraps.

      <div class="results">
        <div class="wrap">           ← Round 1
          <h4>Round 1</h4>
          <ul>
            <li>
              <span class="count">1.</span>
              <a class="playerNameFull playerNameId-{id}">Name</a>
              <em>RB - SF</em>
              <span class="tw">
                <a class="teamName teamId-7">WHITEBOY FOOTBALL</a>
                <ul><li class="first last">Evan</li></ul>
              </span>
            </li>
            ...
          </ul>
        </div>
        <div class="wrap">           ← Round 2
          ...
        </div>
      </div>
    """
    page  = soup(html)
    picks = []

    # All wraps inside div.results, one per round
    results_div = page.find("div", class_="results")
    if not results_div:
        print("  ✗ Could not find div.results — page structure unexpected")
        return []

    wraps = results_div.find_all("div", class_="wrap")
    if not wraps:
        print("  ✗ No div.wrap rounds found inside div.results")
        return []

    print(f"  Found {len(wraps)} rounds in HTML")

    for wrap in wraps:
        # Round number from <h4>
        h4 = wrap.find("h4")
        if not h4:
            continue
        m = re.search(r"Round\s+(\d+)", clean_text(h4.get_text()), re.I)
        if not m:
            continue
        current_round = int(m.group(1))

        pick_list = wrap.find("ul")
        if not pick_list:
            continue

        for round_pick_idx, li in enumerate(pick_list.find_all("li", recursive=False), start=1):

            # Overall pick number — the <span class="count"> shows global number
            count_el = li.find("span", class_="count")
            overall  = None
            if count_el:
                overall = int(re.sub(r"\D", "", count_el.get_text()) or "0") or None

            # Player name
            player_el = li.find("a", class_=re.compile(r"playerNameFull", re.I))
            player    = clean_text(player_el.get_text()) if player_el else None

            # Player ID (useful for cross-referencing)
            player_id = None
            if player_el:
                m2 = re.search(r"playerNameId-(\d+)", " ".join(player_el.get("class", [])))
                if m2:
                    player_id = m2.group(1)

            # Position + NFL team from <em>: "RB - SF"
            em_el    = li.find("em")
            pos_nfl  = clean_text(em_el.get_text()) if em_el else ""
            parts    = [p.strip() for p in pos_nfl.split("-")]
            position = parts[0] if parts and len(parts[0]) <= 4 else "?"
            nfl_team = parts[1] if len(parts) > 1 else ""

            # Fantasy team name and team_id
            team_el   = li.find("a", class_=re.compile(r"teamName", re.I))
            team_name = clean_text(team_el.get_text()) if team_el else ""
            team_id   = None
            if team_el:
                m3 = re.search(r"teamId[=\-](\d+)", team_el.get("href", ""))
                if m3:
                    team_id = int(m3.group(1))

            # Manager name is in span.tw > ul > li
            manager_name = None
            tw = li.find("span", class_="tw")
            if tw:
                owner_li = tw.find("li")
                if owner_li:
                    manager_name = clean_text(owner_li.get_text())

            # Map NFL.com display name → our canonical name via config.
            # Case-sensitive pass first so "Sean" (Costigan) doesn't collapse
            # into "sean" (current member) via the case-insensitive fallback.
            user_id = None
            if manager_name:
                all_members = config.CURRENT_MEMBERS + config.FORMER_MEMBERS
                # Pass 1: exact case match on NFL display name
                for uid, my_name, nfl_name in all_members:
                    if nfl_name == manager_name:
                        manager_name = my_name
                        user_id      = uid
                        break
                else:
                    # Pass 2: case-insensitive fallback
                    for uid, my_name, nfl_name in all_members:
                        if nfl_name.lower() == manager_name.lower() or \
                           my_name.lower()  == manager_name.lower():
                            manager_name = my_name
                            user_id      = uid
                            break

            if not player:
                continue

            picks.append({
                "overall_pick": overall or (current_round - 1) * 12 + round_pick_idx,
                "round":        current_round,
                "round_pick":   round_pick_idx,
                "player_id":    player_id,
                "player_name":  player,
                "position":     position,
                "nfl_team":     nfl_team,
                "team_name":    team_name,
                "manager_name": manager_name or "",
                "user_id":      user_id,
            })

    return picks


# ══════════════════════════════════════════════════════════════════════════════
#  Sleeper  (uses requests — avoids Mac SSL cert issues with urllib)
# ══════════════════════════════════════════════════════════════════════════════

def sleeper_get(session, path: str):
    """GET Sleeper public API using the existing requests session."""
    url = f"{SLEEPER_API}{path}"
    print(f"  Sleeper: {url}")
    time.sleep(0.5)
    # Sleeper is a different domain — make a plain session for it
    import requests
    resp = requests.get(url, timeout=15)
    resp.raise_for_status()
    return resp.json()


def scrape_sleeper_draft(session, season: int) -> list:
    """Pull draft picks from Sleeper API."""
    try:
        drafts = sleeper_get(session, f"/league/{SLEEPER_LEAGUE_ID}/drafts")
    except Exception as e:
        print(f"  ✗ Sleeper API error: {e}")
        return []

    if not drafts:
        print(f"  No Sleeper drafts found.")
        return []

    draft    = drafts[0]
    draft_id = draft.get("draft_id")
    status   = draft.get("status")
    print(f"  Draft ID: {draft_id} | Status: {status}")

    if status != "complete":
        print(f"  Draft not complete yet — skipping.")
        return []

    try:
        raw_picks = sleeper_get(session, f"/draft/{draft_id}/picks")
    except Exception as e:
        print(f"  ✗ Could not fetch picks: {e}")
        return []

    uid_to_name = {uid: name for uid, name, _ in config.CURRENT_MEMBERS + config.FORMER_MEMBERS}

    picks = []
    for p in raw_picks:
        meta        = p.get("metadata") or {}
        player_name = f"{meta.get('first_name', '')} {meta.get('last_name', '')}".strip()
        position    = meta.get("position", "?")
        user_id_raw = p.get("picked_by", "")
        user_id     = int(user_id_raw) if str(user_id_raw).isdigit() else None
        manager     = uid_to_name.get(user_id, "")

        picks.append({
            "overall_pick": p.get("pick_no"),
            "round":        p.get("round"),
            "round_pick":   p.get("draft_slot"),
            "player_name":  player_name or "?",
            "position":     position,
            "nfl_team":     meta.get("team", ""),
            "team_name":    "",
            "manager_name": manager,
            "user_id":      user_id,
        })

    picks.sort(key=lambda x: x["overall_pick"] or 0)
    print(f"  → Parsed {len(picks)} Sleeper picks")
    return picks


# ══════════════════════════════════════════════════════════════════════════════
#  Save helpers
# ══════════════════════════════════════════════════════════════════════════════

def save_draft(season: int, picks: list) -> None:
    if not picks:
        print(f"  [skip] No picks for {season}")
        return

    data = {"year": season, "picks": picks}

    out = output_path("drafts", f"{season}.json")
    save_json(data, out)
    print(f"  ✓ Saved scraper output → {out}")

    SITE_DATA_DIR.mkdir(parents=True, exist_ok=True)
    site_out = SITE_DATA_DIR / f"{season}.json"
    save_json(data, site_out)
    print(f"  ✓ Saved site data     → {site_out}")


# ══════════════════════════════════════════════════════════════════════════════
#  Main
# ══════════════════════════════════════════════════════════════════════════════

def main():
    print("=" * 70)
    print("07 — PAMS Draft Scraper")
    print("=" * 70)

    session = make_session()

    for season in NFL_SEASONS:
        print(f"\n{'─'*60}")
        print(f"  Season {season} — NFL.com")
        print(f"{'─'*60}")
        picks = scrape_nfl_draft(session, season)
        save_draft(season, picks)

    for season in SLEEPER_SEASONS:
        print(f"\n{'─'*60}")
        print(f"  Season {season} — Sleeper API")
        print(f"{'─'*60}")
        picks = scrape_sleeper_draft(session, season)
        save_draft(season, picks)

    print("\n" + "=" * 70)
    print("Done. Check output/drafts/ and data/drafts/")
    print("=" * 70)


if __name__ == "__main__":
    main()
