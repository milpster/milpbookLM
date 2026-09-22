"""
Sandbox output collection: validate → quarantine → blob → publish (EXE-01).

Only declared paths under the writable output mount are collected; the
collector rejects path traversal, symlinks and special files, enforces
per-file and total output quotas, determines content type independently of
filename (byte-magic sniffing through the house sniffer), quarantines the
bytes, and hands off to the crash-consistent blob protocol. Publication is
a SEPARATE step that runs only after authorization revalidation — collected
bytes are never auto-trusted (T21 quarantine discipline, T28 download
precedent).
"""

from __future__ import annotations

import hashlib
import os
import re
import stat
import uuid
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path, PurePosixPath
from typing import Final

from milpbooklm_application.blob_store import BlobStore
from milpbooklm_application.execution import (
    DeclaredOutput,
    ExecutionLimits,
    ExecutionRefusalCode,
    ExecutionRefusedError,
    ProducedOutput,
)

from milpbooklm_adapters.parsers.sniffing import SNIFF_SAMPLE_BYTES, sniff_media_type

_CHUNK: Final = 1024 * 1024
_EXECUTION_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


@dataclass(frozen=True, slots=True)
class _QuarantineRecord:
    path: Path
    device: int
    inode: int
    declared_path: str
    content_sha256: str
    size_bytes: int


def validate_declared_path(relative: str) -> PurePosixPath:
    """
    Accept only safe relative POSIX paths (typed refusal otherwise).

    Absolute paths, ``..`` components, empty segments and backslashes are
    refused — the same class of check the input side applies to broker
    staging paths.
    """
    pure = PurePosixPath(relative)
    if pure.is_absolute() or not pure.parts or "\\" in relative:
        raise ExecutionRefusedError(
            ExecutionRefusalCode.INVALID_SPEC,
            f"declared output path is not safe-relative: {relative!r}",
        )
    if any(part in ("..", "") for part in pure.parts):
        raise ExecutionRefusedError(
            ExecutionRefusalCode.INVALID_SPEC,
            f"declared output path has unsafe components: {relative!r}",
        )
    return pure


