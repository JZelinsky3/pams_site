"""
02 — Scrape final standings + regular-season records for every season.

NFL.com splits this across TWO pages, AND the regular-season page renders
multiple <table> elements (one per division, plus a "first place" table at top).
We loop every table and extract every team_id we see, capturing division name too.

Produces:
  output/standings/<season>.json
  output/standings/<season>.csv
  output/standings_all_seasons.csv  (combined)
"""

import re

from _common import (
    BASE,
    config,
    ensure_dirs,
    make_session,
    output_path,
    parse_float,
    parse_int,
    polite_get,
    save_csv,
    save_json,
    save_raw_html,
    soup,
    clean_text,
)


def parse_record(text: str) -> dict:
    text = (text or "").strip()
    m = re.match(r"(\d+)-(\d+)(?:-(\d+))?", text)
    if not m:
        return {"wins": None, "losses": None, "ties": None}
    return {
        "wins": int(m.group(1)),
        "losses": int(m.group(2)),
        "ties": int(m.group(3) or 0),
    }


def fetch_final_placements(session, season: int) -> dict[int, dict]:
    """
    Parse the 'final standings' page (1st place ... 12th place list).
    Used to get the final playoff finish — the regular-season page doesn't have it.
    """
    url = f"{BASE}/league/{config.LEAGUE_ID}/history/{season}/standings"
    print(f"  Fetching final placements: {url}")
    resp = polite_get(session, url)
    save_raw_html(resp.text, str(season), "standings_final.html")
    page = soup(resp.text)

    placements: dict[int, dict] = {}
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
            "final_rank": rank,
            "team_id": team_id,
            "team_name": team_name,
            "owner": owner,
        }
    return placements


def fetch_regular_season(session, season: int) -> dict[int, dict]:
    """
    Parse the regular-season standings — which is rendered as MULTIPLE tables
    (one per division). We loop every <table>, every <tr>, extract every team.

    The HTML pattern per team row is:
      <tr class="team-N">
        <td class="teamRank">...<span class="teamRank teamId-N">DIV_RANK</span>
            <span class="teamRank teamId-N">(OVERALL_RANK)</span>...</td>
        <td class="teamImageAndName"><a class="teamName teamId-N">NAME</a></td>
        <td class="teamRecord numeric">W-L-T</td>
        <td class="teamWinPct numeric">.571</td>
        <td class="teamStreak numeric">W2</td>
        <td class="teamPts stat numeric">1,812.08</td>      <-- Points For
        <td class="teamPts stat numeric last">1,700.56</td> <-- Points Against
      </tr>

    Division name comes from the <h5> just before each <table>.
    """
    url = (
        f"{BASE}/league/{config.LEAGUE_ID}/history/{season}/standings"
        f"?historyStandingsType=regular"
    )
    print(f"  Fetching regular season: {url}")
    resp = polite_get(session, url)
    save_raw_html(resp.text, str(season), "standings_regular.html")
    page = soup(resp.text)

    out: dict[int, dict] = {}
    seen = set()  # skip the "first place" duplicate at top of page

    # Each table is wrapped in a div.tableWrap, optionally preceded by an h5 division header
    for table_wrap in page.select("div.tableWrap"):
        # Division name from <h5><em>Division N</em>: NAME</h5>
        h5 = table_wrap.find("h5")
        division = ""
        if h5:
            division = clean_text(h5.get_text())
            division = re.sub(r"^Division\s*\d+\s*:\s*", "", division).strip()

        # The "firstTableWrap" is the duplicate-leader table — skip its rows
        # (they'll appear again under their division)
        is_leader_table = "firstTableWrap" in (table_wrap.get("class") or [])

        for tr in table_wrap.select("tbody tr"):
            # Find team_id from class like "team-2"
            team_id = None
            for c in tr.get("class", []):
                m = re.match(r"team-(\d+)", c)
                if m:
                    team_id = int(m.group(1))
                    break
            if team_id is None:
                team_link = tr.find("a", href=lambda h: h and "teamhome" in h)
                if team_link:
                    m = re.search(r"teamId=(\d+)", team_link.get("href", ""))
                    if m:
                        team_id = int(m.group(1))
            if team_id is None:
                continue

            if is_leader_table and team_id in seen:
                continue
            if team_id in seen:
                # already captured in the leader table — extend with division name
                if division and not out[team_id].get("division"):
                    out[team_id]["division"] = division
                continue

            # Team name
            team_name_a = tr.find("a", class_=re.compile(r"\bteamName\b"))
            team_name = clean_text(team_name_a.get_text()) if team_name_a else ""

            # Pull cells by their CSS class — much more reliable than positional indexing
            def cell_text(cls_pattern):
                td = tr.find("td", class_=re.compile(cls_pattern))
                return clean_text(td.get_text()) if td else None

            record_text = cell_text(r"\bteamRecord\b")
            rec = parse_record(record_text) if record_text else {
                "wins": None, "losses": None, "ties": None
            }

            win_pct = parse_float(cell_text(r"\bteamWinPct\b"))
            streak = cell_text(r"\bteamStreak\b")

            # Points: TWO td.teamPts cells — first is "For", second is "Against"
            pts_cells = tr.find_all("td", class_=re.compile(r"\bteamPts\b"))
            pf = parse_float(clean_text(pts_cells[0].get_text())) if len(pts_cells) >= 1 else None
            pa = parse_float(clean_text(pts_cells[1].get_text())) if len(pts_cells) >= 2 else None

            # Overall rank is the SECOND span inside td.teamRank, in parens: "(2)"
            # (when divisions exist — like 2023+)
            # For older seasons without divisions (like 2019), there's only ONE span
            # and it IS the overall rank directly.
            overall_rank = None
            div_rank = None
            rank_td = tr.find("td", class_=re.compile(r"\bteamRank\b"))
            if rank_td:
                spans = rank_td.find_all("span", class_=re.compile(r"\bteamRank\b"))
                if len(spans) >= 2:
                    # Multi-table (division) layout: first span = div rank, second = overall
                    div_rank = parse_int(clean_text(spans[0].get_text()))
                    m = re.search(r"\((\d+)\)", spans[1].get_text())
                    if m:
                        overall_rank = int(m.group(1))
                elif len(spans) == 1:
                    # Single-table layout (no divisions): the only rank IS the overall rank
                    overall_rank = parse_int(clean_text(spans[0].get_text()))
                    div_rank = None

            out[team_id] = {
                "team_id": team_id,
                "team_name": team_name,
                "division": division,
                "division_rank": div_rank,
                "overall_rank_reg_season": overall_rank,
                "wins": rec["wins"],
                "losses": rec["losses"],
                "ties": rec["ties"],
                "win_pct": win_pct,
                "streak": streak,
                "points_for": pf,
                "points_against": pa,
            }
            seen.add(team_id)

    return out


