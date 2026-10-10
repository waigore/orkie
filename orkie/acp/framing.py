"""Pure JSON-RPC encode/decode and permission choice."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class PermissionOption:
    option_id: str
    kind: str
    title: str | None = None


@dataclass(frozen=True, slots=True)
class JsonRpcRequest:
    method: str
    params: dict[str, Any]
    id: int | str | None = None


@dataclass(frozen=True, slots=True)
class JsonRpcResponse:
    id: int | str | None
    result: object | None
    error: object | None


@dataclass(frozen=True, slots=True)
class JsonRpcNotification:
    method: str
    params: dict[str, Any]


class AcpFramingError(Exception):
    """Invalid ACP framing."""


def encode_message(message: dict[str, Any]) -> bytes:
    text = json.dumps(message, separators=(",", ":"), ensure_ascii=False)
    if "\n" in text:
        raise AcpFramingError("JSON-RPC message must not contain newlines")
    return (text + "\n").encode("utf-8")


def decode_line(line: bytes) -> dict[str, Any]:
    try:
        data = json.loads(line.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AcpFramingError("invalid JSON-RPC line") from exc
    if not isinstance(data, dict):
        raise AcpFramingError("JSON-RPC message must be an object")
    return data


def classify_message(
    data: dict[str, Any],
) -> JsonRpcResponse | JsonRpcNotification | JsonRpcRequest:
    if "method" in data and "id" not in data:
        method = data["method"]
        params = data.get("params") or {}
        if not isinstance(method, str) or not isinstance(params, dict):
            raise AcpFramingError("invalid notification")
        return JsonRpcNotification(method=method, params=params)
    if "method" in data and "id" in data:
        method = data["method"]
        params = data.get("params") or {}
        if not isinstance(method, str) or not isinstance(params, dict):
            raise AcpFramingError("invalid request")
        return JsonRpcRequest(method=method, params=params, id=data["id"])
    if "id" in data and ("result" in data or "error" in data):
        return JsonRpcResponse(
            id=data.get("id"),
            result=data.get("result"),
            error=data.get("error"),
        )
    raise AcpFramingError("unrecognized JSON-RPC message")


def build_initialize(request_id: int, *, version: str) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": "initialize",
        "params": {
            "protocolVersion": 2,
            "capabilities": {},
            "info": {"name": "orkie", "title": "Orkie", "version": version},
        },
    }


def build_session_new(request_id: int, *, cwd: str) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": "session/new",
        "params": {"cwd": cwd, "mcpServers": []},
    }


def build_session_prompt(
    request_id: int, *, session_id: str, text: str
) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": "session/prompt",
        "params": {
            "sessionId": session_id,
            "prompt": [{"type": "text", "text": text}],
        },
    }


def build_session_cancel(*, session_id: str) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "method": "session/cancel",
        "params": {"sessionId": session_id},
    }


def build_session_delete(request_id: int, *, session_id: str) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": "session/delete",
        "params": {"sessionId": session_id},
    }


def build_permission_selected(request_id: int | str, option_id: str) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "result": {
            "outcome": {
                "outcome": "selected",
                "optionId": option_id,
            }
        },
    }


def build_permission_cancelled(request_id: int | str) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "result": {"outcome": {"outcome": "cancelled"}},
    }


def parse_permission_options(params: dict[str, Any]) -> list[PermissionOption]:
    options_raw = params.get("options") or []
    if not isinstance(options_raw, list):
        return []
    options: list[PermissionOption] = []
    for item in options_raw:
        if not isinstance(item, dict):
            continue
        option_id = item.get("optionId") or item.get("option_id")
        kind = item.get("kind")
        if not isinstance(option_id, str) or not isinstance(kind, str):
            continue
        title = item.get("title")
        if title is not None and not isinstance(title, str):
            title = None
        options.append(PermissionOption(option_id=option_id, kind=kind, title=title))
    return options


class AcpError(Exception):
    """Handshake, prompt, permission, or process failure."""


def choose_permission_option(options: list[PermissionOption]) -> PermissionOption:
    if not options:
        raise AcpError("permission request has no options")
    for option in options:
        if option.kind == "allow_always":
            return option
    for option in options:
        if option.kind == "allow_once":
            return option
    for option in options:
        if option.kind not in {"reject_once", "reject_always"}:
            return option
    return options[0]
