"""
01 — List all teams and confirm your team_id.

Since your team_id is now known (1, Joey), this script is mostly diagnostic:
  - Verifies your cookies work
  - Pulls every team name + owner per season into teams.{csv,json}
  - Helpful if team names changed year to year
"""

import re

from _common import (
    BASE,
    config,
    ensure_dirs,
    make_session,
    output_path,
    polite_get,
    save_csv,
    save_json,
    save_raw_html,
    soup,
    clean_text,
)


def fetch_owners(session, season: int) -> list[dict]:
    """The owners page lists team_id + team name + owner display name."""
    url = f"{BASE}/league/{config.LEAGUE_ID}/history/{season}/owners"
    print(f"  Fetching {url}")
    resp = polite_get(session, url)
    save_raw_html(resp.text, str(season), "owners.html")
    page = soup(resp.text)

    teams: list[dict] = []
    seen_ids = set()

    # Strategy: find every link that looks like teamhome with a teamId
    for link in page.find_all("a", href=lambda h: h and "teamhome" in h):
        m = re.search(r"teamId=(\d+)", link.get("href", ""))
        if not m:
            continue
        team_id = int(m.group(1))
        if team_id in seen_ids:
            continue
        team_name = clean_text(link.get_text())
        if not team_name or len(team_name) > 60:
            continue

        # Owner — look for a userName span nearby in the parent row
        owner = ""
        user_id = None
        parent = link.find_parent(["tr", "li", "div"])
        if parent:
            user_span = parent.find("span", class_=re.compile(r"\buserName\b"))
            if user_span:
                owner = clean_text(user_span.get_text())
                for c in user_span.get("class", []):
                    mm = re.match(r"userId-(\d+)", c)
                    if mm:
                        user_id = int(mm.group(1))
                        break

        teams.append(
            {
                "season": season,
                "team_id": team_id,
                "team_name": team_name,
                "owner": owner,
                "user_id": user_id,
            }
        )
        seen_ids.add(team_id)

    teams.sort(key=lambda t: t["team_id"])
    return teams


def main():
    ensure_dirs(output_path())
    session = make_session()

    all_teams: list[dict] = []
    for season in config.SEASONS:
        print(f"\n=== Season {season} ===")
        try:
            teams = fetch_owners(session, season)
        except Exception as e:
            print(f"  !! Failed: {e}")
            continue
        if not teams:
            print("  (no teams parsed)")
        for t in teams:
            print(
                f"    team_id={t['team_id']:>3}  {t['team_name']!r:30s}  "
                f"owner={t['owner']!r}"
            )
            all_teams.append(t)

    save_json(all_teams, output_path("teams.json"))
    save_csv(all_teams, output_path("teams.csv"))
    print(f"\nSaved {len(all_teams)} team-season rows to output/teams.{{json,csv}}")


if __name__ == "__main__":
    main()
