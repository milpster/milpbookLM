"""
Deterministic CSV canonical parser (stdlib csv module).

Dialect handling is bounded: the csv.Sniffer decision uses only the first
``_DIALECT_SAMPLE_BYTES`` of decoded text and falls back to the excel
dialect when the sample is inconclusive. Locator guarantees: one table per
file with row/column-numbered structural paths and ``row``/``col`` locator
extras — never character offsets, which quoting makes unstable.
"""

from __future__ import annotations

import csv
import io
import sys
import uuid
from typing import Final

from milpbooklm_contracts.canonical_document import (
    CanonicalDocument,
    CanonicalNode,
    JsonValue,
    NodeKind,
    ParserDescriptor,
    SourceLocator,
    canonical_document_id,
    canonical_node_id,
)

from .textcodec import decode_text

_PROFILE: Final = "csv-table-v1"
_MAX_ROWS: Final = 100_000
_MAX_FIELDS: Final = 4_096
_DIALECT_SAMPLE_BYTES: Final = 64 * 1024


class CsvTooLargeError(Exception):
    """The CSV exceeds the declared row or field limits."""


def parse_csv(source_version_id: uuid.UUID, data: bytes) -> CanonicalDocument:
    """Convert delimited text into a table-addressable canonical document."""
    text = decode_text(data)
    dialect, dialect_name, has_header = _detect_dialect(text)
    rows = _read_rows(text, dialect)
    parser = ParserDescriptor(
        identity="milpbooklm.csv",
        version="1",
        profile=_PROFILE,
        tool_versions=(
            f"python={sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        ),
    )
    document_id = canonical_document_id(source_version_id, parser)
    root_id = canonical_node_id(document_id, "document")
    table_id = canonical_node_id(document_id, "table:1")
    table_extra: dict[str, JsonValue] = {}
    if has_header and rows:
        table_extra = {"header": list[JsonValue](rows[0])}
    nodes = [
        CanonicalNode(
            node_id=root_id,
            kind=NodeKind.DOCUMENT,
            structural_identity="document",
            parent_id=None,
            child_order=0,
            text=None,
            locator=SourceLocator(path=("document",)),
        ),
        CanonicalNode(
            node_id=table_id,
            kind=NodeKind.TABLE,
            structural_identity="table:1",
            parent_id=root_id,
            child_order=1,
            text=None,
            locator=SourceLocator(path=("document", "table", "1"), extra_fields=table_extra),
        ),
    ]
    for row_number, row in enumerate(rows, start=1):
        row_identity = f"table:1:row:{row_number}"
        row_id = canonical_node_id(document_id, row_identity)
        row_path = ("document", "table", "1", "row", str(row_number))
        nodes.append(
            CanonicalNode(
                node_id=row_id,
                kind=NodeKind.ROW,
                structural_identity=row_identity,
                parent_id=table_id,
                child_order=row_number,
                text=None,
                locator=SourceLocator(path=row_path, extra_fields={"row": row_number}),
            )
        )
        for column, value in enumerate(row, start=1):
            cell_identity = f"{row_identity}:cell:{column}"
            nodes.append(
                CanonicalNode(
                    node_id=canonical_node_id(document_id, cell_identity),
                    kind=NodeKind.CELL,
                    structural_identity=cell_identity,
                    parent_id=row_id,
                    child_order=column,
                    text=value,
                    locator=SourceLocator(
                        path=row_path, extra_fields={"row": row_number, "col": column}
                    ),
                )
            )
    return CanonicalDocument(
        document_id=document_id,
        source_version_id=source_version_id,
        mime_type="text/csv",
        parser=parser,
        languages=(),
        metadata={"dialect": dialect_name, "has_header": has_header, "rows": len(rows)},
        root_node_ids=(root_id,),
        nodes=tuple(nodes),
    )


def _read_rows(text: str, dialect: csv.Dialect | type[csv.Dialect]) -> list[list[str]]:
    rows: list[list[str]] = []
    for row in csv.reader(io.StringIO(text, newline=""), dialect=dialect):
        if len(rows) >= _MAX_ROWS:
            raise CsvTooLargeError(f"CSV exceeds {_MAX_ROWS} row limit")
        if len(row) > _MAX_FIELDS:
            raise CsvTooLargeError(f"CSV row exceeds {_MAX_FIELDS} field limit")
        rows.append(row)
    if not rows:
        raise CsvTooLargeError("CSV contains no rows")
    return rows


def _detect_dialect(
    text: str,
) -> tuple[csv.Dialect | type[csv.Dialect], str, bool]:
    sample = text[:_DIALECT_SAMPLE_BYTES]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
        has_header = csv.Sniffer().has_header(sample)
    except csv.Error:
        return csv.excel, "excel-fallback", False
    return dialect, "sniffed", has_header
