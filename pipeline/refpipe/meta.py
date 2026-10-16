import re
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from refpipe.errors import MetaError

LICENSE_RE = re.compile(r"PD|own|CC0( 1\.0)?|CC BY \d\.\d|CC BY-SA \d\.\d|CC BY-NC \d\.\d")
ALLOWED_LICENSES = "PD, own, CC0, CC BY x.y, CC BY-SA x.y, CC BY-NC x.y"
VOICE_RANGES = {"male": (45, 69), "female": (53, 77)}


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Work(Strict):
    title: str
    author: str
    license: str
    source: str | None = None
    license_url: str | None = None
    screenshot: str | None = None
    author_died: int | None = None
    wartime: bool = False
    folk: bool = False

    @model_validator(mode="after")
    def check_license(self) -> "Work":
        if not LICENSE_RE.fullmatch(self.license):
            raise ValueError(f"license {self.license!r} is not allowed, use {ALLOWED_LICENSES}")
        if self.license.startswith("CC") and self.source and not (self.license_url and self.screenshot):
            raise ValueError("third-party CC work needs license_url and screenshot")
        return self


def pd_ok(work: Work, year: int) -> bool:
    if work.folk:
        return True
    if work.author_died is None:
        return False
    return year >= work.author_died + 71 + (4 if work.wartime else 0)


class License(Strict):
    music: Work
    recording: Work
    attribution: str
    changes: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def check_pd(self) -> "License":
        year = datetime.now(UTC).year
        for name, work in (("music", self.music), ("recording", self.recording)):
            if work.license == "PD" and not pd_ok(work, year):
                raise ValueError(f"{name}: PD needs folk: true or author_died more than 70 years ago")
        return self


class Vocalist(Strict):
    name: str
    consent: bool
    consent_date: date | None = None

    @model_validator(mode="after")
    def check_consent(self) -> "Vocalist":
        if not self.consent:
            raise ValueError(f"vocalist {self.name!r} has no written consent")
        return self


class Source(Strict):
    origin: Literal["own_midi", "ultrasinger", "manual"]
    generator: str | None = None
    t0_ms: int = 0


class Meta(Strict):
    title: str
    artist: str
    language: str = "ru"
    voice: Literal["male", "female"]
    source: Source
    license: License
    vocalists: list[Vocalist] = Field(default_factory=list)


def _read_yaml(path: Path) -> object:
    try:
        return yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError, yaml.YAMLError) as exc:
        raise MetaError(f"{path}: {exc}") from exc


def load_meta(path: Path) -> Meta:
    data = _read_yaml(path)
    try:
        return Meta.model_validate(data)
    except ValidationError as exc:
        raise MetaError(f"{path}: {exc}") from exc


def dump_meta(meta: Meta, path: Path) -> None:
    data = meta.model_dump(mode="json", exclude_none=True)
    Path(path).write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")


def set_t0_ms(path: Path, t0_ms: int) -> None:
    data = _read_yaml(path)
    if not isinstance(data, dict):
        raise MetaError(f"{path}: root must be a mapping")
    source = data.setdefault("source", {})
    if not isinstance(source, dict):
        raise MetaError(f"{path}: source must be a mapping")
    source["t0_ms"] = int(t0_ms)
    Path(path).write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
