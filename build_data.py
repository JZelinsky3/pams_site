"""
build_data.py — Convert scraper output into site-ready JSON.

Reads from `../nfl_ff_scraper/output/summary/*.json`
Writes to `./data/*.json` for the PAMS site to consume.

Usage:
    python3 build_data.py

Produces:
    data/league.json                    Top-level league info (used by every page)
    data/managers_directory.json        The 12 + 5 alumni list for managers/index.html
    data/managers/<user_id>.json        Individual manager profile (one file each)
    data/seasons_directory.json         Year picker for seasons/index.html
    data/seasons/<year>.json            Per-season standings + champions
    data/record_book.json               Pre-formatted record book for the hub + records page

This script ONLY reads files, never modifies the scraper output. Safe to re-run.
"""

import json
import sys
from collections import defaultdict
from pathlib import Path

# ============================================================
# CONFIG — adjust these paths if your folder structure differs
# ============================================================
HERE = Path(__file__).resolve().parent

# Look for the scraper folder in a few likely places:
#   - inside pams_site/ (current setup — scraper moved as a child)
#   - sibling to pams_site/ (original setup)
SCRAPER_CANDIDATES = [
    HERE / "nfl_ff_scraper",
    HERE / "nfl_ff_scraper",
    HERE.parent / "nfl_ff_scraper",
    HERE.parent / "nfl_ff_scraper",
]
SCRAPER_DIR = None
for candidate in SCRAPER_CANDIDATES:
    if (candidate / "output" / "summary").exists():
        SCRAPER_DIR = candidate
        break
if SCRAPER_DIR is None:
    print("ERROR: Couldn't find scraper output folder.")
    print(f"Looked in: {[str(c) for c in SCRAPER_CANDIDATES]}")
    print("Either move pams_site/ next to your scraper folder, or edit SCRAPER_DIR in this script.")
    sys.exit(1)

SUMMARY_DIR = SCRAPER_DIR / "output" / "summary"
DATA_DIR = HERE / "data"
MANAGERS_OUT = DATA_DIR / "managers"
SEASONS_OUT = DATA_DIR / "seasons"

# Add scraper path so we can import its config (CURRENT_MEMBERS, etc.)
sys.path.insert(0, str(SCRAPER_DIR))
import config  # noqa: E402


# ============================================================
# HELPERS
# ============================================================

