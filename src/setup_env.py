import os
import sys
from pathlib import Path
from dotenv import load_dotenv


def find_repo_root_by_subfolders(start_path: Path, required_subfolders=("src", "notebooks"), max_up=5) -> Path:
    """
    Walks up from start_path up to max_up levels to find a folder
    containing all required_subfolders.
    Returns the Path to the repo root or raises FileNotFoundError.
    """
    current = start_path.resolve()
    for _ in range(max_up):
        if all((current / subfolder).exists() for subfolder in required_subfolders):
            return current
        current = current.parent
    raise FileNotFoundError(
        f"Could not find repo root containing {required_subfolders} "
        f"within {max_up} levels up from {start_path}"
    )


def initialize_environment():
    """
    Initializes the project environment:
    - Locates repo root
    - Adds src to sys.path
    - Loads environment variables
    - Returns key paths and headers
    """
    cwd = Path().resolve()
    repo_root = find_repo_root_by_subfolders(cwd)
    src_path = repo_root / "src"
    notebooks_path = repo_root / "notebooks"

    if str(src_path) not in sys.path:
        sys.path.append(str(src_path))

    dotenv_path = repo_root / ".env"
    load_dotenv(dotenv_path=dotenv_path)

    riot_api_key = os.getenv("RIOT_API_KEY")
    if not riot_api_key:
        raise ValueError("RIOT_API_KEY not found in .env")

    headers = {
        "X-Riot-Token": riot_api_key
    }

    # Optional routing from .env, or defaults
    region_routing = os.getenv("REGION_ROUTING", "europe")
    platform_routing = os.getenv("PLATFORM_ROUTING", "euw1")

    return {
        "repo_root": repo_root,
        "src_path": src_path,
        "notebooks_path": notebooks_path,
        "riot_api_key": riot_api_key,
        "headers": headers,
        "region_routing": region_routing,
        "platform_routing": platform_routing
    }

