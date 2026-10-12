# Migrate StatsPlus Scraping to API

The StatsPlus developer requested that we stop scraping HTML pages from the site, as this causes unnecessary load and rate limits (429 / 403), and the information is available via API.

## Implemented API Endpoints

1. **Date & Season Phase**:
   - `/api/date/`: Accurately resolves the in-game calendar date (e.g. `2009-04-13`).
   - `/api/lgdata/`: Returns JSON with league state (`0`=Preseason, `1`=Spring Training, `2`=Regular Season, `3`=Playoffs, `4`=Offseason), full standings, games back, magic numbers, and team alignment.

2. **Best Performances & Notable Games**:
   - `/api/atbats/`: Ingests every plate appearance in the sim window.
   - **Best Pitcher**: Computes Bill James Game Score per pitching appearance (`50 + outs + bonus + K - 2*H - 4*R - 2*BB`).
   - **Best Batter**: Computes batting game score based on Total Bases, RBIs, Runs, and Walks.
   - **Notable Games**: Computes double-digit blowouts, 20+ run slugfests, and 3+ HR single-game achievements without scraping HTML.

3. **Season Stats & Oddities**:
   - `/api/playerbatstatsv2/`, `/api/playerpitchstatsv2/`, `/api/players/`, and `/api/teams/` for statistical oddities and rotating analytics.

4. **Game History**:
   - `/api/gamehistory/`: Available for game decisions, scores, and complete games. Note: StatsPlus enforces a **5-minute rate limit cooldown** per team on this endpoint.

