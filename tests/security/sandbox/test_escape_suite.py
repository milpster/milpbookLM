from __future__ import annotations

import json
import os
import shutil
import socket
import threading
import uuid
from dataclasses import dataclass, replace
from pathlib import Path

import pytest
from milpbooklm_adapters.execution.broker import (
    ExecutionBroker,
    recv_frame,
    send_frame,
    spec_to_wire,
)
from milpbooklm_adapters.execution.cgroups import DelegatedCgroupController
from milpbooklm_adapters.execution.host_probe import probe_execution_host
from milpbooklm_adapters.execution.images import RuntimeImageStore
from milpbooklm_adapters.execution.outputs import OutputCollector
from milpbooklm_adapters.execution.sandbox import BubblewrapExecutionProvider
from milpbooklm_adapters.execution.spec_protocol import generate_signing_keypair, sign_envelope
from milpbooklm_application.execution import (
    DeclaredOutput,
    ExecutionHostPosture,
    ExecutionLimits,
    ExecutionSpec,
    ExecutionStatus,
)


@dataclass(frozen=True, slots=True)
class _InputReader:
    payloads: dict[uuid.UUID, bytes]

    def read(self, blob_id: uuid.UUID) -> bytes:
        return self.payloads[blob_id]


@dataclass(frozen=True, slots=True)
class _Harness:
    provider: BubblewrapExecutionProvider
    collector: OutputCollector
    posture: ExecutionHostPosture
    cgroup_slice: Path
    input_id: uuid.UUID
    image_digest: str


@pytest.fixture(scope="module")
def sandbox(tmp_path_factory: pytest.TempPathFactory) -> _Harness:
    root = tmp_path_factory.mktemp("sandbox-sec-001")
    runtime = root / "runtime" / "usr" / "bin"
    runtime.mkdir(parents=True)
    shutil.copy2("/usr/bin/busybox", runtime / "busybox")
    images = RuntimeImageStore(root / "images")
    digest = images.install(runtime.parents[1], name="busybox-1.37", sbom={"packages": ["busybox"]})
    posture = probe_execution_host()
    if not posture.execution_available or posture.cgroup_root is None:
        pytest.fail(f"mandatory execution posture unavailable: {posture.notes}")
    cgroups = DelegatedCgroupController(Path(posture.cgroup_root))
    collector = OutputCollector(root / "quarantine")
    input_id = uuid.uuid4()
    provider = BubblewrapExecutionProvider(
        posture=posture,
        images=images,
        read_service=_InputReader({input_id: b"staged-only"}),
        work_root=root / "work",
        collector=collector,
        cgroups=cgroups,
    )
    return _Harness(provider, collector, posture, Path(cgroups.slice_path), input_id, digest)


def _spec(sandbox: _Harness, script: str, **limits: int | float) -> ExecutionSpec:
    defaults = ExecutionLimits(
        wall_timeout_seconds=3.0,
        memory_max_bytes=64 * 1024 * 1024,
        pids_max=32,
        cpu_quota_micros=100_000,
        cpu_period_micros=100_000,
        tmpfs_max_bytes=16 * 1024 * 1024,
        max_stdout_bytes=4096,
        max_stderr_bytes=4096,
    )
    return ExecutionSpec(
        image_digest=sandbox.image_digest,
        argv=("/bin/busybox", "sh", "-c", script),
        limits=replace(defaults, **limits),
    )


def test_filesystem_inputs_and_declared_output_boundaries(sandbox: _Harness) -> None:
    spec = replace(
        _spec(
            sandbox,
            "set -eu; "
            "test ! -e /home/srcds; test ! -e /run/user/1000; test ! -e /etc/passwd; "
            "! touch /usr/escape; ! touch /workspace/escape; "
            'test "$(cat /workspace/inputs/input-000.bin)" = staged-only; '
            "! sh -c 'echo x >> /workspace/inputs/input-000.bin'; "
            "printf result > /workspace/outputs/result.txt",
        ),
        input_blob_ids=(sandbox.input_id,),
        declared_outputs=(DeclaredOutput("result.txt", 64),),
    )

    outcome = sandbox.provider.run(spec)

    assert outcome.status is ExecutionStatus.SUCCEEDED
    assert Path(outcome.outputs[0].quarantine_path).read_bytes() == b"result"
    sandbox.collector.discard(outcome.outputs)


