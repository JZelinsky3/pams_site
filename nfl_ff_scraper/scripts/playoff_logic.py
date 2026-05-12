"""
Playoff bracket logic.

For each team in a season, determine which weeks of playoff matchups
count toward their record (and which are consolation games).

THE RULES (per the league):
  - A team makes the playoffs if their reg-season rank is within the
    bracket size (6 for most years, 8 for 2020).
  - In a 6-team playoff: seeds 1 and 2 get a Round 1 bye.
  - Once you lose, you're out — subsequent weeks are consolation and
    DO NOT count.
  - EXCEPTION: a Round 2 (semifinal) loser plays in the 3rd-place game
    the following week. THAT game counts as a playoff game.

USAGE:
    from playoff_logic import classify_playoff_matchups

    counted = classify_playoff_matchups(
        season=2023,
        team_matchups=[(week, won_bool), ...],   # team's playoff-week games chronologically
    )
    # returns set of weeks that count as playoff games for this team

For non-playoff teams: no playoff weeks count (they're in consolation
brackets from the start).
"""

import config


def classify_playoff_matchups(
    season: int,
    user_id: int,
    user_reg_rank: int | None,
    user_matchups: list[dict],
) -> dict:
    """
    Given one user's matchups across an entire season, return:
      {
          "made_playoffs": bool,
          "counted_playoff_weeks": set of week numbers that count toward record,
          "consolation_weeks":   set of week numbers that DON'T count,
      }

    user_matchups must be a chronological list of matchup rows for this user
    in this season. Each row needs at minimum: week, result ("W"/"L"/"T"), team_score.
    """
    bracket_size = config.PLAYOFF_BRACKET_SIZE.get(season, 6)
    playoff_weeks = sorted(config.PLAYOFF_WEEKS.get(season, []))

    made_playoffs = user_reg_rank is not None and user_reg_rank <= bracket_size

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

    # Did this team have a Round 1 bye?
    # In a 6-team bracket, seeds 1 and 2 get byes.
    # In an 8-team bracket, no byes.
    has_bye = bracket_size == 6 and user_reg_rank in (1, 2)

    # ---- Walk the team's playoff path ----
    alive = True
    last_result = None  # track if the most recent game was a loss (for 3rd-place game exception)

    # ROUND 1
    if not has_bye:
        m = matchups_by_week.get(w1)
        if m:
            counted.add(w1)
            if m["result"] == "L":
                alive = False
                last_result = "L"
            else:
                last_result = m["result"]
    # else: bye seed plays no Round 1 game (sometimes NFL.com still shows a matchup
    # in week 1 of playoffs for bye seeds — see note below)

    # NOTE: If a #1 or #2 seed in a 6-team bracket somehow appears in a Week 1 matchup,
    # that's a consolation/seeding game, not a real playoff game. So we should NOT count it.
    # If their team_id appears in matchups for w1 even though they have a bye, mark it consolation.
    if has_bye:
        m = matchups_by_week.get(w1)
        if m:
            consolation.add(w1)

    # ROUND 2 (semifinals)
    if alive:
        m = matchups_by_week.get(w2)
        if m:
            counted.add(w2)
            if m["result"] == "L":
                # Lost in semis — they will play the 3rd-place game in R3, which DOES count
                alive = False
                last_result = "L"
                last_round_lost = "semis"
            else:
                last_result = m["result"]
                last_round_lost = None
        else:
            # No semi matchup? Weird, but skip
            pass

    # ROUND 3 (championship or 3rd-place game)
    # Three sub-cases:
    #   a) Team won the semis → playing in the championship → counts
    #   b) Team lost the semis → playing in the 3rd-place game → counts (the exception)
    #   c) Team was already eliminated in QF → any R3 game is consolation
    if last_result == "L" and not alive:
        # If they lost in semis (R2), R3 is the 3rd-place game and counts.
        # But if they lost in QF (R1), R3 is a consolation game.
        # Determine which by checking when they lost.
        m_w2 = matchups_by_week.get(w2)
        if m_w2 and m_w2["result"] == "L":
            # Lost in semis → R3 counts (it's the 3rd-place game)
            m_w3 = matchups_by_week.get(w3)
            if m_w3:
                counted.add(w3)
        else:
            # Lost in QF (R1) → R3 is consolation
            m_w3 = matchups_by_week.get(w3)
            if m_w3:
                consolation.add(w3)
    elif alive:
        # Still alive after R2 = won the semis = playing in the chip game
        m_w3 = matchups_by_week.get(w3)
        if m_w3:
            counted.add(w3)
    else:
        # Defensive fallback
        m_w3 = matchups_by_week.get(w3)
        if m_w3:
            consolation.add(w3)

    return {
        "made_playoffs": True,
        "counted_playoff_weeks": counted,
        "consolation_weeks": consolation,
    }


def matchup_counts_as_playoff(
    season: int,
    week: int,
    user_id: int,
    user_reg_rank: int | None,
    user_season_matchups: list[dict],
) -> bool:
    """Convenience: does this single matchup count as a playoff game?"""
    if not config.is_playoff_week(season, week):
        return False
    result = classify_playoff_matchups(season, user_id, user_reg_rank, user_season_matchups)
    return week in result["counted_playoff_weeks"]