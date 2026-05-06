# OOTP StatsPlus Slack Bot

A Python automation script that interfaces with an OOTP StatsPlus league portal (e.g., XFBL) to fetch the best performances and major career milestones from the recent simulation timeframe, formatting them into an elegant Block Kit payload for a dedicated Slack channel.

## Features
- ⚾ **Best Performances**: Automatically scrapes the StatsPlus `bestgames` pages to find the single highest Game Score for a pitcher and the highest WPA for a batter within the defined timeframe.
- 🏆 **Milestone Tracking**: Scrapes the StatsPlus `recap` page to detect and alert the league when players hit major career milestones (e.g., 2000 Hits, 400 HRs, 300 Wins).
- 💬 **Slack Block Kit Integration**: Packages the alerts into highly readable, professional UI blocks complete with direct links to the box score and player profiles.
- ⚡ **No-API Web Scraping**: Relies entirely on `BeautifulSoup4` to quickly parse public HTML tables rather than relying on heavy box-score downloads or undocumented JSON APIs.

## Requirements
- Python 3.8+
- A Slack App with `chat:write` permissions added to your workspace.

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
   - `SLACK_BOT_TOKEN`: The `xoxb-...` token for your Slack bot.
   - `SLACK_CHANNEL_ID`: The specific channel ID (e.g., `C01ABCD234`) where alerts should go.
   - `LEAGUE_URL`: The base URL of your StatsPlus league (e.g., `https://statsplus.net/xfbl`).
   - `DAYS_BACK`: The lookback window (in days) to search for performances. Defaults to 7.

## Usage

Simply run the bot script after a simulation finishes:
```bash
python bot.py
```

### Automation
For hands-free operation, you can schedule the execution using Windows Task Scheduler, a cron job on a Linux server, or trigger it via an external ETL pipeline whenever a new OOTP database export completes.
