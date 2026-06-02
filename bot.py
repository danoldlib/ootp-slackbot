import os
import re
import threading
from dotenv import load_dotenv
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
import time
import sys
from scraper import (
    get_best_performances, get_headlines_and_milestones,
    get_team_momentum, get_team_luck, get_close_division_races,
    get_notable_games, get_api_oddities, get_sim_analytics,
    get_streaks_and_records, get_milestone_countdowns, get_trivia_question,
    get_season_phase, get_power_rankings, get_offseason_transactions,
    get_playoff_odds
)

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
            # stats mapping: 0:IP, 1:R, 2:H, 3:HR, 4:BB, 5:K, 6:GS
            ip = stats[0]
            hits = stats[2]
            ks = stats[5]
            bbs = stats[4]
            hrs = stats[3]
            gs = stats[6]
            blurb = f"Threw *{ip} innings* against {opponent}, striking out *{ks}* with only *{bbs} walks* and allowing *{hits} hits*. Game Score: *{gs}*."
        except (IndexError, ValueError):
            blurb = f"Dominated the opposition vs {opponent}."
    elif not performance.get('is_pitcher') and len(stats) >= 7:
        try:
            # stats mapping: 0:AB, 1:H, 2:RBI, 3:HR, 4:R, 5:BB, 6:GS
            h = stats[1]
            ab = stats[0]
            hrs = int(stats[3])
            rbi = stats[2]
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

def build_headlines_blocks(headlines):
    if not headlines:
        return []
        
    headlines_text = "\n".join([f"• {h}" for h in headlines])
        
    blocks = [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"🏆 *Sim Highlights & Headlines*\n{headlines_text}"
            }
        },
        {"type": "divider"}
    ]
    
    return blocks

def build_analytics_blocks(analytics_data, streak_callouts=None, milestones=None):
    """
    Builds the Sim Analytics & Trends section.
    Accepts the dict from get_sim_analytics() and renders the correct mode.
    Optionally appends streak callouts and milestone countdowns.
    """
    if not analytics_data:
        return []

    mode = analytics_data.get("mode", "standard")
    blocks = []

    if mode == "standard":
        hottest = analytics_data.get("hottest")
        coldest = analytics_data.get("coldest")
        luckiest = analytics_data.get("luckiest")
        unluckiest = analytics_data.get("unluckiest")
        if not hottest or not luckiest:
            return []
        blocks = [
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": "📊 *Sim Analytics & Trends*"}
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
        ]

    elif mode == "rankings_shakeup":
        gainer = analytics_data.get("biggest_gainer")
        loser = analytics_data.get("biggest_loser")
        luckiest = analytics_data.get("luckiest")
        unluckiest = analytics_data.get("unluckiest")
        if not gainer or not luckiest:
            return []
        blocks = [
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": "📊 *Sim Analytics & Trends: Rankings Shakeup Edition*"}
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"📈 *Biggest Climber*: The *{gainer['team']}* made the biggest jump this sim, gaining *+{gainer['change']}* ELO points.\n📉 *Biggest Faller*: The *{loser['team']}* took the hardest hit, dropping *{loser['change']}* ELO points."
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"🍀 *Running Lucky*: The *{luckiest['team']}* still have *+{luckiest['luck']}* more wins than BaseRuns predicts ({luckiest['actual']} actual vs {luckiest['expected']} expected).\n🌩️ *Still Getting Robbed*: The *{unluckiest['team']}* remain *{unluckiest['luck']}* wins below their BaseRuns expectation."
                }
            },
        ]

    elif mode == "luck_focus":
        hottest = analytics_data.get("hottest")
        coldest = analytics_data.get("coldest")
        luckiest = analytics_data.get("luckiest")
        unluckiest = analytics_data.get("unluckiest")
        if not luckiest:
            return []
        blocks = [
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": "📊 *Sim Analytics & Trends: Luck Report*"}
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f"⚖️ *BaseRuns Luck Standings* — who's been blessed and who's been robbed:\n"
                        f"🍀 *{luckiest['team']}*: *+{luckiest['luck']}* wins above expectation ({luckiest['actual']} actual vs {luckiest['expected']} expected) — riding some serious fortune.\n"
                        f"🌩️ *{unluckiest['team']}*: *{unluckiest['luck']}* wins below expectation ({unluckiest['actual']} actual vs {unluckiest['expected']} expected) — the simulation engine has been brutal."
                    )
                }
            },
        ]
        if hottest and coldest:
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"🔥 *Momentum Check*: {hottest['team']} (+{hottest['change']} ELO) trending up, {coldest['team']} ({coldest['change']} ELO) trending down."
                }
            })

    # Append streak callouts
    if streak_callouts:
        for callout in streak_callouts:
            blocks.append({
                "type": "section",
                "text": {"type": "mrkdwn", "text": callout}
            })

    # Append milestone countdowns
    if milestones:
        milestones_text = "\n".join(milestones)
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": milestones_text}
        })

    blocks.append({"type": "divider"})
    return blocks


