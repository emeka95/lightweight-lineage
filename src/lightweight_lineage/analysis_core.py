"""Shared parser, graph-resolution, and lineage extraction primitives."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable
from urllib.parse import urlsplit

from sqlfluff.core.parser import BaseSegment

from lightweight_lineage.graph import (
    Diagnostic,
    LineageEdge,
    LineageObject,
)
from lightweight_lineage.options import ExplicitMapping
from lightweight_lineage.scanner import ScanDeadline

_DATA_MODIFICATION_TYPES = (
    "insert_statement",
    "update_statement",
    "merge_statement",
)


@dataclass(frozen=True, slots=True)
class _ParsedFile:
    path: str
    tree: BaseSegment


@dataclass(frozen=True, slots=True)
class _Reference:
    name: str
    file: str
    line: int
    column: int
    type_hint: str = "relation"


@dataclass(frozen=True, slots=True)
class _Resolution:
    node: LineageObject
    status: str


@dataclass(frozen=True, slots=True)
class _ProcedureSpan:
    id: str
    start: int
    stop: int


def _identifier_parts(value: str) -> tuple[str, ...]:
    parts: list[str] = []
    current: list[str] = []
    quote: str | None = None
    index = 0
    while index < len(value):
        character = value[index]
        if quote is not None:
            closing = "]" if quote == "[" else quote
            if character == closing:
                if index + 1 < len(value) and value[index + 1] == closing:
                    current.append(closing)
                    index += 2
                    continue
                quote = None
            else:
                current.append(character)
        elif character in ("[", '"'):
            quote = character
        elif character == ".":
            part = "".join(current).strip()
            if part:
                parts.append(part)
            current.clear()
        else:
            current.append(character)
        index += 1

    part = "".join(current).strip()
    if part:
        parts.append(part)
    return tuple(parts)


def _normalized_name(value: str) -> str:
    return ".".join(part.casefold() for part in _identifier_parts(value))


def _is_temporary(value: str) -> bool:
    parts = _identifier_parts(value)
    return bool(parts) and (parts[-1].startswith("#") or parts[-1].startswith("@"))


def _location(segment: BaseSegment) -> tuple[int, int]:
    if segment.pos_marker is None:
        return 1, 1
    return segment.pos_marker.source_position()


def _direct_children(segment: BaseSegment, *types: str) -> list[BaseSegment]:
    return [child for child in segment.segments if child.get_type() in types]


def _descendants(segment: BaseSegment, *types: str) -> Iterable[BaseSegment]:
    return segment.recursive_crawl(*types)


def _first_direct(segment: BaseSegment, *types: str) -> BaseSegment | None:
    return next(iter(_direct_children(segment, *types)), None)


def _segment_offset(segment: BaseSegment) -> tuple[int, int] | None:
    if segment.pos_marker is None:
        return None
    source_slice = segment.pos_marker.templated_slice
    return source_slice.start, source_slice.stop


def _literal_value(raw: str) -> str:
    value = raw.strip()
    if value[:1].casefold() == "n" and value[1:2] == "'":
        value = value[1:]
    if len(value) >= 2 and value[0] == "'" and value[-1] == "'":
        return value[1:-1].replace("''", "'")
    return value


class _GraphBuilder:
    def __init__(
        self,
        mappings: tuple[ExplicitMapping, ...],
        deadline: ScanDeadline,
    ) -> None:
        self.deadline = deadline
        self.objects: dict[str, LineageObject] = {}
        self.edges: dict[tuple[str, str, str, str, str | None], LineageEdge] = {}
        self.diagnostics: dict[tuple[str, str, str, int | None, str], Diagnostic] = {}
        self.declarations: dict[str, list[str]] = {}
        self.synonyms: dict[str, list[str]] = {}
        self.mappings: dict[str, list[str]] = {}
        for mapping in mappings:
            alias = _normalized_name(mapping.alias)
            target = mapping.target.strip()
            normalized_target = _normalized_name(target)
            if normalized_target not in self.mappings.setdefault(alias, []):
                self.mappings[alias].append(target)

    def add_diagnostic(
        self,
        severity: str,
        code: str,
        file: str,
        message: str,
        line: int | None = None,
        column: int | None = None,
    ) -> None:
        self.deadline.check()
        key = severity, code, file, line, message
        self.diagnostics.setdefault(
            key,
            Diagnostic(severity, code, file, message, line, column),
        )

    def add_object(
        self,
        object_type: str,
        name: str,
        status: str,
        file: str | None = None,
        parse_status: str | None = None,
    ) -> LineageObject:
        self.deadline.check()
        normalized = _normalized_name(name) or name.casefold()
        if status == "unknown":
            id_type = "unknown"
        elif object_type == "stored_procedure":
            id_type = "procedure"
        else:
            id_type = object_type
        object_id = f"{id_type}:{normalized}"
        node = self.objects.get(object_id)
        if node is None:
            node = LineageObject(
                id=object_id,
                type=object_type,
                name=".".join(_identifier_parts(name)) or name,
                status=status,
                source_file=file,
                parse_status=parse_status,
            )
            self.objects[object_id] = node
        elif status == "declared":
            node.status = status
            if file is not None and node.source_file is None:
                node.source_file = file
            if parse_status is not None:
                node.parse_status = parse_status
        if file is not None and node.status == "unknown":
            node.referenced_in.add(file)
        return node

    def add_declaration(
        self,
        object_type: str,
        name: str,
        file: str,
    ) -> LineageObject | None:
        if not name or _is_temporary(name):
            return None
        node = self.add_object(
            object_type,
            name,
            status="declared",
            file=file,
            parse_status="parsed",
        )
        key = _normalized_name(name)
        declaration_ids = self.declarations.setdefault(key, [])
        if node.id not in declaration_ids:
            declaration_ids.append(node.id)
        return node

    def add_edge(
        self,
        source: LineageObject,
        target: LineageObject,
        kind: str,
        status: str,
        file: str,
        line: int,
        column: int,
        via_procedure: str | None = None,
    ) -> None:
        self.deadline.check()
        key = source.id, target.id, kind, status, via_procedure
        existing = self.edges.get(key)
        if existing is None:
            self.edges[key] = LineageEdge(
                source.id,
                target.id,
                kind,
                status,
                file,
                line,
                column,
                via_procedure,
            )
        elif (line, column, file) < (
            existing.line,
            existing.column,
            existing.evidence_file,
        ):
            existing.evidence_file = file
            existing.line = line
            existing.column = column

    def declared_resolutions(
        self,
        name: str,
        file: str,
        line: int,
        column: int,
    ) -> list[_Resolution]:
        identifiers = self.declarations.get(_normalized_name(name), [])
        nodes = [self.objects[identifier] for identifier in identifiers]
        if len(nodes) > 1:
            self.add_diagnostic(
                "warning",
                "ambiguous_sql_declaration",
                file,
                f"Reference {name!r} matches multiple SQL object declarations.",
                line,
                column,
            )
            return [_Resolution(node, "ambiguous") for node in nodes]
        return [_Resolution(node, "resolved") for node in nodes]

    def _create_external_object(
        self,
        name: str,
        file: str,
        line: int,
    ) -> LineageObject:
        parts = _identifier_parts(name)
        connection_name = parts[0]
        connection = self.add_object(
            "external_connection",
            connection_name,
            status="discovered",
            file=file,
        )
        remote = self.add_object(
            "external_object",
            name,
            status="discovered",
            file=file,
        )
        self.add_edge(
            connection,
            remote,
            "connection",
            "confirmed",
            file,
            line,
            1,
        )
        return remote

    def _create_file_object(
        self,
        name: str,
        file: str,
        line: int,
        column: int,
    ) -> LineageObject:
        data_file = self.add_object("data_file", name, status="discovered", file=file)
        location = urlsplit(name)
        if location.scheme.casefold() == "s3" and location.netloc:
            connection = self.add_object(
                "external_connection",
                f"s3://{location.netloc}",
                status="discovered",
                file=file,
            )
            self.add_edge(
                connection,
                data_file,
                "connection",
                "confirmed",
                file,
                line,
                column,
            )
        return data_file

    def _resolve_sql_name(
        self,
        name: str,
        reference: _Reference,
        *,
        allow_inference: bool = True,
        mapped: bool = False,
        write_target: bool = False,
        synonym_depth: int = 0,
    ) -> list[_Resolution]:
        normalized = _normalized_name(name)
        declared = self.declared_resolutions(
            name,
            reference.file,
            reference.line,
            reference.column,
        )
        if declared:
            for resolution in declared:
                if resolution.node.status == "unknown":
                    resolution.node.referenced_in.add(reference.file)
            return declared

        synonym_targets = self.synonyms.get(normalized, [])
        distinct_synonyms = list(
            dict.fromkeys(_normalized_name(target) for target in synonym_targets)
        )
        if distinct_synonyms:
            if synonym_depth >= 16:
                self.add_diagnostic(
                    "warning",
                    "synonym_cycle",
                    reference.file,
                    f"Synonym resolution for {name!r} exceeded the supported depth.",
                    reference.line,
                    reference.column,
                )
                return []
            if len(distinct_synonyms) > 1:
                self.add_diagnostic(
                    "warning",
                    "ambiguous_synonym",
                    reference.file,
                    f"Synonym {name!r} has conflicting SQL definitions.",
                    reference.line,
                    reference.column,
                )
                candidates: list[_Resolution] = []
                for target in synonym_targets:
                    candidates.extend(
                        self._resolve_sql_name(
                            target,
                            reference,
                            allow_inference=allow_inference,
                            mapped=mapped,
                            write_target=write_target,
                            synonym_depth=synonym_depth + 1,
                        )
                    )
                return [
                    _Resolution(item.node, "ambiguous")
                    for item in _unique_resolutions(candidates)
                ]
            return self._resolve_sql_name(
                synonym_targets[0],
                reference,
                allow_inference=allow_inference,
                mapped=mapped,
                write_target=write_target,
                synonym_depth=synonym_depth + 1,
            )

        parts = _identifier_parts(name)
        if len(parts) == 4:
            remote = self._create_external_object(name, reference.file, reference.line)
            remote.referenced_in.add(reference.file)
            return [_Resolution(remote, "resolved")]

        if allow_inference and parts:
            suffix = tuple(part.casefold() for part in parts)
            candidates = [
                self.objects[identifier]
                for declared_name, identifiers in self.declarations.items()
                if tuple(declared_name.split("."))[-len(suffix) :] == suffix
                for identifier in identifiers
            ]
            candidates = list({candidate.id: candidate for candidate in candidates}.values())
            if len(candidates) == 1:
                candidate = candidates[0]
                candidate.referenced_in.add(reference.file)
                self.add_diagnostic(
                    "info",
                    "inferred_reference",
                    reference.file,
                    f"Reference {name!r} was inferred as {candidate.name!r} from a qualified SQL declaration.",
                    reference.line,
                    reference.column,
                )
                return [_Resolution(candidate, "inferred")]
            if len(candidates) > 1:
                self.add_diagnostic(
                    "warning",
                    "inference_conflict",
                    reference.file,
                    f"Reference {name!r} has multiple qualified SQL candidates; its database/schema remains unspecified.",
                    reference.line,
                    reference.column,
                )
                unknown = self.add_object(
                    reference.type_hint
                    if reference.type_hint != "relation"
                    else "relation",
                    name,
                    status="unknown",
                    file=reference.file,
                )
                return [_Resolution(unknown, "unknown")]

        if mapped:
            object_type = (
                reference.type_hint
                if reference.type_hint != "relation"
                else "relation"
            )
            node = self.add_object(object_type, name, status="mapped", file=reference.file)
            return [_Resolution(node, "resolved")]

        if write_target:
            object_type = (
                reference.type_hint
                if reference.type_hint != "relation"
                else "table"
            )
            node = self.add_object(
                object_type,
                name,
                status="referenced",
                file=reference.file,
            )
            return [_Resolution(node, "resolved")]

        object_type = (
            reference.type_hint
            if reference.type_hint != "relation"
            else "relation"
        )
        unknown = self.add_object(
            object_type,
            name,
            status="unknown",
            file=reference.file,
        )
        self.add_diagnostic(
            "warning",
            "unknown_relation",
            reference.file,
            f"Relation {name!r} is unresolved because no matching object is declared in the scanned repository.",
            reference.line,
            reference.column,
        )
        return [_Resolution(unknown, "unknown")]

    def resolve(
        self,
        reference: _Reference,
        *,
        write_target: bool = False,
    ) -> list[_Resolution]:
        if _is_temporary(reference.name):
            return []

        if reference.type_hint == "data_file":
            file_object = self._create_file_object(
                reference.name,
                reference.file,
                reference.line,
                reference.column,
            )
            file_object.referenced_in.add(reference.file)
            return [_Resolution(file_object, "resolved")]

        mapping_targets = self.mappings.get(_normalized_name(reference.name), [])
        if len(mapping_targets) > 1:
            self.add_diagnostic(
                "warning",
                "ambiguous_mapping",
                reference.file,
                f"Explicit mappings for {reference.name!r} have multiple targets.",
                reference.line,
                reference.column,
            )
            candidates: list[_Resolution] = []
            for target in mapping_targets:
                candidates.extend(
                    self._resolve_sql_name(
                        target,
                        reference,
                        allow_inference=False,
                        mapped=True,
                        write_target=write_target,
                    )
                )
            return [
                _Resolution(item.node, "ambiguous")
                for item in _unique_resolutions(candidates)
            ]

        if mapping_targets:
            target = mapping_targets[0]
            if _normalized_name(target) != _normalized_name(reference.name):
                if self.declarations.get(_normalized_name(reference.name)):
                    self.add_diagnostic(
                        "info",
                        "mapping_override",
                        reference.file,
                        f"Explicit mapping for {reference.name!r} overrides SQL-discovered information.",
                        reference.line,
                        reference.column,
                    )
            return self._resolve_sql_name(
                target,
                reference,
                allow_inference=False,
                mapped=True,
                write_target=write_target,
            )

        return self._resolve_sql_name(
            reference.name,
            reference,
            write_target=write_target,
        )


GraphBuilder = _GraphBuilder
ParsedFile = _ParsedFile
Reference = _Reference


def _unique_resolutions(values: list[_Resolution]) -> list[_Resolution]:
    unique: dict[str, _Resolution] = {}
    for value in values:
        unique.setdefault(value.node.id, value)
    return list(unique.values())


def _reference(segment: BaseSegment, file: str, type_hint: str = "relation") -> _Reference:
    line, column = _location(segment)
    return _Reference(segment.raw, file, line, column, type_hint)


def _cte_names(scope: BaseSegment) -> set[str]:
    names: set[str] = set()
    for cte in _descendants(scope, "common_table_expression"):
        first = next(
            (
                child
                for child in cte.segments
                if child.is_code and child.get_type() in {
                    "naked_identifier",
                    "quoted_identifier",
                    "identifier",
                }
            ),
            None,
        )
        if first is not None:
            names.add(_normalized_name(first.raw))
    return names


def _table_references(scope: BaseSegment, file: str) -> list[_Reference]:
    ctes = _cte_names(scope)
    references: list[_Reference] = []
    for segment in _descendants(scope, "table_reference"):
        if _normalized_name(segment.raw) in ctes or _is_temporary(segment.raw):
            continue
        references.append(_reference(segment, file))
    return references


def _source_file_references(scope: BaseSegment, file: str) -> list[_Reference]:
    references: list[_Reference] = []
    for rowset in _descendants(scope, "openrowset_segment"):
        if "BULK" not in rowset.raw.upper():
            line, column = _location(rowset)
            references_warning = _Reference(
                rowset.raw,
                file,
                line,
                column,
                "unsupported_external",
            )
            references.append(references_warning)
            continue
        literal = next(iter(_descendants(rowset, "quoted_literal")), None)
        if literal is not None:
            references.append(
                _Reference(
                    _literal_value(literal.raw),
                    file,
                    *_location(literal),
                    "data_file",
                )
            )
    return references


def _statement_identifier(statement: BaseSegment, *types: str) -> BaseSegment | None:
    return _first_direct(statement, *types)


def _procedure_spans(
    parsed_file: _ParsedFile,
    builder: _GraphBuilder,
) -> list[_ProcedureSpan]:
    spans: list[_ProcedureSpan] = []
    for procedure in _descendants(parsed_file.tree, "create_procedure_statement"):
        name_segment = _statement_identifier(procedure, "object_reference")
        span = _segment_offset(procedure)
        if name_segment is None or span is None:
            continue
        name = name_segment.raw
        identifiers = builder.declarations.get(_normalized_name(name), [])
        procedure_id = next(
            (
                identifier
                for identifier in identifiers
                if builder.objects[identifier].type == "stored_procedure"
            ),
            f"stored_procedure:{_normalized_name(name)}",
        )
        spans.append(_ProcedureSpan(procedure_id, span[0], span[1]))
    return spans


def _containing_procedure(
    segment: BaseSegment,
    spans: list[_ProcedureSpan],
) -> str | None:
    offset = _segment_offset(segment)
    if offset is None:
        return None
    start, stop = offset
    containing = [span for span in spans if span.start <= start and stop <= span.stop]
    if not containing:
        return None
    return min(containing, key=lambda span: span.stop - span.start).id


def _resolve_endpoint(
    builder: _GraphBuilder,
    reference: _Reference,
    *,
    write_target: bool = False,
) -> list[_Resolution]:
    if reference.type_hint == "unsupported_external":
        builder.add_diagnostic(
            "warning",
            "unsupported_external_reference",
            reference.file,
            "OPENROWSET without BULK input is not resolved because connection-string parsing is out of scope.",
            reference.line,
            reference.column,
        )
        return []
    return builder.resolve(reference, write_target=write_target)


def _edge_status(source: _Resolution, target: _Resolution) -> str:
    if source.status == "ambiguous" or target.status == "ambiguous":
        return "ambiguous"
    if source.status == "unknown":
        return "unknown_source"
    if target.status == "unknown":
        return "unknown_target"
    if source.status == "inferred" or target.status == "inferred":
        return "inferred"
    return "confirmed"


def _add_data_flow(
    builder: _GraphBuilder,
    sources: list[_Reference],
    targets: list[_Resolution],
    file: str,
    via_procedure: str | None = None,
) -> None:
    resolved_sources: list[tuple[_Resolution, _Reference]] = []
    for source in sources:
        for resolved in _resolve_endpoint(builder, source):
            resolved_sources.append((resolved, source))

    for target in targets:
        for source, evidence in resolved_sources:
            if source.node.id == target.node.id and source.status == "resolved":
                continue
            builder.add_edge(
                source.node,
                target.node,
                "data_flow",
                _edge_status(source, target),
                file,
                evidence.line,
                evidence.column,
                via_procedure,
            )


def _add_view_flows(
    parsed_file: _ParsedFile,
    builder: _GraphBuilder,
) -> None:
    for view in _descendants(parsed_file.tree, "create_view_statement"):
        name_segment = _statement_identifier(view, "object_reference")
        if name_segment is None:
            continue
        line, column = _location(name_segment)
        targets = builder.declared_resolutions(
            name_segment.raw,
            parsed_file.path,
            line,
            column,
        )
        sources = _table_references(view, parsed_file.path)
        sources.extend(_source_file_references(view, parsed_file.path))
        _add_data_flow(builder, sources, targets, parsed_file.path)


def _target_aliases(statement: BaseSegment) -> dict[str, str]:
    aliases: dict[str, str] = {}
    for element in _descendants(statement, "from_expression_element"):
        table = next(iter(_descendants(element, "table_reference")), None)
        alias_segment = next(iter(_descendants(element, "alias_expression")), None)
        if table is None or alias_segment is None:
            continue
        alias = re.sub(r"^\s*AS\s+", "", alias_segment.raw, flags=re.IGNORECASE).strip()
        normalized_alias = _normalized_name(alias)
        if normalized_alias:
            aliases[normalized_alias] = table.raw
    return aliases


def _dml_target(
    statement: BaseSegment,
    target_segment: BaseSegment,
    file: str,
) -> _Reference:
    name = target_segment.raw
    aliases = _target_aliases(statement)
    name = aliases.get(_normalized_name(name), name)
    return _Reference(name, file, *_location(target_segment), "table")


def _add_dml_flows(
    parsed_file: _ParsedFile,
    builder: _GraphBuilder,
    procedure_spans: list[_ProcedureSpan],
    procedure_id: str | None = None,
) -> None:
    file = parsed_file.path
    for statement_type in _DATA_MODIFICATION_TYPES:
        for statement in _descendants(parsed_file.tree, statement_type):
            target_segment = _first_direct(statement, "table_reference")
            if target_segment is None:
                continue
            target_reference = _dml_target(statement, target_segment, file)
            if _is_temporary(target_reference.name):
                continue
            targets = _resolve_endpoint(builder, target_reference, write_target=True)
            sources = [
                reference
                for reference in _table_references(statement, file)
                if _normalized_name(reference.name)
                != _normalized_name(target_segment.raw)
            ]
            sources.extend(_source_file_references(statement, file))
            _add_data_flow(
                builder,
                sources,
                targets,
                file,
                _containing_procedure(statement, procedure_spans) or procedure_id,
            )

    for select in _descendants(parsed_file.tree, "select_statement"):
        into_clause = _first_direct(select, "into_table_clause")
        if into_clause is None:
            continue
        target_segment = next(iter(_descendants(into_clause, "object_reference")), None)
        if target_segment is None:
            continue
        target_reference = _reference(target_segment, file, "table")
        builder.add_declaration("table", target_reference.name, file)
        if _is_temporary(target_reference.name):
            continue
        targets = _resolve_endpoint(builder, target_reference, write_target=True)
        sources = [
            reference
            for reference in _table_references(select, file)
            if _normalized_name(reference.name)
            != _normalized_name(target_reference.name)
        ]
        sources.extend(_source_file_references(select, file))
        _add_data_flow(
            builder,
            sources,
            targets,
            file,
            _containing_procedure(select, procedure_spans) or procedure_id,
        )


def _add_bulk_insert_flows(
    parsed_file: _ParsedFile,
    builder: _GraphBuilder,
    procedure_spans: list[_ProcedureSpan],
) -> None:
    for statement in _descendants(parsed_file.tree, "bulk_insert_statement"):
        target_segment = _first_direct(statement, "table_reference")
        literal = next(iter(_descendants(statement, "quoted_literal")), None)
        if target_segment is None or literal is None:
            continue
        target = _reference(target_segment, parsed_file.path, "table")
        source = _Reference(
            _literal_value(literal.raw),
            parsed_file.path,
            *_location(literal),
            "data_file",
        )
        _add_data_flow(
            builder,
            [source],
            _resolve_endpoint(builder, target, write_target=True),
            parsed_file.path,
            _containing_procedure(statement, procedure_spans),
        )


def _add_procedure_calls(
    parsed_file: _ParsedFile,
    builder: _GraphBuilder,
    procedure_spans: list[_ProcedureSpan],
) -> None:
    for statement in _descendants(parsed_file.tree, "execute_script_statement"):
        caller_id = _containing_procedure(statement, procedure_spans)
        if caller_id is None:
            continue
        called_segment = _first_direct(statement, "object_reference")
        if called_segment is None:
            continue
        reference = _reference(
            called_segment,
            parsed_file.path,
            "stored_procedure",
        )
        callees = builder.resolve(reference)
        caller = builder.objects.get(caller_id)
        if caller is None:
            continue
        for callee in callees:
            if callee.node.type != "stored_procedure" and callee.node.status != "unknown":
                builder.add_diagnostic(
                    "warning",
                    "non_procedure_call_target",
                    parsed_file.path,
                    f"EXEC target {reference.name!r} resolves to a non-procedure object.",
                    reference.line,
                    reference.column,
                )
            status = "ambiguous" if callee.status == "ambiguous" else (
                "unknown_target" if callee.status == "unknown" else "confirmed"
            )
            builder.add_edge(
                caller,
                callee.node,
                "procedure_call",
                status,
                parsed_file.path,
                reference.line,
                reference.column,
            )


__all__ = [
    "GraphBuilder",
    "ParsedFile",
    "Reference",
    "_add_bulk_insert_flows",
    "_add_data_flow",
    "_add_dml_flows",
    "_add_procedure_calls",
    "_add_view_flows",
    "_descendants",
    "_first_direct",
    "_location",
    "_literal_value",
    "_normalized_name",
    "_procedure_spans",
    "_reference",
    "_resolve_endpoint",
    "_statement_identifier",
    "_table_references",
]
