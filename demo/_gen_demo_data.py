"""
Lakeside League — Demo data generator.
Simulates 7 seasons (2019-2025) of fake-but-internally-consistent fantasy football
for 12 current managers + 5 former managers, then emits all JSON files the demo
site expects under demo/data/.

Idempotent: rerun to refresh.
"""
import json
import random
import os
from collections import defaultdict
from pathlib import Path

random.seed(2026)
ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"

# ── League constants ───────────────────────────────────────────────────────────
LEAGUE_NAME = "The Lakeside League"
LEAGUE_ABBR = "LSL"
FOUNDED = 2019
CURRENT_SEASON = 2025
ALL_YEARS = list(range(FOUNDED, CURRENT_SEASON + 1))  # 2019..2025
REG_WEEKS = 14  # 14-week regular season
PLAYOFF_WEEKS = 3  # 3-week playoffs (weeks 15-17), top 6 seeds

# ── 17 fake managers (12 active + 5 former) ────────────────────────────────────
# user_id, name, is_current, latest_team_name, joined_year, strength_bias (-2..+3)
MANAGERS = [
    # Active
    (1001, "Marcus",  True,  "Stoneridge Hammers",     2019,  2.5),
    (1002, "Tyler",   True,  "Crosstown Comets",       2019,  1.8),
    (1003, "Jordan",  True,  "Highland Hawks",         2019,  1.5),
    (1004, "Ethan",   True,  "Eastside Express",       2019,  1.2),
    (1005, "Brandon", True,  "Brimstone FC",           2019,  0.8),
    (1006, "Devin",   True,  "Den of Thieves",         2019,  1.7),
    (1007, "Cole",    True,  "Cold Front",             2020,  2.0),  # 2025 champ
    (1008, "Trevor",  True,  "Trojan Horse",           2019,  0.2),
    (1009, "Adam",    True,  "Avalanche",              2020, -0.2),
    (1010, "Noah",    True,  "Northern Lights",        2019,  0.5),
    (1011, "Ryan",    True,  "Riverside Reign",        2019, -0.3),
    (1012, "Owen",    True,  "Old Glory",              2023, -0.8),
    # Former (alumni)
    (1013, "Pete",    False, "Phantoms",               2019, -1.4),
    (1014, "Dave",    False, "Dark Horse",             2019,  0.4),
    (1015, "Greg",    False, "Gridiron Gospel",        2019, -1.0),
    (1016, "Sam",     False, "Steel City",             2021,  0.7),
    (1017, "Nathan",  False, "Nightcrawlers",          2019, -1.6),
]

NAME = {uid: n for uid, n, *_ in MANAGERS}
TEAM_LATEST = {uid: t for uid, _, _, t, *_ in MANAGERS}
IS_CURRENT = {uid: c for uid, _, c, *_ in MANAGERS}
BIAS = {uid: b for uid, *_, b in MANAGERS}

# ── Roster of 12 teams per season (with rotation as alumni come/go) ────────────
# Lock in a slightly different roster each year to make alumni history feel real.
def roster_for(year):
    # All 12 active managers always play. Add a former/alumni to fill if needed.
    actives = [uid for uid, *_, b in MANAGERS if IS_CURRENT[uid]]
    formers_history = {
        2019: [1013, 1014, 1015, 1017],  # Pete, Dave, Greg, Nathan (Cole/Adam not yet in 2019)
        2020: [1013, 1014, 1015],        # Pete, Dave, Greg (Cole/Adam joined; Nathan out)
        2021: [1014, 1016],              # Dave, Sam (Pete/Greg out)
        2022: [1016],                    # Sam
        2023: [1016],                    # Sam (Owen joins this year)
        2024: [],
        2025: [],
    }
    # In 2019 we have 12 actives - Cole(1007) - Adam(1009) - Owen(1012) = 9, +4 formers = 13 → drop one
    # Simpler: pre-build the per-year roster manually to fit 12 (or 14 in 2019)
    return None

# Manually defined roster of exactly 12 teams per year (14 in 2019 founding year)
SEASON_ROSTERS = {
    2019: [1001, 1002, 1003, 1004, 1005, 1006, 1008, 1010, 1011, 1013, 1014, 1015, 1016, 1017],  # 14 teams
    2020: [1001, 1002, 1003, 1004, 1005, 1006, 1007, 1008, 1010, 1011, 1013, 1014],
    2021: [1001, 1002, 1003, 1004, 1005, 1006, 1007, 1008, 1009, 1010, 1011, 1014],
    2022: [1001, 1002, 1003, 1004, 1005, 1006, 1007, 1008, 1009, 1010, 1011, 1016],
    2023: [1001, 1002, 1003, 1004, 1005, 1006, 1007, 1008, 1009, 1010, 1011, 1012],
    2024: [1001, 1002, 1003, 1004, 1005, 1006, 1007, 1008, 1009, 1010, 1011, 1012],
    2025: [1001, 1002, 1003, 1004, 1005, 1006, 1007, 1008, 1009, 1010, 1011, 1012],
}

# Pre-baked champions / runner-ups / 3rd by year — gives demo a believable narrative
PRESCRIBED_PODIUM = {
    2019: {"champ": 1001, "runner": 1003, "third": 1002},
    2020: {"champ": 1004, "runner": 1001, "third": 1006},
    2021: {"champ": 1002, "runner": 1006, "third": 1001},
    2022: {"champ": 1003, "runner": 1007, "third": 1002},
    2023: {"champ": 1001, "runner": 1004, "third": 1006},
    2024: {"champ": 1006, "runner": 1002, "third": 1007},
    2025: {"champ": 1007, "runner": 1001, "third": 1003},
}

# Divisions (only used for 2025 — matching pams_site behavior)
DIVISIONS_2025 = {
    "North": [1001, 1003, 1006, 1007, 1010, 1012],
    "South": [1002, 1004, 1005, 1008, 1009, 1011],
}

PRIZES = {
    2025: "$540",
    2024: "$480",
    2023: "$420",
    2022: "$360",
    2021: "$300",
    2020: "$240",
    2019: "$180",
}

