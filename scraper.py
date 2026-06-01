import requests
from bs4 import BeautifulSoup
import re
from datetime import datetime, timedelta

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

def get_best_performances(league_url="https://statsplus.net/xfbl", days_back=7):
    """
    Scrapes the Best Performances pages from StatsPlus.
    Finds the highest ranked performance within the designated timeframe.
    """
    bat_url = f"{league_url}/bestgames/bat/"
    pitch_url = f"{league_url}/bestgames/pitch/"
    
    # Get the current game date from S+ home to establish our timeframe
    try:
        home_html = requests.get(league_url).text
        home_soup = BeautifulSoup(home_html, 'html.parser')
        date_element = home_soup.find(string=re.compile(r"Game Date:"))
        if date_element:
            date_str = date_element.replace("Game Date:", "").strip()
            current_date = datetime.strptime(date_str, "%Y-%m-%d")
        else:
            current_date = datetime.now()
    except Exception:
        current_date = datetime.now()
        
    cutoff_date = current_date - timedelta(days=days_back)
    print(f"Looking for performances between {cutoff_date.strftime('%Y-%m-%d')} and {current_date.strftime('%Y-%m-%d')}")

    best_batter = scrape_table_with_dates(bat_url, cutoff_date, current_date, league_url, is_pitcher=False)
    best_pitcher = scrape_table_with_dates(pitch_url, cutoff_date, current_date, league_url, is_pitcher=True)
    
    return best_pitcher, best_batter

def scrape_table_with_dates(url, cutoff_date, current_date, league_url, is_pitcher=False):
    response = requests.get(url)
    soup = BeautifulSoup(response.text, 'html.parser')
    
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

def get_headlines_and_milestones(league_url="https://statsplus.net/xfbl"):
    recap_url = f"{league_url.rstrip('/')}/recap/"
    try:
        response = requests.get(recap_url)
        soup = BeautifulSoup(response.text, 'html.parser')
    except Exception as e:
        print(f"Error fetching recap page: {e}")
        return []
    
    headlines = []
    panel = soup.find(id='recap-msg-panel')
    if not panel:
        return headlines
        
    for div in panel.find_all('div', class_='smallfont oneline'):
        text = " ".join(div.text.split())
        
        # 1. Career Milestones
        match = re.search(r'reached (\d+) ([a-z\s]+)', text, re.IGNORECASE)
        if match:
            amount = int(match.group(1))
            stat = match.group(2).strip().lower()
            
            is_impressive = False
            if 'hit' in stat and not 'extra' in stat and amount >= 1000:
                is_impressive = True
            elif 'home run' in stat and amount >= 200:
                is_impressive = True
            elif 'win' in stat and amount >= 150:
                is_impressive = True
            elif 'strikeout' in stat and amount >= 1000:
                is_impressive = True
            elif 'save' in stat and amount >= 200:
                is_impressive = True
            elif 'rbi' in stat and amount >= 1000:
                is_impressive = True
            elif 'extra base' in stat and amount >= 500:
                is_impressive = True
                
            if is_impressive:
                name_match = re.search(r'^[A-Z0-9]{1,2} ([^\(]+) \(([A-Z]+)\)', text)
                if name_match:
                    name = name_match.group(1).strip()
                    team = name_match.group(2).strip()
                    headlines.append(f"🎖️ *{name}* ({team}) reached *{amount:,} {stat}*.")
            continue
            
        # 2. Rare Feats & Special Events
        name_match = re.search(r'^[A-Z0-9]{1,2} ([^\(]+) \(([A-Z]+)\)', text)
        if name_match:
            name = name_match.group(1).strip()
            team = name_match.group(2).strip()
            
            if re.search(r'NO-HITTER', text):
                headlines.append(f"🎩 *NO-HITTER Alert*: {name} ({team}) threw a no-hitter!")
            elif re.search(r'PERFECT GAME', text):
                headlines.append(f"👑 *PERFECT GAME Alert*: {name} ({team}) threw a perfect game!")
            elif re.search(r'hits for the CYCLE', text, re.IGNORECASE):
                headlines.append(f"🚲 *Cycle Watch*: {name} ({team}) hit for the cycle!")
            elif re.search(r'WALK-OFF|walk-off', text):
                headlines.append(f"🚨 *Walk-off Magic*: {name} ({team}) delivered a walk-off hit!")
            elif re.search(r'Major League debut|MLB debut', text, re.IGNORECASE):
                headlines.append(f"👶 *Prospect Watch*: {name} ({team}) made his Major League debut.")

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
    "MIL": "Milwaukee Brewers", "MIN": "Minnesota Twins", "MON": "Montreal Expos",
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

def get_team_momentum(league_url="https://statsplus.net/xfbl"):
    elo_url = f"{league_url.rstrip('/')}/elo/current/"
    try:
        response = requests.get(elo_url)
        soup = BeautifulSoup(response.text, 'html.parser')
    except Exception as e:
        print(f"Error fetching ELO page: {e}")
        return None, None
        
    table = soup.find('table')
    if not table:
        return None, None
        
    teams_elo = []
    for row in table.find_all('tr')[1:]:
        cols = [td.text.strip() for td in row.find_all('td')]
        if len(cols) > 9:
            team_name = get_full_team_name(cols[1])
            try:
                momentum = float(cols[9])
                teams_elo.append((team_name, momentum))
            except ValueError:
                pass

    if not teams_elo:
        return None, None
        
    teams_elo.sort(key=lambda x: x[1])
    coldest = {"team": teams_elo[0][0], "change": teams_elo[0][1]}
    hottest = {"team": teams_elo[-1][0], "change": teams_elo[-1][1]}
    return hottest, coldest

