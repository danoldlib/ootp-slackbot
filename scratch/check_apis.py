import requests
import io
import pandas as pd

urls = [
    "https://statsplus.net/xfbl/api/playerbatstatsv2/",
    "https://statsplus.net/xfbl/api/playerpitchstatsv2/",
    "https://statsplus.net/xfbl/api/players/",
    "https://statsplus.net/xfbl/api/teams/"
]

for url in urls:
    print(f"\n--- {url} ---")
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        # Use pandas to read the first row to get headers
        df = pd.read_csv(io.StringIO(resp.text), nrows=0)
        print("Columns:", df.columns.tolist())
    except Exception as e:
        print(f"Error: {e}")
