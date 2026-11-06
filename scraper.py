import requests
from bs4 import BeautifulSoup
import re
import os
from datetime import datetime, timedelta
from dotenv import load_dotenv, set_key

load_dotenv(override=True)


def _get_api_token():
    """
    Returns the current StatsPlus API token stripped of any whitespace or surrounding quotes.
    """
    return os.environ.get("STATSPLUS_API_TOKEN", "").strip().strip("'").strip('"')


def _update_env_token_in_place(env_path, new_token):
    """
    Updates STATSPLUS_API_TOKEN in .env in-place without os.replace() so Docker
    single-file bind mounts (./.env:/app/.env) never fail with EBUSY or add quotes.
    """
    try:
        if os.path.exists(env_path):
            with open(env_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
            found = False
            new_lines = []
            for line in lines:
                if re.match(r"^\s*STATSPLUS_API_TOKEN\s*=", line):
                    new_lines.append(f"STATSPLUS_API_TOKEN={new_token}\n")
                    found = True
                else:
                    new_lines.append(line)
            if not found:
                if new_lines and not new_lines[-1].endswith("\n"):
                    new_lines[-1] += "\n"
                new_lines.append(f"STATSPLUS_API_TOKEN={new_token}\n")
            with open(env_path, "w", encoding="utf-8") as f:
                f.writelines(new_lines)
        else:
            set_key(env_path, "STATSPLUS_API_TOKEN", new_token, quote_mode="never")
    except Exception as e:
        print(f"Warning: Could not update .env file in-place: {e}")


def parse_ootp_date(date_str):
    """
    Attempts to parse a date string from an OOTP box score.
    Format is usually like 'April 23, 2007' or 'April 23rd, 2007'.
    """
    from dateutil import parser
    try:
        # Strip ordinal suffixes (st, nd, rd, th)
        date_str = re.sub(r'(\d+)(st|nd|rd|th)', r'\1', date_str)
        dt = parser.parse(date_str)
        return dt
    except Exception as e:
        print(f"Could not parse date: {date_str} - {e}")
        return None

def get_statsplus_session():
    """
    Returns a requests.Session configured with browser headers and initialized
    with cookies from the StatsPlus homepage to avoid 403 Forbidden responses.
    """
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    })
    try:
        session.get("https://statsplus.net/xfbl/", timeout=10)
    except Exception:
        pass
    return session

def refresh_statsplus_api_token(league_url="https://statsplus.net/xfbl"):
    """
    Checks and refreshes the StatsPlus API token via the /api/tokenrefresh/ endpoint.
    If a new token is issued, updates the local .env file and os.environ.
    Returns a dict with:
      - 'status': 'valid' | 'refreshed' | 'expired' | 'error'
      - 'message': human-readable description
      - 'token': active token string
    """
    # Always reload .env with override=True so manual runs (`docker exec ...`) or external
    # .env edits override stale container creation-time environment variables.
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    load_dotenv(dotenv_path=env_path, override=True)
    token = _get_api_token()
    if not token:
        return {
            "status": "error",
            "message": "STATSPLUS_API_TOKEN is not set in environment.",
            "token": ""
        }

    url = f"{league_url.rstrip('/')}/api/tokenrefresh/"
    headers = {"Authorization": f"Bearer {token}"}
    try:
        resp = requests.post(url, headers=headers, timeout=20)
        if resp.status_code == 200:
            data = resp.json()
            new_token = (data.get("token") or "").strip().strip("'").strip('"')
            expires = data.get("expires", "")
            rotated = data.get("rotated", False)

            if rotated and new_token and new_token != token:
                # Update os.environ
                os.environ["STATSPLUS_API_TOKEN"] = new_token
                # Update .env file in-place (safe for Docker single-file bind mounts)
                _update_env_token_in_place(env_path, new_token)
                print(f"StatsPlus API token automatically rotated! Expires: {expires}")
                return {
                    "status": "refreshed",
                    "message": f"Token automatically rotated. New expiration: {expires}",
                    "token": new_token
                }
            return {
                "status": "valid",
                "message": f"Token is active and healthy (expires: {expires}).",
                "token": token
            }
        elif resp.status_code in (400, 401):
            return {
                "status": "expired",
                "message": resp.text.strip() or "API token has expired.",
                "token": token
            }
        else:
            return {
                "status": "error",
                "message": f"Unexpected status {resp.status_code}: {resp.text[:100]}",
                "token": token
            }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Network error during token refresh: {e}",
            "token": token
        }

# Per-sim in-memory API cache keyed by (league_url, game_date_str)
_API_CACHE = {
    "date_key": None,
    "lgdata": None,
    "players": None,
    "players_active": None,
    "teams_csv": None,
    "bat_season": None,
    "pitch_season": None,
    "bat_career": None,
    "pitch_career": None,
    "atbats": {},
    "gamehistory": {},
}

