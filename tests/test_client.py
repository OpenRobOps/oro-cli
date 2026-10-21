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

import pytest

from oro_cli.client import Oro, OroAuthError, OroError

URL = "https://oro.example.com/api"


def test_get_sends_auth_header_and_params(requests_mock):
    requests_mock.get(f"{URL}/configuration/list", json={"items": []})
    r = Oro(URL, "oro_xxx").http_get("/configuration/list", {"kind": "ActionDefinition"})
    assert r.json() == {"items": []}
    assert requests_mock.last_request.headers["x-auth-api-key"] == "oro_xxx"
    assert requests_mock.last_request.qs == {"kind": ["actiondefinition"]}


def test_post_sends_json_body(requests_mock):
    requests_mock.post(f"{URL}/configuration/apply", json={"operationStatus": "SUCCESS"})
    Oro(URL, "oro_xxx").http_post("configuration/apply", {"kind": "Test"})
    assert requests_mock.last_request.json() == {"kind": "Test"}


@pytest.mark.parametrize("status", [401, 403])
def test_authentication_error(requests_mock, status):
    requests_mock.get(
        f"{URL}/test", status_code=status, json={"error": "AUTHENTICATION_ERROR: wrong credentials"}
    )
    with pytest.raises(OroAuthError, match="^AUTHENTICATION_ERROR: wrong credentials$") as e:
        Oro(URL, "oro_xxx").http_get("test")
    assert e.value.status == status


def test_role_401_is_plain_error(requests_mock):
    requests_mock.get(f"{URL}/configuration/list", status_code=401, json="User not authorized")
    with pytest.raises(OroError, match=r"^\(401\) User not authorized$") as e:
        Oro(URL, "oro_xxx").http_get("configuration/list")
    assert e.value.status == 401


def test_500_text_body(requests_mock):
    requests_mock.get(f"{URL}/robots", status_code=500, text="boom")
    with pytest.raises(OroError, match=r"^\(500\) boom$"):
        Oro(URL, "oro_xxx").http_get("robots")


def test_connection_error_is_oro_error(requests_mock):
    import requests

    requests_mock.get(f"{URL}/robots", exc=requests.ConnectionError("refused"))
    with pytest.raises(OroError, match=rf"^Cannot reach {URL}/robots: refused$"):
        Oro(URL, "oro_xxx").http_get("robots")


def test_non_json_2xx_is_oro_error(requests_mock):
    requests_mock.get(f"{URL}/robots", text="<html>meteor</html>")
    with pytest.raises(OroError, match=r"^Unexpected non-JSON response from .*should end in /api"):
        Oro(URL, "oro_xxx").http_get("robots")


def test_error_body_is_truncated(requests_mock):
    requests_mock.get(f"{URL}/robots", status_code=404, text="x" * 1000)
    with pytest.raises(OroError) as e:
        Oro(URL, "oro_xxx").http_get("robots")
    assert len(str(e.value)) < 300
