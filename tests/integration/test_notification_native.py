"""Pinned CLI, synthetic home and loopback only; no actual auth or model call."""

import sys

import pytest
from test_loop_c_min_native import (
    test_installed_cli_zero_declarations_clean_mock_json_and_owned_peer as native_case,
)


@pytest.mark.skipif(sys.platform != "win32", reason="Pinned Windows CLI required")
@pytest.mark.parametrize("mode", ["success", "tool", "cancel"])
def test_official_cli_notify_suppression_is_invocation_only(tmp_path, monkeypatch, mode):
    native_case(tmp_path, monkeypatch, mode, suppression=True)
