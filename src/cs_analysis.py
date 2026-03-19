"""
cs_analysis.py
--------------
CS trend analysis for a single summoner.
 
Design principles:
- All functions accept `puuid: str` directly — callers resolve it once via
  api_handler.get_summoner_info(), no API calls happen inside this module.
- File I/O goes through utils.py exclusively (load_match_and_timeline,
  get_recent_match_files, get_player_by_puuid).
- extract_cs_timeline() is the single frame-walking primitive; all higher-level
  functions delegate to it rather than re-implementing frame iteration.
- Position data is already available in participantFrames[n]["position"] inside
  timeline frames — heatmap analysis can be layered on top of the same
  load_match_and_timeline() call without touching the API again.
"""
 
from enum import Enum
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from pathlib import Path
 
from utils import (
    get_recent_match_files,
    load_match_and_timeline,
    get_player_by_puuid,
    matches_champion_filter,
)
class KillSource(str, Enum):
    LANE = "lane"
    GANK = "gank"
    ROAM = "roam"
    NONE = "none"
 
 
# ---------------------------------------------------------------------------
# Core timeline primitive
# ---------------------------------------------------------------------------
 
def extract_cs_timeline(timeline: dict, participant_id: int) -> list[int | None]:
    """
    Returns cumulative CS at each minute-mark (frames 0–15) for one participant.
 
    Frame index == minute (frame 0 = game start snapshot, frame 15 = end of
    minute 15). Returns a 16-element list; individual entries are None when
    frame data is missing.
 
    This is the single entry point for all frame-walking.  Higher-level
    functions build on this rather than re-implementing the loop.
 
    Extension note: timeline frames also carry
        participantFrames[n]["position"] = {"x": int, "y": int}
    which can be fed directly into heatmap analysis without an extra load.
    """
    pid = str(participant_id)
    cs_by_minute: list[int | None] = []
 
    for frame in timeline["info"]["frames"][:16]:
        pf = frame.get("participantFrames", {}).get(pid)
        if pf is None:
            cs_by_minute.append(None)
        else:
            cs_by_minute.append(
                pf.get("minionsKilled", 0) + pf.get("jungleMinionsKilled", 0)
            )
 
    # Pad to 16 entries for games that ended before minute 15 (surrenders,
    # remakes). Downstream code can treat trailing Nones as missing data.
    while len(cs_by_minute) < 16:
        cs_by_minute.append(None)
 
    return cs_by_minute
 
 
def cs_deltas(cumulative: list[int | None]) -> list[int | None]:
    """
    Converts a cumulative CS list (from extract_cs_timeline) into per-minute
    deltas, i.e. CS gained in each individual minute.
 
    Kept separate so callers can choose cumulative vs delta representation.
    """
    deltas: list[int | None] = []
    prev = 0
    for value in cumulative:
        if value is None:
            deltas.append(None)
        else:
            deltas.append(value - prev)
            prev = value
    return deltas
 
 
# ---------------------------------------------------------------------------
# Per-match stat extraction
# ---------------------------------------------------------------------------
 
