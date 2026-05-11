"""
04 — Scrape weekly roster + player stats for YOUR team.

Produces:
  output/my_rosters/<season>/week_<NN>.json
  output/my_player_weekly.csv  (one row per player-week, your starters + bench)

Captures: player name, NFL team, position, slot (QB/RB/etc), fantasy points,
opponent, and game stats.
"""

import re

from _common import (
    BASE,
    config,
    ensure_dirs,
    make_session,
    output_path,
    parse_float,
    polite_get,
    save_csv,
    save_json,
    save_raw_html,
    soup,
    clean_text,
)


def fetch_my_roster_week(session, season: int, week: int) -> list[dict]:
    """
    Fetch your team's gamecenter page for a given week.
    URL pattern: /league/<L>/history/<season>/teamhome?statCategory=stats&statSeason=<season>&statType=weekStats&statWeek=<week>&teamId=<T>
    Or for the gamecenter view: /league/<L>/history/<season>/teamgamecenter?teamId=<T>&week=<W>
    """
    if not config.YOUR_TEAM_ID:
        raise RuntimeError(
            "Set YOUR_TEAM_ID in config.py first (run 01_find_my_team.py to discover it)."
        )

    url = (
        f"{BASE}/league/{config.LEAGUE_ID}/history/{season}/teamgamecenter"
        f"?teamId={config.YOUR_TEAM_ID}&week={week}"
    )
    print(f"  W{week:>2}: {url}")
    resp = polite_get(session, url)
    save_raw_html(resp.text, str(season), f"week_{week:02d}_roster.html")
    page = soup(resp.text)

    rows: list[dict] = []

    # Roster is rendered as table rows. Each player row has class containing "player"
    # and a slot label (QB/RB/WR/TE/FLEX/K/DEF/BN/IR).
    # We look for <table class="teamWrap ..."> with <tr> rows containing player anchors.
    for tr in page.select("tr"):
        # Slot label is usually in a <td class="teamPosition"> or first cell
        slot_cell = tr.find(class_=re.compile(r"(teamPosition|position)"))
        if not slot_cell:
            # Fallback: first td with short uppercase text like "QB", "BN"
            tds = tr.find_all("td")
            if not tds:
                continue
            slot_text = clean_text(tds[0].get_text())
            if not re.fullmatch(r"[A-Z/]{1,5}", slot_text):
                continue
            slot = slot_text
        else:
            slot = clean_text(slot_cell.get_text())

        player_link = tr.find("a", class_=re.compile(r"playerName|playerCard"))
        if not player_link:
            # Some rows are empty slots
            continue
        player_name = clean_text(player_link.get_text())

        # Player NFL team + position is typically in an <em> next to the name
        meta_em = tr.find("em")
        nfl_team, position = "", ""
        if meta_em:
            meta_text = clean_text(meta_em.get_text())  # e.g. "QB - KC"
            m = re.match(r"([A-Z/]+)\s*-\s*([A-Z]+)", meta_text)
            if m:
                position = m.group(1)
                nfl_team = m.group(2)

        # Player ID from link
        player_id = None
        href = player_link.get("href", "")
        m = re.search(r"playerId=(\d+)", href)
        if m:
            player_id = int(m.group(1))

        # Opponent — cell with class containing "opponent" or "playerOpponent"
        opp_cell = tr.find(class_=re.compile(r"opponent", re.I))
        opponent = clean_text(opp_cell.get_text()) if opp_cell else ""

        # Fantasy points — cell with class containing "statTotal" or "playerTotal"
        pts_cell = tr.find(class_=re.compile(r"statTotal|playerTotal|playerPts"))
        fantasy_points = (
            parse_float(clean_text(pts_cell.get_text())) if pts_cell else None
        )

        # Collect any other stat cells (passing yds, TDs, etc.) keyed by their CSS class
        extra_stats: dict[str, float | None] = {}
        for stat_cell in tr.find_all("td", class_=re.compile(r"stat")):
            classes = stat_cell.get("class", [])
            # Class like ['stat', 'stat_5'] — use the numeric id as the key
            for c in classes:
                m = re.fullmatch(r"stat_(\d+)", c)
                if m:
                    extra_stats[f"stat_{m.group(1)}"] = parse_float(
                        clean_text(stat_cell.get_text())
                    )

        rows.append(
            {
                "season": season,
                "week": week,
                "team_id": config.YOUR_TEAM_ID,
                "slot": slot,
                "player_id": player_id,
                "player_name": player_name,
                "position": position,
                "nfl_team": nfl_team,
                "opponent": opponent,
                "fantasy_points": fantasy_points,
                **extra_stats,
            }
        )

    return rows


def main():
    ensure_dirs(output_path("my_rosters"))
    session = make_session()

    all_rows: list[dict] = []
    for season in config.SEASONS:
        print(f"\n=== My rosters: {season} ===")
        season_dir = output_path("my_rosters", str(season))
        season_dir.mkdir(parents=True, exist_ok=True)
        for week in config.WEEKS:
            try:
                rows = fetch_my_roster_week(session, season, week)
            except Exception as e:
                print(f"    !! Failed W{week}: {e}")
                continue
            if not rows:
                continue
            save_json(rows, season_dir / f"week_{week:02d}.json")
            all_rows.extend(rows)
            print(f"    W{week}: parsed {len(rows)} player slots")

    save_csv(all_rows, output_path("my_player_weekly.csv"))
    save_json(all_rows, output_path("my_player_weekly.json"))
    print(f"\nSaved {len(all_rows)} player-week rows for your team.")
    print(
        "NOTE: NFL.com's stat column IDs (stat_1, stat_2, …) map to specific stats "
        "(pass yds, rush TDs, etc.). The mapping is league-scoring dependent — "
        "check output/_raw_html for the column headers if you need to translate them."
    )


if __name__ == "__main__":
    main()
