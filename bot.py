import os
import re
from dotenv import load_dotenv
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
import time
import sys
from scraper import get_best_performances, get_milestones, get_team_momentum, get_team_luck, get_close_division_races, get_notable_games, get_api_oddities

# Load environment variables
load_dotenv()

SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")
SLACK_APP_TOKEN = os.getenv("SLACK_APP_TOKEN")
SLACK_CHANNEL_ID = os.getenv("SLACK_CHANNEL_ID")
LEAGUE_URL = os.getenv("LEAGUE_URL", "https://statsplus.net/xfbl")
DAYS_BACK = int(os.getenv("DAYS_BACK", "7"))

app = App(token=SLACK_BOT_TOKEN)

def build_sim_header_blocks(summary_text=""):
    return [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": "📰 XFBL Daily Digest: Sim Complete!",
                "emoji": True
            }
        },
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": f"_{summary_text}_"
                }
            ]
        },
        {
            "type": "divider"
        }
    ]

def build_performance_blocks(performance, title):
    stats_table = performance['stat_line']
    stats = performance.get('stats', [])
    opponent = performance.get('opponent', '???')
    
    # Generate a contextual blurb from the actual stats
    if performance.get('is_pitcher') and len(stats) >= 7:
        try:
            ip = stats[0]
            hits = stats[1]
            ks = stats[2]
            bbs = stats[3]
            hrs = stats[4]
            gs = stats[6]
            blurb = f"Threw *{ip} innings* against {opponent}, striking out *{ks}* with only *{bbs} walks* and allowing *{hits} hits*. Game Score: *{gs}*."
        except (IndexError, ValueError):
            blurb = f"Dominated the opposition vs {opponent}."
    elif not performance.get('is_pitcher') and len(stats) >= 7:
        try:
            h = stats[2]
            ab = stats[0]
            hrs = int(stats[3])
            rbi = stats[4]
            bbs = stats[5]
            hr_str = f" *{hrs} home run{'s' if hrs != 1 else ''}* and" if hrs > 0 else ""
            blurb = f"Went *{h}-for-{ab}* vs {opponent} with{hr_str} *{rbi} RBI*."
        except (IndexError, ValueError):
            blurb = f"Had a monster game vs {opponent}."
    else:
        blurb = f"Put on a show vs {opponent}."

    blocks = [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"🔥 *{title}: {performance['name']}*\n*{performance['name']}* ({performance['team']}) {blurb}\n`{stats_table}`"
            }
        },
        {
            "type": "context",
            "elements": [
                {
                    "type": "plain_text",
                    "text": f"Game Date: {performance['date']} | Metric: {performance['metric']}",
                    "emoji": True
                }
            ]
        },
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "text": "View Box Score",
                        "emoji": True
                    },
                    "url": performance['box_url'],
                    "action_id": f"btn_box_{performance['name'].replace(' ', '_')}"
                }
            ]
        }
    ]
    
    if performance.get('player_id'):
        blocks[-1]['elements'].append({
            "type": "button",
            "text": {
                "type": "plain_text",
                "text": "Player Profile",
                "emoji": True
            },
            "url": f"{LEAGUE_URL}/player/{performance['player_id']}",
            "action_id": f"btn_prof_{performance['player_id']}"
        })

    blocks.append({"type": "divider"})
    return blocks

def build_milestones_blocks(milestones):
    if not milestones:
        return []
        
    blocks = [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "🏆 *Sim Highlights & Milestones*"
            }
        }
    ]
    
    for milestone in milestones:
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"• *{milestone['name']}* ({milestone['team']}) reached *{milestone['amount']} {milestone['stat']}*"
            }
        })
        
    blocks.append({"type": "divider"})
    return blocks

def build_analytics_blocks(hottest, coldest, luckiest, unluckiest):
    if not hottest or not luckiest:
        return []
        
    blocks = [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "📊 *Sim Analytics & Trends*"
            }
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"🔥 *Who's Hot*: The *{hottest['team']}* surged this sim, gaining *+{hottest['change']}* ELO points.\n🧊 *Who's Not*: The *{coldest['team']}* collapsed, dropping *{coldest['change']}* ELO points."
            }
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"🍀 *Luckiest Team*: The *{luckiest['team']}* have *+{luckiest['luck']}* more wins than their BaseRuns predict ({luckiest['actual']} actual vs {luckiest['expected']} expected).\n🌩️ *Unluckiest Team*: The *{unluckiest['team']}* have *{unluckiest['luck']}* fewer wins than their BaseRuns predict ({unluckiest['actual']} actual vs {unluckiest['expected']} expected)."
            }
        },
        {
            "type": "divider"
        }
    ]
    
    return blocks

def build_notable_games_blocks(notable_games):
    if not notable_games:
        return []

    blocks = [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "🗞️ *Weird Sim: Notable Moments*"
            }
        }
    ]

    for game in notable_games:
        block = {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": game['text']
            }
        }
        if game.get('box_url'):
            block["accessory"] = {
                "type": "button",
                "text": {"type": "plain_text", "text": "Box Score", "emoji": True},
                "url": game['box_url'],
                "action_id": f"btn_notable_{notable_games.index(game)}"
            }
        blocks.append(block)

    blocks.append({"type": "divider"})
    return blocks

