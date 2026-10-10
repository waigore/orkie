"""GitHub pull-list and detail mergeable_state coverage."""

from __future__ import annotations

import json

import pytest

from orkie.connectors.github import GitHubConnector, pull_detail_url, repo_url
from orkie.connectors.types import OwnerRepo


def test_list_pulls_fetches_detail_when_unknown(monkeypatch: pytest.MonkeyPatch) -> None:
    list_payload = [
        {
            "number": 3,
            "title": "t",
            "html_url": "u",
            "draft": False,
            "head": {"ref": "h"},
            "base": {"ref": "main"},
            "mergeable_state": None,
        }
    ]
    detail_payload = {
        "number": 3,
        "title": "t",
        "html_url": "u",
        "draft": False,
        "head": {"ref": "h"},
        "base": {"ref": "main"},
        "mergeable_state": "dirty",
    }
    calls: list[str] = []

    class Resp:
        def __init__(self, payload: object) -> None:
            self._payload = payload

        def __enter__(self) -> Resp:
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def read(self) -> bytes:
            return json.dumps(self._payload).encode()

        @property
        def headers(self) -> dict[str, str]:
            return {}

    def urlopen(req: object) -> Resp:
        url = req.full_url  # type: ignore[attr-defined]
        calls.append(url)
        if "/pulls/3" in url:
            return Resp(detail_payload)
        return Resp(list_payload)

    monkeypatch.setattr("orkie.connectors.github.urllib.request.urlopen", urlopen)
    client = GitHubConnector("tok", OwnerRepo("o", "r"))
    pulls = client.list_open_pull_requests()
    assert pulls[0].mergeable_state == "dirty"
    assert any("/pulls/3" in url for url in calls)


def test_url_helpers() -> None:
    assert repo_url("o", "r").endswith("/repos/o/r")
    assert "/pulls/9" in pull_detail_url("o", "r", 9)