def get_team_luck(league_url="https://statsplus.net/xfbl"):
    baseruns_url = f"{league_url.rstrip('/')}/baseruns/"
    try:
        response = requests.get(baseruns_url)
        soup = BeautifulSoup(response.text, 'html.parser')
    except Exception as e:
        print(f"Error fetching BaseRuns page: {e}")
        return None, None
        
    table = soup.find('table')
    if not table:
        return None, None
        
    teams_luck = []
    for row in table.find_all('tr')[1:]:
        cols = [td.text.strip() for td in row.find_all('td')]
        if len(cols) > 21:
            team_name = get_full_team_name(cols[0])
            try:
                luck = int(cols[21])
                actual_w = cols[11]
                actual_l = cols[12]
                xw = cols[18]
                xl = cols[19]
                teams_luck.append({
                    "team": team_name,
                    "luck": luck,
                    "actual": f"{actual_w}-{actual_l}",
                    "expected": f"{xw}-{xl}"
                })
            except ValueError:
                pass

    if not teams_luck:
        return None, None
        
    teams_luck.sort(key=lambda x: x['luck'])
    unluckiest = teams_luck[0]
    luckiest = teams_luck[-1]
    return luckiest, unluckiest

def get_close_division_races(league_url="https://statsplus.net/xfbl"):
    standings_url = f"{league_url.rstrip('/')}/standings/"
    try:
        response = requests.get(standings_url)
        soup = BeautifulSoup(response.text, 'html.parser')
    except Exception as e:
        print(f"Error fetching Standings page: {e}")
        return []
        
    close_races = []
    for table in soup.find_all('table'):
        th = table.find('th')
        if th and 'Division' in th.text:
            div_name = th.text.strip().replace(' Division', '')
            rows = table.find_all('tr')
            if len(rows) > 3:
                cols1 = [td.text.strip() for td in rows[2].find_all('td')]
                cols2 = [td.text.strip() for td in rows[3].find_all('td')]
                if len(cols1) > 4 and len(cols2) > 4:
                    first_place = get_full_team_name(cols1[0])
                    second_place = get_full_team_name(cols2[0])
                    gb_str = cols2[4]
                    if gb_str == '-':
                        gb = 0.0
                    else:
                        gb_val = gb_str.replace('½', '.5')
                        try:
                            gb = float(gb_val)
                        except ValueError:
                            continue
                    if gb <= 2.0:
                        close_races.append({
                            "division": div_name,
                            "first_place": first_place,
                            "second_place": second_place,
                            "gb": gb_str
                        })
    return close_races

def get_notable_games(league_url="https://statsplus.net/xfbl", days_back=7):
    """
    Scans the best batting performances for noteworthy/weird games:
    - Blowouts (margin of 10+ runs)
    - High-scoring affairs (combined score 20+)
    - Individual players hitting 3+ HRs in a game
    """
    from urllib.parse import urljoin
    bat_url = f"{league_url}/bestgames/bat/"
    
    try:
        home_html = requests.get(league_url).text
        home_soup = BeautifulSoup(home_html, 'html.parser')
        date_element = home_soup.find(string=re.compile(r"Game Date:"))
        if date_element:
            date_str = date_element.replace("Game Date:", "").strip()
            current_date = datetime.strptime(date_str, "%Y-%m-%d")
        else:
            current_date = datetime.now()
    except Exception:
        current_date = datetime.now()

    cutoff_date = current_date - timedelta(days=days_back)
    
    response = requests.get(bat_url)
    soup = BeautifulSoup(response.text, 'html.parser')
    table = soup.find('table')
    if not table:
        return []

    tbody = table.find('tbody')
    rows = tbody.find_all('tr') if tbody else table.find_all('tr')
    
    notable = []
    seen_games = set()  # avoid reporting the same game twice

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

        # Parse score from box score link text (e.g. "13-4")
        box_link_tag = cols[5].find('a')
        score_text = box_link_tag.text.strip() if box_link_tag else ""
        box_url = urljoin(league_url, box_link_tag['href']) if box_link_tag else ""
        
        # Check for multi-HR game
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

        # Check for blowout or high-scoring game
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

    # Deduplicate by text
    seen_texts = set()
    deduped = []
    for item in notable:
        if item['text'] not in seen_texts:
            seen_texts.add(item['text'])
            deduped.append(item)
    
    return deduped[:5]  # Cap at 5 to keep the digest clean


