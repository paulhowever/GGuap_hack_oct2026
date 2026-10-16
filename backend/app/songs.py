import json
import logging
from pathlib import Path

from app.core.logging import log_event
from app.ids import SONG_ID

log = logging.getLogger("karaoke.songs")
BROKEN = (OSError, ValueError, KeyError, TypeError, AttributeError)

__all__ = ["SONG_ID", "SongRepo"]


def item_of(ref: dict) -> dict:
    lic = ref.get("license", {})
    return {
        "id": ref["id"],
        "title": ref["title"],
        "artist": ref["artist"],
        "duration": ref["audio"]["duration"],
        "difficulty": ref["stats"]["difficulty"],
        "range_midi": ref["stats"]["range_midi"],
        "license": {
            "short": lic.get("recording") or lic.get("music"),
            "attribution": lic.get("attribution"),
        },
        "top": None,
    }


def skip(song_dir: Path, error: Exception) -> None:
    log.warning(
        "song_skipped", extra={"fields": {"dir": song_dir.name, "error": f"{type(error).__name__}: {error}"}}
    )


class SongRepo:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.skipped: list[str] = []

    def _load(self, song_dir: Path) -> dict | None:
        ref_path = song_dir / "reference.json"
        if not ref_path.is_file():
            return None
        if not SONG_ID.match(song_dir.name):
            raise ValueError(f"dir name must match {SONG_ID.pattern}")
        check_path = song_dir / "check.json"
        if check_path.is_file():
            check = json.loads(check_path.read_text(encoding="utf-8"))
            if not isinstance(check, dict):
                raise ValueError("check.json is not an object")
            if not check.get("pass", True):
                log_event(log, "song_hidden", dir=song_dir.name, reason="check_failed")
                return None
        ref = json.loads(ref_path.read_text(encoding="utf-8"))
        if ref["id"] != song_dir.name:
            raise ValueError(f"reference id {ref['id']!r} differs from dir name")
        return ref

    def _entry(self, song_dir: Path) -> tuple[dict, dict] | None:
        ref = self._load(song_dir)
        return None if ref is None else (ref, item_of(ref))

    def get(self, song_id: str) -> dict | None:
        if not SONG_ID.match(song_id):
            return None
        song_dir = self.root / song_id
        try:
            entry = self._entry(song_dir)
        except BROKEN as error:
            skip(song_dir, error)
            return None
        return None if entry is None else entry[0]

    def list(self) -> list[dict]:
        if not self.root.is_dir():
            self.skipped = []
            return []
        out, skipped = [], []
        for d in sorted(p for p in self.root.iterdir() if p.is_dir()):
            try:
                entry = self._entry(d)
            except BROKEN as error:
                skip(d, error)
                skipped.append(d.name)
                continue
            if entry is not None:
                out.append(entry[1])
        self.skipped = skipped
        return out

    def count(self) -> int:
        if not self.root.is_dir():
            raise FileNotFoundError(str(self.root))
        return len(self.list())
