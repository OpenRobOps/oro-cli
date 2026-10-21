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
"""Thin HTTP client for the ORO REST API."""

import logging
from typing import Any

import requests

API_KEY_HEADER = "x-auth-api-key"
AUTH_ERROR_PREFIX = "AUTHENTICATION_ERROR"


class OroError(Exception):
    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


class OroAuthError(OroError):
    pass


class Oro:
    def __init__(self, url: str, api_key: str, logger: logging.Logger | None = None) -> None:
        self.url = url.rstrip("/")
        self.session = requests.Session()
        self.session.headers[API_KEY_HEADER] = api_key
        self.logger = logger or logging.getLogger(__name__)

    def _request(
        self, method: str, path: str, params: dict | None = None, data: Any = None
    ) -> requests.Response:
        url = f"{self.url}/{path.lstrip('/')}"
        self.logger.debug("%s %s params=%s body=%s", method, url, params, data)
        response = self.session.request(method, url, params=params, json=data)
        self.logger.debug("Response %s: %s", response.status_code, response.text)
        if 200 <= response.status_code < 300:
            return response
        try:
            body = response.json()
        except ValueError:
            body = response.text
        message = body.get("error") if isinstance(body, dict) else body
        if not isinstance(message, str):
            message = response.text
        if response.status_code in (401, 403) and message.startswith(AUTH_ERROR_PREFIX):
            raise OroAuthError(message, response.status_code)
        raise OroError(f"({response.status_code}) {message}", response.status_code)

    def http_get(self, path: str, params: dict | None = None) -> requests.Response:
        return self._request("GET", path, params=params)

    def http_post(self, path: str, data: dict | None = None) -> requests.Response:
        return self._request("POST", path, data=data)
