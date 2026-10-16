import mido
import pytest

from refpipe import usdx
from refpipe.cli import main
from refpipe.compile import compile_dir, line_text
from refpipe.errors import MidiError
from refpipe.frommidi import build_song, from_midi, melody_notes, syllables, txt_bpm

TPB = 480
MELODY = [(60, 1, 0), (62, 1, 0), (64, 2, 1), (65, 1, 0), (67, 1, 0)]


def write_midi(path, notes, tempo_bpm=120.0, lead_beats=4, channel=0):
    mid = mido.MidiFile(ticks_per_beat=TPB)
    track = mido.MidiTrack()
    mid.tracks.append(track)
    track.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(tempo_bpm), time=0))
    wait = lead_beats * TPB
    for pitch, beats, rest in notes:
        track.append(mido.Message("note_on", note=pitch, velocity=90, channel=channel, time=wait))
        track.append(mido.Message("note_off", note=pitch, velocity=0, channel=channel, time=int(beats * TPB)))
        wait = int(rest * TPB)
    mid.save(str(path))
    return path


@pytest.fixture
def gamma(tmp_path):
    lyrics = tmp_path / "lyrics.txt"
    lyrics.write_text("до ре ми\nфа соль\n", encoding="utf-8")
    return write_midi(tmp_path / "melody.mid", MELODY), lyrics


def test_syllables():
    assert syllables("Ка-лин-ка мо-я!\n\n  ой  \n") == [["Ка", "лин", "ка ", "мо", "я!"], ["ой"]]
    assert syllables("мо-я-~ да") == [["мо", "я", "~ ", "да"]]


def test_txt_bpm():
    assert txt_bpm(mido.bpm2tempo(120)) == 240.0
    assert txt_bpm(mido.bpm2tempo(250)) == 250.0
    assert txt_bpm(mido.bpm2tempo(60)) == 240.0


def test_from_midi_builds_expected_txt(gamma):
    song = from_midi(*gamma, "Гамма", "нар.")
    assert song.bpm == 240.0
    assert song.gap_ms == 2000.0
    assert usdx.serialize(song).splitlines()[2:] == [
        "#VOCALS:guide.mp3",
        "#CREATOR:refpipe from-midi",
        "#MP3:minus.mp3",
        "#AUDIO:minus.mp3",
        "#BPM:240",
        "#GAP:2000",
        ": 0 8 0 до ",
        ": 8 8 2 ре ",
        ": 16 16 4 ми",
        "- 32",
        ": 40 8 5 фа ",
        ": 48 8 7 соль",
        "E",
    ]


def test_offset_and_bpm_override(gamma):
    song = from_midi(*gamma, "T", "A", offset_ms=150, bpm=300)
    assert song.gap_ms == 2150.0
    assert [n.beat for n in song.notes] == [0, 10, 20, 50, 60]
    assert [n.length for n in song.notes] == [10, 10, 20, 10, 10]


def test_syllable_mismatch(gamma, tmp_path):
    lyrics = tmp_path / "short.txt"
    lyrics.write_text("до ре\nфа соль\n", encoding="utf-8")
    with pytest.raises(MidiError, match="4 syllables"):
        from_midi(gamma[0], lyrics, "T", "A")


def test_auto_channel_and_missing_channel(tmp_path, gamma):
    midi = write_midi(tmp_path / "ch3.mid", MELODY, channel=3)
    assert len(from_midi(midi, gamma[1], "T", "A").notes) == 5
    with pytest.raises(MidiError, match="channel 0"):
        from_midi(midi, gamma[1], "T", "A", channel=0)


def test_legato_overlap_is_truncated(tmp_path):
    mid = mido.MidiFile(ticks_per_beat=TPB)
    track = mido.MidiTrack()
    mid.tracks.append(track)
    track.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(120), time=0))
    track.append(mido.Message("note_on", note=60, velocity=90, time=0))
    track.append(mido.Message("note_on", note=62, velocity=90, time=480))
    track.append(mido.Message("note_off", note=60, velocity=0, time=120))
    track.append(mido.Message("note_off", note=62, velocity=0, time=360))
    mid.save(str(tmp_path / "legato.mid"))
    lyrics = tmp_path / "l.txt"
    lyrics.write_text("a b\n", encoding="utf-8")
    song = from_midi(tmp_path / "legato.mid", lyrics, "T", "A")
    assert [(n.beat, n.length, n.pitch) for n in song.notes] == [(0, 8, 0), (8, 8, 2)]
    assert song.gap_ms == 0.0


