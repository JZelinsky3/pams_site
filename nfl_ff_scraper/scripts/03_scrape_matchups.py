"""
03 — Scrape every weekly matchup for every season.

Based on actual NFL.com HTML structure:
  <ul class="scheduleContent">
    <li class="matchups">
      <ul>
        <li class="matchup matchup-win|matchup-loss|matchup-tie">
          <div class="teamWrap teamWrap-1">
            <a class="teamName teamId-N">TEAM NAME</a>
            <ul class="teamStats">
              <li class="name"><span class="userName userId-N">Owner</span></li>
              <li class="record">RECORD <span class="teamRank">(rank)</span></li>
              <li class="streak">Streak: W3</li>
            </ul>
            <div class="teamTotal teamId-N">147.76</div>
          </div>
          <div class="teamWrap teamWrap-2">... opponent ...</div>
        </li>
      </ul>
    </li>
  </ul>

Produces:
  output/matchups/<season>/week_<NN>.json
  output/matchups_all.csv
  output/matchups_all.json
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


def parse_team_wrap(tw) -> dict | None:
    """Pull team_id, team_name, owner, user_id, score, record, rank, streak from one teamWrap div."""
    team_link = tw.find("a", class_=re.compile(r"\bteamName\b"))
    if not team_link:
        return None

    # team_id is in the class "teamName teamId-N"
    team_id = None
    for c in team_link.get("class", []):
        m = re.match(r"teamId-(\d+)", c)
        if m:
            team_id = int(m.group(1))
            break
    if team_id is None:
        # Fallback to href
        m = re.search(r"teamId=(\d+)", team_link.get("href", ""))
        if m:
            team_id = int(m.group(1))
    if team_id is None:
        return None

    team_name = clean_text(team_link.get_text())

    # Score is in a sibling <div class="teamTotal teamId-N">
    score = None
    total_div = tw.find("div", class_=re.compile(r"\bteamTotal\b"))
    if total_div:
        score = parse_float(clean_text(total_div.get_text()))

    # Owner name + NFL.com user id
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

    # Record (e.g. "1-0-0") and rank ("(2)")
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

    # Streak (in <li class="streak"> after the label)
    streak = ""
    streak_li = tw.find("li", class_=re.compile(r"\bstreak\b"))
    if streak_li:
        strong = streak_li.find("strong")
        if strong:
            streak = clean_text(strong.get_text())

    return {
        "team_id": team_id,
        "team_name": team_name,
        "owner": owner,
        "user_id": user_id,
        "score": score,
        "record_through_week": record,
        "rank_through_week": rank,
        "streak_through_week": streak,
    }


def fetch_week_schedule(session, season: int, week: int) -> list[dict]:
    """Fetch one season-week's schedule page and parse all matchups."""
    url = (
        f"{BASE}/league/{config.LEAGUE_ID}/history/{season}/schedule"
        f"?gameSeason={season}&leagueId={config.LEAGUE_ID}&scheduleDetail={week}"
        f"&scheduleType=week&standingsTab=schedule"
    )
    print(f"  W{week:>2}: {url}")
    resp = polite_get(session, url)
    save_raw_html(resp.text, str(season), f"week_{week:02d}_schedule.html")
    page = soup(resp.text)

    rows: list[dict] = []

    # Each matchup is an <li class="matchup matchup-win/loss/tie">
    for li in page.select("li.matchup"):
        # Find the two teamWrap divs inside this matchup
        wraps = li.find_all("div", class_=re.compile(r"\bteamWrap\b"), recursive=False)
        if len(wraps) != 2:
            # Some layouts have them nested deeper; try a non-recursive search
            wraps = [
                div
                for div in li.find_all("div", class_=re.compile(r"\bteamWrap\b"))
                if any(re.match(r"teamWrap-\d+", c) for c in div.get("class", []))
            ]
        if len(wraps) != 2:
            continue

        a = parse_team_wrap(wraps[0])
        b = parse_team_wrap(wraps[1])
        if not a or not b:
            continue

        # Determine result for each side
        if a["score"] is None or b["score"] is None:
            a_result = b_result = None
        elif a["score"] > b["score"]:
            a_result, b_result = "W", "L"
        elif a["score"] < b["score"]:
            a_result, b_result = "L", "W"
        else:
            a_result = b_result = "T"

        for me, opp, result in [(a, b, a_result), (b, a, b_result)]:
            rows.append(
                {
                    "season": season,
                    "week": week,
                    "team_id": me["team_id"],
                    "team_name": me["team_name"],
                    "owner": me["owner"],
                    "user_id": me["user_id"],
                    "team_score": me["score"],
                    "opp_team_id": opp["team_id"],
                    "opp_team_name": opp["team_name"],
                    "opp_owner": opp["owner"],
                    "opp_user_id": opp["user_id"],
                    "opp_score": opp["score"],
                    "result": result,
                    "margin": (
                        round(me["score"] - opp["score"], 2)
                        if me["score"] is not None and opp["score"] is not None
                        else None
                    ),
                    "record_through_week": me["record_through_week"],
                    "rank_through_week": me["rank_through_week"],
                    "streak_through_week": me["streak_through_week"],
                }
            )

    return rows


def main():
    ensure_dirs(output_path("matchups"))
    session = make_session()

    all_rows: list[dict] = []
    for season in config.SEASONS:
        print(f"\n=== Matchups: {season} ===")
        season_dir = output_path("matchups", str(season))
        season_dir.mkdir(parents=True, exist_ok=True)
        season_rows = 0
        for week in config.WEEKS:
            try:
                rows = fetch_week_schedule(session, season, week)
            except Exception as e:
                print(f"    !! Failed W{week}: {e}")
                continue
            if not rows:
                print(f"    W{week}: no matchups parsed (likely past playoffs)")
                continue
            save_json(rows, season_dir / f"week_{week:02d}.json")
            all_rows.extend(rows)
            season_rows += len(rows)
            print(f"    W{week}: parsed {len(rows)//2} matchups")
        print(f"  Season {season}: {season_rows//2} total matchups")

    save_csv(all_rows, output_path("matchups_all.csv"))
    save_json(all_rows, output_path("matchups_all.json"))
    print(f"\nSaved {len(all_rows)} matchup-team rows ({len(all_rows)//2} matchups)")


if __name__ == "__main__":
    main()
