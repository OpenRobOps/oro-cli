# Copyright 2026 InOrbit, Inc.
#
#    Licensed under the Apache License, Version 2.0 (the "License");
#    you may not use this file except in compliance with the License.
#    You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS,
#    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#    See the License for the specific language governing permissions and
#    limitations under the License.
"""Contexts file (~/.config/oro/config.yaml) and environment overrides."""

import os
from dataclasses import dataclass
from pathlib import Path

import yaml

ENV_URL = "ORO_URL"
ENV_API_KEY = "ORO_API_KEY"
ENV_VERBOSE = "ORO_VERBOSE"
ENV_CONTEXT = "ORO_CONTEXT"
TRUE_VALUES = {"1", "true", "yes"}

NO_CONFIG_MSG = (
    "No ORO configuration found. Run `oro context add <name> --url <url> --api-key <key>` "
    "to create one."
)
NO_CURRENT_MSG = "No current context. Run `oro use <name>`."


class ConfigError(Exception):
    pass


@dataclass(frozen=True)
class Settings:
    name: str | None
    url: str
    api_key: str
    verbose: bool


def config_path() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config"
    return Path(base) / "oro" / "config.yaml"


def _env(name: str) -> str | None:
    """Environment variable value, with empty strings counting as unset."""
    value = os.environ.get(name, "").strip()
    return value or None


def _validate_context(name: str, context: object) -> dict:
    if not isinstance(context, dict):
        raise ValueError(f"context {name!r} is not a mapping")
    for field in ("url", "api_key"):
        if not isinstance(context.get(field), str) or not context[field]:
            raise ValueError(f"context {name!r} is missing {field}")
    return {
        "url": context["url"],
        "api_key": context["api_key"],
        "verbose": bool(context.get("verbose", False)),
    }


def load() -> dict:
    """Returns {"current": name | None, "contexts": {name: {url, api_key, verbose}}}."""
    path = config_path()
    if not path.exists():
        return {"current": None, "contexts": {}}
    try:
        data = yaml.safe_load(path.read_text())
        if data is None:
            data = {}
        if not isinstance(data, dict):
            raise ValueError("top level is not a mapping")
        contexts = data.get("contexts", {})
        if not isinstance(contexts, dict):
            raise ValueError("'contexts' is not a mapping")
        current = data.get("current")
        if current is not None and not isinstance(current, str):
            raise ValueError("'current' is not a string")
        return {
            "current": current,
            "contexts": {name: _validate_context(name, ctx) for name, ctx in contexts.items()},
        }
    except (yaml.YAMLError, ValueError) as e:
        raise ConfigError(f"Cannot parse {path}: {e}") from e


def save(data: dict) -> None:
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, sort_keys=False))
    path.chmod(0o600)


def resolve() -> Settings:
    """Settings for the current context, with ORO_* environment variables taking precedence."""
    env_url, env_key, env_verbose = _env(ENV_URL), _env(ENV_API_KEY), _env(ENV_VERBOSE)
    verbose_override = None if env_verbose is None else env_verbose.lower() in TRUE_VALUES
    if env_url and env_key:
        return Settings(
            name=None, url=env_url.rstrip("/"), api_key=env_key, verbose=bool(verbose_override)
        )
    data = load()
    if not data["contexts"]:
        raise ConfigError(NO_CONFIG_MSG)
    name = _env(ENV_CONTEXT) or data["current"]
    if not name:
        raise ConfigError(NO_CURRENT_MSG)
    if name not in data["contexts"]:
        available = ", ".join(sorted(data["contexts"]))
        raise ConfigError(f"Unknown context {name}. Available: {available}")
    context = data["contexts"][name]
    return Settings(
        name=name,
        url=(env_url or context["url"]).rstrip("/"),
        api_key=env_key or context["api_key"],
        verbose=context["verbose"] if verbose_override is None else verbose_override,
    )
