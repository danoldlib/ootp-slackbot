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
                    stat_line = f"IP: {stats[0]} | H: {stats[1]} | K: {stats[2]} | BB: {stats[3]} | HR: {stats[4]} | GS: {stats[6]}"
                    metric = f"{stats[-1]} Game Score"
                else:
                    stat_line = " | ".join(stats)
                    metric = f"{stats[-1]} Game Score" if stats else "Unknown"
            else:
                stats = [c.text.strip() for c in cols[6:]]
                if len(stats) >= 7:
                    stat_line = f"AB: {stats[0]} | R: {stats[1]} | H: {stats[2]} | HR: {stats[3]} | RBI: {stats[4]} | BB: {stats[5]} | K: {stats[6]}"
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

def get_milestones(league_url="https://statsplus.net/xfbl"):
    recap_url = f"{league_url.rstrip('/')}/recap/"
    try:
        response = requests.get(recap_url)
        soup = BeautifulSoup(response.text, 'html.parser')
    except Exception as e:
        print(f"Error fetching recap page: {e}")
        return []
    
    milestones = []
    panel = soup.find(id='recap-msg-panel')
    if not panel:
        return milestones
        
    for div in panel.find_all('div', class_='smallfont oneline'):
        text = " ".join(div.text.split())
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
                    milestones.append({
                        "name": name,
                        "team": team,
                        "amount": amount,
                        "stat": stat,
                        "full_text": text
                    })
    return milestones

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
            # Strip blank lines, which the API sometimes includes
            text = "\n".join(line for line in resp.text.splitlines() if line.strip())
            return list(csv.DictReader(io.StringIO(text)))
        except Exception as e:
            print(f"API fetch failed for {url}: {e}")
            return []

    # Build lookup dicts
    player_rows = fetch_csv(players_api)
    player_names = {r['player_id']: r['player_name'] for r in player_rows if 'player_id' in r and 'player_name' in r}

    team_rows = fetch_csv(teams_api)
    team_names = {r['team_id']: r['team_abbr'] for r in team_rows if 'team_id' in r and 'team_abbr' in r}

    def pname(pid, tid):
        return player_names.get(str(pid), f"Player#{pid}"), team_names.get(str(tid), f"T{tid}")

    # --- Batting oddities ---
    bat_rows = fetch_csv(bat_api)
    # Only use overall split (split_id == '1')
    bat_overall = [r for r in bat_rows if r.get('split_id') == '1']

    oddities = []

    def safe_int(d, key, default=0):
        try: return int(d.get(key, default) or default)
        except: return default

    def safe_float(d, key, default=0.0):
        try: return float(d.get(key, default) or default)
        except: return default

    # Qualified batters: at least 100 PA
    qualified_bat = [r for r in bat_overall if safe_int(r, 'pa') >= 100]

    if qualified_bat:
        # 1. K-rate King (most K per PA)
        k_king = max(qualified_bat, key=lambda r: safe_int(r, 'k') / max(safe_int(r, 'pa'), 1))
        k_rate = safe_int(k_king, 'k') / max(safe_int(k_king, 'pa'), 1)
        name, team = pname(k_king['player_id'], k_king['team_id'])
        oddities.append({
            "text": f"🎳 *K-Rate King:* {name} ({team}) strikes out *{k_rate:.0%}* of the time — {safe_int(k_king, 'k')} Ks in {safe_int(k_king, 'pa')} PA.",
            "emoji": "🎳"
        })

        # 2. Walk Machine (most BB per PA)
        bb_king = max(qualified_bat, key=lambda r: safe_int(r, 'bb') / max(safe_int(r, 'pa'), 1))
        bb_rate = safe_int(bb_king, 'bb') / max(safe_int(bb_king, 'pa'), 1)
        name, team = pname(bb_king['player_id'], bb_king['team_id'])
        oddities.append({
            "text": f"🚶 *Walk Machine:* {name} ({team}) draws a walk *{bb_rate:.0%}* of the time — {safe_int(bb_king, 'bb')} BBs this season.",
            "emoji": "🚶"
        })

        # 3. GIDP Machine (most double plays grounded into, min 10)
        gdp_leaders = [r for r in bat_overall if safe_int(r, 'gdp') >= 5]
        if gdp_leaders:
            gdp_king = max(gdp_leaders, key=lambda r: safe_int(r, 'gdp'))
            name, team = pname(gdp_king['player_id'], gdp_king['team_id'])
            oddities.append({
                "text": f"💀 *Double Play Machine:* {name} ({team}) has grounded into *{safe_int(gdp_king, 'gdp')} double plays* — the league's premier rally killer.",
                "emoji": "💀"
            })

        # 4. Best HR/AB rate among batters with at least 50 AB and 5 HR
        hr_rate_leaders = [r for r in bat_overall if safe_int(r, 'ab') >= 50 and safe_int(r, 'hr') >= 5]
        if hr_rate_leaders:
            hr_king = max(hr_rate_leaders, key=lambda r: safe_int(r, 'hr') / max(safe_int(r, 'ab'), 1))
            ab_per_hr = safe_int(hr_king, 'ab') / safe_int(hr_king, 'hr')
            name, team = pname(hr_king['player_id'], hr_king['team_id'])
            oddities.append({
                "text": f"💣 *HR Freak:* {name} ({team}) is going yard every *{ab_per_hr:.1f} ABs* with {safe_int(hr_king, 'hr')} homers already.",
                "emoji": "💣"
            })

        # 5. Stolen base leader
        sb_leaders = [r for r in bat_overall if safe_int(r, 'sb') >= 5]
        if sb_leaders:
            sb_king = max(sb_leaders, key=lambda r: safe_int(r, 'sb'))
            cs = safe_int(sb_king, 'cs')
            sb = safe_int(sb_king, 'sb')
            pct = sb / max(sb + cs, 1)
            name, team = pname(sb_king['player_id'], sb_king['team_id'])
            oddities.append({
                "text": f"🔫 *Speed Demon:* {name} ({team}) leads the league with *{sb} steals* (success rate: {pct:.0%}).",
                "emoji": "🔫"
            })

        # 6. Best WAR batter
        war_leaders = [r for r in bat_overall if safe_float(r, 'war') > 0]
        if war_leaders:
            war_king = max(war_leaders, key=lambda r: safe_float(r, 'war'))
            name, team = pname(war_king['player_id'], war_king['team_id'])
            oddities.append({
                "text": f"🏆 *Position Player WAR Leader:* {name} ({team}) paces the league with *{safe_float(war_king, 'war'):.1f} WAR*.",
                "emoji": "🏆"
            })

        # 7. Worst WPA batter (most negative, blame game)
        wpa_losers = [r for r in bat_overall if safe_float(r, 'wpa') < -0.5 and safe_int(r, 'pa') >= 100]
        if wpa_losers:
            wpa_loser = min(wpa_losers, key=lambda r: safe_float(r, 'wpa'))
            name, team = pname(wpa_loser['player_id'], wpa_loser['team_id'])
            oddities.append({
                "text": f"📉 *Clutch Kryptonite:* {name} ({team}) has been absolutely *crushing his team's win probability* with {safe_float(wpa_loser, 'wpa'):.2f} WPA.",
                "emoji": "📉"
            })

    # --- Pitching oddities ---
    pitch_rows = fetch_csv(pitch_api)
    pitch_overall = [r for r in pitch_rows if r.get('split_id') == '1']

    # Qualified starters: min 20 IP, at least 3 GS
    qualified_sp = [r for r in pitch_overall if safe_float(r, 'ip') >= 20 and safe_int(r, 'gs') >= 3]
    # Qualified relievers: min 10 IP, 0 GS
    qualified_rp = [r for r in pitch_overall if safe_float(r, 'ip') >= 10 and safe_int(r, 'gs') == 0]

    if qualified_sp:
        # 8. K/BF king (strikeout rate among starters)
        k_bf_king = max(qualified_sp, key=lambda r: safe_int(r, 'k') / max(safe_int(r, 'bf'), 1))
        k_bf_rate = safe_int(k_bf_king, 'k') / max(safe_int(k_bf_king, 'bf'), 1)
        name, team = pname(k_bf_king['player_id'], k_bf_king['team_id'])
        oddities.append({
            "text": f"🔥 *Swing-and-Miss SP:* {name} ({team}) is fanning *{k_bf_rate:.0%}* of batters faced — a terrifying arm.",
            "emoji": "🔥"
        })

        # 9. Best WAR pitcher
        war_leaders_p = [r for r in pitch_overall if safe_float(r, 'war') > 0]
        if war_leaders_p:
            war_king_p = max(war_leaders_p, key=lambda r: safe_float(r, 'war'))
            name, team = pname(war_king_p['player_id'], war_king_p['team_id'])
            oddities.append({
                "text": f"🎖️ *Pitcher WAR Leader:* {name} ({team}) leads all arms with *{safe_float(war_king_p, 'war'):.1f} WAR*.",
                "emoji": "🎖️"
            })

        # 10. Walk problem SP (most BB, min 20 IP)
        bb_problem = max(qualified_sp, key=lambda r: safe_int(r, 'bb') / max(safe_float(r, 'ip'), 1))
        bb_per_9 = safe_int(bb_problem, 'bb') / max(safe_float(bb_problem, 'ip'), 1) * 9
        name, team = pname(bb_problem['player_id'], bb_problem['team_id'])
        oddities.append({
            "text": f"😬 *Control Issues:* {name} ({team}) is issuing *{bb_per_9:.1f} walks per 9 innings* — somebody get them the strike zone.",
            "emoji": "😬"
        })

    if qualified_rp:
        # 11. Best save% reliever
        sv_leaders = [r for r in qualified_rp if (safe_int(r, 's') + safe_int(r, 'bs')) >= 3]
        if sv_leaders:
            sv_king = max(sv_leaders, key=lambda r: safe_int(r, 's') / max(safe_int(r, 's') + safe_int(r, 'bs'), 1))
            svs = safe_int(sv_king, 's')
            bsv = safe_int(sv_king, 'bs')
            name, team = pname(sv_king['player_id'], sv_king['team_id'])
            if svs > 0:
                oddities.append({
                    "text": f"🔒 *Closer of the Year:* {name} ({team}) has been *{svs}-for-{svs+bsv}* in save opportunities.",
                    "emoji": "🔒"
                })

    # Shuffle for variety and cap at 4 to avoid overloading the digest
    import random
    random.shuffle(oddities)
    return oddities[:4]


if __name__ == "__main__":

    best_pitcher, best_batter = get_best_performances()
    print("Best Pitcher:", best_pitcher)
    print("Best Batter:", best_batter)
