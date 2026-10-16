from pathlib import Path

import pytest
import yaml

from refpipe.cli import main
from refpipe.errors import MetaError
from refpipe.meta import Work, load_meta, pd_ok, set_t0_ms

REPO = Path(__file__).resolve().parents[2]

CC_WORK = {
    "title": "Night Song",
    "author": "Example Artist",
    "license": "CC BY-SA 4.0",
    "source": "https://example.org/night-song",
    "license_url": "https://creativecommons.org/licenses/by-sa/4.0/",
    "screenshot": "license.png",
}


def write_meta(tmp_path: Path, data: dict) -> Path:
    path = tmp_path / "meta.yaml"
    path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return path


@pytest.fixture
def demo_data(demo_meta_text) -> dict:
    return yaml.safe_load(demo_meta_text)


def test_demo_meta_loads(tmp_path, demo_data):
    meta = load_meta(write_meta(tmp_path, demo_data))
    assert meta.voice == "female"
    assert meta.source.origin == "manual"
    assert meta.source.t0_ms == 0
    assert meta.license.music.license == "own"


def test_example_meta_is_valid():
    meta = load_meta(REPO / "pipeline" / "examples" / "meta.example.yaml")
    assert meta.title == "Калинка"
    assert meta.license.music.license == "PD"
    assert meta.vocalists[0].consent is True


def test_cc_import_meta_is_valid(tmp_path, demo_data):
    demo_data["source"] = {"origin": "ultrasinger", "generator": "UltraSinger", "t0_ms": 61200}
    demo_data["license"]["music"] = dict(CC_WORK)
    demo_data["license"]["recording"] = dict(CC_WORK)
    assert load_meta(write_meta(tmp_path, demo_data)).license.recording.license == "CC BY-SA 4.0"


@pytest.mark.parametrize(
    "license", ["CC BY", "CC BY-SA", "CC BY-NC", "CC BY-ND 4.0", "CC BY-NC-SA 4.0", "All rights reserved"]
)
def test_rejects_forbidden_licenses(tmp_path, demo_data, license):
    demo_data["license"]["recording"]["license"] = license
    with pytest.raises(MetaError, match="not allowed"):
        load_meta(write_meta(tmp_path, demo_data))


def test_third_party_cc_needs_screenshot(tmp_path, demo_data):
    work = dict(CC_WORK)
    del work["screenshot"]
    demo_data["license"]["recording"] = work
    with pytest.raises(MetaError, match="screenshot"):
        load_meta(write_meta(tmp_path, demo_data))


def test_third_party_cc_nc_loads(tmp_path, demo_data):
    demo_data["license"]["recording"] = {**CC_WORK, "license": "CC BY-NC 4.0"}
    assert load_meta(write_meta(tmp_path, demo_data)).license.recording.license == "CC BY-NC 4.0"


def test_pd_needs_long_dead_author(tmp_path, demo_data):
    demo_data["license"]["music"].update({"license": "PD", "author_died": 1990})
    with pytest.raises(MetaError, match="PD"):
        load_meta(write_meta(tmp_path, demo_data))


def test_pd_with_trailing_newline_is_rejected(tmp_path, demo_data):
    demo_data["license"]["music"].update({"license": "PD\n", "author_died": 1990})
    with pytest.raises(MetaError, match="not allowed"):
        load_meta(write_meta(tmp_path, demo_data))


def test_pd_rule():
    work = Work(title="t", author="a", license="PD", author_died=1950)
    assert pd_ok(work, 2021)
    assert not pd_ok(work, 2020)
    wartime = Work(title="t", author="a", license="PD", author_died=1950, wartime=True)
    assert not pd_ok(wartime, 2024)
    assert pd_ok(wartime, 2025)
    assert pd_ok(Work(title="t", author="нар.", license="PD", folk=True), 2026)


def test_vocalist_needs_consent(tmp_path, demo_data):
    demo_data["vocalists"] = [{"name": "Анна", "consent": False}]
    with pytest.raises(MetaError, match="consent"):
        load_meta(write_meta(tmp_path, demo_data))


def test_unknown_key_rejected(tmp_path, demo_data):
    demo_data["licence"] = "typo"
    with pytest.raises(MetaError, match="licence"):
        load_meta(write_meta(tmp_path, demo_data))


