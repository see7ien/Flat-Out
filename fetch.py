from pathlib import Path

import fastf1

CACHE = Path(__file__).parent / "cache"


def load_quali(year, event):
    """Return a loaded FastF1 qualifying session, cached to cache/."""
    fastf1.Cache.enable_cache(str(CACHE))
    session = fastf1.get_session(year, event, "Q")
    session.load()
    return session
