"""
Generate static-but-functional demo fixtures for pickems + powerrank.

What it produces:
- pickems/teams.json     — 12 demo teams w/ unique inline SVG logos
- pickems/users.json     — login accounts (PIN 1234 for everyone)
- pickems/manifest.json  — Week 1 (played) + Week 2 (open for picks)
- pickems/weeks/week*.json
- powerrank/manifest.json — Preseason + Week 1 + Week 2
- powerrank/weeks/*.json  — full schema with score = sum(factors),
                            real records that match pickems, projections
                            populated on every week.

Idempotent.
"""
import json, random, urllib.parse
from pathlib import Path

random.seed(11)
ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"

# ── Demo managers, in division order ─────────────────────────────────────────
md = json.load(open(DATA / "managers_directory.json"))["managers"]
ACTIVE = [m for m in md if m["is_current"]]
NAME = {m["user_id"]: m["name"] for m in md}
TEAM = {m["user_id"]: m["team_latest"] for m in md}
PEDIGREE_RAW = {m["user_id"]: m for m in md}  # for championships/top-3

NORTH = [1001, 1003, 1006, 1007, 1010, 1012]
SOUTH = [1002, 1004, 1005, 1008, 1009, 1011]
ALL_UIDS = NORTH + SOUTH

def team_id(name): return name.lower()
TID_TO_UID = {team_id(NAME[u]): u for u in ALL_UIDS}

# ── Per-team SVG logo (inline data URI) ──────────────────────────────────────
PALETTE = [
    "#a04830", "#6b8aa8", "#e8c889", "#8aad48",
    "#b09ad8", "#7aad8e", "#d494a8", "#c08060",
    "#d4bc60", "#6abdb8", "#a88a4a", "#d25555",
]

def make_logo(team_name, color):
    # Take initial of each major word, up to 2 chars (e.g. "Cold Front" → "CF")
    words = [w for w in team_name.replace("&", " ").split() if w and w[0].isalpha()]
    if len(words) >= 2:
        initials = (words[0][0] + words[1][0]).upper()
    else:
        initials = words[0][:2].upper()
    fs = 38 if len(initials) == 2 else 50
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 80 80">'
        f'<circle cx="40" cy="40" r="36" fill="{color}" stroke="#0e1620" stroke-width="3"/>'
        f'<text x="40" y="{52 if fs==38 else 56}" font-family="Georgia, serif" font-style="italic" '
        f'font-size="{fs}" font-weight="700" text-anchor="middle" fill="#f4ebd8" letter-spacing="-2">'
        f'{initials}</text></svg>'
    )
    return "data:image/svg+xml;utf8," + urllib.parse.quote(svg)

LOGO = {uid: make_logo(TEAM[uid], PALETTE[i % 12]) for i, uid in enumerate(ALL_UIDS)}

# ── pickems/teams.json ───────────────────────────────────────────────────────
teams_json = {
    "season": 2026,
    "teams": [
        {
            "id": team_id(NAME[uid]),
            "name": TEAM[uid],
            "manager": NAME[uid],
            "roster_id": i + 1,
            "division": 1 if uid in NORTH else 2,
            "division_name": "North" if uid in NORTH else "South",
            "logo": LOGO[uid],
        }
        for i, uid in enumerate(ALL_UIDS)
    ],
}
(ROOT / "pickems" / "teams.json").write_text(json.dumps(teams_json, indent=2))

# ── pickems/users.json ───────────────────────────────────────────────────────
users_json = {
    "accounts": [
        {"name": NAME[uid], "teamId": team_id(NAME[uid]), "pin": "1234"}
        for uid in ALL_UIDS
    ]
}
(ROOT / "pickems" / "users.json").write_text(json.dumps(users_json, indent=2))

