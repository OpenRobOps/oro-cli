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

from tests.conftest import run

URL = "https://oro.example.com/api"
EXPECTED = {"kind": "ActionDefinition", "apiVersion": "v0.1", "metadata": {"id": "wave"}}


def test_delete_config_posts_expected_body(ctx, requests_mock):
    requests_mock.post(f"{URL}/configuration/clear", json={"operationStatus": "SUCCESS"})
    r = run("delete", "config", "--kind", "ActionDefinition", "wave")
    assert r.exit_code == 0, r.output
    assert requests_mock.last_request.json() == EXPECTED
    assert "OK" in r.output


def test_delete_file_fills_api_version_and_drops_scope(ctx, requests_mock, tmp_path):
    requests_mock.post(f"{URL}/configuration/clear", json={"operationStatus": "SUCCESS"})
    f = tmp_path / "a.yaml"
    f.write_text("kind: ActionDefinition\nmetadata:\n  id: wave\n  scope: account\nspec: {x: 1}\n")
    r = run("delete", "-f", f)
    assert r.exit_code == 0, r.output
    assert requests_mock.last_request.json() == EXPECTED
    assert "warning: ignoring metadata.scope in ActionDefinition/wave" in r.stderr
    assert "deleted successfully" in r.output


def test_delete_without_args_shows_help(ctx, requests_mock):
    r = run("delete")
    assert r.exit_code == 0 and "Usage" in r.output
    assert requests_mock.call_count == 0


def test_delete_role_401(ctx, requests_mock):
    requests_mock.post(f"{URL}/configuration/clear", status_code=401, json="User not authorized")
    r = run("delete", "config", "--kind", "ActionDefinition", "wave")
    assert r.exit_code == 1 and "(401)" in r.stderr


def test_delete_directory(ctx, requests_mock, tmp_path):
    requests_mock.post(f"{URL}/configuration/clear", json={"operationStatus": "SUCCESS"})
    d = tmp_path / "cfgs"
    d.mkdir()
    (d / "a.yaml").write_text("kind: ActionDefinition\nmetadata:\n  id: a\n")
    (d / "b.yaml").write_text("kind: ActionDefinition\nmetadata:\n  id: b\n")
    r = run("delete", "-f", d)
    assert r.exit_code == 0, r.output
    assert requests_mock.call_count == 2
