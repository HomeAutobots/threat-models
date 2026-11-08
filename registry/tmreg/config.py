"""project.toml and system.toml loading and validation."""
from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

from . import db

DEFAULT_ORIGINS = (
    "design-review", "threat-model", "testing", "vulnerability", "incident", "ad-hoc",
)
METHODS = ("stride-per-element", "linddun")


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class ProjectConfig:
    root: Path
    framework_path: Path
    reviewer_name: str
    reviewer_email: str
    origins: tuple[str, ...]


@dataclass(frozen=True)
class SystemConfig:
    slug: str
    name: str
    owner: str
    methods: tuple[str, ...]
    personal_data_classes: tuple[str, ...]
    legacy_catalog: str | None

    @property
    def effective_methods(self) -> tuple[str, ...]:
        if self.personal_data_classes and "linddun" not in self.methods:
            return self.methods + ("linddun",)
        return self.methods


def _read(path: Path) -> dict:
    try:
        with open(path, "rb") as f:
            return tomllib.load(f)
    except FileNotFoundError:
        raise ConfigError(f"{path} not found") from None
    except tomllib.TOMLDecodeError as e:
        raise ConfigError(f"{path}: invalid TOML: {e}") from None


def _str_list(raw: dict, key: str, default: tuple[str, ...]) -> tuple[str, ...]:
    val = raw.get(key, list(default))
    if (not isinstance(val, list)
            or not all(isinstance(v, str) and v.strip() for v in val)):
        raise ConfigError(f"{key} must be a list of non-empty strings")
    if len(set(val)) != len(val):
        raise ConfigError(f"{key} entries must be unique")
    return tuple(val)


def load_project(root: Path) -> ProjectConfig:
    root = Path(root)
    raw = _read(root / "project.toml")
    name = raw.get("reviewer_name", "")
    if not isinstance(name, str) or not name.strip():
        raise ConfigError("reviewer_name must be a non-empty string")
    fw_raw = raw.get("framework_path")
    if not isinstance(fw_raw, str) or not fw_raw.strip():
        raise ConfigError("framework_path is required")
    fw = (root / fw_raw).resolve()
    if not fw.exists():
        raise ConfigError(f"framework_path {fw} does not exist")
    email = raw.get("reviewer_email", "")
    if not isinstance(email, str):
        raise ConfigError("reviewer_email must be a string")
    return ProjectConfig(root=root, framework_path=fw, reviewer_name=name.strip(),
                         reviewer_email=email, origins=_str_list(raw, "origins", DEFAULT_ORIGINS))


def load_system(root: Path, slug: str) -> SystemConfig:
    db.validate_slug(slug)
    raw = _read(Path(root) / "systems" / slug / "system.toml")
    name = raw.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ConfigError("name is required in system.toml")
    methods = _str_list(raw, "methods", ("stride-per-element",))
    if not methods:
        raise ConfigError(f"methods must name at least one of {', '.join(METHODS)}")
    for m in methods:
        if m not in METHODS:
            raise ConfigError(f"unknown method {m!r}; expected one of {', '.join(METHODS)}")
    legacy = raw.get("legacy_catalog")
    if legacy is not None and not isinstance(legacy, str):
        raise ConfigError("legacy_catalog must be a string")
    owner = raw.get("owner", "")
    if not isinstance(owner, str):
        raise ConfigError("owner must be a string")
    return SystemConfig(slug=slug, name=name.strip(), owner=owner, methods=methods,
                        personal_data_classes=_str_list(raw, "personal_data_classes", ()),
                        legacy_catalog=legacy)
