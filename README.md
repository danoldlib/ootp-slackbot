# OOTP StatsPlus Slack Bot

A Python automation script that interfaces with an OOTP StatsPlus league portal (e.g., XFBL) to provide high-level sim recaps, player awards, and team analytics directly to your league's Slack channel.

## Key Features

### ⚾ Play of the Week (Best Performances)
Automatically scans the StatsPlus `bestgames` pages to find the single highest Game Score for a pitcher and the highest WPA for a batter within the simulation timeframe.

### 🏆 Career Milestone Tracking
Celebrates league-wide achievements by detecting when players hit major career milestones (e.g., 2000 Hits, 300 Wins, 400 HRs, etc.). Aggressive filtering ensures only the most impressive achievements are highlighted.

### 📊 Team Analytics (Momentum & Luck)
Surfaces under-the-radar storylines using advanced sabermetrics:
- **Who's Hot / Who's Not**: Analyzes 7-Day ELO differentials to determine which team dominated the sim and which collapsed.
- **Luckiest / Unluckiest**: Compares Actual Record to Expected BaseRuns Record to find teams overperforming or getting robbed by the simulation engine.

### 🏁 Pennant Race Watch
Automatically detects tight division battles where the 1st and 2nd place teams are separated by **2.0 games or less**, hyping up the chase for the playoffs.

### 🧵 Slack Threading & Full Team Mapping
- **Threaded Recaps**: To prevent a "wall of text," the bot posts a single clean announcement and threads all rich data blocks underneath it.
- **Full Team Names**: Includes a built-in mapping of MLB abbreviations to full franchise names (e.g., "NYY" -> "New York Yankees") for a professional presentation.

## Setup Instructions

1. **Clone the Repository & Setup Environment**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows use: venv\Scripts\activate
   pip install -r requirements.txt
   ```

2. **Configure Environment Variables**
   Copy the example environment file and fill in your credentials:
   ```bash
   cp .env.example .env
   ```
   Open `.env` and configure:
   - `SLACK_BOT_TOKEN`: Your `xoxb-...` bot token.
   - `SLACK_CHANNEL_ID`: The channel ID for recaps.
   - `LEAGUE_URL`: Your StatsPlus league URL (e.g., `https://statsplus.net/xfbl`).
   - `DAYS_BACK`: Lookback window in days (Defaults to 7).

## Usage

Run the bot after a simulation finishes:
```bash
python bot.py
```

### Automation
This script is designed to be easily automated. You can schedule it via Windows Task Scheduler or as a cron job to run immediately after your league's scheduled simulation times.
