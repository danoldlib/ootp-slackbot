import requests
from bs4 import BeautifulSoup
import json

league_url = "https://statsplus.net/xfbl"
recap_url = f"{league_url}/recap/"
print(f"Fetching {recap_url}")
response = requests.get(recap_url)
soup = BeautifulSoup(response.text, 'html.parser')
panel = soup.find(id='recap-msg-panel')

if panel:
    texts = [div.text.strip() for div in panel.find_all('div', class_='smallfont oneline')]
    print("Recap messages:")
    for t in texts[:20]:
        print("-", t)
else:
    print("No recap panel found.")

# Let's also check if there's an API for games
print("\nChecking APIs...")
try:
    r = requests.get(f"{league_url}/api/games/")
    if r.status_code == 200:
        print("Games API works!")
    else:
        print("Games API returned:", r.status_code)
except Exception as e:
    print("Games API error:", e)