def _get_api_headers():
    token = _get_api_token()
    headers = {
        "User-Agent": "XFBL-SlackBot/2.0 (+https://statsplus.net/xfbl)"
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers

def _ensure_cache_fresh(league_url, current_date=None):
    if current_date is None:
        current_date = get_league_current_date(league_url)
    date_key = f"{league_url.rstrip('/')}:{current_date.strftime('%Y-%m-%d')}"
    if _API_CACHE["date_key"] != date_key:
        _API_CACHE["date_key"] = date_key
        _API_CACHE["lgdata"] = None
        _API_CACHE["players"] = None
        _API_CACHE["players_active"] = None
        _API_CACHE["teams_csv"] = None
        _API_CACHE["bat_season"] = None
        _API_CACHE["pitch_season"] = None
        _API_CACHE["bat_career"] = None
        _API_CACHE["pitch_career"] = None
        _API_CACHE["atbats"] = {}
        _API_CACHE["gamehistory"] = {}

def _fetch_csv_api(url):
    import csv
    import io
    import time
    try:
        resp = requests.get(url, headers=_get_api_headers(), timeout=25)
        if resp.status_code != 200:
            return []
        text = resp.text.strip()
        if text.startswith("Request too soon"):
            m = re.search(r"wait\s+(\d+)\s+second", text, re.IGNORECASE)
            wait_sec = int(m.group(1)) + 2 if m else 15
            if wait_sec <= 65:
                time.sleep(wait_sec)
                resp = requests.get(url, headers=_get_api_headers(), timeout=25)
                if resp.status_code != 200:
                    return []
                text = resp.text.strip()
        if not text or text.startswith("Request too soon") or text.startswith("Invalid") or text.startswith("API token has expired") or text.startswith("Unknown API"):
            return []
        lines = [line for line in text.splitlines() if line.strip()]
        if not lines or "," not in lines[0]:
            return []
        return list(csv.DictReader(io.StringIO("\n".join(lines))))
    except Exception as e:
        print(f"API CSV fetch failed for {url}: {e}")
        return []

def get_cached_lgdata(league_url="https://statsplus.net/xfbl"):
    _ensure_cache_fresh(league_url)
    if _API_CACHE["lgdata"] is not None:
        return _API_CACHE["lgdata"]
    token = _get_api_token()
    token_param = f"?token={token}" if token else ""
    url = f"{league_url.rstrip('/')}/api/lgdata/{token_param}"
    try:
        resp = requests.get(url, headers=_get_api_headers(), timeout=15)
        if resp.status_code == 200 and "application/json" in resp.headers.get("Content-Type", ""):
            _API_CACHE["lgdata"] = resp.json()
            return _API_CACHE["lgdata"]
    except Exception as e:
        print(f"Error fetching /api/lgdata/: {e}")
    return {}

def get_cached_players(league_url="https://statsplus.net/xfbl", active_only=False):
    _ensure_cache_fresh(league_url)
    token = _get_api_token()
    token_param = f"?token={token}" if token else ""
    if active_only:
        if _API_CACHE["players_active"] is not None:
            return _API_CACHE["players_active"]
        sep = "&" if token_param else "?"
        url = f"{league_url.rstrip('/')}/api/players/{token_param}{sep}retired=0"
        rows = _fetch_csv_api(url)
        if rows:
            _API_CACHE["players_active"] = rows
        return rows
    else:
        if _API_CACHE["players"] is not None:
            return _API_CACHE["players"]
        url = f"{league_url.rstrip('/')}/api/players/{token_param}"
        rows = _fetch_csv_api(url)
        if rows:
            _API_CACHE["players"] = rows
        return rows

def get_cached_teams_csv(league_url="https://statsplus.net/xfbl"):
    _ensure_cache_fresh(league_url)
    if _API_CACHE["teams_csv"] is not None:
        return _API_CACHE["teams_csv"]
    token = _get_api_token()
    token_param = f"?token={token}" if token else ""
    url = f"{league_url.rstrip('/')}/api/teams/{token_param}"
    rows = _fetch_csv_api(url)
    if rows:
        _API_CACHE["teams_csv"] = rows
    return rows

def get_cached_season_stats(league_url="https://statsplus.net/xfbl"):
    _ensure_cache_fresh(league_url)
    token = _get_api_token()
    token_param = f"?token={token}" if token else ""
    if _API_CACHE["bat_season"] is None:
        bat_rows = _fetch_csv_api(f"{league_url.rstrip('/')}/api/playerbatstatsv2/{token_param}")
        if bat_rows:
            _API_CACHE["bat_season"] = bat_rows
    if _API_CACHE["pitch_season"] is None:
        pitch_rows = _fetch_csv_api(f"{league_url.rstrip('/')}/api/playerpitchstatsv2/{token_param}")
        if pitch_rows:
            _API_CACHE["pitch_season"] = pitch_rows
    return _API_CACHE["bat_season"] or [], _API_CACHE["pitch_season"] or []

def get_cached_career_stats(league_url="https://statsplus.net/xfbl"):
    """
    Aggregates career MLB stats (level_id=1, split_id=1) across up to 25 seasons
    ending at the current game year using a single multi-year API request.
    Returns (career_bat_dict, career_pitch_dict) keyed by player_id string.
    """
    from collections import defaultdict
    current_date = get_league_current_date(league_url)
    _ensure_cache_fresh(league_url, current_date)
    if _API_CACHE["bat_career"] is not None and _API_CACHE["pitch_career"] is not None:
        return _API_CACHE["bat_career"], _API_CACHE["pitch_career"]

    token = _get_api_token()
    token_param = f"?token={token}" if token else "?"
    sep = "&" if token else ""
    current_year = current_date.year
    years_query = "&".join(f"year={y}" for y in range(current_year - 24, current_year + 1))

    bat_url = f"{league_url.rstrip('/')}/api/playerbatstatsv2/{token_param}{sep}split=1&{years_query}"
    pitch_url = f"{league_url.rstrip('/')}/api/playerpitchstatsv2/{token_param}{sep}split=1&{years_query}"

    bat_rows = _fetch_csv_api(bat_url)
    pitch_rows = _fetch_csv_api(pitch_url)

    career_bat = defaultdict(lambda: {"h": 0, "hr": 0, "rbi": 0, "d": 0, "t": 0, "xbh": 0, "sb": 0, "bb": 0, "pa": 0, "g": 0, "team_id": ""})
    for r in bat_rows:
        if r.get("level_id") == "1" and r.get("split_id") == "1":
            pid = r.get("player_id", "").strip()
            if not pid:
                continue
            cb = career_bat[pid]
            h = int(r.get("h") or 0)
            d = int(r.get("d") or 0)
            t = int(r.get("t") or 0)
            hr = int(r.get("hr") or 0)
            cb["h"] += h
            cb["d"] += d
            cb["t"] += t
            cb["hr"] += hr
            cb["xbh"] += (d + t + hr)
            cb["rbi"] += int(r.get("rbi") or 0)
            cb["sb"] += int(r.get("sb") or 0)
            cb["bb"] += int(r.get("bb") or 0)
            cb["pa"] += int(r.get("pa") or 0)
            cb["g"] += int(r.get("g") or 0)
            if r.get("year") == str(current_year) and r.get("team_id"):
                cb["team_id"] = r.get("team_id")

    career_pitch = defaultdict(lambda: {"w": 0, "l": 0, "k": 0, "s": 0, "g": 0, "gs": 0, "ip_outs": 0, "team_id": ""})
    for r in pitch_rows:
        if r.get("level_id") == "1" and r.get("split_id") == "1":
            pid = r.get("player_id", "").strip()
            if not pid:
                continue
            cp = career_pitch[pid]
            cp["w"] += int(r.get("w") or 0)
            cp["l"] += int(r.get("l") or 0)
            cp["k"] += int(r.get("k") or 0)
            cp["s"] += int(r.get("s") or 0)
            cp["g"] += int(r.get("g") or 0)
            cp["gs"] += int(r.get("gs") or 0)
            if r.get("year") == str(current_year) and r.get("team_id"):
                cp["team_id"] = r.get("team_id")

    if bat_rows:
        _API_CACHE["bat_career"] = career_bat
    if pitch_rows:
        _API_CACHE["pitch_career"] = career_pitch
    return career_bat, career_pitch

def get_cached_atbats(league_url, cutoff_date, current_date):
    _ensure_cache_fresh(league_url, current_date)
    start_str = cutoff_date.strftime("%Y-%m-%d")
    end_str = current_date.strftime("%Y-%m-%d")
    key = (start_str, end_str)
    if key in _API_CACHE["atbats"]:
        return _API_CACHE["atbats"][key]

    token = _get_api_token()
    token_param = f"?token={token}" if token else ""
    sep = "&" if token_param else "?"
    atbats_url = f"{league_url.rstrip('/')}/api/atbats/{token_param}{sep}start={start_str}&end={end_str}"
    rows = _fetch_csv_api(atbats_url)
    if rows:
        _API_CACHE["atbats"][key] = rows
    return rows

def get_cached_gamehistory(league_url, cutoff_date, current_date):
    _ensure_cache_fresh(league_url, current_date)
    start_str = cutoff_date.strftime("%Y-%m-%d")
    end_str = current_date.strftime("%Y-%m-%d")
    key = (start_str, end_str)
    if key in _API_CACHE["gamehistory"]:
        return _API_CACHE["gamehistory"][key]

    token = _get_api_token()
    token_param = f"?token={token}" if token else ""
    sep = "&" if token_param else "?"
    gh_url = f"{league_url.rstrip('/')}/api/gamehistory/{token_param}{sep}start={start_str}&end={end_str}"
    rows = _fetch_csv_api(gh_url)
    if rows:
        _API_CACHE["gamehistory"][key] = rows
    return rows

def _get_maps(league_url="https://statsplus.net/xfbl"):
    """
    Returns (player_names, player_teams, team_abbr_map, team_full_map, primary_lid)
    from cached API data.
    """
    lgdata = get_cached_lgdata(league_url)
    primary_lid = 100
    for l in lgdata.get("leagues", []):
        if l.get("primary_league"):
            primary_lid = l.get("league_id", 100)
            break

    team_abbr_map = {}
    team_full_map = {}
    for t in lgdata.get("teams", []):
        tid_str = str(t.get("team_id"))
        abbr = t.get("abbr", "")
        full = f"{t.get('name', '')} {t.get('nickname', '')}".strip()
        team_abbr_map[tid_str] = abbr
        if t.get("league_id") == primary_lid:
            team_full_map[tid_str] = full

    player_names = {}
    player_teams = {}
    for pr in get_cached_players(league_url, active_only=False):
        pid = pr.get("ID", "").strip()
        if pid:
            first = pr.get("First Name", "").strip()
            last = pr.get("Last Name", "").strip()
            player_names[pid] = f"{first} {last}".strip()
            tid = pr.get("Team ID", "").strip()
            if tid and tid != "0":
                player_teams[pid] = tid

    return player_names, player_teams, team_abbr_map, team_full_map, primary_lid

def get_league_current_date(league_url="https://statsplus.net/xfbl"):
    """
    Fetches the exact in-game date from the /api/date/ endpoint.
    Falls back to scraping the homepage if unavailable.
    """
    token = _get_api_token()
    token_param = f"?token={token}" if token else ""
    try:
        resp = requests.get(f"{league_url.rstrip('/')}/api/date/{token_param}", headers=_get_api_headers(), timeout=10)
        if resp.status_code == 200 and resp.text.strip():
            date_str = resp.text.strip()
            return datetime.strptime(date_str, "%Y-%m-%d")
    except Exception as e:
        print(f"Error fetching date from API: {e}")

    try:
        session = get_statsplus_session()
        home_html = session.get(league_url, timeout=10).text
        home_soup = BeautifulSoup(home_html, 'html.parser')
        date_element = home_soup.find(string=re.compile(r"Game Date:"))
        if date_element:
            date_str = date_element.replace("Game Date:", "").strip()
            return datetime.strptime(date_str, "%Y-%m-%d")
    except Exception:
        pass

    return datetime.now()

def get_best_performances(league_url="https://statsplus.net/xfbl", days_back=7):
    """
    Fetches the highest ranked pitcher and batter performances within the sim window.
    Prefers using the StatsPlus API (/api/atbats/, /api/players/, /api/lgdata/) to avoid
    triggering 429 rate limits on HTML scraping. Falls back to HTML scraping if API data is unavailable.
    """
    current_date = get_league_current_date(league_url)
    cutoff_date = current_date - timedelta(days=days_back)
    print(f"Looking for performances between {cutoff_date.strftime('%Y-%m-%d')} and {current_date.strftime('%Y-%m-%d')}")

    # 1. Attempt API calculation first
    try:
        best_p, best_b = get_best_performances_from_api(league_url, cutoff_date, current_date)
        if best_p or best_b:
            return best_p, best_b
    except Exception as e:
        print(f"API performance calculation error: {e}")

    # 2. Fallback to HTML scraping
    bat_url = f"{league_url}/bestgames/bat/"
    pitch_url = f"{league_url}/bestgames/pitch/"
    session = get_statsplus_session()

    best_batter = scrape_table_with_dates(bat_url, cutoff_date, current_date, league_url, is_pitcher=False, session=session)
    best_pitcher = scrape_table_with_dates(pitch_url, cutoff_date, current_date, league_url, is_pitcher=True, session=session)

    return best_pitcher, best_batter

def get_best_performances_from_api(league_url, cutoff_date, current_date):
    """
    Calculates top batter and pitcher performances directly from cached /api/atbats/ and /api/lgdata/.
    """
    from collections import defaultdict

    player_names, _, team_abbr_map, _, _ = _get_maps(league_url)
    rows = get_cached_atbats(league_url, cutoff_date, current_date)
    if not rows:
        return None, None

    # Track games and teams
    game_teams = defaultdict(set)
    for r in rows:
        gid = r.get('game_id')
        tid = r.get('team_id')
        if gid and tid:
            game_teams[gid].add(tid)

    # 1. Evaluate Batters (regular season '0' or postseason '3')
    batter_games = defaultdict(lambda: {'ab': 0, 'h': 0, 'd': 0, 't': 0, 'hr': 0, 'rbi': 0, 'r': 0, 'bb': 0, 'k': 0, 'date': '', 'team_id': '', 'game_id': ''})
    for r in rows:
        if r.get('game_type') not in ('0', '3'):
            continue
        gdate_str = r.get('date', '')
        try:
            gdate = datetime.strptime(gdate_str, "%Y-%m-%d")
            if not (cutoff_date <= gdate <= current_date):
                continue
        except Exception:
            continue

        pid = r.get('player_id')
        gid = r.get('game_id')
        key = (pid, gid)
        bg = batter_games[key]
        bg['date'] = gdate_str
        bg['team_id'] = r.get('team_id')
        bg['game_id'] = gid
        bg['rbi'] += int(r.get('rbi') or 0)
        bg['r'] += int(r.get('r') or 0)
        res = r.get('result')
        if res in ('4', '5', '6', '7', '8', '9', '1'):
            bg['ab'] += 1
        if res in ('6', '7', '8', '9'):
            bg['h'] += 1
        if res == '7':
            bg['d'] += 1
        if res == '8':
            bg['t'] += 1
        if res == '9':
            bg['hr'] += 1
        if res == '2':
            bg['bb'] += 1
        if res == '1':
            bg['k'] += 1

    best_batter_obj = None
    if batter_games:
        scored_batters = []
        for (pid, gid), st in batter_games.items():
            tb = (st['h'] - st['d'] - st['t'] - st['hr']) + (st['d'] * 2) + (st['t'] * 3) + (st['hr'] * 4)
            score = tb * 2 + st['rbi'] * 1.5 + st['r'] * 1.0 + st['bb'] * 0.75
            scored_batters.append((score, pid, gid, st, tb))
        
        scored_batters.sort(reverse=True, key=lambda x: x[0])
        score, b_pid, b_gid, b_st, b_tb = scored_batters[0]
        
        opp_set = game_teams.get(b_gid, set()) - {b_st['team_id']}
        opp_abbr = team_abbr_map.get(list(opp_set)[0], '???') if opp_set else '???'
        team_abbr = team_abbr_map.get(str(b_st['team_id']), '???')
        pname = player_names.get(b_pid, f"Player {b_pid}")
        box_url = f"{league_url.rstrip('/')}/reports/news/html/box_scores/game_box_{b_gid}.html"

        # stats mapping matching Slack block builder: 0:AB, 1:H, 2:RBI, 3:HR, 4:R, 5:BB, 6:GS
        b_stats = [str(b_st['ab']), str(b_st['h']), str(b_st['rbi']), str(b_st['hr']), str(b_st['r']), str(b_st['bb']), f"{score:.1f}"]
        b_stat_line = f"AB: {b_st['ab']} | R: {b_st['r']} | H: {b_st['h']} | HR: {b_st['hr']} | RBI: {b_st['rbi']} | BB: {b_st['bb']} | GS: {score:.1f}"

        best_batter_obj = {
            "name": pname,
            "team": team_abbr,
            "opponent": opp_abbr,
            "player_id": b_pid,
            "date": b_st['date'],
            "stat_line": b_stat_line,
            "stats": b_stats,
            "metric": f"{score:.1f} Batting Score",
            "is_pitcher": False,
            "box_url": box_url
        }

    # 2. Evaluate Pitchers (regular season '0' or postseason '3')
    pitcher_games = defaultdict(lambda: {'bf': 0, 'h': 0, 'd': 0, 't': 0, 'hr': 0, 'rbi': 0, 'r': 0, 'bb': 0, 'k': 0, 'outs': 0, 'date': '', 'team_id': '', 'game_id': '', 'opp_id': ''})
    for r in rows:
        if r.get('game_type') not in ('0', '3'):
            continue
        gdate_str = r.get('date', '')
        try:
            gdate = datetime.strptime(gdate_str, "%Y-%m-%d")
            if not (cutoff_date <= gdate <= current_date):
                continue
        except Exception:
            continue

        pid = r.get('pitcher_id')
        gid = r.get('game_id')
        opp_tid = r.get('team_id')
        key = (pid, gid)
        pg = pitcher_games[key]
        pg['date'] = gdate_str
        pg['game_id'] = gid
        pg['opp_id'] = opp_tid
        pg['bf'] += 1
        pg['r'] += int(r.get('r') or 0)
        res = r.get('result')
        if res in ('4', '5', '1'):
            pg['outs'] += 1
        if res in ('6', '7', '8', '9'):
            pg['h'] += 1
        if res == '7':
            pg['d'] += 1
        if res == '8':
            pg['t'] += 1
        if res == '9':
            pg['hr'] += 1
        if res == '2':
            pg['bb'] += 1
        if res == '1':
            pg['k'] += 1

    best_pitcher_obj = None
    if pitcher_games:
        scored_pitchers = []
        for (pid, gid), st in pitcher_games.items():
            outs = st['outs']
            ip_full = outs // 3
            ip_rem = outs % 3
            ip_str = f"{ip_full}.{ip_rem}"
            bonus = max(0, (ip_full - 4) * 2)
            gs = 50 + outs + bonus + st['k'] - (2 * st['h']) - (4 * st['r']) - (2 * st['bb'])
            scored_pitchers.append((gs, pid, gid, st, ip_str))

        scored_pitchers.sort(reverse=True, key=lambda x: x[0])
        gs_score, p_pid, p_gid, p_st, p_ip_str = scored_pitchers[0]

        opp_abbr = team_abbr_map.get(str(p_st['opp_id']), '???')
        p_team_set = game_teams.get(p_gid, set()) - {p_st['opp_id']}
        team_abbr = team_abbr_map.get(list(p_team_set)[0], '???') if p_team_set else '???'
        pname = player_names.get(p_pid, f"Player {p_pid}")
        box_url = f"{league_url.rstrip('/')}/reports/news/html/box_scores/game_box_{p_gid}.html"

        # stats mapping: 0:IP, 1:R, 2:H, 3:HR, 4:BB, 5:K, 6:GS
        p_stats = [p_ip_str, str(p_st['r']), str(p_st['h']), str(p_st['hr']), str(p_st['bb']), str(p_st['k']), str(gs_score)]
        p_stat_line = f"IP: {p_ip_str} | H: {p_st['h']} | K: {p_st['k']} | BB: {p_st['bb']} | HR: {p_st['hr']} | GS: {gs_score}"

        best_pitcher_obj = {
            "name": pname,
            "team": team_abbr,
            "opponent": opp_abbr,
            "player_id": p_pid,
            "date": p_st['date'],
            "stat_line": p_stat_line,
            "stats": p_stats,
            "metric": f"{gs_score} Game Score",
            "is_pitcher": True,
            "box_url": box_url
        }

    return best_pitcher_obj, best_batter_obj

def scrape_table_with_dates(url, cutoff_date, current_date, league_url, is_pitcher=False, session=None):
    if session is None:
        session = get_statsplus_session()
    try:
        response = session.get(url, timeout=15)
        soup = BeautifulSoup(response.text, 'html.parser')
    except Exception as e:
        print(f"Error scraping {url}: {e}")
        return None
    
    table = soup.find('table')
    if not table:
        print(f"Could not find data table at {url}")
        return None
        
    tbody = table.find('tbody')
    rows = tbody.find_all('tr') if tbody else table.find_all('tr')
    
    for row in rows:
        cols = row.find_all('td')
        if not cols or len(cols) < 10:
            continue
            
        player_link = cols[1].find('a')
        player_name = player_link.text.strip() if player_link else cols[1].text.strip()
        player_id = re.search(r'/player/(\d+)', player_link['href']).group(1) if player_link else None
        
        team_abbr = cols[2].text.strip()
        opponent = cols[3].text.strip()
        date_str = cols[4].text.strip()
        game_date = parse_ootp_date(date_str)
        
        if not game_date:
            continue
            
        box_link_tag = cols[5].find('a')
        box_url = ""
        if box_link_tag:
            from urllib.parse import urljoin
            box_url = urljoin(league_url, box_link_tag['href'])
                
        if cutoff_date <= game_date <= current_date:
            if is_pitcher:
                stats = [c.text.strip() for c in cols[6:]]
                if len(stats) >= 7:
                    # Pitching columns: 0:IP, 1:R, 2:H, 3:HR, 4:BB, 5:K, 6:GS
                    stat_line = f"IP: {stats[0]} | H: {stats[2]} | K: {stats[5]} | BB: {stats[4]} | HR: {stats[3]} | GS: {stats[6]}"
                    metric = f"{stats[-1]} Game Score"
                else:
                    stat_line = " | ".join(stats)
                    metric = f"{stats[-1]} Game Score" if stats else "Unknown"
            else:
                stats = [c.text.strip() for c in cols[6:]]
                if len(stats) >= 7:
                    # Batting columns: 0:AB, 1:H, 2:RBI, 3:HR, 4:R, 5:BB, 6:GS
                    stat_line = f"AB: {stats[0]} | R: {stats[4]} | H: {stats[1]} | HR: {stats[3]} | RBI: {stats[2]} | BB: {stats[5]} | GS: {stats[6]}"
                    metric = f"Score/WPA: {stats[-1]}"
                else:
                    stat_line = " | ".join(stats)
                    metric = f"Score: {stats[-1]}" if stats else "Unknown"

            return {
                "name": player_name,
                "team": team_abbr,
                "opponent": opponent,
                "player_id": player_id,
                "date": game_date.strftime('%Y-%m-%d'),
                "stat_line": stat_line,
                "stats": stats,
                "metric": metric,
                "is_pitcher": is_pitcher,
                "box_url": box_url
            }

    print(f"Could not find a performance in the timeframe among the listed games.")
    return None


def get_headlines_and_milestones(league_url="https://statsplus.net/xfbl", days_back=7):
    """
    Detects career milestones reached this sim and rare feats/awards.
    1. Pure StatsPlus API calculation: compares multi-year career totals from
       /api/playerbatstatsv2/ & /api/playerpitchstatsv2/ against sim deltas
       from /api/atbats/ & /api/gamehistory/, plus checks for no-hitters,
       1-hit shutouts, cycles, and 5+ hit games.
    2. Supplements with OOTP static news report (league_100_news.html) within
       the sim window (e.g. Player of the Week, hitting streaks, milestones).
    3. Falls back to authenticated /api/recap/ only if needed.
    """
    from collections import defaultdict

    current_date = get_league_current_date(league_url)
    cutoff_date = current_date - timedelta(days=days_back)
    player_names, player_teams, team_abbr_map, _, _ = _get_maps(league_url)

    headlines = []
    seen_milestone_keys = set()  # (player_name_lower, stat_category)

    # ── 1. API-BASED CAREER MILESTONES & RARE FEATS ───────────────────────────
    try:
        career_bat, career_pitch = get_cached_career_stats(league_url)
        atbats_rows = get_cached_atbats(league_url, cutoff_date, current_date)
        gh_rows = get_cached_gamehistory(league_url, cutoff_date, current_date)

        sim_bat = defaultdict(lambda: {"h": 0, "hr": 0, "rbi": 0, "xbh": 0, "sb": 0, "team_id": ""})
        sim_pitch = defaultdict(lambda: {"k": 0, "w": 0, "s": 0, "team_id": ""})

        # Track single-game batter feats from atbats
        batter_game_lines = defaultdict(lambda: {"1b": 0, "2b": 0, "3b": 0, "hr": 0, "h": 0, "team_id": ""})

        for r in atbats_rows:
            if r.get("game_type") not in ("0", "3"):
                continue
            gdate_str = r.get("date", "")
            try:
                gdate = datetime.strptime(gdate_str, "%Y-%m-%d")
                if not (cutoff_date <= gdate <= current_date):
                    continue
            except Exception:
                continue

            pid = r.get("player_id", "").strip()
            pitcher_id = r.get("pitcher_id", "").strip()
            tid = r.get("team_id", "").strip()
            gid = r.get("game_id", "").strip()
            res = r.get("result", "")

            if pid:
                sb_row = sim_bat[pid]
                sb_row["team_id"] = tid
                sb_row["rbi"] += int(r.get("rbi") or 0)
                sb_row["sb"] += int(r.get("sb") or 0)
                bgl = batter_game_lines[(pid, gid)]
                bgl["team_id"] = tid
                if res in ("6", "7", "8", "9"):
                    sb_row["h"] += 1
                    bgl["h"] += 1
                if res == "6":
                    bgl["1b"] += 1
                elif res == "7":
                    sb_row["xbh"] += 1
                    bgl["2b"] += 1
                elif res == "8":
                    sb_row["xbh"] += 1
                    bgl["3b"] += 1
                elif res == "9":
                    sb_row["hr"] += 1
                    sb_row["xbh"] += 1
                    bgl["hr"] += 1

            if pitcher_id and res == "1":
                sim_pitch[pitcher_id]["k"] += 1

        # Track pitcher wins, saves, no-hitters, 1-hit shutouts from gamehistory
        for gh in gh_rows:
            if gh.get("game_type") not in ("0", "3"):
                continue
            wp = gh.get("winning_pitcher", "").strip()
            sp = gh.get("save_pitcher", "").strip()
            home_tid = gh.get("home_team", "").strip()
            away_tid = gh.get("away_team", "").strip()
            runs0 = int(gh.get("runs0") or 0)
            runs1 = int(gh.get("runs1") or 0)
            hits0 = int(gh.get("hits0") or 0)
            hits1 = int(gh.get("hits1") or 0)
            cg0 = gh.get("cg0", "0") == "1"
            cg1 = gh.get("cg1", "0") == "1"

            win_tid = home_tid if runs1 > runs0 else away_tid
            if wp and wp != "0":
                sim_pitch[wp]["w"] += 1
                sim_pitch[wp]["team_id"] = win_tid
            if sp and sp != "0":
                sim_pitch[sp]["s"] += 1
                sim_pitch[sp]["team_id"] = win_tid

            # No-hitter / 1-hit shutout check
            if hits0 == 0 and runs1 > 0:
                p_name = gh.get("starter1_name") or player_names.get(gh.get("starter1", ""), "Pitcher")
                t_abbr = team_abbr_map.get(home_tid, "???")
                opp_abbr = team_abbr_map.get(away_tid, "???")
                headlines.append(f"🎩 *NO-HITTER Alert*: *{p_name}* ({t_abbr}) threw a no-hitter against {opp_abbr}!")
                seen_milestone_keys.add((p_name.lower(), "nohitter"))
            elif hits1 == 0 and runs0 > 0:
                p_name = gh.get("starter0_name") or player_names.get(gh.get("starter0", ""), "Pitcher")
                t_abbr = team_abbr_map.get(away_tid, "???")
                opp_abbr = team_abbr_map.get(home_tid, "???")
                headlines.append(f"🎩 *NO-HITTER Alert*: *{p_name}* ({t_abbr}) threw a no-hitter against {opp_abbr}!")
                seen_milestone_keys.add((p_name.lower(), "nohitter"))
            elif cg1 and runs0 == 0 and hits0 == 1:
                p_name = gh.get("starter1_name") or player_names.get(gh.get("starter1", ""), "Pitcher")
                t_abbr = team_abbr_map.get(home_tid, "???")
                opp_abbr = team_abbr_map.get(away_tid, "???")
                headlines.append(f"💎 *1-Hit Shutout*: *{p_name}* ({t_abbr}) spun a complete-game 1-hit shutout vs {opp_abbr}!")
                seen_milestone_keys.add((p_name.lower(), "shutout"))
            elif cg0 and runs1 == 0 and hits1 == 1:
                p_name = gh.get("starter0_name") or player_names.get(gh.get("starter0", ""), "Pitcher")
                t_abbr = team_abbr_map.get(away_tid, "???")
                opp_abbr = team_abbr_map.get(home_tid, "???")
                headlines.append(f"💎 *1-Hit Shutout*: *{p_name}* ({t_abbr}) spun a complete-game 1-hit shutout vs {opp_abbr}!")
                seen_milestone_keys.add((p_name.lower(), "shutout"))

        # Check cycles and 5+ hit games from atbats
        for (pid, gid), bgl in batter_game_lines.items():
            name = player_names.get(pid, f"Player {pid}")
            t_abbr = team_abbr_map.get(bgl["team_id"] or player_teams.get(pid, ""), "???")
            if bgl["1b"] >= 1 and bgl["2b"] >= 1 and bgl["3b"] >= 1 and bgl["hr"] >= 1:
                headlines.append(f"🚲 *Cycle Watch*: *{name}* ({t_abbr}) hit for the cycle!")
                seen_milestone_keys.add((name.lower(), "cycle"))
            elif bgl["h"] >= 5:
                headlines.append(f"🔥 *5-Hit Game*: *{name}* ({t_abbr}) collected *{bgl['h']} hits* in a single game!")
                seen_milestone_keys.add((name.lower(), "5hit"))

        # Check Batting Career Milestones crossed this sim
        bat_thresholds = [
            ("h", [1000, 1500, 2000, 2500, 3000, 3500, 4000], "career hits", "hit"),
            ("hr", [200, 250, 300, 350, 400, 450, 500, 600, 700], "career home runs", "hr"),
            ("rbi", [1000, 1250, 1500, 1750, 2000, 2500], "career RBIs", "rbi"),
            ("xbh", [500, 600, 700, 800, 900, 1000, 1200, 1400], "career extra-base hits", "xbh"),
            ("sb", [300, 400, 500, 600, 700, 800], "career stolen bases", "sb"),
        ]
        for pid, sb_vals in sim_bat.items():
            c_vals = career_bat.get(pid)
            if not c_vals:
                continue
            name = player_names.get(pid, f"Player {pid}")
            tid = sb_vals["team_id"] or c_vals.get("team_id") or player_teams.get(pid, "")
            t_abbr = team_abbr_map.get(str(tid), "???")
            for stat_key, milestones, label, cat_key in bat_thresholds:
                delta = sb_vals.get(stat_key, 0)
                if delta <= 0:
                    continue
                curr_total = c_vals.get(stat_key, 0)
                prev_total = curr_total - delta
                for m in milestones:
                    if prev_total < m <= curr_total:
                        headlines.append(f"🎖️ *{name}* ({t_abbr}) reached *{m:,} {label}*!")
                        seen_milestone_keys.add((name.lower(), cat_key))

        # Check Pitching Career Milestones crossed this sim
        pitch_thresholds = [
            ("w", [150, 200, 250, 300, 350], "career wins", "win"),
            ("k", [1000, 1500, 2000, 2500, 3000, 3500, 4000], "career strikeouts", "k"),
            ("s", [200, 250, 300, 350, 400, 500], "career saves", "save"),
        ]
        for pid, sp_vals in sim_pitch.items():
            c_vals = career_pitch.get(pid)
            if not c_vals:
                continue
            name = player_names.get(pid, f"Player {pid}")
            tid = sp_vals["team_id"] or c_vals.get("team_id") or player_teams.get(pid, "")
            t_abbr = team_abbr_map.get(str(tid), "???")
            for stat_key, milestones, label, cat_key in pitch_thresholds:
                delta = sp_vals.get(stat_key, 0)
                if delta <= 0:
                    continue
                curr_total = c_vals.get(stat_key, 0)
                prev_total = curr_total - delta
                for m in milestones:
                    if prev_total < m <= curr_total:
                        headlines.append(f"🎖️ *{name}* ({t_abbr}) reached *{m:,} {label}*!")
                        seen_milestone_keys.add((name.lower(), cat_key))
    except Exception as e:
        print(f"API milestone/feat detection error: {e}")

    # ── 2. OOTP STATIC NEWS REPORT SUPPLEMENT (league_100_news.html) ──────────
    news_url = f"{league_url.rstrip('/')}/reports/news/html/leagues/league_100_news.html"
    try:
        resp = requests.get(news_url, headers=_get_api_headers(), timeout=15)
        if resp.status_code == 200:
            news_soup = BeautifulSoup(resp.text, "html.parser")
            for table in news_soup.find_all("table", class_="data"):
                th = table.find("th", class_="dl")
                if not th:
                    continue
                event_date = parse_ootp_date(th.get_text(separator=" ", strip=True))
                if not event_date:
                    continue
                if event_date < cutoff_date:
                    break
                if event_date > current_date:
                    continue

                for tr in table.find_all("tr"):
                    td = tr.find("td", class_=lambda c: c and "dl" in c)
                    if not td:
                        continue
                    text = td.get_text(separator=" ", strip=True)
                    text_clean = re.sub(r"\s+", " ", text).strip()

                    # Career milestones in OOTP news (e.g. "Florida Marlins : Bernie Williams gets his 3500th career hit!")
                    m_hit = re.search(r":\s*([^:]+?)\s+(?:gets|collects|reaches)\s+his\s+(\d+)(?:st|nd|rd|th)\s+career\s+hit", text_clean, re.IGNORECASE)
                    if m_hit:
                        pname = m_hit.group(1).strip()
                        amt = int(m_hit.group(2))
                        if (pname.lower(), "hit") not in seen_milestone_keys:
                            headlines.append(f"🎖️ *{pname}* reached *{amt:,} career hits*!")
                            seen_milestone_keys.add((pname.lower(), "hit"))
                        continue

                    m_hr = re.search(r":\s*([^:]+?)\s+(?:launches|hits|belts|blasts|clubs)\s+his\s+(\d+)(?:st|nd|rd|th)\s+career\s+(?:home run|homer|HR)", text_clean, re.IGNORECASE)
                    if m_hr:
                        pname = m_hr.group(1).strip()
                        amt = int(m_hr.group(2))
                        if (pname.lower(), "hr") not in seen_milestone_keys:
                            headlines.append(f"🎖️ *{pname}* launched his *{amt:,}th career home run*!")
                            seen_milestone_keys.add((pname.lower(), "hr"))
                        continue

                    m_win = re.search(r":\s*([^:]+?)\s+(?:wins|picks up|earns)\s+his\s+(\d+)(?:st|nd|rd|th)\s+career\s+(?:win|victory)", text_clean, re.IGNORECASE)
                    if m_win:
                        pname = m_win.group(1).strip()
                        amt = int(m_win.group(2))
                        if (pname.lower(), "win") not in seen_milestone_keys:
                            headlines.append(f"🎖️ *{pname}* earned his *{amt:,}th career win*!")
                            seen_milestone_keys.add((pname.lower(), "win"))
                        continue

                    # Player of the Week awards
                    m_potw = re.search(r"^[A-Z0-9]{1,3}\s+(.+?)\s+of the\s+(.+?)\s+honored:\s+Wins the\s+(.+?Player of the Week Award)", text_clean, re.IGNORECASE)
                    if m_potw:
                        pname = m_potw.group(1).strip()
                        tname = m_potw.group(2).strip()
                        award = m_potw.group(3).strip()
                        headlines.append(f"🏅 *{pname}* ({tname}) won the *{award}*.")
                        continue

                    # No-hitters, shutouts, hitting streaks
                    if re.search(r"no-hitter|perfect game", text_clean, re.IGNORECASE):
                        m_nh = re.search(r":\s*([^:]+?)\s+(?:pitches|throws|tosses)", text_clean, re.IGNORECASE)
                        pname = m_nh.group(1).strip() if m_nh else ""
                        if not pname or (pname.lower(), "nohitter") not in seen_milestone_keys:
                            headlines.append(f"🎩 *{text_clean}*")
                    elif re.search(r"1-hit shutout|hits for the cycle|hitting streak to \d+ games", text_clean, re.IGNORECASE):
                        m_sh = re.search(r":\s*([A-Za-z\.\s'-]+?)\s+(?:pitches|hits|extends)", text_clean, re.IGNORECASE)
                        pname = m_sh.group(1).strip() if m_sh else ""
                        if not pname or (pname.lower(), "shutout") not in seen_milestone_keys:
                            headlines.append(f"⚡ {text_clean}")
    except Exception as e:
        print(f"Error checking news report for headlines: {e}")

    # ── 3. AUTHENTICATED /api/recap/ FALLBACK ─────────────────────────────────
    if not headlines:
        token = _get_api_token()
        token_param = f"?token={token}" if token else ""
        recap_url = f"{league_url.rstrip('/')}/api/recap/{token_param}"
        try:
            response = requests.get(recap_url, headers=_get_api_headers(), timeout=15)
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, "html.parser")
                panel = soup.find(id="recap-msg-panel")
                if panel:
                    for div in panel.find_all("div", class_="smallfont oneline"):
                        text = " ".join(div.text.split())
                        match = re.search(r"reached (\d+) ([a-z\s]+)", text, re.IGNORECASE)
                        if match:
                            amount = int(match.group(1))
                            stat = match.group(2).strip().lower()
                            is_impressive = (
                                ("hit" in stat and "extra" not in stat and amount >= 1000)
                                or ("home run" in stat and amount >= 200)
                                or ("win" in stat and amount >= 150)
                                or ("strikeout" in stat and amount >= 1000)
                                or ("save" in stat and amount >= 200)
                                or ("rbi" in stat and amount >= 1000)
                                or ("extra base" in stat and amount >= 500)
                            )
                            if is_impressive:
                                name_match = re.search(r"^[A-Z0-9]{1,2} ([^\(]+) \(([A-Z]+)\)", text)
                                if name_match:
                                    name = name_match.group(1).strip()
                                    team = name_match.group(2).strip()
                                    headlines.append(f"🎖️ *{name}* ({team}) reached *{amount:,} {stat}*.")
        except Exception as e:
            print(f"Error fetching authenticated recap fallback: {e}")

    # Deduplicate headlines while preserving order
    seen = set()
    deduped = []
    for h in headlines:
        if h not in seen:
            seen.add(h)
            deduped.append(h)

    return deduped