def load(name: str):
    """Load a summary JSON file by name."""
    path = SUMMARY_DIR / name
    if not path.exists():
        print(f"  ⚠ Missing: {path}")
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save(obj, path: Path):
    """Save JSON, pretty-formatted."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False, default=str)


def fmt_record(w, l, t=0):
    return f"{w or 0}-{l or 0}-{t or 0}"


def my_name(user_id: int, fallback: str = "") -> str:
    name = config.display_name(user_id)
    return name if name else (fallback or "?")


def name_lookup_map() -> dict:
    """user_id -> {name, nfl_display, is_current, is_former}"""
    out = {}
    for uid, name, nfl_display in config.CURRENT_MEMBERS:
        out[uid] = {"name": name, "nfl_display": nfl_display, "is_current": True, "is_former": False}
    for uid, name, nfl_display in config.FORMER_MEMBERS:
        out[uid] = {"name": name, "nfl_display": nfl_display, "is_current": False, "is_former": True}
    return out


# ============================================================
# DATA LOADING
# ============================================================

print(f"Reading from: {SUMMARY_DIR}")
print(f"Writing to:   {DATA_DIR}")
print()

matchups = load("../matchups_all.json")  # one level up in output/
if matchups is None:
    matchups = json.load(open(SCRAPER_DIR / "output" / "matchups_all.json", "r"))

standings = json.load(open(SCRAPER_DIR / "output" / "standings_all_seasons.json", "r"))
manager_summary = load("manager_career_summary.json") or []
record_book = load("record_book.json") or {}
career_extras = load("career_extras.json") or []
season_extremes = load("season_extremes.json") or []
h2h_matrix = load("h2h_matrix.json") or {}
streaks = load("manager_streaks.json") or []

print(f"  Loaded {len(matchups)} matchup rows")
print(f"  Loaded {len(standings)} standings rows")
print(f"  Loaded {len(manager_summary)} manager summary rows")
print()

names = name_lookup_map()


# ============================================================
# 1. LEAGUE.JSON — top-level info for hub
# ============================================================

print("Building data/league.json ...")

# Find defending champion
defending = None
seasons_sorted = sorted(set(s["season"] for s in standings if s.get("final_rank")), reverse=True)
for yr in seasons_sorted:
    chip_row = next(
        (s for s in standings if s["season"] == yr and s.get("final_rank") == 1),
        None,
    )
    if chip_row:
        defending = chip_row
        break

# Get the user_id of the defending champion
def season_team_to_uid(season, team_id):
    for m in matchups:
        if m["season"] == season and m["team_id"] == team_id:
            return m.get("user_id")
    return None

defending_uid = season_team_to_uid(defending["season"], defending["team_id"]) if defending else None
defending_name = my_name(defending_uid) if defending_uid else (defending.get("owner") if defending else "")

league = {
    "name": "The Milk Society",
    "abbreviation": "PAMS",
    "founded": 2019,
    "current_season": max(s["season"] for s in standings),
    "total_matchups": len(matchups) // 2,
    "total_seasons": len(set(s["season"] for s in standings)),
    "current_members_count": len(config.CURRENT_MEMBERS),
    "former_members_count": len(config.FORMER_MEMBERS),
    "all_seasons": sorted(set(s["season"] for s in standings)),
    "defending_champion": {
        "year": defending["season"] if defending else None,
        "team_name": defending["team_name"] if defending else "",
        "owner_name": defending_name,
        "owner_user_id": defending_uid,
        "record": fmt_record(defending["wins"], defending["losses"], defending["ties"]) if defending else "",
        "points_for": defending["points_for"] if defending else 0,
    } if defending else None,
}
save(league, DATA_DIR / "league.json")
print(f"  ✓ Saved")


# ============================================================
# 2. RECORD_BOOK.JSON — formatted for site display
# ============================================================

print("Building data/record_book.json ...")

# We translate each record into the format the hub's records array uses
def format_weekly_record(r, prose_template, label):
    """Turn a record_book weekly entry into the {label, value, name, detail, prose, gameContext} shape."""
    if not r:
        return None
    return {
        "label": label,
        "value": str(r.get("score") or r.get("margin") or r.get("combined_score") or "?"),
        "name": f"<em>{r['owner']}</em>" + (
            f" over {r['opp_owner']}" if r.get("result") == "W"
            else f", defeated" if r.get("result") == "L"
            else ""
        ),
        "detail": f"{r['season']} · W{r['week']} · {r['score']}–{r.get('opp_score','?')}",
        "prose": prose_template.format(**r),
        "gameContext": f"{r['season']} · Week {r['week']} · {r['score']}–{r.get('opp_score','?')}",
    }


def fmt_score(x):
    if x is None: return "?"
    if isinstance(x, float) and x == int(x):
        return str(int(x))
    return f"{x:.2f}".rstrip("0").rstrip(".")


def first(lst):
    return lst[0] if lst else None


hub_records = []

# 1. Highest single-week score
r = first(record_book.get("weekly", {}).get("highest_single_week_score", []))
if r:
    hub_records.append({
        "label": "Highest Single-Week Score",
        "value": fmt_score(r["score"]),
        "name": f"<em>{r['owner']}</em>, untouchable",
        "detail": f"{r['season']} · W{r['week']} · vs {r['opp_owner']}",
        "prose": f"<strong>{r['owner']}</strong> dropped {fmt_score(r['score'])} on {r['opp_owner']} in week {r['week']} of the {r['season']} season — still the only manager to break the barrier.",
        "gameContext": f"{r['season']} · Week {r['week']} · {fmt_score(r['score'])}—{fmt_score(r['opp_score'])}",
    })

# 2. Biggest blowout
r = first(record_book.get("weekly", {}).get("biggest_blowouts", []))
if r:
    hub_records.append({
        "label": "Biggest Blowout",
        "value": fmt_score(r["margin"]),
        "name": f"<em>{r['owner']}</em> over {r['opp_owner']}",
        "detail": f"{r['season']} · W{r['week']} · {fmt_score(r['score'])}—{fmt_score(r['opp_score'])}",
        "prose": f"<strong>{r['owner']}</strong> hung {fmt_score(r['score'])} on {r['opp_owner']} in week {r['week']} of {r['season']}, {fmt_score(r['margin'])} points clear — the most lopsided beating in league history.",
        "gameContext": f"{r['season']} · Week {r['week']} · {fmt_score(r['score'])}—{fmt_score(r['opp_score'])}",
    })

# 3. Longest win streak
r = first(record_book.get("career", {}).get("longest_win_streaks", []))
if r:
    hub_records.append({
        "label": "Longest Win Streak",
        "value": str(r["length"]),
        "name": f"<em>{r['owner']}</em> — {r['start_season']} run",
        "detail": f"Weeks {r['start_week']} through {r['end_week']}, undefeated",
        "prose": f"<strong>{r['owner']}</strong> ran the table for {r['length']} straight in {r['start_season']}, weeks {r['start_week']} through {r['end_week']} — the longest unbroken stretch any manager has put together.",
        "gameContext": f"{r['start_season']} · W{r['start_week']} → W{r['end_week']} · {r['length']} straight wins",
    })

# 4. Highest season PF
r = first(record_book.get("season", {}).get("highest_season_pf", []))
if r:
    ppg = r.get("avg_ppg", 0)
    hub_records.append({
        "label": "Highest Season Total",
        "value": f"{int(r['total_pf']):,}",
        "name": f"<em>{r['owner']}</em> — \"{r['team_name']}\"",
        "detail": f"{r['season']} · {ppg} ppg avg",
        "prose": f"<strong>{r['owner']}</strong>'s {r['season']} \"{r['team_name']}\" squad piled up {int(r['total_pf']):,} points across the year, averaging {int(ppg)} a game — the highest single-season output in league history.",
        "gameContext": f"{r['season']} Season · {int(r['total_pf']):,} PF · {ppg} ppg",
    })

# 5. Closest game
r = first(record_book.get("weekly", {}).get("closest_games", []))
if r:
    hub_records.append({
        "label": "Closest Game Ever",
        "value": fmt_score(r["margin"]),
        "name": f"<em>{r['owner']}</em> over {r['opp_owner']}",
        "detail": f"{r['season']} · W{r['week']} · {fmt_score(r['score'])}—{fmt_score(r['opp_score'])}",
        "prose": f"<strong>{r['owner']}</strong> edged {r['opp_owner']} by {fmt_score(r['margin'])} in week {r['week']} of {r['season']} — the smallest possible margin in fantasy football.",
        "gameContext": f"{r['season']} · Week {r['week']} · {fmt_score(r['score'])}—{fmt_score(r['opp_score'])}",
    })

# 6. Unluckiest loss
r = first(record_book.get("weekly", {}).get("unluckiest_losses", []))
if r:
    hub_records.append({
        "label": "Unluckiest Loss",
        "value": fmt_score(r["score"]),
        "name": f"<em>{r['owner']}</em>, defeated",
        "detail": f"{r['season']} · W{r['week']} · Lost to {r['opp_owner']} ({fmt_score(r['opp_score'])})",
        "prose": f"<strong>{r['owner']}</strong> put up {fmt_score(r['score'])} points in week {r['week']} of {r['season']} — a top-twenty score in league history — and still lost to {r['opp_owner']}, who somehow scored {fmt_score(r['opp_score'])}.",
        "gameContext": f"{r['season']} · Week {r['week']} · {fmt_score(r['score'])}—{fmt_score(r['opp_score'])} L",
    })

# 7. Shootout
r = first(record_book.get("weekly", {}).get("highest_combined_score", []))
if r:
    hub_records.append({
        "label": "Shootout (Highest Combined)",
        "value": fmt_score(r["combined_score"]),
        "name": f"<em>{r['owner']}</em> vs {r['opp_owner']}",
        "detail": f"{r['season']} · W{r['week']} · {fmt_score(r['score'])}—{fmt_score(r['opp_score'])}",
        "prose": f"<strong>{r['owner']}</strong> and <strong>{r['opp_owner']}</strong> combined for {fmt_score(r['combined_score'])} points in week {r['week']} of {r['season']} — the highest-scoring matchup ever played in the league.",
        "gameContext": f"{r['season']} · Week {r['week']} · {fmt_score(r['score'])}—{fmt_score(r['opp_score'])}",
    })

# 8. Longest losing streak
r = first(record_book.get("career", {}).get("longest_loss_streaks", []))
if r:
    hub_records.append({
        "label": "Longest Losing Streak",
        "value": str(r["length"]),
        "name": f"<em>{r['owner']}</em>'s nightmare",
        "detail": f"W{r['start_week']} {r['start_season']} → W{r['end_week']} {r['end_season']}",
        "prose": f"<strong>{r['owner']}</strong> went on a brutal {r['length']}-game losing slide spanning {r['start_season']} into {r['end_season']} — the longest cold stretch any manager has endured.",
        "gameContext": f"{r['start_season']}–{r['end_season']} · {r['length']} straight losses",
    })

save({
    "hub_records": hub_records,
    "full_book": record_book,
}, DATA_DIR / "record_book.json")
print(f"  ✓ Saved {len(hub_records)} hub records")


# ============================================================
# 3. MANAGERS_DIRECTORY.JSON — list for managers/index.html
# ============================================================

# Compute playoff appearances from standings.
# 2020 used a top-8 bracket; every other season used top-6.
_PO_CUTOFF = {2020: 8}
uid_playoff_apps: dict = defaultdict(int)
for _s in standings:
    _rank = _s.get("final_rank")
    if _rank is None:
        continue
    _cutoff = _PO_CUTOFF.get(_s["season"], 6)
    if _rank <= _cutoff:
        _uid = season_team_to_uid(_s["season"], _s["team_id"])
        if _uid:
            uid_playoff_apps[_uid] += 1

print("Building data/managers_directory.json ...")

# Build a quick uid -> career_extras lookup
extras_by_uid = {c["user_id"]: c for c in career_extras}
summary_by_uid = {m["user_id"]: m for m in manager_summary}

# For each member (current + former), build the directory entry
directory_entries = []

def build_directory_entry(uid, name, nfl_display, is_current):
    summary = summary_by_uid.get(uid, {})
    extras = extras_by_uid.get(uid, {})

    # Latest team name — most recent matchup row for this user
    latest_matchup = None
    for m in sorted(matchups, key=lambda x: (x["season"], x["week"]), reverse=True):
        if m.get("user_id") == uid:
            latest_matchup = m
            break

    # Parse "W-L-T" from total_record
    total_record = summary.get("total_record", "0-0-0")
    parts = total_record.split("-")
    try:
        wins, losses, ties = int(parts[0]), int(parts[1]), int(parts[2]) if len(parts) > 2 else 0
    except (ValueError, IndexError):
        wins, losses, ties = 0, 0, 0

    games = wins + losses + ties
    win_pct = wins / games if games else 0

    # Total PF (sum of reg + post)
    total_pf = (summary.get("reg_pf", 0) or 0) + (summary.get("post_pf", 0) or 0)

    return {
        "user_id": uid,
        "name": name,
        "nfl_display_name": nfl_display,
        "team_latest": latest_matchup["team_name"] if latest_matchup else "—",
        "is_current": is_current,
        "seasons_played": summary.get("seasons_played", extras.get("seasons_played", 0)),
        "wins": wins,
        "losses": losses,
        "ties": ties,
        "total_record": total_record,
        "win_pct": round(win_pct, 4),
        "total_pf": round(total_pf, 2),
        "championships": summary.get("championships", 0),
        "championship_seasons": [int(y) for y in str(summary.get("championship_seasons", "")).split(",") if y],
        "top_three_finishes": summary.get("top_3_finishes", 0),
        "playoff_appearances": uid_playoff_apps.get(uid, 0),
    }

for uid, name, nfl_display in config.CURRENT_MEMBERS:
    directory_entries.append(build_directory_entry(uid, name, nfl_display, True))
for uid, name, nfl_display in config.FORMER_MEMBERS:
    directory_entries.append(build_directory_entry(uid, name, nfl_display, False))

save({
    "managers": directory_entries,
}, DATA_DIR / "managers_directory.json")
print(f"  ✓ Saved {len(directory_entries)} entries ({sum(1 for e in directory_entries if e['is_current'])} current, {sum(1 for e in directory_entries if not e['is_current'])} alumni)")


# ============================================================
# 4. INDIVIDUAL MANAGER PROFILES (one JSON per user_id)
# ============================================================

print(f"Building data/managers/<user_id>.json ...")

# Group matchups by user
matchups_by_uid = defaultdict(list)
for m in matchups:
    uid = m.get("user_id")
    if uid is None: continue
    matchups_by_uid[uid].append(m)

# Group standings by team-season
standings_by_season_team = {}
for s in standings:
    standings_by_season_team[(s["season"], s["team_id"])] = s

# Group season_extremes by uid
extremes_by_uid = defaultdict(list)
for se in season_extremes:
    extremes_by_uid[se["user_id"]].append(se)


def build_profile(uid: int, name: str, nfl_display: str, is_current: bool) -> dict:
    user_matchups = matchups_by_uid.get(uid, [])
    summary = summary_by_uid.get(uid, {})
    extras = extras_by_uid.get(uid, {})

    # Parse total record
    total_record = summary.get("total_record", "0-0-0")
    parts = total_record.split("-")
    try:
        wins, losses, ties = int(parts[0]), int(parts[1]), int(parts[2]) if len(parts) > 2 else 0
    except (ValueError, IndexError):
        wins, losses, ties = 0, 0, 0
    total_games = wins + losses + ties

    # High/low scores
    scores = [m["team_score"] for m in user_matchups if m["team_score"] is not None]
    high_score = max(scores) if scores else None
    low_score = min(scores) if scores else None
    avg_ppg = round(sum(scores) / len(scores), 2) if scores else None

    # Season ledger
    user_seasons = sorted(extremes_by_uid.get(uid, []), key=lambda s: s["season"])
    season_ledger = []
    for s in user_seasons:
        season_ledger.append({
            "year": s["season"],
            "team_name": s["team_name"],
            "final_rank": s.get("final_rank"),
            "reg_season_rank": s.get("reg_season_rank"),
            "reg_record": s.get("reg_record", "—"),
            "reg_pf": s.get("reg_pf"),
            "reg_pa": s.get("reg_pa"),
            "playoff_record": s.get("playoff_record", "—"),
            "playoff_games": s.get("playoff_games", 0),
            "playoff_pf": s.get("playoff_pf"),
            "total_pf": s.get("total_pf"),
            "avg_ppg": s.get("avg_ppg"),
            "high_week_score": s.get("high_week_score"),
            "low_week_score": s.get("low_week_score"),
        })

    # H2H against the current 12 (and former members where applicable)
    h2h_for_user = h2h_matrix.get(str(uid), {}).get("opponents", {})
    h2h_list = []
    for opp_uid_str, h in h2h_for_user.items():
        h2h_list.append({
            "opp_user_id": int(opp_uid_str),
            "opp_name": h.get("b_name", ""),
            "reg_record": h.get("reg_record", "0-0-0"),
            "reg_pf": h.get("reg_pf", 0),
            "reg_pa": h.get("reg_pa", 0),
            "playoff_record": h.get("playoff_record", "0-0-0"),
            "playoff_pf": h.get("playoff_pf", 0),
            "playoff_pa": h.get("playoff_pa", 0),
            "total_record": h.get("total_record", "0-0-0"),
            "total_games": h.get("total_games", 0),
        })
    h2h_list.sort(key=lambda x: x["total_games"], reverse=True)

    # Championship years
    chip_seasons = []
    for s in user_seasons:
        if s.get("final_rank") == 1:
            chip_seasons.append(s["season"])

    # Win pct stats
    reg_wins = sum(int(s["reg_record"].split("-")[0]) for s in user_seasons if "-" in s.get("reg_record", ""))
    reg_losses = sum(int(s["reg_record"].split("-")[1]) for s in user_seasons if "-" in s.get("reg_record", ""))
    reg_ties = sum(int(s["reg_record"].split("-")[2]) for s in user_seasons if s.get("reg_record","").count("-") >= 2)
    post_wins = sum(int(s["playoff_record"].split("-")[0]) for s in user_seasons if "-" in s.get("playoff_record", ""))
    post_losses = sum(int(s["playoff_record"].split("-")[1]) for s in user_seasons if "-" in s.get("playoff_record", ""))
    post_ties = sum(int(s["playoff_record"].split("-")[2]) for s in user_seasons if s.get("playoff_record","").count("-") >= 2)

    reg_g = reg_wins + reg_losses + reg_ties
    post_g = post_wins + post_losses + post_ties

    return {
        "user_id": uid,
        "name": name,
        "nfl_display_name": nfl_display,
        "is_current": is_current,
        "tagline": f"{summary.get('seasons_played', 0)} seasons of league history. " + (
            f"{summary.get('championships', 0)} championship{'s' if summary.get('championships',0) != 1 else ''}." if summary.get('championships', 0) > 0
            else "Still chasing the first chip."
        ),
        "seasons_played": summary.get("seasons_played", 0),
        "total_games": total_games,
        "championships": summary.get("championships", 0),
        "championship_seasons": chip_seasons,
        "top_three_finishes": summary.get("top_3_finishes", 0),
        "playoff_appearances": uid_playoff_apps.get(uid, 0),

        "reg_record": fmt_record(reg_wins, reg_losses, reg_ties),
        "reg_win_pct": round(reg_wins / reg_g, 4) if reg_g else 0,
        "reg_pf": round(summary.get("reg_pf", 0) or 0, 2),
        "reg_pa": round(summary.get("reg_pa", 0) or 0, 2),

        "playoff_record": fmt_record(post_wins, post_losses, post_ties),
        "playoff_win_pct": round(post_wins / post_g, 4) if post_g else 0,
        "playoff_pf": round(summary.get("post_pf", 0) or 0, 2),
        "playoff_pa": round(summary.get("post_pa", 0) or 0, 2),

        "high_score": high_score,
        "low_score": low_score,
        "avg_ppg": avg_ppg,

        "longest_win_streak": {
            "length": extras.get("longest_win_streak", 0),
            "when": extras.get("longest_win_streak_when", ""),
        },
        "longest_loss_streak": {
            "length": extras.get("longest_loss_streak", 0),
            "when": extras.get("longest_loss_streak_when", ""),
        },

        "season_ledger": season_ledger,
        "h2h": h2h_list,
    }


saved_profiles = 0
for uid, name, nfl_display in config.CURRENT_MEMBERS + config.FORMER_MEMBERS:
    is_current = config.is_current_member(uid)
    profile = build_profile(uid, name, nfl_display, is_current)
    save(profile, MANAGERS_OUT / f"{uid}.json")
    saved_profiles += 1
print(f"  ✓ Saved {saved_profiles} manager profiles")


# ============================================================
# 5. SEASONS_DIRECTORY.JSON + per-season JSON files
# ============================================================

print("Building season files ...")

# Group standings by season
standings_by_season = defaultdict(list)
for s in standings:
    standings_by_season[s["season"]].append(s)

seasons_dir_entries = []
for year in sorted(standings_by_season.keys()):
    rows = standings_by_season[year]
    champ_row = next((s for s in rows if s.get("final_rank") == 1), None)
    runner_up = next((s for s in rows if s.get("final_rank") == 2), None)
    third = next((s for s in rows if s.get("final_rank") == 3), None)

    def name_from_team(row):
        if not row: return ""
        uid = season_team_to_uid(row["season"], row["team_id"])
        return my_name(uid, row.get("owner", ""))

    # Build full season detail file
    season_detail = {
        "year": year,
        "total_teams": len(rows),
        "champion": {
            "team_name": champ_row["team_name"] if champ_row else "",
            "owner_name": name_from_team(champ_row),
            "owner_user_id": season_team_to_uid(year, champ_row["team_id"]) if champ_row else None,
            "record": fmt_record(champ_row["wins"], champ_row["losses"], champ_row["ties"]) if champ_row else "",
            "points_for": champ_row["points_for"] if champ_row else 0,
        } if champ_row else None,
        "runner_up": {
            "team_name": runner_up["team_name"] if runner_up else "",
            "owner_name": name_from_team(runner_up),
            "owner_user_id": season_team_to_uid(year, runner_up["team_id"]) if runner_up else None,
        } if runner_up else None,
        "third_place": {
            "team_name": third["team_name"] if third else "",
            "owner_name": name_from_team(third),
            "owner_user_id": season_team_to_uid(year, third["team_id"]) if third else None,
        } if third else None,
        "standings": [
            {
                "final_rank": r.get("final_rank"),
                "reg_season_rank": r.get("overall_rank_reg_season"),
                "team_id": r["team_id"],
                "team_name": r["team_name"],
                "owner_name": name_from_team(r),
                "owner_user_id": season_team_to_uid(year, r["team_id"]),
                "division": r.get("division", ""),
                "wins": r.get("wins"),
                "losses": r.get("losses"),
                "ties": r.get("ties"),
                "win_pct": r.get("win_pct"),
                "points_for": r.get("points_for"),
                "points_against": r.get("points_against"),
            }
            for r in sorted(rows, key=lambda x: x.get("final_rank") or 99)
        ],
    }
    save(season_detail, SEASONS_OUT / f"{year}.json")

    # Add to directory
    seasons_dir_entries.append({
        "year": year,
        "champion_name": name_from_team(champ_row),
        "champion_team_name": champ_row["team_name"] if champ_row else "",
        "champion_user_id": season_team_to_uid(year, champ_row["team_id"]) if champ_row else None,
        "total_teams": len(rows),
        "has_complete_data": champ_row is not None,
    })

save({"seasons": seasons_dir_entries}, DATA_DIR / "seasons_directory.json")
print(f"  ✓ Saved {len(seasons_dir_entries)} seasons")


# ============================================================
# DRAFT DATA — copy from scraper output if available
# ============================================================
DRAFTS_SCRAPER = SCRAPER_DIR / "output" / "drafts"
DRAFTS_OUT = DATA_DIR / "drafts"
draft_files_copied = 0

if DRAFTS_SCRAPER.exists():
    print()
    print("Building draft files ...")
    DRAFTS_OUT.mkdir(parents=True, exist_ok=True)
    years_index = []
    for draft_file in sorted(DRAFTS_SCRAPER.glob("*.json")):
        dest = DRAFTS_OUT / draft_file.name
        data = json.loads(draft_file.read_text(encoding="utf-8"))
        save(data, dest)
        draft_files_copied += 1
        year = data.get("year")
        if year:
            years_index.append({
                "year": year,
                "total_picks": len(data.get("picks", [])),
                "rounds": max((p.get("round") or 0 for p in data.get("picks", [])), default=0),
            })
        print(f"  ✓ Saved data/drafts/{draft_file.name}")
    if years_index:
        save({"drafts": sorted(years_index, key=lambda x: x["year"])},
             DRAFTS_OUT / "drafts_directory.json")
        print(f"  ✓ Saved data/drafts/drafts_directory.json")
else:
    print()
    print("  (Skipping draft files — run 07_scrape_drafts.py first)")


# ============================================================
# DONE
# ============================================================
print()
print("=" * 60)
print("✓ Build complete!")
print("=" * 60)
print(f"  data/league.json")
print(f"  data/record_book.json")
print(f"  data/managers_directory.json")
print(f"  data/managers/*.json  ({saved_profiles} files)")
print(f"  data/seasons_directory.json")
print(f"  data/seasons/*.json  ({len(seasons_dir_entries)} files)")
if draft_files_copied:
    print(f"  data/drafts/*.json  ({draft_files_copied} files)")
print()
print("Next: refresh your pams_site pages in the browser.")
print("They'll now load real data automatically.")