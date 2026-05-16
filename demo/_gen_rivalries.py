"""
Generate the demo rivalries page from real H2H + matchup data.
Rewrites just the <main class="rv-grid">...</main> block + the header stats.
"""
import json, re
from pathlib import Path
from collections import defaultdict

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"

# Load manager directory + per-manager details
md = json.load(open(DATA / "managers_directory.json"))["managers"]
current = {m["user_id"]: m["name"] for m in md if m["is_current"]}
team_latest = {m["user_id"]: m["team_latest"] for m in md}
details = {m["user_id"]: json.load(open(DATA / "managers" / f"{m['user_id']}.json")) for m in md if m["is_current"]}

# Find 6 most interesting head-to-head rivalries among current managers
pairs = {}
for uid, d in details.items():
    for h in d["h2h"]:
        opp = h["opp_user_id"]
        if opp not in current: continue
        key = tuple(sorted([uid, opp]))
        if key in pairs: continue
        wl = h["total_record"].split("-")
        my_w, my_l = int(wl[0]), int(wl[1])
        games = my_w + my_l
        if games < 6: continue
        margin = abs(my_w - my_l)
        score = games * 10 - margin * 3
        pairs[key] = {
            "a_uid": uid, "b_uid": opp,
            "a_w": my_w, "a_l": my_l, "games": games,
            "margin": margin, "score": score,
            "a_reg": h["reg_record"], "a_po": h["playoff_record"],
            "b_reg": "-".join(h["reg_record"].split("-")[::-1][1:] + [h["reg_record"].split("-")[1], h["reg_record"].split("-")[0], h["reg_record"].split("-")[2]]),
            "a_reg_pf": h["reg_pf"], "a_reg_pa": h["reg_pa"],
            "a_po_pf": h["playoff_pf"], "a_po_pa": h["playoff_pa"],
        }

top_pairs = sorted(pairs.values(), key=lambda p: -p["score"])[:6]

# For each pair, dig into the actual matchup history to extract: last 5 games and the most lopsided game
# Load all season matchups by reading season files (have only standings) — instead, regenerate from simulation
# Simpler approach: each h2h entry on the manager file has aggregates only. We need per-game details.
# Use the per-manager all_weekly_scores would help, but we didn't persist that. So let me load season files and
# reconstruct matchups by looking at the per-week scores stored in season standings? Season files only have aggregates.
# So we need to either re-run the simulator (overkill) or use what's stored.
# Pragmatic fix: load each manager's TOP-5 weekly + use the per-manager all-weekly data — but that's not persisted.
#
# What IS persisted in manager files: season_ledger (per-season aggregates), h2h (per-opponent aggregates).
# Neither has per-game records.
#
# Solution: use the records in record_book.json (top10 weekly and combined) to find a "key moment" per rivalry
# when possible; otherwise use a generic blurb from the H2H aggregate.

rb = json.load(open(DATA / "record_book.json"))
weekly_top = rb["full_book"]["weekly"]["highest_single_week_score"]
matchup_top = rb["full_book"]["weekly"]["highest_combined_score"]

def find_moment(a_uid, b_uid):
    """Try to find a record-book entry that involved this pair."""
    a_name = current[a_uid]; b_name = current[b_uid]
    for g in matchup_top:
        if {g["owner"], g["opp_owner"]} == {a_name, b_name}:
            return ("Shootout", g)
    for g in weekly_top:
        if {g["owner"], g["opp_owner"]} == {a_name, b_name}:
            return ("Big Score", g)
    return (None, None)

# Build per-pair last-5 by re-importing the simulator
# Re-running is expensive but cleanest; alternative: persist the weekly schedule.
# Cleanest: import the generator module — but it has side effects. Let me re-run it
# carefully by isolating the simulation step.
import importlib.util
spec = importlib.util.spec_from_file_location("gen", ROOT / "_gen_demo_data.py")
gen = importlib.util.module_from_spec(spec)
# The generator writes files as a side effect; we suppress that by patching write_text
import builtins
_orig_write = Path.write_text
def noop(self, *a, **k): return None
Path.write_text = noop
try:
    spec.loader.exec_module(gen)
