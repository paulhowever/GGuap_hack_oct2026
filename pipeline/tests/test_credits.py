from refpipe.cli import main
from refpipe.credits import HEADER, render_credits

NIGHT_META = """\
title: Night Song
artist: Example Artist
language: en
voice: male
source:
  origin: ultrasinger
  generator: UltraSinger
  t0_ms: 61200
license:
  music: &work
    title: Night Song
    author: Example Artist
    license: CC BY 4.0
    source: https://example.org/night-song
    license_url: https://creativecommons.org/licenses/by/4.0/
    screenshot: license.png
  recording: *work
  attribution: «Night Song», Example Artist, CC BY 4.0
  changes:
    - fragment 61.2-92.2 s
vocalists: []
"""

EXPECTED_LINES = [
    "",
    "## Демо-гамма — команда (`a-demo`)",
    "",
    "- Music and lyrics: «Демо-гамма», huap team, own",
    "- Recording: «Демо-гамма», huap team, own",
    "- Attribution: huap team",
    "",
    "## Night Song — Example Artist (`b-night`)",
    "",
    (
        "- Music and lyrics: «Night Song», Example Artist, CC BY 4.0, "
        "https://creativecommons.org/licenses/by/4.0/, source: https://example.org/night-song"
    ),
    (
        "- Recording: «Night Song», Example Artist, CC BY 4.0, "
        "https://creativecommons.org/licenses/by/4.0/, source: https://example.org/night-song"
    ),
    "- Changes: fragment 61.2-92.2 s",
    "- Reference notes: generated with UltraSinger (MIT), checked by hand",
    "- Attribution: «Night Song», Example Artist, CC BY 4.0",
    "",
]
EXPECTED = HEADER + "\n".join(EXPECTED_LINES)


def make_songs(tmp_path, demo_meta_text):
    songs = tmp_path / "songs"
    for name, text in (("b-night", NIGHT_META), ("a-demo", demo_meta_text)):
        (songs / name).mkdir(parents=True)
        (songs / name / "meta.yaml").write_text(text, encoding="utf-8")
    (songs / "README.md").write_text("songs\n", encoding="utf-8")
    return songs


def test_render_credits(tmp_path, demo_meta_text):
    assert render_credits(make_songs(tmp_path, demo_meta_text)) == EXPECTED


def test_vocalists_line(tmp_path, demo_meta_text):
    songs = tmp_path / "songs"
    (songs / "x").mkdir(parents=True)
    text = demo_meta_text.replace(
        "vocalists: []", "vocalists:\n  - name: Анна\n    consent: true\n  - name: Борис\n    consent: true"
    )
    (songs / "x" / "meta.yaml").write_text(text, encoding="utf-8")
    assert "- Vocals: Анна, Борис\n" in render_credits(songs)


def test_empty_songs_dir(tmp_path):
    (tmp_path / "songs").mkdir()
    assert render_credits(tmp_path / "songs") == HEADER


def test_cli_credits(tmp_path, demo_meta_text, capsys):
    out = tmp_path / "CREDITS.md"
    assert main(["credits", "--songs", str(make_songs(tmp_path, demo_meta_text)), "--out", str(out)]) == 0
    assert out.read_text(encoding="utf-8") == EXPECTED
    assert "2 songs" in capsys.readouterr().out


def test_cli_credits_rejects_bad_meta(tmp_path, demo_meta_text, capsys):
    songs = make_songs(tmp_path, demo_meta_text)
    (songs / "c-bad").mkdir()
    (songs / "c-bad" / "meta.yaml").write_text(
        demo_meta_text.replace("license: own", "license: CC BY-ND 4.0"), encoding="utf-8"
    )
    out = tmp_path / "C.md"
    assert main(["credits", "--songs", str(songs), "--out", str(out)]) == 2
    assert "not allowed" in capsys.readouterr().err
    assert not out.exists()


def test_cli_credits_keeps_out_when_songs_dir_is_not_a_directory(tmp_path, capsys):
    out = tmp_path / "CREDITS.md"
    out.write_text("keep\n", encoding="utf-8")
    regular_file = tmp_path / "songs.txt"
    regular_file.write_text("x\n", encoding="utf-8")
    for songs in (tmp_path / "typo", regular_file):
        assert main(["credits", "--songs", str(songs), "--out", str(out)]) == 2
        assert out.read_text(encoding="utf-8") == "keep\n"
    assert "not a songs directory" in capsys.readouterr().err


def test_cli_credits_reports_unwritable_out(tmp_path, demo_meta_text, capsys):
    out = tmp_path / "missing" / "CREDITS.md"
    assert main(["credits", "--songs", str(make_songs(tmp_path, demo_meta_text)), "--out", str(out)]) == 2
    err = capsys.readouterr().err
    assert err.startswith("refpipe: ")
    assert "CREDITS.md" in err
