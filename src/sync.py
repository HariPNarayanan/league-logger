import os
import json
import time
import re
from pathlib import Path
import pandas as pd
from api_handler import (
    get_summoner_info,
    get_recent_match_ids,
    get_match_data,
    get_timeline_data,
)

MY_SUMMONER = "RainbowThenga#420"
my_info = get_summoner_info(MY_SUMMONER)
my_puuid = my_info["puuid"]


def sync_user_data(
    summoner_name: str,
    base_data_path: str = "data/users",
    champion_name: str = None,
    start_time: int = None,  # Unix timestamp in seconds
    end_time: int = None,    # Unix timestamp in seconds
    timeline_delay: float = 1.2,  # Delay between timeline API calls
):
    # Clean summoner name for safe folder name
    if "#" in summoner_name:
        clean_name = re.sub(r'[^a-zA-Z0-9]', '_', summoner_name)
    else:
        clean_name = summoner_name

    user_dir = Path(base_data_path) / clean_name
    match_dir = user_dir / "matches"
    timeline_dir = user_dir / "timelines"
    match_dir.mkdir(parents=True, exist_ok=True)
    timeline_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n📥 Syncing data for summoner: {summoner_name}")
    print(f"   Champion filter: {champion_name}")
    if start_time:
        print(f"   Start time filter: {start_time} ({pd.to_datetime(start_time, unit='s')})")
    if end_time:
        print(f"   End time filter: {end_time} ({pd.to_datetime(end_time, unit='s')})")

    # Get summoner info and puuid
    summoner_info = get_summoner_info(summoner_name)
    puuid = summoner_info["puuid"]

    # Existing matches already saved locally
    existing_matches = {f.stem for f in match_dir.glob("*.json")}

    # Fetch recent match IDs (you may adjust count if you want)
    all_match_ids = get_recent_match_ids(
    puuid,
    my_puuid=my_puuid,
    my_summoner_name=MY_SUMMONER,
    requested_summoner_name=summoner_name
    )

    # Filter out matches already saved
    new_match_ids = [mid for mid in all_match_ids if mid not in existing_matches]

    print(f"🔍 Found {len(new_match_ids)} new matches to check.")

    # List to keep matches that pass all filters
    filtered_match_ids = []

    for match_id in new_match_ids:
        print(f"→ Checking match {match_id} for filters...")
        try:
            match_data = get_match_data(match_id)
        except Exception as e:
            print(f"   [ERROR] Could not fetch match data: {e}")
            continue

        # Filter Ranked Solo queue only (420)
        if match_data["info"]["queueId"] != 420:
            print("   Skipped (not Ranked Solo).")
            continue

        # Filter by start_time / end_time
        game_start_sec = match_data["info"]["gameStartTimestamp"] / 1000
        if start_time and game_start_sec < start_time:
            print("   Skipped (before start_time).")
            continue
        if end_time and game_start_sec > end_time:
            print("   Skipped (after end_time).")
            continue

        # Champion filter
        if champion_name:
            participants = match_data["info"]["participants"]
            player_data = next((p for p in participants if p["puuid"] == puuid), None)
            if not player_data:
                print("   Skipped (player not found).")
                continue
            if player_data["championName"].lower() != champion_name.lower():
                print(f"   Skipped (champion played: {player_data['championName']}).")
                continue

        # Passed all filters, save match data
        match_file = match_dir / f"{match_id}.json"
        with open(match_file, "w") as f:
            json.dump(match_data, f, indent=2)
        print("   Saved match data.")

        filtered_match_ids.append(match_id)

    # Fetch & save timelines in batch
    if filtered_match_ids:
        print(f"\n⏳ Downloading timelines for {len(filtered_match_ids)} matches...")
        get_timeline_data(filtered_match_ids, user_dir=user_dir, delay=timeline_delay)
    else:
        print("No new matches to download timelines for.")

    print("\n✅ Sync complete.\n")
