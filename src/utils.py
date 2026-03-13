"""
utils.py
--------
Shared file-loading and player-lookup helpers used across metrics.py,
cs_analysis.py, and any future analysis modules.

All functions here are pure data-access utilities — no API calls,
no plotting, no side effects beyond reading local JSON files.
"""

import json
from pathlib import Path


# ---------------------------------------------------------------------------
# File loading
# ---------------------------------------------------------------------------

def load_match_data(match_id: str, user_dir: Path) -> dict:
    """Load and return the match JSON for a given match ID."""
    match_path = user_dir / "matches" / f"{match_id}.json"
    with open(match_path, "r") as f:
        return json.load(f)


def load_timeline_data(match_id: str, user_dir: Path) -> dict:
    """Load and return the timeline JSON for a given match ID."""
    timeline_path = user_dir / "timelines" / f"{match_id}.json"
    with open(timeline_path, "r") as f:
        return json.load(f)


def load_match_and_timeline(match_id: str, user_dir: Path) -> tuple[dict, dict]:
    """
    Convenience wrapper — loads and returns both match and timeline data.

    Returns:
        (match_data, timeline_data)

    Raises:
        FileNotFoundError if either file is missing.
    """
    match_path = user_dir / "matches" / f"{match_id}.json"
    timeline_path = user_dir / "timelines" / f"{match_id}.json"

    missing = [p for p in (match_path, timeline_path) if not p.exists()]
    if missing:
        raise FileNotFoundError(f"Missing files for {match_id}: {[str(p) for p in missing]}")

    return load_match_data(match_id, user_dir), load_timeline_data(match_id, user_dir)


# ---------------------------------------------------------------------------
# Match sorting
# ---------------------------------------------------------------------------

def get_match_creation_time(match_file: Path) -> int:
    """
    Returns the gameCreation timestamp from a match file.
    Used as a sort key when ordering matches chronologically.
    Falls back to 0 if the file is unreadable or the field is missing.

    Note: gameCreation is the lobby-creation time (ms epoch). Use this
    consistently rather than gameStartTimestamp, which some older matches
    may not include.
    """
    try:
        with match_file.open() as f:
            data = json.load(f)
        return data.get("info", {}).get("gameCreation", 0)
    except Exception:
        return 0


def get_recent_match_files(
    user_dir: Path,
    num_matches: int = 20,
) -> list[Path]:
    """
    Returns up to num_matches match files from user_dir/matches/,
    sorted by gameCreation descending (most recent first).
    """
    match_dir = user_dir / "matches"
    match_files = sorted(
        match_dir.glob("*.json"),
        key=get_match_creation_time,
        reverse=True,
    )
    return match_files[:num_matches]


# ---------------------------------------------------------------------------
# Player lookup
# ---------------------------------------------------------------------------

def get_player_by_puuid(match_data: dict, puuid: str) -> dict:
    """
    Returns the participant dict for the given puuid.

    Raises:
        ValueError if the puuid is not found among participants.
    """
    player = next(
        (p for p in match_data["info"]["participants"] if p["puuid"] == puuid),
        None,
    )
    if player is None:
        raise ValueError(f"puuid {puuid!r} not found in match participants.")
    return player


def get_player_by_name(match_data: dict, summoner_name: str) -> dict:
    # Accept either "Name#Tag" or bare "Name"
    game_name = summoner_name.split("#")[0]
    player = next(
        (
            p for p in match_data["info"]["participants"]
            if p["riotIdGameName"].lower() == game_name.lower()
        ),
        None,
    )
    if player is None:
        raise ValueError(f"Summoner {summoner_name!r} not found in match participants.")
    return player


def get_teams(match_data: dict) -> tuple[list, list]:
    """
    Splits participants into (team1, team2) by teamId (100 and 200).

    Returns:
        (team_100, team_200)
    """
    participants = match_data["info"]["participants"]
    team_100 = [p for p in participants if p["teamId"] == 100]
    team_200 = [p for p in participants if p["teamId"] == 200]
    return team_100, team_200


def get_player_team_and_enemy(match_data: dict, puuid: str) -> tuple[list, list]:
    """
    Returns (your_team, enemy_team) participant lists for the given puuid.
    """
    player = get_player_by_puuid(match_data, puuid)
    team_100, team_200 = get_teams(match_data)
    if player in team_100:
        return team_100, team_200
    return team_200, team_100


# ---------------------------------------------------------------------------
# Champion filter helper
# ---------------------------------------------------------------------------

def matches_champion_filter(player: dict, champion_filter: str | None) -> bool:
    """
    Returns True if no filter is set, or if the player's championName
    matches the filter (case-insensitive).
    """
    if champion_filter is None:
        return True
    return player["championName"].lower() == champion_filter.lower()