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

import json

from tests.conftest import run

URL = "https://oro.example.com/api"
ITEMS = [
    {
        "kind": "ActionDefinition",
        "apiVersion": "v0.1",
        "metadata": {"id": "a", "scope": ""},
        "spec": {"label": "A"},
    }
]


def test_get_config_short_strips_scope(ctx, requests_mock):
    requests_mock.get(
        f"{URL}/configuration/list",
        json={"items": [{"id": "a", "kind": "ActionDefinition", "label": "A", "scope": ""}]},
    )
    r = run("get", "config", "--kind", "ActionDefinition")
    assert r.exit_code == 0, r.output
    assert "scope" not in r.output and "ActionDefinition" in r.output
    assert requests_mock.last_request.qs == {"kind": ["actiondefinition"], "format": ["short"]}


def test_get_config_yaml_full_strips_metadata_scope(ctx, requests_mock):
    requests_mock.get(f"{URL}/configuration/list", json={"items": ITEMS})
    r = run("get", "config", "--kind", "ActionDefinition", "a", "--yaml")
    assert r.exit_code == 0, r.output
    assert "scope" not in r.output and "label: A" in r.output
    assert requests_mock.last_request.qs == {
        "kind": ["actiondefinition"],
        "format": ["full"],
        "id": ["a"],
    }


def test_get_config_json_all(ctx, requests_mock):
    requests_mock.get(f"{URL}/configuration/list", json={"items": ITEMS})
    r = run("get", "config", "--kind", "ActionDefinition", "--json", "--all")
    assert r.exit_code == 0, r.output
    assert requests_mock.last_request.qs["all"] == ["true"]
    expected = [{**ITEMS[0], "metadata": {"id": "a"}}]
    assert json.loads(r.output) == expected


def test_get_config_flags_exclusive(ctx):
    r = run("get", "config", "--kind", "X", "--json", "--yaml")
    assert r.exit_code == 2 and "Only one of --json, --yaml and --summary" in r.stderr


def test_get_config_role_401(ctx, requests_mock):
    requests_mock.get(f"{URL}/configuration/list", status_code=401, json="User not authorized")
    r = run("get", "config", "--kind", "ActionDefinition")
    assert r.exit_code == 1 and "Unauthorized for kind ActionDefinition" in r.stderr


def test_list_kinds_sorted(ctx, requests_mock):
    requests_mock.get(f"{URL}/configuration/kinds", json={"items": ["Test", "ActionDefinition"]})
    r = run("list", "kinds")
    assert r.exit_code == 0
    assert r.output.index("ActionDefinition") < r.output.index("Test")


ROBOTS = [
    {
        "id": "r1",
        "name": "gont",
        "agentVersion": "1.0",
        "agentOnline": False,
        "updatedTs": 1588596807808,
    }
]


def test_get_robots(ctx, requests_mock):
    requests_mock.get(f"{URL}/robots", json=ROBOTS)
    r = run("get", "robots")
    assert r.exit_code == 0, r.output
    assert all(s in r.output for s in ("gont", "r1", "1.0"))
    assert "online" not in r.output


def test_describe_robots(ctx, requests_mock):
    requests_mock.get(f"{URL}/robots", json=ROBOTS)
    r = run("describe", "robots")
    assert r.exit_code == 0, r.output
    assert "False" in r.output and "2020-05-04" in r.output


def test_wrong_credentials_any_command(ctx, requests_mock):
    requests_mock.get(
        f"{URL}/robots", status_code=403, json={"error": "AUTHENTICATION_ERROR: wrong credentials"}
    )
    r = run("get", "robots")
    assert r.exit_code == 1
    assert "AUTHENTICATION_ERROR: wrong credentials" in r.stderr
    assert "Traceback" not in r.output
