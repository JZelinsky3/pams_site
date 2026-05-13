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
import math
import random
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
import requests

LEAGUE_ID = "1304235036874149888"
BASE = Path(__file__).resolve().parent.parent   # pams_site root
PICKEMS_DIR   = BASE / "pickems"
POWERRANK_DIR = BASE / "powerrank"

# Sleeper user_id → manager slug (update when Luke and Charlie join)
SLEEPER_TO_MANAGER = {
    "591884559361040384":  "joey",
    "458329320843112448":  "andrew",
    "609426003600670720":  "kyle",
    "728687640840372224":  "mason",
    "728702248099663872":  "sean",
    "739747288599150592":  "chris",
    "739751326224969728":  "isaac",
    "868712689332031488":  "connor",
    "1346560472878452736": "evan",
    "1358933101526409216": "connie",
    # "??": "luke",    — add when they join
    # "??": "charlie", — add when they join
}

DISPLAY_NAMES = {
    "joey": "Joey", "andrew": "Andrew", "kyle": "Kyle",
    "mason": "Mason", "sean": "Sean", "charlie": "Charlie",
    "isaac": "Isaac", "connor": "Connor", "evan": "Evan",
    "connie": "Connie", "chris": "Chris", "luke": "Luke",
}

LOGO_FALLBACK = {
    "joey":    "/assets/images/logos/gooners.png",
    "mason":   "/assets/images/logos/rizzlers2.png",
    "sean":    "/assets/images/logos/thefamilyguy2.png",
    "chris":   "/assets/images/logos/kylerthecreator.png",
    "isaac":   "/assets/images/logos/childofgod2.png",
    "kyle":    "/assets/images/logos/gingerninger2.png",
    "connie":  "/assets/images/logos/tequilasunrise.png",
    "charlie": "/assets/images/logos/moneygod2.png",
    "luke":    "/assets/images/logos/theglizzys2.png",
    "evan":    "/assets/images/logos/whiteboyfootball2.png",
    "andrew":  "/assets/images/logos/bodix2.png",
    "connor":  "/assets/images/logos/thepeoplestightend2.png",
}

