# OOTP StatsPlus Slack Bot

A Python automation script that interfaces with an OOTP StatsPlus league portal (e.g., XFBL) to provide high-level sim recaps, player awards, team analytics, and statistical oddities directly to your league's Slack channel.

## Key Features

### ⚾ Play of the Week (Best Performances)
Automatically scans the StatsPlus `bestgames` pages to find the single highest Game Score for a pitcher and the highest WPA for a batter within the simulation timeframe. Each performance includes a generated narrative blurb, stat line, and links to the box score and player profile.

### 🏆 Career Milestone Tracking
Celebrates league-wide achievements by detecting when players hit major career milestones (e.g., 2,000 Hits, 300 Wins, 400 HRs, 1,000 Strikeouts, etc.). Aggressive filtering ensures only the most impressive achievements are highlighted.

### 📊 Team Analytics (Momentum & Luck)
Surfaces under-the-radar storylines using advanced sabermetrics:
- **Who's Hot / Who's Not**: Analyzes 7-Day ELO differentials to determine which team dominated the sim and which collapsed.
- **Luckiest / Unluckiest**: Compares Actual Record to Expected BaseRuns Record to find teams overperforming or getting robbed by the simulation engine.

### 📊 By the Numbers: League Oddities
Mines the StatsPlus CSV API each sim and randomly surfaces 5 of 17 rotating statistical facts and oddities to keep posts feeling fresh. The full pool includes:

**Batting**
- 🎳 K-Rate King — highest strikeout rate (min 100 PA)
- 🚶 Walk Machine — highest walk rate (min 100 PA)
- 💀 Double Play Machine — most GIDPs
- 💣 HR Freak — best home run rate (min 5 HR / 50 AB)
- 🔫 Speed Demon — stolen base leader with success rate
- 🏆 Position Player WAR Leader
- 📉 Clutch Kryptonite — worst WPA (min 100 PA)
- 🧱 Human Out — lowest batting average (min 100 PA)
- 👻 Ghost Runner — most triples
- 🍀 BABIP Lottery Winner — highest BABIP (min 100 PA)
- 🤡 BABIP Victim — lowest BABIP (min 100 PA)
- 🤝 RBI Dependent — most RBI with 3 or fewer HR
- 🏃 Caught Red-Handed — most caught stealing
- 😈 Statistically Cursed — top-5 in both Ks AND GIDPs simultaneously

**Pitching**
- 🔥 Swing-and-Miss SP — highest K/BF rate among starters
- 🎖️ Pitcher WAR Leader
- 😬 Control Issues — most walks per 9 innings
- 🛢️ Gas Can — highest ERA among starters (min 20 IP)
- 🏔️ Worm Killer — best GO/AO ratio among starters
- 🎭 Mr. Reliable — most quality starts
- 😤 Home Run Derby Pitcher — most HR allowed by a starter
- 📦 Iron Man — most innings pitched
- 🔒 Closer of the Year — best save conversion rate (min 3 opportunities)
- 💥 Blown Save King — most blown saves

### 🗞️ Weird Sim: Notable Moments
Scans recent box scores to highlight unusual or memorable games:
- **Blowouts**: Games decided by 10+ runs
- **Run Fests**: Games where teams combined for 20+ runs
- **Multi-HR Games**: Any player who went deep 3 or more times in a single game

### 🏁 Pennant Race Watch
Automatically detects tight division battles where the 1st and 2nd place teams are separated by **2.0 games or less**, hyping up the chase for the playoffs.

### 📰 Daily Digest Presentation
- **Consolidated Recaps**: Posts a single comprehensive "Newspaper" style digest per sim to keep the channel clean.
- **Threaded posting**: The bot acknowledges Slack events instantly (preventing duplicate posts from Slack retries) and processes the digest in a background thread.
- **Full Team Names**: Built-in mapping of MLB abbreviations to full franchise names (e.g., `NYY` → `New York Yankees`).

---

## Setup Instructions

### 1. Configure Slack App (Socket Mode)
This bot uses **Slack Socket Mode** to listen for sim completion messages in real-time.
1. Enable **Socket Mode** in your Slack App settings and generate an `xapp` App-Level Token with `connections:write` scope.
2. Enable **Event Subscriptions**, turn on events, and subscribe to the `message.channels` bot event.
3. Invite your bot to the channel where StatsPlus posts its updates.

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
- `DAYS_BACK`: Lookback window in days (Defaults to `7`).

---

## Deployment

### Using Docker (Recommended)
The easiest way to run the bot is using Docker Compose:
```bash
docker-compose up -d --build
```
This will run the bot in the background and automatically restart it if it crashes or the system reboots.

### Manual Setup
1. **Setup Environment**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows use: venv\Scripts\activate
   pip install -r requirements.txt
   ```
2. **Run the Bot**
   ```bash
   python bot.py
   ```

---

## Usage
Once running, the bot sits idle in the background. It automatically triggers when it detects the message **"StatsPlus website has been updated"** in your Slack channel. It waits 3 minutes for data to propagate (in a background thread), then posts the full Daily Digest.

### 💡 Tips & Troubleshooting
- **Channel Membership**: The bot **must** be a member of the channel where StatsPlus announcements are posted. In Slack, go to that channel and type `/invite @YourBotName`.
- **Duplicate Posts**: The bot processes the digest in a background thread so Slack's event is acknowledged immediately, preventing Slack from retrying and causing duplicate posts.
- **Manual Run**: If a sim finished but the bot didn't trigger (or you just want to run it on demand), force a manual update:
  ```bash
  python bot.py --manual
  ```
  If using Docker, run the manual command inside the container:
  ```bash
  docker-compose run ootp-slackbot python bot.py --manual
  ```
