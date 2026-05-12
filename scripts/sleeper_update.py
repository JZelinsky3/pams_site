"""
sleeper_update.py — PA Milk Society weekly auto-update.

Runs every Tuesday via GitHub Actions. Pulls from Sleeper API and writes:
  pickems/teams.json          — team roster with Sleeper info
  pickems/manifest.json       — list of available pick-em weeks
  pickems/weeks/week-XX.json  — per-week matchups, records, winners
  powerrank/manifest.json     — list of available power-ranking weeks
  powerrank/weeks/week-XX.json — pre-calculated power rankings

Formula (score = 0–100):
  record    40 pts  — blended (career history fades → current wins by week 5)
  pts_for   30 pts  — percentile rank among all teams
  efficiency 20 pts  — (PF / (PF+PA)) representing margin dominance
  form       10 pts  — win% in last 3 completed weeks
"""

import json
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
import requests

LEAGUE_ID = "1304235036874149888"
BASE = Path(__file__).resolve().parent.parent   # pams_site root
PICKEMS_DIR   = BASE / "pickems"
POWERRANK_DIR = BASE / "powerrank"

# Sleeper user_id → manager slug (update when Chris and Luke join)
SLEEPER_TO_MANAGER = {
    "591884559361040384":  "joey",
    "458329320843112448":  "andrew",
    "609426003600670720":  "kyle",
    "728687640840372224":  "mason",
    "728702248099663872":  "sean",
    "739747288599150592":  "charlie",
    "739751326224969728":  "isaac",
    "868712689332031488":  "connor",
    "1346560472878452736": "evan",
    "1358933101526409216": "connie",
    # "??": "chris",   — add when they join
    # "??": "luke",    — add when they join
}

DISPLAY_NAMES = {
    "joey": "Joey", "andrew": "Andrew", "kyle": "Kyle",
    "mason": "Mason", "sean": "Sean", "charlie": "Charlie",
    "isaac": "Isaac", "connor": "Connor", "evan": "Evan",
    "connie": "Connie", "chris": "Chris", "luke": "Luke",
}

# Career win percentages from pams_site NFL.com historical data (7 seasons)
CAREER_WIN_PCT = {
    "joey":    0.5417,
    "mason":   0.5694,
    "sean":    0.4861,
    "chris":   0.4583,
    "isaac":   0.5556,
    "kyle":    0.5278,
    "connie":  0.4444,
    "charlie": 0.5417,
    "luke":    0.3889,
    "evan":    0.4722,
    "andrew":  0.5833,
    "connor":  0.4444,
}

# NOTE: 2026 NFL Week 1 Thursday is estimated as Sept 3, 2026.
# Update SEASON_FIRST_THURSDAY if the actual date differs once schedule drops.
SEASON_FIRST_THURSDAY = datetime(2026, 9, 3, tzinfo=timezone.utc)


# ── Helpers ──────────────────────────────────────────────────────────────────

def sleeper(path):
    r = requests.get(f"https://api.sleeper.app/v1{path}", timeout=15)
    r.raise_for_status()
    return r.json()


