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
    
    blocks = [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"🔥 *{title}: {performance['name']}*\n*{performance['name']}* ({performance['team']}) put on an absolute clinic.\n`{stats_table}`"
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
    if races:
        all_blocks.extend(build_division_races_blocks(races))
        
    # Remove the very last divider if it exists
    if all_blocks and all_blocks[-1].get("type") == "divider":
        all_blocks.pop()

    print(f"Posting Daily Digest to Slack ({len(all_blocks)} blocks)...")
    post_daily_digest(all_blocks)

if __name__ == "__main__":
    main()