class OutputCollector:
    """Collect, validate and quarantine one execution's declared outputs."""

    def __init__(self, quarantine_root: Path) -> None:
        """Bind the quarantine root (per-execution directories below it)."""
        self._root = quarantine_root
        self._root.mkdir(parents=True, exist_ok=True)
        self._root.chmod(0o700)
        self._records: dict[Path, _QuarantineRecord] = {}
        self._directories: dict[Path, tuple[int, int]] = {}

    def collect(
        self,
        outputs_dir: Path,
        declared: tuple[DeclaredOutput, ...],
        limits: ExecutionLimits,
        execution_id: str,
    ) -> tuple[tuple[ProducedOutput, ...], int]:
        """
        Collect declared outputs into quarantine; return (outputs, undeclared count).

        Raises ExecutionRefusedError(OUTPUT_POLICY_VIOLATION) on traversal,
        symlink/special-file tricks, per-file or total quota violations, or
        a missing/unidentifiable declared output. The quarantine directory
        is removed again on refusal.
        """
        if _EXECUTION_ID.fullmatch(execution_id) is None:
            raise ExecutionRefusedError(
                ExecutionRefusalCode.OUTPUT_POLICY_VIOLATION,
                "execution quarantine identity is invalid",
            )
        _validate_output_tree(outputs_dir, declared)
        quarantine_dir = self._root / f"exec-{execution_id}"
        quarantine_dir.mkdir(mode=0o700)
        directory_info = quarantine_dir.stat(follow_symlinks=False)
        self._directories[quarantine_dir] = (directory_info.st_dev, directory_info.st_ino)
        collected: list[ProducedOutput] = []
        try:
            total = 0
            for entry in declared:
                pure = validate_declared_path(entry.relative_path)
                source = outputs_dir / pure
                digest, size, media = _validate_and_hash(source)
                if size > min(entry.max_bytes, limits.max_output_file_bytes):
                    raise ExecutionRefusedError(
                        ExecutionRefusalCode.OUTPUT_POLICY_VIOLATION,
                        f"output {entry.relative_path} exceeds its declared size cap",
                    )
                total += size
                if total > limits.max_total_output_bytes:
                    raise ExecutionRefusedError(
                        ExecutionRefusalCode.OUTPUT_POLICY_VIOLATION,
                        "declared outputs exceed the total output quota",
                    )
                target = quarantine_dir / f"{len(collected):03d}-{pure.name}"
                _copy_quarantine(source, target)
                output = ProducedOutput(
                    declared_path=entry.relative_path,
                    content_sha256=digest,
                    size_bytes=size,
                    sniffed_media=media,
                    quarantine_path=str(target),
                )
                info = target.stat(follow_symlinks=False)
                self._records[target] = _QuarantineRecord(
                    path=target,
                    device=info.st_dev,
                    inode=info.st_ino,
                    declared_path=output.declared_path,
                    content_sha256=output.content_sha256,
                    size_bytes=output.size_bytes,
                )
                collected.append(output)
            return tuple(collected), 0
        except ExecutionRefusedError:
            self._discard_directory(quarantine_dir)
            raise

    def publish(
        self,
        outputs: tuple[ProducedOutput, ...],
        *,
        authorize: Callable[[ProducedOutput], bool],
        blobs: BlobStore,
        referrer_kind: str,
        referrer_id: uuid.UUID,
    ) -> tuple[ProducedOutput, ...]:
        """
        Publish quarantined outputs through the blob protocol AFTER authz revalidation.

        The authorization predicate is re-evaluated per output at publication
        time; any denial refuses the whole publication (nothing is written)
        with a typed PUBLISH_AUTHZ_DENIED refusal.
        """
        records = tuple(self._record_for(output) for output in outputs)
        for output in outputs:
            if not authorize(output):
                raise ExecutionRefusedError(
                    ExecutionRefusalCode.PUBLISH_AUTHZ_DENIED,
                    f"publication of {output.declared_path} was not re-authorized",
                )
        published: list[ProducedOutput] = []
        for output, record in zip(outputs, records, strict=True):
            descriptor = _open_record(record)
            with os.fdopen(descriptor, "rb") as handle:
                blob = blobs.put(
                    (chunk for chunk in iter(lambda: handle.read(_CHUNK), b"")),
                    content_type=output.sniffed_media,
                    referrer_kind=referrer_kind,
                    referrer_id=referrer_id,
                )
            published.append(replace(output, blob_id=blob.id))
        return tuple(published)

    def discard(self, outputs: tuple[ProducedOutput, ...]) -> None:
        """Remove the quarantine directories of one execution."""
        records = tuple(self._record_for(output) for output in outputs)
        parents = {record.path.parent for record in records}
        for record in records:
            record.path.unlink()
            self._records.pop(record.path)
        for parent in parents:
            self._remove_empty_directory(parent)

    def _record_for(self, output: ProducedOutput) -> _QuarantineRecord:
        path = Path(output.quarantine_path)
        record = self._records.get(path)
        if record is None or (
            record.declared_path != output.declared_path
            or record.content_sha256 != output.content_sha256
            or record.size_bytes != output.size_bytes
        ):
            raise ExecutionRefusedError(
                ExecutionRefusalCode.OUTPUT_POLICY_VIOLATION,
                "quarantine identity is not broker-owned",
            )
        descriptor = _open_record(record)
        os.close(descriptor)
        return record

    def _discard_directory(self, directory: Path) -> None:
        for path in tuple(self._records):
            if path.parent == directory:
                path.unlink(missing_ok=True)
                self._records.pop(path)
        self._remove_empty_directory(directory)

    def _remove_empty_directory(self, directory: Path) -> None:
        expected = self._directories.get(directory)
        if expected is None:
            raise ExecutionRefusedError(
                ExecutionRefusalCode.OUTPUT_POLICY_VIOLATION,
                "quarantine directory identity is not broker-owned",
            )
        info = directory.stat(follow_symlinks=False)
        if (info.st_dev, info.st_ino) != expected:
            raise ExecutionRefusedError(
                ExecutionRefusalCode.OUTPUT_POLICY_VIOLATION,
                "quarantine directory identity changed",
            )
        directory.rmdir()
        self._directories.pop(directory)


