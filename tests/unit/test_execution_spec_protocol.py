from __future__ import annotations

import json

import pytest
from milpbooklm_adapters.execution.spec_protocol import (
    NonceReplayGuard,
    generate_signing_keypair,
    sign_envelope,
    verify_envelope,
)
from milpbooklm_application.execution import ExecutionRefusalCode, ExecutionRefusedError


def _spec() -> dict[str, object]:
    return {"image_digest": "sha256:" + "a" * 64, "argv": ["/bin/true"]}


def test_signed_envelope_binds_verified_nonce() -> None:
    secret_key, public_key = generate_signing_keypair()
    raw = sign_envelope(_spec(), "nonce-0123456789abcdef", secret_key)

    verified = verify_envelope(raw, public_key, NonceReplayGuard())

    assert verified.nonce == "nonce-0123456789abcdef"
    assert verified.spec == _spec()


def test_unsigned_envelope_is_refused() -> None:
    _secret_key, public_key = generate_signing_keypair()
    raw = json.dumps(
        {
            "version": 1,
            "nonce": "nonce-0123456789abcdef",
            "issued_at": 1.0,
            "spec": _spec(),
            "signature": None,
        }
    ).encode()

    with pytest.raises(ExecutionRefusedError) as raised:
        verify_envelope(raw, public_key, NonceReplayGuard(now=lambda: 1.0))

    assert raised.value.code is ExecutionRefusalCode.UNSIGNED_SPEC


def test_tampered_envelope_is_refused() -> None:
    secret_key, public_key = generate_signing_keypair()
    payload = json.loads(sign_envelope(_spec(), "nonce-0123456789abcdef", secret_key))
    payload["spec"]["argv"] = ["/bin/false"]

    with pytest.raises(ExecutionRefusedError) as raised:
        verify_envelope(
            json.dumps(payload).encode(),
            public_key,
            NonceReplayGuard(),
        )

    assert raised.value.code is ExecutionRefusalCode.BAD_SIGNATURE


def test_replayed_envelope_is_refused() -> None:
    secret_key, public_key = generate_signing_keypair()
    raw = sign_envelope(_spec(), "nonce-0123456789abcdef", secret_key)
    replay = NonceReplayGuard()
    verify_envelope(raw, public_key, replay)

    with pytest.raises(ExecutionRefusedError) as raised:
        verify_envelope(raw, public_key, replay)

    assert raised.value.code is ExecutionRefusalCode.NONCE_REPLAY


def test_stale_and_non_finite_timestamps_are_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    secret_key, public_key = generate_signing_keypair()
    monkeypatch.setattr("milpbooklm_adapters.execution.spec_protocol.time.time", lambda: 10.0)
    stale = sign_envelope(_spec(), "nonce-0123456789abcdef", secret_key)
    monkeypatch.setattr("milpbooklm_adapters.execution.spec_protocol.time.time", lambda: 50.0)

    with pytest.raises(ExecutionRefusedError) as stale_error:
        verify_envelope(stale, public_key, NonceReplayGuard(window_seconds=5.0))
    assert stale_error.value.code is ExecutionRefusalCode.NONCE_STALE

    monkeypatch.setattr(
        "milpbooklm_adapters.execution.spec_protocol.time.time", lambda: float("nan")
    )
    non_finite = sign_envelope(_spec(), "nonce-fedcba9876543210", secret_key)
    with pytest.raises(ExecutionRefusedError) as malformed:
        verify_envelope(non_finite, public_key, NonceReplayGuard())
    assert malformed.value.code is ExecutionRefusalCode.MALFORMED_FRAME
