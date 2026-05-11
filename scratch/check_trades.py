import requests
import io
import pandas as pd

url = "https://statsplus.net/xfbl/api/playerbatstatsv2/"

try:
    resp = requests.get(url, timeout=10)
    resp.raise_for_status()
    df = pd.read_csv(io.StringIO(resp.text))
    overall = df[df['split_id'] == 1]
    dupes = overall[overall.duplicated('player_id', keep=False)]
    if not dupes.empty:
        print("Traded players found (multiple rows for same player_id):")
        print(dupes[['player_id', 'team_id', 'pa', 'war']].head(10))
    else:
        print("No duplicate player_ids found in overall stats.")
except Exception as e:
    print(f"Error: {e}")
