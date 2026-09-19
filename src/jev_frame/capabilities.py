from __future__ import annotations

import inspect
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from types import MappingProxyType, NoneType
from typing import Any, Literal, cast

from pydantic import BaseModel, ConfigDict, create_model

from .definitions import (
    Binding,
    Candidate,
    CandidateSet,
    Coverage,
    DefinitionError,
    InputValidationError,
    RetryOwner,
    ScopeError,
    StaleInputError,
    Tool,
    ToolEffect,
    UnsupportedTypeError,
    validate_value,
)
from .state import canonical_digest

_VERSION = re.compile(r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$")
_COMMON_SCHEMA_KEYS = {"type", "title", "description", "default"}


class CapabilityImportError(DefinitionError):
    pass


class StaleCapabilityError(StaleInputError):
    pass


def _text(value: str, name: str) -> None:
    if type(value) is not str or not value.strip():
        raise CapabilityImportError(f"{name} must be a non-empty string")


def _schema_mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise UnsupportedTypeError(f"{name} must be a JSON schema object")
    return value


def _freeze_json(value: Any, path: str) -> Any:
    if value is None or type(value) in {str, bool, int, float}:
        return value
    if isinstance(value, Mapping):
        if any(type(key) is not str for key in value):
            raise UnsupportedTypeError(f"{path} contains a non-string key")
        return MappingProxyType(
            {key: _freeze_json(item, f"{path}.{key}") for key, item in value.items()}
        )
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return tuple(
            _freeze_json(item, f"{path}[{index}]") for index, item in enumerate(value)
        )
    raise UnsupportedTypeError(f"{path} contains a non-JSON value")


def _foreign_value(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return {
            name: _foreign_value(item)
            for name, item in value.model_dump(mode="python").items()
        }
    if isinstance(value, Mapping):
        return {name: _foreign_value(item) for name, item in value.items()}
    if isinstance(value, list):
        return [_foreign_value(item) for item in value]
    return value


def _model_name(path: str) -> str:
    value = re.sub(r"[^0-9A-Za-z]+", "_", path).strip("_") or "Value"
    return "Imported" + "".join(part.title() for part in value.split("_"))


def _schema_type(schema: Mapping[str, Any], path: str) -> Any:
    schema = _schema_mapping(schema, path)
    schema_type = schema.get("type")
    allowed = set(_COMMON_SCHEMA_KEYS)
    if "enum" in schema:
        allowed.add("enum")
        values = schema["enum"]
        if (
            not isinstance(values, Sequence)
            or isinstance(values, (str, bytes))
            or not values
            or any(type(value) not in {str, int, float, bool} for value in values)
            or len(set(values)) != len(values)
        ):
            raise UnsupportedTypeError(f"{path} has an unsupported enum")
        if schema_type is None or any(
            {
                str: "string",
                int: "integer",
                float: "number",
                bool: "boolean",
            }[type(value)]
            != schema_type
            for value in values
        ):
            raise UnsupportedTypeError(f"{path} enum values do not match its type")
        if set(schema) - allowed:
            raise UnsupportedTypeError(f"{path} uses unsupported schema keywords")
        return Literal.__getitem__(tuple(values))
    result: Any
    if schema_type == "string":
        result = str
    elif schema_type == "integer":
        result = int
    elif schema_type == "number":
        result = float
    elif schema_type == "boolean":
        result = bool
    elif schema_type == "null":
        result = NoneType
    elif schema_type == "array":
        allowed.add("items")
        item_type = _schema_type(
            _schema_mapping(schema.get("items"), path), f"{path}[]"
        )
        result = list[item_type]  # type: ignore[valid-type]
    elif schema_type == "object":
        allowed.update({"properties", "required", "additionalProperties"})
        properties = schema.get("properties", {})
        required = schema.get("required", [])
        additional = schema.get("additionalProperties", True)
        if (
            not isinstance(properties, Mapping)
            or not isinstance(required, Sequence)
            or isinstance(required, (str, bytes))
        ):
            raise UnsupportedTypeError(f"{path} has invalid object fields")
        if any(type(name) is not str or not name for name in properties) or any(
            type(name) is not str or name not in properties for name in required
        ):
            raise UnsupportedTypeError(f"{path} has invalid required properties")
        if len(required) != len(set(required)):
            raise UnsupportedTypeError(f"{path} repeats a required property")
        if properties:
            if additional is not False:
                raise UnsupportedTypeError(
                    f"{path} must set additionalProperties to false"
                )
            fields: dict[str, tuple[Any, Any]] = {}
            for name, child in properties.items():
                child = _schema_mapping(child, f"{path}.{name}")
                annotation = _schema_type(child, f"{path}.{name}")
                if name in required:
                    default = ...
                elif "default" in child:
                    default = validate_value(
                        annotation, child["default"], f"{path}.{name} default"
                    )
                else:
                    raise UnsupportedTypeError(
                        f"{path}.{name} must be required or declare a default"
                    )
                fields[name] = (annotation, default)
            result = create_model(  # type: ignore[call-overload]
                _model_name(path),
                __config__=ConfigDict(strict=True, extra="forbid"),
                **fields,
            )
        elif isinstance(additional, Mapping):
            item_type = _schema_type(additional, f"{path}.*")
            result = dict[str, item_type]  # type: ignore[valid-type]
        elif additional is False:
            result = create_model(
                _model_name(path),
                __config__=ConfigDict(strict=True, extra="forbid"),
            )
        else:
            raise UnsupportedTypeError(f"{path} has unrestricted object values")
    else:
        raise UnsupportedTypeError(f"{path} has unsupported type {schema_type!r}")
    if set(schema) - allowed:
        raise UnsupportedTypeError(f"{path} uses unsupported schema keywords")
    return result


def _input_parameters(
    schema: Mapping[str, Any], identifier: str
) -> dict[str, tuple[Any, Any]]:
    if schema.get("type") != "object":
        raise UnsupportedTypeError(f"{identifier} input schema must be an object")
    model = _schema_type(schema, f"{identifier}.input")
    if not isinstance(model, type) or not issubclass(model, BaseModel):
        raise UnsupportedTypeError(
            f"{identifier} input schema must declare finite properties"
        )
    return {
        name: (
            field.annotation,
            ... if field.is_required() else field.default,
        )
        for name, field in model.model_fields.items()
    }


@dataclass(frozen=True, slots=True)
class ForeignToolDescriptor:
    id: str
    version: str
    description: str
    input_schema: Mapping[str, Any]
    output_schema: Mapping[str, Any]
    invoke: Callable[[Mapping[str, Any]], Any] = field(repr=False, compare=False)
    scopes: tuple[str, ...]
    source_id: str = "host"
    schema_digest: str = field(init=False)

    def __post_init__(self) -> None:
        _text(self.id, "foreign tool id")
        if type(self.version) is not str or _VERSION.fullmatch(self.version) is None:
            raise CapabilityImportError("foreign tool version must be semantic")
        _text(self.description, "foreign tool description")
        _text(self.source_id, "foreign tool source")
        if not callable(self.invoke):
            raise CapabilityImportError("foreign tool invoke must be callable")
        if not inspect.iscoroutinefunction(self.invoke):
            raise CapabilityImportError("foreign tool invoke must be asynchronous")
        if (
            not self.scopes
            or len(self.scopes) != len(set(self.scopes))
            or any(type(scope) is not str or not scope for scope in self.scopes)
        ):
            raise CapabilityImportError(
                "foreign tool scopes must be unique non-empty strings"
            )
        input_schema = _schema_mapping(
            _freeze_json(self.input_schema, f"{self.id}.input"), f"{self.id}.input"
        )
        output_schema = _schema_mapping(
            _freeze_json(self.output_schema, f"{self.id}.output"),
            f"{self.id}.output",
        )
        _input_parameters(input_schema, self.id)
        _schema_type(output_schema, f"{self.id}.output")
        object.__setattr__(self, "input_schema", input_schema)
        object.__setattr__(self, "output_schema", output_schema)
        object.__setattr__(
            self,
            "schema_digest",
            canonical_digest({"input": input_schema, "output": output_schema}),
        )


@dataclass(frozen=True, slots=True)
class CapabilityReference:
    catalog_id: str
    tool_id: str
    tool_version: str
    schema_digest: str
    candidate_key: str
    scope: str


@dataclass(frozen=True, slots=True)
class ImportedToolSemantics:
    bindings: Mapping[str, Binding] | None = None
    effect: ToolEffect | None = None
    requires_evidence: tuple[str, ...] | None = None
    produces_evidence: tuple[str, ...] | None = None
    scope_requirements: tuple[str, ...] | None = None
    timeout: float = 30.0
    retry_owner: RetryOwner = RetryOwner.NONE


@dataclass(frozen=True, slots=True)
class CapabilityCatalog:
    id: str
    version: str
    tools: tuple[ForeignToolDescriptor, ...]
    scopes: tuple[str, ...]
    max_results: int = 50

    def __post_init__(self) -> None:
        _text(self.id, "capability catalog id")
        if type(self.version) is not str or _VERSION.fullmatch(self.version) is None:
            raise CapabilityImportError("capability catalog version must be semantic")
        if type(self.max_results) is not int or self.max_results < 1:
            raise CapabilityImportError("catalog max_results must be positive")
        if (
            not self.scopes
            or len(self.scopes) != len(set(self.scopes))
            or any(type(scope) is not str or not scope for scope in self.scopes)
        ):
            raise CapabilityImportError(
                "catalog scopes must be unique non-empty strings"
            )
        if any(not isinstance(tool, ForeignToolDescriptor) for tool in self.tools):
            raise CapabilityImportError("catalog entries must be foreign tools")
        identities = [tool.id for tool in self.tools]
        if len(identities) != len(set(identities)):
            raise CapabilityImportError("catalog tool ids must be unique")

    def discover(
        self,
        query: str,
        scope: str,
        *,
        limit: int,
        offset: int = 0,
    ) -> CandidateSet:
        if type(query) is not str or type(scope) is not str or not scope:
            raise CapabilityImportError("discovery query and scope must be strings")
        if scope not in self.scopes:
            raise ScopeError("capability catalog is unavailable in this scope")
        if (
            type(limit) is not int
            or limit < 1
            or limit > self.max_results
            or type(offset) is not int
            or offset < 0
        ):
            raise CapabilityImportError("discovery bounds are invalid")
        terms = query.casefold().split()
        permitted = [
            tool
            for tool in self.tools
            if scope in tool.scopes
            and all(
                term in f"{tool.id} {tool.description}".casefold() for term in terms
            )
        ]
        permitted.sort(key=lambda tool: tool.id)
        selected = permitted[offset : offset + limit]
        end = offset + len(selected)
        coverage = Coverage.COMPLETE if end >= len(permitted) else Coverage.TRUNCATED
        candidates = []
        for tool in selected:
            key = canonical_digest(
                {
                    "catalog": self.id,
                    "tool": tool.id,
                    "version": tool.version,
                    "schema": tool.schema_digest,
                    "scope": scope,
                }
            )
            reference = CapabilityReference(
                self.id, tool.id, tool.version, tool.schema_digest, key, scope
            )
            candidates.append(
                Candidate(
                    key,
                    reference,
                    tool.description,
                    tool.source_id,
                    f"{tool.version}:{tool.schema_digest}",
                )
            )
        return CandidateSet(
            self.id,
            self.version,
            tuple(candidates),
            coverage,
            scope,
            total_count=len(permitted),
            query=query or None,
            retrieval_parameters=MappingProxyType({"limit": limit, "offset": offset}),
            expansion_ref=str(end) if coverage is Coverage.TRUNCATED else None,
        )

    def expand(self, snapshot: CandidateSet, *, limit: int) -> CandidateSet:
        if (
            snapshot.id != self.id
            or snapshot.version != self.version
            or snapshot.expansion_ref is None
        ):
            raise StaleCapabilityError("candidate snapshot cannot be expanded")
        try:
            offset = int(snapshot.expansion_ref)
        except (TypeError, ValueError) as error:
            raise StaleCapabilityError(
                "candidate expansion reference is invalid"
            ) from error
        return self.discover(
            snapshot.query or "", snapshot.scope, limit=limit, offset=offset
        )

    def activate(
        self,
        reference: CapabilityReference,
        semantics: ImportedToolSemantics,
    ) -> Tool:
        if not isinstance(reference, CapabilityReference):
            raise CapabilityImportError("activation requires a capability reference")
        if not isinstance(semantics, ImportedToolSemantics):
            raise CapabilityImportError("activation requires imported tool semantics")
        descriptor = next(
            (tool for tool in self.tools if tool.id == reference.tool_id), None
        )
        if (
            descriptor is None
            or reference.catalog_id != self.id
            or reference.tool_version != descriptor.version
            or reference.schema_digest != descriptor.schema_digest
        ):
            raise StaleCapabilityError("selected capability version is stale")
        expected_key = canonical_digest(
            {
                "catalog": self.id,
                "tool": descriptor.id,
                "version": descriptor.version,
                "schema": descriptor.schema_digest,
                "scope": reference.scope,
            }
        )
        if reference.candidate_key != expected_key:
            raise StaleCapabilityError("selected capability identity is invalid")
        if reference.scope not in descriptor.scopes:
            raise ScopeError("selected capability is not available in this scope")
        missing = [
            name
            for name in (
                "bindings",
                "effect",
                "requires_evidence",
                "produces_evidence",
                "scope_requirements",
            )
            if getattr(semantics, name) is None
        ]
        if missing:
            raise CapabilityImportError(
                f"activation requires explicit semantic metadata: {', '.join(missing)}"
            )
        if semantics.effect is ToolEffect.MUTATION:
            raise CapabilityImportError(
                "foreign mutations require an application-authored Jev Tool receipt contract"
            )
        parameters = _input_parameters(descriptor.input_schema, descriptor.id)
        output_type = _schema_type(descriptor.output_schema, f"{descriptor.id}.output")
        bindings = cast(Mapping[str, Binding], semantics.bindings)
        effect = cast(ToolEffect, semantics.effect)
        requires_evidence = cast(tuple[str, ...], semantics.requires_evidence)
        produces_evidence = cast(tuple[str, ...], semantics.produces_evidence)
        scope_requirements = cast(tuple[str, ...], semantics.scope_requirements)

        async def invoke(**arguments: Any) -> Any:
            if set(arguments) - set(parameters):
                raise InputValidationError(
                    f"{descriptor.id} received unknown arguments"
                )
            payload: dict[str, Any] = {}
            for name, (annotation, default) in parameters.items():
                if name in arguments:
                    raw = arguments[name]
                elif default is ...:
                    raise InputValidationError(
                        f"{descriptor.id} is missing argument {name}"
                    )
                else:
                    raw = default
                payload[name] = _foreign_value(
                    validate_value(annotation, raw, f"{descriptor.id}.{name}")
                )
            value = descriptor.invoke(MappingProxyType(payload))
            if inspect.isawaitable(value):
                value = await value
            return validate_value(output_type, value, f"{descriptor.id} output")

        invoke.__name__ = descriptor.id
        invoke.__annotations__ = {
            **{name: annotation for name, (annotation, _) in parameters.items()},
            "return": output_type,
        }
        invoke.__signature__ = inspect.Signature(  # type: ignore[attr-defined]
            [
                inspect.Parameter(
                    name,
                    inspect.Parameter.KEYWORD_ONLY,
                    default=(inspect.Parameter.empty if default is ... else default),
                    annotation=annotation,
                )
                for name, (annotation, default) in parameters.items()
            ],
            return_annotation=output_type,
        )
        return Tool(
            descriptor.id,
            descriptor.version,
            descriptor.description,
            invoke,
            bindings,
            effect=effect,
            timeout=semantics.timeout,
            retry_owner=semantics.retry_owner,
            requires_evidence=requires_evidence,
            produces_evidence=produces_evidence,
            scope_requirements=scope_requirements,
        )


def mcp_tool_descriptor(
    session: Any,
    descriptor: Mapping[str, Any],
    *,
    version: str,
    scopes: tuple[str, ...],
    source_id: str = "mcp",
) -> ForeignToolDescriptor:
    """Adapt one descriptor from an already configured host MCP session."""

    call_tool = getattr(session, "call_tool", None)
    if not callable(call_tool):
        raise CapabilityImportError("MCP session must expose call_tool")
    name = descriptor.get("name")
    description = descriptor.get("description")
    input_schema = descriptor.get("inputSchema")
    output_schema = descriptor.get("outputSchema")
    if type(name) is not str or type(description) is not str:
        raise CapabilityImportError(
            "MCP descriptor requires string name and description"
        )

    async def invoke(arguments: Mapping[str, Any]) -> Any:
        value = call_tool(name, dict(arguments))
        if inspect.isawaitable(value):
            value = await value
        if isinstance(value, Mapping) and "structuredContent" in value:
            return value["structuredContent"]
        for attribute in ("structuredContent", "structured_content"):
            structured = getattr(value, attribute, None)
            if structured is not None:
                return structured
        return value

    return ForeignToolDescriptor(
        name,
        version,
        description,
        _schema_mapping(input_schema, f"{name}.input"),
        _schema_mapping(output_schema, f"{name}.output"),
        invoke,
        scopes,
        source_id,
    )
