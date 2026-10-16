import re
from typing import Literal

from app.duel import CHALLENGE_ID

SONG_ID_PATTERN = r"^[a-z0-9_-]{1,64}$"
SONG_ID = re.compile(SONG_ID_PATTERN)
CLIENT_ID_PATTERN = r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"

Difficulty = Literal["easy", "normal", "hard"]

__all__ = ["CHALLENGE_ID", "CLIENT_ID_PATTERN", "SONG_ID", "SONG_ID_PATTERN", "Difficulty"]
