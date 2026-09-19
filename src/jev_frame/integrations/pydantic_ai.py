from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel

from ..decisions import DecisionClient, DecisionInputs
from ..definitions import (
    DecisionContext,
    JevFrameError,
    Judgment,
    UsageCoverage,
)
from ..inspection import serialize_decision_result
from ..planning import PlannerRequest, PlannerTurn
from ..policy import ActionProposal, CheckpointRecord, RequiredCheckpoint


class PydanticAIIntegrationError(JevFrameError):
    pass


class RequiredCheckpointRejected(PydanticAIIntegrationError):
    pass


@dataclass(frozen=True, slots=True)
class PydanticAIDecisionContext:
    decision_context: DecisionContext
    input_factory: Callable[[BaseModel], DecisionInputs]

    def __post_init__(self) -> None:
        if not isinstance(self.decision_context, DecisionContext):
            raise PydanticAIIntegrationError(
                "decision_context must be a DecisionContext"
            )
        if not callable(self.input_factory):
            raise PydanticAIIntegrationError("input_factory must be callable")


@dataclass(frozen=True, slots=True)
class CheckpointedOutput:
    value: BaseModel
    checkpoint: CheckpointRecord


@dataclass(frozen=True, slots=True)
class NativeTypeSafeUsage:
    coverage: UsageCoverage
    input_tokens: int | None
    output_tokens: int | None
    request_count: int | None
    returned_model: str | None


def decision_tool(
    client: DecisionClient,
    judgment: Judgment,
    *,
    name: str,
    description: str,
    args_schema: type[BaseModel],
) -> Any:
    """Return a Pydantic AI tool while leaving the agent loop to the host."""

    try:
        from pydantic_ai import RunContext, Tool, ToolReturn
    except ImportError as error:  # pragma: no cover - exercised without the extra
        raise PydanticAIIntegrationError(
            "install jev-frame[pydantic-ai] to use the Pydantic AI integration"
        ) from error
    if not isinstance(args_schema, type) or not issubclass(args_schema, BaseModel):
        raise PydanticAIIntegrationError("args_schema must be a Pydantic model")

    decide = client.as_callable(judgment)

    async def invoke(ctx: Any, **arguments: Any) -> Any:
        host = ctx.deps
        if not isinstance(host, PydanticAIDecisionContext):
            raise PydanticAIIntegrationError(
                "RunContext deps must be PydanticAIDecisionContext"
            )
        validated = args_schema.model_validate(arguments, strict=True)
        inputs = host.input_factory(validated)
        if not isinstance(inputs, DecisionInputs):
            raise PydanticAIIntegrationError("input_factory must return DecisionInputs")
        result = await decide(inputs, host.decision_context)
        return ToolReturn(
            return_value=serialize_decision_result(result),
            metadata=result,
        )

    invoke.__annotations__["ctx"] = RunContext[PydanticAIDecisionContext]
    return Tool.from_schema(
        invoke,
        name=name,
        description=description,
        json_schema=args_schema.model_json_schema(),
        takes_ctx=True,
    )


def required_checkpoint_output(
    checkpoint: RequiredCheckpoint,
    proposal_factory: Callable[[PydanticAIDecisionContext, BaseModel], ActionProposal],
    *,
    name: str,
    description: str,
    args_schema: type[BaseModel],
) -> Any:
    """Return an output function that checks the exact current proposed output."""

    try:
        from pydantic_ai import RunContext, ToolOutput
    except ImportError as error:  # pragma: no cover - exercised without the extra
        raise PydanticAIIntegrationError(
            "install jev-frame[pydantic-ai] to use the Pydantic AI integration"
        ) from error
    if not isinstance(checkpoint, RequiredCheckpoint):
        raise PydanticAIIntegrationError("checkpoint must be a RequiredCheckpoint")
    if not callable(proposal_factory):
        raise PydanticAIIntegrationError("proposal_factory must be callable")
    if not isinstance(args_schema, type) or not issubclass(args_schema, BaseModel):
        raise PydanticAIIntegrationError("args_schema must be a Pydantic model")

    async def check(ctx: Any, value: BaseModel) -> CheckpointedOutput:
        host = ctx.deps
        if not isinstance(host, PydanticAIDecisionContext):
            raise PydanticAIIntegrationError(
                "RunContext deps must be PydanticAIDecisionContext"
            )
        proposal = proposal_factory(host, value)
        if not isinstance(proposal, ActionProposal):
            raise PydanticAIIntegrationError(
                "proposal_factory must return an ActionProposal"
            )
        record = await checkpoint.check(proposal)
        if not record.accepts(proposal):
            raise RequiredCheckpointRejected(
                f"required checkpoint {record.checkpoint_id!r} rejected the output"
            )
        return CheckpointedOutput(value, record)

    check.__annotations__["ctx"] = RunContext[PydanticAIDecisionContext]
    check.__annotations__["value"] = args_schema
    return ToolOutput(check, name=name, description=description)


def inspect_native_typesafe_usage(response: Any) -> NativeTypeSafeUsage:
    """Report only native TypeSafe usage that the returned response proves."""

    details = response.provider_details
    details = details if isinstance(details, Mapping) else {}
    request_count = details.get("requests")
    request_count = (
        request_count if type(request_count) is int and request_count >= 0 else None
    )
    usage = response.usage
    input_tokens = getattr(usage, "input_tokens", None)
    output_tokens = getattr(usage, "output_tokens", None)
    complete = (
        request_count is not None
        and type(input_tokens) is int
        and type(output_tokens) is int
    )
    native_response = response.provider_name == "typesafe"
    coverage = (
        UsageCoverage.COMPLETE
        if complete
        else UsageCoverage.PARTIAL
        if native_response
        else UsageCoverage.UNKNOWN
    )
    return NativeTypeSafeUsage(
        coverage,
        input_tokens if type(input_tokens) is int else None,
        output_tokens if type(output_tokens) is int else None,
        request_count,
        response.model_name if type(response.model_name) is str else None,
    )


def planner_callable(
    agent: Any,
    prompt_factory: Callable[[PlannerRequest], str],
    decode: Callable[[Any, PlannerRequest], PlannerTurn],
) -> Callable[[PlannerRequest], Any]:
    """Adapt a configured Pydantic AI agent as a proposal-only planner."""

    run = getattr(agent, "run", None)
    if not callable(run) or not callable(prompt_factory) or not callable(decode):
        raise PydanticAIIntegrationError(
            "planner adapter requires an agent, prompt factory and decoder"
        )

    async def plan(request: PlannerRequest) -> PlannerTurn:
        result = await run(prompt_factory(request))
        turn = decode(result.output, request)
        if not isinstance(turn, PlannerTurn):
            raise PydanticAIIntegrationError("planner decoder must return PlannerTurn")
        return turn

    return plan