# ── Pickems Week 1 fixture (played, with winners) ────────────────────────────
pickems_week1_pairs = [
    ("marcus", "tyler"),
    ("jordan", "ethan"),
    ("brandon", "devin"),
    ("cole", "trevor"),
    ("adam", "noah"),
    ("ryan", "owen"),
]
pickems_week1 = {
    "id": "week1",
    "label": "Week 1",
    "openAt": "2026-09-09T00:00:00Z",
    "gameOfWeek": "m1",
    "matchups": [
        {"id": f"m{i+1}", "home": h, "away": a}
        for i, (h, a) in enumerate(pickems_week1_pairs)
    ],
    "winners": {"m1": "marcus", "m2": "jordan", "m3": "devin",
                "m4": "cole", "m5": "noah", "m6": "owen"},
    "highestLowestOptions": [team_id(NAME[u]) for u in ALL_UIDS],
    "highest": "marcus",
    "lowest":  "trevor",
}
(ROOT / "pickems" / "weeks" / "week1.json").write_text(json.dumps(pickems_week1, indent=2))

# ── Pickems Week 2 (open for picks, no winners) ──────────────────────────────
pickems_week2_pairs = [
    ("marcus", "jordan"),
    ("tyler", "ethan"),
    ("brandon", "cole"),
    ("devin", "trevor"),
    ("adam", "ryan"),
    ("noah", "owen"),
]
pickems_week2 = {
    "id": "week2",
    "label": "Week 2",
    "openAt": "2026-09-16T00:00:00Z",
    "gameOfWeek": "m3",
    "matchups": [
        {"id": f"m{i+1}", "home": h, "away": a}
        for i, (h, a) in enumerate(pickems_week2_pairs)
    ],
    "winners": {},
    "highestLowestOptions": [team_id(NAME[u]) for u in ALL_UIDS],
}
(ROOT / "pickems" / "weeks" / "week2.json").write_text(json.dumps(pickems_week2, indent=2))

pickems_manifest = {
    "season": 2026,
    "weeks": [
        {"id": "week1", "label": "Week 1", "data": "weeks/week1.json"},
        {"id": "week2", "label": "Week 2", "data": "weeks/week2.json"},
    ],
}
(ROOT / "pickems" / "manifest.json").write_text(json.dumps(pickems_manifest, indent=2))

# ── Simulate real game results so records line up across both pages ──────────
# Week 1 results derived from pickems winners (so the two pages agree).
# Week 2 results synthesized here (purely demo-time, not shown on pickems yet).
records = {uid: {"w": 0, "l": 0, "pf": 0.0, "pa": 0.0, "last3": []} for uid in ALL_UIDS}

# Apply Week 1
WEEK1_PF = {}  # uid → points scored that week
for matchup in pickems_week1["matchups"]:
    h_uid = TID_TO_UID[matchup["home"]]
    a_uid = TID_TO_UID[matchup["away"]]
    win_tid = pickems_week1["winners"][matchup["id"]]
    win_uid = TID_TO_UID[win_tid]
    lose_uid = a_uid if win_uid == h_uid else h_uid

    win_pf  = round(random.uniform(120, 165), 2)
    lose_pf = round(win_pf - random.uniform(6, 35), 2)

    records[win_uid]["w"] += 1
    records[win_uid]["pf"] += win_pf
    records[win_uid]["pa"] += lose_pf
    records[win_uid]["last3"].append("W")
    records[lose_uid]["l"] += 1
    records[lose_uid]["pf"] += lose_pf
    records[lose_uid]["pa"] += win_pf
    records[lose_uid]["last3"].append("L")
    WEEK1_PF[win_uid]  = win_pf
    WEEK1_PF[lose_uid] = lose_pf

# Snapshot for week 1's powerrank
records_after_w1 = {u: {k: (list(v) if isinstance(v, list) else v) for k, v in records[u].items()} for u in records}