def test_voice_required(tmp_path, demo_data):
    del demo_data["voice"]
    with pytest.raises(MetaError, match="voice"):
        load_meta(write_meta(tmp_path, demo_data))


def test_dump_and_set_t0(tmp_path, demo_data):
    meta = load_meta(write_meta(tmp_path, demo_data))
    out = tmp_path / "copy.yaml"
    out.write_text(yaml.safe_dump(demo_data, allow_unicode=True, sort_keys=False), encoding="utf-8")
    assert load_meta(out) == meta
    set_t0_ms(out, 61200)
    assert load_meta(out).source.t0_ms == 61200
    assert "Демо-гамма" in out.read_text(encoding="utf-8")


def test_set_t0_keeps_comments_and_long_lines(tmp_path):
    attribution = "«Калинка», муз. и сл. И. Ларионова (PD); " + "аранжировка и запись huap team " * 3
    assert len(attribution) >= 120
    text = (REPO / "pipeline" / "examples" / "meta.example.yaml").read_text(encoding="utf-8")
    text = text.replace("  t0_ms: 0\n", "  t0_ms: 0  # секунда начала фрагмента\n")
    text = "# мета песни, правится руками\n" + text
    text = text.replace(
        "  attribution: «Калинка», муз. и сл. И. Ларионова (PD); аранжировка и запись huap team, CC BY 4.0\n",
        f"  attribution: {attribution}\n",
    )
    path = tmp_path / "meta.yaml"
    path.write_text(text, encoding="utf-8")
    set_t0_ms(path, 61200)
    after = path.read_text(encoding="utf-8")
    assert after == text.replace("t0_ms: 0  #", "t0_ms: 61200  #")
    assert "# мета песни, правится руками" in after
    assert f"  attribution: {attribution}\n" in after
    meta = load_meta(path)
    assert meta.source.t0_ms == 61200
    assert meta.license.attribution == attribution.strip()


def test_set_t0_without_t0_line_keeps_long_lines(tmp_path, demo_data):
    attribution = " ".join(["huap team"] * 15)
    demo_data["license"]["attribution"] = attribution
    path = write_meta(tmp_path, demo_data)
    set_t0_ms(path, 3000)
    meta = load_meta(path)
    assert meta.source.t0_ms == 3000
    assert meta.license.attribution == attribution
    assert f"  attribution: {attribution}\n" in path.read_text(encoding="utf-8")


def test_missing_file_is_meta_error(tmp_path):
    with pytest.raises(MetaError, match="missing.yaml"):
        load_meta(tmp_path / "missing.yaml")


def test_non_utf8_file_is_meta_error(tmp_path):
    path = tmp_path / "meta.yaml"
    path.write_bytes(b"title: \xff\xfe\n")
    with pytest.raises(MetaError, match="meta.yaml"):
        load_meta(path)


@pytest.mark.parametrize("content", ["", "- 1\n"])
def test_set_t0_rejects_non_mapping_root(tmp_path, content):
    path = tmp_path / "meta.yaml"
    path.write_text(content, encoding="utf-8")
    with pytest.raises(MetaError, match="mapping"):
        set_t0_ms(path, 61200)


@pytest.mark.parametrize("source", ["source:\n", "source: manual\n"])
def test_set_t0_rejects_non_mapping_source(tmp_path, source):
    path = tmp_path / "meta.yaml"
    path.write_text(f"title: x\n{source}", encoding="utf-8")
    with pytest.raises(MetaError, match="source"):
        set_t0_ms(path, 61200)


def test_impossible_timestamp_is_meta_error(demo_dir, demo_meta_text, capsys):
    bad = demo_meta_text.replace(
        "vocalists: []", "vocalists:\n  - name: Анна\n    consent: true\n    consent_date: 2026-13-45"
    )
    (demo_dir / "meta.yaml").write_text(bad, encoding="utf-8")
    with pytest.raises(MetaError, match="meta.yaml"):
        load_meta(demo_dir / "meta.yaml")
    assert main(["compile", str(demo_dir), "--duration", "12"]) == 2
    err = capsys.readouterr().err
    assert err.startswith("refpipe: ")
    assert "meta.yaml" in err
