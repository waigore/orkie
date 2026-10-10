"""ACP framing and permission choice tests."""

from __future__ import annotations

import pytest

from orkie.acp.framing import (
    AcpError,
    PermissionOption,
    build_authenticate,
    build_initialize,
    choose_permission_option,
    decode_line,
    encode_message,
    first_auth_method_id,
)


def test_encode_decode_round_trip() -> None:
    payload = build_initialize(1, version="0.1.0")
    line = encode_message(payload)
    assert line.endswith(b"\n")
    assert b"\n" not in line[:-1]
    decoded = decode_line(line.rstrip(b"\n"))
    assert decoded["method"] == "initialize"


def test_build_authenticate() -> None:
    payload = build_authenticate(2, method_id="cursor_login")
    assert payload["method"] == "authenticate"
    assert payload["params"]["methodId"] == "cursor_login"


def test_first_auth_method_id_shapes() -> None:
    assert first_auth_method_id([]) is None
    assert first_auth_method_id(["cursor_login"]) == "cursor_login"
    assert first_auth_method_id([{"id": "cursor_login"}]) == "cursor_login"
    assert first_auth_method_id([{"methodId": "cursor_login"}]) == "cursor_login"
    assert first_auth_method_id([{}]) is None


@pytest.mark.parametrize(
    ("kinds", "expected"),
    [
        (["allow_always", "allow_once"], "allow_always"),
        (["allow_once", "reject_once"], "allow_once"),
        (["reject_once", "other"], "other"),
        (["reject_once", "reject_always"], "reject_once"),
    ],
)
def test_permission_option_order(kinds: list[str], expected: str) -> None:
    options = [
        PermissionOption(option_id=kind, kind=kind) for kind in kinds
    ]
    chosen = choose_permission_option(options)
    assert chosen.kind == expected


def test_empty_permission_options_raise() -> None:
    with pytest.raises(AcpError):
        choose_permission_option([])
