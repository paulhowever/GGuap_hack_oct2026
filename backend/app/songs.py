import json
import re
from pathlib import Path

SONG_ID = re.compile(r"^[a-z0-9_-]{1,64}$")


class SongRepo:
    def __init__(self, root: Path) -> None:
        self.root = root

    def _load(self, song_dir: Path) -> dict | None:
        ref_path = song_dir / "reference.json"
        if not ref_path.is_file():
            return None
        check_path = song_dir / "check.json"
        if check_path.is_file() and not json.loads(check_path.read_text(encoding="utf-8")).get("pass", True):
            return None
        return json.loads(ref_path.read_text(encoding="utf-8"))

    def get(self, song_id: str) -> dict | None:
        if not SONG_ID.match(song_id):
            return None
        return self._load(self.root / song_id)

    def list(self) -> list[dict]:
        if not self.root.is_dir():
            return []
        out = []
        for d in sorted(p for p in self.root.iterdir() if p.is_dir()):
            ref = self._load(d)
            if ref is None:
                continue
            lic = ref.get("license", {})
            out.append(
                {
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
            )
        return out

    def count(self) -> int:
        if not self.root.is_dir():
            raise FileNotFoundError(str(self.root))
        return len(self.list())