# Apply Week 2 (synthetic, deterministic by seed)
week2_pairs = [(TID_TO_UID[h], TID_TO_UID[a]) for h, a in pickems_week2_pairs]
for h_uid, a_uid in week2_pairs:
    h_pf = round(random.uniform(95, 165), 2)
    a_pf = round(random.uniform(95, 165), 2)
    if h_pf == a_pf:
        a_pf -= 0.5
    win_uid, lose_uid = (h_uid, a_uid) if h_pf > a_pf else (a_uid, h_uid)
    win_pf, lose_pf = (h_pf, a_pf) if h_pf > a_pf else (a_pf, h_pf)
    records[win_uid]["w"] += 1
    records[win_uid]["pf"] += win_pf
    records[win_uid]["pa"] += lose_pf
    records[win_uid]["last3"].append("W")
    records[lose_uid]["l"] += 1
    records[lose_uid]["pf"] += lose_pf
    records[lose_uid]["pa"] += win_pf
    records[lose_uid]["last3"].append("L")

records_after_w2 = records  # full

# ── Powerrank scoring: factors that ACTUALLY sum to score ────────────────────
def pedigree_pts(uid):
    """Cap at 34. Championships(14ea) + Top-3 finishes(12 total weighted) + playoff apps(8 total weighted)."""
    m = PEDIGREE_RAW[uid]
    chips = min(28, m["championships"] * 14)
    top3  = min(12, m["top_three_finishes"] * 3)
    appns = min(8, m["playoff_appearances"] * 1.5)
    return round(min(34, chips + top3 + appns), 2)

def career_winpct(uid):
    m = PEDIGREE_RAW[uid]
    g = m["wins"] + m["losses"]
    return m["wins"] / g if g else 0.0

def percentile_rank(uid, values):
    """Returns percentile 0..1 of values[uid] among all ALL_UIDS."""
    sorted_vals = sorted(values.values())
    v = values[uid]
    # rank from bottom
    rank = sorted_vals.index(v)
    return rank / (len(sorted_vals) - 1) if len(sorted_vals) > 1 else 0.5

def preseason_factors(uid):
    # win_pct (0-20)
    win_pct = round(career_winpct(uid) * 20, 2)
    # pf_avg (0-20) — percentile of career PF
    pf_vals = {u: PEDIGREE_RAW[u]["total_pf"] for u in ALL_UIDS}
    pf_avg = round(percentile_rank(uid, pf_vals) * 20, 2)
    # recent (0-26) — % of recent 3 seasons finishes (1st=high, last=low)
    # Pull from manager_highs/season ledger — easier: use top_three_finishes ratio
    m = PEDIGREE_RAW[uid]
    recent_ratio = (m["top_three_finishes"] * 0.4 + (m["playoff_appearances"] / max(1, m["seasons_played"])))
    recent = round(min(26, recent_ratio * 13), 2)
    # pedigree (0-34)
    ped = pedigree_pts(uid)
    return {"win_pct": win_pct, "pf_avg": pf_avg, "recent": recent, "pedigree": ped}

def inseason_factors(uid, rec_state, conf_rank_in_div):
    """Week 4+ formula. For weeks 1-3 the renderer treats it the same — we
    just pass whatever factors object we provide. Score = sum of these."""
    games = rec_state[uid]["w"] + rec_state[uid]["l"]
    # record (0-35) — current win pct * 35
    record = round((rec_state[uid]["w"] / max(1, games)) * 35, 2)
    # pf (0-35) — percentile of season PF among 12 teams
    pf_vals = {u: rec_state[u]["pf"] for u in ALL_UIDS}
    pf = round(percentile_rank(uid, pf_vals) * 35, 2)
    # form (0-15) — last 3 games win pct
    last3 = rec_state[uid]["last3"][-3:]
    form_w = sum(1 for x in last3 if x == "W")
    form = round((form_w / max(1, len(last3))) * 15, 2) if last3 else 0.0
    # conf (0-15) — 1st in division = 15, last = 0
    if conf_rank_in_div is None:
        conf = 0.0
    else:
        # 6 teams per division → ranks 1..6 → 15, 12, 9, 6, 3, 0
        conf = round(max(0, 15 - (conf_rank_in_div - 1) * 3), 2)
    return {"record": record, "pf": pf, "form": form, "conf": conf}

