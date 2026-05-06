import requests
from bs4 import BeautifulSoup

league_url = "https://statsplus.net/xfbl"
res = requests.get(f"{league_url}/elo/current/")
soup = BeautifulSoup(res.text, "html.parser")
table = soup.find('table')
for row in table.find_all('tr')[1:3]:
    td = row.find_all('td')[1]
    print("TD raw html:")
    print(td)
    a = td.find('a')
    if a:
        print("A tag:", a)
