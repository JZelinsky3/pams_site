"""
05 — Analyze scraped data into summary reports.

What's new in this version:
  - Regular-season and playoff records tracked separately (per config.PLAYOFF_WEEKS)
  - Current-12 leaderboard (config.CURRENT_MEMBERS) AND all-time leaderboard
  - Championship + top-3 finish counts per manager
  - Rivalry table uses YOUR names for friends (not NFL.com display names)
  - Rivalries split into reg / playoff records

Reads matchups_all.json + standings_all_seasons.json and produces:
  output/summary/manager_career_summary.csv           (everyone)
  output/summary/manager_career_summary_current12.csv (just current 12)
  output/summary/manager_team_names.csv               (name history per manager)
  output/summary/my_career_summary.json|csv
  output/summary/my_weekly_matchups.csv
  output/summary/rivalry_head_to_head.csv             (vs current 12, with reg/playoff split)
  output/summary/season_finishes.csv
  output/summary/top_10_blowouts.csv
  output/summary/top_10_close_games.csv
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

import sys
from pathlib import Path as _Path
sys.path.insert(0, str(_Path(__file__).resolve().parent))
from playoff_logic import classify_playoff_matchups  # noqa: E402


def load_json(path: Path):
    if not path.exists():
        return []
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def my_name_for(user_id, fallback_owner=""):
    """Return 'Your name' for this user_id if they're in CURRENT_MEMBERS, else NFL display name."""
    name = config.display_name(user_id)
    return name if name else fallback_owner


def empty_split_record():
    return {
        "reg_games": 0, "reg_wins": 0, "reg_losses": 0, "reg_ties": 0,
        "reg_pf": 0.0, "reg_pa": 0.0,
        "post_games": 0, "post_wins": 0, "post_losses": 0, "post_ties": 0,
        "post_pf": 0.0, "post_pa": 0.0,
    }


def add_matchup_to_record(rec, m, counts_playoff_fn=None):
    """
    Add a single matchup row to either the reg or post bucket of `rec`.

    counts_playoff_fn(season, week, user_id) -> bool:
        Optional helper that returns True if this matchup should count as a
        real playoff game (vs consolation). If None, falls back to "any
        playoff-week game counts as playoff".
    """
    is_playoff_week_on_calendar = config.is_playoff_week(m["season"], m["week"])
    uid = m.get("user_id")

    if counts_playoff_fn is not None and is_playoff_week_on_calendar:
        is_real_playoff = counts_playoff_fn(m["season"], m["week"], uid)
        if not is_real_playoff:
            # It's a consolation game — skip it entirely from both buckets
            return
    else:
        is_real_playoff = is_playoff_week_on_calendar

    prefix = "post" if is_real_playoff else "reg"
    rec[f"{prefix}_games"] += 1
    if m["result"] == "W":
        rec[f"{prefix}_wins"] += 1
    elif m["result"] == "L":
        rec[f"{prefix}_losses"] += 1
    elif m["result"] == "T":
        rec[f"{prefix}_ties"] += 1
    if m["team_score"] is not None:
        rec[f"{prefix}_pf"] += m["team_score"]
    if m["opp_score"] is not None:
        rec[f"{prefix}_pa"] += m["opp_score"]


def finalize_split_record(rec):
    """Compute derived fields and return a flat dict for CSV output."""
    reg_g, post_g = rec["reg_games"], rec["post_games"]
    return {
        "reg_record": f"{rec['reg_wins']}-{rec['reg_losses']}-{rec['reg_ties']}",
        "reg_win_pct": round(rec["reg_wins"] / reg_g, 4) if reg_g else None,
        "reg_pf": round(rec["reg_pf"], 2),
        "reg_pa": round(rec["reg_pa"], 2),
        "post_record": f"{rec['post_wins']}-{rec['post_losses']}-{rec['post_ties']}",
        "post_win_pct": round(rec["post_wins"] / post_g, 4) if post_g else None,
        "post_pf": round(rec["post_pf"], 2),
        "post_pa": round(rec["post_pa"], 2),
        "total_games": reg_g + post_g,
        "total_record": f"{rec['reg_wins']+rec['post_wins']}-"
                        f"{rec['reg_losses']+rec['post_losses']}-"
                        f"{rec['reg_ties']+rec['post_ties']}",
    }