def build_trivia_blocks(trivia):
    """
    Builds the trivia section. Reveals the previous sim's answer if available,
    then posts the new blind stat challenge.
    """
    if not trivia:
        return []

    blocks = []
    last_answer = trivia.get("last_answer")

    if last_answer:
        player_name = last_answer.get("player_name", "Unknown")
        prev_question = last_answer.get("question_text", "")
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"❓ *Last Sim's Trivia Answer:* The answer was *{player_name}*!\n_{prev_question}_"
            }
        })

    blocks.append({
        "type": "section",
        "text": {
            "type": "mrkdwn",
            "text": f"🧩 *Guess the Player!*\n{trivia['question']}\n_Reply in thread with your guess — answer revealed next sim!_"
        }
    })
    blocks.append({"type": "divider"})
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

def build_playoff_odds_blocks(odds_data):
    if not odds_data:
        return []

    blocks = [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "🔮 *Postseason Projections & Playoff Odds*"
            }
        }
    ]

    al_lines = []
    nl_lines = []

    # 1. American League (AL)
    al_data = odds_data.get("AL", {})
    al_bubble = al_data.get("bubble", [])
    al_contenders = al_data.get("contenders", [])

    if al_bubble or al_contenders:
        al_lines.append("*🇺🇸 American League*")
        
        # Show bubble teams (up to 4)
        if al_bubble:
            al_lines.append("  _On the Bubble:_")
            for t in al_bubble[:4]:
                al_lines.append(f"  • *{t['team']}*: *{t['po_pct']:.1f}%* PO (Proj: {t['avg_w']:.1f}-{t['avg_l']:.1f})")
                
        # Show top contenders (briefly)
        if al_contenders:
            contender_names = [f"*{t['team']}* ({t['po_pct']:.0f}%)" for t in al_contenders[:3]]
            al_lines.append(f"  _Heavy Favorites:_ {', '.join(contender_names)}")

    # 2. National League (NL)
    nl_data = odds_data.get("NL", {})
    nl_bubble = nl_data.get("bubble", [])
    nl_contenders = nl_data.get("contenders", [])

    if nl_bubble or nl_contenders:
        nl_lines.append("*🇪🇺 National League*")
        
        # Show bubble teams (up to 4)
        if nl_bubble:
            nl_lines.append("  _On the Bubble:_")
            for t in nl_bubble[:4]:
                nl_lines.append(f"  • *{t['team']}*: *{t['po_pct']:.1f}%* PO (Proj: {t['avg_w']:.1f}-{t['avg_l']:.1f})")
                
        # Show top contenders (briefly)
        if nl_contenders:
            contender_names = [f"*{t['team']}* ({t['po_pct']:.0f}%)" for t in nl_contenders[:3]]
            nl_lines.append(f"  _Heavy Favorites:_ {', '.join(contender_names)}")

    # Combine text blocks
    text_content = ""
    if al_lines:
        text_content += "\n".join(al_lines)
    if nl_lines:
        if text_content:
            text_content += "\n\n"
        text_content += "\n".join(nl_lines)

    if text_content:
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": text_content
            }
        })
        blocks.append({"type": "divider"})

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

def build_power_rankings_blocks(rankings):
    """
    Builds a Slack block for the OOTP weekly power rankings.
    Shows the top 5 and bottom 5, highlighting big movers (++ or --).
    """
    if not rankings:
        return []

    trend_emoji = {"++": "🔥", "+": "📈", "o": "➡️", "-": "📉", "--": "❄️"}

    # Top 5 risers/fallers first
    big_movers = [r for r in rankings if r["trend"] in ("++", "--")]
    top5 = rankings[:5]
    bottom5 = rankings[-5:]

    def fmt(r):
        emoji = trend_emoji.get(r["trend"], "")
        return f"{emoji} *{r['rank']}.* {r['team']} ({r['points']:.1f} pts)"

    lines = ["*📊 Weekly Power Rankings*", ""]
    lines.append("_Top of the league:_")
    lines += [fmt(r) for r in top5]
    lines.append("")
    lines.append("_Struggling:_")
    lines += [fmt(r) for r in bottom5]

    if big_movers:
        lines.append("")
        lines.append("_Big movers this sim:_")
        for r in big_movers:
            direction = "🔥 rising" if r["trend"] == "++" else "❄️ falling"
            lines.append(f"• *{r['team']}* is {direction} (#{r['rank']})`")

    return [
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": "\n".join(lines)}
        },
        {"type": "divider"}
    ]


