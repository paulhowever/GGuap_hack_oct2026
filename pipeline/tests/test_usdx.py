import pytest

from refpipe import usdx
from refpipe.errors import UsdxError


def make(
    *body: str, headers: tuple[str, ...] = ("#TITLE:T", "#ARTIST:A", "#MP3:a.mp3", "#BPM:300", "#GAP:0")
) -> str:
    return "\n".join([*headers, *body, "E"]) + "\n"


def test_parse_demo(demo_txt):
    song = usdx.parse(demo_txt)
    assert (song.title, song.artist, song.audio) == ("Демо-гамма", "команда", "minus.mp3")
    assert song.bpm == 300.0
    assert song.gap_ms == 2500.0
    assert [len(line.notes) for line in song.lines] == [3, 3]
    assert song.lines[0].break_beat == 60
    assert song.lines[1].break_beat is None
    assert song.notes[0].syl == "до "
    assert song.notes[2].type == "golden"
    assert song.extra == {"LANGUAGE": "Russian"}


def test_note_times(demo_txt):
    song = usdx.parse(demo_txt)
    assert song.beat_s == pytest.approx(0.05)
    assert song.note_t(song.notes[3]) == pytest.approx(6.0)
    assert song.note_end_t(song.notes[5]) == pytest.approx(8.9)


def test_decimal_comma_and_audio_header():
    text = make(": 0 4 0 a", headers=("#TITLE:T", "#ARTIST:A", "#AUDIO:x.ogg", "#BPM:287,5", "#GAP:1234,5"))
    song = usdx.parse(text)
    assert song.bpm == 287.5
    assert song.gap_ms == 1234.5
    assert song.audio == "x.ogg"


def test_all_note_types():
    song = usdx.parse(make(": 0 2 0 a", "* 2 2 0 b", "F 4 2 0 c", "R 6 2 0 d", "G 8 2 0 e"))
    assert [n.type for n in song.notes] == ["normal", "golden", "free", "rap", "rap_golden"]


def test_crlf_bom_and_cp1251(demo_txt):
    assert usdx.parse(demo_txt.replace("\n", "\r\n")).notes[0].syl == "до "
    assert usdx.decode_text("\ufeff".encode() + demo_txt.encode("utf-8")) == demo_txt
    assert usdx.decode_text(demo_txt.encode("cp1251")) == demo_txt


def test_read_cp1251_file(tmp_path, demo_txt):
    path = tmp_path / "song.txt"
    path.write_bytes(demo_txt.encode("cp1251"))
    assert usdx.read(path).title == "Демо-гамма"


@pytest.mark.parametrize("kind", ["missing", "directory", "undecodable"])
def test_read_failures_are_usdx_errors(tmp_path, kind):
    path = tmp_path / "song.txt"
    if kind == "directory":
        path.mkdir()
    elif kind == "undecodable":
        path.write_bytes(b"#TITLE:\x98\n")
    with pytest.raises(UsdxError, match="song.txt"):
        usdx.read(path)


def test_trailing_break_before_end_is_dropped():
    song = usdx.parse(make(": 0 4 0 a", "- 6", ": 8 4 0 b", "- 14"))
    assert [line.break_beat for line in song.lines] == [6, None]


@pytest.mark.parametrize(
    ("text", "message"),
    [
        (
            make(
                ": 0 4 0 a",
                headers=("#TITLE:T", "#ARTIST:A", "#MP3:a", "#BPM:300", "#GAP:0", "#RELATIVE:yes"),
            ),
            "RELATIVE",
        ),
        (make("P1", ": 0 4 0 a"), "duet"),
        (
            make(": 0 4 0 a", headers=("#TITLE:T", "#ARTIST:A", "#MP3:a", "#BPM:300", "#GAP:0", "#P1:X")),
            "duet",
        ),
        (make(), "no notes"),
        (make(": 0 4 0 a", headers=("#TITLE:T", "#ARTIST:A", "#BPM:300", "#GAP:0")), "AUDIO"),
        (make(": 0 4 0 a", headers=("#TITLE:T", "#ARTIST:A", "#MP3:a", "#GAP:0")), "BPM"),
        (make(": 0 4 0 a", headers=("#TITLE:T", "#ARTIST:A", "#MP3:a", "#BPM:0", "#GAP:0")), "BPM"),
        (make(": 0 4 0 a", headers=("#TITLE:T", "#ARTIST:A", "#MP3:a", "#BPM:x", "#GAP:0")), "not a number"),
        (make(": 0 x 0 a"), "line 6"),
    ],
)
def test_rejects(text, message):
    with pytest.raises(UsdxError, match=message):
        usdx.parse(text)


def test_roundtrip(tmp_path, demo_txt):
    song = usdx.parse(demo_txt)
    usdx.write(song, tmp_path / "song.txt")
    assert usdx.read(tmp_path / "song.txt") == song
    text = usdx.serialize(song)
    assert text.splitlines()[:7] == [
        "#TITLE:Демо-гамма",
        "#ARTIST:команда",
        "#LANGUAGE:Russian",
        "#MP3:minus.mp3",
        "#AUDIO:minus.mp3",
        "#BPM:300",
        "#GAP:2500",
    ]
    assert text.endswith("- 60\n: 70 16 5 фа \n: 90 16 7 соль \n: 110 18 9 ля\nE\n")


def test_fmt_num():
    assert usdx.fmt_num(300.0) == "300"
    assert usdx.fmt_num(287.5) == "287.5"
    assert usdx.fmt_num(1234.56789) == "1234.568"
