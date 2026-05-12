"""
Playoff bracket logic.

For each team in a season, determine which weeks of playoff matchups
count toward their record (and which are consolation games).

THE RULES:
  - A team makes the playoffs if their seed (caller-supplied) is within
    the bracket size (6 for most years, 8 for 2020).
  - In a 6-team playoff: seeds 1 and 2 get a Round 1 bye.
  - Once you lose, you're out — subsequent weeks are consolation and
    DO NOT count.
  - EXCEPTION: a Round 2 (semifinal) loser plays in the 3rd-place game
    the following week. THAT game counts as a playoff game.

The CALLER decides which seeding to use:
  - 2019-2024:  pass overall_rank_reg_season as `playoff_seed`
  - 2025:       pass final_rank as `playoff_seed` (custom non-standings seeding)
  - Generally:  whatever rank corresponds to actual playoff bracket position
"""

import config


def classify_playoff_matchups(
    season: int,
    user_id: int,
    playoff_seed: int | None,
    user_matchups: list[dict],
) -> dict:
    """
    Given one user's matchups across an entire season, return:
      {
          "made_playoffs": bool,
          "counted_playoff_weeks": set of week numbers that count toward record,
          "consolation_weeks":   set of week numbers that DON'T count,
      }

    Args:
        season: 4-digit year
        user_id: user_id of the team
        playoff_seed: this team's seed in the playoff bracket (1 = top seed).
            Pass None if seed is unknown — team will be treated as non-playoff.
        user_matchups: chronological list of matchup rows for this user
            in this season. Each row needs: week, result ("W"/"L"/"T"), team_score.
    """
    bracket_size = config.PLAYOFF_BRACKET_SIZE.get(season, 6)
    playoff_weeks = sorted(config.PLAYOFF_WEEKS.get(season, []))

    made_playoffs = playoff_seed is not None and playoff_seed <= bracket_size

    counted = set()
    consolation = set()

    if not made_playoffs:
        # Every playoff-week game for this team is consolation
        for m in user_matchups:
            if m["week"] in playoff_weeks:
                consolation.add(m["week"])
        return {
            "made_playoffs": False,
            "counted_playoff_weeks": counted,
            "consolation_weeks": consolation,
        }

    # Build a dict: week -> matchup
    matchups_by_week = {m["week"]: m for m in user_matchups}

    if len(playoff_weeks) != 3:
        # Defensive — we only handle 3-round brackets
        return {
            "made_playoffs": True,
            "counted_playoff_weeks": counted,
            "consolation_weeks": consolation,
        }

    w1, w2, w3 = playoff_weeks  # round 1, round 2, round 3

    # Bye seeds (top 2 in a 6-team bracket only)
    has_bye = bracket_size == 6 and playoff_seed in (1, 2)

    alive = True

    # ROUND 1
    if not has_bye:
        m = matchups_by_week.get(w1)
        if m:
            counted.add(w1)
            if m["result"] == "L":
                alive = False
    else:
        # Bye seed shouldn't have a real R1 game; if NFL.com shows one,
        # it's a placeholder/consolation
        m = matchups_by_week.get(w1)
        if m:
            consolation.add(w1)

    # ROUND 2 (semifinals)
    lost_in_semis = False
    if alive:
        m = matchups_by_week.get(w2)
        if m:
            counted.add(w2)
            if m["result"] == "L":
                alive = False
                lost_in_semis = True

    # ROUND 3 (championship or 3rd-place game)
    m_w3 = matchups_by_week.get(w3)
    if m_w3:
        if alive:
            # Won the semis → championship game → counts
            counted.add(w3)
        elif lost_in_semis:
            # Lost in semis → 3rd-place game → counts (the exception)
            counted.add(w3)
        else:
            # Lost in QF → R3 is consolation
            consolation.add(w3)

    return {
        "made_playoffs": True,
        "counted_playoff_weeks": counted,
        "consolation_weeks": consolation,
    }