finally:
    Path.write_text = _orig_write

SIMS = gen.SIMS

# Build chronological per-pair game list from SIMS
pair_games = defaultdict(list)
for year, sim in SIMS.items():
    for (wk, a, b, sa, sb, is_po) in sim["matchups"]:
        if a in current and b in current:
            key = tuple(sorted([a, b]))
            pair_games[key].append({
                "year": year, "week": wk, "a": a, "b": b, "sa": sa, "sb": sb, "is_po": is_po,
            })

# Sort each pair chronologically
for k in pair_games:
    pair_games[k].sort(key=lambda g: (g["year"], g["week"]))

# --- Build the rivalry cards HTML ---
RIVALRY_NAMES = [
    "THE BORDER WAR",
    "THE LAKEFRONT BOWL",
    "THE STANDOFF",
    "THE COLD WAR",
    "THE NEIGHBORS' FEUD",
    "THE GROUDGE MATCH",
]
TAGLINES = [
    "Twelve months of trash talk. Sixty minutes to back it up.",
    "Tied or trailing — every meeting feels like the tiebreaker.",
    "Familiarity breeds contempt. So does the schedule.",
    "First on the schedule, last to be forgiven.",
    "Nothing personal. Except all of it.",
    "Decided in the regular season. Decided again in the playoffs.",
]

cards_html = []
total_meetings = 0
leaders_count = 0
deadlocked_count = 0