TEAM_MAPPING = {
    "ANA": "Anaheim Angels", "ARI": "Arizona Diamondbacks", "ATL": "Atlanta Braves",
    "BAL": "Baltimore Orioles", "BOS": "Boston Red Sox", "CWS": "Chicago White Sox",
    "CHC": "Chicago Cubs", "CIN": "Cincinnati Reds", "CLE": "Cleveland Indians",
    "COL": "Colorado Rockies", "DET": "Detroit Tigers", "FLA": "Florida Marlins",
    "HOU": "Houston Astros", "KC": "Kansas City Royals", "LAD": "Los Angeles Dodgers",
    "MIL": "Milwaukee Brewers", "MLW": "Milwaukee Brewers", "MIN": "Minnesota Twins", "MON": "Montreal Expos",
    "NYM": "New York Mets", "NYY": "New York Yankees", "OAK": "Oakland Athletics",
    "PHI": "Philadelphia Phillies", "PIT": "Pittsburgh Pirates", "SD": "San Diego Padres",
    "SF": "San Francisco Giants", "SEA": "Seattle Mariners", "STL": "St. Louis Cardinals",
    "TB": "Tampa Bay Rays", "TEX": "Texas Rangers", "TOR": "Toronto Blue Jays",
    "WAS": "Washington Nationals", "LAA": "Los Angeles Angels", "MIA": "Miami Marlins"
}

def get_full_team_name(raw_text):
    parts = raw_text.split('\n')
    if len(parts) > 1:
        abbr = parts[1].strip()
        return TEAM_MAPPING.get(abbr, f"{parts[0]} ({abbr})")
    return raw_text

def get_team_momentum(league_url="https://statsplus.net/xfbl", days_back=7):
    """
    Computes each MLB team's momentum (ELO rating change) over the sim window
    directly from /api/gamehistory/ and /api/lgdata/ without scraping HTML.
    """
    from collections import defaultdict

    current_date = get_league_current_date(league_url)
    cutoff_date = current_date - timedelta(days=days_back)
    lgdata = get_cached_lgdata(league_url)
    gh_rows = get_cached_gamehistory(league_url, cutoff_date, current_date)
    if not lgdata or not gh_rows:
        return None, None

    primary_lid = 100
    for l in lgdata.get("leagues", []):
        if l.get("primary_league"):
            primary_lid = l.get("league_id", 100)
            break

    teams_dict = {
        str(t["team_id"]): f"{t.get('name', '')} {t.get('nickname', '')}".strip()
        for t in lgdata.get("teams", [])
        if t.get("league_id") == primary_lid
    }
    standings_pct = {
        str(st["team_id"]): float(st.get("pct") or 0.500)
        for st in lgdata.get("standings", [])
    }

    # Seed each team's base ELO from their season winning percentage (1500 baseline)
    base_elo = {
        tid: 1500.0 + (standings_pct.get(tid, 0.5) - 0.5) * 400.0
        for tid in teams_dict
    }
    elo_delta = defaultdict(float)
    games_played = defaultdict(int)

    K = 12.0
    for gh in gh_rows:
        if gh.get("game_type") != "0":
            continue
        away_id = str(gh.get("away_team", ""))
        home_id = str(gh.get("home_team", ""))
        if away_id not in teams_dict or home_id not in teams_dict:
            continue
        runs0 = int(gh.get("runs0") or 0)
        runs1 = int(gh.get("runs1") or 0)
        if runs0 == runs1:
            continue

        elo_away = base_elo[away_id] + elo_delta[away_id]
        elo_home = base_elo[home_id] + elo_delta[home_id] + 24.0  # home field advantage
        exp_away = 1.0 / (1.0 + 10.0 ** ((elo_home - elo_away) / 400.0))
        exp_home = 1.0 - exp_away

        actual_away = 1.0 if runs0 > runs1 else 0.0
        actual_home = 1.0 - actual_away

        # Margin of victory multiplier
        margin = abs(runs0 - runs1)
        mov_mult = (margin ** 0.4) if margin > 1 else 1.0

        elo_delta[away_id] += K * mov_mult * (actual_away - exp_away)
        elo_delta[home_id] += K * mov_mult * (actual_home - exp_home)
        games_played[away_id] += 1
        games_played[home_id] += 1

    active_deltas = [
        (teams_dict[tid], round(elo_delta[tid], 1))
        for tid in teams_dict
        if games_played[tid] > 0
    ]
    if not active_deltas:
        return None, None

    active_deltas.sort(key=lambda x: x[1])
    coldest = {"team": active_deltas[0][0], "change": active_deltas[0][1]}
    hottest = {"team": active_deltas[-1][0], "change": active_deltas[-1][1]}
    return hottest, coldest

