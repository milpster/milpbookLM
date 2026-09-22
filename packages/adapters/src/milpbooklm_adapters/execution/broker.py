"""
Execution broker: the permission-restricted Unix-socket service (EXE-01, guide/04).

The broker is the narrow boundary ``worker-core`` talks to. It owns a
0600-mode Unix socket inside an 0700 directory, identifies every caller via
``SO_PEERCRED`` kernel credentials (never a client-supplied identity),
accepts only signed+nonce-bound execution specs, re-resolves staged inputs
through the provider's narrow read service (staged blob IDs become bytes on
the broker side — the spec schema has no host-path or mount field at all),
runs the sandbox executor, and answers with either a typed refusal or the
bounded execution outcome.

The wire protocol is one request and one response per connection: a 4-byte
big-endian length prefix (capped at :data:`MAX_FRAME_BYTES`) framing the
JSON envelope from :mod:`milpbooklm_adapters.execution.spec_protocol`.
Responses carry only metadata, digests and bounded (base64) excerpts —
never full content (arch ch12 §9: execution traces are user-private; logs
carry codes, sizes and timings only). Output quarantine paths are internal
handles for the publishing step (``OutputCollector.publish`` after authz
revalidation); in the dedicated-account deployment form this becomes a
follow-up broker operation (documented deferral).

Deployment form (deferred, T8-class): the reference form is a host-side
systemd service under a dedicated unprivileged account with a cgroup
delegation drop-in; this module is the user-space core running under the
current account for the prototype, unchanged in its boundary semantics.
Serving is sequential: one execution at a time IS the concurrency limit.
"""

from __future__ import annotations

import base64
import contextlib
import json
import logging
import socket
import struct
import uuid
from pathlib import Path

from milpbooklm_application.execution import (
    DeclaredOutput,
    ExecutionLimits,
    ExecutionOutcome,
    ExecutionProvider,
    ExecutionRefusalCode,
    ExecutionRefusedError,
    ExecutionSpec,
    ExecutionStatus,
    ProducedOutput,
)

from milpbooklm_adapters.execution.spec_protocol import (
    MAX_FRAME_BYTES,
    NonceReplayGuard,
    sign_envelope,
    verify_envelope,
)

logger = logging.getLogger(__name__)

_LENGTH_PREFIX = struct.Struct("!I")
_SO_PEERCRED = getattr(socket, "SO_PEERCRED", 17)
_LIMIT_FIELDS = (
    "wall_timeout_seconds",
    "memory_max_bytes",
    "pids_max",
    "cpu_quota_micros",
    "cpu_period_micros",
    "tmpfs_max_bytes",
    "max_stdout_bytes",
    "max_stderr_bytes",
    "max_staged_input_bytes",
    "max_output_file_bytes",
    "max_total_output_bytes",
)


def send_frame(sock: socket.socket, payload: bytes) -> None:
    """Write one length-prefixed frame."""
    sock.sendall(_LENGTH_PREFIX.pack(len(payload)) + payload)


def recv_frame(sock: socket.socket) -> bytes:
    """
    Read one length-prefixed frame (typed refusal on oversize/EOF).

    Raises ExecutionRefusedError(MALFORMED_FRAME) for a truncated stream or
    a frame beyond the protocol cap.
    """
    header = _recv_exact(sock, _LENGTH_PREFIX.size)
    if header is None:
        raise ExecutionRefusedError(
            ExecutionRefusalCode.MALFORMED_FRAME, "stream ended before frame"
        )
    (length,) = _LENGTH_PREFIX.unpack(header)
    if length > MAX_FRAME_BYTES:
        raise ExecutionRefusedError(
            ExecutionRefusalCode.MALFORMED_FRAME, "frame exceeds protocol cap"
        )
    body = _recv_exact(sock, length)
    if body is None:
        raise ExecutionRefusedError(ExecutionRefusalCode.MALFORMED_FRAME, "stream ended mid-frame")
    return body


