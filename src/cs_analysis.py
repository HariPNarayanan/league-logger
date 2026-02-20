import json
from pathlib import Path
from collections import defaultdict
from datetime import datetime
import api_handler

import json
from pathlib import Path
from collections import defaultdict
from datetime import datetime
import api_handler

def cs_at_15_for_recent_matches(
    summoner_riot_id: str,
    base_data_path: Path,
    num_matches: int = 10,
    champion_filter: str = None
):
    puuid = api_handler.get_summoner_info(summoner_riot_id)["puuid"]
    user_dir = base_data_path / summoner_riot_id.replace("#", "_")
    match_dir = user_dir / "matches"
    timeline_dir = user_dir / "timelines"

    def get_match_time(file):
        try:
            with file.open() as f:
                data = json.load(f)
                return data.get("info", {}).get("gameCreation", 0)
        except Exception:
            return 0

    # Step 1: Get most recent matches by gameCreation, not file mtime
    match_files = list(match_dir.glob("*.json"))
    match_files.sort(key=get_match_time, reverse=True)
    match_files = match_files[:num_matches]

    results = []

    for match_file in match_files:
        match_id = match_file.stem
        timeline_path = timeline_dir / f"{match_id}.json"

        if not timeline_path.exists():
            print(f"⚠ Timeline not found for {match_id}")
            continue

        with open(match_file) as f:
            match_data = json.load(f)
        with open(timeline_path) as f:
            timeline_data = json.load(f)

        participants = match_data["info"]["participants"]
        player = next((p for p in participants if p["puuid"] == puuid), None)
        if not player:
            print(f"❌ Could not find player in {match_id}")
            continue

        if champion_filter and player["championName"].lower() != champion_filter.lower():
            continue

        participant_id = player["participantId"]
        frames = timeline_data["info"]["frames"]

        try:
            cs_at_15 = (
                frames[14]["participantFrames"][str(participant_id)]["minionsKilled"] +
                frames[14]["participantFrames"][str(participant_id)]["jungleMinionsKilled"]
            )
        except Exception as e:
            print(f"⚠ Error extracting CS for {match_id}: {e}")
            continue

        cs_per_min = cs_at_15 / 15
        results.append({
            "match_id": match_id,
            "champion": player["championName"],
            "cs_at_15": cs_at_15,
            "cs_per_min": round(cs_per_min, 2),
        })

    # Step 2: Output results
    print(f"\n🎯 CS@15 for last {len(results)} matches for {summoner_riot_id}:")
    for res in results:
        print(f"{res['match_id']} | {res['champion']:>10} | CS@15: {res['cs_at_15']:>3} | CS/m: {res['cs_per_min']:.2f}")

    return results

import pandas as pd

def bin_cs_per_min_stats(cs_data: list, bin_size: int = 5):
    """
    Given list of match stats with 'cs_per_min', compute rolling averages.
    """
    if len(cs_data) < bin_size:
        raise ValueError("Not enough matches to create at least one full bin.")

    df = pd.DataFrame(cs_data)
    df = df.sort_values(by="match_id", ascending=False).reset_index(drop=True)  # Most recent first

    df["cs_per_min_avg"] = df["cs_per_min"].rolling(window=bin_size).mean()

    print(f"\n📊 Rolling CS/m (window size = {bin_size}):")
    for i in range(bin_size - 1, len(df)):
        window_matches = df.loc[i - bin_size + 1 : i]
        match_ids = ", ".join(window_matches["match_id"].tolist())
        print(f"Matches: {match_ids} | Avg CS/m: {df.loc[i, 'cs_per_min_avg']:.2f}")

    return df

import json
from pathlib import Path