def get_match_cs_stats(
    match_id: str,
    puuid: str,
    user_dir: Path,
    champion_filter: str | None = None,
    early_death_before_minute: int = 10,
) -> dict | None:
    """
    Returns a flat stats dict for one match, or None if the match should be
    skipped (champion filter miss, missing files, player not found, or too
    short to be meaningful).
 
    Args:
        early_death_before_minute: A death before this minute counts as an
            early death. Default 10 — captures genuine laning disasters
            (dives, level-2 all-ins) without flagging normal mid-game trades.
            Minute 15 is too wide for ADC: a single death in a 15-min window
            is nearly guaranteed and produces noisy signal.
 
    Returned keys:
        match_id, champion, cs_at_15, cs_per_min (float),
        cumulative_cs (list[int|None], 16 values),
        early_death (bool),
        game_creation (int ms epoch)   <- useful for time-bucketing later
 
    Extension note: add `position_frames` here when heatmap work starts,
    it's in the same timeline object so no extra I/O.
    """
    try:
        match_data, timeline = load_match_and_timeline(match_id, user_dir)
    except FileNotFoundError:
        return None
 
    try:
        player = get_player_by_puuid(match_data, puuid)
    except ValueError:
        return None
 
    if not matches_champion_filter(player, champion_filter):
        return None
 
    # Exclude games that didn't reach 15 minutes — sub-15 FFs (either
    # side) and remakes are not valid laning samples for CS@15.
    # gameDuration is in seconds in modern match-v5 data.
    if match_data["info"].get("gameDuration", 0) < 15 * 60:
        return None
 
    pid = player["participantId"]
    cumulative = extract_cs_timeline(timeline, pid)
    frames = timeline["info"]["frames"]
 
    # cumulative[15] should always be populated now that we've gated on
    # game duration, but guard anyway for malformed timeline data.
    cs_at_15 = cumulative[15]
    if cs_at_15 is None:
        return None
 
    early_death = any(
        event.get("type") == "CHAMPION_KILL" and event.get("victimId") == pid
        for frame in frames[:early_death_before_minute]
        for event in frame.get("events", [])
    )
 
    return {
        "match_id": match_id,
        "champion": player["championName"],
        "cs_at_15": cs_at_15,
        "cs_per_min": round(cs_at_15 / 15, 2) if cs_at_15 is not None else None,
        "cumulative_cs": cumulative,
        "early_death": early_death,
        "win": player["win"],
        "game_creation": match_data["info"].get("gameCreation", 0),
    }
 
 
# ---------------------------------------------------------------------------
# Batch collection
# ---------------------------------------------------------------------------
 
def collect_cs_stats(
    puuid: str,
    user_dir: Path,
    num_matches: int = 20,
    champion_filter: str | None = None,
    early_death_before_minute: int = 10,
) -> pd.DataFrame:
    """
    Loads the most recent `num_matches` matches and returns a DataFrame of
    CS stats, one row per valid match (champion-filtered, files present).
 
    Columns: match_id, champion, cs_at_15, cs_per_min, cumulative_cs,
             early_death, game_creation.
 
    Args:
        early_death_before_minute: Passed to get_match_cs_stats. Default 10.
 
    This is the primary entry point for notebook analysis — call it once,
    then pass the DataFrame to any plotting or analysis function below.
    """
    match_files = get_recent_match_files(user_dir, num_matches=num_matches)
    rows = []
 
    for f in match_files:
        stats = get_match_cs_stats(
            f.stem, puuid, user_dir, champion_filter,
            early_death_before_minute=early_death_before_minute,
        )
        if stats is not None:
            rows.append(stats)
 
    if not rows:
        print("⚠ No matching data found.")
        return pd.DataFrame()
 
    df = pd.DataFrame(rows)
    df = df.sort_values("game_creation", ascending=True).reset_index(drop=True)
    df["match_number"] = range(1, len(df) + 1)   # chronological index for x-axis
    return df
 
 
# ---------------------------------------------------------------------------
# Printing / quick summaries
# ---------------------------------------------------------------------------
 
def print_cs_summary(df: pd.DataFrame) -> None:
    """Tabular console summary of CS@15 and early death flag."""
    if df.empty:
        print("No data.")
        return
    for _, row in df.iterrows():
        death_flag = "💀" if row["early_death"] else "  "
        result     = "W" if row["win"] else "L"
        print(
            f"[{result}] {death_flag} {row['match_id']} | {row['champion']:>12} | "
            f"CS@15: {row['cs_at_15']:>3} | CS/m: {row['cs_per_min']:.2f}"
        )
 
 
# ---------------------------------------------------------------------------
# Plotting
# ---------------------------------------------------------------------------
 
