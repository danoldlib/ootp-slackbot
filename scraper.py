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
                "player_id": player_id,
                "date": game_date.strftime('%Y-%m-%d'),
                "stat_line": stat_line,
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

if __name__ == "__main__":
    best_pitcher, best_batter = get_best_performances()
    print("Best Pitcher:", best_pitcher)
    print("Best Batter:", best_batter)
