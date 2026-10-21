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

import os
import stat

import pytest
import yaml

from oro_cli import config

SAMPLE = {
    "current": "myinstance",
    "contexts": {
        "myinstance": {"url": "https://oro.example.com/api", "api_key": "oro_xxx"},
        "local": {"url": "http://localhost:3000/api/", "api_key": "oro_yyy", "verbose": True},
    },
}


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(data if isinstance(data, str) else yaml.safe_dump(data))


def test_config_path_honors_xdg(isolated_config):
    assert config.config_path() == isolated_config


def test_load_missing_file(isolated_config):
    assert config.load() == {"current": None, "contexts": {}}


def test_save_sets_mode_0600_and_round_trips(isolated_config):
    config.save(SAMPLE)
    assert stat.S_IMODE(os.stat(isolated_config).st_mode) == 0o600
    data = config.load()
    assert data["contexts"]["local"]["verbose"] is True
    assert data["contexts"]["myinstance"]["verbose"] is False


@pytest.mark.parametrize(
    "content",
    [
        "current: [unclosed",
        "contexts: []",
        "contexts: {a: {url: x}}",
        "contexts: {a: {api_key: k}}",
        "contexts: {a: {url: x, api_key: ''}}",
        "contexts: null",
    ],
)
def test_load_rejects_bad_shape(isolated_config, content):
    write(isolated_config, content)
    with pytest.raises(config.ConfigError, match=f"^Cannot parse {isolated_config}: "):
        config.load()


def test_resolve_uses_current_and_strips_trailing_slash(isolated_config):
    write(isolated_config, {**SAMPLE, "current": "local"})
    assert config.resolve() == config.Settings(
        name="local", url="http://localhost:3000/api", api_key="oro_yyy", verbose=True
    )


def test_resolve_env_context_overrides_current(isolated_config, monkeypatch):
    write(isolated_config, SAMPLE)
    monkeypatch.setenv("ORO_CONTEXT", "local")
    assert config.resolve().name == "local"


def test_resolve_env_url_and_key_need_no_file(isolated_config, monkeypatch):
    monkeypatch.setenv("ORO_URL", "https://oro.example.com/api/")
    monkeypatch.setenv("ORO_API_KEY", "oro_env")
    assert config.resolve() == config.Settings(
        name=None, url="https://oro.example.com/api", api_key="oro_env", verbose=False
    )


def test_resolve_env_key_overrides_file_key(isolated_config, monkeypatch):
    write(isolated_config, SAMPLE)
    monkeypatch.setenv("ORO_API_KEY", "oro_env")
    s = config.resolve()
    assert (s.name, s.api_key) == ("myinstance", "oro_env")


@pytest.mark.parametrize(
    "value,expected",
    [("1", True), ("true", True), ("YES", True), ("false", False), ("0", False), ("", False)],
)
def test_resolve_env_verbose(isolated_config, monkeypatch, value, expected):
    write(isolated_config, SAMPLE)
    monkeypatch.setenv("ORO_VERBOSE", value)
    assert config.resolve().verbose is expected


def test_resolve_no_file(isolated_config):
    with pytest.raises(
        config.ConfigError,
        match=(
            "^No ORO configuration found. Run `oro context add <name> --url <url> "
            "--api-key <key>` to create one.$"
        ),
    ):
        config.resolve()


def test_resolve_unknown_context(isolated_config):
    write(isolated_config, {**SAMPLE, "current": "nope"})
    with pytest.raises(
        config.ConfigError, match="^Unknown context nope. Available: local, myinstance$"
    ):
        config.resolve()


def test_resolve_no_current(isolated_config):
    write(isolated_config, {"contexts": SAMPLE["contexts"]})
    with pytest.raises(config.ConfigError, match="^No current context. Run `oro use <name>`.$"):
        config.resolve()


def test_save_never_exposes_file_more_than_0600(isolated_config, monkeypatch):
    old = os.umask(0o000)
    try:
        config.save(SAMPLE)
    finally:
        os.umask(old)
    assert stat.S_IMODE(os.stat(isolated_config).st_mode) == 0o600
    assert [p.name for p in isolated_config.parent.iterdir()] == ["config.yaml"]