def get_team_luck(league_url="https://statsplus.net/xfbl"):
    """
    Computes each MLB team's BaseRuns / Pythagorean expected record vs actual record
    directly from /api/playerbatstatsv2/, /api/playerpitchstatsv2/, and /api/lgdata/.
    """
    from collections import defaultdict

    lgdata = get_cached_lgdata(league_url)
    bat_rows, pitch_rows = get_cached_season_stats(league_url)
    if not lgdata or not bat_rows or not pitch_rows:
        return None, None

    primary_lid = 100
    for l in lgdata.get("leagues", []):
        if l.get("primary_league"):
            primary_lid = l.get("league_id", 100)
            break

    teams_dict = {
        str(t["team_id"]): f"{t.get('name', '')} {t.get('nickname', '')}".strip()
        for t in lgdata.get("teams", [])
        if t.get("league_id") == primary_lid
    }

    # Aggregate team offensive and pitching components for BaseRuns / Pythagenpat
    team_rs = defaultdict(int)
    team_ra = defaultdict(int)
    for r in bat_rows:
        if r.get("split_id") == "1" and r.get("level_id") == "1":
            tid = str(r.get("team_id", ""))
            if tid in teams_dict:
                team_rs[tid] += int(r.get("r") or 0)

    for r in pitch_rows:
        if r.get("split_id") == "1" and r.get("level_id") == "1":
            tid = str(r.get("team_id", ""))
            if tid in teams_dict:
                team_ra[tid] += int(r.get("r") or 0)

    teams_luck = []
    for st in lgdata.get("standings", []):
        tid = str(st.get("team_id", ""))
        if tid not in teams_dict:
            continue
        w = int(st.get("w") or 0)
        l = int(st.get("l") or 0)
        g = w + l
        if g < 10:
            continue
        rs = max(team_rs.get(tid, 0), 1)
        ra = max(team_ra.get(tid, 0), 1)

        # Pythagenpat exponent: ((RS + RA) / G) ^ 0.287
        rpg = (rs + ra) / g
        exp = max(1.6, min(2.1, rpg ** 0.287))
        exp_pct = (rs ** exp) / ((rs ** exp) + (ra ** exp))
        xw = int(round(exp_pct * g))
        xl = g - xw
        luck = w - xw

        teams_luck.append({
            "team": teams_dict[tid],
            "luck": luck,
            "actual": f"{w}-{l}",
            "expected": f"{xw}-{xl}",
        })

    if not teams_luck:
        return None, None

    teams_luck.sort(key=lambda x: x["luck"])
    unluckiest = teams_luck[0]
    luckiest = teams_luck[-1]
    return luckiest, unluckiest

def get_close_division_races(league_url="https://statsplus.net/xfbl"):
    data = get_cached_lgdata(league_url)
    if not data:
        return []
        
    primary_lid = 100
    for l in data.get('leagues', []):
        if l.get('primary_league'):
            primary_lid = l.get('league_id')
            break

    subleagues_dict = {
        sl['sub_league_id']: sl.get('abbr') or sl.get('name')
        for sl in data.get('subleagues', [])
        if sl.get('league_id') == primary_lid
    }

    divs_dict = {
        (d.get('sub_league_id', 0), d['division_id']): d.get('name', 'Unknown')
        for d in data.get('divisions', [])
        if d.get('league_id') == primary_lid
    }

    teams_dict = {
        t['team_id']: t
        for t in data.get('teams', [])
        if t.get('league_id') == primary_lid
    }

    primary_standings = [
        st for st in data.get('standings', [])
        if st.get('team_id') in teams_dict
    ]

    # Suppress pennant races during the first month/30 games of the season
    max_games = max((st.get('g', 0) for st in primary_standings), default=0)
    if max_games < 30:
        return []

    div_standings = {}
    for st in primary_standings:
        tid = st['team_id']
        team_info = teams_dict.get(tid)
        if not team_info:
            continue
        sl_id = team_info.get('sub_league_id', 0)
        did = team_info.get('division_id', 0)
        div_key = (sl_id, did)
        if div_key not in div_standings:
            div_standings[div_key] = []
        div_standings[div_key].append({
            'team_name': f"{team_info.get('name')} {team_info.get('nickname')}",
            'gb': st.get('gb', 0),
            'pos': st.get('pos', 99)
        })

    close_races = []
    for (sl_id, did), st_list in div_standings.items():
        div_base_name = divs_dict.get((sl_id, did), 'Unknown')
        sl_name = subleagues_dict.get(sl_id, '')
        full_div_name = f"{sl_name} {div_base_name}".strip() if sl_name else div_base_name

        st_list.sort(key=lambda x: x['pos'])
        if len(st_list) >= 2:
            first = st_list[0]
            second = st_list[1]
            gb_val = second['gb']
            if gb_val <= 2.0:
                is_tied = (gb_val == 0)
                gb_str = "0" if is_tied else str(gb_val)
                close_races.append({
                    "division": full_div_name,
                    "first_place": first['team_name'],
                    "second_place": second['team_name'],
                    "gb": gb_str,
                    "is_tied": is_tied
                })

    return close_races

def get_playoff_odds(league_url="https://statsplus.net/xfbl"):
    """
    Computes postseason projections and playoff odds directly from the StatsPlus API
    (/api/lgdata/, /api/playerbatstatsv2/, /api/playerpitchstatsv2/) via Monte Carlo
    simulation when the season is past the halfway mark (max games played >= 80).
    """
    from collections import defaultdict
    import random

    data = get_cached_lgdata(league_url)
    bat_rows, pitch_rows = get_cached_season_stats(league_url)
    if not data:
        return None

    primary_lid = 100
    for l in data.get("leagues", []):
        if l.get("primary_league"):
            primary_lid = l.get("league_id", 100)
            break

    subleagues_dict = {
        sl["sub_league_id"]: sl.get("abbr") or sl.get("name", "")
        for sl in data.get("subleagues", [])
        if sl.get("league_id") == primary_lid
    }

    teams_dict = {
        t["team_id"]: t
        for t in data.get("teams", [])
        if t.get("league_id") == primary_lid
    }

    standings = [st for st in data.get("standings", []) if st.get("team_id") in teams_dict]
    if not standings:
        return None

    max_gp = max((int(st.get("w") or 0) + int(st.get("l") or 0) for st in standings), default=0)
    if max_gp < 80:
        print(f"Season is not past halfway point yet (max games played: {max_gp} < 80). Skipping playoff odds.")
        return None

    # Calculate true-talent team win rate (blending actual win% and Pythagorean win% regressed toward .500)
    team_rs = defaultdict(int)
    team_ra = defaultdict(int)
    for r in bat_rows:
        if r.get("split_id") == "1" and r.get("level_id") == "1":
            tid = int(r.get("team_id") or 0)
            if tid in teams_dict:
                team_rs[tid] += int(r.get("r") or 0)
    for r in pitch_rows:
        if r.get("split_id") == "1" and r.get("level_id") == "1":
            tid = int(r.get("team_id") or 0)
            if tid in teams_dict:
                team_ra[tid] += int(r.get("r") or 0)

    teams_sim_info = []
    for st in standings:
        tid = st["team_id"]
        tinfo = teams_dict[tid]
        w = int(st.get("w") or 0)
        l = int(st.get("l") or 0)
        gp = w + l
        rem = max(0, 162 - gp)
        actual_pct = w / gp if gp > 0 else 0.5
        rs = max(team_rs.get(tid, 0), 1)
        ra = max(team_ra.get(tid, 0), 1)
        pyth_pct = (rs ** 1.83) / ((rs ** 1.83) + (ra ** 1.83)) if (rs > 1 or ra > 1) else actual_pct
        true_pct = 0.45 * pyth_pct + 0.35 * actual_pct + 0.20 * 0.500

        sl_id = tinfo.get("sub_league_id", 0)
        sl_name = subleagues_dict.get(sl_id, "AL" if sl_id == 0 else "NL")
        teams_sim_info.append({
            "tid": tid,
            "team": f"{tinfo.get('name', '')} {tinfo.get('nickname', '')}".strip(),
            "abbr": tinfo.get("abbr", ""),
            "sl_id": sl_id,
            "league": sl_name,
            "div_id": tinfo.get("division_id", 0),
            "w": w,
            "l": l,
            "gp": gp,
            "rem": rem,
            "true_pct": true_pct,
            "avg_w": w + rem * true_pct,
            "avg_l": l + rem * (1.0 - true_pct),
            "div_wins": 0,
            "po_wins": 0,
        })

    # Run 1,500 Monte Carlo simulations of the remaining schedule
    N_SIMS = 1500
    rng = random.Random(max_gp * 1000 + sum(t["w"] for t in teams_sim_info))
    by_sl = defaultdict(list)
    for t in teams_sim_info:
        by_sl[t["sl_id"]].append(t)

    for _ in range(N_SIMS):
        sim_w = {}
        for t in teams_sim_info:
            # Binomial approximation with normal jitter
            p = t["true_pct"]
            rem = t["rem"]
            if rem > 0:
                std = (rem * p * (1.0 - p)) ** 0.5
                add_w = int(round(rng.gauss(rem * p, std)))
                add_w = max(0, min(rem, add_w))
            else:
                add_w = 0
            # Small random tiebreaker
            sim_w[t["tid"]] = t["w"] + add_w + rng.random() * 0.01

        for sl_id, sl_teams in by_sl.items():
            by_div = defaultdict(list)
            for t in sl_teams:
                by_div[t["div_id"]].append(t)

            div_winners = set()
            for div_id, d_teams in by_div.items():
                winner = max(d_teams, key=lambda x: sim_w[x["tid"]])
                winner["div_wins"] += 1
                winner["po_wins"] += 1
                div_winners.add(winner["tid"])

            # Wild card winner(s) among non-division winners (1 wild card if 3 divisions)
            non_winners = [t for t in sl_teams if t["tid"] not in div_winners]
            if non_winners:
                non_winners.sort(key=lambda x: sim_w[x["tid"]], reverse=True)
                non_winners[0]["po_wins"] += 1

    al_bubble, al_contenders = [], []
    nl_bubble, nl_contenders = [], []

    for t in teams_sim_info:
        t["div_pct"] = (t["div_wins"] / N_SIMS) * 100.0
        t["po_pct"] = (t["po_wins"] / N_SIMS) * 100.0
        is_al = "AL" in t["league"] or "American" in t["league"] or t["sl_id"] == 0
        if 10.0 <= t["po_pct"] <= 90.0:
            (al_bubble if is_al else nl_bubble).append(t)
        elif t["po_pct"] > 90.0:
            (al_contenders if is_al else nl_contenders).append(t)

    al_bubble.sort(key=lambda x: x["po_pct"], reverse=True)
    nl_bubble.sort(key=lambda x: x["po_pct"], reverse=True)
    al_contenders.sort(key=lambda x: x["po_pct"], reverse=True)
    nl_contenders.sort(key=lambda x: x["po_pct"], reverse=True)

    return {
        "max_gp": max_gp,
        "AL": {"bubble": al_bubble, "contenders": al_contenders},
        "NL": {"bubble": nl_bubble, "contenders": nl_contenders},
    }

def get_notable_games(league_url="https://statsplus.net/xfbl", days_back=7):
    """
    Scans for noteworthy/weird games:
    - Blowouts (margin of 10+ runs)
    - High-scoring affairs (combined score 20+)
    - Individual players hitting 3+ HRs in a game
    Uses cached /api/atbats/, /api/players/, and /api/lgdata/ first, falling back to HTML scraping.
    """
    from urllib.parse import urljoin
    from collections import defaultdict

    current_date = get_league_current_date(league_url)
    cutoff_date = current_date - timedelta(days=days_back)

    # Attempt API calculation first using cached data
    try:
        rows = get_cached_atbats(league_url, cutoff_date, current_date)
        if rows:
            player_names, _, team_abbr_map, _, _ = _get_maps(league_url)
            notable = []
            seen_games = set()

            game_runs = defaultdict(lambda: defaultdict(int))
            player_game_hrs = defaultdict(int)

            for r in rows:
                if r.get('game_type') not in ('0', '3'):
                    continue
                gdate_str = r.get('date', '')
                try:
                    gdate = datetime.strptime(gdate_str, "%Y-%m-%d")
                    if not (cutoff_date <= gdate <= current_date):
                        continue
                except Exception:
                    continue

                gid = r.get('game_id')
                tid = r.get('team_id')
                pid = r.get('player_id')
                game_runs[gid][tid] += int(r.get('r') or 0)

                if r.get('result') == '9':  # Home run
                    player_game_hrs[(pid, gid, tid)] += 1

            # Check for 3+ HR games
            for (pid, gid, tid), hr_count in player_game_hrs.items():
                if hr_count >= 3:
                    pname = player_names.get(pid, f"Player {pid}")
                    tabbr = team_abbr_map.get(tid, '???')
                    other_teams = [team_abbr_map.get(t, '???') for t in game_runs[gid].keys() if t != tid]
                    opp = other_teams[0] if other_teams else '???'
                    box_url = f"{league_url.rstrip('/')}/reports/news/html/box_scores/game_box_{gid}.html"
                    notable.append({
                        "type": "multi_hr",
                        "text": f"💣 *{pname}* ({tabbr}) went deep *{hr_count} times* in a single game vs {opp}!",
                        "box_url": box_url
                    })

            # Check for blowouts and slugfests
            for gid, runs_by_team in game_runs.items():
                if len(runs_by_team) == 2 and gid not in seen_games:
                    seen_games.add(gid)
                    t_list = list(runs_by_team.keys())
                    t1, t2 = t_list[0], t_list[1]
                    r1, r2 = runs_by_team[t1], runs_by_team[t2]
                    abbr1 = team_abbr_map.get(t1, '???')
                    abbr2 = team_abbr_map.get(t2, '???')
                    margin = abs(r1 - r2)
                    total = r1 + r2
                    box_url = f"{league_url.rstrip('/')}/reports/news/html/box_scores/game_box_{gid}.html"

                    if margin >= 10:
                        notable.append({
                            "type": "blowout",
                            "text": f"💥 *Blowout Alert!* {abbr1} vs {abbr2} ended *{r1}-{r2}* — a {margin}-run shellacking.",
                            "box_url": box_url
                        })
                    elif total >= 20:
                        notable.append({
                            "type": "slugfest",
                            "text": f"⚡ *Run Fest!* {abbr1} vs {abbr2} combined for *{total} runs* in a wild {r1}-{r2} affair.",
                            "box_url": box_url
                        })

            seen_texts = set()
            deduped = []
            for item in notable:
                if item['text'] not in seen_texts:
                    seen_texts.add(item['text'])
                    deduped.append(item)
            return deduped[:5]
    except Exception as e:
        print(f"API notable games calculation error: {e}")

    # Fallback to HTML scraping
    bat_url = f"{league_url}/bestgames/bat/"
    session = get_statsplus_session()
    try:
        response = session.get(bat_url, timeout=15)
        soup = BeautifulSoup(response.text, 'html.parser')
        table = soup.find('table')
        if not table:
            return []
    except Exception:
        return []

    tbody = table.find('tbody')
    rows = tbody.find_all('tr') if tbody else table.find_all('tr')

    notable = []
    seen_games = set()

    for row in rows:
        cols = row.find_all('td')
        if not cols or len(cols) < 10:
            continue

        player_link = cols[1].find('a')
        player_name = player_link.text.strip() if player_link else cols[1].text.strip()
        team_abbr = cols[2].text.strip()
        opponent = cols[3].text.strip()
        date_str = cols[4].text.strip()
        game_date = parse_ootp_date(date_str)

        if not game_date or not (cutoff_date <= game_date <= current_date):
            continue

        box_link_tag = cols[5].find('a')
        score_text = box_link_tag.text.strip() if box_link_tag else ""
        box_url = urljoin(league_url, box_link_tag['href']) if box_link_tag else ""

        stats = [c.text.strip() for c in cols[6:]]
        if len(stats) >= 4:
            try:
                hr_count = int(stats[3])
                if hr_count >= 3:
                    notable.append({
                        "type": "multi_hr",
                        "text": f"💣 *{player_name}* ({team_abbr}) went deep *{hr_count} times* in a single game vs {opponent}!",
                        "box_url": box_url
                    })
            except (ValueError, IndexError):
                pass

        score_match = re.match(r'(\d+)-(\d+)', score_text)
        if score_match and box_url not in seen_games:
            seen_games.add(box_url)
            r1, r2 = int(score_match.group(1)), int(score_match.group(2))
            margin = abs(r1 - r2)
            total = r1 + r2
            if margin >= 10:
                notable.append({
                    "type": "blowout",
                    "text": f"💥 *Blowout Alert!* {team_abbr} vs {opponent} ended *{score_text}* — a {margin}-run shellacking.",
                    "box_url": box_url
                })
            elif total >= 20:
                notable.append({
                    "type": "slugfest",
                    "text": f"⚡ *Run Fest!* {team_abbr} vs {opponent} combined for *{total} runs* in a wild {score_text} affair.",
                    "box_url": box_url
                })

    seen_texts = set()
    deduped = []
    for item in notable:
        if item['text'] not in seen_texts:
            seen_texts.add(item['text'])
            deduped.append(item)

    return deduped[:5]


