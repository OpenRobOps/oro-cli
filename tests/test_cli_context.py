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

from oro_cli import config
from tests.conftest import run

URL = "https://oro.example.com/api"


def add(name, url=URL, key="oro_xxx", *extra):
    return run("context", "add", name, "--url", url, "--api-key", key, *extra)


def test_add_first_context_becomes_current(isolated_config):
    r = add("myinstance", URL + "/")
    assert r.exit_code == 0, r.output
    assert "Context myinstance added." in r.output
    assert "Current context: myinstance" in r.output
    assert config.load() == {
        "current": "myinstance",
        "contexts": {"myinstance": {"url": URL, "api_key": "oro_xxx", "verbose": False}},
    }


def test_add_second_does_not_switch_unless_use(isolated_config):
    add("myinstance")
    r = add("local", "http://localhost:3000/api", "oro_yyy")
    assert "Current context" not in r.output
    assert config.load()["current"] == "myinstance"
    r = add("other", "http://localhost:3001/api", "oro_zzz", "--use", "--verbose")
    assert "Current context: other" in r.output
    assert config.load()["current"] == "other"
    assert config.load()["contexts"]["other"]["verbose"] is True


def test_add_existing_replaces(isolated_config):
    add("myinstance")
    r = add("myinstance", URL, "oro_new")
    assert "Context myinstance replaced." in r.output
    assert config.load()["contexts"]["myinstance"]["api_key"] == "oro_new"


def test_use_switches_and_rejects_unknown(isolated_config):
    add("myinstance")
    add("local", "http://localhost:3000/api", "oro_yyy")
    r = run("use", "local")
    assert r.exit_code == 0 and "Current context: local" in r.output
    assert config.load()["current"] == "local"
    r = run("context", "use", "nope")
    assert r.exit_code == 1
    assert "Unknown context nope. Available: local, myinstance" in r.stderr


def test_context_list_marks_current_and_hides_keys(isolated_config):
    add("myinstance")
    add("local", "http://localhost:3000/api", "oro_yyy")
    r = run("context", "list")
    assert r.exit_code == 0
    assert "oro_xxx" not in r.output and "oro_yyy" not in r.output
    current_row = next(line for line in r.output.splitlines() if "myinstance" in line)
    assert current_row.strip().startswith("*")


def test_context_current(isolated_config):
    r = run("context", "current")
    assert r.exit_code == 1 and "No ORO configuration found" in r.stderr
    add("myinstance")
    r = run("context", "current")
    assert r.exit_code == 0 and r.output.strip() == "myinstance"


def test_remove_current_clears_current(isolated_config):
    add("myinstance")
    r = run("context", "remove", "myinstance")
    assert r.exit_code == 0 and "Context myinstance removed." in r.output
    assert config.load() == {"current": None, "contexts": {}}


def test_remove_unknown_fails_and_keeps_file(isolated_config):
    add("myinstance")
    before = isolated_config.read_bytes()
    r = run("context", "remove", "nope")
    assert r.exit_code == 1 and "Unknown context nope." in r.stderr
    assert isolated_config.read_bytes() == before


def test_help_and_version_work_without_config(isolated_config):
    assert run("--help").exit_code == 0
    r = run("--version")
    assert r.exit_code == 0 and "0.1.0" in r.output


def test_whoami_ok(isolated_config, requests_mock):
    add("myinstance")
    requests_mock.get(f"{URL}/test", json={"ok": True, "user": "u1"})
    r = run("whoami")
    assert r.exit_code == 0, r.output
    for line in (
        "Context: myinstance",
        f"URL: {URL}",
        "CLI version: 0.1.0",
        "Authenticated as user u1",
    ):
        assert line in r.output


def test_whoami_bad_key(isolated_config, requests_mock):
    add("myinstance")
    requests_mock.get(
        f"{URL}/test", status_code=403, json={"error": "AUTHENTICATION_ERROR: wrong credentials"}
    )
    r = run("whoami")
    assert r.exit_code == 1
    assert "AUTHENTICATION_ERROR: wrong credentials" in r.stderr
    assert "Traceback" not in r.output


def test_whoami_env_only(isolated_config, monkeypatch, requests_mock):
    monkeypatch.setenv("ORO_URL", URL)
    monkeypatch.setenv("ORO_API_KEY", "oro_env")
    requests_mock.get(f"{URL}/test", json={"ok": True, "user": "u1"})
    r = run("whoami")
    assert r.exit_code == 0 and "Context: (environment)" in r.output
    assert requests_mock.last_request.headers["x-auth-api-key"] == "oro_env"
