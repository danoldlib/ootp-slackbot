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
        print("Unique split_id:", df['split_id'].unique().tolist())
        # Let's see some sample data for split_id 1 vs others
        sample = df[df['split_id'] == 1].head(1)
        if not sample.empty:
            print("Sample for split_id 1 (PA/IP):", sample[['pa', 'ab']].iloc[0].to_dict() if 'pa' in sample.columns else sample[['ip', 'bf']].iloc[0].to_dict())
    except Exception as e:
        print(f"Error: {e}")
