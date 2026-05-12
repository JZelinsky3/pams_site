"""
Re-parse cached raw HTML without hitting NFL.com again.

The scrapers save every page to output/_raw_html/<season>/<page>.html. If we
fix a parser bug, you can run this to re-parse all those cached pages instantly,
no network requests, no waiting.

This re-runs the standings parser and the matchups parser against your
cached HTML. Run this AFTER you've done at least one full scrape.

Usage:
  python scripts/reparse_cached.py
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Import the parsers from the scraper scripts
sys.path.insert(0, str(Path(__file__).resolve().parent))

import config
from _common import (
    output_path, save_csv, save_json, soup, clean_text, parse_float, parse_int,
    ensure_dirs,
)


# ============================================================
# Re-import parser logic. Rather than re-fetch, we read the
# raw HTML files and apply the SAME parsing functions.
# ============================================================

def _read_cached(season, filename):
    path = output_path("_raw_html", str(season), filename)
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8")


# --- Standings parsers (same as in 02_scrape_standings.py) ---

def parse_record(text):
    text = (text or "").strip()
    m = re.match(r"(\d+)-(\d+)(?:-(\d+))?", text)
    if not m:
        return {"wins": None, "losses": None, "ties": None}
    return {
        "wins": int(m.group(1)),
        "losses": int(m.group(2)),
        "ties": int(m.group(3) or 0),
    }


def parse_final_placements(html):
    if not html:
        return {}
    page = soup(html)
    placements = {}
    for li in page.select("#championResults .results li"):
        rank = None
        for c in li.get("class", []):
            m = re.match(r"place-(\d+)", c)
            if m:
                rank = int(m.group(1))
                break
        if rank is None:
            continue
        team_link = li.find("a", href=lambda h: h and "teamhome" in h)
        if not team_link:
            continue
        m = re.search(r"teamId=(\d+)", team_link.get("href", ""))
        if not m:
            continue
        team_id = int(m.group(1))
        team_name = clean_text(team_link.get_text())
        ems = [clean_text(e.get_text()) for e in li.find_all("em")]
        owner = ems[0] if ems else ""
        placements[team_id] = {
            "final_rank": rank, "team_id": team_id,
            "team_name": team_name, "owner": owner,
        }
    return placements


def parse_regular_season(html):
    if not html:
        return {}
    page = soup(html)
    out = {}
    seen = set()
    for table_wrap in page.select("div.tableWrap"):
        h5 = table_wrap.find("h5")
        division = ""
        if h5:
            division = clean_text(h5.get_text())
            division = re.sub(r"^Division\s*\d+\s*:\s*", "", division).strip()
        is_leader = "firstTableWrap" in (table_wrap.get("class") or [])

        for tr in table_wrap.select("tbody tr"):
            team_id = None
            for c in tr.get("class", []):
                m = re.match(r"team-(\d+)", c)
                if m:
                    team_id = int(m.group(1))
                    break
            if team_id is None:
                continue
            if is_leader and team_id in seen:
                continue
            if team_id in seen:
                if division and not out[team_id].get("division"):
                    out[team_id]["division"] = division
                continue

            a = tr.find("a", class_=re.compile(r"\bteamName\b"))
            team_name = clean_text(a.get_text()) if a else ""

            def cell_text(cls_pattern):
                td = tr.find("td", class_=re.compile(cls_pattern))
                return clean_text(td.get_text()) if td else None

            rec = parse_record(cell_text(r"\bteamRecord\b"))
            win_pct = parse_float(cell_text(r"\bteamWinPct\b"))
            streak = cell_text(r"\bteamStreak\b")
            pts_cells = tr.find_all("td", class_=re.compile(r"\bteamPts\b"))
            pf = parse_float(clean_text(pts_cells[0].get_text())) if len(pts_cells) >= 1 else None
            pa = parse_float(clean_text(pts_cells[1].get_text())) if len(pts_cells) >= 2 else None

            rank_td = tr.find("td", class_=re.compile(r"\bteamRank\b"))
            overall_rank = None
            div_rank = None
            if rank_td:
                spans = rank_td.find_all("span", class_=re.compile(r"\bteamRank\b"))
                if len(spans) >= 2:
                    div_rank = parse_int(clean_text(spans[0].get_text()))
                    m = re.search(r"\((\d+)\)", spans[1].get_text())
                    if m:
                        overall_rank = int(m.group(1))
                elif len(spans) == 1:
                    overall_rank = parse_int(clean_text(spans[0].get_text()))
                    div_rank = None

            out[team_id] = {
                "team_id": team_id, "team_name": team_name, "division": division,
                "division_rank": div_rank, "overall_rank_reg_season": overall_rank,
                "wins": rec["wins"], "losses": rec["losses"], "ties": rec["ties"],
                "win_pct": win_pct, "streak": streak,
                "points_for": pf, "points_against": pa,
            }
            seen.add(team_id)
    return out


# --- Matchup parser (same as in 03_scrape_matchups.py) ---

def parse_team_wrap(tw):
    team_link = tw.find("a", class_=re.compile(r"\bteamName\b"))
    if not team_link:
        return None
    team_id = None
    for c in team_link.get("class", []):
        m = re.match(r"teamId-(\d+)", c)
        if m:
            team_id = int(m.group(1))
            break
    if team_id is None:
        return None
    team_name = clean_text(team_link.get_text())
    score = None
    total_div = tw.find("div", class_=re.compile(r"\bteamTotal\b"))
    if total_div:
        score = parse_float(clean_text(total_div.get_text()))
    owner = ""
    user_id = None
    user_span = tw.find("span", class_=re.compile(r"\buserName\b"))
    if user_span:
        owner = clean_text(user_span.get_text())
        for c in user_span.get("class", []):
            m = re.match(r"userId-(\d+)", c)
            if m:
                user_id = int(m.group(1))
                break
    record = ""
    rank = None
    rec_span = tw.find("span", class_=re.compile(r"\bteamRecord\b"))
    if rec_span:
        record = clean_text(rec_span.get_text())
    rank_span = tw.find("span", class_=re.compile(r"\bteamRank\b"))
    if rank_span:
        m = re.search(r"\((\d+)\)", rank_span.get_text())
        if m:
            rank = int(m.group(1))
    streak = ""
    streak_li = tw.find("li", class_=re.compile(r"\bstreak\b"))
    if streak_li:
        strong = streak_li.find("strong")
        if strong:
            streak = clean_text(strong.get_text())
    return {
        "team_id": team_id, "team_name": team_name, "owner": owner,
        "user_id": user_id, "score": score,
        "record_through_week": record, "rank_through_week": rank,
        "streak_through_week": streak,
    }


def parse_week_schedule(html, season, week):
    if not html:
        return []
    page = soup(html)
    rows = []
    for li in page.select("li.matchup"):
        wraps = [
            div for div in li.find_all("div", class_=re.compile(r"\bteamWrap\b"))
            if any(re.match(r"teamWrap-\d+", c) for c in div.get("class", []))
        ]
        if len(wraps) != 2:
            continue
        a = parse_team_wrap(wraps[0])
        b = parse_team_wrap(wraps[1])
        if not a or not b:
            continue
        if a["score"] is None or b["score"] is None:
            a_result = b_result = None
        elif a["score"] > b["score"]:
            a_result, b_result = "W", "L"
        elif a["score"] < b["score"]:
            a_result, b_result = "L", "W"
        else:
            a_result = b_result = "T"
        for me, opp, result in [(a, b, a_result), (b, a, b_result)]:
            rows.append({
                "season": season, "week": week,
                "team_id": me["team_id"], "team_name": me["team_name"],
                "owner": me["owner"], "user_id": me["user_id"],
                "team_score": me["score"],
                "opp_team_id": opp["team_id"], "opp_team_name": opp["team_name"],
                "opp_owner": opp["owner"], "opp_user_id": opp["user_id"],
                "opp_score": opp["score"], "result": result,
                "margin": (
                    round(me["score"] - opp["score"], 2)
                    if me["score"] is not None and opp["score"] is not None else None
                ),
                "record_through_week": me["record_through_week"],
                "rank_through_week": me["rank_through_week"],
                "streak_through_week": me["streak_through_week"],
            })
    return rows


def main():
    ensure_dirs(output_path("standings"), output_path("matchups"))

    print("=" * 70)
    print("Re-parsing standings from cached HTML")
    print("=" * 70)

    combined_standings = []
    for season in config.SEASONS:
        print(f"\n=== Season {season} ===")
        final_html = _read_cached(season, "standings_final.html")
        reg_html = _read_cached(season, "standings_regular.html")
        if not final_html and not reg_html:
            print(f"  No cached HTML for {season} — skipping")
            continue

        placements = parse_final_placements(final_html)
        regular = parse_regular_season(reg_html)

        all_ids = set(placements) | set(regular)
        rows = []
        for tid in all_ids:
            p = placements.get(tid, {})
            r = regular.get(tid, {})
            rows.append({
                "season": season,
                "final_rank": p.get("final_rank"),
                "team_id": tid,
                "team_name": r.get("team_name") or p.get("team_name") or "",
                "owner": p.get("owner", ""),
                "division": r.get("division", ""),
                "division_rank": r.get("division_rank"),
                "overall_rank_reg_season": r.get("overall_rank_reg_season"),
                "wins": r.get("wins"),
                "losses": r.get("losses"),
                "ties": r.get("ties"),
                "win_pct": r.get("win_pct"),
                "points_for": r.get("points_for"),
                "points_against": r.get("points_against"),
                "streak": r.get("streak"),
            })
        rows.sort(key=lambda x: x["final_rank"] or 999)
        for r in rows:
            fr = r["final_rank"] if r["final_rank"] is not None else "?"
            print(
                f"    #{str(fr):>3}  team {r['team_id']:>2}  "
                f"{r['team_name']!r:30s}  "
                f"{r['wins']}-{r['losses']}-{r['ties']}  "
                f"PF={r['points_for']}  PA={r['points_against']}"
            )
        save_json(rows, output_path("standings", f"{season}.json"))
        save_csv(rows, output_path("standings", f"{season}.csv"))
        combined_standings.extend(rows)

    save_csv(combined_standings, output_path("standings_all_seasons.csv"))
    save_json(combined_standings, output_path("standings_all_seasons.json"))
    print(f"\n>>> Saved {len(combined_standings)} standings rows")

    print("\n" + "=" * 70)
    print("Re-parsing matchups from cached HTML")
    print("=" * 70)

    all_matchups = []
    for season in config.SEASONS:
        print(f"\n=== Season {season} ===")
        season_dir = output_path("matchups", str(season))
        season_dir.mkdir(parents=True, exist_ok=True)
        season_total = 0
        for week in config.WEEKS:
            html = _read_cached(season, f"week_{week:02d}_schedule.html")
            if not html:
                continue
            rows = parse_week_schedule(html, season, week)
            if rows:
                save_json(rows, season_dir / f"week_{week:02d}.json")
                all_matchups.extend(rows)
                season_total += len(rows) // 2
        print(f"  Parsed {season_total} matchups")

    save_csv(all_matchups, output_path("matchups_all.csv"))
    save_json(all_matchups, output_path("matchups_all.json"))
    print(f"\n>>> Saved {len(all_matchups)} matchup-team rows "
          f"({len(all_matchups)//2} matchups)")

    print("\n✓ Re-parse complete. Now run: python scripts/05_analyze.py")


if __name__ == "__main__":
    main()