def build_api_oddities_blocks(oddities):
    if not oddities:
        return []

    blocks = [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "📊 *By the Numbers: League Oddities*"
            }
        }
    ]

    for item in oddities:
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": item['text']
            }
        })

    blocks.append({"type": "divider"})
    return blocks


def build_division_races_blocks(races):
    if not races:
        return []
        
    blocks = [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "🏁 *Pennant Race Watch*"
            }
        }
    ]
    
    for race in races:
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*{race['division']}*: The *{race['second_place']}* are trailing the *{race['first_place']}* by just *{race['gb']}* games!"
            }
        })
        
    return blocks

def post_daily_digest(blocks):
    if not SLACK_BOT_TOKEN or not SLACK_CHANNEL_ID:
        print("Missing Slack configuration. Cannot post to Slack.")
        return
        
    client = WebClient(token=SLACK_BOT_TOKEN)
    
    try:
        client.chat_postMessage(
            channel=SLACK_CHANNEL_ID,
            blocks=blocks,
            text="📰 XFBL Daily Digest: Sim Complete!"
        )
        print("Successfully posted daily digest to Slack!")
    except SlackApiError as e:
        print(f"Error posting daily digest to Slack: {e.response['error']}")

def trigger_daily_digest():
    print(f"Fetching best performances from StatsPlus ({DAYS_BACK} days back)...")
    best_pitcher, best_batter = get_best_performances(LEAGUE_URL, DAYS_BACK)
    
    print(f"Fetching milestones from StatsPlus recap...")
    milestones = get_milestones(LEAGUE_URL)
    
    print(f"Fetching team analytics...")
    hottest, coldest = get_team_momentum(LEAGUE_URL)
    luckiest, unluckiest = get_team_luck(LEAGUE_URL)
    
    print(f"Fetching API oddities...")
    api_oddities = get_api_oddities(LEAGUE_URL)

    print(f"Fetching notable/weird games...")
    notable_games = get_notable_games(LEAGUE_URL, DAYS_BACK)
    print(f"Fetching close division races...")
    races = get_close_division_races(LEAGUE_URL)

    # Build summary text
    summary_parts = []
    if best_pitcher or best_batter:
        summary_parts.append("Play of the Week")
    if milestones:
        summary_parts.append(f"{len(milestones)} Milestones")
    if hottest:
        summary_parts.append("Team Analytics")
    if races:
        summary_parts.append(f"{len(races)} Pennant Races")
    if notable_games:
        summary_parts.append(f"{len(notable_games)} Weird Moments")
    if api_oddities:
        summary_parts.append(f"{len(api_oddities)} League Stats")
        
    summary_text = "Includes: " + ", ".join(summary_parts) if summary_parts else "No notable updates this sim."

    print("Building Daily Digest blocks...")
    all_blocks = []
    all_blocks.extend(build_sim_header_blocks(summary_text))
    
    if best_pitcher:
        all_blocks.extend(build_performance_blocks(best_pitcher, "Pitcher of the Sim"))
    if best_batter:
        all_blocks.extend(build_performance_blocks(best_batter, "Batter of the Sim"))
    if milestones:
        all_blocks.extend(build_milestones_blocks(milestones))
    if hottest and luckiest:
        all_blocks.extend(build_analytics_blocks(hottest, coldest, luckiest, unluckiest))
    if api_oddities:
        all_blocks.extend(build_api_oddities_blocks(api_oddities))
    if notable_games:
        all_blocks.extend(build_notable_games_blocks(notable_games))
    if races:
        all_blocks.extend(build_division_races_blocks(races))
        
    # Remove the very last divider if it exists
    if all_blocks and all_blocks[-1].get("type") == "divider":
        all_blocks.pop()

    print(f"Posting Daily Digest to Slack ({len(all_blocks)} blocks)...")
    post_daily_digest(all_blocks)

@app.message(re.compile(r"StatsPlus.*updated", re.IGNORECASE))
def handle_sim_complete(message, say):
    print(f"✅ MATCH FOUND: {message.get('text')}")
    print("🚀 Detected StatsPlus update message! Waiting 3 minutes before scraping...")
    time.sleep(180)
    trigger_daily_digest()

@app.event("message")
def handle_message_events(body, logger):
    # This captures all messages for debugging purposes
    event = body.get("event", {})
    text = event.get("text")
    subtype = event.get("subtype")
    
    if subtype == "channel_join" or subtype == "channel_leave":
        return # Quietly ignore join/leave messages
        
    if text:
        print(f"📩 Message received: {text}")
    elif event.get("blocks"):
        print(f"📦 Block message received (Subtype: {subtype})")

def main():
    if not SLACK_APP_TOKEN or not SLACK_BOT_TOKEN:
        print("Missing SLACK_APP_TOKEN or SLACK_BOT_TOKEN. Cannot start Socket Mode.")
        return
        
    print("Starting Slack bot in Socket Mode...")
    handler = SocketModeHandler(app, SLACK_APP_TOKEN)
    handler.start()

if __name__ == "__main__":
    if "--manual" in sys.argv:
        print("🚀 Manual override detected. Running Daily Digest immediately...")
        trigger_daily_digest()
    else:
        main()
