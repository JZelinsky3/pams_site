"""
06 — Compute the Record Book + interesting stats (league-wide, all managers).

This is intentionally NOT a duplicate of 05_analyze.py. 05 produces career
summaries and YOUR personal rivalries. This produces:

  CAREER (per manager — NEW stats not in 05):
    - longest win streak (length + season/week span)
    - longest losing streak
    - perfect / winless regular seasons
    - playoff appearances, top-3 finishes, average finish, best/worst finish

  SEASON (every team-season, sortable):
    - regular + playoff records split
    - high week / low week scores
    - average ppg
    - final rank + regular-season rank

  WEEKLY EXTREMES (single-week records, league-wide):
    - highest / lowest single-week score
    - biggest blowout, closest game
    - unluckiest loss (highest losing score)
    - luckiest win (lowest winning score)
    - shootout (highest combined), snoozer (lowest combined)

  HEAD-TO-HEAD MATRIX (current 12 only):
    - For each pair (A vs B): A's record split into reg/playoff

Outputs (all in output/summary/):
  record_book.json           Top-10 lists for every category, ready to render
  record_book.csv            Flat "the records" table (one row per record)
  manager_streaks.csv|json   Every streak >= 3 games, with details
  career_extras.csv|json     Per-manager NEW stats (no overlap with 05)
  season_extremes.csv|json   Every team-season, sortable by various dimensions
  h2h_matrix.json|csv        12 x 12 grid for the H2H page
"""

import json
from collections import defaultdict
from pathlib import Path

from _common import (
    config,
    ensure_dirs,
    output_path,
    save_csv,
    save_json,
)

# Add scripts dir to path so we can import sibling modules
import sys
from pathlib import Path as _Path
sys.path.insert(0, str(_Path(__file__).resolve().parent))
from playoff_logic import classify_playoff_matchups  # noqa: E402


def load_json(path: Path):
    if not path.exists():
        return []
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def my_name_for(user_id, fallback=""):
    name = config.display_name(user_id)
    return name if name else fallback


def compute_streaks(games_in_order: list[dict]) -> list[dict]:
    """Return all W or L streaks of length >= 3 from a chronological game list."""
    streaks = []
    if not games_in_order:
        return streaks

    cur_type = None
    cur_games = []

    def flush():
        if cur_type in ("W", "L") and len(cur_games) >= 3:
            streaks.append({
                "type": "win" if cur_type == "W" else "loss",
                "length": len(cur_games),
                "start_season": cur_games[0]["season"],
                "start_week": cur_games[0]["week"],
                "end_season": cur_games[-1]["season"],
                "end_week": cur_games[-1]["week"],
                "total_pf": round(sum(g.get("team_score") or 0 for g in cur_games), 2),
                "total_pa": round(sum(g.get("opp_score") or 0 for g in cur_games), 2),
            })

    for g in games_in_order:
        r = g["result"]
        if r == cur_type:
            cur_games.append(g)
        else:
            flush()
            cur_type = r
            cur_games = [g]
    flush()
    return streaks