def get_api_oddities(league_url="https://statsplus.net/xfbl"):
    """
    Uses the StatsPlus CSV API to mine for funny, odd, and noteworthy
    season-level stats. Returns a list of oddity dicts with 'text' and 'emoji'.
    Only uses split_id=1 (overall stats).
    """
    player_rows = get_cached_players(league_url, active_only=False)
    player_names = {}
    for r in player_rows:
        pid = r.get('ID', '').strip()
        first = r.get('First Name', '').strip()
        last = r.get('Last Name', '').strip()
        if pid:
            player_names[pid] = f"{first} {last}".strip()

    team_rows = get_cached_teams_csv(league_url)
    team_display = {}
    for r in team_rows:
        tid = r.get('ID', '').strip()
        name = r.get('Name', '').strip()
        if tid:
            team_display[tid] = name

    def pname(pid, tid):
        return player_names.get(str(pid), f"Player#{pid}"), team_display.get(str(tid), f"T{tid}")

    bat_rows, pitch_rows = get_cached_season_stats(league_url)
    bat_overall = [r for r in bat_rows if r.get('split_id') == '1' and r.get('level_id', '1') == '1']

    all_oddities = {}

    def safe_int(d, key, default=0):
        try: return int(d.get(key, default) or default)
        except: return default

    def safe_float(d, key, default=0.0):
        try: return float(d.get(key, default) or default)
        except: return default

    def calc_avg(r):
        h = safe_int(r, 'h')
        ab = safe_int(r, 'ab')
        return h / ab if ab > 0 else 0.0

    def calc_babip(r):
        h = safe_int(r, 'h')
        hr = safe_int(r, 'hr')
        ab = safe_int(r, 'ab')
        k = safe_int(r, 'k')
        sf = safe_int(r, 'sf')
        denom = ab - k - hr + sf
        return (h - hr) / denom if denom > 0 else 0.0

    # Adaptive sample size thresholds for early season / Opening Day
    max_pa = max((safe_int(r, 'pa') for r in bat_overall), default=0)
    min_pa = 100 if max_pa >= 100 else max(3, int(max_pa * 0.7))
    min_gdp = 5 if max_pa >= 100 else 1
    min_hr_ab_ab = 50 if max_pa >= 100 else 5
    min_hr_ab_hr = 5 if max_pa >= 100 else 1
    min_raw_hr = 5 if max_pa >= 100 else 1
    min_sb = 5 if max_pa >= 100 else 1
    min_3b = 2 if max_pa >= 100 else 1
    min_rbi = 15 if max_pa >= 100 else 2
    min_cs = 3 if max_pa >= 100 else 1

    qualified_bat = [r for r in bat_overall if safe_int(r, 'pa') >= min_pa]

    if qualified_bat:
        k_king = max(qualified_bat, key=lambda r: safe_int(r, 'k') / max(safe_int(r, 'pa'), 1))
        k_rate = safe_int(k_king, 'k') / max(safe_int(k_king, 'pa'), 1)
        name, team = pname(k_king['player_id'], k_king['team_id'])
        all_oddities["k_rate_king"] = {
            "text": f"🎳 *K-Rate King:* {name} ({team}) strikes out *{k_rate:.0%}* of the time — {safe_int(k_king, 'k')} Ks in {safe_int(k_king, 'pa')} PA.",
            "emoji": "🎳", "winner_id": k_king['player_id']
        }

        bb_king = max(qualified_bat, key=lambda r: safe_int(r, 'bb') / max(safe_int(r, 'pa'), 1))
        bb_rate = safe_int(bb_king, 'bb') / max(safe_int(bb_king, 'pa'), 1)
        name, team = pname(bb_king['player_id'], bb_king['team_id'])
        all_oddities["walk_machine"] = {
            "text": f"🚶 *Walk Machine:* {name} ({team}) draws a walk *{bb_rate:.0%}* of the time — {safe_int(bb_king, 'bb')} BBs this season.",
            "emoji": "🚶", "winner_id": bb_king['player_id']
        }

        gdp_leaders = [r for r in bat_overall if safe_int(r, 'gdp') >= min_gdp]
        if gdp_leaders:
            gdp_king = max(gdp_leaders, key=lambda r: safe_int(r, 'gdp'))
            name, team = pname(gdp_king['player_id'], gdp_king['team_id'])
            all_oddities["gidp_machine"] = {
                "text": f"💀 *Double Play Machine:* {name} ({team}) has grounded into *{safe_int(gdp_king, 'gdp')} double plays* — the league's premier rally killer.",
                "emoji": "💀", "winner_id": gdp_king['player_id']
            }

        hr_rate_leaders = [r for r in bat_overall if safe_int(r, 'ab') >= min_hr_ab_ab and safe_int(r, 'hr') >= min_hr_ab_hr]
        if hr_rate_leaders:
            hr_king = max(hr_rate_leaders, key=lambda r: safe_int(r, 'hr') / max(safe_int(r, 'ab'), 1))
            ab_per_hr = safe_int(hr_king, 'ab') / safe_int(hr_king, 'hr')
            name, team = pname(hr_king['player_id'], hr_king['team_id'])
            all_oddities["hr_freak"] = {
                "text": f"💣 *HR Freak:* {name} ({team}) is going yard every *{ab_per_hr:.1f} ABs* with {safe_int(hr_king, 'hr')} homers already.",
                "emoji": "💣", "winner_id": hr_king['player_id']
            }

        hr_raw_leaders = [r for r in bat_overall if safe_int(r, 'hr') >= min_raw_hr]
        if hr_raw_leaders:
            hr_raw_king = max(hr_raw_leaders, key=lambda r: safe_int(r, 'hr'))
            name, team = pname(hr_raw_king['player_id'], hr_raw_king['team_id'])
            all_oddities["hr_king"] = {
                "text": f"🏡 *Home Run King:* {name} ({team}) leads the league with *{safe_int(hr_raw_king, 'hr')} home runs* on the season.",
                "emoji": "🏡", "winner_id": hr_raw_king['player_id']
            }

        sb_leaders = [r for r in bat_overall if safe_int(r, 'sb') >= min_sb]
        if sb_leaders:
            sb_king = max(sb_leaders, key=lambda r: safe_int(r, 'sb'))
            cs = safe_int(sb_king, 'cs')
            sb = safe_int(sb_king, 'sb')
            pct = sb / max(sb + cs, 1)
            name, team = pname(sb_king['player_id'], sb_king['team_id'])
            all_oddities["speed_demon"] = {
                "text": f"🔫 *Speed Demon:* {name} ({team}) leads the league with *{sb} steals* (success rate: {pct:.0%}).",
                "emoji": "🔫", "winner_id": sb_king['player_id']
            }

        war_leaders = [r for r in bat_overall if safe_float(r, 'war') > 0]
        if war_leaders:
            war_king = max(war_leaders, key=lambda r: safe_float(r, 'war'))
            name, team = pname(war_king['player_id'], war_king['team_id'])
            all_oddities["bat_war_leader"] = {
                "text": f"🏆 *Position Player WAR Leader:* {name} ({team}) paces the league with *{safe_float(war_king, 'war'):.1f} WAR*.",
                "emoji": "🏆", "winner_id": war_king['player_id']
            }

        wpa_losers = [r for r in bat_overall if safe_float(r, 'wpa') < -0.2 and safe_int(r, 'pa') >= min_pa]
        if wpa_losers:
            wpa_loser = min(wpa_losers, key=lambda r: safe_float(r, 'wpa'))
            name, team = pname(wpa_loser['player_id'], wpa_loser['team_id'])
            all_oddities["clutch_kryptonite"] = {
                "text": f"📉 *Clutch Kryptonite:* {name} ({team}) has been absolutely *crushing his team's win probability* with {safe_float(wpa_loser, 'wpa'):.2f} WPA.",
                "emoji": "📉", "winner_id": wpa_loser['player_id']
            }

        avg_losers = [r for r in qualified_bat if calc_avg(r) > 0]
        if avg_losers:
            avg_loser = min(avg_losers, key=calc_avg)
            name, team = pname(avg_loser['player_id'], avg_loser['team_id'])
            avg_val = calc_avg(avg_loser)
            avg_str = f"{avg_val:.3f}".lstrip('0')
            all_oddities["human_out"] = {
                "text": f"🧱 *Human Out:* {name} ({team}) is hitting a paltry *{avg_str}* — making outs is basically his full-time job.",
                "emoji": "🧱", "winner_id": avg_loser['player_id']
            }

        contact_leaders = sorted(qualified_bat, key=lambda r: safe_int(r, 'k') / max(safe_int(r, 'pa'), 1))
        if contact_leaders:
            contact_king = contact_leaders[0]
            k_rate_low = safe_int(contact_king, 'k') / max(safe_int(contact_king, 'pa'), 1)
            name, team = pname(contact_king['player_id'], contact_king['team_id'])
            all_oddities["contact_machine"] = {
                "text": f"🎯 *Contact Machine:* {name} ({team}) only strikes out *{k_rate_low:.0%}* of the time — {safe_int(contact_king, 'k')} Ks in {safe_int(contact_king, 'pa')} PA. Old-school baseball.",
                "emoji": "🎯", "winner_id": contact_king['player_id']
            }

        triple_leaders = [r for r in bat_overall if safe_int(r, 't') >= min_3b]
        if triple_leaders:
            triple_king = max(triple_leaders, key=lambda r: safe_int(r, 't'))
            name, team = pname(triple_king['player_id'], triple_king['team_id'])
            all_oddities["ghost_runner"] = {
                "text": f"👻 *Ghost Runner:* {name} ({team}) leads the league with *{safe_int(triple_king, 't')} triples* — the rarest hit in baseball.",
                "emoji": "👻", "winner_id": triple_king['player_id']
            }

        babip_leaders = [r for r in qualified_bat if calc_babip(r) > 0]
        if babip_leaders:
            babip_king = max(babip_leaders, key=calc_babip)
            name, team = pname(babip_king['player_id'], babip_king['team_id'])
            all_oddities["babip_winner"] = {
                "text": f"🍀 *BABIP Lottery Winner:* {name} ({team}) is batting on a *.{int(calc_babip(babip_king) * 1000):03d} BABIP* — the baseball gods are smiling on this one.",
                "emoji": "🍀", "winner_id": babip_king['player_id']
            }

            babip_victim = min(babip_leaders, key=calc_babip)
            name, team = pname(babip_victim['player_id'], babip_victim['team_id'])
            all_oddities["babip_victim"] = {
                "text": f"🤡 *BABIP Victim:* {name} ({team}) is stranded at *.{int(calc_babip(babip_victim) * 1000):03d} BABIP* — every ball finds a glove.",
                "emoji": "🤡", "winner_id": babip_victim['player_id']
            }

        rbi_dep = [r for r in bat_overall if safe_int(r, 'rbi') >= min_rbi and safe_int(r, 'hr') <= 3]
        if rbi_dep:
            rbi_king = max(rbi_dep, key=lambda r: safe_int(r, 'rbi'))
            name, team = pname(rbi_king['player_id'], rbi_king['team_id'])
            all_oddities["rbi_dependent"] = {
                "text": f"🤝 *RBI Dependent:* {name} ({team}) has driven in *{safe_int(rbi_king, 'rbi')} runs* with only *{safe_int(rbi_king, 'hr')} home runs* — a pure product of his lineup.",
                "emoji": "🤝", "winner_id": rbi_king['player_id']
            }

        cs_leaders = [r for r in bat_overall if safe_int(r, 'cs') >= min_cs]
        if cs_leaders:
            cs_king = max(cs_leaders, key=lambda r: safe_int(r, 'cs'))
            sb = safe_int(cs_king, 'sb')
            cs = safe_int(cs_king, 'cs')
            name, team = pname(cs_king['player_id'], cs_king['team_id'])
            all_oddities["caught_stealing"] = {
                "text": f"🏃 *Caught Red-Handed:* {name} ({team}) has been thrown out *{cs} times* stealing — {sb} successes, {cs} failures. Slow down!",
                "emoji": "🏃", "winner_id": cs_king['player_id']
            }

        if len(qualified_bat) >= 3:
            sorted_by_k = sorted(qualified_bat, key=lambda r: safe_int(r, 'k'), reverse=True)
            sorted_by_gdp = sorted(qualified_bat, key=lambda r: safe_int(r, 'gdp'), reverse=True)
            top_k_ids = {r['player_id'] for r in sorted_by_k[:5]}
            top_gdp_ids = {r['player_id'] for r in sorted_by_gdp[:5]}
            cursed_ids = top_k_ids & top_gdp_ids
            if cursed_ids:
                cursed_pid = list(cursed_ids)[0]
                cursed = next(r for r in qualified_bat if r['player_id'] == cursed_pid)
                name, team = pname(cursed['player_id'], cursed['team_id'])
                all_oddities["statistically_cursed"] = {
                    "text": f"😈 *Statistically Cursed:* {name} ({team}) ranks top-5 in *both* strikeouts ({safe_int(cursed, 'k')} Ks) AND double plays grounded into ({safe_int(cursed, 'gdp')} GIDPs). An absolute menace to offenses.",
                    "emoji": "😈", "winner_id": cursed['player_id']
                }

    pitch_overall = [r for r in pitch_rows if r.get('split_id') == '1' and r.get('level_id', '1') == '1']

    max_sp_ip = max((safe_float(r, 'ip') for r in pitch_overall), default=0.0)
    min_sp_ip = 20.0 if max_sp_ip >= 20.0 else max(1.0, max_sp_ip * 0.5)
    min_sp_gs = 3 if max_sp_ip >= 20.0 else 1

    max_rp_ip = max((safe_float(r, 'ip') for r in pitch_overall if safe_int(r, 'gs') == 0), default=0.0)
    min_rp_ip = 10.0 if max_rp_ip >= 10.0 else max(1.0, max_rp_ip * 0.3)

    min_qs = 3 if max_sp_ip >= 20.0 else 1
    min_hr_allowed = 3 if max_sp_ip >= 20.0 else 1
    min_save_opp = 3 if max_sp_ip >= 20.0 else 1
    min_bs = 2 if max_sp_ip >= 20.0 else 1

    qualified_sp = [r for r in pitch_overall if safe_float(r, 'ip') >= min_sp_ip and safe_int(r, 'gs') >= min_sp_gs]
    qualified_rp = [r for r in pitch_overall if safe_float(r, 'ip') >= min_rp_ip and safe_int(r, 'gs') == 0]

    if qualified_sp:
        k_bf_king = max(qualified_sp, key=lambda r: safe_int(r, 'k') / max(safe_int(r, 'bf'), 1))
        k_bf_rate = safe_int(k_bf_king, 'k') / max(safe_int(k_bf_king, 'bf'), 1)
        name, team = pname(k_bf_king['player_id'], k_bf_king['team_id'])
        all_oddities["swing_miss_sp"] = {
            "text": f"🔥 *Swing-and-Miss SP:* {name} ({team}) is fanning *{k_bf_rate:.0%}* of batters faced — a terrifying arm.",
            "emoji": "🔥", "winner_id": k_bf_king['player_id']
        }

        war_leaders_p = [r for r in pitch_overall if safe_float(r, 'war') > 0]
        if war_leaders_p:
            war_king_p = max(war_leaders_p, key=lambda r: safe_float(r, 'war'))
            name, team = pname(war_king_p['player_id'], war_king_p['team_id'])
            all_oddities["pitch_war_leader"] = {
                "text": f"🎖️ *Pitcher WAR Leader:* {name} ({team}) leads all arms with *{safe_float(war_king_p, 'war'):.1f} WAR*.",
                "emoji": "🎖️", "winner_id": war_king_p['player_id']
            }

        bb_problem = max(qualified_sp, key=lambda r: safe_int(r, 'bb') / max(safe_float(r, 'ip'), 1))
        bb_per_9 = safe_int(bb_problem, 'bb') / max(safe_float(bb_problem, 'ip'), 1) * 9
        name, team = pname(bb_problem['player_id'], bb_problem['team_id'])
        all_oddities["control_issues"] = {
            "text": f"😬 *Control Issues:* {name} ({team}) is issuing *{bb_per_9:.1f} walks per 9 innings* — somebody get them the strike zone.",
            "emoji": "😬", "winner_id": bb_problem['player_id']
        }

        kb_ratio_leaders = [r for r in qualified_sp if safe_int(r, 'bb') > 0]
        if kb_ratio_leaders:
            kb_king = max(kb_ratio_leaders, key=lambda r: safe_int(r, 'k') / max(safe_int(r, 'bb'), 1))
            kb_ratio = safe_int(kb_king, 'k') / max(safe_int(kb_king, 'bb'), 1)
            name, team = pname(kb_king['player_id'], kb_king['team_id'])
            all_oddities["kb_ratio_king"] = {
                "text": f"🧊 *K/BB Ratio King:* {name} ({team}) strikes out *{kb_ratio:.1f} batters for every walk* — the gold standard of command.",
                "emoji": "🧊", "winner_id": kb_king['player_id']
            }

        def calc_era(r):
            ip = safe_float(r, 'ip')
            er = safe_float(r, 'er')
            return round((er / ip) * 9, 2) if ip > 0 else 0.0

        era_losers = [r for r in qualified_sp if calc_era(r) > 0]
        if era_losers:
            gas_can = max(era_losers, key=calc_era)
            name, team = pname(gas_can['player_id'], gas_can['team_id'])
            all_oddities["gas_can"] = {
                "text": f"🛢️ *Gas Can:* {name} ({team}) is sporting a *{calc_era(gas_can):.2f} ERA* — every run scores when this one takes the mound.",
                "emoji": "🛢️", "winner_id": gas_can['player_id']
            }

        gb_leaders = [r for r in qualified_sp if safe_int(r, 'fb') > 0]
        if gb_leaders:
            gb_king = max(gb_leaders, key=lambda r: safe_int(r, 'gb') / max(safe_int(r, 'fb'), 1))
            go_ao = safe_int(gb_king, 'gb') / max(safe_int(gb_king, 'fb'), 1)
            name, team = pname(gb_king['player_id'], gb_king['team_id'])
            all_oddities["worm_killer"] = {
                "text": f"🏔️ *Worm Killer:* {name} ({team}) has a *{go_ao:.2f} GB/FB ratio* — batters just keep beating it into the dirt.",
                "emoji": "🏔️", "winner_id": gb_king['player_id']
            }

        qs_leaders = [r for r in qualified_sp if safe_int(r, 'qs') >= min_qs]
        if qs_leaders:
            qs_king = max(qs_leaders, key=lambda r: safe_int(r, 'qs'))
            name, team = pname(qs_king['player_id'], qs_king['team_id'])
            gs = safe_int(qs_king, 'gs')
            qs = safe_int(qs_king, 'qs')
            all_oddities["mr_reliable"] = {
                "text": f"🎭 *Mr. Reliable:* {name} ({team}) has delivered *{qs} quality starts* in {gs} outings — the definition of a workhorse.",
                "emoji": "🎭", "winner_id": qs_king['player_id']
            }

        hr_allowed_leaders = [r for r in qualified_sp if safe_int(r, 'hra') >= min_hr_allowed]
        if hr_allowed_leaders:
            hr_allowed_king = max(hr_allowed_leaders, key=lambda r: safe_int(r, 'hra'))
            name, team = pname(hr_allowed_king['player_id'], hr_allowed_king['team_id'])
            all_oddities["hr_derby_pitcher"] = {
                "text": f"😤 *Home Run Derby Pitcher:* {name} ({team}) has surrendered *{safe_int(hr_allowed_king, 'hra')} home runs* — opposing hitters love facing this one.",
                "emoji": "😤", "winner_id": hr_allowed_king['player_id']
            }

        ip_king = max(qualified_sp, key=lambda r: safe_float(r, 'ip'))
        name, team = pname(ip_king['player_id'], ip_king['team_id'])
        all_oddities["iron_man"] = {
            "text": f"📦 *Iron Man:* {name} ({team}) leads all starters with *{safe_float(ip_king, 'ip'):.1f} innings pitched* — the manager's best friend.",
            "emoji": "📦", "winner_id": ip_king['player_id']
        }

        if qualified_rp:
            rp_workhorse = max(qualified_rp, key=lambda r: safe_int(r, 'g'))
            name, team = pname(rp_workhorse['player_id'], rp_workhorse['team_id'])
            all_oddities["bullpen_burnout"] = {
                "text": f"🎪 *Bullpen Burnout:* {name} ({team}) has appeared in *{safe_int(rp_workhorse, 'g')} games* out of the pen — their arm must be held together with tape.",
                "emoji": "🎪", "winner_id": rp_workhorse['player_id']
            }

    if qualified_rp:
        sv_leaders = [r for r in qualified_rp if (safe_int(r, 's') + safe_int(r, 'bs')) >= min_save_opp]
        if sv_leaders:
            sv_king = max(sv_leaders, key=lambda r: safe_int(r, 's') / max(safe_int(r, 's') + safe_int(r, 'bs'), 1))
            svs = safe_int(sv_king, 's')
            bsv = safe_int(sv_king, 'bs')
            name, team = pname(sv_king['player_id'], sv_king['team_id'])
            if svs > 0:
                all_oddities["closer_of_year"] = {
                    "text": f"🔒 *Closer of the Year:* {name} ({team}) has been *{svs}-for-{svs+bsv}* in save opportunities.",
                    "emoji": "🔒", "winner_id": sv_king['player_id']
                }

        bs_leaders = [r for r in qualified_rp if safe_int(r, 'bs') >= min_bs]
        if bs_leaders:
            bs_king = max(bs_leaders, key=lambda r: safe_int(r, 'bs'))
            name, team = pname(bs_king['player_id'], bs_king['team_id'])
            all_oddities["blown_save_king"] = {
                "text": f"💥 *Blown Save King:* {name} ({team}) has blown *{safe_int(bs_king, 'bs')} saves* this season — opposing managers love seeing this reliever jog in.",
                "emoji": "💥", "winner_id": bs_king['player_id']
            }

    import random
    import json

    state_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "state.json")
    try:
        with open(state_path, "r") as f:
            state = json.load(f)
    except Exception:
        state = {}

    recently_shown = set(state.get("last_oddity_categories", []))
    last_winners = state.get("last_oddity_winners", {})

    available_keys = list(all_oddities.keys())
    fresh_keys = [k for k in available_keys if k not in recently_shown]
    stale_keys = [k for k in available_keys if k in recently_shown]

    def pick_key(pool):
        repeat_winner_keys = [k for k in pool if all_oddities[k].get("winner_id") == last_winners.get(k)]
        non_repeat_keys = [k for k in pool if k not in repeat_winner_keys]
        return non_repeat_keys if non_repeat_keys else pool

    random.shuffle(fresh_keys)
    random.shuffle(stale_keys)

    fresh_to_use = pick_key(fresh_keys)
    stale_to_use = pick_key(stale_keys)
    ordered_keys = fresh_to_use + stale_to_use
    chosen_keys = ordered_keys[:5]

    new_winners = {k: all_oddities[k].get("winner_id") for k in chosen_keys}
    state["last_oddity_categories"] = chosen_keys
    state["last_oddity_winners"] = {**last_winners, **new_winners}
    try:
        with open(state_path, "w") as f:
            json.dump(state, f, indent=2)
    except Exception as e:
        print(f"Warning: Could not save state: {e}")

    return [all_oddities[k] for k in chosen_keys]


