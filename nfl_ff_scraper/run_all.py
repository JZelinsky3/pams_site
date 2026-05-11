"""
Run the full pipeline end-to-end.

Equivalent to running each script in scripts/ in order:
  01 → 02 → 03 → 04 → 05

NOTE: 04 (rosters) and 05 (analyze) require YOUR_TEAM_ID to be set in config.py.
If it's still None, this runner will skip them and tell you to set it first.
"""

import subprocess
import sys
from pathlib import Path

import config

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE / "scripts"


def run(name: str) -> int:
    print("\n" + "#" * 70)
    print(f"#  {name}")
    print("#" * 70)
    return subprocess.call([sys.executable, str(SCRIPTS / name)])


def main():
    if run("01_find_my_team.py") != 0:
        print("\nStep 01 failed. Fix config.py (cookies?) and try again.")
        return 1
    if run("02_scrape_standings.py") != 0:
        return 1
    if run("03_scrape_matchups.py") != 0:
        return 1

    if not config.YOUR_TEAM_ID:
        print("\n" + "!" * 70)
        print("! YOUR_TEAM_ID is still None in config.py.")
        print("! Look at output/teams.csv, find your row, and set it.")
        print("! Then re-run: python run_all.py  (or just 04 + 05)")
        print("!" * 70)
        return 0

    if run("04_scrape_my_rosters.py") != 0:
        return 1
    if run("05_analyze.py") != 0:
        return 1

    print("\n✓ Done. Check the output/ directory.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
