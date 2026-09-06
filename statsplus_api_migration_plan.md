# Migrate StatsPlus Scraping to API

The StatsPlus developer has requested that we stop scraping HTML pages from the site, as this causes unnecessary load and the information is available via API. This plan outlines how we will transition `scraper.py` and `bot.py` to use the official StatsPlus API.

## Requirements

The StatsPlus API requires a token for programmatic access (`?token=XXXX`). We will need to:
1. Provide the league's API token (found on the Preferences page of the StatsPlus website).
2. Add it to the `.env` file as `STATSPLUS_API_TOKEN`.

We also need to verify exactly which endpoints are supported by the StatsPlus API to fully replace our current HTML scraping. If certain endpoints (like playoff odds, ELO, or specific HTML reports) do not have a 1:1 API equivalent yet, we will need to disable those features temporarily and request them from the StatsPlus developer, as per their message.

## Proposed Changes

We will refactor `scraper.py` to strip out all `BeautifulSoup` HTML parsing. We will replace these with `requests.get` calls to the `/api/...` endpoints that return JSON or CSV, appending the API token to authenticate the requests.

### `scraper.py`
- **Token Integration**: Add support for reading `STATSPLUS_API_TOKEN` from environment variables and passing it in the query string or headers for all API requests.
- **`get_best_performances`**: Replace HTML scraping of `/bestgames/bat/` and `/bestgames/pitch/` with calls to the appropriate API endpoints (e.g., box scores or daily game logs).
- **`get_headlines_and_milestones`**: Replace `/recap/` scraping with API recap data (if available), or disable this feature and request it from the developer.
- **`get_team_momentum` & `get_team_luck`**: Replace `/elo/current/` and `/baseruns/` scraping with their respective API equivalents.
- **`get_close_division_races` & `get_playoff_odds`**: Replace `/standings/` and `/playoffodds/` with API data.
- **`get_power_rankings`**: Replace HTML parsing of `league_100_home.html` with an API call for rankings.
- **`get_offseason_transactions` & `get_offseason_data`**: Replace scraping of the OOTP HTML reports with API calls for transactions and news (or use the OOTP CSV data dumps directly if StatsPlus exposes them via API).
- **`get_season_phase`**: Refactor the season phase detection to use the `/api/date` or `/api/league` endpoint instead of parsing the homepage and scores report HTML.

### `.env.example`
- Add `STATSPLUS_API_TOKEN=` to the example environment file so users know they need to configure it.

## Open Questions for Implementation
1. Does the StatsPlus Wiki or API documentation for the league list endpoints for: Box Scores/Game Logs (for `best_performances`), ELO, BaseRuns, Standings, Playoff Odds, Power Rankings, and Transactions? 
2. If any of these are missing from the API, how should they be handled? (e.g., skip those features in the Slack digest until the API supports them?)