for i, p in enumerate(top_pairs):
    a_uid, b_uid = p["a_uid"], p["b_uid"]
    key = tuple(sorted([a_uid, b_uid]))
    games = pair_games[key]
    if not games:
        continue
    # Recompute totals from per-game data (a's perspective)
    a_wins = sum(1 for g in games if (g["a"] == a_uid and g["sa"] > g["sb"]) or (g["b"] == a_uid and g["sb"] > g["sa"]))
    b_wins = len(games) - a_wins
    total_meetings += len(games)

    if a_wins == b_wins:
        deadlocked_count += 1
        badge = f'<span class="rv-badge tied">Deadlocked · {a_wins}–{b_wins}</span>'
        bar = '<div class="rv-bar" style="background: #374151"></div>'
        series_lbl = '<div class="rv-series-lbl tied">Deadlocked</div>'
        wins_class_a = "tied-color"; wins_class_b = "tied-color"
        side_a_class = ""; side_b_class = ""
    elif a_wins > b_wins:
        leaders_count += 1
        badge = f'<span class="rv-badge">{current[a_uid]} Leads · {a_wins}–{b_wins}</span>'
        pct = a_wins / len(games) * 100
        bar = f'<div class="rv-bar" style="background: linear-gradient(to right, #dc2626 0%, #dc2626 {pct:.1f}%, #1f2937 {pct:.1f}%, #1f2937 100%)"></div>'
        series_lbl = f'<div class="rv-series-lbl">{current[a_uid]} Leads</div>'
        wins_class_a = "hot"; wins_class_b = ""
        side_a_class = "side-leads"; side_b_class = ""
    else:
        leaders_count += 1
        badge = f'<span class="rv-badge">{current[b_uid]} Leads · {b_wins}–{a_wins}</span>'
        pct = b_wins / len(games) * 100
        bar = f'<div class="rv-bar" style="background: linear-gradient(to left, #dc2626 0%, #dc2626 {pct:.1f}%, #1f2937 {pct:.1f}%, #1f2937 100%)"></div>'
        series_lbl = f'<div class="rv-series-lbl">{current[b_uid]} Leads</div>'
        wins_class_a = ""; wins_class_b = "hot"
        side_a_class = ""; side_b_class = "side-leads"

    # Reg/playoff splits per side
    a_reg_w = a_reg_l = a_po_w = a_po_l = 0
    a_pf_total = 0.0; b_pf_total = 0.0
    for g in games:
        if g["a"] == a_uid:
            a_score = g["sa"]; b_score = g["sb"]
        else:
            a_score = g["sb"]; b_score = g["sa"]
        a_pf_total += a_score; b_pf_total += b_score
        a_won = a_score > b_score
        if g["is_po"]:
            a_po_w += int(a_won); a_po_l += int(not a_won)
        else:
            a_reg_w += int(a_won); a_reg_l += int(not a_won)

    b_reg_w = len([g for g in games if not g["is_po"]]) - a_reg_w
    b_reg_l = a_reg_w
    b_po_w = len([g for g in games if g["is_po"]]) - a_po_w
    b_po_l = a_po_w

    a_ppg = a_pf_total / len(games)
    b_ppg = b_pf_total / len(games)

    # Last 5 games
    last5 = games[-5:]
    a_dots = []; b_dots = []
    for g in last5:
        if g["a"] == a_uid:
            a_score, b_score = g["sa"], g["sb"]
        else:
            a_score, b_score = g["sb"], g["sa"]
        a_won = a_score > b_score
        margin = abs(a_score - b_score)
        a_dot_cls = "w" if a_won else "l"
        b_dot_cls = "l" if a_won else "w"
        a_sign = "+" if a_won else "−"
        b_sign = "−" if a_won else "+"
        a_tip = f"{g['year']} W{g['week']} · {'W' if a_won else 'L'} · {a_sign}{margin:.1f}"
        b_tip = f"{g['year']} W{g['week']} · {'W' if not a_won else 'L'} · {b_sign}{margin:.1f}"
        a_dots.append(f'<span class="rv-dot {a_dot_cls}" data-tip="{a_tip}"></span>')
        b_dots.append(f'<span class="rv-dot {b_dot_cls}" data-tip="{b_tip}"></span>')

    # Key moment: most lopsided game in the series
    biggest = max(games, key=lambda g: abs(g["sa"] - g["sb"]))
    if biggest["a"] == a_uid:
        win_owner = current[a_uid] if biggest["sa"] > biggest["sb"] else current[b_uid]
        lose_owner = current[b_uid] if biggest["sa"] > biggest["sb"] else current[a_uid]
        win_score, lose_score = (biggest["sa"], biggest["sb"]) if biggest["sa"] > biggest["sb"] else (biggest["sb"], biggest["sa"])
    else:
        win_owner = current[b_uid] if biggest["sb"] > biggest["sa"] else current[a_uid]
        lose_owner = current[a_uid] if biggest["sb"] > biggest["sa"] else current[b_uid]
        win_score, lose_score = (biggest["sb"], biggest["sa"]) if biggest["sb"] > biggest["sa"] else (biggest["sa"], biggest["sb"])
    margin = win_score - lose_score
    key_text = f"{win_owner} drops {win_score:.2f} on {lose_owner} — a {margin:.1f}-point demolition that still gets brought up at the draft."
    key_date = f"{biggest['year']} · Week {biggest['week']}"

    last_game = games[-1]
    last_game_lbl = f"{last_game['year']} · W{last_game['week']}"

    first_year = games[0]["year"]
    label_top = f"Rivalry {['I','II','III','IV','V','VI'][i]} · {current[a_uid]} vs {current[b_uid]} · {len(games)} Meetings · Since {first_year}"

    cards_html.append(f"""
  <div class="rv-card">
    <div class="rv-card-head">
      <span class="rv-card-label">{label_top}</span>
      {badge}
    </div>
    <div class="rv-body">
      <div class="rv-side rv-side-a {side_a_class}">
        <div class="rv-wins {wins_class_a}">{a_wins}</div>
        <div class="rv-wins-lbl">Wins</div>
        <div class="rv-name">{current[a_uid]}</div>
        <div class="rv-ppg">{a_ppg:.1f} avg PPG</div>
        <div class="rv-rec">Reg {a_reg_w}–{a_reg_l} &nbsp;·&nbsp; Playoff {a_po_w}–{a_po_l}</div>
        <div class="rv-dots">
          {''.join(a_dots)}
        </div>
        <div class="rv-dots-label">Last {len(last5)}</div>
      </div>
      <div class="rv-center">
        <div class="rv-rivalry-name">{RIVALRY_NAMES[i]}</div>
        <div class="rv-vs">vs</div>
        <div class="rv-games">{len(games)} Meetings</div>
        <div class="rv-bar-wrap">
          {bar}
          <div class="rv-bar-nums"><span>{a_wins}</span><span>{b_wins}</span></div>
        </div>
        {series_lbl}
        <div class="rv-last-game">Last: <span>{last_game_lbl}</span></div>
      </div>
      <div class="rv-side rv-side-b {side_b_class}">
        <div class="rv-wins {wins_class_b}">{b_wins}</div>
        <div class="rv-wins-lbl">Wins</div>
        <div class="rv-name">{current[b_uid]}</div>
        <div class="rv-ppg">{b_ppg:.1f} avg PPG</div>
        <div class="rv-rec">Reg {b_reg_w}–{b_reg_l} &nbsp;·&nbsp; Playoff {b_po_w}–{b_po_l}</div>
        <div class="rv-dots">
          {''.join(b_dots)}
        </div>
        <div class="rv-dots-label">Last {len(last5)}</div>
      </div>
    </div>
    <div class="rv-key">
      <span class="rv-key-badge">Key Moment</span>
      <span class="rv-key-text">{key_text}</span>
      <span class="rv-key-date">{key_date}</span>
    </div>
    <div class="rv-tagline">
      <em>"{TAGLINES[i]}"</em>
    </div>
  </div>
""")