def get_sim_analytics(league_url="https://statsplus.net/xfbl"):
    """
    Returns analytics data for the Sim Analytics section, computed 100% via API.
    Rotates between three different storyline modes each sim:
      - Mode 0: Standard — Who's Hot/Cold (ELO) + Luckiest/Unluckiest (BaseRuns)
      - Mode 1: Rankings Shakeup — Biggest ELO movers + Luckiest/Unluckiest
      - Mode 2: Luck Focus — Lead with BaseRuns luck, Hot/Cold as secondary context
    State is persisted in state.json.
    """
    import json

    state_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "state.json")
    try:
        with open(state_path, "r") as f:
            state = json.load(f)
    except Exception:
        state = {}

    current_mode = state.get("analytics_mode", 0)
    next_mode = (current_mode + 1) % 3
    state["analytics_mode"] = next_mode
    try:
        with open(state_path, "w") as f:
            json.dump(state, f, indent=2)
    except Exception as e:
        print(f"Warning: Could not save analytics state: {e}")

    hottest, coldest = get_team_momentum(league_url)
    luckiest, unluckiest = get_team_luck(league_url)

    if current_mode == 0:
        return {
            "mode": "standard",
            "hottest": hottest,
            "coldest": coldest,
            "luckiest": luckiest,
            "unluckiest": unluckiest,
        }
    elif current_mode == 1:
        return {
            "mode": "rankings_shakeup",
            "biggest_gainer": hottest,
            "biggest_loser": coldest,
            "luckiest": luckiest,
            "unluckiest": unluckiest,
        }
    else:
        return {
            "mode": "luck_focus",
            "hottest": hottest,
            "coldest": coldest,
            "luckiest": luckiest,
            "unluckiest": unluckiest,
        }

PLAYOFF_KEYWORDS = [
    "wild card", "wildcard", "division series", "alds", "nlds",
    "championship series", "alcs", "nlcs", "world series",
    "league championship", "league division",
    "playoff", "postseason", "october baseball",
]

def get_season_phase(league_url, best_pitcher=None, best_batter=None):
    """
    Determines the current season phase: 'regular', 'postseason', 'spring_training', or 'offseason'.
    Uses cached /api/lgdata/ to read the exact league_state.
    """
    try:
        data = get_cached_lgdata(league_url)
        if data:
            for league in data.get("leagues", []):
                if league.get("primary_league"):
                    state = league.get("state")
                    # 0=Preseason, 1=Spring Training, 2=Regular, 3=Playoffs, 4=Offseason
                    if state == 3:
                        return "postseason"
                    elif state in [0, 1]:
                        return "spring_training"
                    elif state == 4:
                        return "offseason"
                    else:
                        return "regular"
            if data.get("leagues"):
                state = data["leagues"][0].get("state")
                if state == 3:
                    return "postseason"
                elif state in [0, 1]:
                    return "spring_training"
                elif state == 4:
                    return "offseason"
                else:
                    return "regular"
    except Exception as e:
        print(f"Error fetching season phase from API: {e}")

    return "regular"


def get_streaks_and_records(league_url, state, days_back=7):
    """
    Detects active team winning/losing streaks, multi-sim ELO streaks, and season stat records
    using 100% StatsPlus API data (/api/lgdata/, /api/gamehistory/, /api/playerbatstatsv2/, /api/playerpitchstatsv2/).
    """
    from collections import defaultdict

    callouts = []
    current_date = get_league_current_date(league_url)
    cutoff_date = current_date - timedelta(days=days_back)

    # --- 1. Team Streaks via /api/lgdata/ & /api/gamehistory/ ---
    try:
        lgdata = get_cached_lgdata(league_url)
        gh_rows = get_cached_gamehistory(league_url, cutoff_date, current_date)
        primary_lid = 100
        for l in lgdata.get("leagues", []):
            if l.get("primary_league"):
                primary_lid = l.get("league_id", 100)
                break

        teams_dict = {
            str(t["team_id"]): f"{t.get('name', '')} {t.get('nickname', '')}".strip()
            for t in lgdata.get("teams", [])
            if t.get("league_id") == primary_lid
        }

        # Check active single-game winning/losing streaks from /api/lgdata/ standings
        hot_game_streaks = []
        cold_game_streaks = []
        for st in lgdata.get("standings", []):
            tid = str(st.get("team_id", ""))
            if tid not in teams_dict:
                continue
            stk = int(st.get("streak") or 0)
            if stk >= 6:
                hot_game_streaks.append((stk, teams_dict[tid]))
            elif stk <= -6:
                cold_game_streaks.append((abs(stk), teams_dict[tid]))

        if hot_game_streaks:
            hot_game_streaks.sort(reverse=True)
            stk, tname = hot_game_streaks[0]
            callouts.append(f"🔥 *Red Hot:* The *{tname}* have won *{stk} straight games*!")
        if cold_game_streaks:
            cold_game_streaks.sort(reverse=True)
            stk, tname = cold_game_streaks[0]
            callouts.append(f"🧊 *Freefall:* The *{tname}* have dropped *{stk} games in a row*.")

        # Update multi-sim ELO history in state.json (only once per game date)
        last_streak_date = state.get("last_streak_date")
        date_str = current_date.strftime("%Y-%m-%d")
        elo_history = state.get("elo_history", {})

        if gh_rows and last_streak_date != date_str:
            sim_net = defaultdict(float)
            for gh in gh_rows:
                if gh.get("game_type") != "0":
                    continue
                a_id = str(gh.get("away_team", ""))
                h_id = str(gh.get("home_team", ""))
                r0 = int(gh.get("runs0") or 0)
                r1 = int(gh.get("runs1") or 0)
                if a_id in teams_dict and h_id in teams_dict and r0 != r1:
                    delta = round((r0 - r1) * 1.5, 1)
                    sim_net[a_id] += delta
                    sim_net[h_id] -= delta

            for tid, tname in teams_dict.items():
                if tid in sim_net:
                    hist = elo_history.get(tname, [])
                    hist.append(round(sim_net[tid], 1))
                    elo_history[tname] = hist[-4:]
            state["elo_history"] = elo_history
            state["last_streak_date"] = date_str

        for team, history in elo_history.items():
            if len(history) >= 3:
                recent = history[-3:]
                if all(x > 0 for x in recent):
                    streak_len = 0
                    for x in reversed(history):
                        if x > 0:
                            streak_len += 1
                        else:
                            break
                    if streak_len >= 3:
                        callouts.append(f"📈 *Multi-Sim Surge:* The *{team}* have posted positive momentum in *{streak_len} straight sims*.")
                elif all(x < 0 for x in recent):
                    streak_len = 0
                    for x in reversed(history):
                        if x < 0:
                            streak_len += 1
                        else:
                            break
                    if streak_len >= 3:
                        callouts.append(f"📉 *Multi-Sim Slide:* The *{team}* have lost ground in *{streak_len} straight sims*.")
    except Exception as e:
        print(f"Error computing streaks from API: {e}")

    # --- 2. Season Records via cached batting/pitching API ---
    def safe_int(d, key, default=0):
        try: return int(d.get(key, default) or default)
        except: return default

    def safe_float(d, key, default=0.0):
        try: return float(d.get(key, default) or default)
        except: return default

    player_names, _, _, _, _ = _get_maps(league_url)
    def pname(pid):
        return player_names.get(str(pid), f"Player#{pid}")

    bat_rows, pitch_rows = get_cached_season_stats(league_url)
    bat_overall = [r for r in bat_rows if r.get('split_id') == '1' and r.get('level_id', '1') == '1']
    pitch_overall = [r for r in pitch_rows if r.get('split_id') == '1' and r.get('level_id', '1') == '1']

    season_records = state.get("season_records", {})

    def check_record(key, player_name, value, emoji, label, higher_is_better=True):
        prev = season_records.get(key, {})
        prev_val = prev.get("value")
        is_new = prev_val is None or (higher_is_better and value > prev_val) or (not higher_is_better and value < prev_val)
        if is_new:
            season_records[key] = {"player": player_name, "value": value}
            if prev_val is not None:
                return f"{emoji} *New Season High!* {player_name} now leads the league in {label} with *{value}* (previous best: {prev_val})."
        return None

    if bat_overall:
        hr_leader = max(bat_overall, key=lambda r: safe_int(r, 'hr'))
        hr_val = safe_int(hr_leader, 'hr')
        if hr_val > 0:
            note = check_record("most_hr", pname(hr_leader['player_id']), hr_val, "💣", "home runs")
            if note:
                callouts.append(note)

    if pitch_overall:
        k_leader = max(pitch_overall, key=lambda r: safe_int(r, 'k'))
        k_val = safe_int(k_leader, 'k')
        if k_val > 0:
            note = check_record("most_k_pitcher", pname(k_leader['player_id']), k_val, "🔥", "strikeouts (pitcher)")
            if note:
                callouts.append(note)

    def calc_era(r):
        ip = safe_float(r, 'ip')
        er = safe_float(r, 'er')
        return round((er / ip) * 9, 2) if ip > 0 else 0.0

    qualified_sp = [r for r in pitch_overall if safe_float(r, 'ip') >= 30]
    if qualified_sp:
        era_leader = min(qualified_sp, key=lambda r: calc_era(r) if calc_era(r) > 0 else 99)
        era_val = calc_era(era_leader)
        if era_val > 0:
            note = check_record("best_era", pname(era_leader['player_id']), era_val, "🎯", "ERA (lowest)", higher_is_better=False)
            if note:
                callouts.append(note)

    state["season_records"] = season_records
    return callouts[:3]


