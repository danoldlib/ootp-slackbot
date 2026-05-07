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

### 📰 Daily Digest Presentation
- **Consolidated Recaps**: To keep the channel clean, the bot posts a single comprehensive "Newspaper" style digest instead of multiple fragmented messages.
- **Full Team Names**: Includes a built-in mapping of MLB abbreviations to full franchise names (e.g., "NYY" -> "New York Yankees") for a professional presentation.

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
- `DAYS_BACK`: Lookback window in days (Defaults to 7).

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

## Usage
Once running, the bot sits idle in the background. It automatically triggers when it detects the message **"StatsPlus website has been updated"** in your Slack channel. It will wait 3 minutes for data to propagate and then post the Daily Digest.
