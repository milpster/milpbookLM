"""Rootless parser child entry point; parser libraries are imported only here."""

from __future__ import annotations

import importlib.abc
import importlib.machinery
import json
import os
import sys
import uuid
from collections.abc import Sequence
from pathlib import Path
from types import ModuleType
from typing import Final, override

from milpbooklm_contracts.canonical_document import JsonValue

_BLOCKED_IMPORTS: Final = frozenset({"socket", "ssl", "http.client", "urllib.request", "ftplib"})


class _NoNetworkImports(importlib.abc.MetaPathFinder):
    """Reject network-capable modules before parser dependencies can load them."""

    @override
    def find_spec(
        self,
        fullname: str,
        path: Sequence[str] | None,
        target: ModuleType | None = None,
    ) -> importlib.machinery.ModuleSpec | None:
        """Raise for network modules and defer every other import."""
        if fullname in _BLOCKED_IMPORTS:
            raise ImportError(f"network module disabled in parser child: {fullname}")
        return None


def main() -> int:  # noqa: PLR0911
    """Read source bytes from stdin and write one bounded result envelope."""
    output = Path(sys.argv[1])
    source_version_id = uuid.UUID(sys.argv[2])
    media_type = sys.argv[3]
    if os.geteuid() == 0:
        return _write(output, {"state": "internal", "detail": "parser child must be rootless"})
    preloaded = sorted(module for module in _BLOCKED_IMPORTS if module in sys.modules)
    if preloaded:
        return _write(
            output,
            {"state": "internal", "detail": f"network modules preloaded: {','.join(preloaded)}"},
        )
    sys.meta_path.insert(0, _NoNetworkImports())
    from milpbooklm_adapters.parsers.pdf import (  # noqa: PLC0415
        PdfCorruptError,
        PdfEncryptedError,
        parse_pdf,
    )
    from milpbooklm_adapters.parsers.text import parse_text  # noqa: PLC0415

    data = sys.stdin.buffer.read()
    try:
        match media_type:
            case "text/plain":
                document = parse_text(source_version_id, data)
            case "application/pdf":
                document = parse_pdf(source_version_id, data)
            case _:
                return _write(output, {"state": "unsupported", "detail": "unsupported media type"})
    except UnicodeDecodeError:
        return _write(output, {"state": "corrupt", "detail": "text is not strict UTF-8"})
    except PdfEncryptedError:
        return _write(output, {"state": "encrypted", "detail": "PDF is encrypted"})
    except PdfCorruptError:
        return _write(output, {"state": "corrupt", "detail": "PDF is malformed"})
    except Exception as exc:
        return _write(output, {"state": "internal", "detail": type(exc).__name__})
    return _write(output, {"state": "succeeded", "document": document.to_json()})


def _write(output: Path, value: dict[str, JsonValue]) -> int:
    _ = output.write_text(
        json.dumps(value, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
