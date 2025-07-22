import os
import json
import pandas as pd

from api_handler import (
    get_summoner_info,
    get_recent_match_ids,
    get_match_data,
    get_timeline_data,
)

def sync_user_data(
    summoner_name: str,
    base_data_path: str = "data/users",
    champion_name: str = None,
    start_time: int = None,  # Unix timestamp in seconds
    end_time: int = None,    # Unix timestamp in seconds
):
    """
    Sync match and timeline data for a summoner.
    Optional filters:
     - champion_name: only matches where summoner played this champ
     - start_time: only matches played on/after this Unix timestamp (seconds)
     - end_time: only matches played on/before this Unix timestamp (seconds)
    """
    print(f"\n📥 Syncing data for summoner: {summoner_name}")
    print(f"   Champion filter: {champion_name}")
    if start_time:
        print(f"   Start time filter: {start_time} ({pd.to_datetime(start_time, unit='s')})")
    if end_time:
        print(f"   End time filter: {end_time} ({pd.to_datetime(end_time, unit='s')})")

    user_path = os.path.join(base_data_path, summoner_name)
    match_dir = os.path.join(user_path, "matches")
    timeline_dir = os.path.join(user_path, "timelines")
    os.makedirs(match_dir, exist_ok=True)
    os.makedirs(timeline_dir, exist_ok=True)

    summoner_info = get_summoner_info(summoner_name)
    puuid = summoner_info["puuid"]

    existing_matches = {
        f.replace(".json", "") for f in os.listdir(match_dir) if f.endswith(".json")
    }

    all_match_ids = get_recent_match_ids(puuid)
    new_match_ids = [m for m in all_match_ids if m not in existing_matches]

    print(f"🔍 Found {len(new_match_ids)} new matches to check.")

    for match_id in new_match_ids:
        print(f"→ Checking match {match_id} for filters...")

        match_data = get_match_data(match_id)

        # Filter Ranked Solo queue only
        if match_data["info"]["queueId"] != 420:
            print("   Skipped (not Ranked Solo).")
            continue

        # Filter by start_time / end_time
        # gameStartTimestamp is in milliseconds; convert to seconds
        game_start_sec = match_data["info"]["gameStartTimestamp"] / 1000
        if start_time and game_start_sec < start_time:
            print("   Skipped (before start_time).")
            continue
        if end_time and game_start_sec > end_time:
            print("   Skipped (after end_time).")
            continue

        # Champion filter
        if champion_name is not None:
            participants = match_data["info"]["participants"]
            player_data = next((p for p in participants if p["puuid"] == puuid), None)
            if player_data is None:
                print("   Skipped (player not found).")
                continue
            if player_data["championName"].lower() != champion_name.lower():
                print(f"   Skipped (champion played: {player_data['championName']}).")
                continue

        # Passed all filters: save match + timeline
        with open(os.path.join(match_dir, f"{match_id}.json"), "w") as f:
            json.dump(match_data, f, indent=2)

        timeline_data = get_timeline_data(match_id)
        with open(os.path.join(timeline_dir, f"{match_id}.json"), "w") as f:
            json.dump(timeline_data, f, indent=2)

        print("   Saved match and timeline.")

    print("\n✅ Sync complete.\n")