def extract_cs_timeline_from_files(match_id: str, puuid: str, user_data_path: Path):
    """
    Load match info and timeline for a given match ID and return CS per minute
    from the timeline for the player with the given puuid.
    """
    match_path = user_data_path / "matches" / f"{match_id}.json"
    timeline_path = user_data_path / "timelines" / f"{match_id}.json"

    if not match_path.exists() or not timeline_path.exists():
        raise FileNotFoundError(f"Missing files for {match_id}: "
                                f"{'match' if not match_path.exists() else ''} "
                                f"{'timeline' if not timeline_path.exists() else ''}")

    with open(match_path) as f:
        match_info = json.load(f)

    with open(timeline_path) as f:
        timeline = json.load(f)

    # Find participant ID for the user
    participants = match_info["info"]["participants"]
    player = next(p for p in participants if p["puuid"] == puuid)
    participant_id = player["participantId"]

    # Extract CS per minute timeline
    cs_by_minute = []
    for frame in timeline["info"]["frames"][:16]:  # up to minute 15
        try:
            cs = (
                frame["participantFrames"][str(participant_id)]["minionsKilled"]
                + frame["participantFrames"][str(participant_id)]["jungleMinionsKilled"]
            )
            cs_by_minute.append(cs)
        except KeyError:
            cs_by_minute.append(None)  # fallback if data is missing

    # Convert to per-minute deltas
    cs_deltas = []
    prev = 0
    for cs in cs_by_minute:
        if cs is None:
            cs_deltas.append(None)
        else:
            cs_deltas.append(cs - prev)
            prev = cs

    return cs_deltas


import matplotlib.pyplot as plt
import json

import matplotlib.pyplot as plt
from collections import defaultdict
import numpy as np
import json

def plot_cs_timelines_by_bins(
    user_data_path: Path,
    summoner_name: str,
    num_matches: int = 20,
    bin_size: int = 5,
    filter_champion: str = None
):
    from api_handler import get_summoner_info
    puuid = get_summoner_info(summoner_name)["puuid"]

    # Sort match files by gameCreation timestamp
    match_dir = user_data_path / "matches"

    def get_match_time(file):
        try:
            with file.open() as f:
                data = json.load(f)
                return data.get("info", {}).get("gameCreation", 0)
        except Exception:
            return 0

    match_files = sorted(
        match_dir.glob("*.json"),
        key=get_match_time,
        reverse=True
    )[:num_matches]

    curves = []

    for file in match_files:
        match_id = file.stem
        try:
            with open(file) as f:
                match_data = json.load(f)
            player = next(p for p in match_data["info"]["participants"] if p["puuid"] == puuid)
            if filter_champion and player["championName"].lower() != filter_champion.lower():
                continue

            cs_curve = extract_cs_timeline_from_files(match_id, puuid, user_data_path)
            if len(cs_curve) == 16:  # 16 frames from 0 to 15 min
                curves.append(cs_curve)
        except Exception as e:
            print(f"[!] Skipping {match_id}: {e}")
            continue

    if not curves:
        print("No valid CS timeline data found.")
        return

    # Bin curves
    binned_curves = []
    for i in range(0, len(curves), bin_size):
        group = curves[i:i + bin_size]
        binned_curves.append(group)

    # Plot
    fig, ax = plt.subplots(figsize=(10, 6))
    for idx, group in enumerate(binned_curves):
        arr = np.array([c for c in group if c is not None])
        mean_curve = np.nanmean(arr, axis=0)
        ax.plot(range(16), mean_curve, label=f"Bin {idx + 1} ({len(group)} games)")

    ax.set_title(f"CS/min Timeline for {summoner_name} (Grouped by {bin_size})")
    ax.set_xlabel("Minute")
    ax.set_ylabel("CS gained (delta per min)")
    ax.legend()
    ax.grid(True)
    plt.tight_layout()
    plt.show()

    import matplotlib.pyplot as plt
import numpy as np
import json

