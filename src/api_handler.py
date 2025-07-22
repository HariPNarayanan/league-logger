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


def get_summoner_info(summoner_name: str, tagline: str = None) -> dict:
    """Fetch basic info for a given summoner name (and optional tagline for Riot ID)."""
    if tagline:
        # Use Riot ID endpoint (for cross-region Riot IDs, like 'MyName#EUW')
        url = f"https://europe.api.riotgames.com/riot/account/v1/accounts/by-riot-id/{summoner_name}/{tagline}"
    else:
        # Use classic summoner name endpoint (platform-specific)
        url = f"https://{PLATFORM_ROUTING}.api.riotgames.com/lol/summoner/v4/summoners/by-name/{summoner_name}"

    res = requests.get(url, headers=HEADERS)

    if res.status_code == 200:
        return res.json()
    else:
        raise Exception(f"Failed to fetch summoner info: {res.status_code} - {res.text}")

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


import requests

def get_match_data(match_id: str) -> dict:
    """
    Fetch match data JSON from Riot API for a single match ID.
    Returns the match JSON data as a dictionary.
    Raises an exception if the API call fails.
    """
    url = f"https://{REGION_ROUTING}.api.riotgames.com/lol/match/v5/matches/{match_id}"
    res = requests.get(url, headers=HEADERS)
    if res.status_code == 200:
        return res.json()
    else:
        raise Exception(f"Failed to fetch match data for {match_id}: {res.status_code} {res.text}")



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

def get_champion_mastery(summoner_id: str) -> list:
    url = f"https://{PLATFORM_ROUTING}.api.riotgames.com/lol/champion-mastery/v4/champion-masteries/by-summoner/{summoner_id}"
    res = requests.get(url, headers=HEADERS)
    if res.status_code == 200:
        return res.json()
    else:
        raise Exception(f"Champion mastery request failed: {res.status_code} - {res.text}")

def get_ranked_info(summoner_id: str) -> list:
    url = f"https://{PLATFORM_ROUTING}.api.riotgames.com/lol/league/v4/entries/by-summoner/{summoner_id}"
    res = requests.get(url, headers=HEADERS)
    if res.status_code == 200:
        return res.json()
    else:
        raise Exception(f"Ranked info request failed: {res.status_code} - {res.text}")

def get_latest_dd_version() -> str:
    url = "https://ddragon.leagueoflegends.com/api/versions.json"
    res = requests.get(url)
    if res.status_code == 200:
        return res.json()[0]
    else:
        raise Exception("Failed to fetch Data Dragon version list.")


def get_champion_data(version: str) -> dict:
    url = f"https://ddragon.leagueoflegends.com/cdn/{version}/data/en_US/champion.json"
    res = requests.get(url)
    if res.status_code == 200:
        return res.json()["data"]
    else:
        raise Exception("Failed to fetch champion data.")
    
def sync_user_profile(summoner_name: str):
    summoner_data = get_summoner_info(summoner_name)
    summoner_id = summoner_data["id"]
    
    # Champion Mastery
    mastery_data = get_champion_mastery(summoner_id)
    with open(f"data/users/{summoner_name}/champion_mastery.json", "w") as f:
        json.dump(mastery_data, f, indent=2)

    # Ranked Info
    ranked_data = get_ranked_info(summoner_id)
    with open(f"data/users/{summoner_name}/ranked_info.json", "w") as f:
        json.dump(ranked_data, f, indent=2)

    # Static Champion Data
    version = get_latest_dd_version()
    champ_data = get_champion_data(version)
    with open("data/static/champions.json", "w") as f:
        json.dump(champ_data, f, indent=2)

    print(f"User profile data synced for {summoner_name}")