def _recv_exact(sock: socket.socket, count: int) -> bytes | None:
    chunks: list[bytes] = []
    remaining = count
    while remaining > 0:
        chunk = sock.recv(min(remaining, 65536))
        if not chunk:
            return None
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def peer_uid(conn: socket.socket) -> int | None:
    """Return the connecting peer's kernel-verified uid (or None off-Linux)."""
    try:
        raw = conn.getsockopt(socket.SOL_SOCKET, _SO_PEERCRED, struct.calcsize("3i"))
    except OSError:
        return None
    credentials = struct.unpack("3i", raw)
    return int(credentials[1])


def spec_to_wire(spec: ExecutionSpec) -> dict[str, object]:
    """Serialize a spec to its wire dict (the signed surface)."""
    limits = spec.limits
    return {
        "image_digest": spec.image_digest,
        "argv": list(spec.argv),
        "env": dict(spec.env_allowlist),
        "input_blob_ids": [str(blob_id) for blob_id in spec.input_blob_ids],
        "declared_outputs": [
            {"path": entry.relative_path, "max_bytes": entry.max_bytes}
            for entry in spec.declared_outputs
        ],
        "limits": {field: getattr(limits, field) for field in _LIMIT_FIELDS},
    }


def spec_from_wire(payload: dict[str, object], *, nonce: str) -> ExecutionSpec:  # noqa: C901, PLR0912 - strict boundary parse: one refusal branch per wire field
    """
    Parse a wire dict back into a typed spec (strict: unknown keys refused).

    Raises ExecutionRefusedError(INVALID_SPEC) on any shape drift — parse,
    don't validate (the boundary owns trust).
    """
    known = {
        "image_digest",
        "argv",
        "env",
        "input_blob_ids",
        "declared_outputs",
        "limits",
    }
    unknown = set(payload) - known
    if unknown:
        raise ExecutionRefusedError(
            ExecutionRefusalCode.INVALID_SPEC, f"unknown spec fields: {sorted(unknown)}"
        )
    image_digest = payload.get("image_digest")
    argv = payload.get("argv")
    if not isinstance(image_digest, str) or not isinstance(argv, list) or not argv:
        raise ExecutionRefusedError(ExecutionRefusalCode.INVALID_SPEC, "image_digest/argv missing")
    if not all(isinstance(part, str) for part in argv):
        raise ExecutionRefusedError(
            ExecutionRefusalCode.INVALID_SPEC, "argv entries must be strings"
        )
    env_raw = payload.get("env", {})
    if not isinstance(env_raw, dict) or not all(
        isinstance(key, str) and isinstance(value, str) for key, value in env_raw.items()
    ):
        raise ExecutionRefusedError(ExecutionRefusalCode.INVALID_SPEC, "env must be a string map")
    blob_ids_raw = payload.get("input_blob_ids", [])
    if not isinstance(blob_ids_raw, list):
        raise ExecutionRefusedError(
            ExecutionRefusalCode.INVALID_SPEC, "input_blob_ids must be a list"
        )
    blob_ids: list[uuid.UUID] = []
    for entry in blob_ids_raw:
        if not isinstance(entry, str):
            raise ExecutionRefusedError(
                ExecutionRefusalCode.INVALID_SPEC, "blob id must be a string"
            )
        try:
            blob_ids.append(uuid.UUID(entry))
        except ValueError as exc:
            raise ExecutionRefusedError(
                ExecutionRefusalCode.INVALID_SPEC, "blob id is not a uuid"
            ) from exc
    outputs_raw = payload.get("declared_outputs", [])
    if not isinstance(outputs_raw, list):
        raise ExecutionRefusedError(
            ExecutionRefusalCode.INVALID_SPEC, "declared_outputs must be a list"
        )
    declared: list[DeclaredOutput] = []
    for entry in outputs_raw:
        if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
            raise ExecutionRefusedError(
                ExecutionRefusalCode.INVALID_SPEC, "declared output entry malformed"
            )
        max_bytes = entry.get("max_bytes")
        if not isinstance(max_bytes, int):
            raise ExecutionRefusedError(
                ExecutionRefusalCode.INVALID_SPEC, "declared output max_bytes must be an int"
            )
        declared.append(DeclaredOutput(relative_path=entry["path"], max_bytes=max_bytes))
    limits_raw = payload.get("limits", {})
    if not isinstance(limits_raw, dict):
        raise ExecutionRefusedError(ExecutionRefusalCode.INVALID_SPEC, "limits must be an object")
    defaults = ExecutionLimits()
    fields = {field: getattr(defaults, field) for field in _LIMIT_FIELDS}
    for field, value in limits_raw.items():
        if field not in fields or not isinstance(value, (int, float)):
            raise ExecutionRefusedError(
                ExecutionRefusalCode.INVALID_SPEC, f"limit field {field!r} is not known/numeric"
            )
        fields[field] = value
    limits = ExecutionLimits(**fields)
    return ExecutionSpec(
        image_digest=image_digest,
        argv=tuple(argv),
        env_allowlist=tuple(sorted(env_raw.items())),
        input_blob_ids=tuple(blob_ids),
        declared_outputs=tuple(declared),
        limits=limits,
        nonce=nonce,
    )