def projections(uid, rec_state, power_score):
    """proj_wins/losses (14 reg-season games), playoff_pct, bye_pct, conf_win_pct."""
    games_played = rec_state[uid]["w"] + rec_state[uid]["l"]
    games_left = max(0, 14 - games_played)
    # Future win rate ~ 0.30 + 0.45 * normalized_power
    future_winrate = 0.30 + 0.50 * (power_score / 100)
    future_wins = round(games_left * future_winrate)
    proj_wins = rec_state[uid]["w"] + future_wins
    proj_losses = 14 - proj_wins

    # playoff % — top 6 of 12 make playoffs; scale w/ power
    playoff_pct = round(max(5, min(96, 8 + power_score * 0.95)), 1)
    bye_pct = round(max(1, min(60, (power_score - 50) * 1.1)), 1)
    if bye_pct < 0: bye_pct = 1.0
    conf_win_pct = round(max(2, min(70, (power_score - 45) * 1.4)), 1)
    if conf_win_pct < 2: conf_win_pct = 2.0
    return {
        "proj_wins": proj_wins, "proj_losses": proj_losses,
        "playoff_pct": playoff_pct, "bye_pct": bye_pct,
        "conf_win_pct": conf_win_pct,
    }

def blend_factors_for_week(uid, week_num, rec_state, conf_rank):
    """Implements the 'blend history' rule from the formula popup:
       weeks 1-3 mix 30/20/10% preseason history into in-season factors,
       weeks 4+ are pure in-season. Keys are always in-season keys after week 0."""
    inseason = inseason_factors(uid, rec_state, conf_rank)
    if week_num >= 4:
        return inseason
    pre_score = sum(preseason_factors(uid).values())
    in_score  = sum(inseason.values())
    hist_w    = {1: 0.30, 2: 0.20, 3: 0.10}[week_num]
    blended   = in_score * (1 - hist_w) + pre_score * hist_w
    scale     = (blended / in_score) if in_score > 0 else 0
    # Scale in-season factors so they sum to the blended score
    out = {k: round(v * scale, 2) for k, v in inseason.items()}
    # Fix rounding drift so factors exactly equal blended score
    drift = round(blended, 2) - round(sum(out.values()), 2)
    if abs(drift) > 0.01:
        # Apply drift to the largest factor
        max_key = max(out, key=lambda k: out[k])
        out[max_key] = round(out[max_key] + drift, 2)
    return out

def build_team(uid, rank, rec_state, factors, prev_rank_map):
    score = round(sum(factors.values()), 2)
    prev_rank = prev_rank_map.get(uid)
    delta = (prev_rank - rank) if prev_rank else 0
    proj = projections(uid, rec_state, score)
    return {
        "rank": rank,
        "team_id": team_id(NAME[uid]),
        "team_name": TEAM[uid],
        "manager": NAME[uid],
        "logo": LOGO[uid],
        "division": 1 if uid in NORTH else 2,
        "division_name": "North" if uid in NORTH else "South",
        "wins": rec_state[uid]["w"],
        "losses": rec_state[uid]["l"],
        "pf": round(rec_state[uid]["pf"], 1),
        "pa": round(rec_state[uid]["pa"], 1),
        "score": score,
        "delta": delta,
        "factors": factors,
        **proj,
    }

# Empty record state for preseason
empty_state = {uid: {"w": 0, "l": 0, "pf": 0.0, "pa": 0.0, "last3": []} for uid in ALL_UIDS}

# ── Preseason snapshot ───────────────────────────────────────────────────────
preseason_factors_by_uid = {uid: preseason_factors(uid) for uid in ALL_UIDS}
preseason_ranked = sorted(ALL_UIDS, key=lambda u: -sum(preseason_factors_by_uid[u].values()))
preseason_overall = []
for rk, uid in enumerate(preseason_ranked):
    t = build_team(uid, rk + 1, empty_state, preseason_factors_by_uid[uid], {})
    t["is_preseason"] = True
    preseason_overall.append(t)
