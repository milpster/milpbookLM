"""
Execution adapters: the local-bubblewrap provider stack (EXE-01, guide/12).

Composition: :func:`probe_execution_host` verifies the fail-closed host
posture, :class:`RuntimeImageStore` resolves content-addressed runtime
images, :class:`BubblewrapExecutionProvider` runs the reviewed isolation
profile with per-execution cgroup limits, :class:`OutputCollector`
validates/quarantines/publishes outputs, and :class:`ExecutionBroker` +
:class:`BrokerExecutionClient` are the signed Unix-socket boundary.
"""

from milpbooklm_adapters.execution.broker import (
    BrokerExecutionClient,
    ExecutionBroker,
    outcome_from_wire,
    outcome_to_wire,
    peer_uid,
    recv_frame,
    send_frame,
    spec_from_wire,
    spec_to_wire,
)
from milpbooklm_adapters.execution.cgroups import (
    DelegatedCgroupController,
    ExecutionCgroup,
    discover_delegated_cgroup_root,
)
from milpbooklm_adapters.execution.host_probe import probe_execution_host
from milpbooklm_adapters.execution.images import (
    ImageVerificationError,
    RuntimeImage,
    RuntimeImageStore,
)
from milpbooklm_adapters.execution.outputs import OutputCollector, validate_declared_path
from milpbooklm_adapters.execution.sandbox import BubblewrapExecutionProvider, StagedInputReader
from milpbooklm_adapters.execution.spec_protocol import (
    NonceReplayGuard,
    generate_signing_keypair,
    load_signing_secret,
    load_verification_key,
    sign_envelope,
    verify_envelope,
)

__all__ = [
    "BrokerExecutionClient",
    "BubblewrapExecutionProvider",
    "DelegatedCgroupController",
    "ExecutionBroker",
    "ExecutionCgroup",
    "ImageVerificationError",
    "NonceReplayGuard",
    "OutputCollector",
    "RuntimeImage",
    "RuntimeImageStore",
    "StagedInputReader",
    "discover_delegated_cgroup_root",
    "generate_signing_keypair",
    "load_signing_secret",
    "load_verification_key",
    "outcome_from_wire",
    "outcome_to_wire",
    "peer_uid",
    "probe_execution_host",
    "recv_frame",
    "send_frame",
    "sign_envelope",
    "spec_from_wire",
    "spec_to_wire",
    "validate_declared_path",
    "verify_envelope",
]