def outcome_to_wire(outcome: ExecutionOutcome) -> dict[str, object]:
    """Serialize an outcome for the response frame (bounded, metadata only)."""
    return {
        "status": outcome.status.value,
        "exit_code": outcome.exit_code,
        "stdout_b64": base64.b64encode(outcome.stdout_excerpt).decode("ascii"),
        "stderr_b64": base64.b64encode(outcome.stderr_excerpt).decode("ascii"),
        "outputs": [
            {
                "declared_path": output.declared_path,
                "content_sha256": output.content_sha256,
                "size_bytes": output.size_bytes,
                "sniffed_media": output.sniffed_media,
                "quarantine_path": output.quarantine_path,
                "blob_id": str(output.blob_id) if output.blob_id else None,
            }
            for output in outcome.outputs
        ],
        "wall_seconds": outcome.wall_seconds,
        "oom_kill_count": outcome.oom_kill_count,
        "kill_method": outcome.kill_method,
        "image_digest": outcome.image_digest,
        "truncated_streams": outcome.truncated_streams,
        "undeclared_output_count": outcome.undeclared_output_count,
    }


def outcome_from_wire(payload: dict[str, object]) -> ExecutionOutcome:
    """
    Parse a response outcome payload back into the typed outcome (strict).

    Any shape drift — missing fields, wrong types, undecodable base64 or a
    non-uuid blob id — is a typed PROTOCOL_TRANSPORT refusal; nothing is
    coerced or defaulted into existence.
    """
    status = payload.get("status")
    exit_code = payload.get("exit_code")
    stdout_b64 = payload.get("stdout_b64")
    stderr_b64 = payload.get("stderr_b64")
    outputs_raw = payload.get("outputs", [])
    wall_seconds = payload.get("wall_seconds")
    oom_kill_count = payload.get("oom_kill_count")
    kill_method = payload.get("kill_method")
    image_digest = payload.get("image_digest")
    truncated = payload.get("truncated_streams", False)
    undeclared = payload.get("undeclared_output_count", 0)
    if (
        not isinstance(status, str)
        or not (exit_code is None or isinstance(exit_code, int))
        or not isinstance(stdout_b64, str)
        or not isinstance(stderr_b64, str)
        or not isinstance(outputs_raw, list)
        or not isinstance(wall_seconds, (int, float))
        or not isinstance(oom_kill_count, int)
        or not isinstance(kill_method, str)
        or not isinstance(image_digest, str)
        or not isinstance(truncated, bool)
        or not isinstance(undeclared, int)
    ):
        raise ExecutionRefusedError(
            ExecutionRefusalCode.PROTOCOL_TRANSPORT, "outcome payload is malformed"
        )
    try:
        stdout_excerpt = base64.b64decode(stdout_b64, validate=True)
        stderr_excerpt = base64.b64decode(stderr_b64, validate=True)
    except (ValueError, TypeError) as exc:
        raise ExecutionRefusedError(
            ExecutionRefusalCode.PROTOCOL_TRANSPORT, "outcome payload is not decodable"
        ) from exc
    outputs: list[ProducedOutput] = []
    for entry in outputs_raw:
        if not isinstance(entry, dict):
            raise ExecutionRefusedError(
                ExecutionRefusalCode.PROTOCOL_TRANSPORT, "outcome output entry is not an object"
            )
        declared_path = entry.get("declared_path")
        content_sha256 = entry.get("content_sha256")
        size_bytes = entry.get("size_bytes")
        sniffed_media = entry.get("sniffed_media")
        quarantine_path = entry.get("quarantine_path")
        blob_raw = entry.get("blob_id")
        if (
            not isinstance(declared_path, str)
            or not isinstance(content_sha256, str)
            or not isinstance(size_bytes, int)
            or not isinstance(sniffed_media, str)
            or not isinstance(quarantine_path, str)
            or not (blob_raw is None or isinstance(blob_raw, str))
        ):
            raise ExecutionRefusedError(
                ExecutionRefusalCode.PROTOCOL_TRANSPORT, "outcome output entry is malformed"
            )
        try:
            blob_id = uuid.UUID(blob_raw) if blob_raw is not None else None
        except ValueError as exc:
            raise ExecutionRefusedError(
                ExecutionRefusalCode.PROTOCOL_TRANSPORT, "outcome output entry is not decodable"
            ) from exc
        outputs.append(
            ProducedOutput(
                declared_path=declared_path,
                content_sha256=content_sha256,
                size_bytes=size_bytes,
                sniffed_media=sniffed_media,
                quarantine_path=quarantine_path,
                blob_id=blob_id,
            )
        )
    return ExecutionOutcome(
        status=ExecutionStatus(status),
        exit_code=exit_code,
        stdout_excerpt=stdout_excerpt,
        stderr_excerpt=stderr_excerpt,
        outputs=tuple(outputs),
        wall_seconds=float(wall_seconds),
        oom_kill_count=oom_kill_count,
        kill_method=kill_method,
        image_digest=image_digest,
        truncated_streams=truncated,
        undeclared_output_count=undeclared,
    )


