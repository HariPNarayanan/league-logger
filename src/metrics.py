import json
from pathlib import Path
from typing import Union, Tuple, List
import pandas as pd
# Optional: if you're displaying timestamps or need to handle durations
import datetime

from pathlib import Path
import json

from pathlib import Path
import json  # Adjust if in same file

import json
from pathlib import Path
from collections import Counter
from api_handler import get_summoner_info  # Update this if the import path differs


def champ_counts(summoner_riot_id: str, repo_root: Path) -> Counter:
    """
    Counts how many times each champion was played by the summoner in their synced match data.

    Args:
        summoner_riot_id (str): Riot ID in the format "Name#Tag"
        repo_root (Path): Root of the repo (should contain data/users/...)

    Returns:
        Counter: A Counter object with champion names as keys and match counts as values
    """
    puuid = get_summoner_info(summoner_riot_id)["puuid"]
    clean_name = summoner_riot_id.replace("#", "_")
    match_path = repo_root / "data" / "users" / clean_name / "matches"

    champions = []
    for file in match_path.glob("*.json"):
        with open(file, encoding="utf-8") as f:
            match = json.load(f)
        try:
            player = next(p for p in match["info"]["participants"] if p["puuid"] == puuid)
            champions.append(player["championName"])
        except StopIteration:
            continue  # skip if puuid not found in this match

    return Counter(champions)


def load_match_data(match_id: str, user_dir: Path) -> dict:
    match_path = user_dir / "matches" / f"{match_id}.json"
    with open(match_path, "r") as f:
        return json.load(f)

def get_participant_data(match_data: dict, summoner_name: str) -> tuple:
    participants = match_data["info"]["participants"]
    your_data = next((p for p in participants if p["riotIdGameName"].lower() == summoner_name.lower()), None)

    if not your_data:
        raise ValueError("Summoner not found in match data.")

    # Group by teamId
    team1 = [p for p in participants if p["teamId"] == 100]
    team2 = [p for p in participants if p["teamId"] == 200]

    return your_data, team1, team2

def load_timeline_data(match_id: str, user_dir: Path) -> dict:
    path = user_dir / "timelines" / f"{match_id}.json"
    with open(path, "r") as f:
        return json.load(f)

def get_cs_at_15(timeline: dict, participant_id: int) -> int:
    total_cs = 0
    for frame in timeline["info"]["frames"][:16]:  # Minute 0 to 15 inclusive
        participant_frame = frame["participantFrames"].get(str(participant_id))
        if participant_frame:
            total_cs = participant_frame["minionsKilled"] + participant_frame["jungleMinionsKilled"]
    return total_cs

def get_damage_ranking(participants: list, your_participant: dict) -> tuple:
    all_damages = [(p["riotIdGameName"], p["totalDamageDealtToChampions"]) for p in participants]
    all_damages_sorted = sorted(all_damages, key=lambda x: x[1], reverse=True)

    rank = next(i + 1 for i, (name, dmg) in enumerate(all_damages_sorted)
                if name.lower() == your_participant["riotIdGameName"].lower())

    return your_participant["totalDamageDealtToChampions"], rank

def summarize_match_for_notes(match_id: str, summoner_name: str, user_dir: Union[str, Path]) -> str:
    user_dir = Path(user_dir)
    match = load_match_data(match_id, user_dir)
    timeline = load_timeline_data(match_id, user_dir)
    
    your_data, team1, team2 = get_participant_data(match, summoner_name)
    cs_at_15 = get_cs_at_15(timeline, your_data["participantId"])
    total_minutes = match["info"]["gameDuration"] / 60
    cs_per_min = your_data["totalMinionsKilled"] / total_minutes

    dmg, dmg_rank = get_damage_ranking(match["info"]["participants"], your_data)

    # Lane partners and opponents
    def find_lane_roles(team):
        bot = next((p for p in team if p["teamPosition"] == "BOTTOM"), None)
        support = next((p for p in team if p["teamPosition"] == "UTILITY"), None)
        return bot, support

    your_team = team1 if your_data in team1 else team2
    enemy_team = team2 if your_team == team1 else team1

    your_bot, your_supp = find_lane_roles(your_team)
    enemy_bot, enemy_supp = find_lane_roles(enemy_team)

    win_tag = f"win-yes" if your_data["win"] else f"win-no"

    tags = [
        "#leagueoflegends",
        "#adc",
        f"#champ-{your_bot['championName']}",
        f"#ally-champ-{your_supp['championName']}",
        f"#opp-champ-{enemy_bot['championName']}",
        f"#opp-champ-{enemy_supp['championName']}",
        f"#{win_tag}"
    ]
    tags_line = "Tags: " + " ".join(tags)

    text = f"""\
## Match Summary: {match_id}

Champion: {your_data['championName']}
KDA: {your_data['kills']}/{your_data['deaths']}/{your_data['assists']}
CS: {your_data['totalMinionsKilled']} ({cs_per_min:.1f}/min), CS@15: {cs_at_15} ({round(cs_at_15/15, 2)}/min)
Damage Dealt: {dmg:,} (Rank {dmg_rank}/10)

Bot Lane:

    You: {your_bot['championName']} + {your_supp['championName']}

    Enemy: {enemy_bot['championName']} + {enemy_supp['championName']}

Result: {"Win" if your_data["win"] else "Loss"}
Game Duration: {int(total_minutes)} min

{tags_line}

"""
    return text

def get_match_time(file):
    try:
        with file.open() as f:
            data = json.load(f)
            return data.get("info", {}).get("gameStartTimestamp", 0)
    except Exception:
        return 0  # fallback if file is corrupt or missing field

def summarize_recent_matchups(
    summoner_name: str,
    user_data_path: Path,
    num_matches: int = 15
):
    match_dir = user_data_path / "matches"
    if not match_dir.exists():
        raise FileNotFoundError(f"No match data found at {match_dir}")

    match_files = list(match_dir.glob("*.json"))

    def get_match_time(file):
        try:
            with file.open() as f:
                data = json.load(f)
                return data.get("info", {}).get("gameCreation", 0)
        except Exception:
            return 0  # fallback if file is corrupt or missing field

    match_files.sort(key=get_match_time, reverse=True)
    match_files = match_files[:num_matches]

    print(f"🧾 Last {len(match_files)} matchups for {summoner_name}:\n")
    for file in match_files:
        match_id = file.stem
        try:
            summary = summarize_match_for_notes(match_id, summoner_name, user_data_path)
            print(f"{match_id}: {summary.splitlines()[9]}")  # Print just the matchup line
        except Exception as e:
            print(f"{match_id}: [Error] {e}")

