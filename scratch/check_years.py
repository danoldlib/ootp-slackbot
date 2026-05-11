import requests
import io
import pandas as pd

urls = [
    "https://statsplus.net/xfbl/api/playerbatstatsv2/",
    "https://statsplus.net/xfbl/api/playerpitchstatsv2/"
]

for url in urls:
    print(f"\n--- {url} ---")
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        df = pd.read_csv(io.StringIO(resp.text))
        if 'year' in df.columns:
            print("Unique years:", df['year'].unique().tolist())
        else:
            print("No year column found.")
    except Exception as e:
        print(f"Error: {e}")