class ExecutionBroker:
    """The Unix-socket execution service (one signed request per connection)."""

    def __init__(
        self,
        socket_path: Path,
        *,
        provider: ExecutionProvider,
        public_key: bytes,
        allowed_uids: frozenset[int],
        replay: NonceReplayGuard | None = None,
        socket_mode: int = 0o600,
    ) -> None:
        """Wire the socket path, provider, verification key and peer policy."""
        self._socket_path = socket_path
        self._provider = provider
        self._public_key = public_key
        self._allowed_uids = allowed_uids
        self._replay = replay if replay is not None else NonceReplayGuard()
        self._socket_mode = socket_mode

    def listen(self) -> None:
        """Bind the socket with restricted permissions (0700 dir, 0600 socket)."""
        self._socket_path.parent.mkdir(parents=True, exist_ok=True)
        self._socket_path.parent.chmod(0o700)
        if self._socket_path.exists():
            self._socket_path.unlink()
        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server.bind(str(self._socket_path))
        self._socket_path.chmod(self._socket_mode)
        server.listen(4)
        self._server = server

    def serve(self, max_connections: int | None = None) -> None:
        """Accept and answer connections sequentially (concurrency limit: 1)."""
        served = 0
        while max_connections is None or served < max_connections:
            try:
                conn, _addr = self._server.accept()
            except OSError:
                break
            try:
                self._handle(conn)
            finally:
                conn.close()
            served += 1

    def close(self) -> None:
        """Close the listening socket and remove the socket file."""
        self._server.close()
        self._socket_path.unlink(missing_ok=True)

    def _handle(self, conn: socket.socket) -> None:
        """Answer one connection: verify, execute, respond (typed refusals)."""
        try:
            response = self._build_response(conn)
        except ExecutionRefusedError as refusal:
            response = {
                "refused": {"code": refusal.code.value, "detail": refusal.detail},
            }
        except Exception as exc:  # boundary: never leak internals or content
            logger.warning(
                "execution broker internal failure",
                extra={"error_class": exc.__class__.__name__},
            )
            response = {
                "refused": {
                    "code": ExecutionRefusalCode.BROKER_UNAVAILABLE.value,
                    "detail": "internal",
                },
            }
        with contextlib.suppress(OSError):
            send_frame(conn, _json_bytes(response))

    def _build_response(self, conn: socket.socket) -> dict[str, object]:
        """Run the full verification pipeline; return the response payload."""
        uid = peer_uid(conn)
        if uid is None or uid not in self._allowed_uids:
            raise ExecutionRefusedError(
                ExecutionRefusalCode.UNKNOWN_PEER, f"peer uid {uid} is not an authorized caller"
            )
        raw = recv_frame(conn)
        verified = verify_envelope(raw, self._public_key, self._replay)
        spec = spec_from_wire(verified.spec, nonce=verified.nonce)
        outcome = self._provider.run(spec)
        logger.info(
            "execution completed",
            extra={
                "status": outcome.status.value,
                "wall_seconds": round(outcome.wall_seconds, 3),
                "oom_kill_count": outcome.oom_kill_count,
                "kill_method": outcome.kill_method,
                "outputs": len(outcome.outputs),
            },
        )
        return {"outcome": outcome_to_wire(outcome)}


