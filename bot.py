import os
import re
from dotenv import load_dotenv
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from scraper import get_best_performances, get_milestones, get_team_momentum, get_team_luck, get_close_division_races

# Load environment variables
load_dotenv()

SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")
SLACK_CHANNEL_ID = os.getenv("SLACK_CHANNEL_ID")
LEAGUE_URL = os.getenv("LEAGUE_URL", "https://statsplus.net/xfbl")
DAYS_BACK = int(os.getenv("DAYS_BACK", "7"))

def post_sim_header(summary_text=""):
    """
    Posts the main header to the channel and returns the thread_ts for threaded replies.
    """
    if not SLACK_BOT_TOKEN or not SLACK_CHANNEL_ID:
        print("Missing Slack configuration. Cannot post to Slack.")
        return None
        
    client = WebClient(token=SLACK_BOT_TOKEN)
    text = f"⚾ *XFBL Sim Complete!* Expand this thread for your recap...\n_{summary_text}_"
    try:
        result = client.chat_postMessage(
            channel=SLACK_CHANNEL_ID,
            text=text
        )
        return result['ts']
    except SlackApiError as e:
        print(f"Error posting header to Slack: {e.response['error']}")
        return None

def post_to_slack(performance, title, thread_ts=None):
    """
    Constructs a Block Kit payload and posts it to Slack.
    """
    if not SLACK_BOT_TOKEN or not SLACK_CHANNEL_ID:
         return
         
    client = WebClient(token=SLACK_BOT_TOKEN)
    stats_table = performance['stat_line']
    
    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"🔥 {title}: {performance['name']} 🔥",
                "emoji": True
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
            "type": "divider"
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*{performance['name']}* ({performance['team']}) put on an absolute clinic.\n\n*Stat Line:*\n`{stats_table}`"
            }
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
                    "action_id": "btn_box_score"
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
            "action_id": "btn_profile"
        })

    try:
        client.chat_postMessage(
            channel=SLACK_CHANNEL_ID,
            thread_ts=thread_ts,
            blocks=blocks,
            text=f"{title}: {performance['name']}"
        )
        print("Successfully posted to Slack!")
    except SlackApiError as e:
        print(f"Error posting to Slack: {e.response['error']}")

def post_milestones_to_slack(milestones, thread_ts=None):
    if not milestones or not SLACK_BOT_TOKEN or not SLACK_CHANNEL_ID:
        return
        
    client = WebClient(token=SLACK_BOT_TOKEN)
    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": "🏆 Sim Recap Highlights 🏆",
                "emoji": True
            }
        },
        {
            "type": "divider"
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
        
    try:
        client.chat_postMessage(
            channel=SLACK_CHANNEL_ID,
            thread_ts=thread_ts,
            blocks=blocks,
            text="Sim Recap Highlights"
        )
        print("Successfully posted milestones to Slack!")
    except SlackApiError as e:
        print(f"Error posting milestones to Slack: {e.response['error']}")

def post_analytics_to_slack(hottest, coldest, luckiest, unluckiest, thread_ts=None):
    if not SLACK_BOT_TOKEN or not SLACK_CHANNEL_ID or not hottest or not luckiest:
        return
        
    client = WebClient(token=SLACK_BOT_TOKEN)
    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": "📊 Sim Analytics & Trends 📊",
                "emoji": True
            }
        },
        {
            "type": "divider"
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
        }
    ]
    
    try:
        client.chat_postMessage(
            channel=SLACK_CHANNEL_ID,
            thread_ts=thread_ts,
            blocks=blocks,
            text="Sim Analytics & Trends"
        )
        print("Successfully posted analytics to Slack!")
    except SlackApiError as e:
        print(f"Error posting analytics to Slack: {e.response['error']}")

def post_division_races_to_slack(races, thread_ts=None):
    if not races or not SLACK_BOT_TOKEN or not SLACK_CHANNEL_ID:
        return
        
    client = WebClient(token=SLACK_BOT_TOKEN)
    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": "🏁 Pennant Race Watch 🏁",
                "emoji": True
            }
        },
        {
            "type": "divider"
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
        
    try:
        client.chat_postMessage(
            channel=SLACK_CHANNEL_ID,
            thread_ts=thread_ts,
            blocks=blocks,
            text="Pennant Race Watch"
        )
        print("Successfully posted division races to Slack!")
    except SlackApiError as e:
        print(f"Error posting division races to Slack: {e.response['error']}")


def main():
    print(f"Fetching best performances from StatsPlus ({DAYS_BACK} days back)...")
    best_pitcher, best_batter = get_best_performances(LEAGUE_URL, DAYS_BACK)
    
    print(f"Fetching milestones from StatsPlus recap...")
    milestones = get_milestones(LEAGUE_URL)
    
    print(f"Fetching team analytics...")
    hottest, coldest = get_team_momentum(LEAGUE_URL)
    luckiest, unluckiest = get_team_luck(LEAGUE_URL)
    
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
        
    summary_text = "Includes: " + ", ".join(summary_parts) if summary_parts else "No notable updates this sim."

    print("Posting Sim Header...")
    thread_ts = post_sim_header(summary_text)
    
    if not thread_ts:
        print("Failed to start thread. Posting individually.")

    if best_pitcher:
        print(f"Best Pitcher Found: {best_pitcher['name']}")
        post_to_slack(best_pitcher, "Pitcher of the Sim", thread_ts)
    else:
        print("No pitching performance found in timeframe.")
        
    if best_batter:
        print(f"Best Batter Found: {best_batter['name']}")
        post_to_slack(best_batter, "Batter of the Sim", thread_ts)
    else:
        print("No batting performance found in timeframe.")

    if milestones:
        print(f"Found {len(milestones)} impressive milestones.")
        post_milestones_to_slack(milestones, thread_ts)
    else:
        print("No impressive milestones found.")

    if hottest and luckiest:
        print("Team analytics found.")
        post_analytics_to_slack(hottest, coldest, luckiest, unluckiest, thread_ts)
    else:
        print("Could not fetch complete team analytics.")
        
    if races:
        print(f"Found {len(races)} close division races.")
        post_division_races_to_slack(races, thread_ts)
    else:
        print("No close division races found.")

if __name__ == "__main__":
    main()
