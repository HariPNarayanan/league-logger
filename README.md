# league-logger

A personal League of Legends match and timeline data logger using Riot Games API.

## Overview

This project syncs match and timeline data for a specified summoner, saving detailed JSON files locally for analysis. It supports filtering by champion and match dates and leverages Riot’s official API endpoints with updated Riot ID formats.

## Features

- Fetch summoner info by Riot ID (e.g. `RainbowThenga#420`).
- Retrieve recent ranked solo queue matches.
- Download match details and timelines.
- Filter matches by champion and date range.
- Automatically manage local storage of match data.
- Rate-limited API calls to comply with Riot’s usage policies.

## Setup

1. Clone the repository:
   ```bash
   git clone https://github.com/yourusername/league-logger.git
   cd league-logger/league-logger

2. Create a .env file in the repo root with your Riot API key and region routing:

RIOT_API_KEY=your_api_key_here
REGION_ROUTING=europe

3. Install dependencies:

pip install -r requirements.txt

Run syncing script (e.g. from Jupyter notebook or directly):

    from sync import sync_user_data

    sync_user_data("RainbowThenga#420")

## Usage

    Modify parameters like champion_name, start_time, and end_time to filter sync data.

    JSON data is saved inside the data/users folder by default.

    Use provided analysis notebooks or scripts to explore your saved data.

## Notes

    The repo dynamically finds its root directory, so scripts work seamlessly from notebooks or command line.

    Make sure to respect Riot’s API rate limits.

    The data/ folder is large and should be added to .gitignore to avoid pushing to GitHub.

## Future Work

    Add support for Data Dragon assets and champion mastery data.

    Expand analysis scripts for deeper insights.

    Improve caching and error handling.