class BrokerExecutionClient:
    """The worker-core side: signs specs and speaks the broker protocol."""

    def __init__(self, socket_path: Path, *, secret_key: bytes) -> None:
        """Bind the broker socket path and the client signing key."""
        self._socket_path = socket_path
        self._secret_key = secret_key

    def run(self, spec: ExecutionSpec) -> ExecutionOutcome:
        """
        Send one signed spec; return the outcome or raise the typed refusal.

        Every call mints a fresh nonce (uuid4); a reused envelope would be
        refused as a replay by the broker.
        """
        envelope = sign_envelope(
            spec_to_wire(spec), nonce=spec.nonce or uuid.uuid4().hex, secret_key=self._secret_key
        )
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            sock.connect(str(self._socket_path))
            send_frame(sock, envelope)
            payload: object = json.loads(recv_frame(sock))
        except OSError as exc:
            raise ExecutionRefusedError(
                ExecutionRefusalCode.BROKER_UNAVAILABLE,
                f"broker unreachable: {exc.__class__.__name__}",
            ) from exc
        finally:
            sock.close()
        if not isinstance(payload, dict):
            raise ExecutionRefusedError(
                ExecutionRefusalCode.PROTOCOL_TRANSPORT, "response is not an object"
            )
        refused = payload.get("refused")
        if isinstance(refused, dict):
            code = str(refused.get("code", ExecutionRefusalCode.BROKER_UNAVAILABLE.value))
            raise ExecutionRefusedError(ExecutionRefusalCode(code), str(refused.get("detail", "")))
        outcome = payload.get("outcome")
        if not isinstance(outcome, dict):
            raise ExecutionRefusedError(
                ExecutionRefusalCode.PROTOCOL_TRANSPORT, "response carries no outcome"
            )
        return outcome_from_wire(outcome)


def _json_bytes(payload: dict[str, object]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