def test_output_compiles(tmp_path, gamma, demo_meta_text):
    song_dir = tmp_path / "gamma"
    song_dir.mkdir()
    usdx.write(from_midi(*gamma, "Гамма", "нар."), song_dir / "song.txt")
    (song_dir / "meta.yaml").write_text(demo_meta_text, encoding="utf-8")
    ref = compile_dir(song_dir, duration=8.0)
    assert ref["stats"]["first_note"] == 2.0
    assert [n["midi"] for line in ref["lines"] for n in line["notes"]] == [60, 62, 64, 65, 67]
    assert [line["text"] for line in ref["lines"]] == ["до ре ми", "фа соль"]


def test_cli_from_midi(tmp_path, gamma, capsys):
    out = tmp_path / "songs" / "gamma" / "song.txt"
    assert (
        main(
            [
                "from-midi",
                str(gamma[0]),
                str(gamma[1]),
                "-o",
                str(out),
                "--title",
                "Гамма",
                "--artist",
                "нар.",
            ]
        )
        == 0
    )
    assert usdx.read(out).title == "Гамма"
    assert "5 notes, 2 lines, BPM 240, GAP 2000" in capsys.readouterr().out


def test_colliding_onsets_rejected():
    with pytest.raises(MidiError, match=r"melody note 2 at 0\.030 s"):
        build_song([(0.0, 0.02, 60), (0.03, 0.5, 62)], [["a", "b"]], 240.0, "T", "A")


def test_phrase_break_follows_floored_last_note():
    song = build_song([(0.0, 0.03, 60), (0.2, 0.5, 62)], [["a"], ["b"]], 240.0, "T", "A")
    assert song.lines[0].notes[-1].end == 1
    assert song.lines[0].break_beat == 1
    assert "- 1\n" in usdx.serialize(song)


def write_raw(path, messages, tempo_bpm=120.0, end_tick=None):
    mid = mido.MidiFile(ticks_per_beat=TPB)
    track = mido.MidiTrack()
    mid.tracks.append(track)
    track.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(tempo_bpm), time=0))
    prev = 0
    for tick, kind, pitch, *channel in messages:
        velocity = 90 if kind == "note_on" else 0
        track.append(
            mido.Message(
                kind, note=pitch, velocity=velocity, channel=channel[0] if channel else 0, time=tick - prev
            )
        )
        prev = tick
    if end_tick is not None:
        track.append(mido.MetaMessage("end_of_track", time=end_tick - prev))
    mid.save(str(path))
    return path


REPEATED_PITCH = {
    "off_first": [(0, "note_on", 64), (480, "note_off", 64), (480, "note_on", 64), (960, "note_off", 64)],
    "on_first": [(0, "note_on", 64), (480, "note_on", 64), (480, "note_off", 64), (960, "note_off", 64)],
}


@pytest.mark.parametrize("messages", REPEATED_PITCH.values(), ids=REPEATED_PITCH.keys())
def test_repeated_pitch_on_a_shared_tick_is_kept(tmp_path, messages):
    mid = mido.MidiFile(str(write_raw(tmp_path / "rep.mid", messages)))
    assert melody_notes(mid) == [(0.0, 0.5, 64), (0.5, 1.0, 64)]


def test_note_without_note_off_ends_with_the_track(tmp_path):
    messages = [(0, "note_on", 60), (480, "note_off", 60), (480, "note_on", 62)]
    mid = mido.MidiFile(str(write_raw(tmp_path / "open.mid", messages, end_tick=960)))
    assert melody_notes(mid) == [(0.0, 0.5, 60), (0.5, 1.0, 62)]


@pytest.mark.parametrize("bpm", ["0", "-5"])
def test_cli_rejects_non_positive_bpm(gamma, tmp_path, capsys, bpm):
    out = tmp_path / "song.txt"
    argv = ["from-midi", str(gamma[0]), str(gamma[1]), "-o", str(out), "--title", "T", "--artist", "A"]
    assert main([*argv, f"--bpm={bpm}"]) == 2
    assert "refpipe: --bpm must be positive" in capsys.readouterr().err
    assert not out.exists()


def test_mismatch_names_channel_and_counts(tmp_path, capsys):
    messages = [(0, "note_on", 60, 0), (480, "note_off", 60, 0)]
    for k in range(4):
        messages += [(480 * (k + 1), "note_on", 64 + k, 3), (480 * (k + 2), "note_off", 64 + k, 3)]
    messages.sort(key=lambda m: m[0])
    midi = write_raw(tmp_path / "two.mid", messages)
    lyrics = tmp_path / "l.txt"
    lyrics.write_text("a b c\n", encoding="utf-8")
    out = tmp_path / "song.txt"
    argv = ["from-midi", str(midi), str(lyrics), "-o", str(out), "--title", "T", "--artist", "A"]
    assert main(argv) == 2
    err = capsys.readouterr().err
    assert "channel 3" in err
    assert "0: 1" in err and "3: 4" in err
    assert "--channel" in err


