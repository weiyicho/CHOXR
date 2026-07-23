from __future__ import annotations

from typing import Any


class RecordingRestClient:
    def __init__(self, responses: list[Any] | None = None):
        self.calls: list[dict[str, Any]] = []
        self.responses = list(responses or [])

    def request(self, method: str, path: str, params=None, **kwargs):
        self.calls.append(
            {"method": method, "path": path, "params": params or {}, **kwargs}
        )
        return self.responses.pop(0) if self.responses else {}


class FakeResponse:
    def __init__(self, status_code: int, payload: Any, headers=None, text=""):
        self.status_code = status_code
        self._payload = payload
        self.headers = headers or {}
        self.text = text

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self, results):
        self.results = list(results)
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append({"method": method, "url": url, **kwargs})
        result = self.results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result