def build_postseason_blocks(best_pitcher, best_batter, headlines, notable_games):
    """
    Builds a postseason-specific digest. Focuses on performances and drama,
    strips out regular-season analytics, oddities, and standings races.
    """
    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": "🏆 XFBL Postseason: October Baseball!",
                "emoji": True
            }
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "_The regular season is over. Every game now is win-or-go-home. Let's see who's stepping up._"
            }
        },
        {"type": "divider"}
    ]

    if best_pitcher:
        blocks.extend(build_performance_blocks(best_pitcher, "Playoff Pitcher of the Sim"))
    if best_batter:
        blocks.extend(build_performance_blocks(best_batter, "Playoff Batter of the Sim"))
    if headlines:
        # Re-label headlines section for playoffs
        headlines_text = "\n".join([f"• {h}" for h in headlines])
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"📋 *Playoff Highlights*\n{headlines_text}"
            }
        })
        blocks.append({"type": "divider"})
    if notable_games:
        blocks.extend(build_notable_games_blocks(notable_games))

    if blocks and blocks[-1].get("type") == "divider":
        blocks.pop()
    return blocks


def build_offseason_blocks(transactions=None):
    """
    Posts an offseason sim update. If transactions are available, lists the
    real roster moves that happened. Falls back to flavor text if empty.
    """
    import random
    flavor_lines = [
        "The hot stove is heating up. GMs are wheeling and dealing.",
        "No games today — just front office moves, contract talks, and roster shuffling.",
        "Players are working out, agents are calling, and rosters are taking shape.",
        "It's quiet on the diamond, but busy in the front office.",
        "The offseason grind continues. Every move matters for next year.",
    ]
    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": "💤 XFBL Offseason Sim Complete",
                "emoji": True
            }
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"_{random.choice(flavor_lines)}_"
            }
        }
    ]

    if transactions:
        # Group by date
        from collections import defaultdict
        by_date = defaultdict(list)
        for t in transactions:
            by_date[t["date"]].append(t)

        tx_lines = ["*📋 Recent Roster Moves*", ""]
        for date, moves in list(by_date.items())[:3]:  # cap at 3 date groups
            tx_lines.append(f"__{date}__")
            for m in moves[:8]:  # cap moves per day
                tx_lines.append(f"• *{m['team']}*: {m['action']}")
            tx_lines.append("")

        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": "\n".join(tx_lines).strip()}
        })
    else:
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "No transactions logged this sim. Check the site for the latest moves."
            }
        })

    return blocks


