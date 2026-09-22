from __future__ import annotations

import os
from pathlib import Path

import pytest
from milpbooklm_adapters.execution.images import ImageVerificationError, RuntimeImageStore


def _runtime_tree(root: Path) -> Path:
    tree = root / "runtime"
    executable = tree / "usr" / "bin" / "tool"
    executable.parent.mkdir(parents=True)
    executable.write_bytes(b"#!/bin/sh\nexit 0\n")
    executable.chmod(0o755)
    return tree


def test_image_install_is_content_addressed_and_preserves_executable_mode(tmp_path: Path) -> None:
    tree = _runtime_tree(tmp_path)
    store = RuntimeImageStore(tmp_path / "images")

    first = store.install(tree, name="micro", sbom={"packages": []})
    second = store.install(tree, name="micro", sbom={"packages": []})
    image = store.verify(first)

    assert first == second
    assert image.digest == first
    assert os.access(image.rootfs / "usr" / "bin" / "tool", os.X_OK)
    assert store.read_sbom(first) == {"packages": []}


def test_image_verification_rejects_tampering_and_unmanifested_files(tmp_path: Path) -> None:
    store = RuntimeImageStore(tmp_path / "images")
    digest = store.install(_runtime_tree(tmp_path), name="micro", sbom={"packages": []})
    image = store.verify(digest)
    executable = image.rootfs / "usr" / "bin" / "tool"
    executable.chmod(0o755)
    executable.write_bytes(b"tampered")

    with pytest.raises(ImageVerificationError):
        store.verify(digest)

    executable.write_bytes(b"#!/bin/sh\nexit 0\n")
    (image.rootfs / "extra.txt").write_text("not manifested")
    with pytest.raises(ImageVerificationError):
        store.verify(digest)


def test_image_install_rejects_symlink(tmp_path: Path) -> None:
    tree = _runtime_tree(tmp_path)
    (tree / "usr" / "bin" / "alias").symlink_to("tool")

    with pytest.raises(ImageVerificationError):
        RuntimeImageStore(tmp_path / "images").install(
            tree,
            name="unsafe",
            sbom={"packages": []},
        )
