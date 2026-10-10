"""GitHub connector helpers with patched urlopen."""

from __future__ import annotations

import io
import json
from urllib.error import HTTPError

import pytest

from orkie.connectors.github import (
    GitHubConnector,
    issues_list_url,
    parse_issue,
    parse_pull_request,
    pulls_list_url,
)
from orkie.connectors.types import AuthError, OwnerRepo, Privilege, RateLimitError


def test_url_builders() -> None:
    assert "state=open" in issues_list_url("o", "r")
    assert "per_page=100" in pulls_list_url("o", "r")


def test_parse_issue_skips_none_body() -> None:
    issue = parse_issue(
        {
            "number": 1,
            "title": "t",
            "body": None,
            "html_url": "u",
            "state": "open",
            "labels": [{"name": "orkie"}],
        }
    )
    assert issue.body == ""
    assert issue.labels == ["orkie"]


def test_parse_pull_unknown_mergeable() -> None:
    pr = parse_pull_request(
        {
            "number": 2,
            "title": "t",
            "html_url": "u",
            "draft": False,
            "head": {"ref": "h"},
            "base": {"ref": "main"},
            "mergeable_state": None,
        }
    )
    assert pr.mergeable_state == "unknown"


def test_list_open_issues_excludes_prs(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = [
        {"number": 1, "title": "i", "body": "", "html_url": "u", "state": "open", "labels": []},
        {
            "number": 2,
            "title": "pr",
            "body": "",
            "html_url": "u",
            "state": "open",
            "labels": [],
            "pull_request": {},
        },
    ]

    class Resp:
        def __enter__(self) -> Resp:
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def read(self) -> bytes:
            return json.dumps(payload).encode()

        @property
        def headers(self) -> dict[str, str]:
            return {}

    monkeypatch.setattr("orkie.connectors.github.urllib.request.urlopen", lambda req: Resp())
    client = GitHubConnector("tok", OwnerRepo("o", "r"))
    issues = client.list_open_issues()
    assert [i.number for i in issues] == [1]


def test_probe_empty_token_no_http() -> None:
    client = GitHubConnector("", OwnerRepo("o", "r"))
    result = client.probe_privileges({Privilege.TOKEN, Privilege.READ_REPOSITORY})
    assert Privilege.TOKEN in result.missing_required
    assert result.missing_warn_only == set()


def test_probe_auth_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def raise_auth(req: object) -> object:
        raise HTTPError(req.full_url, 401, "no", hdrs=None, fp=io.BytesIO(b"{}"))  # type: ignore[attr-defined]

    monkeypatch.setattr("orkie.connectors.github.urllib.request.urlopen", raise_auth)
    client = GitHubConnector("tok", OwnerRepo("o", "r"))
    result = client.probe_privileges({Privilege.READ_REPOSITORY})
    assert Privilege.READ_REPOSITORY in result.missing_required


def test_rate_limit_maps(monkeypatch: pytest.MonkeyPatch) -> None:
    def raise_rl(req: object) -> object:
        raise HTTPError(
            "https://api.github.com",
            403,
            "no",
            hdrs=None,
            fp=io.BytesIO(b'{"message":"API rate limit exceeded"}'),
        )

    monkeypatch.setattr("orkie.connectors.github.urllib.request.urlopen", raise_rl)
    client = GitHubConnector("tok", OwnerRepo("o", "r"))
    with pytest.raises(RateLimitError):
        client.list_open_issues()


def test_auth_error_on_list(monkeypatch: pytest.MonkeyPatch) -> None:
    def raise_auth(req: object) -> object:
        raise HTTPError(
            "https://api.github.com",
            401,
            "no",
            hdrs=None,
            fp=io.BytesIO(b"{}"),
        )

    monkeypatch.setattr("orkie.connectors.github.urllib.request.urlopen", raise_auth)
    client = GitHubConnector("tok", OwnerRepo("o", "r"))
    with pytest.raises(AuthError):
        client.list_open_issues()