def get_milestone_countdowns(league_url):
    """
    Scans multi-year player career stats from the StatsPlus API to find active MLB
    players approaching major career milestones.
    Returns a list of countdown strings, capped at 4.
    """
    HIT_MILESTONES = [1000, 1500, 2000, 2500, 3000, 3500]
    HR_MILESTONES = [200, 300, 400, 500, 600, 700]
    RBI_MILESTONES = [1000, 1500, 2000]
    WIN_MILESTONES = [150, 200, 250, 300]
    K_MILESTONES = [1000, 1500, 2000, 2500, 3000]
    SAVE_MILESTONES = [200, 300, 400, 500]

    active_players = get_cached_players(league_url, active_only=True)
    active_mlb = {}
    _, _, team_abbr_map, _, _ = _get_maps(league_url)
    for p in active_players:
        pid = p.get("ID", "").strip()
        if pid and p.get("Level") == "1":
            name = f"{p.get('First Name', '').strip()} {p.get('Last Name', '').strip()}".strip()
            tid = p.get("Team ID", "").strip()
            tabbr = team_abbr_map.get(tid, "")
            active_mlb[pid] = f"{name} ({tabbr})" if tabbr else name

    career_bat, career_pitch = get_cached_career_stats(league_url)
    countdowns = []

    for pid, display_name in active_mlb.items():
        cb = career_bat.get(pid)
        if cb:
            hits = cb["h"]
            for m in HIT_MILESTONES:
                rem = m - hits
                if 0 < rem <= 25:
                    countdowns.append((rem / 25.0, f"🎯 *Milestone Watch:* *{display_name}* needs just *{rem} more hit{'s' if rem != 1 else ''}* to reach *{m:,} career hits* (currently at {hits:,})."))
                    break

            hrs = cb["hr"]
            for m in HR_MILESTONES:
                rem = m - hrs
                if 0 < rem <= 8:
                    countdowns.append((rem / 8.0, f"💣 *Milestone Watch:* *{display_name}* is *{rem} home run{'s' if rem != 1 else ''} away* from *{m:,} career HR* (currently at {hrs:,})."))
                    break

            rbis = cb["rbi"]
            for m in RBI_MILESTONES:
                rem = m - rbis
                if 0 < rem <= 20:
                    countdowns.append((rem / 20.0, f"🍽️ *Milestone Watch:* *{display_name}* is *{rem} RBI{'s' if rem != 1 else ''} away* from *{m:,} career RBIs* (currently at {rbis:,})."))
                    break

        cp = career_pitch.get(pid)
        if cp:
            wins = cp["w"]
            for m in WIN_MILESTONES:
                rem = m - wins
                if 0 < rem <= 4:
                    countdowns.append((rem / 4.0, f"🏆 *Milestone Watch:* *{display_name}* needs *{rem} more win{'s' if rem != 1 else ''}* to reach *{m:,} career wins* (currently at {wins:,})."))
                    break

            ks = cp["k"]
            for m in K_MILESTONES:
                rem = m - ks
                if 0 < rem <= 30:
                    countdowns.append((rem / 30.0, f"🔥 *Milestone Watch:* *{display_name}* is *{rem} strikeout{'s' if rem != 1 else ''} away* from *{m:,} career Ks* (currently at {ks:,})."))
                    break

            saves = cp["s"]
            for m in SAVE_MILESTONES:
                rem = m - saves
                if 0 < rem <= 8:
                    countdowns.append((rem / 8.0, f"🔒 *Milestone Watch:* *{display_name}* needs *{rem} more save{'s' if rem != 1 else ''}* to reach *{m:,} career saves* (currently at {saves:,})."))
                    break

    countdowns.sort(key=lambda x: x[0])
    return [text for _, text in countdowns[:4]]


REPORTS_BASE = "https://statsplus.net/xfbl/reports/news/html/leagues"

def get_power_rankings(league_url="https://statsplus.net/xfbl", days_back=7):
    """
    Computes OOTP-style Weekly Power Rankings directly from the StatsPlus API
    (/api/lgdata/ and /api/gamehistory/) without scraping HTML.
    Returns a list of dicts: {rank, team, points, trend}
    where trend is one of: '++', '+', 'o', '-', '--'.
    """
    from collections import defaultdict

    lgdata = get_cached_lgdata(league_url)
    if not lgdata:
        return []

    current_date = get_league_current_date(league_url)
    cutoff_date = current_date - timedelta(days=days_back)
    gh_rows = get_cached_gamehistory(league_url, cutoff_date, current_date)

    primary_lid = 100
    for l in lgdata.get("leagues", []):
        if l.get("primary_league"):
            primary_lid = l.get("league_id", 100)
            break

    teams_dict = {
        t["team_id"]: f"{t.get('name', '')} {t.get('nickname', '')}".strip()
        for t in lgdata.get("teams", [])
        if t.get("league_id") == primary_lid
    }

    sim_w = defaultdict(int)
    sim_l = defaultdict(int)
    for gh in gh_rows:
        if gh.get("game_type") != "0":
            continue
        a_id = int(gh.get("away_team") or 0)
        h_id = int(gh.get("home_team") or 0)
        r0 = int(gh.get("runs0") or 0)
        r1 = int(gh.get("runs1") or 0)
        if r0 > r1:
            sim_w[a_id] += 1
            sim_l[h_id] += 1
        elif r1 > r0:
            sim_w[h_id] += 1
            sim_l[a_id] += 1

    raw_rankings = []
    for st in lgdata.get("standings", []):
        tid = st.get("team_id")
        if tid not in teams_dict:
            continue
        w = int(st.get("w") or 0)
        l = int(st.get("l") or 0)
        if w + l == 0:
            continue
        pct = float(st.get("pct") or (w / (w + l)))
        streak = int(st.get("streak") or 0)

        sw = sim_w[tid]
        sl = sim_l[tid]
        sim_gp = sw + sl
        sim_pct = (sw / sim_gp) if sim_gp > 0 else pct

        # OOTP Power Ranking points formula:
        # 90 * season_pct + 54 * recent_pct + 2 * streak + 18 baseline (~90.0 average)
        points = round((pct * 90.0) + (sim_pct * 54.0) + (streak * 1.5) + 18.0, 1)

        diff = sim_pct - pct
        if (sim_gp >= 4 and sim_pct >= 0.75) or streak >= 5 or diff >= 0.25:
            trend = "++"
        elif diff >= 0.08 or streak >= 2:
            trend = "+"
        elif (sim_gp >= 4 and sim_pct <= 0.25) or streak <= -5 or diff <= -0.25:
            trend = "--"
        elif diff <= -0.08 or streak <= -2:
            trend = "-"
        else:
            trend = "o"

        raw_rankings.append({
            "team": teams_dict[tid],
            "points": points,
            "trend": trend,
        })

    if not raw_rankings:
        return []

    raw_rankings.sort(key=lambda x: x["points"], reverse=True)
    for idx, item in enumerate(raw_rankings, start=1):
        item["rank"] = idx

    return raw_rankings


def get_offseason_transactions(league_url="https://statsplus.net/xfbl", max_days=7):
    """
    Scrapes the static OOTP transactions report for roster moves strictly within
    [cutoff_date, current_date].
    Returns a list of dicts: {date, team, action}
    """
    current_game_date = get_league_current_date(league_url)
    cutoff_date = current_game_date - timedelta(days=max_days)
    report_url = f"{league_url.rstrip('/')}/reports/news/html/leagues/league_100_transactions_0_0.html"
    try:
        resp = requests.get(report_url, headers=_get_api_headers(), timeout=15)
        soup = BeautifulSoup(resp.text, 'html.parser')
    except Exception as e:
        print(f"Could not fetch transactions: {e}")
        return []

    transactions = []
    for table in soup.find_all('table', class_='data'):
        header = table.find('th', class_='dl')
        if not header:
            continue
        date_str = header.get_text(separator=' ', strip=True)
        event_date = parse_ootp_date(date_str)
        if not event_date:
            continue
        if event_date < cutoff_date:
            break
        if event_date > current_game_date:
            continue

        for td in table.find_all('td', class_=lambda c: c and 'dl' in c):
            text = td.get_text(separator=' ', strip=True)
            team_tag = td.find('a')
            team = team_tag.get_text(strip=True) if team_tag else "Unknown"
            action = re.sub(r'^[^:]+:\s*', '', text).strip()
            if action:
                transactions.append({
                    "date": event_date.strftime("%Y-%m-%d"),
                    "team": team,
                    "action": action
                })

    print(f"Transactions in sim window: found {len(transactions)} moves.")
    return transactions


def get_offseason_data(league_url="https://statsplus.net/xfbl", days_back=7):
    """
    Scrapes both the static OOTP news report and transactions report for updates
    within the sim window, using /api/date/ for the exact in-game date.
    """
    current_date = get_league_current_date(league_url)
    cutoff_date = current_date - timedelta(days=days_back)
    print(f"Offseason lookback: {cutoff_date.strftime('%Y-%m-%d')} to {current_date.strftime('%Y-%m-%d')}")

    awards = []
    trades = []
    major_signings = []
    retirements_hof = []
    financials = []
    minor_moves = []
    
    seen_events = set()
    
    def is_duplicate(text):
        normalized = re.sub(r'[^a-zA-Z0-9]', '', text).lower()
        if normalized in seen_events:
            return True
        seen_events.add(normalized)
        return False

    reports_base = f"{league_url.rstrip('/')}/reports/news/html/leagues"

    # A. Scrape News Report
    news_url = f"{reports_base}/league_100_news.html"
    try:
        resp = requests.get(news_url, headers=_get_api_headers(), timeout=15)
        news_soup = BeautifulSoup(resp.text, 'html.parser')
    except Exception as e:
        print(f"Error fetching news report: {e}")
        news_soup = None

    if news_soup:
        for table in news_soup.find_all('table', class_='data'):
            th = table.find('th', class_='dl')
            if not th:
                continue
            date_str = th.get_text(separator=' ', strip=True)
            event_date = parse_ootp_date(date_str)
            if not event_date or not (cutoff_date <= event_date <= current_date):
                continue
                
            for tr in table.find_all('tr'):
                td = tr.find('td', class_=lambda c: c and 'dl' in c)
                if not td:
                    continue
                text = td.get_text(separator=' ', strip=True)
                if is_duplicate(text):
                    continue
                
                text_lower = text.lower()
                
                if "wins the" in text_lower or "honored:" in text_lower or "award" in text_lower:
                    if "finished" not in text_lower:
                        awards.append(text)
                elif "inducted into" in text_lower or "hall of fame" in text_lower or "retired" in text_lower:
                    retirements_hof.append(text)
                elif "owner took" in text_lower or "cash as profit" in text_lower or ("received" in text_lower and "from the owner" in text_lower):
                    financials.append(text)
                elif "traded" in text_lower:
                    trades.append(text)
                elif "signed" in text_lower or "contract extension" in text_lower:
                    contract_match = re.search(r'(\d+)-year contract worth a total of \$([0-9,]+)', text)
                    is_major = False
                    if contract_match:
                        years = int(contract_match.group(1))
                        total_val = int(contract_match.group(2).replace(',', ''))
                        avg_val = total_val / years
                        if avg_val >= 4000000 or total_val >= 10000000:
                            is_major = True
                    if is_major:
                        major_signings.append(text)
                    else:
                        minor_moves.append(text)
                elif "trading block" in text_lower:
                    minor_moves.append(text)

    # B. Scrape Transactions Report
    tx_url = f"{reports_base}/league_100_transactions_0_0.html"
    try:
        resp = requests.get(tx_url, headers=_get_api_headers(), timeout=15)
        tx_soup = BeautifulSoup(resp.text, 'html.parser')
    except Exception as e:
        print(f"Error fetching transactions report: {e}")
        tx_soup = None

    if tx_soup:
        for table in tx_soup.find_all('table', class_='data'):
            th = table.find('th', class_='dl')
            if not th:
                continue
            date_str = th.get_text(separator=' ', strip=True)
            event_date = parse_ootp_date(date_str)
            if not event_date or not (cutoff_date <= event_date <= current_date):
                continue
                
            for tr in table.find_all('tr'):
                td = tr.find('td', class_=lambda c: c and 'dl' in c)
                if not td:
                    continue
                text = td.get_text(separator=' ', strip=True)
                if is_duplicate(text):
                    continue
                
                team_tag = td.find('a')
                team = team_tag.get_text(strip=True) if team_tag else ""
                clean_text = re.sub(r'^[^:]+:\s*', '', text).strip()
                display_text = f"{team}: {clean_text}" if team else clean_text
                
                text_lower = text.lower()
                if "traded" in text_lower or "exchange for" in text_lower:
                    trades.append(display_text)
                elif "signed" in text_lower or "contract extension" in text_lower:
                    contract_match = re.search(r'(\d+)-year contract worth a total of \$([0-9,]+)', clean_text)
                    is_major = False
                    if contract_match:
                        years = int(contract_match.group(1))
                        total_val = int(contract_match.group(2).replace(',', ''))
                        avg_val = total_val / years
                        if avg_val >= 4000000 or total_val >= 10000000:
                            is_major = True
                    if is_major:
                        major_signings.append(display_text)
                    else:
                        minor_moves.append(display_text)
                elif "retired" in text_lower:
                    retirements_hof.append(display_text)
                else:
                    minor_moves.append(display_text)

    return {
        "awards": awards,
        "trades": trades,
        "major_signings": major_signings,
        "retirements_hof": retirements_hof,
        "financials": financials,
        "minor_moves": minor_moves,
        "cutoff_date": cutoff_date,
        "current_date": current_date
    }

def get_regular_season_trades(league_url, state, days_back=7):
    """
    Returns trades completed strictly within the current sim window [cutoff_date, current_date].
    """
    transactions = get_offseason_transactions(league_url, max_days=days_back)
    trades = []
    seen = set()
    for t in transactions:
        if "traded" in t["action"].lower():
            # Deduplicate identical trade descriptions
            norm = re.sub(r"\s+", " ", t["action"]).strip()
            if norm not in seen:
                seen.add(norm)
                trades.append(t)
    return trades

