# -*- coding: utf-8 -*-
import os
import time
import json
import requests
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()
RIOT_API_KEY = os.getenv("RIOT_API_KEY")

if not RIOT_API_KEY:
    raise ValueError("RIOT_API_KEY not found in .env")

HEADERS = {"X-Riot-Token": RIOT_API_KEY}

REGION_ROUTING = "europe"   # For match/v5 endpoints (matches & timelines)
PLATFORM_ROUTING = "euw1"   # For summoner-v4 endpoints (summoner info)


def get_summoner_info(riot_id: str) -> dict:
    """
    Fetch account info using Riot ID format: 'Name#Tag'.
    Uses the Account-V1 API (global).
    Returns puuid, gameName, tagLine.
    """
    if "#" not in riot_id:
        raise ValueError("Riot ID must include a tag, e.g. 'RainbowThenga#EUW'")
    game_name, tag_line = riot_id.split("#")
    url = f"https://{REGION_ROUTING}.api.riotgames.com/riot/account/v1/accounts/by-riot-id/{game_name}/{tag_line}"
    res = requests.get(url, headers=HEADERS)
    if res.status_code != 200:
        raise Exception(f"Failed to fetch summoner info: {res.status_code} - {res.text}")
    return res.json()


def get_recent_match_ids(
    puuid: str,
    count: int = 20,
    queue: int = 420,
    my_puuid: str = None,
    my_summoner_name: str = None,
    requested_summoner_name: str = None,
    max_count: int = 100,
) -> list:
    """
    Fetches recent match IDs for a puuid. queue=420 filters for Ranked Solo/Duo.
    Automatically fetches max_count matches if the puuid matches the repo owner's account.
    """
    override = False
    if my_puuid and puuid == my_puuid:
        override = True
    elif my_summoner_name and requested_summoner_name and requested_summoner_name.lower() == my_summoner_name.lower():
        override = True
    if override:
        count = max_count

    url = f"https://{REGION_ROUTING}.api.riotgames.com/lol/match/v5/matches/by-puuid/{puuid}/ids"
    params = {"start": 0, "count": count, "queue": queue}
    res = requests.get(url, headers=HEADERS, params=params)
    if res.status_code == 200:
        return res.json()
    else:
        raise Exception(f"Failed to get match IDs: {res.status_code} - {res.text}")


def get_match_data(match_id: str) -> dict:
    """Fetch and return match data JSON for a single match ID."""
    url = f"https://{REGION_ROUTING}.api.riotgames.com/lol/match/v5/matches/{match_id}"
    res = requests.get(url, headers=HEADERS)
    if res.status_code == 200:
        return res.json()
    else:
        raise Exception(f"Failed to fetch match data for {match_id}: {res.status_code} {res.text}")


def get_timeline_data(match_ids: list, user_dir: Path, delay: float = 1.2):
    """
    Downloads and stores timeline JSON for each match ID under user_dir/timelines/.
    Skips matches already downloaded.
    """
    timeline_dir = user_dir / "timelines"
    timeline_dir.mkdir(parents=True, exist_ok=True)

    for match_id in match_ids:
        timeline_path = timeline_dir / f"{match_id}.json"
        if timeline_path.exists():
            print(f"[SKIP] Timeline already exists: {match_id}")
            continue
        url = f"https://{REGION_ROUTING}.api.riotgames.com/lol/match/v5/matches/{match_id}/timeline"
        try:
            res = requests.get(url, headers=HEADERS)
            if res.status_code == 200:
                with open(timeline_path, "w") as f:
                    json.dump(res.json(), f, indent=2)
                print(f"[✔] Timeline saved: {match_id}")
            else:
                print(f"[ERROR {res.status_code}] Could not fetch {match_id}: {res.text}")
        except Exception as e:
            print(f"[EXCEPTION] {match_id}: {e}")
        time.sleep(delay)


def get_champion_mastery(puuid: str) -> list:
    """Fetch champion mastery data by puuid."""
    url = f"https://{PLATFORM_ROUTING}.api.riotgames.com/lol/champion-mastery/v4/champion-masteries/by-puuid/{puuid}"
    res = requests.get(url, headers=HEADERS)
    if res.status_code == 200:
        return res.json()
    else:
        raise Exception(f"Champion mastery request failed: {res.status_code} - {res.text}")


def get_ranked_info(puuid: str) -> list:
    """Fetch ranked info by puuid."""
    url = f"https://{PLATFORM_ROUTING}.api.riotgames.com/lol/league/v4/entries/by-puuid/{puuid}"
    res = requests.get(url, headers=HEADERS)
    if res.status_code == 200:
        return res.json()
    else:
        raise Exception(f"Ranked info request failed: {res.status_code} - {res.text}")


def get_dd_version_for_patch(patch: str) -> str:
    """Maps a short patch string like '14.10' to the full DDragon version like '14.10.1'."""
    url = "https://ddragon.leagueoflegends.com/api/versions.json"
    res = requests.get(url)
    if res.status_code != 200:
        raise Exception("Failed to fetch Data Dragon version list.")
    for v in res.json():
        if v.startswith(patch + "."):
            return v
    raise Exception(f"No DDragon version found for patch {patch}")


def get_champion_data(version: str) -> dict:
    """Fetch champion data from DDragon for a given full version string."""
    url = f"https://ddragon.leagueoflegends.com/cdn/{version}/data/en_US/champion.json"
    res = requests.get(url)
    if res.status_code == 200:
        return res.json()["data"]
    else:
        raise Exception(f"Failed to fetch champion data for version {version}.")