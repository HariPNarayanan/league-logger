import os
import time
import json
import requests
from dotenv import load_dotenv
from pathlib import Path

load_dotenv()
RIOT_API_KEY = os.getenv("RIOT_API_KEY")

if not RIOT_API_KEY:
    raise ValueError("RIOT_API_KEY not found in .env")

HEADERS = {
    "X-Riot-Token": RIOT_API_KEY
}

# Change these as needed
REGION_ROUTING = "europe"   # For match/v5 endpoints (matches & timelines)
PLATFORM_ROUTING = "euw1"      # For summoner-v4 endpoints (summoner info)


def get_puuid(summoner_name: str) -> str:
    url = f"https://{PLATFORM_ROUTING}.api.riotgames.com/lol/summoner/v4/summoners/by-name/{summoner_name}"
    res = requests.get(url, headers=HEADERS)

    if res.status_code == 200:
        return res.json()["puuid"]
    else:
        raise Exception(f"Failed to get PUUID for {summoner_name}: {res.status_code} - {res.text}")


def get_recent_match_ids(puuid: str, count: int = 10, queue: int = 420) -> list:
    """
    queue=420 filters for ranked Solo/Duo
    """
    url = f"https://{REGION_ROUTING}.api.riotgames.com/lol/match/v5/matches/by-puuid/{puuid}/ids"
    params = {"start": 0, "count": count, "queue": queue}
    res = requests.get(url, headers=HEADERS, params=params)

    if res.status_code == 200:
        return res.json()
    else:
        raise Exception(f"Failed to get match IDs: {res.status_code} - {res.text}")


def sync_recent_ranked_matches(user_dir: Path, summoner_name: str, count: int = 10, delay: float = 1.2) -> list:
    """
    Downloads match details for the last `count` ranked games and stores them in /matches/.
    Skips already downloaded matches.
    Returns list of match IDs synced.
    """
    match_dir = user_dir / "matches"
    match_dir.mkdir(parents=True, exist_ok=True)

    puuid = get_puuid(summoner_name)
    match_ids = get_recent_match_ids(puuid, count=count)

    for match_id in match_ids:
        match_path = match_dir / f"{match_id}.json"
        if match_path.exists():
            print(f"[SKIP] Match already exists: {match_id}")
            continue

        url = f"https://{REGION_ROUTING}.api.riotgames.com/lol/match/v5/matches/{match_id}"
        res = requests.get(url, headers=HEADERS)

        if res.status_code == 200:
            with open(match_path, "w") as f:
                json.dump(res.json(), f, indent=2)
            print(f"[✔] Downloaded match: {match_id}")
        else:
            print(f"[ERROR] Failed to get match {match_id}: {res.status_code} - {res.text}")

        time.sleep(delay)  # Respect rate limits

    return match_ids


def sync_timelines(user_dir: Path, match_ids: list, delay: float = 1.2):
    """
    Downloads timeline data for given match IDs and stores them in /timelines/.
    Skips already downloaded timelines.
    """
    timeline_dir = user_dir / "timelines"
    timeline_dir.mkdir(parents=True, exist_ok=True)

    for match_id in match_ids:
        timeline_path = timeline_dir / f"{match_id}.json"
        if timeline_path.exists():
            print(f"[SKIP] Timeline exists for {match_id}")
            continue

        url = f"https://{REGION_ROUTING}.api.riotgames.com/lol/match/v5/matches/{match_id}/timeline"
        try:
            response = requests.get(url, headers=HEADERS)
            if response.status_code == 200:
                with open(timeline_path, "w") as f:
                    json.dump(response.json(), f, indent=2)
                print(f"[✔] Downloaded timeline for {match_id}")
            else:
                print(f"[ERROR {response.status_code}] Failed to fetch timeline {match_id}: {response.text}")
        except Exception as e:
            print(f"[EXCEPTION] {match_id}: {e}")

        time.sleep(delay)  # Rate limiting

"""
# Example of usage if run as a script:
if __name__ == "__main__":
    user = "your_summoner_name"  # update this
    user_dir = Path("data") / "users" / user

    print("Syncing recent ranked matches...")
    matches = sync_recent_ranked_matches(user_dir, user, count=10)

    print("\nSyncing timelines...")
    sync_timelines(user_dir, matches)
"""