# Stitch the new <main> + updated stat cells into the existing rivalries/index.html
page = (ROOT / "rivalries" / "index.html").read_text()

# Replace stat cells
new_stats = f"""<div class="rv-header-stats">
    <div class="rv-stat-cell">
      <span class="rv-stat-val">{len(top_pairs)}</span>
      <span class="rv-stat-label">Active Feuds</span>
    </div>
    <div class="rv-stat-cell">
      <span class="rv-stat-val">{total_meetings}</span>
      <span class="rv-stat-label">Total Meetings</span>
    </div>
    <div class="rv-stat-cell">
      <span class="rv-stat-val">7</span>
      <span class="rv-stat-label">Seasons</span>
    </div>
    <div class="rv-stat-cell">
      <span class="rv-stat-val">{leaders_count}</span>
      <span class="rv-stat-label">Leaders</span>
    </div>
    <div class="rv-stat-cell">
      <span class="rv-stat-val">{deadlocked_count}</span>
      <span class="rv-stat-label">Deadlocked</span>
    </div>
  </div>"""

page = re.sub(r'<div class="rv-header-stats">.*?</div>\s*</header>',
              new_stats + "\n</header>", page, count=1, flags=re.DOTALL)

# Replace also the sub-line that says "Six feuds. Seven seasons. No mercy."
page = page.replace("Six feuds. Seven seasons. No mercy.", f"{['One','Two','Three','Four','Five','Six'][len(top_pairs)-1]} feuds. Seven seasons. No mercy.")

# Replace the entire <main class="rv-grid">...</main>
new_main = f'<main class="rv-grid">\n{"".join(cards_html)}\n</main>'
page = re.sub(r'<main class="rv-grid">.*?</main>',
              new_main, page, count=1, flags=re.DOTALL)

(ROOT / "rivalries" / "index.html").write_text(page)
print(f"Generated {len(top_pairs)} rivalries · {total_meetings} total meetings · {leaders_count} leaders · {deadlocked_count} deadlocked")
