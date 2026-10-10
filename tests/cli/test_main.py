"""CLI entrypoint smoke tests."""

from orkie.cli import main


def test_main_returns_zero_before_implementation() -> None:
    assert main([]) == 0