# Team names per year (mostly use latest, but vary for early seasons to feel real)
def team_name(uid, year):
    base = TEAM_LATEST[uid]
    # Manager-specific name evolution
    history = {
        1001: {2019: "Hammer Time", 2020: "Hammer Time", 2021: "Stoneridge Hammers"},
        1002: {2019: "Comet Crew",  2020: "Comet Crew",  2021: "Crosstown Comets"},
        1003: {2019: "Hawks Nest",  2020: "Highland Hawks"},
        1004: {2020: "East End",    2021: "Eastside Express"},
        1006: {2019: "The Den",     2020: "Den of Thieves"},
        1007: {2020: "Coldfront 22", 2021: "Cold Front"},
    }
    return history.get(uid, {}).get(year, base)


# ──────────────────────────────────────────────────────────────────────────────
# Season simulator
# Each season: 12 (or 14) teams, 14-week regular season schedule + 3 playoff weeks.
# Output per season: list of (week, home_uid, away_uid, home_score, away_score, is_playoff)
# Plus final standings (forced to honor PRESCRIBED_PODIUM via post-hoc playoff fix-up).
# ──────────────────────────────────────────────────────────────────────────────

def gen_score(strength):
    """Generate a single-team fantasy score given a strength rating."""
    mean = 110 + strength * 6  # 100-130 typical
    s = random.gauss(mean, 22)
    return max(40, min(220, round(s, 2)))


