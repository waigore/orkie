"""GitHub REST v3 client via urllib."""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any
from urllib.request import Request

from orkie.connectors.types import (
    AuthError,
    ConnectorError,
    Issue,
    NotFoundError,
    OwnerRepo,
    Privilege,
    ProbeResult,
    PullRequest,
    RateLimitError,
)

API_BASE = "https://api.github.com"
ACCEPT_HEADER = "application/vnd.github+json"
API_VERSION = "2022-11-28"


def issues_list_url(owner: str, repo: str, *, per_page: int = 100, page: int = 1) -> str:
    query = urllib.parse.urlencode({"state": "open", "per_page": per_page, "page": page})
    return f"{API_BASE}/repos/{owner}/{repo}/issues?{query}"


def pulls_list_url(owner: str, repo: str, *, per_page: int = 100, page: int = 1) -> str:
    query = urllib.parse.urlencode({"state": "open", "per_page": per_page, "page": page})
    return f"{API_BASE}/repos/{owner}/{repo}/pulls?{query}"


def repo_url(owner: str, repo: str) -> str:
    return f"{API_BASE}/repos/{owner}/{repo}"


def pull_detail_url(owner: str, repo: str, number: int) -> str:
    return f"{API_BASE}/repos/{owner}/{repo}/pulls/{number}"


def parse_issue(item: dict[str, Any]) -> Issue:
    labels_raw = item.get("labels") or []
    labels: list[str] = []
    if isinstance(labels_raw, list):
        for label in labels_raw:
            if isinstance(label, dict) and isinstance(label.get("name"), str):
                labels.append(label["name"])
            elif isinstance(label, str):
                labels.append(label)
    body = item.get("body")
    if body is None:
        body = ""
    elif not isinstance(body, str):
        body = str(body)
    return Issue(
        number=int(item["number"]),
        title=str(item.get("title") or ""),
        body=body,
        url=str(item.get("html_url") or ""),
        state=str(item.get("state") or ""),
        labels=labels,
    )


def parse_pull_request(item: dict[str, Any]) -> PullRequest:
    head = item.get("head") or {}
    base = item.get("base") or {}
    head_ref = head.get("ref") if isinstance(head, dict) else ""
    base_ref = base.get("ref") if isinstance(base, dict) else ""
    mergeable = item.get("mergeable_state")
    if mergeable is None or mergeable == "":
        mergeable_state = "unknown"
    else:
        mergeable_state = str(mergeable)
    return PullRequest(
        number=int(item["number"]),
        title=str(item.get("title") or ""),
        url=str(item.get("html_url") or ""),
        head=str(head_ref or ""),
        base=str(base_ref or ""),
        draft=bool(item.get("draft", False)),
        mergeable_state=mergeable_state,
    )


class GitHubConnector:
    def __init__(self, token: str, owner_repo: OwnerRepo) -> None:
        self._token = token
        self._owner_repo = owner_repo

    def repository_id(self) -> OwnerRepo:
        return self._owner_repo

    def list_open_issues(self) -> list[Issue]:
        owner = self._owner_repo.owner
        name = self._owner_repo.name
        issues: list[Issue] = []
        page = 1
        while True:
            url = issues_list_url(owner, name, page=page)
            body, link = self._get(url)
            if not isinstance(body, list):
                raise ConnectorError("unexpected issues list response")
            for item in body:
                if not isinstance(item, dict):
                    continue
                if "pull_request" in item:
                    continue
                issues.append(parse_issue(item))
            if not _has_next_link(link):
                break
            page += 1
        return issues

    def list_open_pull_requests(self) -> list[PullRequest]:
        owner = self._owner_repo.owner
        name = self._owner_repo.name
        pulls: list[PullRequest] = []
        page = 1
        while True:
            url = pulls_list_url(owner, name, page=page)
            body, link = self._get(url)
            if not isinstance(body, list):
                raise ConnectorError("unexpected pulls list response")
            for item in body:
                if not isinstance(item, dict):
                    continue
                pr = parse_pull_request(item)
                if pr.mergeable_state in {"", "unknown"} or item.get("mergeable_state") is None:
                    detail_body, _ = self._get(pull_detail_url(owner, name, pr.number))
                    if isinstance(detail_body, dict):
                        pr = parse_pull_request(detail_body)
                pulls.append(pr)
            if not _has_next_link(link):
                break
            page += 1
        return pulls

    def probe_privileges(self, required: set[Privilege]) -> ProbeResult:
        missing: set[Privilege] = set()
        owner = self._owner_repo.owner
        name = self._owner_repo.name
        if Privilege.TOKEN in required:
            if not self._token:
                missing.add(Privilege.TOKEN)
                return ProbeResult(missing_required=missing, missing_warn_only=set())
        if Privilege.READ_REPOSITORY in required and Privilege.TOKEN not in missing:
            if not self._probe_ok(repo_url(owner, name)):
                missing.add(Privilege.READ_REPOSITORY)
        if Privilege.READ_ISSUES in required and Privilege.TOKEN not in missing:
            url = issues_list_url(owner, name, per_page=1, page=1)
            if not self._probe_ok(url):
                missing.add(Privilege.READ_ISSUES)
        if Privilege.READ_PULL_REQUESTS in required and Privilege.TOKEN not in missing:
            url = pulls_list_url(owner, name, per_page=1, page=1)
            if not self._probe_ok(url):
                missing.add(Privilege.READ_PULL_REQUESTS)
        return ProbeResult(missing_required=missing, missing_warn_only=set())

    def _probe_ok(self, url: str) -> bool:
        try:
            self._get(url)
        except AuthError:
            return False
        except RateLimitError:
            raise
        except ConnectorError:
            return False
        return True

    def _get(self, url: str) -> tuple[object, str | None]:
        request = Request(
            url,
            headers={
                "Authorization": f"Bearer {self._token}",
                "Accept": ACCEPT_HEADER,
                "X-GitHub-Api-Version": API_VERSION,
                "User-Agent": "orkie",
            },
            method="GET",
        )
        try:
            with urllib.request.urlopen(request) as response:
                raw = response.read()
                link = response.headers.get("Link")
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise _map_http_error(exc.code, body) from exc
        except urllib.error.URLError as exc:
            raise ConnectorError(str(exc)) from exc
        try:
            data = json.loads(raw.decode("utf-8")) if raw else None
        except json.JSONDecodeError as exc:
            raise ConnectorError("invalid JSON from GitHub") from exc
        return data, link


def _has_next_link(link: str | None) -> bool:
    if not link:
        return False
    return 'rel="next"' in link


def _map_http_error(code: int, body: str) -> ConnectorError:
    lower = body.lower()
    if "rate limit" in lower or code == 429:
        return RateLimitError("GitHub rate limit exceeded")
    if code in {401, 403}:
        return AuthError(f"GitHub auth failed ({code})")
    if code == 404:
        return NotFoundError("GitHub resource not found")
    return ConnectorError(f"GitHub HTTP {code}")