@pytest.mark.parametrize(
    ("payload", "reason"),
    [(b"not a midi file", "MThd"), (b"MThd\x00\x00\x00\x06\x00\x01\x00\x01", "EOFError")],
    ids=["no_header", "truncated"],
)
def test_bad_midi_file_is_reported(tmp_path, gamma, capsys, payload, reason):
    bad = tmp_path / "bad.mid"
    bad.write_bytes(payload)
    argv = [
        "from-midi",
        str(bad),
        str(gamma[1]),
        "-o",
        str(tmp_path / "s.txt"),
        "--title",
        "T",
        "--artist",
        "A",
    ]
    assert main(argv) == 2
    err = capsys.readouterr().err
    assert err.startswith("refpipe: ")
    assert "bad.mid" in err
    assert reason in err


def test_missing_midi_and_lyrics_are_reported(tmp_path, gamma, capsys):
    base = ["-o", str(tmp_path / "s.txt"), "--title", "T", "--artist", "A"]
    assert main(["from-midi", str(tmp_path / "none.mid"), str(gamma[1]), *base]) == 2
    assert main(["from-midi", str(gamma[0]), str(tmp_path / "none.txt"), *base]) == 2
    err = capsys.readouterr().err.splitlines()
    assert "none.mid" in err[0] and "none.txt" in err[1]
    assert all(line.startswith("refpipe: ") for line in err)


def test_undecodable_lyrics_are_reported(tmp_path, gamma, capsys):
    lyrics = tmp_path / "bad.txt"
    lyrics.write_bytes(b"\x98\x98\n")
    argv = [
        "from-midi",
        str(gamma[0]),
        str(lyrics),
        "-o",
        str(tmp_path / "s.txt"),
        "--title",
        "T",
        "--artist",
        "A",
    ]
    assert main(argv) == 2
    assert "bad.txt" in capsys.readouterr().err


@pytest.mark.parametrize(
    "encode", [lambda t: t.encode("utf-8-sig"), lambda t: t.encode("cp1251")], ids=["bom", "cp1251"]
)
def test_lyrics_with_bom_or_cp1251(tmp_path, gamma, encode):
    lyrics = tmp_path / "enc.txt"
    lyrics.write_bytes(encode("до ре ми\nфа соль\n"))
    song = from_midi(gamma[0], lyrics, "T", "A")
    assert [n.syl for n in song.notes][:2] == ["до ", "ре "]


def test_double_hyphen_keeps_literal_hyphen():
    syls = syllables("Ой, пол-ным--пол-на мо-я\n")
    assert syls == [["Ой, ", "пол", "ным-", "пол", "на ", "мо", "я"]]
    notes = tuple(usdx.Note(":", 2 * k, 2, 0, syl) for k, syl in enumerate(syls[0]))
    assert line_text(usdx.Line(notes, None)) == "Ой, полным-полна моя"


def test_standalone_dash_is_glued_to_previous_syllable():
    syls = syllables("Ка-лин-ка — мо-я\nой …\n— ой\n")
    assert syls[0] == ["Ка", "лин", "ка — ", "мо", "я"]
    assert syls[1] == ["ой …"]
    assert syls[2] == ["— ", "ой"]


def test_tilde_and_bare_hyphen_keep_old_meaning():
    assert syllables("мо-я-~") == [["мо", "я", "~"]]
    assert syllables("ка - мо") == [["ка ", "мо"]]
    assert syllables("Ка-лин-ка мо-я!") == [["Ка", "лин", "ка ", "мо", "я!"]]


def test_literal_hyphen_survives_compile(tmp_path, demo_meta_text):
    melody = write_midi(tmp_path / "melody.mid", [(60 + k, 1, 0) for k in range(7)])
    lyrics = tmp_path / "lyrics.txt"
    lyrics.write_text("Ой, пол-ным--пол-на мо-я\n", encoding="utf-8")
    song_dir = tmp_path / "korobeiniki"
    song_dir.mkdir()
    usdx.write(from_midi(melody, lyrics, "Коробейники", "нар."), song_dir / "song.txt")
    (song_dir / "meta.yaml").write_text(demo_meta_text, encoding="utf-8")
    ref = compile_dir(song_dir, duration=8.0)
    assert [line["text"] for line in ref["lines"]] == ["Ой, полным-полна моя"]