def round_robin(teams):
    """Generate a single-round-robin schedule (each pair plays once). Returns list of weeks."""
    teams = list(teams)
    if len(teams) % 2:
        teams.append(None)
    n = len(teams)
    weeks = []
    for w in range(n - 1):
        pairs = []
        for i in range(n // 2):
            a, b = teams[i], teams[n - 1 - i]
            if a is not None and b is not None:
                pairs.append((a, b))
        weeks.append(pairs)
        teams = [teams[0]] + [teams[-1]] + teams[1:-1]
    return weeks


def simulate_season(year):
    teams = SEASON_ROSTERS[year]
    rr = round_robin(teams)
    weeks = []
    # Take first REG_WEEKS weeks (cycle if not enough)
    for w in range(REG_WEEKS):
        week_pairs = rr[w % len(rr)]
        matchups = []
        for (a, b) in week_pairs:
            sa = gen_score(BIAS[a])
            sb = gen_score(BIAS[b])
            matchups.append((w + 1, a, b, sa, sb, False))
        weeks.append(matchups)

    # Compute regular-season standings
    record = defaultdict(lambda: {"w": 0, "l": 0, "pf": 0.0, "pa": 0.0, "high": 0, "high_wk": None, "low": 9999})
    weekly_scores = defaultdict(list)  # uid → [(week, score, opp_uid, opp_score, result)]
    for week_matchups in weeks:
        for (wk, a, b, sa, sb, _) in week_matchups:
            record[a]["pf"] += sa; record[a]["pa"] += sb
            record[b]["pf"] += sb; record[b]["pa"] += sa
            if sa > sb:
                record[a]["w"] += 1; record[b]["l"] += 1
                weekly_scores[a].append((wk, sa, b, sb, "W"))
                weekly_scores[b].append((wk, sb, a, sa, "L"))
            elif sb > sa:
                record[b]["w"] += 1; record[a]["l"] += 1
                weekly_scores[a].append((wk, sa, b, sb, "L"))
                weekly_scores[b].append((wk, sb, a, sa, "W"))
            else:
                # treat the ridiculously rare exact tie as 0.01 bump to a
                sa += 0.01
                record[a]["w"] += 1; record[b]["l"] += 1
                weekly_scores[a].append((wk, sa, b, sb, "W"))
                weekly_scores[b].append((wk, sb, a, sa, "L"))
            if sa > record[a]["high"]:
                record[a]["high"] = sa; record[a]["high_wk"] = wk
            if sb > record[b]["high"]:
                record[b]["high"] = sb; record[b]["high_wk"] = wk
            if sa < record[a]["low"]: record[a]["low"] = sa
            if sb < record[b]["low"]: record[b]["low"] = sb

    # Force the prescribed podium into the top seeds — nudge wins of those teams
    podium = PRESCRIBED_PODIUM[year]
    for boost_uid in [podium["champ"], podium["runner"], podium["third"]]:
        if record[boost_uid]["w"] < 8:
            # swap a loss into a win
            losers = [u for u in teams if u != boost_uid and record[u]["w"] > 5]
            if losers:
                victim = random.choice(losers)
                record[boost_uid]["w"] += 1; record[boost_uid]["l"] -= 1
                record[victim]["w"] -= 1; record[victim]["l"] += 1

    # Regular-season rank order: wins desc, then pf desc
    reg_rank_list = sorted(teams, key=lambda u: (-record[u]["w"], -record[u]["pf"]))
    reg_rank = {u: i + 1 for i, u in enumerate(reg_rank_list)}

    # ── Playoffs: top 6 seeds. 3 rounds (wildcard, semis, final). Force champ. ──
    seeds = reg_rank_list[:6]
    # Re-order seeds so that the prescribed champ/runner/third sit at seeds 1-3 ish.
    if podium["champ"] not in seeds:
        seeds[-1] = podium["champ"]
    if podium["runner"] not in seeds:
        seeds[-2] = podium["runner"]
    if podium["third"] not in seeds:
        seeds[-3] = podium["third"]

    # Re-rank reg-season for those that moved (since standings show final_rank vs reg_season_rank)
    # We keep reg_rank as-is. final_rank is purely playoff-derived.

    # Build playoff brackets: seeds 1-6.
    # Week 15 (wildcard): 3v6, 4v5. Seeds 1, 2 bye.
    # Week 16 (semis): 1 vs lowest remaining, 2 vs other.
    # Week 17 (final): two semi winners.
    # Force outcomes so champ wins.
    playoff_matchups = []
    playoff_record = defaultdict(lambda: {"w": 0, "l": 0, "pf": 0.0, "pa": 0.0, "games": 0})

    def play_game(week, winner_uid, loser_uid, force_winner=True):
        sa = gen_score(BIAS[winner_uid] + 0.5)
        sb = gen_score(BIAS[loser_uid] - 0.5)
        if force_winner and sb >= sa:
            sa, sb = sb + 5.0, sa - 5.0  # ensure winner wins
        playoff_matchups.append((week, winner_uid, loser_uid, sa, sb, True))
        playoff_record[winner_uid]["w"] += 1; playoff_record[winner_uid]["games"] += 1
        playoff_record[loser_uid]["l"] += 1; playoff_record[loser_uid]["games"] += 1
        playoff_record[winner_uid]["pf"] += sa; playoff_record[winner_uid]["pa"] += sb
        playoff_record[loser_uid]["pf"] += sb; playoff_record[loser_uid]["pa"] += sa
        # weekly score record
        weekly_scores[winner_uid].append((week, sa, loser_uid, sb, "W"))
        weekly_scores[loser_uid].append((week, sb, winner_uid, sa, "L"))
        if sa > record[winner_uid]["high"]:
            record[winner_uid]["high"] = sa; record[winner_uid]["high_wk"] = week
        if sb > record[loser_uid]["high"]:
            record[loser_uid]["high"] = sb; record[loser_uid]["high_wk"] = week

    s1, s2, s3, s4, s5, s6 = seeds

    # Wildcard week 15: 3 vs 6, 4 vs 5. The prescribed champ/runner/third must survive.
    champ = podium["champ"]; runner = podium["runner"]; third = podium["third"]

    def survive(matchup_seeds):
        a, b = matchup_seeds
        # Prefer to keep champ > runner > third
        priority = {champ: 3, runner: 2, third: 1}
        if priority.get(a, 0) >= priority.get(b, 0):
            return a, b
        return b, a

    # Week 15
    w15_win1, w15_lose1 = survive((s3, s6))
    w15_win2, w15_lose2 = survive((s4, s5))
    play_game(15, w15_win1, w15_lose1)
    play_game(15, w15_win2, w15_lose2)

    # Semifinals week 16: s1 vs lower remaining; s2 vs higher remaining
    semis_pool = [s1, s2, w15_win1, w15_win2]
    # We want champ + runner + third still alive after semis (3rd-place game is separate)
    # Pair: s1 vs winner with lowest priority among (w15_win1, w15_win2)
    # Just hand-craft: split into two semis preserving champ + runner
    if champ in [s1, w15_win1]:
        semi_a = (s1, w15_win1); semi_b = (s2, w15_win2)
    else:
        semi_a = (s1, w15_win2); semi_b = (s2, w15_win1)

    sa1_win, sa1_lose = survive(semi_a)
    sb1_win, sb1_lose = survive(semi_b)
    play_game(16, sa1_win, sa1_lose)
    play_game(16, sb1_win, sb1_lose)

    # Championship week 17 — champ wins
    final_a, final_b = sa1_win, sb1_win
    if final_a == champ:
        play_game(17, final_a, final_b)
        runner_actual = final_b
    elif final_b == champ:
        play_game(17, final_b, final_a)
        runner_actual = final_a
    else:
        # champ got knocked out somehow — force a swap (shouldn't happen with above logic)
        play_game(17, final_a, final_b)
        runner_actual = final_b

    # Third-place game: the two semi losers
    third_game = (sa1_lose, sb1_lose)
    if third in third_game:
        # third wins their consolation
        winner = third; loser = sa1_lose if sb1_lose == third else sb1_lose
        play_game(17, winner, loser)
        third_actual = third
    else:
        # pick the higher seed as third
        winner = third_game[0]; loser = third_game[1]
        play_game(17, winner, loser)
        third_actual = winner

    # ── Compose final_rank ──
    # 1=champ, 2=runner, 3=third, then remaining seeds, then non-playoff teams in reg-season order
    final_rank = {champ: 1, runner_actual: 2, third_actual: 3}
    remaining_playoff = [u for u in seeds if u not in final_rank]
    for i, u in enumerate(remaining_playoff):
        final_rank[u] = 4 + i  # 4, 5, 6
    non_playoff = [u for u in reg_rank_list if u not in final_rank]
    for i, u in enumerate(non_playoff):
        final_rank[u] = 7 + i  # 7..12 (or 14 in 2019)

    all_matchups = []
    for week_matchups in weeks:
        all_matchups.extend(week_matchups)
    all_matchups.extend(playoff_matchups)

    # Ensure playoff_record has an entry for every team (non-playoff teams = zeros)
    for uid in teams:
        if uid not in playoff_record:
            playoff_record[uid] = {"w": 0, "l": 0, "pf": 0.0, "pa": 0.0, "games": 0}

    return {
        "year": year,
        "teams": teams,
        "matchups": all_matchups,
        "reg_record": dict(record),
        "playoff_record": dict(playoff_record),
        "reg_rank": reg_rank,
        "final_rank": final_rank,
        "weekly_scores": dict(weekly_scores),
        "podium": {"champ": champ, "runner": runner_actual, "third": third_actual},
    }


# ──────────────────────────────────────────────────────────────────────────────
# Generate all seasons
# ──────────────────────────────────────────────────────────────────────────────
print("Simulating seasons…")
SIMS = {y: simulate_season(y) for y in ALL_YEARS}

# ──────────────────────────────────────────────────────────────────────────────
# Build per-manager career aggregates
# ──────────────────────────────────────────────────────────────────────────────
career = {uid: {
    "wins": 0, "losses": 0, "ties": 0,
    "reg_w": 0, "reg_l": 0, "reg_pf": 0.0, "reg_pa": 0.0,
    "po_w": 0, "po_l": 0, "po_pf": 0.0, "po_pa": 0.0,
    "total_pf": 0.0,
    "seasons_played": 0,
    "championships": 0, "championship_seasons": [],
    "top_three": 0, "playoff_apps": 0,
    "total_games": 0,
    "season_ledger": [],   # one entry per season
    "all_weekly_scores": [],  # (year, week, score, opp_uid, opp_score, result, team_name, is_playoff)
    "h2h": defaultdict(lambda: {"reg_w": 0, "reg_l": 0, "po_w": 0, "po_l": 0, "reg_pf": 0.0, "reg_pa": 0.0, "po_pf": 0.0, "po_pa": 0.0}),
} for uid in NAME}

for year, sim in SIMS.items():
    for uid in sim["teams"]:
        rec = sim["reg_record"][uid]
        pop = sim["playoff_record"][uid]
        career[uid]["seasons_played"] += 1
        career[uid]["reg_w"] += rec["w"]; career[uid]["reg_l"] += rec["l"]
        career[uid]["reg_pf"] += rec["pf"]; career[uid]["reg_pa"] += rec["pa"]
        career[uid]["po_w"]  += pop["w"];  career[uid]["po_l"]  += pop["l"]
        career[uid]["po_pf"] += pop["pf"]; career[uid]["po_pa"] += pop["pa"]
        career[uid]["wins"] = career[uid]["reg_w"] + career[uid]["po_w"]
        career[uid]["losses"] = career[uid]["reg_l"] + career[uid]["po_l"]
        career[uid]["total_pf"] = career[uid]["reg_pf"] + career[uid]["po_pf"]
        career[uid]["total_games"] = career[uid]["wins"] + career[uid]["losses"]
        fr = sim["final_rank"][uid]
        if fr == 1:
            career[uid]["championships"] += 1
            career[uid]["championship_seasons"].append(year)
        if fr <= 3:
            career[uid]["top_three"] += 1
        if pop["games"] > 0:
            career[uid]["playoff_apps"] += 1

        # Season ledger entry
        reg_games = rec["w"] + rec["l"]
        career[uid]["season_ledger"].append({
            "year": year,
            "team_name": team_name(uid, year),
            "final_rank": fr,
            "reg_season_rank": sim["reg_rank"][uid],
            "reg_record": f"{rec['w']}-{rec['l']}-0",
            "reg_pf": round(rec["pf"], 2),
            "reg_pa": round(rec["pa"], 2),
            "playoff_record": f"{pop['w']}-{pop['l']}-0",
            "playoff_games": pop["games"],
            "playoff_pf": round(pop["pf"], 2),
            "total_pf": round(rec["pf"] + pop["pf"], 2),
            "avg_ppg": round((rec["pf"] + pop["pf"]) / max(1, reg_games + pop["games"]), 2),
            "high_week_score": round(rec["high"], 2),
            "low_week_score": round(rec["low"], 2),
            "high_week": rec["high_wk"],
        })

    # Build per-week weekly_scores into all_weekly_scores
    for uid in sim["teams"]:
        for (wk, score, opp, opp_score, result) in sim["weekly_scores"][uid]:
            is_po = wk > REG_WEEKS
            career[uid]["all_weekly_scores"].append({
                "year": year, "week": wk, "score": score, "opp_uid": opp,
                "opp_score": opp_score, "result": result,
                "team_name": team_name(uid, year), "is_playoff": is_po,
            })

    # H2H aggregation
    for (wk, a, b, sa, sb, is_po) in sim["matchups"]:
        winner, loser = (a, b) if sa > sb else (b, a)
        win_score, lose_score = (sa, sb) if sa > sb else (sb, sa)
        if is_po:
            career[a]["h2h"][b]["po_w" if winner == a else "po_l"] += 1
            career[b]["h2h"][a]["po_w" if winner == b else "po_l"] += 1
            career[a]["h2h"][b]["po_pf"] += sa
            career[a]["h2h"][b]["po_pa"] += sb
            career[b]["h2h"][a]["po_pf"] += sb
            career[b]["h2h"][a]["po_pa"] += sa
        else:
            career[a]["h2h"][b]["reg_w" if winner == a else "reg_l"] += 1
            career[b]["h2h"][a]["reg_w" if winner == b else "reg_l"] += 1
            career[a]["h2h"][b]["reg_pf"] += sa
            career[a]["h2h"][b]["reg_pa"] += sb
            career[b]["h2h"][a]["reg_pf"] += sb
            career[b]["h2h"][a]["reg_pa"] += sa


def calc_streaks(weekly):
    """Compute longest win + loss streaks given chronological list of weekly entries."""
    weekly = sorted(weekly, key=lambda w: (w["year"], w["week"]))
    max_w, cur_w = 0, 0
    max_w_when = ""
    cur_w_start = None
    max_l, cur_l = 0, 0
    max_l_when = ""
    cur_l_start = None
    last_w_end = None
    last_l_end = None
    for entry in weekly:
        when = f"W{entry['week']} {entry['year']}"
        if entry["result"] == "W":
            if cur_w == 0:
                cur_w_start = when
            cur_w += 1
            last_w_end = when
            if cur_w > max_w:
                max_w = cur_w
                max_w_when = f"{cur_w_start} → {last_w_end}"
            cur_l = 0; cur_l_start = None
        else:
            if cur_l == 0:
                cur_l_start = when
            cur_l += 1
            last_l_end = when
            if cur_l > max_l:
                max_l = cur_l
                max_l_when = f"{cur_l_start} → {last_l_end}"
            cur_w = 0; cur_w_start = None
    return ({"length": max_w, "when": max_w_when},
            {"length": max_l, "when": max_l_when})


# ──────────────────────────────────────────────────────────────────────────────
# Emit league.json
# ──────────────────────────────────────────────────────────────────────────────
total_matchups = sum(len(s["matchups"]) for s in SIMS.values())
def_champ_uid = SIMS[CURRENT_SEASON]["podium"]["champ"]
def_champ_rec = SIMS[CURRENT_SEASON]["reg_record"][def_champ_uid]
def_champ_pop = SIMS[CURRENT_SEASON]["playoff_record"][def_champ_uid]

league = {
    "name": LEAGUE_NAME,
    "abbreviation": LEAGUE_ABBR,
    "founded": FOUNDED,
    "current_season": CURRENT_SEASON,
    "total_matchups": total_matchups,
    "total_seasons": len(ALL_YEARS),
    "current_members_count": sum(1 for uid in NAME if IS_CURRENT[uid]),
    "former_members_count": sum(1 for uid in NAME if not IS_CURRENT[uid]),
    "all_seasons": ALL_YEARS,
    "defending_champion": {
        "year": CURRENT_SEASON,
        "team_name": team_name(def_champ_uid, CURRENT_SEASON),
        "owner_name": NAME[def_champ_uid],
        "owner_user_id": def_champ_uid,
        "record": f"{def_champ_rec['w']}-{def_champ_rec['l']}-0",
        "points_for": round(def_champ_rec["pf"] + def_champ_pop["pf"], 2),
    },
}
(DATA / "league.json").write_text(json.dumps(league, indent=2))

# ──────────────────────────────────────────────────────────────────────────────
# Emit managers_directory.json
# ──────────────────────────────────────────────────────────────────────────────
md = []
for uid, name, is_cur, latest, _, _ in MANAGERS:
    c = career[uid]
    games = c["wins"] + c["losses"]
    md.append({
        "user_id": uid,
        "name": name,
        "nfl_display_name": name,
        "team_latest": latest,
        "is_current": is_cur,
        "seasons_played": c["seasons_played"],
        "wins": c["wins"],
        "losses": c["losses"],
        "ties": 0,
        "total_record": f"{c['wins']}-{c['losses']}-0",
        "win_pct": round(c["wins"] / games, 4) if games else 0,
        "total_pf": round(c["total_pf"], 2),
        "championships": c["championships"],
        "championship_seasons": sorted(c["championship_seasons"]),
        "top_three_finishes": c["top_three"],
        "playoff_appearances": c["playoff_apps"],
    })
(DATA / "managers_directory.json").write_text(json.dumps({"managers": md}, indent=2))

# ──────────────────────────────────────────────────────────────────────────────
# Emit seasons_directory.json
# ──────────────────────────────────────────────────────────────────────────────
sd = []
for y in ALL_YEARS:
    champ = SIMS[y]["podium"]["champ"]
    sd.append({
        "year": y,
        "champion_name": NAME[champ],
        "champion_team_name": team_name(champ, y),
        "champion_user_id": champ,
        "total_teams": len(SIMS[y]["teams"]),
        "has_complete_data": True,
    })
(DATA / "seasons_directory.json").write_text(json.dumps({"seasons": sd}, indent=2))

# ──────────────────────────────────────────────────────────────────────────────
# Emit per-season files
# ──────────────────────────────────────────────────────────────────────────────
for y in ALL_YEARS:
    sim = SIMS[y]
    champ = sim["podium"]["champ"]; runner = sim["podium"]["runner"]; third = sim["podium"]["third"]
    champ_total_pf = sim["reg_record"][champ]["pf"] + sim["playoff_record"][champ]["pf"]

    # Standings (final_rank order)
    standings = []
    for uid in sorted(sim["teams"], key=lambda u: sim["final_rank"][u]):
        rec = sim["reg_record"][uid]
        pop = sim["playoff_record"][uid]
        total_w = rec["w"] + pop["w"]; total_l = rec["l"] + pop["l"]
        entry = {
            "final_rank": sim["final_rank"][uid],
            "reg_season_rank": sim["reg_rank"][uid],
            "team_id": uid - 1000,
            "team_name": team_name(uid, y),
            "owner_name": NAME[uid],
            "owner_user_id": uid,
            "wins": total_w,
            "losses": total_l,
            "ties": 0,
            "win_pct": round(total_w / max(1, total_w + total_l), 3),
            "points_for": round(rec["pf"] + pop["pf"], 2),
            "points_against": round(rec["pa"] + pop["pa"], 2),
        }
        if y == 2025:
            div = "North" if uid in DIVISIONS_2025["North"] else "South"
            entry["division"] = div
        standings.append(entry)

    season_obj = {
        "year": y,
        "total_teams": len(sim["teams"]),
        "champion": {
            "team_name": team_name(champ, y),
            "owner_name": NAME[champ],
            "owner_user_id": champ,
            "record": f"{sim['reg_record'][champ]['w']}-{sim['reg_record'][champ]['l']}-0",
            "points_for": round(champ_total_pf, 2),
        },
        "runner_up": {
            "team_name": team_name(runner, y),
            "owner_name": NAME[runner],
            "owner_user_id": runner,
        },
        "third_place": {
            "team_name": team_name(third, y),
            "owner_name": NAME[third],
            "owner_user_id": third,
        },
        "standings": standings,
    }
    (DATA / "seasons" / f"{y}.json").write_text(json.dumps(season_obj, indent=2))

# ──────────────────────────────────────────────────────────────────────────────
# Emit per-manager files (managers/<uid>.json)
# ──────────────────────────────────────────────────────────────────────────────
manager_highs_arr = []
for uid, name, is_cur, latest, _, _ in MANAGERS:
    c = career[uid]
    games = c["wins"] + c["losses"]
    if games == 0:
        continue
    win_streak, loss_streak = calc_streaks(c["all_weekly_scores"])
    tagline = f"{c['seasons_played']} seasons of league history. " + (
        f"{c['championships']} championship{'s' if c['championships'] != 1 else ''}." if c['championships'] else "Still chasing the first ring."
    )

    # H2H array (sorted by total_games desc)
    h2h_arr = []
    for opp_uid, h in sorted(c["h2h"].items(), key=lambda kv: -(kv[1]["reg_w"] + kv[1]["reg_l"] + kv[1]["po_w"] + kv[1]["po_l"])):
        total_w = h["reg_w"] + h["po_w"]; total_l = h["reg_l"] + h["po_l"]
        h2h_arr.append({
            "opp_user_id": opp_uid,
            "opp_name": NAME[opp_uid],
            "reg_record": f"{h['reg_w']}-{h['reg_l']}-0",
            "reg_pf": round(h["reg_pf"], 2),
            "reg_pa": round(h["reg_pa"], 2),
            "playoff_record": f"{h['po_w']}-{h['po_l']}-0",
            "playoff_pf": round(h["po_pf"], 2),
            "playoff_pa": round(h["po_pa"], 2),
            "total_record": f"{total_w}-{total_l}-0",
            "total_games": total_w + total_l,
        })

    high_score = max((s["score"] for s in c["all_weekly_scores"]), default=0)
    low_score = min((s["score"] for s in c["all_weekly_scores"]), default=0)
    avg_ppg = c["total_pf"] / max(1, c["total_games"])

    manager = {
        "user_id": uid,
        "name": name,
        "nfl_display_name": name,
        "is_current": is_cur,
        "tagline": tagline,
        "seasons_played": c["seasons_played"],
        "total_games": c["total_games"],
        "championships": c["championships"],
        "championship_seasons": sorted(c["championship_seasons"]),
        "top_three_finishes": c["top_three"],
        "playoff_appearances": c["playoff_apps"],
        "reg_record": f"{c['reg_w']}-{c['reg_l']}-0",
        "reg_win_pct": round(c["reg_w"] / max(1, c["reg_w"] + c["reg_l"]), 4),
        "reg_pf": round(c["reg_pf"], 2),
        "reg_pa": round(c["reg_pa"], 2),
        "playoff_record": f"{c['po_w']}-{c['po_l']}-0",
        "playoff_win_pct": round(c["po_w"] / max(1, c["po_w"] + c["po_l"]), 4) if (c["po_w"] + c["po_l"]) else 0,
        "playoff_pf": round(c["po_pf"], 2),
        "playoff_pa": round(c["po_pa"], 2),
        "high_score": round(high_score, 2),
        "low_score": round(low_score, 2),
        "avg_ppg": round(avg_ppg, 2),
        "longest_win_streak": win_streak,
        "longest_loss_streak": loss_streak,
        "season_ledger": sorted(c["season_ledger"], key=lambda s: s["year"]),
        "h2h": h2h_arr,
    }
    (DATA / "managers" / f"{uid}.json").write_text(json.dumps(manager, indent=2))

    # manager_highs.json: top 5 scoring weeks
    top5 = sorted(c["all_weekly_scores"], key=lambda s: -s["score"])[:5]
    manager_highs_arr.append({
        "user_id": uid,
        "name": name,
        "is_current": is_cur,
        "top5": [{
            "score": round(s["score"], 2),
            "opp_name": NAME[s["opp_uid"]],
            "opp_score": round(s["opp_score"], 2),
            "season": s["year"],
            "week": s["week"],
            "result": s["result"],
            "team": s["team_name"],
        } for s in top5],
    })

(DATA / "manager_highs.json").write_text(json.dumps(manager_highs_arr, indent=2))

# ──────────────────────────────────────────────────────────────────────────────
# Emit record_book.json
# Hub records: ~8 curated entries pulled from the simulated data.
# full_book: top-10 weekly scores + top-10 combined matchups (so the records page works).
# ──────────────────────────────────────────────────────────────────────────────
# Gather all games as weekly entries (one per team)
all_games = []
for year, sim in SIMS.items():
    for (wk, a, b, sa, sb, is_po) in sim["matchups"]:
        all_games.append({
            "year": year, "week": wk,
            "owner_uid": a, "owner": NAME[a], "team_name": team_name(a, year),
            "opp_uid": b, "opp_owner": NAME[b],
            "score": round(sa, 2), "opp_score": round(sb, 2),
            "combined": round(sa + sb, 2),
            "result": "W" if sa > sb else "L",
            "margin": round(abs(sa - sb), 2),
            "is_po": is_po,
        })
        all_games.append({
            "year": year, "week": wk,
            "owner_uid": b, "owner": NAME[b], "team_name": team_name(b, year),
            "opp_uid": a, "opp_owner": NAME[a],
            "score": round(sb, 2), "opp_score": round(sa, 2),
            "combined": round(sa + sb, 2),
            "result": "W" if sb > sa else "L",
            "margin": round(abs(sa - sb), 2),
            "is_po": is_po,
        })

# Hub records (~8 hand-picked, demo-flavored)
high_week = sorted(all_games, key=lambda g: -g["score"])[0]
biggest_blowout = sorted([g for g in all_games if g["result"] == "W"], key=lambda g: -g["margin"])[0]
closest = sorted([g for g in all_games if g["result"] == "W"], key=lambda g: g["margin"])[0]
shootout = sorted(all_games, key=lambda g: -g["combined"])[0]
lowest = sorted([g for g in all_games if not g["is_po"]], key=lambda g: g["score"])[0]

# Highest season PF (regular season only)
season_totals = []
for uid, c in career.items():
    for s in c["season_ledger"]:
        season_totals.append({
            "uid": uid, "name": NAME[uid], "year": s["year"], "team": s["team_name"],
            "reg_pf": s["reg_pf"], "reg_record": s["reg_record"],
        })
high_season = sorted(season_totals, key=lambda s: -s["reg_pf"])[0]

# Best reg-season record
best_reg = sorted(season_totals, key=lambda s: (-int(s["reg_record"].split("-")[0]), -s["reg_pf"]))[0]

# Longest win streak (across all managers)
all_streaks_w = []
all_streaks_l = []
for uid, c in career.items():
    ws, ls = calc_streaks(c["all_weekly_scores"])
    all_streaks_w.append((uid, ws))
    all_streaks_l.append((uid, ls))
top_w_streak = sorted(all_streaks_w, key=lambda x: -x[1]["length"])[0]
top_l_streak = sorted(all_streaks_l, key=lambda x: -x[1]["length"])[0]

hub_records = [
    {
        "label": "Highest Single-Week Score",
        "value": f"{high_week['score']:.2f}",
        "name": f"<em>{high_week['owner']}</em>, untouchable",
        "detail": f"{high_week['year']} · W{high_week['week']} · vs {high_week['opp_owner']}",
        "prose": f"<strong>{high_week['owner']}</strong> dropped {high_week['score']:.2f} on {high_week['opp_owner']} in week {high_week['week']} of the {high_week['year']} season — the highest single-week output in league history.",
        "gameContext": f"{high_week['year']} · Week {high_week['week']} · {high_week['score']:.2f} — {high_week['opp_score']:.2f}",
    },
    {
        "label": "Biggest Blowout",
        "value": f"{biggest_blowout['margin']:.2f}",
        "name": f"<em>{biggest_blowout['owner']}</em> over {biggest_blowout['opp_owner']}",
        "detail": f"{biggest_blowout['year']} · W{biggest_blowout['week']} · {biggest_blowout['score']:.2f} — {biggest_blowout['opp_score']:.2f}",
        "prose": f"<strong>{biggest_blowout['owner']}</strong> hung {biggest_blowout['score']:.0f} on {biggest_blowout['opp_owner']} in week {biggest_blowout['week']} of {biggest_blowout['year']}, {biggest_blowout['margin']:.0f} points clear — the most lopsided result in league history.",
        "gameContext": f"{biggest_blowout['year']} · Week {biggest_blowout['week']} · {biggest_blowout['score']:.2f} — {biggest_blowout['opp_score']:.2f}",
    },
    {
        "label": "Longest Win Streak",
        "value": f"{top_w_streak[1]['length']}",
        "name": f"<em>{NAME[top_w_streak[0]]}</em> on a heater",
        "detail": top_w_streak[1]["when"],
        "prose": f"<strong>{NAME[top_w_streak[0]]}</strong> ran off {top_w_streak[1]['length']} straight wins — the longest unbroken stretch any manager has put together.",
        "gameContext": f"{top_w_streak[1]['when']} · {top_w_streak[1]['length']} straight wins",
    },
    {
        "label": "Highest Season Total",
        "value": f"{high_season['reg_pf']:,.0f}",
        "name": f"<em>{high_season['name']}</em> — \"{high_season['team']}\"",
        "detail": f"{high_season['year']} · {high_season['reg_pf']/REG_WEEKS:.1f} ppg avg",
        "prose": f"<strong>{high_season['name']}</strong>'s {high_season['year']} \"{high_season['team']}\" piled up {high_season['reg_pf']:,.0f} regular-season points, averaging {high_season['reg_pf']/REG_WEEKS:.1f} a game.",
        "gameContext": f"{high_season['year']} Season · {high_season['reg_pf']:,.0f} PF · {high_season['reg_pf']/REG_WEEKS:.1f} ppg",
    },
    {
        "label": "Closest Game Ever",
        "value": f"{closest['margin']:.2f}",
        "name": f"<em>{closest['owner']}</em> over {closest['opp_owner']}",
        "detail": f"{closest['year']} · W{closest['week']} · {closest['score']:.2f} — {closest['opp_score']:.2f}",
        "prose": f"<strong>{closest['owner']}</strong> edged {closest['opp_owner']} by {closest['margin']:.2f} in week {closest['week']} of {closest['year']} — the tightest margin on the books.",
        "gameContext": f"{closest['year']} · Week {closest['week']} · {closest['score']:.2f} — {closest['opp_score']:.2f}",
    },
    {
        "label": "Shootout (Highest Combined)",
        "value": f"{shootout['combined']:.1f}",
        "name": f"<em>{shootout['owner']}</em> vs {shootout['opp_owner']}",
        "detail": f"{shootout['year']} · W{shootout['week']} · {shootout['score']:.2f} — {shootout['opp_score']:.2f}",
        "prose": f"<strong>{shootout['owner']}</strong> and <strong>{shootout['opp_owner']}</strong> combined for {shootout['combined']:.1f} in week {shootout['week']} of {shootout['year']} — the highest-scoring matchup ever played.",
        "gameContext": f"{shootout['year']} · Week {shootout['week']} · {shootout['score']:.2f} — {shootout['opp_score']:.2f}",
    },
    {
        "label": "Longest Losing Streak",
        "value": f"{top_l_streak[1]['length']}",
        "name": f"<em>{NAME[top_l_streak[0]]}</em>'s cold stretch",
        "detail": top_l_streak[1]["when"],
        "prose": f"<strong>{NAME[top_l_streak[0]]}</strong> dropped {top_l_streak[1]['length']} in a row — the longest cold stretch any manager has endured in league history.",
        "gameContext": f"{top_l_streak[1]['when']} · {top_l_streak[1]['length']} straight losses",
    },
    {
        "label": "Best Regular Season Record",
        "value": best_reg["reg_record"].rsplit("-", 1)[0],
        "name": f"<em>{best_reg['name']}</em> — \"{best_reg['team']}\"",
        "detail": f"{best_reg['year']} · seed 1",
        "prose": f"<strong>{best_reg['name']}</strong>'s {best_reg['year']} \"{best_reg['team']}\" team went {best_reg['reg_record'].rsplit('-', 1)[0]} in the regular season — the best single-season record in league history.",
        "gameContext": f"{best_reg['year']} Regular Season · {best_reg['reg_record'].rsplit('-', 1)[0]} · Seed 1",
    },
]

# Top-10 weekly (for record-book page tab "Sunday Spectacles" and "Legendary Duels")
top10_weekly = sorted(all_games, key=lambda g: -g["score"])[:10]
top10_matchups = []
seen_pairs = set()
for g in sorted(all_games, key=lambda g: -g["combined"]):
    key = (g["year"], g["week"], frozenset([g["owner_uid"], g["opp_uid"]]))
    if key in seen_pairs:
        continue
    seen_pairs.add(key)
    top10_matchups.append(g)
    if len(top10_matchups) >= 10:
        break

record_book = {
    "hub_records": hub_records,
    "full_book": {
        "weekly": {
            "highest_single_week_score": [{
                "score": g["score"],
                "owner": g["owner"],
                "user_id": g["owner_uid"],
                "opp_owner": NAME[g["opp_uid"]],
                "opp_user_id": g["opp_uid"],
                "opp_score": g["opp_score"],
                "season": g["year"],
                "week": g["week"],
                "team_name": g["team_name"],
            } for g in top10_weekly],
            "highest_combined_score": [{
                "score": g["score"],
                "owner": g["owner"],
                "user_id": g["owner_uid"],
                "opp_owner": NAME[g["opp_uid"]],
                "opp_user_id": g["opp_uid"],
                "opp_score": g["opp_score"],
                "combined_score": g["combined"],
                "season": g["year"],
                "week": g["week"],
                "team_name": g["team_name"],
                "result": g["result"],
            } for g in top10_matchups],
        },
        "season": {},
        "career": {},
    },
}
(DATA / "record_book.json").write_text(json.dumps(record_book, indent=2))

# ──────────────────────────────────────────────────────────────────────────────
# Draft files — remap real NFL player data from existing pams_site/data/drafts
# to the demo's manager IDs and names. Real players keep them looking authentic.
# ──────────────────────────────────────────────────────────────────────────────
PAMS_DRAFTS = Path("/Users/jojo/Desktop/pams_site/data/drafts")
# PAMS manager ID → demo manager ID. Use the SEASON_ROSTERS to choose 12 (or 14 in 2019).
# We map by slot order — pams's draft order is preserved (snake-draft mechanics fine).
PAMS_TO_DEMO_2025 = {
    21679447: 1007,  # Mason → Cole (champ)
    21679440: 1001,  # Joey → Marcus
    30533399: 1004,  # Evan → Ethan
    25033943: 1003,  # Isaac → Jordan
    21680087: 1006,  # Kyle → Devin
    21679454: 1010,  # Connie → Noah
    21680682: 1002,  # Andrew → Tyler
    21239480: 1011,  # Connor → Ryan
    21688760: 1008,  # Sean → Trevor
    22539599: 1005,  # Charlie → Brandon
    21680417: 1012,  # Chris → Owen
    25036608: 1009,  # Luke → Adam
}

# For older seasons, build a remap that picks 12/14 names from the demo roster for that year
def build_remap(year):
    pams_path = PAMS_DRAFTS / f"{year}.json"
    pams = json.loads(pams_path.read_text())
    pams_uids = []
    for p in pams["picks"]:
        if p["user_id"] not in pams_uids:
            pams_uids.append(p["user_id"])
    # 2025 has the canonical mapping
    if year == 2025:
        return PAMS_TO_DEMO_2025
    # Otherwise, map pams uids to demo uids in this season's roster (in order)
    demo_roster = SEASON_ROSTERS[year]
    remap = {}
    for i, pams_uid in enumerate(pams_uids):
        if i < len(demo_roster):
            remap[pams_uid] = demo_roster[i]
    return remap

drafts_dir = DATA / "drafts"
drafts_dir.mkdir(exist_ok=True)
for y in ALL_YEARS:
    pams = json.loads((PAMS_DRAFTS / f"{y}.json").read_text())
    remap = build_remap(y)
    new_picks = []
    for p in pams["picks"]:
        if p["user_id"] not in remap:
            continue  # skip unmapped (shouldn't happen)
        demo_uid = remap[p["user_id"]]
        new_picks.append({
            **p,
            "team_name": team_name(demo_uid, y),
            "manager_name": NAME[demo_uid],
            "user_id": demo_uid,
        })
    out = {"year": y, "picks": new_picks}
    (drafts_dir / f"{y}.json").write_text(json.dumps(out, indent=2))

# drafts_directory.json
drafts_directory = {"drafts": [
    {"year": y, "total_picks": len(json.loads((drafts_dir / f"{y}.json").read_text())["picks"]),
     "rounds": 15} for y in ALL_YEARS
]}
(drafts_dir / "drafts_directory.json").write_text(json.dumps(drafts_directory, indent=2))

# fantasy_ranks — empty stub so draft page doesn't 404 (not strictly needed)
(DATA / "fantasy_ranks").mkdir(exist_ok=True)

# ──────────────────────────────────────────────────────────────────────────────
# Pickems / Powerrank — frozen "preseason 2026" state
# ──────────────────────────────────────────────────────────────────────────────
pickems_manifest = {"season": 2026, "weeks": []}
(ROOT / "pickems" / "manifest.json").write_text(json.dumps(pickems_manifest, indent=2))

# users.json — generic demo accounts (12 active managers with PIN 1234)
pickems_users = {
    "users": [
        {"name": NAME[uid], "pin": "1234", "user_id": uid}
        for uid, _, is_cur, *_ in MANAGERS if is_cur
    ]
}
(ROOT / "pickems" / "users.json").write_text(json.dumps(pickems_users, indent=2))

# Powerrank: preseason snapshot
preseason_pr = {
    "week_id": "preseason",
    "week_label": "Pre-Season",
    "generated_at": "2026-08-15",
    "rankings": [],
}
# Sort current 12 by total_pf desc as preseason ranking
current_uids = [uid for uid in NAME if IS_CURRENT[uid]]
ranked = sorted(current_uids, key=lambda u: -career[u]["total_pf"])
for i, uid in enumerate(ranked):
    c = career[uid]
    games = c["wins"] + c["losses"]
    preseason_pr["rankings"].append({
        "rank": i + 1,
        "user_id": uid,
        "manager": NAME[uid],
        "team_name": TEAM_LATEST[uid],
        "score": round(80 - i * 4 + random.uniform(-3, 3), 1),
        "delta": 0,
        "record": f"{c['wins']}-{c['losses']}-0",
        "pf": round(c["total_pf"], 2),
        "championships": c["championships"],
        "blurb": f"{c['seasons_played']}-season vet" + (f", {c['championships']}× champ" if c['championships'] else "")
    })
(ROOT / "powerrank" / "weeks" / "preseason.json").write_text(json.dumps(preseason_pr, indent=2))
pr_manifest = {
    "season": 2026,
    "weeks": [{"id": "preseason", "label": "Pre-Season", "data": "weeks/preseason.json"}],
}
(ROOT / "powerrank" / "manifest.json").write_text(json.dumps(pr_manifest, indent=2))

# teams.json — pickems also looks for a teams file mapping uid to team_name for current season
pickems_teams = {NAME[uid]: TEAM_LATEST[uid] for uid in NAME if IS_CURRENT[uid]}
(ROOT / "pickems" / "teams.json").write_text(json.dumps(pickems_teams, indent=2))

print("Done.")
print(f"  Seasons: {len(ALL_YEARS)}  Managers: {len(MANAGERS)} ({sum(IS_CURRENT.values())} active)")
print(f"  Total matchups: {total_matchups}")
print(f"  Defending champion: {NAME[def_champ_uid]} ({TEAM_LATEST[def_champ_uid]})")
