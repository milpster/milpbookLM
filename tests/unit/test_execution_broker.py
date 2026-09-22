from __future__ import annotations

import json
import os
import socket
import stat
import threading
from pathlib import Path

from milpbooklm_adapters.execution.broker import (
    BrokerExecutionClient,
    ExecutionBroker,
    peer_uid,
    recv_frame,
    send_frame,
    spec_to_wire,
)
from milpbooklm_adapters.execution.spec_protocol import generate_signing_keypair, sign_envelope
from milpbooklm_application.execution import (
    ExecutionOutcome,
    ExecutionSpec,
    ExecutionStatus,
)

_SOCKET_MODE = 0o600
_SOCKET_DIR_MODE = 0o700


class _RecordingProvider:
    def __init__(self) -> None:
        self.specs: list[ExecutionSpec] = []

    def run(self, spec: ExecutionSpec) -> ExecutionOutcome:
        self.specs.append(spec)
        return ExecutionOutcome(
            status=ExecutionStatus.SUCCEEDED,
            exit_code=0,
            stdout_excerpt=b"ok",
            stderr_excerpt=b"",
            outputs=(),
            wall_seconds=0.01,
            oom_kill_count=0,
            kill_method="exit",
            image_digest=spec.image_digest,
        )


def _serve_once(broker: ExecutionBroker) -> threading.Thread:
    thread = threading.Thread(target=broker.serve, kwargs={"max_connections": 1})
    thread.start()
    return thread


def test_peer_uid_comes_from_kernel_credentials() -> None:
    first, second = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        assert peer_uid(first) == os.getuid()
        assert peer_uid(second) == os.getuid()
    finally:
        first.close()
        second.close()


def test_broker_runs_signed_spec_over_restricted_real_socket(tmp_path: Path) -> None:
    secret_key, public_key = generate_signing_keypair()
    provider = _RecordingProvider()
    socket_path = tmp_path / "broker" / "execution.sock"
    broker = ExecutionBroker(
        socket_path,
        provider=provider,
        public_key=public_key,
        allowed_uids=frozenset({os.getuid()}),
    )
    broker.listen()
    thread = _serve_once(broker)

    outcome = BrokerExecutionClient(socket_path, secret_key=secret_key).run(
        ExecutionSpec(image_digest="sha256:" + "a" * 64, argv=("/bin/true",))
    )
    thread.join(timeout=2)

    assert outcome.status is ExecutionStatus.SUCCEEDED
    assert provider.specs[0].nonce
    socket_mode = stat.S_IMODE(socket_path.stat().st_mode)
    dir_mode = stat.S_IMODE(socket_path.parent.stat().st_mode)
    assert socket_mode == _SOCKET_MODE
    assert dir_mode == _SOCKET_DIR_MODE
    broker.close()


def test_broker_denies_tampered_spec_before_provider(tmp_path: Path) -> None:
    secret_key, public_key = generate_signing_keypair()
    provider = _RecordingProvider()
    socket_path = tmp_path / "broker" / "execution.sock"
    broker = ExecutionBroker(
        socket_path,
        provider=provider,
        public_key=public_key,
        allowed_uids=frozenset({os.getuid()}),
    )
    broker.listen()
    thread = _serve_once(broker)
    spec = ExecutionSpec(image_digest="sha256:" + "a" * 64, argv=("/bin/true",))
    payload = json.loads(sign_envelope(spec_to_wire(spec), "nonce-0123456789abcdef", secret_key))
    payload["spec"]["argv"] = ["/bin/false"]

    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.connect(str(socket_path))
        send_frame(client, json.dumps(payload).encode())
        response = json.loads(recv_frame(client))
    thread.join(timeout=2)

    assert response["refused"]["code"] == "bad_signature"
    assert provider.specs == []
    broker.close()