def main():
    ensure_dirs(output_path("standings"))
    session = make_session()

    combined: list[dict] = []
    for season in config.SEASONS:
        print(f"\n=== Standings: {season} ===")
        try:
            placements = fetch_final_placements(session, season)
        except Exception as e:
            print(f"  !! Final placements failed: {e}")
            placements = {}

        try:
            regular = fetch_regular_season(session, season)
        except Exception as e:
            print(f"  !! Regular season failed: {e}")
            regular = {}

        # Merge — union of both sources
        all_team_ids = set(placements) | set(regular)
        rows = []
        for team_id in all_team_ids:
            p = placements.get(team_id, {})
            r = regular.get(team_id, {})
            row = {
                "season": season,
                "final_rank": p.get("final_rank"),
                "team_id": team_id,
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
            }
            rows.append(row)

        rows.sort(key=lambda r: r["final_rank"] or 999)

        if not rows:
            print("  (no teams parsed)")
            continue
        for r in rows:
            fr = r["final_rank"] if r["final_rank"] is not None else "?"
            print(
                f"    #{str(fr):>3}  team {r['team_id']:>2}  "
                f"{r['team_name']!r:30s}  "
                f"{r['wins']}-{r['losses']}-{r['ties']}  "
                f"PF={r['points_for']}  PA={r['points_against']}  "
                f"div={r['division']!r}"
            )
        save_json(rows, output_path("standings", f"{season}.json"))
        save_csv(rows, output_path("standings", f"{season}.csv"))
        combined.extend(rows)

    save_csv(combined, output_path("standings_all_seasons.csv"))
    save_json(combined, output_path("standings_all_seasons.json"))
    print(f"\nSaved {len(combined)} total team-season rows.")


if __name__ == "__main__":
    main()