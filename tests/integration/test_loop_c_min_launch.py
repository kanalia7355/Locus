"""A failed durable launch reservation must keep the owned child suspended."""

import http.client
import sys
import time
from pathlib import Path
from typing import Any

import pytest

from loop_engine.audit_transport import AuditRelay
from loop_engine.process import ProcessRunner
from loop_engine.security import SafetyError
from loop_engine.windows_tcp_peer import OwnedCliPeer


@pytest.mark.skipif(sys.platform != "win32", reason="Windows suspended owned-job launch")
def test_failed_launch_reservation_never_resumes_owned_process(tmp_path: Path) -> None:
    marker = tmp_path / "must-not-exist"

    def reserve(pid: int, job: Any) -> None:
        assert pid > 0 and job.handle
        raise SafetyError("synthetic durable launch reservation failure")

    with pytest.raises(SafetyError):
        ProcessRunner().run(
            [
                sys.executable,
                "-c",
                "from pathlib import Path;Path(" + repr(str(marker)) + ').write_text("resumed")',
            ],
            tmp_path,
            timeout=5,
            before_resume=reserve,
        )
    assert not marker.exists()


@pytest.mark.skipif(sys.platform != "win32", reason="Windows kernel TCP owner binding")
def test_same_sid_different_real_pid_is_rejected_before_request(tmp_path: Path) -> None:
    peer = OwnedCliPeer(sys.executable)
    with AuditRelay(
        "gpt-6.1-sol",
        deadline=time.monotonic() + 5,
        cancelled=lambda: False,
        peer_authorized=peer,
        request_validator=lambda _: {},
    ) as relay:

        def bind_and_attack(pid: int, job: Any) -> None:
            peer.bind(pid, job)
            client = http.client.HTTPConnection("127.0.0.1", relay.server.server_port, timeout=2)
            try:
                with pytest.raises((http.client.HTTPException, OSError)):
                    client.request("POST", "/responses", b"{}")
                    client.getresponse()
            finally:
                client.close()
            assert relay.failed and not relay.used
            raise SafetyError("owned child remains suspended after peer rejection")

        try:
            with pytest.raises(SafetyError):
                ProcessRunner().run(
                    [sys.executable, "-c", "pass"],
                    tmp_path,
                    timeout=4,
                    before_resume=bind_and_attack,
                )
        finally:
            peer.close()
        assert relay.connection is None and not relay.accepted