def get_api_oddities(league_url="https://statsplus.net/xfbl"):
    """
    Uses the StatsPlus CSV API to mine for funny, odd, and noteworthy
    season-level stats. Returns a list of oddity dicts with 'text' and 'emoji'.
    Only uses split_id=1 (overall stats).

    Uses smart rotation: each category is keyed by a stable name. The bot
    tracks which categories were shown last sim (via state.json) and prefers
    categories that haven't appeared recently, and players who haven't won
    the same category back-to-back.
    """
    import csv
    import io

    bat_api = f"{league_url}/api/playerbatstatsv2/"
    pitch_api = f"{league_url}/api/playerpitchstatsv2/"
    players_api = f"{league_url}/api/players/"
    teams_api = f"{league_url}/api/teams/"

    def fetch_csv(url):
        try:
            resp = requests.get(url, timeout=15)
            resp.raise_for_status()
            text = "\n".join(line for line in resp.text.splitlines() if line.strip())
            return list(csv.DictReader(io.StringIO(text)))
        except Exception as e:
            print(f"API fetch failed for {url}: {e}")
            return []

    player_rows = fetch_csv(players_api)
    player_names = {}
    for r in player_rows:
        pid = r.get('ID', '').strip()
        first = r.get('First Name', '').strip()
        last = r.get('Last Name', '').strip()
        if pid:
            player_names[pid] = f"{first} {last}".strip()

    team_rows = fetch_csv(teams_api)
    team_display = {}
    for r in team_rows:
        tid = r.get('ID', '').strip()
        name = r.get('Name', '').strip()
        if tid:
            team_display[tid] = name

    def pname(pid, tid):
        return player_names.get(str(pid), f"Player#{pid}"), team_display.get(str(tid), f"T{tid}")

    bat_rows = fetch_csv(bat_api)
    bat_overall = [r for r in bat_rows if r.get('split_id') == '1']

    all_oddities = {}

    def safe_int(d, key, default=0):
        try: return int(d.get(key, default) or default)
        except: return default

    def safe_float(d, key, default=0.0):
        try: return float(d.get(key, default) or default)
        except: return default

    qualified_bat = [r for r in bat_overall if safe_int(r, 'pa') >= 100]

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

        gdp_leaders = [r for r in bat_overall if safe_int(r, 'gdp') >= 5]
        if gdp_leaders:
            gdp_king = max(gdp_leaders, key=lambda r: safe_int(r, 'gdp'))
            name, team = pname(gdp_king['player_id'], gdp_king['team_id'])
            all_oddities["gidp_machine"] = {
                "text": f"💀 *Double Play Machine:* {name} ({team}) has grounded into *{safe_int(gdp_king, 'gdp')} double plays* — the league's premier rally killer.",
                "emoji": "💀", "winner_id": gdp_king['player_id']
            }

        hr_rate_leaders = [r for r in bat_overall if safe_int(r, 'ab') >= 50 and safe_int(r, 'hr') >= 5]
        if hr_rate_leaders:
            hr_king = max(hr_rate_leaders, key=lambda r: safe_int(r, 'hr') / max(safe_int(r, 'ab'), 1))
            ab_per_hr = safe_int(hr_king, 'ab') / safe_int(hr_king, 'hr')
            name, team = pname(hr_king['player_id'], hr_king['team_id'])
            all_oddities["hr_freak"] = {
                "text": f"💣 *HR Freak:* {name} ({team}) is going yard every *{ab_per_hr:.1f} ABs* with {safe_int(hr_king, 'hr')} homers already.",
                "emoji": "💣", "winner_id": hr_king['player_id']
            }

        hr_raw_leaders = [r for r in bat_overall if safe_int(r, 'hr') >= 5]
        if hr_raw_leaders:
            hr_raw_king = max(hr_raw_leaders, key=lambda r: safe_int(r, 'hr'))
            name, team = pname(hr_raw_king['player_id'], hr_raw_king['team_id'])
            all_oddities["hr_king"] = {
                "text": f"🏡 *Home Run King:* {name} ({team}) leads the league with *{safe_int(hr_raw_king, 'hr')} home runs* on the season.",
                "emoji": "🏡", "winner_id": hr_raw_king['player_id']
            }

        sb_leaders = [r for r in bat_overall if safe_int(r, 'sb') >= 5]
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

        wpa_losers = [r for r in bat_overall if safe_float(r, 'wpa') < -0.5 and safe_int(r, 'pa') >= 100]
        if wpa_losers:
            wpa_loser = min(wpa_losers, key=lambda r: safe_float(r, 'wpa'))
            name, team = pname(wpa_loser['player_id'], wpa_loser['team_id'])
            all_oddities["clutch_kryptonite"] = {
                "text": f"📉 *Clutch Kryptonite:* {name} ({team}) has been absolutely *crushing his team's win probability* with {safe_float(wpa_loser, 'wpa'):.2f} WPA.",
                "emoji": "📉", "winner_id": wpa_loser['player_id']
            }

        avg_losers = [r for r in qualified_bat if safe_float(r, 'avg') > 0]
        if avg_losers:
            avg_loser = min(avg_losers, key=lambda r: safe_float(r, 'avg'))
            name, team = pname(avg_loser['player_id'], avg_loser['team_id'])
            all_oddities["human_out"] = {
                "text": f"🧱 *Human Out:* {name} ({team}) is hitting a paltry *.{int(safe_float(avg_loser, 'avg') * 1000):03d}* — making outs is basically his full-time job.",
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

        triple_leaders = [r for r in bat_overall if safe_int(r, '3b') >= 2]
        if triple_leaders:
            triple_king = max(triple_leaders, key=lambda r: safe_int(r, '3b'))
            name, team = pname(triple_king['player_id'], triple_king['team_id'])
            all_oddities["ghost_runner"] = {
                "text": f"👻 *Ghost Runner:* {name} ({team}) leads the league with *{safe_int(triple_king, '3b')} triples* — the rarest hit in baseball.",
                "emoji": "👻", "winner_id": triple_king['player_id']
            }

        babip_leaders = [r for r in qualified_bat if safe_float(r, 'babip') > 0]
        if babip_leaders:
            babip_king = max(babip_leaders, key=lambda r: safe_float(r, 'babip'))
            name, team = pname(babip_king['player_id'], babip_king['team_id'])
            all_oddities["babip_winner"] = {
                "text": f"🍀 *BABIP Lottery Winner:* {name} ({team}) is batting on a *.{int(safe_float(babip_king, 'babip') * 1000):03d} BABIP* — the baseball gods are smiling on this one.",
                "emoji": "🍀", "winner_id": babip_king['player_id']
            }

            babip_victim = min(babip_leaders, key=lambda r: safe_float(r, 'babip'))
            name, team = pname(babip_victim['player_id'], babip_victim['team_id'])
            all_oddities["babip_victim"] = {
                "text": f"🤡 *BABIP Victim:* {name} ({team}) is stranded at *.{int(safe_float(babip_victim, 'babip') * 1000):03d} BABIP* — every ball finds a glove.",
                "emoji": "🤡", "winner_id": babip_victim['player_id']
            }

        rbi_dep = [r for r in bat_overall if safe_int(r, 'rbi') >= 15 and safe_int(r, 'hr') <= 3]
        if rbi_dep:
            rbi_king = max(rbi_dep, key=lambda r: safe_int(r, 'rbi'))
            name, team = pname(rbi_king['player_id'], rbi_king['team_id'])
            all_oddities["rbi_dependent"] = {
                "text": f"🤝 *RBI Dependent:* {name} ({team}) has driven in *{safe_int(rbi_king, 'rbi')} runs* with only *{safe_int(rbi_king, 'hr')} home runs* — a pure product of his lineup.",
                "emoji": "🤝", "winner_id": rbi_king['player_id']
            }

        cs_leaders = [r for r in bat_overall if safe_int(r, 'cs') >= 3]
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

    pitch_rows = fetch_csv(pitch_api)
    pitch_overall = [r for r in pitch_rows if r.get('split_id') == '1']

    qualified_sp = [r for r in pitch_overall if safe_float(r, 'ip') >= 20 and safe_int(r, 'gs') >= 3]
    qualified_rp = [r for r in pitch_overall if safe_float(r, 'ip') >= 10 and safe_int(r, 'gs') == 0]

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

        gb_leaders = [r for r in qualified_sp if safe_int(r, 'ao') > 0]
        if gb_leaders:
            gb_king = max(gb_leaders, key=lambda r: safe_int(r, 'go') / max(safe_int(r, 'ao'), 1))
            go_ao = safe_int(gb_king, 'go') / max(safe_int(gb_king, 'ao'), 1)
            name, team = pname(gb_king['player_id'], gb_king['team_id'])
            all_oddities["worm_killer"] = {
                "text": f"🏔️ *Worm Killer:* {name} ({team}) has a *{go_ao:.2f} GO/AO ratio* — batters just keep beating it into the dirt.",
                "emoji": "🏔️", "winner_id": gb_king['player_id']
            }

        qs_leaders = [r for r in qualified_sp if safe_int(r, 'qs') >= 3]
        if qs_leaders:
            qs_king = max(qs_leaders, key=lambda r: safe_int(r, 'qs'))
            name, team = pname(qs_king['player_id'], qs_king['team_id'])
            gs = safe_int(qs_king, 'gs')
            qs = safe_int(qs_king, 'qs')
            all_oddities["mr_reliable"] = {
                "text": f"🎭 *Mr. Reliable:* {name} ({team}) has delivered *{qs} quality starts* in {gs} outings — the definition of a workhorse.",
                "emoji": "🎭", "winner_id": qs_king['player_id']
            }

        hr_allowed_leaders = [r for r in qualified_sp if safe_int(r, 'hr') >= 3]
        if hr_allowed_leaders:
            hr_allowed_king = max(hr_allowed_leaders, key=lambda r: safe_int(r, 'hr'))
            name, team = pname(hr_allowed_king['player_id'], hr_allowed_king['team_id'])
            all_oddities["hr_derby_pitcher"] = {
                "text": f"😤 *Home Run Derby Pitcher:* {name} ({team}) has surrendered *{safe_int(hr_allowed_king, 'hr')} home runs* — opposing hitters love facing this one.",
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
        sv_leaders = [r for r in qualified_rp if (safe_int(r, 's') + safe_int(r, 'bs')) >= 3]
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

        bs_leaders = [r for r in qualified_rp if safe_int(r, 'bs') >= 2]
        if bs_leaders:
            bs_king = max(bs_leaders, key=lambda r: safe_int(r, 'bs'))
            name, team = pname(bs_king['player_id'], bs_king['team_id'])
            all_oddities["blown_save_king"] = {
                "text": f"💥 *Blown Save King:* {name} ({team}) has blown *{safe_int(bs_king, 'bs')} saves* this season — opposing managers love seeing this reliever jog in.",
                "emoji": "💥", "winner_id": bs_king['player_id']
            }

    import random
    import json
    import os

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
    Returns analytics data for the Sim Analytics section.
    Rotates between three different storyline modes each sim:
      - Mode 0: Standard — Who's Hot/Cold (ELO) + Luckiest/Unluckiest (BaseRuns)
      - Mode 1: Rankings Shakeup — Biggest ELO movers + Luckiest/Unluckiest
      - Mode 2: Luck Focus — Lead with BaseRuns luck, Hot/Cold as secondary context
    State is persisted in state.json.
    """
    import json
    import os

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
        elo_url = f"{league_url.rstrip('/')}/elo/current/"
        biggest_gainer = hottest
        biggest_loser = coldest
        try:
            response = requests.get(elo_url)
            soup = BeautifulSoup(response.text, 'html.parser')
            table = soup.find('table')
            if table:
                teams_elo = []
                for row in table.find_all('tr')[1:]:
                    cols = [td.text.strip() for td in row.find_all('td')]
                    if len(cols) > 9:
                        team_name = get_full_team_name(cols[1])
                        try:
                            momentum = float(cols[9])
                            teams_elo.append({"team": team_name, "change": momentum})
                        except ValueError:
                            pass
                if teams_elo:
                    teams_elo.sort(key=lambda x: x['change'])
                    biggest_loser = teams_elo[0]
                    biggest_gainer = teams_elo[-1]
        except Exception as e:
            print(f"Error fetching ELO shakeup data: {e}")

        return {
            "mode": "rankings_shakeup",
            "biggest_gainer": biggest_gainer,
            "biggest_loser": biggest_loser,
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

def get_season_phase(league_url, best_pitcher, best_batter):
    """
    Determines the current season phase: 'regular', 'postseason', or 'offseason'.

    Logic:
      1. If both best_pitcher and best_batter are None → no games were played
         this sim → 'offseason'.
      2. Otherwise, scrape the recap page and search for known playoff round
         keywords in the page text. If found → 'postseason'.
      3. Otherwise → 'regular'.

    Returns one of: 'regular', 'postseason', 'offseason'
    """
    # Step 1: no game data → offseason
    if not best_pitcher and not best_batter:
        print("No game performances found — treating as offseason sim.")
        return "offseason"

    # Step 2: check recap page for playoff keywords (body content only, not nav)
    recap_url = f"{league_url.rstrip('/')}/recap/"
    try:
        resp = requests.get(recap_url, timeout=15)
        soup = BeautifulSoup(resp.text, 'html.parser')
        # Remove nav and footer to avoid false positives from "Playoff Odds" nav links
        for tag in soup.find_all(['nav', 'footer']):
            tag.decompose()
        body_text = soup.get_text(separator=' ').lower()
        for keyword in PLAYOFF_KEYWORDS:
            if keyword in body_text:
                print(f"Playoff keyword detected in recap body: '{keyword}' → postseason.")
                return "postseason"
    except Exception as e:
        print(f"Could not fetch recap page for phase detection: {e}")

    # Step 3: check OOTP scores report page title (e.g. "ALCS Game 3" vs "Scoreboard: August 13")
    scores_report_url = f"{REPORTS_BASE}/league_100_scores.html"
    try:
        resp = requests.get(scores_report_url, timeout=15)
        title = BeautifulSoup(resp.text, 'html.parser').find('title')
        if title:
            title_lower = title.get_text().lower()
            for keyword in PLAYOFF_KEYWORDS:
                if keyword in title_lower:
                    print(f"Playoff keyword in scores report title: '{keyword}' → postseason.")
                    return "postseason"
    except Exception as e:
        print(f"Could not fetch scores report for phase detection: {e}")

    return "regular"


def get_streaks_and_records(league_url, state):
    """
    Detects multi-sim team streaks and season stat records.

    Uses state['elo_history'] to track each team's last 3 ELO changes, and
    state['season_records'] to track season highs for key stats.

    Returns a list of callout strings to inject into the analytics section.
    """
    import csv
    import io

    callouts = []

    # --- Team Streaks via ELO history ---
    elo_url = f"{league_url.rstrip('/')}/elo/current/"
    try:
        response = requests.get(elo_url, timeout=15)
        soup = BeautifulSoup(response.text, 'html.parser')
        table = soup.find('table')
        if table:
            elo_history = state.get("elo_history", {})
            for row in table.find_all('tr')[1:]:
                cols = [td.text.strip() for td in row.find_all('td')]
                if len(cols) > 9:
                    team_name = get_full_team_name(cols[1])
                    try:
                        change = float(cols[9])
                    except ValueError:
                        continue
                    history = elo_history.get(team_name, [])
                    history.append(change)
                    elo_history[team_name] = history[-4:]  # keep last 4 sims

            state["elo_history"] = elo_history

            # Find teams on a hot/cold streak (3+ consecutive positive/negative)
            for team, history in elo_history.items():
                if len(history) >= 3:
                    recent = history[-3:]
                    if all(x > 0 for x in recent):
                        streak_len = len(history)
                        # Count from the end how many consecutive positives
                        streak_len = 0
                        for x in reversed(history):
                            if x > 0:
                                streak_len += 1
                            else:
                                break
                        if streak_len >= 3:
                            callouts.append(f"🔥 *Hot Streak:* The *{team}* have gained ELO in *{streak_len} straight sims* — the league's hottest team right now.")
                    elif all(x < 0 for x in recent):
                        streak_len = 0
                        for x in reversed(history):
                            if x < 0:
                                streak_len += 1
                            else:
                                break
                        if streak_len >= 3:
                            callouts.append(f"🧊 *Cold Streak:* The *{team}* have lost ELO in *{streak_len} straight sims* — in a serious funk.")
    except Exception as e:
        print(f"Error computing streaks: {e}")

    # --- Season Records via batting/pitching API ---
    bat_api = f"{league_url}/api/playerbatstatsv2/"
    pitch_api = f"{league_url}/api/playerpitchstatsv2/"
    players_api = f"{league_url}/api/players/"

    def fetch_csv(url):
        try:
            resp = requests.get(url, timeout=15)
            resp.raise_for_status()
            text = "\n".join(line for line in resp.text.splitlines() if line.strip())
            return list(csv.DictReader(io.StringIO(text)))
        except Exception as e:
            print(f"API fetch failed for {url}: {e}")
            return []

    def safe_int(d, key, default=0):
        try: return int(d.get(key, default) or default)
        except: return default

    def safe_float(d, key, default=0.0):
        try: return float(d.get(key, default) or default)
        except: return default

    player_rows = fetch_csv(players_api)
    player_names = {}
    for r in player_rows:
        pid = r.get('ID', '').strip()
        first = r.get('First Name', '').strip()
        last = r.get('Last Name', '').strip()
        if pid:
            player_names[pid] = f"{first} {last}".strip()

    def pname(pid):
        return player_names.get(str(pid), f"Player#{pid}")

    bat_rows = fetch_csv(bat_api)
    bat_overall = [r for r in bat_rows if r.get('split_id') == '1']
    pitch_rows = fetch_csv(pitch_api)
    pitch_overall = [r for r in pitch_rows if r.get('split_id') == '1']

    season_records = state.get("season_records", {})

    def check_record(key, player_name, value, emoji, label, higher_is_better=True):
        """Check if value is a new season record; returns callout string or None."""
        prev = season_records.get(key, {})
        prev_val = prev.get("value")
        is_new = prev_val is None or (higher_is_better and value > prev_val) or (not higher_is_better and value < prev_val)
        if is_new:
            season_records[key] = {"player": player_name, "value": value}
            if prev_val is not None:
                return f"{emoji} *New Season High!* {player_name} now leads the league in {label} with *{value}* (previous best: {prev_val})."
        return None

    # Check HR leader
    if bat_overall:
        hr_leader = max(bat_overall, key=lambda r: safe_int(r, 'hr'))
        hr_val = safe_int(hr_leader, 'hr')
        if hr_val > 0:
            note = check_record("most_hr", pname(hr_leader['player_id']), hr_val, "💣", "home runs")
            if note:
                callouts.append(note)

    # Check strikeout leader (pitchers)
    if pitch_overall:
        k_leader = max(pitch_overall, key=lambda r: safe_int(r, 'k'))
        k_val = safe_int(k_leader, 'k')
        if k_val > 0:
            note = check_record("most_k_pitcher", pname(k_leader['player_id']), k_val, "🔥", "strikeouts (pitcher)")
            if note:
                callouts.append(note)

    # Check ERA low (min 30 IP)
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
    return callouts[:2]  # Cap to 2 to keep the section tight


def get_milestone_countdowns(league_url):
    """
    Scans player career stats to find players approaching major milestones.
    Returns a list of countdown strings, capped at 3.
    """
    import csv
    import io

    bat_api = f"{league_url}/api/playerbatstatsv2/"
    pitch_api = f"{league_url}/api/playerpitchstatsv2/"
    players_api = f"{league_url}/api/players/"

    HIT_MILESTONES = [500, 1000, 1500, 2000, 2500, 3000]
    HR_MILESTONES = [100, 200, 300, 400, 500]
    WIN_MILESTONES = [100, 150, 200, 250, 300]
    K_MILESTONES = [500, 1000, 1500, 2000, 2500, 3000]
    SAVE_MILESTONES = [50, 100, 200, 300]
    LOOKAHEAD = 30  # only surface if within this many of the milestone

    def fetch_csv(url):
        try:
            resp = requests.get(url, timeout=15)
            resp.raise_for_status()
            text = "\n".join(line for line in resp.text.splitlines() if line.strip())
            return list(csv.DictReader(io.StringIO(text)))
        except Exception as e:
            print(f"API fetch failed for {url}: {e}")
            return []

    def safe_int(d, key, default=0):
        try: return int(d.get(key, default) or default)
        except: return default

    player_rows = fetch_csv(players_api)
    player_names = {}
    for r in player_rows:
        pid = r.get('ID', '').strip()
        first = r.get('First Name', '').strip()
        last = r.get('Last Name', '').strip()
        if pid:
            player_names[pid] = f"{first} {last}".strip()

    def pname(pid):
        return player_names.get(str(pid), f"Player#{pid}")

    countdowns = []

    # Use career split (split_id == '0') if available, fall back to overall
    bat_rows = fetch_csv(bat_api)
    career_bat = [r for r in bat_rows if r.get('split_id') == '0']
    if not career_bat:
        career_bat = [r for r in bat_rows if r.get('split_id') == '1']

    pitch_rows = fetch_csv(pitch_api)
    career_pitch = [r for r in pitch_rows if r.get('split_id') == '0']
    if not career_pitch:
        career_pitch = [r for r in pitch_rows if r.get('split_id') == '1']

    # Hits
    for r in career_bat:
        hits = safe_int(r, 'h')
        for milestone in HIT_MILESTONES:
            remaining = milestone - hits
            if 0 < remaining <= LOOKAHEAD:
                name = pname(r['player_id'])
                countdowns.append((remaining, f"🎯 *Milestone Watch:* {name} needs just *{remaining} more hits* to reach *{milestone:,} career hits*."))
                break

    # Home Runs
    for r in career_bat:
        hrs = safe_int(r, 'hr')
        for milestone in HR_MILESTONES:
            remaining = milestone - hrs
            if 0 < remaining <= LOOKAHEAD:
                name = pname(r['player_id'])
                countdowns.append((remaining, f"💣 *Milestone Watch:* {name} is *{remaining} home runs away* from *{milestone} career HR*."))
                break

    # Wins
    for r in career_pitch:
        wins = safe_int(r, 'w')
        for milestone in WIN_MILESTONES:
            remaining = milestone - wins
            if 0 < remaining <= LOOKAHEAD:
                name = pname(r['player_id'])
                countdowns.append((remaining, f"🏆 *Milestone Watch:* {name} needs *{remaining} more wins* to reach *{milestone} career wins*."))
                break

    # Strikeouts (pitchers)
    for r in career_pitch:
        ks = safe_int(r, 'k')
        for milestone in K_MILESTONES:
            remaining = milestone - ks
            if 0 < remaining <= LOOKAHEAD:
                name = pname(r['player_id'])
                countdowns.append((remaining, f"🔥 *Milestone Watch:* {name} is *{remaining} strikeouts away* from *{milestone:,} career Ks*."))
                break

    # Saves
    for r in career_pitch:
        saves = safe_int(r, 's')
        for milestone in SAVE_MILESTONES:
            remaining = milestone - saves
            if 0 < remaining <= LOOKAHEAD:
                name = pname(r['player_id'])
                countdowns.append((remaining, f"🔒 *Milestone Watch:* {name} needs *{remaining} more saves* to reach *{milestone} career saves*."))
                break

    # Sort by how close they are and cap at 3
    countdowns.sort(key=lambda x: x[0])
    return [text for _, text in countdowns[:3]]


def get_trivia_question(league_url, state):
    """
    Generates a blind stat trivia question from a notable player.
    Stores the answer in state for the next sim to reveal.
    Returns a dict with:
      - 'last_answer': the previous sim's answer (player name + hint), or None
      - 'question': the new blind stat question text
    """
    import csv
    import io
    import random

    bat_api = f"{league_url}/api/playerbatstatsv2/"
    pitch_api = f"{league_url}/api/playerpitchstatsv2/"
    players_api = f"{league_url}/api/players/"

    def fetch_csv(url):
        try:
            resp = requests.get(url, timeout=15)
            resp.raise_for_status()
            text = "\n".join(line for line in resp.text.splitlines() if line.strip())
            return list(csv.DictReader(io.StringIO(text)))
        except Exception as e:
            print(f"API fetch failed for {url}: {e}")
            return []

    def safe_int(d, key, default=0):
        try: return int(d.get(key, default) or default)
        except: return default

    def safe_float(d, key, default=0.0):
        try: return float(d.get(key, default) or default)
        except: return default

    player_rows = fetch_csv(players_api)
    player_names = {}
    for r in player_rows:
        pid = r.get('ID', '').strip()
        first = r.get('First Name', '').strip()
        last = r.get('Last Name', '').strip()
        if pid:
            player_names[pid] = f"{first} {last}".strip()

    def pname(pid):
        return player_names.get(str(pid), f"Player#{pid}")

    # Retrieve last sim's answer to reveal
    last_answer = state.get("trivia_answer")

    bat_rows = fetch_csv(bat_api)
    bat_overall = [r for r in bat_rows if r.get('split_id') == '1']
    pitch_rows = fetch_csv(pitch_api)
    pitch_overall = [r for r in pitch_rows if r.get('split_id') == '1']

    qualified_bat = [r for r in bat_overall if safe_int(r, 'pa') >= 150]
    qualified_sp = [r for r in pitch_overall if safe_float(r, 'ip') >= 30 and safe_int(r, 'gs') >= 5]

    candidates = []

    # Batter trivia candidates: top WAR, best AVG, worst AVG, most HR
    if qualified_bat:
        war_king = max(qualified_bat, key=lambda r: safe_float(r, 'war'))
        avg = safe_float(war_king, 'avg')
        hr = safe_int(war_king, 'hr')
        rbi = safe_int(war_king, 'rbi')
        war = safe_float(war_king, 'war')
        pa = safe_int(war_king, 'pa')
        q = f"This batter leads all position players with *{war:.1f} WAR*. They're hitting *.{int(avg*1000):03d}* with *{hr} HR* and *{rbi} RBI* in *{pa} PA*. Who is it? 🤔"
        candidates.append({"question": q, "answer": pname(war_king['player_id']), "type": "batter_war"})

        hr_king = max(qualified_bat, key=lambda r: safe_int(r, 'hr'))
        hrs = safe_int(hr_king, 'hr')
        avg2 = safe_float(hr_king, 'avg')
        rbi2 = safe_int(hr_king, 'rbi')
        obp = safe_float(hr_king, 'obp')
        q = f"This slugger leads the league with *{hrs} home runs*. They're batting *.{int(avg2*1000):03d}* with a *.{int(obp*1000):03d} OBP* and *{rbi2} RBI*. Who is it? 🤔"
        candidates.append({"question": q, "answer": pname(hr_king['player_id']), "type": "batter_hr"})

    def calc_era(r):
        ip = safe_float(r, 'ip')
        er = safe_float(r, 'er')
        return round((er / ip) * 9, 2) if ip > 0 else 0.0

    # Pitcher trivia candidates: best ERA, most K, most wins
    if qualified_sp:
        era_leader = min(qualified_sp, key=lambda r: calc_era(r) if calc_era(r) > 0 else 99)
        era = calc_era(era_leader)
        ks = safe_int(era_leader, 'k')
        wins = safe_int(era_leader, 'w')
        ip = safe_float(era_leader, 'ip')
        q = f"This starter has a *{era:.2f} ERA* and *{ks} strikeouts* over *{ip:.0f} innings* with *{wins} wins*. Who is it? 🤔"
        candidates.append({"question": q, "answer": pname(era_leader['player_id']), "type": "pitcher_era"})

        k_king = max(qualified_sp, key=lambda r: safe_int(r, 'k'))
        k_val = safe_int(k_king, 'k')
        era2 = calc_era(k_king)
        wins2 = safe_int(k_king, 'w')
        ip2 = safe_float(k_king, 'ip')
        q = f"This strikeout artist leads all starters with *{k_val} Ks* in *{ip2:.0f} IP*. Their ERA is *{era2:.2f}* and they have *{wins2} wins*. Who is it? 🤔"
        candidates.append({"question": q, "answer": pname(k_king['player_id']), "type": "pitcher_k"})

    if not candidates:
        return None

    # Avoid repeating the same player as last time
    last_type = state.get("trivia_answer", {}).get("type")
    fresh = [c for c in candidates if c["type"] != last_type]
    chosen = random.choice(fresh if fresh else candidates)

    state["trivia_answer"] = {
        "player_name": chosen["answer"],
        "question_text": chosen["question"],
        "type": chosen["type"]
    }

    return {
        "last_answer": last_answer,
        "question": chosen["question"]
    }


REPORTS_BASE = "https://statsplus.net/xfbl/reports/news/html/leagues"

def get_power_rankings(league_url="https://statsplus.net/xfbl"):
    """
    Scrapes the OOTP weekly power rankings from the league home report.
    Returns a list of dicts: {rank, team, points, trend}
    trend is one of: '++', '+', 'o', '-', '--'

    The home page contains a block like:
      1) Atlanta Braves (132.4, +)
      2) Tampa Bay Devil Rays (126.5, -)
    """
    report_url = f"{REPORTS_BASE}/league_100_home.html"
    try:
        resp = requests.get(report_url, timeout=15)
        soup = BeautifulSoup(resp.text, 'html.parser')
    except Exception as e:
        print(f"Could not fetch power rankings: {e}")
        return []

    # The rankings are inside a <td> as plain text lines like "1) Team Name (pts, trend)"
    rankings = []
    pattern = re.compile(r'^(\d+)\)\s+(.+?)\s+\((\d+\.?\d*),\s*([+\-o]+)\)$')

    for td in soup.find_all('td'):
        text = td.get_text(separator='\n')
        for line in text.split('\n'):
            line = line.strip()
            m = pattern.match(line)
            if m:
                rankings.append({
                    "rank": int(m.group(1)),
                    "team": m.group(2).strip(),
                    "points": float(m.group(3)),
                    "trend": m.group(4).strip()
                })

    if rankings:
        print(f"Power rankings: found {len(rankings)} teams.")
    return rankings


def get_offseason_transactions(league_url="https://statsplus.net/xfbl", max_days=7):
    """
    Scrapes the OOTP transactions report for roster moves since the last sim.
    Returns a list of dicts: {date, team, action}
    Limits to the most recent max_days worth of dated sections.
    """
    report_url = f"{REPORTS_BASE}/league_100_transactions_0_0.html"
    try:
        resp = requests.get(report_url, timeout=15)
        soup = BeautifulSoup(resp.text, 'html.parser')
    except Exception as e:
        print(f"Could not fetch transactions: {e}")
        return []

    transactions = []
    current_date = None
    days_seen = 0

    for table in soup.find_all('table', class_='data'):
        # Each <table class="data"> starts with a <th class="dl"> date header
        header = table.find('th', class_='dl')
        if header:
            current_date = header.get_text(strip=True)
            days_seen += 1
            if days_seen > max_days:
                break

        for td in table.find_all('td', class_=lambda c: c and 'dl' in c):
            text = td.get_text(separator=' ', strip=True)
            # Strip team name from linked text at start
            team_tag = td.find('a')
            team = team_tag.get_text(strip=True) if team_tag else "Unknown"
            # Remove leading "TeamName: " prefix
            action = re.sub(r'^[^:]+:\s*', '', text).strip()
            if action and current_date:
                transactions.append({
                    "date": current_date,
                    "team": team,
                    "action": action
                })

    print(f"Offseason transactions: found {len(transactions)} moves.")
    return transactions


if __name__ == "__main__":


    best_pitcher, best_batter = get_best_performances()
    print("Best Pitcher:", best_pitcher)
    print("Best Batter:", best_batter)
