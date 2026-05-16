"""
Fill pickems with demo data:
  · projected_points on every team (so future UI can show a projection)
  · records map on every week (pulled from powerrank-style sim)
  · PIN shortened to 3 digits to match the login form's pattern
  · fake user submissions injected (see pickems.js initRecords override)
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
P = ROOT / "pickems"

# ── teams.json — add projected_points (rough fantasy-pts feel) ────
PROJ = {
  "marcus":  138.5, "jordan": 142.7, "devin":  139.8, "cole":   136.1,
  "noah":    132.4, "owen":   119.8, "tyler":  124.6, "ethan":  122.1,
  "brandon": 117.3, "trevor": 109.5, "adam":   121.7, "ryan":   113.2,
}
teams = json.load(open(P / "teams.json"))
for t in teams["teams"]:
    t["projected_points"] = PROJ.get(t["id"], 120.0)
json.dump(teams, open(P / "teams.json", "w"), indent=2)

# ── users.json — switch PIN to 3 digits to match the form pattern ──
users = json.load(open(P / "users.json"))
for a in users["accounts"]:
    a["pin"] = "123"
json.dump(users, open(P / "users.json", "w"), indent=2)

# ── week1.json — opening week, all teams 0-0 ──────────────────────
w1 = json.load(open(P / "weeks" / "week1.json"))
w1["records"] = {t["id"]: "0-0" for t in teams["teams"]}
json.dump(w1, open(P / "weeks" / "week1.json", "w"), indent=2)

# ── week2.json — after week 1 results (winners from w1 → 1-0, losers → 0-1) ──
w2 = json.load(open(P / "weeks" / "week2.json"))
w1_winners = set(w1["winners"].values())
losers = set()
for m in w1["matchups"]:
    if w1["winners"].get(m["id"]) == m["home"]:
        losers.add(m["away"])
    elif w1["winners"].get(m["id"]) == m["away"]:
        losers.add(m["home"])
w2["records"] = {}
for t in teams["teams"]:
    if t["id"] in w1_winners: w2["records"][t["id"]] = "1-0"
    elif t["id"] in losers:   w2["records"][t["id"]] = "0-1"
    else:                     w2["records"][t["id"]] = "0-0"
json.dump(w2, open(P / "weeks" / "week2.json", "w"), indent=2)

print("Pickems demo data filled:")
print(f"  · projected_points added to {len(teams['teams'])} teams")
print(f"  · PINs reset to '123' for {len(users['accounts'])} users")
print(f"  · records on week1.json (all 0-0)")
print(f"  · records on week2.json (winners 1-0, losers 0-1)")