preseason_data = {
    "week": 0,
    "label": "Pre-Season",
    "season": 2026,
    "generated": "2026-09-01T16:00:00+00:00",
    "overall": preseason_overall,
    "whole":   [t for t in preseason_overall if t["division"] == 1],
    "skim":    [t for t in preseason_overall if t["division"] == 2],
}
(ROOT / "powerrank" / "weeks" / "preseason.json").write_text(json.dumps(preseason_data, indent=2))

# ── Week 1 snapshot ──────────────────────────────────────────────────────────
def build_week_snapshot(rec_state, prev_overall, week_num, label, generated):
    # Compute conference rank within division (by current factor sum)
    factors_by_uid = {uid: inseason_factors(uid, rec_state, None) for uid in ALL_UIDS}
    # First pass: rank within div using preliminary scores (without conf factor)
    prelim_score = {uid: sum(f for k, f in factors_by_uid[uid].items() if k != "conf") for uid in ALL_UIDS}
    north_ranked = sorted(NORTH, key=lambda u: -prelim_score[u])
    south_ranked = sorted(SOUTH, key=lambda u: -prelim_score[u])
    conf_rank = {}
    for i, uid in enumerate(north_ranked): conf_rank[uid] = i + 1
    for i, uid in enumerate(south_ranked): conf_rank[uid] = i + 1

    # Second pass: factors include conf rank + blend history per week 1-3 rule
    factors_by_uid = {uid: blend_factors_for_week(uid, week_num, rec_state, conf_rank[uid]) for uid in ALL_UIDS}
    scored = sorted(ALL_UIDS, key=lambda u: -sum(factors_by_uid[u].values()))
    prev_rank_map = {t["team_id"]: t["rank"] for t in prev_overall}
    prev_rank_by_uid = {TID_TO_UID[tid]: rk for tid, rk in prev_rank_map.items()}

    overall = []
    for rk, uid in enumerate(scored):
        overall.append(build_team(uid, rk + 1, rec_state, factors_by_uid[uid], prev_rank_by_uid))
    return {
        "week": week_num,
        "label": label,
        "season": 2026,
        "generated": generated,
        "overall": overall,
        "whole":   [t for t in overall if t["division"] == 1],
        "skim":    [t for t in overall if t["division"] == 2],
    }

week1_data = build_week_snapshot(
    records_after_w1, preseason_overall, 1, "Week 1", "2026-09-11T17:00:00+00:00"
)
(ROOT / "powerrank" / "weeks" / "week1.json").write_text(json.dumps(week1_data, indent=2))

week2_data = build_week_snapshot(
    records_after_w2, week1_data["overall"], 2, "Week 2", "2026-09-18T17:00:00+00:00"
)
(ROOT / "powerrank" / "weeks" / "week2.json").write_text(json.dumps(week2_data, indent=2))

# Powerrank manifest
pr_manifest = {
    "season": 2026,
    "weeks": [
        {"id": "preseason", "label": "Pre-Season", "data": "weeks/preseason.json"},
        {"id": "week1",     "label": "Week 1",     "data": "weeks/week1.json"},
        {"id": "week2",     "label": "Week 2",     "data": "weeks/week2.json"},
    ],
}
(ROOT / "powerrank" / "manifest.json").write_text(json.dumps(pr_manifest, indent=2))

print("Pickems + Powerrank fixtures regenerated.")
print(f"  12 teams with unique SVG logos")
print(f"  Records: Week 1 winners drive both pages. Week 2 results applied to powerrank only.")
print(f"  Score = sum(factors). Projections populated on every week.")
sample = week1_data["overall"][0]
print(f"  Sample (Week 1 #1): {sample['team_name']} ({sample['manager']}) — score={sample['score']}, factors={sample['factors']}")
