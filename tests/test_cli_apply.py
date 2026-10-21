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
from pathlib import Path

import yaml

from tests.conftest import run

URL = "https://oro.example.com/api"
DATA = Path(__file__).parent / "data"
ACTION = DATA / "action.yaml"
LOCAL = yaml.safe_load(ACTION.read_text())


def server_copy(**spec):
    obj = {**LOCAL, "metadata": {"id": "wave", "scope": ""}, "spec": {**LOCAL["spec"], **spec}}
    return obj


def test_apply_strips_scope_warns_and_posts(ctx, requests_mock):
    requests_mock.get(f"{URL}/configuration/list", json={"items": []})
    requests_mock.post(
        f"{URL}/configuration/apply",
        json={"operationStatus": "SUCCESS", "messages": [{"level": "WARN", "message": "careful"}]},
    )
    r = run("apply", "-f", ACTION, "-y")
    assert r.exit_code == 0, r.output
    assert "warning: ignoring metadata.scope in ActionDefinition/wave" in r.stderr
    assert "scope" not in requests_mock.last_request.json()["metadata"]
    assert "careful" in r.output and "applied successfully" in r.output


def test_apply_compare_shows_diff_and_does_not_post(ctx, requests_mock):
    requests_mock.get(f"{URL}/configuration/list", json={"items": [server_copy(label="Old")]})
    r = run("apply", "-f", ACTION, "--compare")
    assert r.exit_code == 0, r.output
    assert "Showing diff for ActionDefinition: wave" in r.output
    assert "+ " in r.output and "label: Wave" in r.output
    assert requests_mock.call_count == 1


def test_apply_no_diff(ctx, requests_mock):
    requests_mock.get(f"{URL}/configuration/list", json={"items": [server_copy()]})
    r = run("apply", "-f", ACTION, "--compare")
    assert r.exit_code == 0, r.output
    assert "No diffs detected." in r.output


def test_apply_prompt_declined_does_not_post(ctx, requests_mock):
    requests_mock.get(f"{URL}/configuration/list", json={"items": []})
    requests_mock.post(f"{URL}/configuration/apply", json={"operationStatus": "SUCCESS"})
    r = run("apply", "-f", ACTION, input="n\n")
    assert r.exit_code == 0, r.output
    assert requests_mock.call_count == 1


def test_apply_all_reports_missing_and_skips_unauthorized(ctx, requests_mock):
    requests_mock.get(f"{URL}/configuration/kinds", json={"items": ["ActionDefinition", "Test"]})

    def list_cb(request, context):
        if request.qs["kind"] == ["test"]:
            context.status_code = 401
            return "User not authorized"
        other = {**server_copy(), "metadata": {"id": "other", "scope": ""}}
        return {"items": [server_copy(), other]}

    requests_mock.get(f"{URL}/configuration/list", json=list_cb)
    r = run("apply", "-f", ACTION, "--compare", "--all")
    assert r.exit_code == 0, r.output
    assert "warning: unauthorized for kind Test, skipping" in r.stderr
    assert "Missing ActionDefinition config: other" in r.output


def test_apply_exclude_requires_all(ctx):
    r = run("apply", "-f", ACTION, "--exclude", "Test")
    assert r.exit_code == 2 and "--exclude requires --all" in r.stderr


def test_apply_empty_doc_and_json_list(ctx, requests_mock, tmp_path):
    requests_mock.get(f"{URL}/configuration/list", json={"items": []})
    requests_mock.post(f"{URL}/configuration/apply", json={"operationStatus": "SUCCESS"})
    empty = tmp_path / "empty.yaml"
    empty.write_text("---\n---\n")
    r = run("apply", "-f", empty, "-y")
    assert r.exit_code == 0, r.output
    assert requests_mock.call_count == 0
    as_list = tmp_path / "list.json"
    as_list.write_text(
        json.dumps([{"kind": "Test", "apiVersion": "v0.1", "metadata": {"id": "t"}}])
    )
    r = run("apply", "-f", as_list, "-y")
    assert r.exit_code == 0, r.output
    assert [req.method for req in requests_mock.request_history] == ["GET", "POST"]


def test_apply_directory(ctx, requests_mock, tmp_path):
    requests_mock.get(f"{URL}/configuration/list", json={"items": []})
    requests_mock.post(f"{URL}/configuration/apply", json={"operationStatus": "SUCCESS"})
    (tmp_path / "sub").mkdir()
    (tmp_path / "a.yaml").write_text(ACTION.read_text())
    (tmp_path / "sub" / "b.yml").write_text(ACTION.read_text().replace("id: wave", "id: nod"))
    r = run("apply", "-f", tmp_path, "-y")
    assert r.exit_code == 0, r.output
    assert len([q for q in requests_mock.request_history if q.method == "POST"]) == 2


def test_apply_fills_missing_api_version(ctx, requests_mock, tmp_path):
    requests_mock.get(f"{URL}/configuration/list", json={"items": []})
    requests_mock.post(f"{URL}/configuration/apply", json={"operationStatus": "SUCCESS"})
    f = tmp_path / "noversion.yaml"
    f.write_text("kind: Test\nmetadata:\n  id: t\n")
    r = run("apply", "-f", f, "-y")
    assert r.exit_code == 0, r.output
    assert requests_mock.last_request.json()["apiVersion"] == "v0.1"