def test_process_privilege_and_descriptor_boundaries(sandbox: _Harness) -> None:
    outcome = sandbox.provider.run(
        _spec(
            sandbox,
            "set -eu; "
            "test \"$(awk '/^NoNewPrivs:/{print $2}' /proc/self/status)\" = 1; "
            "test \"$(awk '/^CapEff:/{print $2}' /proc/self/status)\" = 0000000000000000; "
            'set -- /proc/[0-9]*; test "$#" -le 4; test ! -e /proc/self/fd/3',
        )
    )

    assert outcome.status is ExecutionStatus.SUCCEEDED


def test_network_namespace_has_no_usable_route(sandbox: _Harness) -> None:
    outcome = sandbox.provider.run(
        _spec(
            sandbox,
            'set -eu; test "$(wc -l < /proc/net/route)" -eq 1; '
            "! /bin/busybox nc -z -w 1 127.0.0.1 9",
        )
    )

    assert outcome.status is ExecutionStatus.SUCCEEDED


def test_undeclared_output_is_a_policy_violation(sandbox: _Harness) -> None:
    spec = replace(
        _spec(
            sandbox,
            "printf declared > /workspace/outputs/result.txt; "
            "printf secret > /workspace/outputs/secret.txt",
        ),
        declared_outputs=(DeclaredOutput("result.txt", 64),),
    )

    outcome = sandbox.provider.run(spec)

    assert outcome.status is ExecutionStatus.POLICY_VIOLATION
    assert outcome.outputs == ()


def test_timeout_and_ignored_signals_leave_no_cgroup_survivors(sandbox: _Harness) -> None:
    outcome = sandbox.provider.run(
        _spec(
            sandbox,
            "trap '' TERM INT HUP; (trap '' TERM INT HUP; sleep 30) & while :; do sleep 30; done",
            wall_timeout_seconds=0.2,
        )
    )

    assert outcome.status is ExecutionStatus.TIMEOUT_KILLED
    assert outcome.kill_method == "cgroup.kill"
    assert list(sandbox.cgroup_slice.glob("exec-*")) == []


def test_cgroup_memory_oom_is_distinct_from_policy_violation(sandbox: _Harness) -> None:
    outcome = sandbox.provider.run(
        _spec(
            sandbox,
            "/bin/busybox dd if=/dev/zero of=/tmp/fill bs=1M count=64",
            memory_max_bytes=24 * 1024 * 1024,
            tmpfs_max_bytes=64 * 1024 * 1024,
        )
    )

    assert outcome.status is ExecutionStatus.OOM_KILLED
    assert outcome.oom_kill_count >= 1


def test_tampered_signed_spec_is_denied_on_real_socket(sandbox: _Harness, tmp_path: Path) -> None:
    secret_key, public_key = generate_signing_keypair()
    socket_path = tmp_path / "broker" / "execution.sock"
    broker = ExecutionBroker(
        socket_path,
        provider=sandbox.provider,
        public_key=public_key,
        allowed_uids=frozenset({os.getuid()}),
    )
    broker.listen()
    thread = threading.Thread(target=broker.serve, kwargs={"max_connections": 1})
    thread.start()
    payload = json.loads(
        sign_envelope(spec_to_wire(_spec(sandbox, "true")), "nonce-0123456789abcdef", secret_key)
    )
    payload["spec"]["argv"] = ["/bin/busybox", "false"]

    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.connect(str(socket_path))
        send_frame(client, json.dumps(payload).encode())
        response = json.loads(recv_frame(client))
    thread.join(timeout=2)
    broker.close()

    assert response["refused"]["code"] == "bad_signature"