def plot_cs_at_15(
    df: pd.DataFrame,
    summoner_name: str = "",
    rolling_window: int = 5,
) -> None:
    """
    Bar chart of CS@15 per match encoding three variables:
      - Bar height : CS@15
      - Bar colour : win (blue) vs loss (red)
      - Hatch      : early death (before early_death_before_minute)
 
    This lets you see at a glance how the three interact — e.g. whether
    early deaths correlate with losses, or whether you can CS well through
    an early death and still win.
    """
    if df.empty:
        print("No data to plot.")
        return
 
    # Colour encodes win/loss; hatch encodes early death.
    # Keeping colour as the primary channel (most salient) for win/loss,
    # since that's the outcome variable. Early death is the modifier.
    WIN_COLOUR  = "#5b9bd5"   # blue
    LOSS_COLOUR = "#e05c5c"   # red
    HATCH       = "///"       # early death marker
 
    fig, ax = plt.subplots(figsize=(12, 5))
 
    for _, row in df.iterrows():
        colour = WIN_COLOUR if row["win"] else LOSS_COLOUR
        hatch  = HATCH if row["early_death"] else None
        ax.bar(
            row["match_number"], row["cs_at_15"],
            color=colour, hatch=hatch,
            alpha=0.85, edgecolor="white", linewidth=0.5,
        )
 
    # Rolling average
    if len(df) >= rolling_window:
        rolling = df["cs_at_15"].rolling(rolling_window, min_periods=rolling_window).mean()
        ax.plot(
            df["match_number"], rolling,
            color="orange", linewidth=2,
            label=f"Rolling avg ({rolling_window})",
        )
 
    ax.axhline(
        y=df["cs_at_15"].mean(), color="grey",
        linestyle="--", linewidth=1, label="Overall mean",
    )
 
    ax.set_xlabel("Match (chronological)")
    ax.set_ylabel("CS at 15 min")
    ax.set_title(f"CS@15 over time — {summoner_name or 'Player'}")
 
    from matplotlib.patches import Patch
    legend_entries = [
        ax.get_legend_handles_labels()[0][0],  # rolling avg line
        ax.get_legend_handles_labels()[0][1],  # overall mean line
        Patch(facecolor=WIN_COLOUR,  edgecolor="white", label="Win"),
        Patch(facecolor=LOSS_COLOUR, edgecolor="white", label="Loss"),
        Patch(facecolor="lightgrey", hatch=HATCH, edgecolor="grey", label="Early death"),
    ]
    ax.legend(handles=legend_entries)
 
    plt.tight_layout()
    plt.show()
 
 
def plot_cumulative_cs_curves(
    df: pd.DataFrame,
    summoner_name: str = "",
    bin_size: int = 5,
) -> None:
    """
    Mean cumulative CS curves grouped into chronological bins of `bin_size` matches.
 
    Bins are labelled oldest → newest so you can visually track improvement
    over time.
    """
    if df.empty:
        print("No data to plot.")
        return
 
    curves = [row for row in df["cumulative_cs"] if row is not None]
    if not curves:
        print("No timeline data available.")
        return
 
    fig, ax = plt.subplots(figsize=(10, 6))
    minutes = list(range(16))
 
    for i in range(0, len(curves), bin_size):
        group = [c for c in curves[i : i + bin_size] if c is not None]
        if not group:
            continue
        arr = np.array(
            [[v if v is not None else np.nan for v in curve] for curve in group],
            dtype=float,
        )
        mean_curve = np.nanmean(arr, axis=0)
        bin_label = f"Games {i + 1}–{i + len(group)}"
        ax.plot(minutes, mean_curve, linewidth=2, label=bin_label)
 
    ax.set_title(f"Cumulative CS over 15 min — {summoner_name or 'Player'} (bins of {bin_size})")
    ax.set_xlabel("Minute")
    ax.set_ylabel("Cumulative CS")
    ax.legend()
    ax.grid(True, alpha=0.4)
    plt.tight_layout()
    plt.show()
 
 