def trigger_daily_digest():
    import json
    import os

    # Load persistent state (used by oddity rotation, analytics mode, streaks, trivia)
    state_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "state.json")
    try:
        with open(state_path, "r") as f:
            state = json.load(f)
    except Exception:
        state = {}

    print(f"Fetching best performances from StatsPlus ({DAYS_BACK} days back)...")
    best_pitcher, best_batter = get_best_performances(LEAGUE_URL, DAYS_BACK)

    print(f"Detecting season phase...")
    season_phase = get_season_phase(LEAGUE_URL, best_pitcher, best_batter)
    print(f"Season phase: {season_phase}")

    # ── OFFSEASON ─────────────────────────────────────────────────────────────
    if season_phase == "offseason":
        print("Offseason sim detected — posting short update, skipping rotation state.")
        print("Fetching offseason transactions...")
        transactions = get_offseason_transactions(LEAGUE_URL)
        all_blocks = build_offseason_blocks(transactions)
        post_daily_digest(all_blocks)
        return

    # ── POSTSEASON ────────────────────────────────────────────────────────────
    if season_phase == "postseason":
        print("Postseason sim detected — posting playoff digest.")
        headlines = get_headlines_and_milestones(LEAGUE_URL)
        notable_games = get_notable_games(LEAGUE_URL, DAYS_BACK)
        all_blocks = build_postseason_blocks(best_pitcher, best_batter, headlines, notable_games)
        # Save state but skip burning rotation state (oddities/trivia/analytics)
        try:
            with open(state_path, "w") as f:
                json.dump(state, f, indent=2)
        except Exception as e:
            print(f"Warning: Could not save state: {e}")
        post_daily_digest(all_blocks)
        return

    # ── REGULAR SEASON ────────────────────────────────────────────────────────
    print(f"Fetching power rankings...")
    power_rankings = get_power_rankings(LEAGUE_URL)

    print(f"Fetching headlines from StatsPlus recap...")
    headlines = get_headlines_and_milestones(LEAGUE_URL)

    print(f"Fetching rotating sim analytics...")
    analytics_data = get_sim_analytics(LEAGUE_URL)

    print(f"Fetching streaks and season records...")
    streak_callouts = get_streaks_and_records(LEAGUE_URL, state)

    print(f"Fetching milestone countdowns...")
    milestones = get_milestone_countdowns(LEAGUE_URL)

    print(f"Fetching API oddities...")
    api_oddities = get_api_oddities(LEAGUE_URL)

    print(f"Fetching notable/weird games...")
    notable_games = get_notable_games(LEAGUE_URL, DAYS_BACK)

    print(f"Fetching close division races...")
    races = get_close_division_races(LEAGUE_URL)

    print(f"Fetching playoff odds...")
    playoff_odds = get_playoff_odds(LEAGUE_URL)

    print(f"Generating trivia question...")
    trivia = get_trivia_question(LEAGUE_URL, state)

    # Save updated state (all functions above may have mutated state)
    try:
        with open(state_path, "w") as f:
            json.dump(state, f, indent=2)
    except Exception as e:
        print(f"Warning: Could not save state: {e}")

    # Build summary text
    summary_parts = []
    if best_pitcher or best_batter:
        summary_parts.append("Play of the Week")
    if headlines:
        summary_parts.append(f"{len(headlines)} Headlines")
    if analytics_data:
        summary_parts.append("Team Analytics")
    if races:
        summary_parts.append(f"{len(races)} Pennant Races")
    if playoff_odds:
        summary_parts.append("Playoff Projections")
    if notable_games:
        summary_parts.append(f"{len(notable_games)} Weird Moments")
    if api_oddities:
        summary_parts.append(f"{len(api_oddities)} League Stats")
    if power_rankings:
        summary_parts.append("Power Rankings")
    if trivia:
        summary_parts.append("Trivia")

    summary_text = "Includes: " + ", ".join(summary_parts) if summary_parts else "No notable updates this sim."

    print("Building Daily Digest blocks...")
    all_blocks = []
    all_blocks.extend(build_sim_header_blocks(summary_text))

    if best_pitcher:
        all_blocks.extend(build_performance_blocks(best_pitcher, "Pitcher of the Sim"))
    if best_batter:
        all_blocks.extend(build_performance_blocks(best_batter, "Batter of the Sim"))
    if headlines:
        all_blocks.extend(build_headlines_blocks(headlines))
    if analytics_data:
        all_blocks.extend(build_analytics_blocks(analytics_data, streak_callouts, milestones))
    if api_oddities:
        all_blocks.extend(build_api_oddities_blocks(api_oddities))
    if notable_games:
        all_blocks.extend(build_notable_games_blocks(notable_games))
    if races:
        all_blocks.extend(build_division_races_blocks(races))
    if playoff_odds:
        all_blocks.extend(build_playoff_odds_blocks(playoff_odds))
    if power_rankings:
        all_blocks.extend(build_power_rankings_blocks(power_rankings))
    if trivia:
        all_blocks.extend(build_trivia_blocks(trivia))

    # Remove the very last divider if it exists
    if all_blocks and all_blocks[-1].get("type") == "divider":
        all_blocks.pop()

    print(f"Posting Daily Digest to Slack ({len(all_blocks)} blocks)...")
    post_daily_digest(all_blocks)

@app.message(re.compile(r"StatsPlus website.*has been updated", re.IGNORECASE))
def handle_sim_complete(message, say):
    if message.get("subtype") == "message_changed":
        print("Ignoring message_changed event to prevent duplicate triggers.")
        return

    # Ensure it's actually from the StatsPlus bot if a bot sent it
    bot_name = message.get("username") or message.get("bot_profile", {}).get("name")
    if bot_name and "statsplus" not in bot_name.lower():
        print(f"Ignoring message from non-StatsPlus bot: {bot_name}")
        return

    print(f"✅ MATCH FOUND: {message.get('text')}")
    print("🚀 Detected StatsPlus update message! Waiting 3 minutes before scraping...")
    
    def run_delayed_digest():
        time.sleep(180)
        trigger_daily_digest()
        
    thread = threading.Thread(target=run_delayed_digest)
    thread.start()

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
    import sys
    # Force unbuffered output so print statements appear immediately in docker exec
    sys.stdout.reconfigure(line_buffering=True)

    if "--manual" in sys.argv:
        print("🚀 Manual override detected. Running Daily Digest immediately...", flush=True)
        try:
            trigger_daily_digest()
        except Exception as e:
            import traceback
            print(f"❌ ERROR during manual digest: {e}", flush=True)
            traceback.print_exc()
    else:
        main()
