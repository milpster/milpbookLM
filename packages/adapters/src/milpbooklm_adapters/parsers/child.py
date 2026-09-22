"""Rootless parser child entry point; parser libraries are imported only here."""

from __future__ import annotations

import importlib.abc
import importlib.machinery
import json
import os
import sys
import uuid
from collections.abc import Callable, Sequence
from csv import Error as CsvError
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Final, NoReturn, override

from milpbooklm_contracts.canonical_document import CanonicalDocument, JsonValue

_BLOCKED_IMPORTS: Final = frozenset({"socket", "ssl", "http.client", "urllib.request", "ftplib"})


@dataclass(frozen=True, slots=True)
class _ParseRequest:
    media_type: str
    source_version_id: uuid.UUID
    data: bytes
    context: dict[str, JsonValue]


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


class _DisabledNetworkModule(ModuleType):
    """Replace a loaded network module so any use fails loudly, not silently."""

    def __getattr__(self, name: str) -> NoReturn:
        raise ImportError(f"network module disabled in parser child: {self.__name__}")


def _install_network_guard() -> None:
    """
    Block network imports, keeping stdlib chains python-pptx needs inert.

    python-pptx imports xml.sax.saxutils, whose stdlib module-level imports
    pull urllib.request/http.client/socket/ssl. Preloading saxutils before
    the finder keeps that inert chain working; stubbing the five network
    modules in sys.modules afterwards makes any later use of them raise.
    """
    importlib.import_module("xml.sax.saxutils")

    sys.meta_path.insert(0, _NoNetworkImports())
    for name in _BLOCKED_IMPORTS:
        sys.modules[name] = _DisabledNetworkModule(name)


def main() -> int:
    """Read source bytes from stdin and write one bounded result envelope."""
    output = Path(sys.argv[1])
    source_version_id = uuid.UUID(sys.argv[2])
    media_type = sys.argv[3]
    context = json.loads(Path(sys.argv[4]).read_text(encoding="utf-8"))
    if os.geteuid() == 0:
        return _write(output, {"state": "internal", "detail": "parser child must be rootless"})
    preloaded = sorted(module for module in _BLOCKED_IMPORTS if module in sys.modules)
    if preloaded:
        return _write(
            output,
            {"state": "internal", "detail": f"network modules preloaded: {','.join(preloaded)}"},
        )
    _install_network_guard()
    return _write(
        output,
        _parse(_ParseRequest(media_type, source_version_id, sys.stdin.buffer.read(), context)),
    )


def _parse(request: _ParseRequest) -> dict[str, JsonValue]:  # noqa: PLR0911
    """Dispatch one payload to its parser and map typed failures to states."""
    from milpbooklm_adapters.parsers.csv_parser import CsvTooLargeError  # noqa: PLC0415
    from milpbooklm_adapters.parsers.html import HtmlCorruptError  # noqa: PLC0415
    from milpbooklm_adapters.parsers.office import (  # noqa: PLC0415
        OfficeCorruptError,
        OfficePolicyError,
        OfficeTooLargeError,
    )
    from milpbooklm_adapters.parsers.pdf import (  # noqa: PLC0415
        PdfCorruptError,
        PdfEncryptedError,
    )

    parse = _load_parsers().get(request.media_type)
    if parse is None and request.media_type != "text/html":
        return {"state": "unsupported", "detail": "unsupported media type"}
    try:
        document = _parse_document(request, parse)
    except UnicodeDecodeError:
        return {"state": "corrupt", "detail": "text is not decodable UTF-8/UTF-16"}
    except CsvError:
        return {"state": "corrupt", "detail": "CSV structure cannot be parsed"}
    except PdfEncryptedError:
        return {"state": "encrypted", "detail": "PDF is encrypted"}
    except PdfCorruptError:
        return {"state": "corrupt", "detail": "PDF is malformed"}
    except OfficePolicyError as exc:
        return {"state": "policy_blocked", "detail": str(exc)}
    except (OfficeTooLargeError, CsvTooLargeError) as exc:
        return {"state": "too_large", "detail": str(exc)}
    except (OfficeCorruptError, HtmlCorruptError):
        return {"state": "corrupt", "detail": "document is malformed"}
    except Exception as exc:
        return {"state": "internal", "detail": type(exc).__name__}
    return {"state": "succeeded", "document": document.to_json()}


def _parse_document(
    request: _ParseRequest,
    parse: Callable[[uuid.UUID, bytes], CanonicalDocument] | None,
) -> CanonicalDocument:
    if request.media_type != "text/html":
        if parse is None:
            raise AssertionError("parser dispatch lost selected parser")
        return parse(request.source_version_id, request.data)
    from milpbooklm_adapters.parsers.html import parse_html  # noqa: PLC0415
    from milpbooklm_adapters.parsers.parser_context import WebLocatorContext  # noqa: PLC0415

    canonical_url = request.context.get("canonical_url")
    captured_at = request.context.get("captured_at")
    web_locator = (
        WebLocatorContext(canonical_url, captured_at)
        if isinstance(canonical_url, str) and isinstance(captured_at, str)
        else None
    )
    return parse_html(request.source_version_id, request.data, web_locator)


def _load_parsers() -> dict[str, Callable[[uuid.UUID, bytes], CanonicalDocument]]:
    """Import every parser behind the installed network guard and index them."""
    from milpbooklm_adapters.parsers.csv_parser import parse_csv  # noqa: PLC0415
    from milpbooklm_adapters.parsers.docx_parser import parse_docx  # noqa: PLC0415
    from milpbooklm_adapters.parsers.epub import parse_epub  # noqa: PLC0415
    from milpbooklm_adapters.parsers.markdown import parse_markdown  # noqa: PLC0415
    from milpbooklm_adapters.parsers.pdf import parse_pdf  # noqa: PLC0415
    from milpbooklm_adapters.parsers.pptx_parser import parse_pptx  # noqa: PLC0415
    from milpbooklm_adapters.parsers.text import parse_text  # noqa: PLC0415
    from milpbooklm_adapters.parsers.xlsx import parse_xlsx  # noqa: PLC0415

    return {
        "text/plain": parse_text,
        "text/markdown": parse_markdown,
        "text/csv": parse_csv,
        "application/pdf": parse_pdf,
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": parse_xlsx,
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document": parse_docx,
        "application/vnd.openxmlformats-officedocument.presentationml.presentation": parse_pptx,
        "application/epub+zip": parse_epub,
    }


def _write(output: Path, value: dict[str, JsonValue]) -> int:
    _ = output.write_text(
        json.dumps(value, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