# Historical stats from managers_directory.json (7 NFL.com seasons through 2025)
# recent_finishes: [2023 finish, 2024 finish, 2025 finish]
# Playoff finish if they made playoffs that year, regular-season rank if they didn't.
HISTORICAL = {
    "joey":    {"win_pct": 0.566,  "pf": 13621.96, "seasons": 7, "champs": 1, "top3": 4, "playoffs": 7, "recent_finishes": [12, 8, 6]},
    "mason":   {"win_pct": 0.5728, "pf": 12732.62, "seasons": 7, "champs": 1, "top3": 2, "playoffs": 7, "recent_finishes": [8, 12, 1]},
    "sean":    {"win_pct": 0.5673, "pf": 12954.28, "seasons": 7, "champs": 0, "top3": 2, "playoffs": 7, "recent_finishes": [3, 4, 10]},
    "chris":   {"win_pct": 0.534,  "pf": 12883.44, "seasons": 7, "champs": 1, "top3": 2, "playoffs": 7, "recent_finishes": [9, 5, 9]},
    "isaac":   {"win_pct": 0.5556, "pf": 11128.66, "seasons": 6, "champs": 1, "top3": 2, "playoffs": 6, "recent_finishes": [2, 11, 5]},
    "kyle":    {"win_pct": 0.4571, "pf": 12446.44, "seasons": 7, "champs": 0, "top3": 0, "playoffs": 6, "recent_finishes": [11, 9, 4]},
    "connie":  {"win_pct": 0.4904, "pf": 12661.06, "seasons": 7, "champs": 1, "top3": 3, "playoffs": 7, "recent_finishes": [1, 6, 2]},
    "charlie": {"win_pct": 0.47,   "pf": 11722.4,  "seasons": 7, "champs": 0, "top3": 0, "playoffs": 7, "recent_finishes": [4, 7, 6]},
    "luke":    {"win_pct": 0.4659, "pf": 10137.52, "seasons": 6, "champs": 1, "top3": 1, "playoffs": 6, "recent_finishes": [6, 1, 12]},
    "evan":    {"win_pct": 0.3953, "pf": 4957.06,  "seasons": 3, "champs": 0, "top3": 0, "playoffs": 3, "recent_finishes": [5, 10, 11]},
    "andrew":  {"win_pct": 0.4904, "pf": 12565.92, "seasons": 7, "champs": 1, "top3": 3, "playoffs": 7, "recent_finishes": [10, 2, 3]},
    "connor":  {"win_pct": 0.44,   "pf": 12259.4,  "seasons": 7, "champs": 0, "top3": 1, "playoffs": 7, "recent_finishes": [7, 3, 5]},
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

        # Use Sleeper team_name if set; otherwise fall back to manager's display name (not username)
        name = umeta.get("team_name") or DISPLAY_NAMES.get(slug, slug.title())

        avatar = umeta.get("avatar") or user.get("avatar") or ""
        if avatar.startswith("http"):
            logo = avatar
        elif avatar:
            logo = f"https://sleepercdn.com/avatars/{avatar}"
        else:
            logo = LOGO_FALLBACK.get(slug, "/assets/images/default_team.png")

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

def compute_historical_score(slug):
    """
    0-100 score based solely on career history.
      Win%        20 pts  — all-time win percentage
      PF Avg      20 pts  — percentile rank on avg points-per-season
      Recent      26 pts  — avg finish over last 3 seasons (2023–2025)
      Pedigree    34 pts  — championships (14) + top-3 rate (12) + playoff rate (8)
    """
    h = HISTORICAL.get(slug)
    if not h:
        return 50.0

    all_pf_avgs = [d["pf"] / d["seasons"] for d in HISTORICAL.values()]
    my_pf_avg   = h["pf"] / h["seasons"]
    pf_pct_rank = sum(1 for x in all_pf_avgs if x <= my_pf_avg) / len(all_pf_avgs)

    avg_finish  = sum(h["recent_finishes"]) / len(h["recent_finishes"])
    win_pts     = h["win_pct"] * 20
    pf_pts      = pf_pct_rank * 20
    recent_pts  = (12 - avg_finish) / 11 * 26
    ped_pts     = (min(h["champs"], 1) * 14
                   + (h["top3"]    / h["seasons"]) * 12
                   + (h["playoffs"] / h["seasons"]) * 8)

    return win_pts + pf_pts + recent_pts + ped_pts


def simulate_projections(scores, teams, n_weeks=14, playoff_spots=6, bye_spots=2, n_sims=8000):
    """
    Monte Carlo season simulation. Returns per-team proj_wins, proj_losses,
    playoff_pct, bye_pct, and conf_win_pct.
    Playoffs: top 3 from each division (not top 6 overall).
    Byes: top 2 seeds overall.
    """
    team_ids   = list(scores.keys())
    n_teams    = len(team_ids)
    div_map    = {t["id"]: t["division"] for t in teams}
    divisions  = sorted(set(div_map.values()))
    spots_per_div = playoff_spots // len(divisions)

    playoff_cnt  = {tid: 0 for tid in team_ids}
    bye_cnt      = {tid: 0 for tid in team_ids}
    conf_win_cnt = {tid: 0 for tid in team_ids}

    for _ in range(n_sims):
        wins   = {tid: 0   for tid in team_ids}
        pf_sim = {tid: 0.0 for tid in team_ids}

        for _ in range(n_weeks):
            pool = list(team_ids)
            random.shuffle(pool)
            for i in range(0, n_teams, 2):
                a, b = pool[i], pool[i + 1]
                sa = scores[a] * max(0.3, 1 + random.gauss(0, 0.15))
                sb = scores[b] * max(0.3, 1 + random.gauss(0, 0.15))
                if sa > sb:
                    wins[a] += 1
                else:
                    wins[b] += 1
                pf_sim[a] += sa
                pf_sim[b] += sb

        # Playoffs: top N from each division
        for div in divisions:
            div_t = [tid for tid in team_ids if div_map.get(tid) == div]
            sorted_div = sorted(div_t, key=lambda t: (-wins[t], -pf_sim[t]))
            for tid in sorted_div[:spots_per_div]:
                playoff_cnt[tid] += 1

        # Byes: top 2 seeds overall by record
        sorted_all = sorted(team_ids, key=lambda t: (-wins[t], -pf_sim[t]))
        for tid in sorted_all[:bye_spots]:
            bye_cnt[tid] += 1

        # Conference title: best record within each division
        for div in divisions:
            div_t = [tid for tid in team_ids if div_map.get(tid) == div]
            winner = max(div_t, key=lambda t: (wins[t], pf_sim[t]))
            conf_win_cnt[winner] += 1

    # Analytical expected wins
    proj = {}
    for tid in team_ids:
        opp = [scores[b] for b in team_ids if b != tid]
        avg_wp = sum(scores[tid] / (scores[tid] + s) for s in opp) / len(opp)
        pw_r = round(avg_wp * n_weeks)
        proj[tid] = {
            "proj_wins":    pw_r,
            "proj_losses":  n_weeks - pw_r,
            "playoff_pct":  round(playoff_cnt[tid]  / n_sims * 100, 1),
            "bye_pct":      round(bye_cnt[tid]       / n_sims * 100, 1),
            "conf_win_pct": round(conf_win_cnt[tid]  / n_sims * 100, 1),
        }
    return proj


def compute_power_rankings(weekly_standings, teams, week_num,
                           n_weeks=14, playoff_spots=6, bye_spots=2):
    """
    Preseason (week 0): 100% history score (win%, PF avg, pedigree).
    Week 1-3:  blended history + current, history fades to 0 by week 4.
    Week 4+:   record 35 + PF percentile 35 + form 15 + conference rank 15.
    """
    slugs  = [t["id"] for t in teams]
    all_pf = [weekly_standings.get(s, {}).get("pf", 0) for s in slugs]
    all_pf_s = sorted(all_pf)
    pf_max   = max(all_pf) if any(all_pf) else 1

    def pf_pct(pf):
        if pf_max == 0:
            return 0.5
        return sum(1 for x in all_pf_s if x <= pf) / max(len(all_pf_s), 1)

    # History weight: full preseason, fades each week, gone by week 4
    if week_num == 0:
        hist_w = 1.0
    elif week_num == 1:
        hist_w = 0.30
    elif week_num == 2:
        hist_w = 0.20
    elif week_num == 3:
        hist_w = 0.10
    else:
        hist_w = 0.0

    # ── Pass 1: base scores (no conf component yet) ───────────────────────
    base = {}
    for t in teams:
        slug = t["id"]
        s    = weekly_standings.get(slug, {})
        wins, losses = s.get("wins", 0), s.get("losses", 0)
        pf   = s.get("pf", 0.0)
        form = s.get("form", 0.5)
        games = wins + losses

        hist_s = compute_historical_score(slug)
        if hist_w >= 1.0:
            base[slug] = hist_s
        else:
            cur_rec    = (wins / games) if games else 0.0
            cur_score  = cur_rec * 35 + pf_pct(pf) * 35 + form * 15 + 7.5  # conf placeholder
            base[slug] = hist_w * hist_s + (1 - hist_w) * cur_score

    # ── Conference rank within each division ─────────────────────────────
    div_teams = {}
    for t in teams:
        div_teams.setdefault(t["division"], []).append(t["id"])
    conf_rank = {}
    for div, members in div_teams.items():
        for i, slug in enumerate(sorted(members, key=lambda s: -base[s])):
            conf_rank[slug] = i + 1

    # ── Pass 2: final scores with real conf component ─────────────────────
    final = {}
    for t in teams:
        slug  = t["id"]
        s     = weekly_standings.get(slug, {})
        wins, losses = s.get("wins", 0), s.get("losses", 0)
        pf    = s.get("pf", 0.0)
        form  = s.get("form", 0.5)
        games = wins + losses
        csize = len(div_teams[t["division"]])

        if hist_w >= 1.0:
            final[slug] = base[slug]
        else:
            hist_s   = compute_historical_score(slug)
            cur_rec  = (wins / games) if games else 0.0
            conf_pts = (1 - (conf_rank[slug] - 1) / max(csize - 1, 1)) * 15
            cur_score = cur_rec * 35 + pf_pct(pf) * 35 + form * 15 + conf_pts
            final[slug] = hist_w * hist_s + (1 - hist_w) * cur_score

    # ── Projections ───────────────────────────────────────────────────────
    # Preseason: compress scores to [49, 51] so higher-ranked teams have modestly
    # better odds (correlated with rank) without extreme spread. Conference-aware
    # playoffs mean a tough conference still lowers your odds.
    if hist_w >= 1.0:
        min_s  = min(final.values())
        max_s  = max(final.values())
        spread = max_s - min_s
        if spread > 0:
            sim_scores = {tid: 49.7 + (final[tid] - min_s) / spread * 0.6 for tid in final}
        else:
            sim_scores = {tid: 50.0 for tid in final}
        projections = simulate_projections(sim_scores, teams, n_weeks, playoff_spots, bye_spots)
    else:
        projections = simulate_projections(final, teams, n_weeks, playoff_spots, bye_spots)

    # ── Assemble output ───────────────────────────────────────────────────
    scored = []
    for slug in sorted(final, key=lambda s: -final[s]):
        t    = next(t for t in teams if t["id"] == slug)
        s    = weekly_standings.get(slug, {})
        wins, losses = s.get("wins", 0), s.get("losses", 0)
        pf   = s.get("pf", 0.0)
        pa   = s.get("pa", 0.0)
        form = s.get("form", 0.5)
        games = wins + losses
        csize = len(div_teams[t["division"]])

        if hist_w >= 1.0:
            h = HISTORICAL.get(slug) or {}
            if h:
                all_pf_avgs  = [d["pf"] / d["seasons"] for d in HISTORICAL.values()]
                my_pf_avg    = h["pf"] / h["seasons"]
                pf_rank      = sum(1 for x in all_pf_avgs if x <= my_pf_avg) / len(all_pf_avgs)
                avg_finish   = sum(h["recent_finishes"]) / len(h["recent_finishes"])
                factors = {
                    "win_pct":  round(h["win_pct"] * 20, 2),
                    "pf_avg":   round(pf_rank * 20, 2),
                    "recent":   round((12 - avg_finish) / 11 * 26, 2),
                    "pedigree": round(min(h["champs"], 1) * 14
                                      + (h["top3"] / h["seasons"]) * 12
                                      + (h["playoffs"] / h["seasons"]) * 8, 2),
                }
            else:
                factors = {"win_pct": 0, "pf_avg": 0, "recent": 0, "pedigree": 0}
        else:
            cur_rec  = (wins / games) if games else 0.0
            conf_pts = (1 - (conf_rank[slug] - 1) / max(csize - 1, 1)) * 15
            factors = {
                "record": round(cur_rec * 35, 2),
                "pf":     round(pf_pct(pf) * 35, 2),
                "form":   round(form * 15, 2),
                "conf":   round(conf_pts, 2),
            }

        proj = projections.get(slug, {})
        scored.append({
            "slug":         slug,
            "score":        round(final[slug], 2),
            "wins":         wins,
            "losses":       losses,
            "pf":           round(pf, 2),
            "pa":           round(pa, 2),
            "factors":      factors,
            "is_preseason": hist_w >= 1.0,
            "proj_wins":    proj.get("proj_wins",    "-"),
            "proj_losses":  proj.get("proj_losses",  "-"),
            "playoff_pct":  proj.get("playoff_pct",  "-"),
            "bye_pct":      proj.get("bye_pct",      "-"),
            "conf_win_pct": proj.get("conf_win_pct", "-"),
        })

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
        print("  Pre-draft — generating pre-season power rankings.")
        ranked = compute_power_rankings({}, teams, week_num=0)
        full_ranked = []
        for i, r in enumerate(ranked):
            team = next((t for t in teams if t["id"] == r["slug"]), {})
            full_ranked.append({
                "rank":          i + 1,
                "team_id":       r["slug"],
                "team_name":     team.get("name", r["slug"]),
                "manager":       team.get("manager", r["slug"].title()),
                "logo":          team.get("logo", ""),
                "division":      team.get("division", 1),
                "division_name": team.get("division_name", "Whole"),
                "wins":          0,
                "losses":        0,
                "pf":            0.0,
                "pa":            0.0,
                "score":         r["score"],
                "delta":         0,
                "factors":       r["factors"],
                "is_preseason":  True,
                "proj_wins":     r["proj_wins"],
                "proj_losses":   r["proj_losses"],
                "playoff_pct":   r["playoff_pct"],
                "bye_pct":       r["bye_pct"],
                "conf_win_pct":  r["conf_win_pct"],
            })
        pr_data = {
            "week":      0,
            "label":     "Pre-Season",
            "season":    season,
            "generated": datetime.now(tz=timezone.utc).isoformat(),
            "overall":   full_ranked,
            "whole":     [r for r in full_ranked if r["division"] == 1],
            "skim":      [r for r in full_ranked if r["division"] == 2],
        }
        save(pr_data, POWERRANK_DIR / "weeks" / "preseason.json")
        save({"season": season, "weeks": []}, PICKEMS_DIR / "manifest.json")
        save({"season": season, "weeks": [
            {"id": "preseason", "label": "Pre-Season", "data": "weeks/preseason.json"}
        ]}, POWERRANK_DIR / "manifest.json")
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

            # Load previous week's ranks for delta (week 1 uses preseason as baseline)
            prev_ranks = {}
            if wk == 1:
                prev_path = POWERRANK_DIR / "weeks" / "preseason.json"
            else:
                prev_path = POWERRANK_DIR / "weeks" / f"week-{wk-1:02d}.json"
            if prev_path.exists():
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
                    "is_preseason":  r["is_preseason"],
                    "proj_wins":     r["proj_wins"],
                    "proj_losses":   r["proj_losses"],
                    "playoff_pct":   r["playoff_pct"],
                    "bye_pct":       r["bye_pct"],
                    "conf_win_pct":  r["conf_win_pct"],
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
