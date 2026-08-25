# OOTP StatsPlus Slack Bot

A Python automation script that interfaces with an OOTP StatsPlus league portal (e.g., XFBL) to deliver rich sim recaps, player awards, team analytics, statistical oddities, and season-aware updates directly to your league's Slack channel.

The bot listens for the League File update message, waits 3 minutes for data to propagate, then posts a fully automated "Daily Digest" to your channel.

---

## Features

### ⚾ Play of the Sim (Best Performances)
Scans the StatsPlus `bestgames` pages for the highest Game Score pitcher and highest WPA batter within the simulation window. Each entry includes a narrative blurb, full stat line, and links to the box score and player profile.

### 🗞️ Sim Headlines & Career Milestones
Parses the StatsPlus recap page for notable events:
- **Career Milestones**: Flags when players reach major thresholds (2,000 Hits, 300 Wins, 400 HRs, 1,000 Ks, 200 Saves, etc.)
- **Rare Feats**: No-hitters, perfect games, cycles, walk-off hits, and MLB debuts

### 📊 Sim Analytics & Trends (Rotating Modes)
Rotates through three analytical modes each sim to keep insights fresh:
- **Standard**: Hot/cold teams by ELO differential + luckiest/unluckiest by BaseRuns
- **Rankings Shakeup**: Flags teams that jumped or dropped significantly in the power rankings
- **Luck Focus**: Deep-dive into teams most over/underperforming their expected record

Includes callouts for:
- **Winning/Losing Streaks**: Teams on 3+ sim ELO streaks
- **Season-High Records**: First time a player reaches a new season-high in HR, pitcher Ks, or best ERA

### 📊 Weekly Power Rankings
Pulls the OOTP-generated team power rankings and surfaces:
- Top 5 and bottom 5 teams with their ranking points
- **Big movers**: Any team with a `++` (surging) or `--` (tumbling) trend highlighted separately

### 🎯 Milestone Countdowns
Identifies players within 30 of a major career milestone (e.g., 498 career HR → 2 away from 500) and teases the approaching moment.
### 📉 By the Numbers: League Oddities
Mines the StatsPlus CSV API and randomly surfaces 5 of 20+ rotating statistical facts per sim. The rotation avoids repeating the same category or winner consecutively.

**Batting**
- 🎳 K-Rate King — highest strikeout rate (min 100 PA)
- 🚶 Walk Machine — highest walk rate (min 100 PA)
- 💀 Double Play Machine — most GIDPs
- 💣 HR Freak — best home run rate (min 5 HR / 50 AB)
- 🏡 Home Run King — raw HR leader
- 🔫 Speed Demon — stolen base leader with success rate
- 🏆 Position Player WAR Leader
- 📉 Clutch Kryptonite — worst WPA (min 100 PA)
- 🧱 Human Out — lowest batting average (min 100 PA)
- 🎯 Contact Machine — lowest strikeout rate (min 100 PA)
- 👻 Ghost Runner — most triples
- 🍀 BABIP Lottery Winner — highest BABIP (min 100 PA)
- 🤡 BABIP Victim — lowest BABIP (min 100 PA)
- 🤝 RBI Dependent — most RBI with ≤3 HR
- 🏃 Caught Red-Handed — most caught stealing
- 😈 Statistically Cursed — top-5 in both Ks AND GIDPs simultaneously

**Pitching**
- 🔥 Swing-and-Miss SP — highest K/BF rate among starters
- 🎖️ Pitcher WAR Leader
- 😬 Control Issues — most walks per 9 innings
- 🧊 K/BB Ratio King — best strikeout-to-walk ratio
- 🛢️ Gas Can — highest ERA among starters (min 20 IP)
- 🏔️ Worm Killer — best GO/AO ratio
- 🎭 Mr. Reliable — most quality starts
- 😤 Home Run Derby Pitcher — most HR allowed
- 📦 Iron Man — most innings pitched
- 🎪 Bullpen Burnout — most relief appearances
- 🔒 Closer of the Year — best save conversion rate (min 3 opportunities)
- 💥 Blown Save King — most blown saves

### 🔥 Weird Sim: Notable Moments
Scans recent box scores for memorable events:
- **Blowouts**: Games decided by 10+ runs
- **Run Fests**: Combined 20+ runs scored
- **Multi-HR Games**: Any player with 3+ home runs in a single game

### 🤝 Trade Tracker
Evaluates regular season trades by tracking players moved and reporting on their post-trade WAR and performance.

### 🚑 Devastating Injury Report
Alerts the channel when a star player goes down for 3+ weeks, identifying massive blows to contenders.

### 🧹 Sweep Watch & 🚨 Walk-off Magic
Highlights series sweeps and dramatic walk-off wins scraped from the league news recap.

### 👶 Prospect Watch
Flags when a highly-touted prospect makes their major league debut.

### 📉 Rough Outings (Golden Sombrero)
The inverse of the Play of the Sim — hilariously flags truly terrible performances, such as 5 strikeouts in a game or a starter getting shelled early.