def save(obj, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(obj, f, indent=2)
    print(f"  wrote {path.relative_to(BASE)}")


def week_dates(week_num):
    """(open_at, reveal_at, lock_at) ISO strings for the given NFL week number."""
    thu = SEASON_FIRST_THURSDAY + timedelta(weeks=week_num - 1)
    wed = thu - timedelta(days=1)
    # Use EDT (-04:00) Sep–Nov, EST (-05:00) Dec+
    et = 4 if thu.month < 12 else 5
    offset = f"-0{et}:00"

    def fmt(base_day, hour):
        dt = base_day.replace(hour=hour + et, minute=0, second=0, microsecond=0)
        return dt.strftime("%Y-%m-%dT%H:%M:%S") + offset

    return fmt(wed, 9), fmt(thu, 12), fmt(thu, 20)   # open, reveal, lock


def week_is_started(matchups):
    return any((m.get("points") or 0) > 0 for m in matchups)


def get_records(cum_w, cum_l, slugs):
    return {s: f"{cum_w.get(s, 0)}-{cum_l.get(s, 0)}" for s in slugs}


# ── Team builder ─────────────────────────────────────────────────────────────

def build_teams(rosters, users, league):
    user_map = {u["user_id"]: u for u in users}
    meta = league.get("metadata") or {}
    div_names = {
        1: meta.get("division_1", "Whole"),
        2: meta.get("division_2", "Skim"),
    }
    teams = []
    for r in sorted(rosters, key=lambda x: x["roster_id"]):
        owner_id = r.get("owner_id") or ""
        slug = SLEEPER_TO_MANAGER.get(owner_id, f"team{r['roster_id']}")
        user = user_map.get(owner_id, {})
        umeta = user.get("metadata") or {}

        name = umeta.get("team_name") or user.get("display_name") or DISPLAY_NAMES.get(slug, slug.title())

        avatar = umeta.get("avatar") or user.get("avatar") or ""
        if avatar.startswith("http"):
            logo = avatar
        elif avatar:
            logo = f"https://sleepercdn.com/avatars/{avatar}"
        else:
            logo = "/assets/images/default_team.png"

        div = r["settings"].get("division", 1)
        teams.append({
            "id":              slug,
            "name":            name,
            "manager":         DISPLAY_NAMES.get(slug, slug.title()),
            "roster_id":       r["roster_id"],
            "sleeper_user_id": owner_id,
            "division":        div,
            "division_name":   div_names.get(div, f"Division {div}"),
            "logo":            logo,
        })
    return teams


# ── Matchup processing ───────────────────────────────────────────────────────

def group_matchups(matchups_data):
    groups = defaultdict(list)
    for m in matchups_data:
        groups[m["matchup_id"]].append(m)
    return groups


def build_matchup_list(groups, teams_by_roster):
    out = []
    for mid in sorted(groups.keys()):
        pair = groups[mid]
        if len(pair) == 2:
            slugs = [teams_by_roster.get(p["roster_id"], {}).get("id", f"r{p['roster_id']}") for p in pair]
            out.append({"id": f"m{mid}", "home": slugs[0], "away": slugs[1]})
    return out


def compute_winners(groups, teams_by_roster):
    """Returns (winners_dict, hl_winners) for a completed week."""
    winners = {}
    hl_scores = {}
    for mid, pair in groups.items():
        if len(pair) != 2:
            continue
        a, b = pair
        pa = (a.get("points") or 0)
        pb = (b.get("points") or 0)
        sa = teams_by_roster.get(a["roster_id"], {}).get("id")
        sb = teams_by_roster.get(b["roster_id"], {}).get("id")
        if sa:
            hl_scores[sa] = pa
        if sb:
            hl_scores[sb] = pb
        winner = sa if pa > pb else (sb if pb > pa else None)
        winners[f"m{mid}"] = winner

    if hl_scores:
        hi = max(hl_scores.values())
        lo = min(hl_scores.values())
        hl_winners = {
            "highest": [s for s, p in hl_scores.items() if p == hi],
            "lowest":  [s for s, p in hl_scores.items() if p == lo],
        }
    else:
        hl_winners = {"highest": None, "lowest": None}

    return winners, hl_winners


# ── Power rankings ───────────────────────────────────────────────────────────

def compute_power_rankings(weekly_standings, teams, week_num):
    """
    Score formula (sums to ~100):
      record     40 pts  blended career history (fades by week 5) + current win%
      pts_for    30 pts  PF percentile rank among all 12 teams
      efficiency 20 pts  PF / (PF + PA) — dominance over opponents
      form       10 pts  win% in last 3 completed weeks
    """
    slugs = [t["id"] for t in teams]

    all_pf = [weekly_standings.get(s, {}).get("pf", 0) for s in slugs]
    all_pf_s = sorted(all_pf)
    pf_max = max(all_pf) if all_pf else 1

    def pf_pct(pf):
        if pf_max == 0:
            return 0.5
        rank = sum(1 for x in all_pf_s if x <= pf)
        return rank / max(len(all_pf_s), 1)

    # History weight: 1.0 at week 1 → 0.0 at week 5+
    hist_w = max(0.0, 1.0 - (week_num - 1) / 4.0)

    scored = []
    for t in teams:
        slug = t["id"]
        s = weekly_standings.get(slug, {})
        wins, losses = s.get("wins", 0), s.get("losses", 0)
        pf, pa = s.get("pf", 0.0), s.get("pa", 0.0)
        form = s.get("form", 0.5)
        games = wins + losses

        career = CAREER_WIN_PCT.get(slug, 0.5)
        cur_rec = wins / max(games, 1)
        blended = career * hist_w + cur_rec * (1.0 - hist_w)

        eff = pf / (pf + pa) if (pf + pa) > 0 else 0.5

        score = blended * 40 + pf_pct(pf) * 30 + eff * 20 + form * 10

        scored.append({
            "slug":    slug,
            "score":   round(score, 3),
            "wins":    wins,
            "losses":  losses,
            "pf":      round(pf, 2),
            "pa":      round(pa, 2),
            "factors": {
                "record":     round(blended * 40, 2),
                "pf":         round(pf_pct(pf) * 30, 2),
                "efficiency": round(eff * 20, 2),
                "form":       round(form * 10, 2),
            },
        })

    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    print("=== PA Milk Society — Sleeper Weekly Update ===")

    league  = sleeper(f"/league/{LEAGUE_ID}")
    rosters = sleeper(f"/league/{LEAGUE_ID}/rosters")
    users   = sleeper(f"/league/{LEAGUE_ID}/users")

    status       = league.get("status", "pre_draft")
    current_week = int(league.get("settings", {}).get("leg", 1))
    season       = int(league.get("season", 2026))

    print(f"  Status: {status}  |  Season: {season}  |  Leg: {current_week}")

    teams = build_teams(rosters, users, league)
    teams_by_roster = {t["roster_id"]: t for t in teams}
    all_slugs = [t["id"] for t in teams]

    (PICKEMS_DIR   / "weeks").mkdir(parents=True, exist_ok=True)
    (POWERRANK_DIR / "weeks").mkdir(parents=True, exist_ok=True)
    save({"season": season, "teams": teams}, PICKEMS_DIR / "teams.json")

    if status == "pre_draft":
        print("  Pre-draft — saving teams.json and empty manifests.")
        save({"season": season, "weeks": []}, PICKEMS_DIR   / "manifest.json")
        save({"season": season, "weeks": []}, POWERRANK_DIR / "manifest.json")
        return

    # ── Fetch all matchup weeks ───────────────────────────────────────────
    print(f"\n  Fetching matchup data...")
    all_matchups = {}
    for wk in range(1, current_week + 2):
        try:
            data = sleeper(f"/league/{LEAGUE_ID}/matchups/{wk}")
            if not data:
                break
            all_matchups[wk] = data
            print(f"    week {wk}: {len(data)} entries")
        except Exception as e:
            print(f"    week {wk}: not available ({e})")
            break

    completed_weeks = [wk for wk, data in all_matchups.items() if week_is_started(data)]
    completed_through = max(completed_weeks) if completed_weeks else 0
    upcoming_week = completed_through + 1

    # Try fetching upcoming week if not already in hand
    if upcoming_week not in all_matchups:
        try:
            data = sleeper(f"/league/{LEAGUE_ID}/matchups/{upcoming_week}")
            if data:
                all_matchups[upcoming_week] = data
        except Exception:
            pass

    print(f"\n  Completed through week {completed_through}, upcoming: week {upcoming_week}")

    # ── Process weeks ────────────────────────────────────────────────────
    # Cumulative trackers for power rankings
    cum_w  = defaultdict(int)
    cum_l  = defaultdict(int)
    cum_pf = defaultdict(float)
    cum_pa = defaultdict(float)
    recent = defaultdict(list)   # slug → [1/0, ...] rolling win history

    pick_manifest = []
    pr_manifest   = []

    weeks_to_process = sorted(
        set(list(range(1, completed_through + 1)) +
            ([upcoming_week] if upcoming_week in all_matchups else []))
    )

    for wk in weeks_to_process:
        matchups_data = all_matchups.get(wk, [])
        is_complete   = wk <= completed_through

        print(f"\n  Week {wk} ({'complete' if is_complete else 'upcoming'})...")

        # ── Build matchup list ────────────────────────────────────────────
        groups = group_matchups(matchups_data)
        matchup_list = build_matchup_list(groups, teams_by_roster)

        # ── Cumulative standings update (completed weeks only) ───────────
        if is_complete:
            for mid, pair in groups.items():
                if len(pair) != 2:
                    continue
                a, b = pair
                pa = (a.get("points") or 0)
                pb = (b.get("points") or 0)
                sa = teams_by_roster.get(a["roster_id"], {}).get("id")
                sb = teams_by_roster.get(b["roster_id"], {}).get("id")
                if not sa or not sb:
                    continue
                cum_pf[sa] += pa
                cum_pf[sb] += pb
                cum_pa[sa] += pb
                cum_pa[sb] += pa
                if pa >= pb:
                    cum_w[sa] += 1
                    cum_l[sb] += 1
                    recent[sa].append(1)
                    recent[sb].append(0)
                else:
                    cum_w[sb] += 1
                    cum_l[sa] += 1
                    recent[sb].append(1)
                    recent[sa].append(0)

        # ── Winners ───────────────────────────────────────────────────────
        if is_complete:
            raw_winners, hl_winners = compute_winners(groups, teams_by_roster)
            winners_dict = {m["id"]: raw_winners.get(m["id"]) for m in matchup_list}
        else:
            winners_dict = {m["id"]: None for m in matchup_list}
            hl_winners   = {"highest": None, "lowest": None}

        records = get_records(cum_w, cum_l, all_slugs)

        # ── Save pickems week file ────────────────────────────────────────
        open_at, reveal_at, lock_at = week_dates(wk)
        week_json = {
            "id":                   f"w{wk:02d}",
            "label":                f"Week {wk}",
            "openAt":               open_at,
            "revealAt":             reveal_at,
            "lockAt":               lock_at,
            "records":              records,
            "matchups":             matchup_list,
            "highestLowestOptions": all_slugs,
            "winners":              winners_dict,
            "hlWinners":            hl_winners,
        }
        save(week_json, PICKEMS_DIR / "weeks" / f"week-{wk:02d}.json")
        pick_manifest.append({
            "id":    f"w{wk:02d}",
            "label": f"Week {wk}",
            "data":  f"weeks/week-{wk:02d}.json",
        })

        # ── Power rankings (completed weeks only) ─────────────────────────
        if is_complete:
            weekly_standings = {}
            for t in teams:
                slug = t["id"]
                form_wins = recent[slug][-3:]
                form = sum(form_wins) / max(len(form_wins), 1) if form_wins else 0.5
                weekly_standings[slug] = {
                    "wins":   cum_w[slug],
                    "losses": cum_l[slug],
                    "pf":     cum_pf[slug],
                    "pa":     cum_pa[slug],
                    "form":   form,
                }

            ranked = compute_power_rankings(weekly_standings, teams, wk)

            # Load previous week's ranks for delta
            prev_ranks = {}
            prev_path  = POWERRANK_DIR / "weeks" / f"week-{wk-1:02d}.json"
            if wk > 1 and prev_path.exists():
                with open(prev_path) as f:
                    for r in json.load(f).get("overall", []):
                        prev_ranks[r["team_id"]] = r["rank"]

            full_ranked = []
            for i, r in enumerate(ranked):
                team  = next((t for t in teams if t["id"] == r["slug"]), {})
                prev  = prev_ranks.get(r["slug"])
                delta = (prev - (i + 1)) if prev else 0
                full_ranked.append({
                    "rank":          i + 1,
                    "team_id":       r["slug"],
                    "team_name":     team.get("name", r["slug"]),
                    "manager":       team.get("manager", r["slug"].title()),
                    "logo":          team.get("logo", ""),
                    "division":      team.get("division", 1),
                    "division_name": team.get("division_name", "Whole"),
                    "wins":          r["wins"],
                    "losses":        r["losses"],
                    "pf":            r["pf"],
                    "pa":            r["pa"],
                    "score":         r["score"],
                    "delta":         delta,
                    "factors":       r["factors"],
                })

            pr_data = {
                "week":      wk,
                "label":     f"Week {wk}",
                "season":    season,
                "generated": datetime.now(tz=timezone.utc).isoformat(),
                "overall":   full_ranked,
                "whole":     [r for r in full_ranked if r["division"] == 1],
                "skim":      [r for r in full_ranked if r["division"] == 2],
            }
            save(pr_data, POWERRANK_DIR / "weeks" / f"week-{wk:02d}.json")
            pr_manifest.append({
                "id":    f"w{wk:02d}",
                "label": f"Week {wk}",
                "data":  f"weeks/week-{wk:02d}.json",
            })

    # ── Save manifests ────────────────────────────────────────────────────
    save({"season": season, "weeks": pick_manifest}, PICKEMS_DIR   / "manifest.json")
    save({"season": season, "weeks": pr_manifest},   POWERRANK_DIR / "manifest.json")

    print("\n=== Done! ===")


if __name__ == "__main__":
    main()