def main():
    if not config.YOUR_USER_ID:
        raise RuntimeError("Set YOUR_USER_ID in config.py first.")

    ensure_dirs(output_path("summary"))

    matchups = load_json(output_path("matchups_all.json"))
    standings = load_json(output_path("standings_all_seasons.json"))

    if not matchups:
        raise RuntimeError("No matchups data. Run 03_scrape_matchups.py first.")

    my_user_id = config.YOUR_USER_ID
    my_owner_name = my_name_for(my_user_id, "Joey")

    # ============================================================
    # Pre-compute playoff classification per (season, user_id)
    # so reg/playoff splits know which playoff games actually count.
    # ============================================================
    # Build lookups for both reg_rank and final_rank — we may need either
    # depending on the year's playoff seeding convention.
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
    # use final_rank as the playoff seed. For everything else, use reg_rank.
    CUSTOM_SEEDING_YEARS = {2025}

    def get_playoff_seed(season, team_id):
        if season in CUSTOM_SEEDING_YEARS:
            return final_rank_lookup.get((season, team_id))
        # Default: use reg-season rank.
        # Fall back to final_rank if reg_rank is missing (e.g. 2019 data quirk)
        return (reg_rank_lookup.get((season, team_id))
                or final_rank_lookup.get((season, team_id)))

    matchups_by_user_season = defaultdict(list)
    for m in matchups:
        uid = m.get("user_id")
        if uid is None:
            continue
        matchups_by_user_season[(m["season"], uid)].append(m)

    playoff_classification = {}
    for (season, uid), mlist in matchups_by_user_season.items():
        team_id = mlist[0]["team_id"] if mlist else None
        seed = get_playoff_seed(season, team_id) if team_id else None
        info = classify_playoff_matchups(
            season=season,
            user_id=uid,
            playoff_seed=seed,
            user_matchups=sorted(mlist, key=lambda m: m["week"]),
        )
        playoff_classification[(season, uid)] = info

    def counts_as_playoff(season: int, week: int, uid: int) -> bool:
        info = playoff_classification.get((season, uid))
        if not info:
            return False
        return week in info["counted_playoff_weeks"]


    # ============================================================
    # Per-manager career summary (every user_id)
    # ============================================================
    per_user = defaultdict(empty_split_record)
    per_user_meta = defaultdict(lambda: {
        "user_id": None, "owner": "", "seasons": set(),
        "team_names": set(), "high_score": None, "low_score": None,
    })

    for m in matchups:
        uid = m.get("user_id")
        if uid is None:
            continue
        add_matchup_to_record(per_user[uid], m, counts_as_playoff)
        meta = per_user_meta[uid]
        meta["user_id"] = uid
        meta["owner"] = m.get("owner") or meta["owner"]
        meta["seasons"].add(m["season"])
        meta["team_names"].add(m["team_name"])
        s = m["team_score"]
        if s is not None:
            if meta["high_score"] is None or s > meta["high_score"]:
                meta["high_score"] = s
            if meta["low_score"] is None or s < meta["low_score"]:
                meta["low_score"] = s

    # ============================================================
    # Championship + top-3 finish counts (from standings final_rank)
    # ============================================================
    # Map (season, team_id) -> user_id (from matchups)
    season_team_to_uid = {}
    for m in matchups:
        season_team_to_uid[(m["season"], m["team_id"])] = m.get("user_id")

    championships = defaultdict(int)
    top3 = defaultdict(int)
    last_place = defaultdict(int)
    finishes_by_uid = defaultdict(list)
    for s in standings:
        uid = season_team_to_uid.get((s["season"], s["team_id"]))
        if uid is None:
            continue
        fr = s.get("final_rank")
        if fr is None:
            continue
        finishes_by_uid[uid].append((s["season"], fr))
        if fr == 1:
            championships[uid] += 1
        if fr <= 3:
            top3[uid] += 1
        # Last place — depends on league size; use the highest rank seen that season
        max_rank_season = max(
            (x.get("final_rank") or 0)
            for x in standings
            if x["season"] == s["season"]
        )
        if fr == max_rank_season and max_rank_season > 0:
            last_place[uid] += 1

    # Build manager rows
    manager_rows_all = []
    for uid, rec in per_user.items():
        meta = per_user_meta[uid]
        split = finalize_split_record(rec)
        championship_seasons = sorted(
            s for (s, fr) in finishes_by_uid[uid] if fr == 1
        )
        manager_rows_all.append({
            "user_id": uid,
            "owner": my_name_for(uid, meta["owner"]),
            "nfl_display_name": meta["owner"],
            "is_current_member": config.is_current_member(uid),
            "seasons_played": len(meta["seasons"]),
            "seasons_list": ",".join(str(x) for x in sorted(meta["seasons"])),
            "team_names_used": " | ".join(sorted(meta["team_names"])),
            **split,
            "championships": championships[uid],
            "championship_seasons": ",".join(str(s) for s in championship_seasons),
            "top_3_finishes": top3[uid],
            "last_place_finishes": last_place[uid],
            "highest_single_score": meta["high_score"],
            "lowest_single_score": meta["low_score"],
        })

    # Sort by total win%
    def total_win_pct(r):
        # Parse "W-L-T" from total_record
        w, l, t = (int(x) for x in r["total_record"].split("-"))
        games = w + l + t
        return w / games if games else 0

    manager_rows_all.sort(key=total_win_pct, reverse=True)
    save_csv(manager_rows_all, output_path("summary", "manager_career_summary.csv"))
    save_json(manager_rows_all, output_path("summary", "manager_career_summary.json"))

    # Current 12 only
    manager_rows_current = [r for r in manager_rows_all if r["is_current_member"]]
    # Re-sort to keep them in the order of CURRENT_MEMBERS config
    member_order = {uid: i for i, (uid, _, _) in enumerate(config.CURRENT_MEMBERS)}
    manager_rows_current_by_winpct = sorted(manager_rows_current, key=total_win_pct, reverse=True)
    save_csv(manager_rows_current_by_winpct,
             output_path("summary", "manager_career_summary_current12.csv"))
    save_json(manager_rows_current_by_winpct,
              output_path("summary", "manager_career_summary_current12.json"))

    # ============================================================
    # Team-name history per manager
    # ============================================================
    name_rows = []
    name_tracker = {}
    for m in matchups:
        uid = m.get("user_id")
        if uid is None:
            continue
        key = (uid, m["season"])
        if key not in name_tracker:
            name_tracker[key] = m["team_name"]
            name_rows.append({
                "user_id": uid,
                "owner": my_name_for(uid, m["owner"]),
                "season": m["season"],
                "team_id": m["team_id"],
                "team_name": m["team_name"],
            })
    name_rows.sort(key=lambda r: (r["owner"], r["season"]))
    save_csv(name_rows, output_path("summary", "manager_team_names.csv"))

    # ============================================================
    # YOUR personal stuff
    # ============================================================
    my_matchups = [m for m in matchups if m.get("user_id") == my_user_id]
    save_csv(my_matchups, output_path("summary", "my_weekly_matchups.csv"))

    my_rec = empty_split_record()
    for m in my_matchups:
        add_matchup_to_record(my_rec, m, counts_as_playoff)
    my_split = finalize_split_record(my_rec)

    high = max((m["team_score"] for m in my_matchups if m["team_score"] is not None),
               default=None)
    low = min((m["team_score"] for m in my_matchups if m["team_score"] is not None),
              default=None)

    my_career = {
        "user_id": my_user_id,
        "owner": my_owner_name,
        "seasons_played": len(set(m["season"] for m in my_matchups)),
        **my_split,
        "championships": championships[my_user_id],
        "championship_seasons": ",".join(
            str(s) for (s, fr) in finishes_by_uid[my_user_id] if fr == 1
        ),
        "top_3_finishes": top3[my_user_id],
        "highest_score": high,
        "lowest_score": low,
    }
    save_json(my_career, output_path("summary", "my_career_summary.json"))
    save_csv([my_career], output_path("summary", "my_career_summary.csv"))

    # ============================================================
    # Head-to-head — vs CURRENT 12 only, reg/playoff split
    # ============================================================
    h2h = {uid: empty_split_record() for uid, _, _ in config.CURRENT_MEMBERS
           if uid != my_user_id}

    for m in my_matchups:
        opp = m.get("opp_user_id")
        if opp is None or opp not in h2h:
            continue
        add_matchup_to_record(h2h[opp], m, counts_as_playoff)

    h2h_rows = []
    for uid, my_name, nfl_name in config.CURRENT_MEMBERS:
        if uid == my_user_id:
            continue
        rec = h2h[uid]
        split = finalize_split_record(rec)
        h2h_rows.append({
            "opp_user_id": uid,
            "opp_name": my_name,
            "opp_nfl_display": nfl_name,
            "reg_record": split["reg_record"],
            "reg_win_pct": split["reg_win_pct"],
            "reg_pf": split["reg_pf"],
            "reg_pa": split["reg_pa"],
            "playoff_record": split["post_record"],
            "playoff_win_pct": split["post_win_pct"],
            "playoff_pf": split["post_pf"],
            "playoff_pa": split["post_pa"],
            "total_record": split["total_record"],
            "total_games": split["total_games"],
        })
    save_csv(h2h_rows, output_path("summary", "rivalry_head_to_head.csv"))
    save_json(h2h_rows, output_path("summary", "rivalry_head_to_head.json"))

    # ============================================================
    # YOUR season finishes (with reg + playoff split per season)
    # ============================================================
    my_finishes = []
    for s in standings:
        uid = season_team_to_uid.get((s["season"], s["team_id"]))
        if uid != my_user_id:
            continue
        # Per-season reg/playoff split from my matchups
        season_matches = [m for m in my_matchups if m["season"] == s["season"]]
        sr = empty_split_record()
        for m in season_matches:
            add_matchup_to_record(sr, m, counts_as_playoff)
        ss = finalize_split_record(sr)
        my_finishes.append({
            "season": s["season"],
            "team_name": s.get("team_name", ""),
            "division": s.get("division", ""),
            "final_rank": s.get("final_rank"),
            "overall_rank_reg_season": s.get("overall_rank_reg_season"),
            "reg_record": ss["reg_record"],
            "reg_pf": ss["reg_pf"],
            "reg_pa": ss["reg_pa"],
            "playoff_record": ss["post_record"],
            "playoff_pf": ss["post_pf"],
            "playoff_pa": ss["post_pa"],
            "season_pf_total": s.get("points_for"),
            "season_pa_total": s.get("points_against"),
        })
    my_finishes.sort(key=lambda r: r["season"])
    save_csv(my_finishes, output_path("summary", "season_finishes.csv"))
    save_json(my_finishes, output_path("summary", "season_finishes.json"))

    # ============================================================
    # League-wide top 10 blowouts + close games (excluding ties)
    # ============================================================
    seen = set()
    dedup = []
    for m in matchups:
        if m["team_score"] is None or m["opp_score"] is None:
            continue
        key = (m["season"], m["week"], min(m["team_id"], m["opp_team_id"]))
        if key in seen:
            continue
        seen.add(key)
        m_copy = dict(m)
        m_copy["is_playoff"] = config.is_playoff_week(m["season"], m["week"])
        dedup.append(m_copy)

    blowouts = sorted(dedup, key=lambda m: abs(m["margin"] or 0), reverse=True)[:10]
    close = sorted(
        [m for m in dedup if (m["margin"] or 0) != 0],
        key=lambda m: abs(m["margin"] or 0),
    )[:10]
    save_csv(blowouts, output_path("summary", "top_10_blowouts.csv"))
    save_csv(close, output_path("summary", "top_10_close_games.csv"))

    # ============================================================
    # Console summary
    # ============================================================
    print("\n" + "=" * 78)
    print(f"  YOUR CAREER — {my_owner_name} (user_id={my_user_id})")
    print("=" * 78)
    print(f"  Seasons played:    {my_career['seasons_played']}")
    print(f"  Regular season:    {my_split['reg_record']:>9s}  ({my_split['reg_win_pct']})  "
          f"PF {my_split['reg_pf']:>8.1f}  PA {my_split['reg_pa']:>8.1f}")
    print(f"  Playoffs:          {my_split['post_record']:>9s}  ({my_split['post_win_pct']})  "
          f"PF {my_split['post_pf']:>8.1f}  PA {my_split['post_pa']:>8.1f}")
    print(f"  TOTAL:             {my_split['total_record']:>9s}")
    print(f"  Championships:     {my_career['championships']} "
          f"({my_career['championship_seasons'] or 'none'})")
    print(f"  Top-3 finishes:    {my_career['top_3_finishes']}")
    print(f"  High / Low score:  {my_career['highest_score']} / {my_career['lowest_score']}")

    print("\n  RIVALRY RECORDS vs CURRENT 12:")
    print(f"  {'Opponent':<10s}  {'Regular Season':>14s}  {'Playoffs':>10s}  {'Total':>10s}")
    print("  " + "-" * 56)
    for r in h2h_rows:
        # Skip rivals with zero games played
        if r["total_games"] == 0:
            continue
        print(
            f"  {r['opp_name']:<10s}  "
            f"{r['reg_record']:>14s}  "
            f"{r['playoff_record']:>10s}  "
            f"{r['total_record']:>10s}"
        )

    print("\n  SEASON FINISHES:")
    for f in my_finishes:
        rank = f["final_rank"] if f["final_rank"] is not None else "?"
        rs_rank = f["overall_rank_reg_season"] if f["overall_rank_reg_season"] is not None else "?"
        trophy = " 🏆" if rank == 1 else (" 🥈" if rank == 2 else (" 🥉" if rank == 3 else ""))
        print(
            f"    {f['season']}:  final #{str(rank):<2}  reg #{str(rs_rank):<2}  "
            f"reg {f['reg_record']:>7s}  playoff {f['playoff_record']:>6s}  "
            f"({f['team_name']}){trophy}"
        )

    print("\n  ALL-TIME LEADERBOARD — CURRENT 12 ONLY (by total win%):")
    print(f"  {'Owner':<10s}  {'Reg Season':>14s}  {'Playoffs':>10s}  {'Total':>10s}  {'Chips':>5s}")
    print("  " + "-" * 64)
    for r in manager_rows_current_by_winpct:
        chips = r["championships"]
        chip_str = f"{chips}🏆" if chips else "-"
        print(
            f"  {r['owner']:<10s}  "
            f"{r['reg_record']:>14s}  "
            f"{r['post_record']:>10s}  "
            f"{r['total_record']:>10s}  "
            f"{chip_str:>5s}"
        )

    print("\n  ALL-TIME LEADERBOARD — INCLUDING FORMER MEMBERS:")
    print(f"  {'Owner':<14s}  {'Total':>10s}  {'Sznz':>5s}  {'Chips':>5s}")
    print("  " + "-" * 44)
    for r in manager_rows_all[:15]:
        marker = "*" if not r["is_current_member"] else " "
        chips = r["championships"]
        chip_str = f"{chips}🏆" if chips else "-"
        print(
            f" {marker}{r['owner']:<13s}  "
            f"{r['total_record']:>10s}  "
            f"{r['seasons_played']:>5d}  "
            f"{chip_str:>5s}"
        )
    print("  (* = former member, no longer in league)")

    print(f"\nAll reports written to output/summary/")


if __name__ == "__main__":
    main()