# NFL.com Fantasy Football League Scraper

A Python tool to archive 7 years (or however many) of your NFL.com Fantasy
league history before NFL.com inevitably retires the platform or breaks the
pages you need. Built for league **7528632**, but easily retargetable.

## What you get

After running the pipeline, you'll have an `output/` folder with:

```
output/
├── teams.csv / teams.json                 # all team_ids across all seasons
├── standings_all_seasons.csv / .json       # final standings per season
├── matchups_all.csv / .json                # every matchup, every week, every season
├── my_player_weekly.csv / .json            # your starters/bench, every week, with fantasy pts
├── standings/<season>.csv|json             # per-season standings
├── matchups/<season>/week_NN.json          # per-week matchup files
├── my_rosters/<season>/week_NN.json        # per-week rosters for YOUR team
├── summary/
│   ├── my_career_summary.csv|json          # all-time totals
│   ├── my_weekly_matchups.csv              # filtered to just your games
│   ├── rivalry_head_to_head.csv|json       # your record vs each opponent
│   ├── season_finishes.csv|json            # where you finished each year
│   ├── top_10_blowouts.csv                 # biggest league blowouts ever
│   └── top_10_close_games.csv              # nail-biters
└── _raw_html/                              # raw HTML cached per page (for re-parsing)
```

## Prerequisites

- **Python 3.10+** (uses some modern type hints)
- An **active login** to NFL.com Fantasy with access to league 7528632

## Setup

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Edit config.py — at minimum, paste your COOKIE_STRING (see below)
```

## ⚠ Getting Your Cookies (the one tricky bit)

NFL.com requires you to be logged in to view your league's history. The scraper
authenticates by sending the same cookies your browser uses. Here's how:

### Chrome / Edge

1. Open Chrome and log into **https://fantasy.nfl.com**
2. Navigate to your league: `https://fantasy.nfl.com/league/7528632`
3. Press **F12** (or `Ctrl+Shift+I`) to open DevTools
4. Click the **Network** tab
5. Refresh the page (`F5`)
6. In the network list on the left, click the first request (usually `7528632` or `league/7528632`)
7. In the right panel, scroll the **Headers** section down to **Request Headers**
8. Find the line that starts with `cookie:` (or `Cookie:`)
9. Right-click the value and **Copy value** (just the value, not "cookie:" itself)
10. Paste it into `config.py` as the value of `COOKIE_STRING = "..."`

It will be a long string with many `name=value;` pairs — that's correct. Keep it on one line.

### Firefox

Same idea: DevTools → Network → click the page request → Headers → Request Headers → Cookie. Right-click the value → Copy.

### Cookie lifespan

Cookies expire. If the scripts start failing with errors like *"Cookies are invalid or expired"*, just re-log in to NFL.com and re-copy the cookie string into `config.py`.

### Security note

Treat `config.py` like a password — it lets anyone act as you on NFL.com until your session expires. Don't commit it to a public git repo. (There's a `.gitignore` included that excludes it.)

## Running the scraper

### The easy way — run everything

```bash
python run_all.py
```

This runs all 5 scripts in order. On the **first run** it will stop after step 03 and tell you to set `YOUR_TEAM_ID` in `config.py`. Find your team in the printed list (or in `output/teams.csv`), set the ID, then run `python run_all.py` again to finish.

### Or run scripts individually

```bash
python scripts/01_find_my_team.py        # discover team IDs → set YOUR_TEAM_ID
python scripts/02_scrape_standings.py    # per-season standings
python scripts/03_scrape_matchups.py     # every weekly matchup
python scripts/04_scrape_my_rosters.py   # your weekly lineups & player pts
python scripts/05_analyze.py             # roll up career stats & rivalries
```

Each script is independent — you can re-run just one if a parser breaks or you tweak something.

## Expected runtime

With the default `REQUEST_DELAY_SECONDS = 1.5` (polite rate limiting):

- **01 find_my_team:** ~10s (one page per season)
- **02 standings:** ~10s
- **03 matchups:** ~3 min (7 seasons × 17 weeks ≈ 120 requests)
- **04 my_rosters:** ~3 min
- **05 analyze:** instant (local computation)

Total: ~7 minutes. You can lower the delay, but be courteous.

## Troubleshooting

**"Got the NFL.com login page" / 401 / 403**
Your cookies expired. Re-log into NFL.com, copy fresh cookies into `config.py`.

**"No rows parsed"**
NFL.com may have changed the page structure for that season. Check `output/_raw_html/<season>/<page>.html` to inspect the actual HTML. The parser uses defensive selectors and should mostly survive, but very old seasons (pre-2018) sometimes use a different layout.

**Missing seasons**
Edit the `SEASONS` list in `config.py` to match what your league actually has. Setting an invalid year won't crash — it'll just print warnings.

**Player stat columns are cryptic (`stat_5`, `stat_14`, etc.)**
NFL.com uses numeric stat IDs whose mapping depends on your league's scoring settings. Look at one of the raw HTML files in `output/_raw_html/<season>/week_01_roster.html`, find the table headers, and you'll see what each `stat_N` corresponds to (passing yards, rushing TDs, etc.). I left them numeric on purpose so the scraper doesn't make wrong guesses.

## Migrating to Sleeper

Once you have all this archived, importing the *narrative* into Sleeper is mostly manual — Sleeper doesn't have an NFL.com importer. But your CSVs make it easy to:

- Recreate team names / owners in your new Sleeper league
- Post a "league history" pinned message
- Settle pre-existing rivalry trash talk with receipts

The Sleeper API itself is read-only, so there's no programmatic way to push historical matchups in. Sorry — that's a Sleeper limitation, not ours.

## License

Public domain. Hack on it freely.
