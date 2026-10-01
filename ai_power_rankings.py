import os
import requests
from google import genai

def fetch_statsplus_data(league_url, api_token):
    """Fetches standings and team data from StatsPlus API."""
    lgdata_url = f"{league_url.rstrip('/')}/api/lgdata/?token={api_token}"
    response = requests.get(lgdata_url, timeout=15)
    response.raise_for_status()
    data = response.json()
    
    # Find the primary league ID (usually 100)
    primary_league_id = None
    for league in data.get('leagues', []):
        if league.get('primary_league'):
            primary_league_id = league.get('id') or league.get('league_id')
            break
            
    # We want to map team_id to team name, but ONLY for the primary league
    teams_dict = {}
    for t in data.get('teams', []):
        t_league_id = t.get('league_id') or t.get('id') # API sometimes varies
        if primary_league_id and t_league_id != primary_league_id:
            continue
        teams_dict[t.get('team_id') or t.get('id')] = f"{t.get('name', '')} {t.get('nickname', '')}".strip()
    
    # Get standings data
    standings = []
    for st in data.get('standings', []):
        tid = st.get('team_id')
        if tid not in teams_dict:
            continue # Skip minor league teams
            
        team_name = teams_dict[tid]
        wins = st.get('w', 0)
        losses = st.get('l', 0)
        rs = st.get('rs', 0) # Runs scored
        ra = st.get('ra', 0) # Runs allowed
        rd = rs - ra
        pct = st.get('pct', 0)
        pos = st.get('pos', 0)
        standings.append({
            "team_name": team_name,
            "record": f"{wins}-{losses}",
            "win_pct": pct,
            "rs": rs,
            "ra": ra,
            "run_diff": rd,
            "division_rank": pos
        })
        
    return standings

def generate_power_rankings(league_url="https://statsplus.net/xfbl"):
    """Fetches data and asks Gemini to generate power rankings."""
    api_token = os.getenv("STATSPLUS_API_TOKEN")
    gemini_key = os.getenv("GEMINI_API_KEY")
    
    if not api_token:
        return "⚠️ Error: `STATSPLUS_API_TOKEN` not set in `.env`."
    if not gemini_key:
        return "⚠️ Error: `GEMINI_API_KEY` not set in `.env`."
        
    try:
        standings = fetch_statsplus_data(league_url, api_token)
    except Exception as e:
        return f"⚠️ Error fetching data from StatsPlus API: {e}"
        
    # Build text prompt for the AI
    prompt = "Here is the current state of our OOTP baseball league based on StatsPlus data:\n\n"
    for team in sorted(standings, key=lambda x: x['win_pct'], reverse=True):
        prompt += f"Team: {team['team_name']} | Record: {team['record']} | Runs Scored: {team['rs']} | Runs Allowed: {team['ra']} | Run Differential: {team['run_diff']} | Division Rank: {team['division_rank']}\n"
        
    prompt += """
Based on this data, make an IN-DEPTH set of power rankings for the entire league.
Rank every team, and give each one a 1-100 score for:
- Overall Team
- Hitting
- Defense
- Starting Pitching
- Bullpen
- Cap Management

Then give each team their biggest strength and biggest weakness. Write about two to three sentences each.

Then based off your rankings, create a new list ranking each team from best to worst and go more depth on each team's season. Give them an overall summary and classify them into if they are: tanking, growing, contending, falling off or are just stuck in purgatory. Then expand further on those strengths and weaknesses you listed before.

Lastly, put together your own awards predictions for the AL and NL!

Format the output nicely in Slack Markdown (use asterisks for bold, etc). Do not use HTML tags. Keep the tone fun, engaging, and analytical!
"""

    try:
        client = genai.Client(api_key=gemini_key)
        response = client.models.generate_content(
            model='gemini-3.8-flash',
            contents=prompt,
        )
        return response.text
    except Exception as e:
        return f"⚠️ Error generating power rankings with Gemini: {e}"