def plot_cs_delta_curves(
    df: pd.DataFrame,
    summoner_name: str = "",
    bin_size: int = 5,
) -> None:
    """
    Mean per-minute CS delta curves grouped into chronological bins.
 
    Useful for spotting which specific minutes are weak (e.g. consistent
    dip at minute 3–5 when the lane is being pushed in).
    """
    if df.empty:
        print("No data to plot.")
        return
 
    fig, ax = plt.subplots(figsize=(10, 6))
    minutes = list(range(16))
 
    delta_curves = [cs_deltas(row) for row in df["cumulative_cs"] if row is not None]
 
    for i in range(0, len(delta_curves), bin_size):
        group = delta_curves[i : i + bin_size]
        arr = np.array(
            [[v if v is not None else np.nan for v in curve] for curve in group],
            dtype=float,
        )
        mean_curve = np.nanmean(arr, axis=0)
        bin_label = f"Games {i + 1}–{i + len(group)}"
        ax.plot(minutes, mean_curve, linewidth=2, label=bin_label)
 
    ax.set_title(f"CS gained per minute — {summoner_name or 'Player'} (bins of {bin_size})")
    ax.set_xlabel("Minute")
    ax.set_ylabel("CS gained")
    ax.legend()
    ax.grid(True, alpha=0.4)
    plt.tight_layout()
    plt.show()
 
 
# ---------------------------------------------------------------------------
# Lane-phase analysis — all four bot-lane participants
# ---------------------------------------------------------------------------
# Unlike get_match_cs_stats (scoped to your own CS trend), these functions
# treat the 2v2 laning phase as the unit of analysis.  All data comes from
# the already-loaded match + timeline files — no additional API calls.
#
# Kill source classification
# --------------------------
# Every CHAMPION_KILL event carries killerId.  We resolve that ID against the
# five role slots we care about to label each death:
#
#   "lane"  — killed by the direct lane opponent (enemy ADC killed you, or
#              enemy support killed your support, etc.)
#   "gank"  — killed by the enemy jungler
#   "roam"  — killed by anyone else (mid roam, tp, dragon fight)
#   None    — did not die before the threshold minute
#
# This matters because a gank death says nothing about the 2v2 matchup; a
# lane kill does.  Separating them is what makes CS@15 interpretable.
 
 
 
def _resolve_bot_lane_participants(
    match_data: dict,
    puuid: str,
) -> dict:
    """
    Resolves the five participant dicts relevant to bot-lane analysis.
 
    Returns a dict with keys:
        you, your_support, enemy_adc, enemy_support, enemy_jungler
 
    Each value is the full participant dict from match_data["info"]["participants"],
    giving access to participantId, championName, win, teamPosition, etc.
 
    Raises ValueError if any role slot cannot be resolved (e.g. a non-standard
    game mode where teamPosition is unpopulated).
    """
    participants = match_data["info"]["participants"]
 
    you = next((p for p in participants if p["puuid"] == puuid), None)
    if you is None:
        raise ValueError("puuid not found in participants.")
 
    your_team_id  = you["teamId"]
    enemy_team_id = 200 if your_team_id == 100 else 100
 
    your_team  = [p for p in participants if p["teamId"] == your_team_id]
    enemy_team = [p for p in participants if p["teamId"] == enemy_team_id]
 
    def _find(team, position):
        p = next((p for p in team if p["teamPosition"] == position), None)
        if p is None:
            raise ValueError(
                f"Could not find {position} on team {team[0]['teamId']}. "
                "teamPosition may be unpopulated (ARAM / non-SR game mode)."
            )
        return p
 
    return {
        "you":            you,
        "your_support":   _find(your_team,  "UTILITY"),
        "enemy_adc":      _find(enemy_team, "BOTTOM"),
        "enemy_support":  _find(enemy_team, "UTILITY"),
        "enemy_jungler":  _find(enemy_team, "JUNGLE"),
    }
 
 