### 🏁 Pennant Race Watch
Flags tight division races where 1st and 2nd place are separated by **2.0 games or less**.

---

## Season Phase Detection

The bot automatically detects the current phase of the OOTP season and adjusts its output accordingly.

| Phase | Detection | What gets posted |
|---|---|---|
| **Regular Season** | Games found in best performances | Full digest (all sections above) |
| **Postseason** | Playoff keywords found in recap or scores report | 🏆 Playoff digest: performances + headlines + notable games only |
| **Offseason** | No game performances found this sim | 💤 Rich offseason digest: major awards, trades, major FA signings, HOF/retirements, owner decisions/finances, and condensed roster moves |

### Offseason Digest
During offseason sims (when no games are played), the bot scrapes both the OOTP news and transactions reports to build a categorized offseason summary:
- **🏆 Major League Awards**: Cy Young, MVP, Rookie of the Year, Reliever of the Year, Gold Gloves, Silver Sluggers, etc.
- **🤝 Offseason Trades**: Roster trades between teams.
- **⭐ Major Free Agent Signings**: Highlights signings with contracts of $10M+ total value or average annual salary of $4M+.
- **🎓 Retirements & Hall of Fame**: Inductions and players hangin' up the cleats.
- **💰 Owner Decisions & Financials**: Ownership cash profit withdrawals or cash injections.
- **📋 Roster Moves & Minor Signings**: Bulleted summary of minor league signings, waiver claims, releases, and DL moves (capped at 15 to avoid text spam).

---

## Persistent State (`state.json`)

The bot maintains a `state.json` file (auto-created on first run) to persist cross-sim data:
- ELO history per team (for streak detection)
- Season-high records per stat
- Last shown oddity categories (for rotation)
- Last oddity winners (to avoid back-to-back repeats)

> During offseason sims, rotation state is **not** updated — your oddity rotation picks up exactly where it left off when the regular season resumes.

---

## Setup Instructions

### 1. Configure Slack App (Socket Mode)
This bot uses **Slack Socket Mode** to listen for sim completion messages in real-time.
1. Enable **Socket Mode** in your Slack App settings and generate an `xapp` App-Level Token with `connections:write` scope.
2. Enable **Event Subscriptions** and subscribe to the `message.channels` bot event.
3. Grant the bot the `chat:write` and `channels:history` OAuth scopes.
4. Invite your bot to the channel where StatsPlus posts its updates.

### 2. Configure Environment Variables
Copy the example environment file and fill in your credentials:
```bash
cp .env.example .env
```
Open `.env` and configure:
- `SLACK_BOT_TOKEN`: Your `xoxb-...` bot token.
- `SLACK_APP_TOKEN`: Your `xapp-...` app-level token (from Socket Mode setup).
- `SLACK_CHANNEL_ID`: The channel ID where the digest will be posted.
- `LEAGUE_URL`: Your StatsPlus league URL (e.g., `https://statsplus.net/xfbl`).
- `DAYS_BACK`: Lookback window in days (defaults to `7`).

---

## Deployment

### Using Docker (Recommended)
The easiest way to run the bot is using Docker Compose:
```bash
docker-compose up -d --build
```
This runs the bot in the background and automatically restarts it if it crashes or the system reboots.

### Manual Setup
1. **Setup Environment**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```
2. **Run the Bot**
   ```bash
   python bot.py
   ```

---

## Usage

Once running, the bot sits idle in the background and triggers automatically when it detects the message **"League File has been updated"** from the "File Watcher" bot in your Slack channel. It waits 3 minutes for data to propagate, then posts the full digest.

### Running a Manual Digest

If a sim finished but the bot didn't trigger, or you want to run it on demand:

**Without Docker:**
```bash
python bot.py --manual
```

**With Docker — option 1: run a one-off container**
```bash
docker-compose run ootp-slackbot python bot.py --manual
```

**With Docker — option 2: exec into the running container**
```bash
# Find the container name
docker ps

# Exec in and run manually
docker exec -it ootp-slackbot python bot.py --manual
```
> If your container is named differently, replace `ootp-slackbot` with the name shown in `docker ps`.

### Viewing Logs

```bash
# Follow live logs from the running container
docker-compose logs -f

# View recent logs only
docker-compose logs --tail=100
```

---

## 💡 Tips & Troubleshooting

- **Channel Membership**: The bot **must** be a member of the channel where StatsPlus posts. In Slack, go to the channel and type `/invite @YourBotName`.
- **Duplicate Posts**: The bot acknowledges Slack events instantly and processes the digest in a background thread, preventing Slack from retrying and causing double posts. It also ignores `message_changed` events and non-StatsPlus bot messages.
- **Offseason Behavior**: When no games are played (offseason sims), the bot posts a short update with real transactions instead of a full digest. Rotation state (oddities) is preserved and picks up next regular season.
- **ERA in Oddities**: ERA is calculated live from earned runs and innings pitched (`(ER / IP) * 9`) since the StatsPlus API does not include a pre-computed ERA field.
- **State Reset**: To reset the oddity rotation, delete `state.json` in the bot directory. It will be recreated fresh on the next run.