def evaluate_traded_players(league_url, state):
    """
    Uses the StatsPlus API (/api/players/, /api/playerbatstatsv2/, /api/playerpitchstatsv2/)
    to evaluate players traded this season (was_traded == '1' or stint > 1) and highlight
    notable post-trade performances on their new club.
    """
    active_players = get_cached_players(league_url, active_only=True)
    _, _, team_abbr_map, _, _ = _get_maps(league_url)
    bat_rows, pitch_rows = get_cached_season_stats(league_url)

    traded_pids = {}
    for p in active_players:
        if p.get("Level") == "1" and p.get("was_traded") == "1":
            pid = p.get("ID", "").strip()
            tid = p.get("Team ID", "").strip()
            last_tid = p.get("last_team_id", "").strip()
            name = f"{p.get('First Name', '').strip()} {p.get('Last Name', '').strip()}".strip()
            traded_pids[pid] = {
                "name": name,
                "team_id": tid,
                "team_abbr": team_abbr_map.get(tid, "???"),
                "old_abbr": team_abbr_map.get(last_tid, ""),
            }

    if not traded_pids:
        return []

    evaluations = []
    # Check batters on their current team stint (stint >= 1 matching their current team_id)
    for r in bat_rows:
        pid = r.get("player_id", "").strip()
        if pid in traded_pids and r.get("split_id") == "1" and r.get("level_id") == "1":
            info = traded_pids[pid]
            if r.get("team_id") == info["team_id"] and int(r.get("stint") or 0) >= 1:
                pa = int(r.get("pa") or 0)
                ab = int(r.get("ab") or 0)
                h = int(r.get("h") or 0)
                hr = int(r.get("hr") or 0)
                rbi = int(r.get("rbi") or 0)
                war = float(r.get("war") or 0.0)
                if pa >= 30 and abs(war) >= 0.5:
                    avg_str = f"{(h / ab):.3f}".lstrip("0") if ab > 0 else ".000"
                    from_str = f" (acquired from {info['old_abbr']})" if info["old_abbr"] and info["old_abbr"] != info["team_abbr"] else ""
                    evaluations.append((
                        abs(war),
                        f"📈 *{info['name']}* ({info['team_abbr']}){from_str}: hitting *{avg_str}* with *{hr} HR*, *{rbi} RBI*, and *{war:+.1f} WAR* in {pa} PA with his new club."
                    ))

    for r in pitch_rows:
        pid = r.get("player_id", "").strip()
        if pid in traded_pids and r.get("split_id") == "1" and r.get("level_id") == "1":
            info = traded_pids[pid]
            if r.get("team_id") == info["team_id"] and int(r.get("stint") or 0) >= 1:
                ip = float(r.get("ip") or 0.0)
                er = float(r.get("er") or 0.0)
                k = int(r.get("k") or 0)
                w = int(r.get("w") or 0)
                l = int(r.get("l") or 0)
                war = float(r.get("war") or 0.0)
                if ip >= 15.0 and abs(war) >= 0.5:
                    era = (er / ip) * 9.0
                    from_str = f" (acquired from {info['old_abbr']})" if info["old_abbr"] and info["old_abbr"] != info["team_abbr"] else ""
                    evaluations.append((
                        abs(war),
                        f"⚾ *{info['name']}* ({info['team_abbr']}){from_str}: *{w}-{l}, {era:.2f} ERA* with *{k} Ks* and *{war:+.1f} WAR* across {ip:.1f} IP since the trade."
                    ))

    evaluations.sort(key=lambda x: x[0], reverse=True)
    return [text for _, text in evaluations[:3]]

def get_injuries(league_url="https://statsplus.net/xfbl", days_back=7):
    """
    Finds major injuries (expected to miss 2+ weeks / 14+ days) that occurred during
    the sim window by combining /api/players/ injury status with the static OOTP
    injury report (league_100_injuries.html).
    """
    current_date = get_league_current_date(league_url)
    cutoff_date = current_date - timedelta(days=days_back)
    inj_url = f"{league_url.rstrip('/')}/reports/news/html/leagues/league_100_injuries.html"

    injuries = []
    seen = set()
    try:
        resp = requests.get(inj_url, headers=_get_api_headers(), timeout=15)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "html.parser")
            for table in soup.find_all("table", class_="data"):
                th = table.find("th", class_="dl")
                if not th:
                    continue
                event_date = parse_ootp_date(th.get_text(separator=" ", strip=True))
                if not event_date:
                    continue
                if event_date < cutoff_date:
                    break
                if event_date > current_date:
                    continue

                for tr in table.find_all("tr"):
                    td = tr.find("td", class_=lambda c: c and "dl" in c)
                    if not td:
                        continue
                    text = re.sub(r"\s+", " ", td.get_text(separator=" ", strip=True)).strip()
                    # Check if injury duration is significant (e.g. 2+ weeks or months)
                    is_severe = False
                    if re.search(r"miss about (\d+(?:-\d+)?)\s*month", text, re.IGNORECASE):
                        is_severe = True
                    elif re.search(r"out for the season|career-ending", text, re.IGNORECASE):
                        is_severe = True
                    else:
                        w_match = re.search(r"(?:miss about|last)\s+(\d+)(?:-\d+)?\s*weeks", text, re.IGNORECASE)
                        if w_match and int(w_match.group(1)) >= 2 and "day-to-day" not in text.lower():
                            is_severe = True

                    if is_severe and text not in seen:
                        seen.add(text)
                        injuries.append({
                            "date": event_date.strftime("%Y-%m-%d"),
                            "text": text,
                        })
    except Exception as e:
        print(f"Error fetching injuries report: {e}")

    return injuries[:5]

def get_sweeps_and_walkoffs(league_url="https://statsplus.net/xfbl", days_back=7):
    """
    Computes 3+ game series sweeps and walk-off wins directly from the StatsPlus API
    (/api/gamehistory/ and /api/atbats/) within the sim window.
    """
    from collections import defaultdict

    current_date = get_league_current_date(league_url)
    cutoff_date = current_date - timedelta(days=days_back)
    player_names, _, team_abbr_map, team_full_map, _ = _get_maps(league_url)

    gh_rows = get_cached_gamehistory(league_url, cutoff_date, current_date)
    ab_rows = get_cached_atbats(league_url, cutoff_date, current_date)

    sweeps = []
    walkoffs = []

    # 1. Detect 3+ game series sweeps from /api/gamehistory/
    if gh_rows:
        # Sort chronologically and group consecutive games with same (away_team, home_team)
        reg_games = [
            g for g in gh_rows
            if g.get("game_type") == "0" and g.get("played") == "1"
        ]
        reg_games.sort(key=lambda g: (g.get("date", ""), int(g.get("game_id") or 0)))

        # Group by (away_team, home_team) series chunks where dates are within 4 days
        series_map = defaultdict(list)
        for g in reg_games:
            key = (g.get("away_team"), g.get("home_team"))
            series_map[key].append(g)

        for (away_tid, home_tid), games in series_map.items():
            # Split into contiguous series if gap > 2 days
            current_series = []
            for g in games:
                gdate = datetime.strptime(g["date"], "%Y-%m-%d")
                if current_series:
                    prev_date = datetime.strptime(current_series[-1]["date"], "%Y-%m-%d")
                    if (gdate - prev_date).days > 2:
                        if len(current_series) >= 3:
                            _check_series_sweep(current_series, away_tid, home_tid, team_full_map, team_abbr_map, sweeps)
                        current_series = [g]
                    else:
                        current_series.append(g)
                else:
                    current_series = [g]
            if len(current_series) >= 3:
                _check_series_sweep(current_series, away_tid, home_tid, team_full_map, team_abbr_map, sweeps)

    # 2. Detect walk-offs from /api/atbats/
    if ab_rows:
        games_pitches = defaultdict(list)
        for r in ab_rows:
            if r.get("game_type") not in ("0", "3"):
                continue
            gdate_str = r.get("date", "")
            try:
                gdate = datetime.strptime(gdate_str, "%Y-%m-%d")
                if not (cutoff_date <= gdate <= current_date):
                    continue
            except Exception:
                continue
            games_pitches[r.get("game_id")].append(r)

        for gid, pas in games_pitches.items():
            if not pas:
                continue
            last_pa = pas[-1]
            home_tid = str(last_pa.get("home_team", ""))
            bat_tid = str(last_pa.get("team_id", ""))
            inning = int(last_pa.get("inning") or 0)
            runs_on_play = int(last_pa.get("r") or 0)

            if bat_tid == home_tid and inning >= 9 and runs_on_play > 0:
                home_runs = sum(int(x.get("r") or 0) for x in pas if str(x.get("team_id")) == home_tid)
                away_runs = sum(int(x.get("r") or 0) for x in pas if str(x.get("team_id")) != home_tid)
                away_tids = {str(x.get("team_id")) for x in pas if str(x.get("team_id")) != home_tid}
                away_tid = list(away_tids)[0] if away_tids else ""

                # Walk-off if home team won and was tied or trailing prior to the final PA
                if home_runs > away_runs and (home_runs - runs_on_play) <= away_runs:
                    pid = last_pa.get("player_id", "")
                    pname = player_names.get(pid, f"Player {pid}")
                    h_abbr = team_abbr_map.get(home_tid, "???")
                    a_abbr = team_abbr_map.get(away_tid, "???")
                    res = last_pa.get("result", "")
                    play_desc = {
                        "9": "walk-off home run",
                        "8": "walk-off triple",
                        "7": "walk-off double",
                        "6": "walk-off single",
                        "2": "bases-loaded walk",
                        "10": "walk-off hit-by-pitch",
                    }.get(res, "walk-off play")
                    inn_str = f"{inning}th" if inning not in (11, 12, 13) else f"{inning}th"
                    box_url = f"{league_url.rstrip('/')}/reports/news/html/box_scores/game_box_{gid}.html"
                    walkoffs.append({
                        "text": f"🚨 *{pname}* ({h_abbr}) delivered a *{play_desc}* in the {inn_str} to beat {a_abbr} *{home_runs}-{away_runs}*!",
                        "box_url": box_url,
                    })

    return {"sweeps": sweeps[:4], "walkoffs": walkoffs[:4]}

def _check_series_sweep(series_games, away_tid, home_tid, team_full_map, team_abbr_map, sweeps_out):
    away_wins = sum(1 for g in series_games if int(g.get("runs0") or 0) > int(g.get("runs1") or 0))
    home_wins = sum(1 for g in series_games if int(g.get("runs1") or 0) > int(g.get("runs0") or 0))
    n = len(series_games)
    if away_wins == n:
        winner = team_full_map.get(str(away_tid)) or team_abbr_map.get(str(away_tid), "???")
        loser = team_full_map.get(str(home_tid)) or team_abbr_map.get(str(home_tid), "???")
        sweeps_out.append(f"🧹 *{winner}* completed a *{n}-game road sweep* over the {loser}!")
    elif home_wins == n:
        winner = team_full_map.get(str(home_tid)) or team_abbr_map.get(str(home_tid), "???")
        loser = team_full_map.get(str(away_tid)) or team_abbr_map.get(str(away_tid), "???")
        sweeps_out.append(f"🧹 *{winner}* swept the {loser} in a *{n}-game home series*!")

def get_prospect_callups(league_url="https://statsplus.net/xfbl", days_back=7):
    """
    Detects rookies who made their Major League debut during this sim window
    using /api/players/?retired=0 (mlb_service_years == 0 and mlb_service_days <= days_back)
    and /api/atbats/.
    """
    current_date = get_league_current_date(league_url)
    cutoff_date = current_date - timedelta(days=days_back)
    active_players = get_cached_players(league_url, active_only=True)
    _, _, team_abbr_map, _, _ = _get_maps(league_url)
    ab_rows = get_cached_atbats(league_url, cutoff_date, current_date)

    pos_map = {
        "1": "P", "2": "C", "3": "1B", "4": "2B", "5": "3B",
        "6": "SS", "7": "LF", "8": "CF", "9": "RF", "10": "DH"
    }

    sim_participants = set()
    for r in ab_rows:
        if r.get("game_type") == "0":
            sim_participants.add(r.get("player_id", "").strip())
            sim_participants.add(r.get("pitcher_id", "").strip())

    debuts = []
    for p in active_players:
        if p.get("Level") != "1":
            continue
        pid = p.get("ID", "").strip()
        srv_yrs = int(p.get("mlb_service_years") or 0)
        srv_days = int(p.get("mlb_service_days") or 0)
        if srv_yrs == 0 and 0 < srv_days <= days_back and pid in sim_participants:
            name = f"{p.get('First Name', '').strip()} {p.get('Last Name', '').strip()}".strip()
            age = p.get("Age", "")
            pos = pos_map.get(p.get("Pos", ""), "")
            tid = p.get("Team ID", "").strip()
            tabbr = team_abbr_map.get(tid, "???")
            age_str = f", {age} yo," if age else ""
            debuts.append(f"👶 *{pos} {name}* ({tabbr}){age_str} made his Major League debut this sim!")

    return debuts[:4]

def get_rough_outings(league_url="https://statsplus.net/xfbl", days_back=7):
    """
    Finds the roughest single-game performances from cached /api/atbats/ in the sim window:
    - Batters with a Golden/Platinum Sombrero (4+ strikeouts in a single game)
    - Pitchers who got shelled (lowest Game Score <= 20 or 6+ runs allowed)
    """
    from collections import defaultdict

    current_date = get_league_current_date(league_url)
    cutoff_date = current_date - timedelta(days=days_back)
    rows = get_cached_atbats(league_url, cutoff_date, current_date)
    if not rows:
        return []

    player_names, _, team_abbr_map, _, _ = _get_maps(league_url)
    game_teams = defaultdict(set)
    for r in rows:
        gid = r.get("game_id")
        tid = r.get("team_id")
        if gid and tid:
            game_teams[gid].add(tid)

    batter_games = defaultdict(lambda: {"ab": 0, "h": 0, "k": 0, "team_id": "", "date": ""})
    pitcher_games = defaultdict(lambda: {"outs": 0, "h": 0, "r": 0, "bb": 0, "k": 0, "hr": 0, "opp_id": "", "date": ""})

    for r in rows:
        if r.get("game_type") not in ("0", "3"):
            continue
        gdate_str = r.get("date", "")
        try:
            gdate = datetime.strptime(gdate_str, "%Y-%m-%d")
            if not (cutoff_date <= gdate <= current_date):
                continue
        except Exception:
            continue

        gid = r.get("game_id")
        pid = r.get("player_id")
        pitcher_id = r.get("pitcher_id")
        tid = r.get("team_id")
        res = r.get("result")

        bg = batter_games[(pid, gid)]
        bg["team_id"] = tid
        bg["date"] = gdate_str
        if res in ("4", "5", "6", "7", "8", "9", "1"):
            bg["ab"] += 1
        if res in ("6", "7", "8", "9"):
            bg["h"] += 1
        if res == "1":
            bg["k"] += 1

        pg = pitcher_games[(pitcher_id, gid)]
        pg["opp_id"] = tid
        pg["date"] = gdate_str
        pg["r"] += int(r.get("r") or 0)
        if res in ("4", "5", "1"):
            pg["outs"] += 1
        if res in ("6", "7", "8", "9"):
            pg["h"] += 1
        if res == "9":
            pg["hr"] += 1
        if res == "2":
            pg["bb"] += 1
        if res == "1":
            pg["k"] += 1

    rough = []

    # 1. Worst pitching outing
    worst_pitchers = []
    for (pid, gid), st in pitcher_games.items():
        outs = st["outs"]
        ip_full = outs // 3
        ip_rem = outs % 3
        ip_str = f"{ip_full}.{ip_rem}"
        bonus = max(0, (ip_full - 4) * 2)
        gs = 50 + outs + bonus + st["k"] - (2 * st["h"]) - (4 * st["r"]) - (2 * st["bb"])
        if gs <= 20 or st["r"] >= 6:
            worst_pitchers.append((gs, -st["r"], pid, gid, st, ip_str))

    if worst_pitchers:
        worst_pitchers.sort(key=lambda x: (x[0], x[1]))
        gs, _, pid, gid, st, ip_str = worst_pitchers[0]
        pname = player_names.get(pid, f"Player {pid}")
        opp_abbr = team_abbr_map.get(str(st["opp_id"]), "???")
        p_team_set = game_teams.get(gid, set()) - {st["opp_id"]}
        t_abbr = team_abbr_map.get(list(p_team_set)[0], "???") if p_team_set else "???"
        rough.append(
            f"📉 *Shelled on the Mound:* *{pname}* ({t_abbr}) was tagged for *{st['r']} runs on {st['h']} hits* over *{ip_str} IP* vs {opp_abbr} (Game Score: *{gs}*)."
        )

    # 2. Golden / Platinum Sombreros (4+ Ks in a game)
    sombreros = [
        (st["k"], st["ab"], -st["h"], pid, gid, st)
        for (pid, gid), st in batter_games.items()
        if st["k"] >= 4
    ]
    if sombreros:
        sombreros.sort(reverse=True)
        k_cnt, ab_cnt, _, pid, gid, st = sombreros[0]
        pname = player_names.get(pid, f"Player {pid}")
        t_abbr = team_abbr_map.get(str(st["team_id"]), "???")
        opp_set = game_teams.get(gid, set()) - {st["team_id"]}
        opp_abbr = team_abbr_map.get(list(opp_set)[0], "???") if opp_set else "???"
        hat_type = "Platinum Sombrero" if k_cnt >= 5 else "Golden Sombrero"
        rough.append(
            f" sombrero *The {hat_type}:* *{pname}* ({t_abbr}) went *{st['h']}-for-{ab_cnt} with {k_cnt} strikeouts* against {opp_abbr}.".replace(" sombrero ", "👒 ")
        )

    return rough

if __name__ == "__main__":
    best_pitcher, best_batter = get_best_performances()
    print("Best Pitcher:", best_pitcher)
    print("Best Batter:", best_batter)
