import requests
import json

league_url = "https://statsplus.net/xfbl"
print("Checking Games API fields...")
r = requests.get(f"{league_url}/api/games/")
games = r.json()
if games:
    print(f"Total games: {len(games)}")
    print("Sample game fields:")
    print(json.dumps(games[0], indent=2))
else:
    print("No games found.")