def plot_cumulative_cs_timelines_by_bins(
    user_data_path: Path,
    summoner_name: str,
    num_matches: int = 20,
    bin_size: int = 5,
    filter_champion: str = None
):
    from api_handler import get_summoner_info
    puuid = get_summoner_info(summoner_name)["puuid"]

    match_dir = user_data_path / "matches"

    def get_match_time(file):
        try:
            with file.open() as f:
                data = json.load(f)
                return data.get("info", {}).get("gameCreation", 0)
        except Exception:
            return 0

    match_files = sorted(
        match_dir.glob("*.json"),
        key=get_match_time,
        reverse=True
    )[:num_matches]

    cs_curves = []
    for file in match_files:
        match_id = file.stem
        try:
            with open(file) as f:
                match_data = json.load(f)
            player = next(p for p in match_data["info"]["participants"] if p["puuid"] == puuid)
            if filter_champion and player["championName"].lower() != filter_champion.lower():
                continue

            cs_curve = extract_cs_timeline_from_files(match_id, puuid, user_data_path)
            if len(cs_curve) == 16:
                cumulative_curve = np.cumsum(cs_curve).tolist()
                cs_curves.append(cumulative_curve)
        except Exception as e:
            print(f"[!] Skipping {match_id}: {e}")
            continue

    if not cs_curves:
        print("No valid CS timeline data found.")
        return

    # Bin curves
    binned_curves = []
    for i in range(0, len(cs_curves), bin_size):
        group = cs_curves[i:i + bin_size]
        binned_curves.append(group)

    # Plot
    fig, ax = plt.subplots(figsize=(10, 6))
    for idx, group in enumerate(binned_curves):
        arr = np.array([c for c in group if c is not None])
        mean_curve = np.nanmean(arr, axis=0)
        ax.plot(range(16), mean_curve, label=f"Bin {idx + 1} ({len(group)} games)")

    ax.set_title(f"Cumulative CS over 15 Minutes — {summoner_name}")
    ax.set_xlabel("Minute")
    ax.set_ylabel("Cumulative CS")
    ax.legend()
    ax.grid(True)
    plt.tight_layout()
    plt.show()

def cs_at_15_and_early_death_for_recent_matches(
    user_data_path: Path,
    summoner_name: str,
    num_matches: int = 10,
    filter_champion: str = None
):
    import json
    from api_handler import get_summoner_info

    puuid = get_summoner_info(summoner_name)["puuid"]

    match_dir = user_data_path / "matches"
    timeline_dir = user_data_path / "timelines"

    def get_match_time(file):
        try:
            with file.open() as f:
                data = json.load(f)
                return data.get("info", {}).get("gameCreation", 0)
        except Exception:
            return 0

    match_files = list(match_dir.glob("*.json"))
    match_files.sort(key=get_match_time, reverse=True)
    match_files = match_files[:num_matches]

    results = []

    for match_file in match_files:
        match_id = match_file.stem
        timeline_path = timeline_dir / f"{match_id}.json"

        if not timeline_path.exists():
            print(f"⚠ Timeline not found for {match_id}")
            continue

        with open(match_file) as f:
            match_data = json.load(f)
        with open(timeline_path) as f:
            timeline_data = json.load(f)

        participants = match_data["info"]["participants"]
        player = next((p for p in participants if p["puuid"] == puuid), None)
        if not player:
            print(f"❌ Could not find player in {match_id}")
            continue

        if filter_champion and player["championName"].lower() != filter_champion.lower():
            continue

        participant_id = player["participantId"]
        frames = timeline_data["info"]["frames"]

        try:
            cs_at_15 = (
                frames[14]["participantFrames"][str(participant_id)]["minionsKilled"] +
                frames[14]["participantFrames"][str(participant_id)]["jungleMinionsKilled"]
            )
        except Exception as e:
            print(f"⚠ Error extracting CS for {match_id}: {e}")
            continue

        # Look for early deaths (before minute 15)
        early_death = any(
            event.get("type") == "CHAMPION_KILL" and event.get("victimId") == participant_id
            for frame in frames[:15]
            for event in frame.get("events", [])
        )

        cs_per_min = cs_at_15 / 15
        results.append({
            "match_id": match_id,
            "champion": player["championName"],
            "cs_at_15": cs_at_15,
            "cs_per_min": round(cs_per_min, 2),
            "early_death": early_death
        })

    # Summary printout
    print(f"\n🎯 CS@15 + Early Deaths for last {len(results)} matches:")
    for res in results:
        flag = "🟥" if res["early_death"] else "🟩"
        print(f"{flag} {res['match_id']} | {res['champion']:>10} | CS@15: {res['cs_at_15']:>3} | CS/m: {res['cs_per_min']:.2f}")

    return results