def _validate_output_tree(outputs_dir: Path, declared: tuple[DeclaredOutput, ...]) -> None:
    declared_paths = tuple(validate_declared_path(entry.relative_path) for entry in declared)
    if len(set(declared_paths)) != len(declared_paths):
        raise ExecutionRefusedError(
            ExecutionRefusalCode.INVALID_SPEC,
            "declared output paths must be unique",
        )
    allowed: set[PurePosixPath] = set(declared_paths)
    for path in declared_paths:
        allowed.update(path.parents[:-1])
    for child in outputs_dir.rglob("*"):
        relative = PurePosixPath(child.relative_to(outputs_dir).as_posix())
        mode = child.lstat().st_mode
        if relative not in allowed:
            raise ExecutionRefusedError(
                ExecutionRefusalCode.OUTPUT_POLICY_VIOLATION,
                f"undeclared output is forbidden: {relative.as_posix()}",
            )
        if relative not in declared_paths and not stat.S_ISDIR(mode):
            raise ExecutionRefusedError(
                ExecutionRefusalCode.OUTPUT_POLICY_VIOLATION,
                "declared output parent is not a directory",
            )


def _open_record(record: _QuarantineRecord) -> int:
    try:
        descriptor = os.open(record.path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    except OSError as exc:
        raise ExecutionRefusedError(
            ExecutionRefusalCode.OUTPUT_POLICY_VIOLATION,
            "quarantine output is missing or unsafe",
        ) from exc
    info = os.fstat(descriptor)
    if not stat.S_ISREG(info.st_mode) or (info.st_dev, info.st_ino) != (
        record.device,
        record.inode,
    ):
        os.close(descriptor)
        raise ExecutionRefusedError(
            ExecutionRefusalCode.OUTPUT_POLICY_VIOLATION,
            "quarantine output identity changed",
        )
    return descriptor


def _validate_and_hash(source: Path) -> tuple[str, int, str]:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(source, flags)
    except OSError as exc:
        raise ExecutionRefusedError(
            ExecutionRefusalCode.OUTPUT_POLICY_VIOLATION,
            f"declared output is missing or unsafe: {exc.__class__.__name__}",
        ) from exc
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            raise ExecutionRefusedError(
                ExecutionRefusalCode.OUTPUT_POLICY_VIOLATION,
                "declared output is not a regular file",
            )
        digest = hashlib.sha256()
        size = 0
        prefix = bytearray()
        while chunk := os.read(fd, _CHUNK):
            digest.update(chunk)
            size += len(chunk)
            if len(prefix) < SNIFF_SAMPLE_BYTES:
                prefix.extend(chunk[: SNIFF_SAMPLE_BYTES - len(prefix)])
    finally:
        os.close(fd)
    media = sniff_media_type(bytes(prefix))
    if media is None:
        raise ExecutionRefusedError(
            ExecutionRefusalCode.OUTPUT_POLICY_VIOLATION,
            "output content type is not identifiable from its bytes",
        )
    return digest.hexdigest(), size, media.value


def _copy_quarantine(source: Path, target: Path) -> None:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(source, flags)
    try:
        with target.open("xb") as writer:
            while chunk := os.read(fd, _CHUNK):
                writer.write(chunk)
            writer.flush()
            os.fsync(writer.fileno())
    finally:
        os.close(fd)
