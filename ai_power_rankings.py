import os
import requests
import csv
import io
from google import genai

def fetch_statsplus_data(league_url, api_token):
    """Fetches standings and team data from StatsPlus API."""
    lgdata_url = f"{league_url.rstrip('/')}/api/lgdata/?token={api_token}"
    response = requests.get(lgdata_url, timeout=15)
    response.raise_for_status()
    data = response.json()
    
    # Find the primary league ID (usually 100) and state
    primary_league_id = None
    state = 2 # Default to regular season
    for league in data.get('leagues', []):
        if league.get('primary_league'):
            primary_league_id = league.get('id') or league.get('league_id')
            state = league.get('state', 2)
            break
            
    is_preseason = state in (0, 1, 4)
            
    # We want to map team_id to team name, but ONLY for the primary league
    teams_dict = {}
    for t in data.get('teams', []):
        t_league_id = t.get('league_id') or t.get('id') # API sometimes varies
        if primary_league_id and t_league_id != primary_league_id:
            continue
        teams_dict[t.get('team_id') or t.get('id')] = f"{t.get('name', '')} {t.get('nickname', '')}".strip()
        
    # Fetch player stats to identify top performers for each team
    bat_url = f"{league_url.rstrip('/')}/api/playerbatstatsv2/?token={api_token}"
    pitch_url = f"{league_url.rstrip('/')}/api/playerpitchstatsv2/?token={api_token}"
    players_url = f"{league_url.rstrip('/')}/api/players/?token={api_token}"
    
    def fetch_csv(url):
        try:
            resp = requests.get(url, timeout=15)
            if resp.status_code == 200:
                text = "\n".join(line for line in resp.text.splitlines() if line.strip())
                return list(csv.DictReader(io.StringIO(text)))
        except:
            pass
        return []

    player_names = {}
    for r in fetch_csv(players_url):
        pid = r.get('ID', '').strip()
        if pid:
            player_names[pid] = f"{r.get('First Name', '')} {r.get('Last Name', '')}".strip()

    def safe_float(d, key, default=0.0):
        try: return float(d.get(key, default) or default)
        except: return default

    bat_data = fetch_csv(bat_url)
    pitch_data = fetch_csv(pitch_url)
    
    # If we have very few stats (start of season), fetch last year's stats
    if len(bat_data) < 50 or is_preseason:
        date_resp = requests.get(f"{league_url.rstrip('/')}/api/date/?token={api_token}")
        try:
            current_year = int(date_resp.text.split('-')[0])
            # In preseason (0) or spring training (1), the year has rolled over.
            # In offseason (4), it might or might not have. We subtract 1 to be safe if no stats exist.
            y = current_year - 1 if state in (0, 1) else current_year
            
            bat_url = f"{league_url.rstrip('/')}/api/playerbatstatsv2/?token={api_token}&year={y}"
            pitch_url = f"{league_url.rstrip('/')}/api/playerpitchstatsv2/?token={api_token}&year={y}"
            
            fallback_bat = fetch_csv(bat_url)
            fallback_pitch = fetch_csv(pitch_url)
            if len(fallback_bat) > 50:
                bat_data = fallback_bat
                pitch_data = fallback_pitch
        except Exception:
            pass
    
    # Group top 3 players by team by WAR (split_id == 1 is overall stats)
    team_top_hitters = {}
    for r in bat_data:
        if r.get('split_id') == '1':
            tid = int(r.get('team_id', 0))
            if tid not in team_top_hitters: team_top_hitters[tid] = []
            team_top_hitters[tid].append({'name': player_names.get(r.get('player_id'), 'Unknown'), 'war': safe_float(r, 'war'), 'ops': safe_float(r, 'ops'), 'hr': r.get('hr', '0')})
            
    team_top_pitchers = {}
    for r in pitch_data:
        if r.get('split_id') == '1':
            tid = int(r.get('team_id', 0))
            if tid not in team_top_pitchers: team_top_pitchers[tid] = []
            team_top_pitchers[tid].append({'name': player_names.get(r.get('player_id'), 'Unknown'), 'war': safe_float(r, 'war'), 'era': r.get('era', '0.00')})

    for tid in team_top_hitters:
        team_top_hitters[tid] = sorted(team_top_hitters[tid], key=lambda x: x['war'], reverse=True)[:3]
    for tid in team_top_pitchers:
        team_top_pitchers[tid] = sorted(team_top_pitchers[tid], key=lambda x: x['war'], reverse=True)[:3]
    
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
        
        hitters_str = ", ".join([f"{h['name']} ({h['hr']} HR, {h['ops']} OPS)" for h in team_top_hitters.get(tid, [])])
        pitchers_str = ", ".join([f"{p['name']} ({p['era']} ERA, {p['war']} WAR)" for p in team_top_pitchers.get(tid, [])])
        
        standings.append({
            "team_name": team_name,
            "record": f"{wins}-{losses}",
            "win_pct": pct,
            "rs": rs,
            "ra": ra,
            "run_diff": rd,
            "division_rank": pos,
            "top_hitters": hitters_str,
            "top_pitchers": pitchers_str
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
    if is_preseason:
        prompt = "Here are the CURRENT rosters for our OOTP baseball league going into the new season. The stats shown for the top players are their stats from LAST SEASON to help you evaluate the current roster:\n\n"
    else:
        prompt = "Here is the current state of our OOTP baseball league based on StatsPlus data:\n\n"
        
    for team in sorted(standings, key=lambda x: x['win_pct'], reverse=True):
        prompt += f"Team: {team['team_name']} | Record: {team['record']} | Runs Scored: {team['rs']} | Runs Allowed: {team['ra']} | Run Differential: {team['run_diff']} | Top Hitters: {team['top_hitters']} | Top Pitchers: {team['top_pitchers']}\n"
        
    prompt += """
Based on this data, make an IN-DEPTH set of power rankings for the entire league. 
"""

    if is_preseason:
        prompt += """
CRITICAL INSTRUCTION: This is a PRESEASON evaluation for a fictional online OOTP baseball league (XFBL). The records are likely 0-0. You must ONLY base your power rankings on the strength of the "Top Hitters" and "Top Pitchers" listed for each team, which reflect their new rosters using last year's stats. DO NOT use real-world MLB history or players not listed here.

Rank every team, and give each one a 1-100 score for:
- Overall Team (based on the combined strength of their top players)
- Hitting (based on Top Hitters)
- Pitching/Defense (based on Top Pitchers)
- Cap Management (make a fun, educated guess)

Then give each team their biggest strength and biggest weakness based on their top players. Write about two to three sentences each.

Then based off your rankings, create a new list ranking each team from best to worst. Give them an overall summary predicting how their season will go, and classify them into if they are: tanking, growing, contending, falling off or are just stuck in purgatory.

Lastly, put together your own awards predictions for the AL and NL using the actual players listed in the data!

Format the output nicely in Slack Markdown (use asterisks for bold, etc). Do not use HTML tags. Keep the tone fun, engaging, and analytical!
"""
    else:
        prompt += """
CRITICAL INSTRUCTION: This is a fictional online OOTP baseball league (XFBL). DO NOT use real-world MLB history, real-world players (unless they happen to be listed in the data above), or historical context. You must ONLY base your analysis on the team records, run differentials, and the specific Top Hitters and Top Pitchers provided above. 

Rank every team, and give each one a 1-100 score for:
- Overall Team (based on Record and Run Diff)
- Hitting (based on Runs Scored and Top Hitters)
- Pitching/Defense (based on Runs Allowed and Top Pitchers)
- Cap Management (make a fun, educated guess based on if they are contending or tanking)

Then give each team their biggest strength and biggest weakness based on their stats and top players. Write about two to three sentences each.

Then based off your rankings, create a new list ranking each team from best to worst and go more depth on each team's season. Give them an overall summary and classify them into if they are: tanking, growing, contending, falling off or are just stuck in purgatory. 

Lastly, put together your own awards predictions for the AL and NL using the actual players listed in the data!

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
