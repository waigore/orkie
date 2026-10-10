"""Additional ACP framing coverage."""

from __future__ import annotations

import pytest

from orkie.acp.framing import (
    JsonRpcNotification,
    JsonRpcRequest,
    JsonRpcResponse,
    build_permission_cancelled,
    build_permission_selected,
    build_session_cancel,
    build_session_delete,
    build_session_new,
    build_session_prompt,
    classify_message,
    decode_line,
    encode_message,
    parse_permission_options,
)


def test_build_helpers() -> None:
    assert build_session_new(2, cwd="/tmp").method if False else build_session_new(2, cwd="/tmp")["method"] == "session/new"
    assert build_session_prompt(3, session_id="s", text="hi")["method"] == "session/prompt"
    assert build_session_cancel(session_id="s")["method"] == "session/cancel"
    assert build_session_delete(4, session_id="s")["method"] == "session/delete"
    assert build_permission_selected(1, "opt")["result"]["outcome"]["optionId"] == "opt"
    assert build_permission_cancelled(1)["result"]["outcome"]["outcome"] == "cancelled"


def test_classify_messages() -> None:
    assert isinstance(
        classify_message({"jsonrpc": "2.0", "method": "session/cancel", "params": {}}),
        JsonRpcNotification,
    )
    assert isinstance(
        classify_message(
            {"jsonrpc": "2.0", "id": 1, "method": "session/request_permission", "params": {}}
        ),
        JsonRpcRequest,
    )
    assert isinstance(
        classify_message({"jsonrpc": "2.0", "id": 1, "result": {}}),
        JsonRpcResponse,
    )


def test_parse_permission_options() -> None:
    options = parse_permission_options(
        {
            "options": [
                {"optionId": "a", "kind": "allow_once", "title": "Allow"},
                {"bad": True},
            ]
        }
    )
    assert len(options) == 1
    assert options[0].title == "Allow"


def test_encode_rejects_newline(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "orkie.acp.framing.json.dumps",
        lambda *_a, **_k: '{"text":"a\\nb"}'.replace("\\n", "\n"),
    )
    with pytest.raises(Exception):
        encode_message({"text": "x"})


def test_decode_invalid() -> None:
    with pytest.raises(Exception):
        decode_line(b"not-json")
