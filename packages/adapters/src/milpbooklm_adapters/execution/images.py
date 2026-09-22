"""
Content-addressed runtime image store with an SBOM slot (EXE-01, guide/12).

Images are content-addressed, versioned and administrator-installed; no
package installation happens during a run. Layout on disk::

    <root>/<sha256-hex>/manifest.json   # schema, name, created, rootfs digest list
    <root>/<sha256-hex>/sbom.json       # the software-bill manifest slot
    <root>/<sha256-hex>/rootfs/...      # the read-only runtime tree

The image id is ``sha256:`` + the SHA-256 of the canonical manifest JSON
(the manifest never self-references its own digest), and the manifest pins
every rootfs file by relative path, size and digest, so :meth:`verify`
re-proves the whole tree byte-for-byte before any execution mounts it. A
symlink or special file anywhere in the tree is rejected at install AND at
verify time (the bwrap 0.11.0 symlink-traversal mitigation: mount sources
are broker-controlled and provably symlink-free).

ADMIN INSTALL FLOW (deferred to deployment, T8-class; documented here as
the plan requires): an administrator stages a curated runtime tree (Python
plus the reviewed analysis stack) and its SBOM document on the host, then
runs ``RuntimeImageStore.install`` (or a future installer CLI wrapping it)
as the execution-service account. The installer computes the digest,
writes manifest+SBOM atomically and publishes the digest to the worker-core
configuration. No download or package installation happens at run time.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import uuid
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Final, TypedDict

from milpbooklm_application.execution import ExecutionRefusalCode, ExecutionRefusedError

_CHUNK: Final = 1024 * 1024
_DIGEST = re.compile(r"^sha256:([0-9a-f]{64})$")
MANIFEST_NAME: Final = "manifest.json"
SBOM_NAME: Final = "sbom.json"
ROOTFS_NAME: Final = "rootfs"


class ImageVerificationError(RuntimeError):
    """An image failed verification (missing, tampered, or unsafe content)."""


class _ImageFileRecord(TypedDict):
    path: str
    sha256: str
    size: int
    mode: int


class _ImageManifest(TypedDict):
    schema: int
    name: str
    sbom_sha256: str
    directories: list[str]
    rootfs: list[_ImageFileRecord]


@dataclass(frozen=True, slots=True)
class RuntimeImage:
    """A verified, resolved image: digest, rootfs path and parsed manifest."""

    digest: str
    rootfs: Path
    manifest: _ImageManifest


class RuntimeImageStore:
    """The content-addressed image store below one root directory."""

    def __init__(self, root: Path) -> None:
        """Bind (and create) the store root."""
        self._root = root
        self._root.mkdir(parents=True, exist_ok=True)

    def install(self, tree: Path, *, name: str, sbom: dict[str, object]) -> str:
        """
        Install a staged tree as a new immutable image; return its digest.

        The tree is copied into a staging directory (rejecting symlinks and
        special files), the manifest is built from the copied bytes, and the
        staging directory is atomically renamed to its digest-named final
        directory. An image with the same digest already installed is a no-op
        (content addressing).
        """
        if not tree.is_dir():
            raise ImageVerificationError("image tree is not a directory")
        entries, directories = _walk_tree(tree)
        staging = self._root / f".staging-{uuid.uuid4().hex}"
        staging.mkdir()
        try:
            copied_root = staging / ROOTFS_NAME
            copied_root.mkdir()
            file_records: list[_ImageFileRecord] = []
            for relative, source in entries:
                target = copied_root / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                digest, size, mode = _copy_file(source, target)
                file_records.append(
                    {"path": relative, "sha256": digest, "size": size, "mode": mode}
                )
            sbom_bytes = _canonical(sbom)
            manifest: _ImageManifest = {
                "schema": 1,
                "name": name,
                "sbom_sha256": hashlib.sha256(sbom_bytes).hexdigest(),
                "directories": list(directories),
                "rootfs": sorted(file_records, key=lambda record: str(record["path"])),
            }
            digest_hex = hashlib.sha256(_canonical(manifest)).hexdigest()
            digest = f"sha256:{digest_hex}"
            _write_fsynced(staging / MANIFEST_NAME, _canonical(manifest))
            _write_fsynced(staging / SBOM_NAME, sbom_bytes)
            final = self._root / digest_hex
            if final.exists():
                shutil.rmtree(staging)
            else:
                staging.rename(final)
                _fsync_directory(self._root)
            return digest
        finally:
            if staging.exists():
                shutil.rmtree(staging, ignore_errors=True)

    def verify(self, digest: str) -> RuntimeImage:
        """
        Re-prove one image end-to-end; return the resolved runtime image.

        Checks the digest shape, the manifest hash chain, every rootfs file
        digest/size, and the absence of symlinks/special files. Any failure
        raises :class:`ImageVerificationError` and the image is never mounted.
        """
        digest_hex = _digest_hex(digest)
        image_dir = self._root / digest_hex
        manifest_path = image_dir / MANIFEST_NAME
        try:
            manifest_raw = manifest_path.read_bytes()
        except OSError as exc:
            raise ImageVerificationError(f"image {digest} manifest unreadable") from exc
        manifest = _parse_manifest(manifest_raw)
        recomputed = f"sha256:{hashlib.sha256(_canonical(manifest)).hexdigest()}"
        if recomputed != digest:
            raise ImageVerificationError("manifest digest mismatch")
        rootfs = image_dir / ROOTFS_NAME
        if not rootfs.is_dir():
            raise ImageVerificationError("rootfs directory missing")
        records = manifest["rootfs"]
        expected_files: set[str] = set()
        for record in records:
            relative = str(record["path"])
            expected_files.add(relative)
            target = rootfs / relative
            digest_found, size_found = _hash_file_no_follow(target)
            mode_found = stat.S_IMODE(target.stat(follow_symlinks=False).st_mode)
            if (
                digest_found != record["sha256"]
                or size_found != record["size"]
                or mode_found != record["mode"]
            ):
                raise ImageVerificationError(f"rootfs file {relative} does not match its manifest")
        actual_files: set[str] = set()
        actual_directories: set[str] = set()
        for child in rootfs.rglob("*"):
            _reject_unsafe(child)
            relative = child.relative_to(rootfs).as_posix()
            if child.is_dir():
                actual_directories.add(relative)
            else:
                actual_files.add(relative)
        if actual_files != expected_files or actual_directories != set(manifest["directories"]):
            raise ImageVerificationError("rootfs inventory does not match its manifest")
        return RuntimeImage(digest=digest, rootfs=rootfs, manifest=manifest)

    def read_sbom(self, digest: str) -> dict[str, object]:
        """Return the parsed SBOM document pinned beside the image."""
        image_dir = self._root / _digest_hex(digest)
        try:
            sbom_raw = (image_dir / SBOM_NAME).read_bytes()
            manifest = _parse_manifest((image_dir / MANIFEST_NAME).read_bytes())
            if hashlib.sha256(sbom_raw).hexdigest() != manifest["sbom_sha256"]:
                raise ImageVerificationError("sbom digest mismatch")
            sbom: object = json.loads(sbom_raw)
        except (OSError, json.JSONDecodeError) as exc:
            raise ImageVerificationError(f"image {digest} sbom unreadable") from exc
        if not isinstance(sbom, dict):
            raise ImageVerificationError("sbom is not an object")
        return sbom


def _parse_manifest(raw: bytes) -> _ImageManifest:
    try:
        payload: object = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ImageVerificationError("manifest is not valid JSON") from exc
    if not isinstance(payload, dict) or set(payload) != {
        "schema",
        "name",
        "sbom_sha256",
        "directories",
        "rootfs",
    }:
        raise ImageVerificationError("manifest shape is invalid")
    schema = payload["schema"]
    name = payload["name"]
    sbom_sha256 = payload["sbom_sha256"]
    directories = payload["directories"]
    rootfs = payload["rootfs"]
    if schema != 1 or not isinstance(name, str) or not name:
        raise ImageVerificationError("manifest identity is invalid")
    if not isinstance(sbom_sha256, str) or re.fullmatch(r"[0-9a-f]{64}", sbom_sha256) is None:
        raise ImageVerificationError("manifest sbom digest is invalid")
    if not isinstance(directories, list) or not all(
        isinstance(entry, str) and _safe_relative(entry) for entry in directories
    ):
        raise ImageVerificationError("manifest directories are invalid")
    if len(set(directories)) != len(directories) or not isinstance(rootfs, list):
        raise ImageVerificationError("manifest inventory is invalid")
    records = [_parse_file_record(record) for record in rootfs]
    paths = [record["path"] for record in records]
    if len(set(paths)) != len(paths):
        raise ImageVerificationError("manifest contains duplicate file paths")
    return {
        "schema": 1,
        "name": name,
        "sbom_sha256": sbom_sha256,
        "directories": directories,
        "rootfs": records,
    }


def _parse_file_record(payload: object) -> _ImageFileRecord:
    if not isinstance(payload, dict) or set(payload) != {"path", "sha256", "size", "mode"}:
        raise ImageVerificationError("rootfs record shape is invalid")
    path = payload["path"]
    digest = payload["sha256"]
    size = payload["size"]
    mode = payload["mode"]
    if not isinstance(path, str) or not _safe_relative(path):
        raise ImageVerificationError("rootfs record path is invalid")
    if not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
        raise ImageVerificationError("rootfs record digest is invalid")
    if isinstance(size, bool) or not isinstance(size, int) or size < 0:
        raise ImageVerificationError("rootfs record size is invalid")
    if isinstance(mode, bool) or mode not in (0o444, 0o555):
        raise ImageVerificationError("rootfs record mode is invalid")
    return {"path": path, "sha256": digest, "size": size, "mode": mode}


def _safe_relative(value: str) -> bool:
    path = PurePosixPath(value)
    return bool(path.parts) and not path.is_absolute() and ".." not in path.parts


def _digest_hex(digest: str) -> str:
    match = _DIGEST.fullmatch(digest)
    if match is None:
        raise ExecutionRefusedError(
            ExecutionRefusalCode.UNKNOWN_IMAGE, "image digest is not sha256-hex"
        )
    return match.group(1)


def _canonical(payload: object) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def _write_fsynced(path: Path, payload: bytes) -> None:
    with path.open("xb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _walk_tree(tree: Path) -> tuple[list[tuple[str, Path]], tuple[str, ...]]:
    entries: list[tuple[str, Path]] = []
    directories: list[str] = []
    for child in sorted(tree.rglob("*")):
        _reject_unsafe(child)
        if child.is_file():
            entries.append((child.relative_to(tree).as_posix(), child))
        else:
            directories.append(child.relative_to(tree).as_posix())
    return entries, tuple(directories)


def _reject_unsafe(path: Path) -> None:
    mode = path.lstat().st_mode
    if stat.S_ISLNK(mode):
        raise ImageVerificationError(f"symlink in image tree is rejected: {path.name}")
    if not (stat.S_ISDIR(mode) or stat.S_ISREG(mode)):
        raise ImageVerificationError(f"special file in image tree is rejected: {path.name}")


def _copy_file(source: Path, target: Path) -> tuple[str, int, int]:
    digest = hashlib.sha256()
    size = 0
    source_fd = os.open(source, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        source_info = os.fstat(source_fd)
        if not stat.S_ISREG(source_info.st_mode):
            raise ImageVerificationError(f"image source is not regular: {source.name}")
        mode = 0o555 if source_info.st_mode & 0o111 else 0o444
        with target.open("xb") as writer:
            while chunk := os.read(source_fd, _CHUNK):
                digest.update(chunk)
                size += len(chunk)
                writer.write(chunk)
            writer.flush()
            os.fsync(writer.fileno())
        target.chmod(mode)
        return digest.hexdigest(), size, mode
    finally:
        os.close(source_fd)


def _hash_file_no_follow(target: Path) -> tuple[str, int]:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(target, flags)
    except OSError as exc:
        raise ImageVerificationError(f"rootfs file unopenable: {target.name}") from exc
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise ImageVerificationError(f"rootfs entry is not a regular file: {target.name}")
        digest = hashlib.sha256()
        size = 0
        while chunk := os.read(fd, _CHUNK):
            digest.update(chunk)
            size += len(chunk)
        return digest.hexdigest(), size
    finally:
        os.close(fd)