def _classify_death(
    frames: list,
    victim_id: int,
    opponent_ids: set[int],
    jungler_id: int,
    before_minute: int,
) -> KillSource:
    """
    Walks timeline frames up to `before_minute` looking for the first death
    of `victim_id` and classifies its source.
 
    Args:
        opponent_ids: participant IDs considered direct lane opponents for
                      this victim (e.g. {enemy_adc_id, enemy_support_id}
                      when classifying your death or your support's death).
        jungler_id:   enemy jungler's participant ID.
        before_minute: only deaths before this frame index count.
 
    Returns a KillSource enum value.
    """
    for frame in frames[:before_minute]:
        for event in frame.get("events", []):
            if event.get("type") != "CHAMPION_KILL":
                continue
            if event.get("victimId") != victim_id:
                continue
            killer = event.get("killerId", 0)
            if killer in opponent_ids:
                return KillSource.LANE
            if killer == jungler_id:
                return KillSource.GANK
            return KillSource.ROAM
    return KillSource.NONE
 
 
def get_lane_phase_stats(
    match_id: str,
    puuid: str,
    user_dir: Path,
    champion_filter: str | None = None,
    early_death_before_minute: int = 10,
) -> dict | None:
    """
    Returns a lane-phase stats dict covering all four bot-lane participants,
    or None if the match should be skipped.
 
    All data is read from the local match + timeline files already on disk.
    No API calls are made.
 
    Returned keys
    -------------
    match_id, game_creation, win
 
    Your side:
        your_champion, your_cs_at_15, your_cs_per_min,
        your_cumulative_cs,
        your_death_source   (KillSource: lane/gank/roam/none)
 
    Support:
        support_champion,
        support_death_source
 
    Enemy ADC:
        enemy_adc_champion, enemy_adc_cs_at_15, enemy_adc_cs_per_min,
        enemy_adc_cumulative_cs,
        enemy_adc_death_source
 
    Enemy support:
        enemy_support_champion,
        enemy_support_death_source
 
    CS differential:
        cs_diff_at_15   (your_cs_at_15 - enemy_adc_cs_at_15)
 
    Extension note: position_frames per participant can be added here
    for heatmap analysis — timeline is already loaded, zero extra I/O.
    """
    try:
        match_data, timeline = load_match_and_timeline(match_id, user_dir)
    except FileNotFoundError:
        return None
 
    # Game length gate — same rule as get_match_cs_stats
    if match_data["info"].get("gameDuration", 0) < 15 * 60:
        return None
 
    try:
        roles = _resolve_bot_lane_participants(match_data, puuid)
    except ValueError:
        return None  # ARAM / missing teamPosition data
 
    you           = roles["you"]
    your_support  = roles["your_support"]
    enemy_adc     = roles["enemy_adc"]
    enemy_support = roles["enemy_support"]
    enemy_jungler = roles["enemy_jungler"]
 
    if not matches_champion_filter(you, champion_filter):
        return None
 
    frames = timeline["info"]["frames"]
 
    # participant IDs as ints (timeline events use int, not str)
    your_id           = you["participantId"]
    support_id        = your_support["participantId"]
    enemy_adc_id      = enemy_adc["participantId"]
    enemy_support_id  = enemy_support["participantId"]
    enemy_jungler_id  = enemy_jungler["participantId"]
 
    # CS timelines — reuses the existing primitive
    your_cs      = extract_cs_timeline(timeline, your_id)
    enemy_adc_cs = extract_cs_timeline(timeline, enemy_adc_id)
 
    your_cs_at_15      = your_cs[15]
    enemy_adc_cs_at_15 = enemy_adc_cs[15]
 
    if your_cs_at_15 is None or enemy_adc_cs_at_15 is None:
        return None  # malformed timeline
 
    # Death source classification for all four bot-laners.
    # "opponent_ids" for each victim is the two players on the other side of
    # the 2v2 — if the enemy ADC kills you, that's a lane kill; if your own
    # support somehow gets the kill that's a roam (covered by the fallthrough).
    your_death_source = _classify_death(
        frames, your_id,
        opponent_ids={enemy_adc_id, enemy_support_id},
        jungler_id=enemy_jungler_id,
        before_minute=early_death_before_minute,
    )
    support_death_source = _classify_death(
        frames, support_id,
        opponent_ids={enemy_adc_id, enemy_support_id},
        jungler_id=enemy_jungler_id,
        before_minute=early_death_before_minute,
    )
    enemy_adc_death_source = _classify_death(
        frames, enemy_adc_id,
        # "opponent" from the enemy ADC's perspective = your side
        opponent_ids={your_id, support_id},
        # enemy jungler is your jungler from their perspective — resolve it
        jungler_id=next(
            p["participantId"] for p in match_data["info"]["participants"]
            if p["teamId"] == you["teamId"] and p["teamPosition"] == "JUNGLE"
        ),
        before_minute=early_death_before_minute,
    )
    enemy_support_death_source = _classify_death(
        frames, enemy_support_id,
        opponent_ids={your_id, support_id},
        jungler_id=next(
            p["participantId"] for p in match_data["info"]["participants"]
            if p["teamId"] == you["teamId"] and p["teamPosition"] == "JUNGLE"
        ),
        before_minute=early_death_before_minute,
    )
 
    return {
        "match_id":        match_id,
        "game_creation":   match_data["info"].get("gameCreation", 0),
        "win":             you["win"],
 
        # Your side
        "your_champion":        you["championName"],
        "your_cs_at_15":        your_cs_at_15,
        "your_cs_per_min":      round(your_cs_at_15 / 15, 2),
        "your_cumulative_cs":   your_cs,
        "your_death_source":    your_death_source,
 
        # Support
        "support_champion":      your_support["championName"],
        "support_death_source":  support_death_source,
 
        # Enemy ADC
        "enemy_adc_champion":        enemy_adc["championName"],
        "enemy_adc_cs_at_15":        enemy_adc_cs_at_15,
        "enemy_adc_cs_per_min":      round(enemy_adc_cs_at_15 / 15, 2),
        "enemy_adc_cumulative_cs":   enemy_adc_cs,
        "enemy_adc_death_source":    enemy_adc_death_source,
 
        # Enemy support
        "enemy_support_champion":      enemy_support["championName"],
        "enemy_support_death_source":  enemy_support_death_source,
 
        # Derived
        "cs_diff_at_15": your_cs_at_15 - enemy_adc_cs_at_15,
    }
 
 
def collect_lane_phase_stats(
    puuid: str,
    user_dir: Path,
    num_matches: int = 20,
    champion_filter: str | None = None,
    early_death_before_minute: int = 10,
) -> pd.DataFrame:
    """
    Batch version of get_lane_phase_stats.
 
    Returns a DataFrame with one row per valid match, sorted chronologically.
    Adds a `match_number` column (1-indexed) for use as a plot x-axis.
 
    Skips matches that are:
      - shorter than 15 minutes
      - missing local files
      - missing teamPosition data (ARAM etc.)
      - filtered out by champion_filter
    """
    match_files = get_recent_match_files(user_dir, num_matches=num_matches)
    rows = []
 
    for f in match_files:
        stats = get_lane_phase_stats(
            f.stem, puuid, user_dir, champion_filter,
            early_death_before_minute=early_death_before_minute,
        )
        if stats is not None:
            rows.append(stats)
 
    if not rows:
        print("⚠ No matching lane-phase data found.")
        return pd.DataFrame()
 
    df = pd.DataFrame(rows)
    df = df.sort_values("game_creation", ascending=True).reset_index(drop=True)
    df["match_number"] = range(1, len(df) + 1)
    return df