def main():
    ensure_dirs(output_path("summary"))

    matchups = load_json(output_path("matchups_all.json"))
    standings = load_json(output_path("standings_all_seasons.json"))

    if not matchups:
        raise RuntimeError("No matchups data. Run scrapers first.")

    # (season, team_id) -> user_id  (team_id is reused across seasons)
    season_team_to_uid = {}
    for m in matchups:
        if m.get("user_id") is not None:
            season_team_to_uid[(m["season"], m["team_id"])] = m["user_id"]

    # ============================================================
    # 0. Pre-compute playoff classification per (season, user_id)
    # ============================================================
    # For each user-season, figure out which playoff weeks COUNT toward
    # their playoff record and which are consolation games.
    #
    # Returns dict: (season, user_id) -> set of week numbers that count
    #
    # Non-counted playoff-week games (consolation, eliminated-team games,
    # missed-playoffs games) are treated as if they don't exist for
    # playoff-record purposes — but they still count for league-wide
    # weekly extremes (a 200pt game is a 200pt game).

    # Build lookups for both reg_rank and final_rank. Most years use reg_rank
    # for playoff seeding, but 2025 had custom seeding so we use final_rank.
    # Also: 2019's standings page doesn't have reg_rank (single-table layout),
    # so we fall back to final_rank for that year too.
    reg_rank_lookup = {}
    final_rank_lookup = {}
    for s in standings:
        reg = s.get("overall_rank_reg_season")
        if reg is not None:
            reg_rank_lookup[(s["season"], s["team_id"])] = reg
        fin = s.get("final_rank")
        if fin is not None:
            final_rank_lookup[(s["season"], s["team_id"])] = fin

    # Years where playoff seeding was custom (not based on reg-season rank)
    CUSTOM_SEEDING_YEARS = {2025}

    def get_playoff_seed(season, team_id):
        if season in CUSTOM_SEEDING_YEARS:
            return final_rank_lookup.get((season, team_id))
        return (reg_rank_lookup.get((season, team_id))
                or final_rank_lookup.get((season, team_id)))

    # Group matchups by (season, user_id)
    matchups_by_user_season = defaultdict(list)
    for m in matchups:
        uid = m.get("user_id")
        if uid is None:
            continue
        matchups_by_user_season[(m["season"], uid)].append(m)

    # For each (season, uid), call classify_playoff_matchups
    playoff_classification = {}
    for (season, uid), mlist in matchups_by_user_season.items():
        team_id = mlist[0]["team_id"] if mlist else None
        seed = get_playoff_seed(season, team_id) if team_id else None

        mlist_sorted = sorted(mlist, key=lambda m: m["week"])
        info = classify_playoff_matchups(
            season=season,
            user_id=uid,
            playoff_seed=seed,
            user_matchups=mlist_sorted,
        )
        playoff_classification[(season, uid)] = info

    def counts_as_playoff(season: int, week: int, uid: int) -> bool:
        """Returns True if (season, week) counts as a real playoff game for this user."""
        info = playoff_classification.get((season, uid))
        if not info:
            return False
        return week in info["counted_playoff_weeks"]



    # ============================================================
    # 1. Streaks — chronological game lists per user
    # ============================================================
    games_by_user = defaultdict(list)
    for m in matchups:
        uid = m.get("user_id")
        if uid is None:
            continue
        games_by_user[uid].append(m)
    for uid in games_by_user:
        games_by_user[uid].sort(key=lambda g: (g["season"], g["week"]))

    all_streaks = []
    longest_win_by_user = {}
    longest_loss_by_user = {}
    for uid, games in games_by_user.items():
        owner = my_name_for(uid, games[0].get("owner", ""))
        streaks = compute_streaks(games)
        for s in streaks:
            s["user_id"] = uid
            s["owner"] = owner
            all_streaks.append(s)
        wins = [s for s in streaks if s["type"] == "win"]
        losses = [s for s in streaks if s["type"] == "loss"]
        if wins:
            longest_win_by_user[uid] = max(wins, key=lambda s: s["length"])
        if losses:
            longest_loss_by_user[uid] = max(losses, key=lambda s: s["length"])

    all_streaks.sort(key=lambda s: s["length"], reverse=True)
    save_csv(all_streaks, output_path("summary", "manager_streaks.csv"))
    save_json(all_streaks, output_path("summary", "manager_streaks.json"))

    # ============================================================
    # 2. Per-season per-team aggregates
    # ============================================================
    season_team_stats = defaultdict(lambda: {
        "reg_wins": 0, "reg_losses": 0, "reg_ties": 0,
        "reg_pf": 0.0, "reg_pa": 0.0, "reg_games": 0,
        "post_wins": 0, "post_losses": 0, "post_ties": 0,
        "post_pf": 0.0, "post_pa": 0.0, "post_games": 0,
        "high_week": None, "high_week_info": None,
        "low_week": None, "low_week_info": None,
    })

    for m in matchups:
        uid = m.get("user_id")
        if uid is None:
            continue
        s = season_team_stats[(m["season"], uid)]
        # Is this a playoff week on the calendar?
        is_playoff_week_on_calendar = config.is_playoff_week(m["season"], m["week"])
        # Does it actually COUNT as a playoff game for this team?
        # (False for consolation, eliminated, or non-playoff teams)
        is_counted_playoff = counts_as_playoff(m["season"], m["week"], uid)

        # If it's a playoff week BUT doesn't count, skip it entirely from
        # the team's record (don't dump into "reg" either — it's a consolation game).
        if is_playoff_week_on_calendar and not is_counted_playoff:
            # Still update high/low week tracking (the score happened), but
            # don't add to either reg or playoff record buckets.
            if m["team_score"] is not None:
                if s["high_week"] is None or m["team_score"] > s["high_week"]:
                    s["high_week"] = m["team_score"]
                    s["high_week_info"] = {"week": m["week"], "opp": m.get("opp_owner", "")}
                if s["low_week"] is None or m["team_score"] < s["low_week"]:
                    s["low_week"] = m["team_score"]
                    s["low_week_info"] = {"week": m["week"], "opp": m.get("opp_owner", "")}
            continue

        prefix = "post" if is_counted_playoff else "reg"
        s[f"{prefix}_games"] += 1
        if m["result"] == "W":
            s[f"{prefix}_wins"] += 1
        elif m["result"] == "L":
            s[f"{prefix}_losses"] += 1
        elif m["result"] == "T":
            s[f"{prefix}_ties"] += 1
        if m["team_score"] is not None:
            s[f"{prefix}_pf"] += m["team_score"]
            if s["high_week"] is None or m["team_score"] > s["high_week"]:
                s["high_week"] = m["team_score"]
                s["high_week_info"] = {"week": m["week"], "opp": m.get("opp_owner", "")}
            if s["low_week"] is None or m["team_score"] < s["low_week"]:
                s["low_week"] = m["team_score"]
                s["low_week_info"] = {"week": m["week"], "opp": m.get("opp_owner", "")}
        if m["opp_score"] is not None:
            s[f"{prefix}_pa"] += m["opp_score"]


    # Build flat per-team-season rows
    season_rows = []
    for (season, uid), s in season_team_stats.items():
        owner = my_name_for(uid)
        # Find team_id and standings row for this user that season
        team_id = None
        for m in matchups:
            if m["season"] == season and m.get("user_id") == uid:
                team_id = m["team_id"]
                break
        final_rank = reg_rank = None
        team_name = ""
        for st in standings:
            if st["season"] == season and st["team_id"] == team_id:
                final_rank = st.get("final_rank")
                reg_rank = st.get("overall_rank_reg_season")
                team_name = st.get("team_name", "")
                break

        total_w = s["reg_wins"] + s["post_wins"]
        total_l = s["reg_losses"] + s["post_losses"]
        total_t = s["reg_ties"] + s["post_ties"]
        total_g = s["reg_games"] + s["post_games"]
        total_pf = s["reg_pf"] + s["post_pf"]

        season_rows.append({
            "season": season,
            "user_id": uid,
            "owner": owner,
            "team_name": team_name,
            "final_rank": final_rank,
            "reg_season_rank": reg_rank,
            "reg_record": f"{s['reg_wins']}-{s['reg_losses']}-{s['reg_ties']}",
            "reg_win_pct": round(s["reg_wins"] / s["reg_games"], 4) if s["reg_games"] else None,
            "reg_pf": round(s["reg_pf"], 2),
            "reg_pa": round(s["reg_pa"], 2),
            "playoff_record": f"{s['post_wins']}-{s['post_losses']}-{s['post_ties']}",
            "playoff_games": s["post_games"],
            "playoff_pf": round(s["post_pf"], 2),
            "total_record": f"{total_w}-{total_l}-{total_t}",
            "total_pf": round(total_pf, 2),
            "avg_ppg": round(total_pf / total_g, 2) if total_g else None,
            "high_week_score": s["high_week"],
            "high_week_when": (
                f"W{s['high_week_info']['week']} vs {s['high_week_info']['opp']}"
                if s["high_week_info"] else ""
            ),
            "low_week_score": s["low_week"],
            "low_week_when": (
                f"W{s['low_week_info']['week']} vs {s['low_week_info']['opp']}"
                if s["low_week_info"] else ""
            ),
        })
    season_rows.sort(key=lambda r: (r["season"], r["final_rank"] or 99))
    save_csv(season_rows, output_path("summary", "season_extremes.csv"))
    save_json(season_rows, output_path("summary", "season_extremes.json"))

    # ============================================================
    # 3. Single-week extremes (every team-week row, league-wide)
    # ============================================================
    weekly_rows = []
    for m in matchups:
        if m["team_score"] is None:
            continue
        weekly_rows.append({
            "season": m["season"],
            "week": m["week"],
            "is_playoff": config.is_playoff_week(m["season"], m["week"]),
            "user_id": m.get("user_id"),
            "owner": my_name_for(m.get("user_id"), m.get("owner", "")),
            "team_name": m["team_name"],
            "score": m["team_score"],
            "opp_user_id": m.get("opp_user_id"),
            "opp_owner": my_name_for(m.get("opp_user_id"), m.get("opp_owner", "")),
            "opp_score": m["opp_score"],
            "result": m["result"],
            "margin": m.get("margin"),
        })

    # Dedupe to one row per matchup for combined-score / blowout records
    seen = set()
    matchup_rows = []
    for r in weekly_rows:
        key = (r["season"], r["week"], min(r["user_id"] or 0, r["opp_user_id"] or 0))
        if key in seen:
            continue
        seen.add(key)
        r2 = dict(r)
        r2["combined_score"] = (r["score"] or 0) + (r["opp_score"] or 0)
        matchup_rows.append(r2)

    # ============================================================
    # 4. Career extras (NEW stats — no overlap with 05)
    # ============================================================
    career_extras = {}
    for uid in games_by_user:
        owner = my_name_for(uid, games_by_user[uid][0].get("owner", ""))
        seasons = set(g["season"] for g in games_by_user[uid])
        team_ids_per_season = {g["season"]: g["team_id"] for g in games_by_user[uid]}

        finishes = []
        for s in standings:
            if s["team_id"] == team_ids_per_season.get(s["season"]) and s.get("final_rank"):
                finishes.append(s["final_rank"])

        playoff_seasons = set()
        for g in games_by_user[uid]:
            if config.is_playoff_week(g["season"], g["week"]):
                playoff_seasons.add(g["season"])

        reg_records_by_season = defaultdict(lambda: {"w": 0, "l": 0, "t": 0})
        for g in games_by_user[uid]:
            if not config.is_playoff_week(g["season"], g["week"]):
                if g["result"] == "W": reg_records_by_season[g["season"]]["w"] += 1
                elif g["result"] == "L": reg_records_by_season[g["season"]]["l"] += 1
                elif g["result"] == "T": reg_records_by_season[g["season"]]["t"] += 1

        perfect = sorted(
            s for s, r in reg_records_by_season.items()
            if r["l"] == 0 and r["t"] == 0 and r["w"] > 0
        )
        winless = sorted(
            s for s, r in reg_records_by_season.items()
            if r["w"] == 0 and r["t"] == 0 and r["l"] > 0
        )

        lws = longest_win_by_user.get(uid, {})
        lls = longest_loss_by_user.get(uid, {})

        career_extras[uid] = {
            "user_id": uid,
            "owner": owner,
            "is_current_member": config.is_current_member(uid),
            "seasons_played": len(seasons),
            "championship_appearances": sum(1 for f in finishes if f in (1, 2)),
            "top_3_finishes": sum(1 for f in finishes if f <= 3),
            "playoff_appearances": len(playoff_seasons),
            "perfect_reg_seasons": ",".join(str(s) for s in perfect),
            "winless_reg_seasons": ",".join(str(s) for s in winless),
            "avg_final_rank": round(sum(finishes) / len(finishes), 2) if finishes else None,
            "best_finish": min(finishes) if finishes else None,
            "worst_finish": max(finishes) if finishes else None,
            "longest_win_streak": lws.get("length", 0),
            "longest_win_streak_when": (
                f"W{lws.get('start_week')} {lws.get('start_season')} → "
                f"W{lws.get('end_week')} {lws.get('end_season')}"
                if lws else ""
            ),
            "longest_loss_streak": lls.get("length", 0),
            "longest_loss_streak_when": (
                f"W{lls.get('start_week')} {lls.get('start_season')} → "
                f"W{lls.get('end_week')} {lls.get('end_season')}"
                if lls else ""
            ),
        }
    save_csv(list(career_extras.values()), output_path("summary", "career_extras.csv"))
    save_json(list(career_extras.values()), output_path("summary", "career_extras.json"))

    # ============================================================
    # 5. THE RECORD BOOK — top-10 for each category
    # ============================================================
    def top_n(rows, key, n=10, reverse=True):
        cleaned = [r for r in rows if r.get(key) is not None]
        return sorted(cleaned, key=lambda r: r[key], reverse=reverse)[:n]

    record_book = {
        "weekly": {
            "highest_single_week_score": top_n(weekly_rows, "score", 10),
            "lowest_single_week_score": top_n(weekly_rows, "score", 10, reverse=False),
            "biggest_blowouts": top_n(matchup_rows, "margin", 10),
            "closest_games": sorted(
                [r for r in matchup_rows if r["margin"] and r["margin"] > 0],
                key=lambda r: r["margin"],
            )[:10],
            "unluckiest_losses": top_n(
                [r for r in weekly_rows if r["result"] == "L"], "score", 10
            ),
            "luckiest_wins": sorted(
                [r for r in weekly_rows if r["result"] == "W" and r["score"] is not None],
                key=lambda r: r["score"],
            )[:10],
            "highest_combined_score": top_n(matchup_rows, "combined_score", 10),
            "lowest_combined_score": top_n(matchup_rows, "combined_score", 10, reverse=False),
        },
        "season": {
            "highest_season_pf": top_n(season_rows, "total_pf", 10),
            "lowest_season_pf": top_n(season_rows, "total_pf", 10, reverse=False),
            "best_reg_season_records": sorted(
                [r for r in season_rows if r["reg_win_pct"] is not None],
                key=lambda r: (-r["reg_win_pct"], -(r["reg_pf"] or 0)),
            )[:10],
            "highest_ppg": top_n(season_rows, "avg_ppg", 10),
            "highest_single_week_in_season": top_n(season_rows, "high_week_score", 10),
            "lowest_single_week_in_season": top_n(
                season_rows, "low_week_score", 10, reverse=False
            ),
        },
        "career": {
            "longest_win_streaks": [s for s in all_streaks if s["type"] == "win"][:10],
            "longest_loss_streaks": [s for s in all_streaks if s["type"] == "loss"][:10],
            "most_top_3_finishes": sorted(
                career_extras.values(),
                key=lambda c: (-c["top_3_finishes"], c["avg_final_rank"] or 99),
            )[:10],
            "best_avg_finish": sorted(
                [c for c in career_extras.values() if c["avg_final_rank"] is not None],
                key=lambda c: c["avg_final_rank"],
            )[:10],
            "most_playoff_appearances": sorted(
                career_extras.values(),
                key=lambda c: -c["playoff_appearances"],
            )[:10],
            "most_championship_appearances": sorted(
                career_extras.values(),
                key=lambda c: -c["championship_appearances"],
            )[:10],
        },
    }
    save_json(record_book, output_path("summary", "record_book.json"))

    # Flat "the records" CSV — single-line record book for quick rendering
    flat_book = []

    def add(category, label, holder, value, detail=""):
        flat_book.append({
            "category": category, "record": label,
            "holder": holder, "value": value, "detail": detail,
        })

    def first(lst):
        return lst[0] if lst else None

    rb = record_book
    r = first(rb["weekly"]["highest_single_week_score"])
    if r:
        add("Weekly", "Highest single-week score", r["owner"], r["score"],
            f"{r['season']} W{r['week']} vs {r['opp_owner']}")
    r = first(rb["weekly"]["lowest_single_week_score"])
    if r:
        add("Weekly", "Lowest single-week score", r["owner"], r["score"],
            f"{r['season']} W{r['week']} vs {r['opp_owner']}")
    r = first(rb["weekly"]["biggest_blowouts"])
    if r:
        add("Weekly", "Biggest blowout (margin)", r["owner"], r["margin"],
            f"{r['season']} W{r['week']} {r['score']}–{r['opp_score']} vs {r['opp_owner']}")
    r = first(rb["weekly"]["closest_games"])
    if r:
        add("Weekly", "Closest game (margin)", r["owner"], r["margin"],
            f"{r['season']} W{r['week']} {r['score']}–{r['opp_score']} vs {r['opp_owner']}")
    r = first(rb["weekly"]["unluckiest_losses"])
    if r:
        add("Weekly", "Unluckiest loss (highest losing score)", r["owner"], r["score"],
            f"{r['season']} W{r['week']} lost to {r['opp_owner']} ({r['opp_score']})")
    r = first(rb["weekly"]["luckiest_wins"])
    if r:
        add("Weekly", "Luckiest win (lowest winning score)", r["owner"], r["score"],
            f"{r['season']} W{r['week']} beat {r['opp_owner']} ({r['opp_score']})")
    r = first(rb["weekly"]["highest_combined_score"])
    if r:
        add("Weekly", "Shootout (highest combined)",
            f"{r['owner']} vs {r['opp_owner']}", r["combined_score"],
            f"{r['season']} W{r['week']} {r['score']}–{r['opp_score']}")
    r = first(rb["weekly"]["lowest_combined_score"])
    if r:
        add("Weekly", "Snoozer (lowest combined)",
            f"{r['owner']} vs {r['opp_owner']}", r["combined_score"],
            f"{r['season']} W{r['week']} {r['score']}–{r['opp_score']}")

    r = first(rb["season"]["highest_season_pf"])
    if r:
        add("Season", "Highest season PF", r["owner"], r["total_pf"],
            f"{r['season']} ({r['team_name']})")
    r = first(rb["season"]["lowest_season_pf"])
    if r:
        add("Season", "Lowest season PF", r["owner"], r["total_pf"],
            f"{r['season']} ({r['team_name']})")
    r = first(rb["season"]["best_reg_season_records"])
    if r:
        add("Season", "Best regular season record", r["owner"], r["reg_record"],
            f"{r['season']} ({r['reg_win_pct']})")
    r = first(rb["season"]["highest_ppg"])
    if r:
        add("Season", "Highest avg ppg", r["owner"], r["avg_ppg"],
            f"{r['season']} ({r['team_name']})")

    r = first(rb["career"]["longest_win_streaks"])
    if r:
        add("Career", "Longest win streak", r["owner"], r["length"],
            f"W{r['start_week']} {r['start_season']} → W{r['end_week']} {r['end_season']}")
    r = first(rb["career"]["longest_loss_streaks"])
    if r:
        add("Career", "Longest losing streak", r["owner"], r["length"],
            f"W{r['start_week']} {r['start_season']} → W{r['end_week']} {r['end_season']}")
    r = first(rb["career"]["most_top_3_finishes"])
    if r:
        add("Career", "Most top-3 finishes", r["owner"], r["top_3_finishes"],
            f"avg finish {r['avg_final_rank']}")
    r = first(rb["career"]["best_avg_finish"])
    if r:
        add("Career", "Best average finish", r["owner"], r["avg_final_rank"],
            f"across {r['seasons_played']} seasons")
    r = first(rb["career"]["most_playoff_appearances"])
    if r:
        add("Career", "Most playoff appearances", r["owner"], r["playoff_appearances"],
            f"in {r['seasons_played']} seasons")

    save_csv(flat_book, output_path("summary", "record_book.csv"))

    # ============================================================
    # 6. H2H matrix — current 12 only, reg + playoff split
    # ============================================================
    member_ids = [uid for uid, _, _ in config.CURRENT_MEMBERS]
    name_lookup = {uid: name for uid, name, _ in config.CURRENT_MEMBERS}

    # matrix[A][B] = A's record vs B
    matrix = {a: {b: {
        "reg_w": 0, "reg_l": 0, "reg_t": 0, "reg_pf": 0.0, "reg_pa": 0.0,
        "post_w": 0, "post_l": 0, "post_t": 0, "post_pf": 0.0, "post_pa": 0.0,
    } for b in member_ids if b != a} for a in member_ids}

    for m in matchups:
        a = m.get("user_id")
        b = m.get("opp_user_id")
        if a not in matrix or b not in matrix.get(a, {}):
            continue
        is_playoff_week_on_calendar = config.is_playoff_week(m["season"], m["week"])
        # For H2H purposes, count it as a playoff game ONLY if it counts for BOTH teams.
        # (e.g. a 3rd-place game counts for both losers; a consolation game counts for neither)
        is_counted_a = counts_as_playoff(m["season"], m["week"], a)
        is_counted_b = counts_as_playoff(m["season"], m["week"], b)

        # If it's a playoff week but doesn't count for either team, skip entirely
        if is_playoff_week_on_calendar and not (is_counted_a or is_counted_b):
            continue

        # If both teams' game counts → real playoff
        # If only one team's counts (shouldn't normally happen but defensive) → also playoff
        is_real_playoff = is_playoff_week_on_calendar and (is_counted_a or is_counted_b)
        prefix = "post" if is_real_playoff else "reg"
        cell = matrix[a][b]
        if m["result"] == "W": cell[f"{prefix}_w"] += 1
        elif m["result"] == "L": cell[f"{prefix}_l"] += 1
        elif m["result"] == "T": cell[f"{prefix}_t"] += 1
        if m["team_score"] is not None:
            cell[f"{prefix}_pf"] += m["team_score"]
        if m["opp_score"] is not None:
            cell[f"{prefix}_pa"] += m["opp_score"]


    # Build flat CSV (1 row per ordered pair) + nested JSON for matrix display
    h2h_flat = []
    h2h_nested = {}
    for a in member_ids:
        h2h_nested[a] = {
            "user_id": a,
            "name": name_lookup[a],
            "opponents": {},
        }
        for b in member_ids:
            if b == a:
                continue
            c = matrix[a][b]
            row = {
                "a_user_id": a,
                "a_name": name_lookup[a],
                "b_user_id": b,
                "b_name": name_lookup[b],
                "reg_record": f"{c['reg_w']}-{c['reg_l']}-{c['reg_t']}",
                "reg_pf": round(c["reg_pf"], 2),
                "reg_pa": round(c["reg_pa"], 2),
                "playoff_record": f"{c['post_w']}-{c['post_l']}-{c['post_t']}",
                "playoff_pf": round(c["post_pf"], 2),
                "playoff_pa": round(c["post_pa"], 2),
                "total_record": (
                    f"{c['reg_w']+c['post_w']}-"
                    f"{c['reg_l']+c['post_l']}-"
                    f"{c['reg_t']+c['post_t']}"
                ),
                "total_games": (
                    c["reg_w"] + c["reg_l"] + c["reg_t"]
                    + c["post_w"] + c["post_l"] + c["post_t"]
                ),
            }
            h2h_flat.append(row)
            h2h_nested[a]["opponents"][b] = row

    save_csv(h2h_flat, output_path("summary", "h2h_matrix.csv"))
    save_json(h2h_nested, output_path("summary", "h2h_matrix.json"))

    # ============================================================
    # Console summary
    # ============================================================
    print("\n" + "=" * 76)
    print("  RECORD BOOK")
    print("=" * 76)
    for r in flat_book:
        print(f"  [{r['category']:<7s}] {r['record']:<42s}  "
              f"{str(r['holder'])[:18]:<18s}  {r['value']}")
        if r['detail']:
            print(f"  {'':<10s} {r['detail']}")

    print("\n  TOP 5 ALL-TIME WIN STREAKS:")
    for s in record_book["career"]["longest_win_streaks"][:5]:
        print(f"    {s['owner']:<12s}  {s['length']} games  "
              f"(W{s['start_week']} {s['start_season']} → W{s['end_week']} {s['end_season']})")

    print("\n  TOP 5 ALL-TIME LOSING STREAKS:")
    for s in record_book["career"]["longest_loss_streaks"][:5]:
        print(f"    {s['owner']:<12s}  {s['length']} games  "
              f"(W{s['start_week']} {s['start_season']} → W{s['end_week']} {s['end_season']})")

    print(f"\n  Outputs written to output/summary/")
    print(f"    record_book.json + .csv")
    print(f"    manager_streaks.csv + .json")
    print(f"    career_extras.csv + .json")
    print(f"    season_extremes.csv + .json")
    print(f"    h2h_matrix.csv + .json")


if __name__ == "__main__":
    main()