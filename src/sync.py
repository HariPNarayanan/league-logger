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
    get_champion_data,
    get_champion_mastery
)

MY_SUMMONER = "RainbowThenga#420"
my_info = get_summoner_info(MY_SUMMONER)
my_puuid = my_info["puuid"]


def sync_user_data(
    summoner_name: str,
    base_data_path: str = "data/users",
    champion_name: str = None,
    start_time: int = None,
    end_time: int = None,
    timeline_delay: float = 1.2,
    fetch_mastery: bool = True,
    fetch_dd: bool = True,
):
    import re
    import json
    from pathlib import Path
    import pandas as pd

    # Clean folder name
    clean_name = re.sub(r'[^a-zA-Z0-9]', '_', summoner_name)
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

    # Summoner & puuid
    summoner_info = get_summoner_info(summoner_name)
    puuid = summoner_info["puuid"]

    existing_matches = {f.stem for f in match_dir.glob("*.json")}

    all_match_ids = get_recent_match_ids(
        puuid,
        my_puuid=my_puuid,
        my_summoner_name=MY_SUMMONER,
        requested_summoner_name=summoner_name
    )

    new_match_ids = [mid for mid in all_match_ids if mid not in existing_matches]
    print(f"🔍 Found {len(new_match_ids)} new matches to check.")

    filtered_match_ids = []

    for match_id in new_match_ids:
        print(f"→ Checking match {match_id} for filters...")
        try:
            match_data = get_match_data(match_id)
        except Exception as e:
            print(f"   [ERROR] Could not fetch match data: {e}")
            continue

        # Filter Ranked Solo
        if match_data["info"]["queueId"] != 420:
            print("   Skipped (not Ranked Solo).")
            continue

        # Filter time
        game_start_sec = match_data["info"]["gameStartTimestamp"] / 1000
        if start_time and game_start_sec < start_time:
            print("   Skipped (before start_time).")
            continue
        if end_time and game_start_sec > end_time:
            print("   Skipped (after end_time).")
            continue

        # Champion filter
        if champion_name:
            player_data = next((p for p in match_data["info"]["participants"] if p["puuid"] == puuid), None)
            if not player_data:
                print("   Skipped (player not found).")
                continue
            if player_data["championName"].lower() != champion_name.lower():
                print(f"   Skipped (champion played: {player_data['championName']}).")
                continue

        # Save match
        with open(match_dir / f"{match_id}.json", "w") as f:
            json.dump(match_data, f, indent=2)
        print("   Saved match data.")
        filtered_match_ids.append(match_id)

    # Fetch timelines
    if filtered_match_ids:
        print(f"\n⏳ Downloading timelines for {len(filtered_match_ids)} matches...")
        get_timeline_data(filtered_match_ids, user_dir=user_dir, delay=timeline_delay)
    else:
        print("No new matches to download timelines for.")

    # === Champion Mastery ===
    if fetch_mastery:
        mastery_path = user_dir / "mastery.json"
        if not mastery_path.exists():
            print("📊 Fetching champion mastery...")
            try:
                mastery_data = get_champion_mastery(summoner_info["id"])
                with open(mastery_path, "w") as f:
                    json.dump(mastery_data, f, indent=2)
                print("✔ Champion mastery saved.")
            except Exception as e:
                print(f"⚠ Failed to fetch mastery: {e}")
        else:
            print("↪ Champion mastery already exists. Skipping.")

    # === Data Dragon ===
    if fetch_dd:
        dd_root = Path(base_data_path).parent / "ddragon"
        dd_root.mkdir(parents=True, exist_ok=True)
        existing_dd_versions = {p.name for p in dd_root.glob("*") if (p / "champion.json").exists()}
        required_patches = set()

        for match_file in match_dir.glob("*.json"):
            with open(match_file) as f:
                match_data = json.load(f)
                patch = ".".join(match_data["info"]["gameVersion"].split(".")[:2])
                required_patches.add(patch)

        for patch in required_patches - existing_dd_versions:
            print(f"🌐 Fetching DDragon data for patch {patch}...")
            try:
                full_version = get_dd_version_for_patch(patch)
                dd_data = get_champion_data(full_version)
                patch_dir = dd_root / patch  # still store it under the short patch name for consistency
                patch_dir.mkdir(parents=True, exist_ok=True)
                with open(patch_dir / "champion.json", "w") as f:
                    json.dump(dd_data, f, indent=2)
                print(f"✔ Data Dragon saved for patch {patch}")
            except Exception as e:
                print(f"⚠ Failed to fetch DDragon {patch}: {e}")

    print("\n✅ Sync complete.\n")
