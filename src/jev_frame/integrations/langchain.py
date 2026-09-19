from __future__ import annotations

import json
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Any, TypeVar

from ..decisions import DecisionClient, DecisionInputs
from ..definitions import DecisionContext, DecisionResult, JevFrameError, Judgment
from ..inspection import serialize_decision_result
from ..policy import ActionProposal, CheckpointRecord, RequiredCheckpoint

StateT = TypeVar("StateT", bound=Mapping[str, Any])


class LangChainIntegrationError(JevFrameError):
    pass


class RequiredCheckpointRejected(LangChainIntegrationError):
    pass


@dataclass(frozen=True, slots=True)
class LangChainDecisionContext:
    decision_context: DecisionContext
    input_factory: Callable[[Mapping[str, Any]], DecisionInputs]

    def __post_init__(self) -> None:
        if not isinstance(self.decision_context, DecisionContext):
            raise LangChainIntegrationError(
                "decision_context must be a DecisionContext"
            )
        if not callable(self.input_factory):
            raise LangChainIntegrationError("input_factory must be callable")


def decision_tool(
    client: DecisionClient,
    judgment: Judgment,
    *,
    name: str,
    description: str,
    args_schema: type[Any],
) -> Any:
    """Return a LangChain tool while leaving graph and retry ownership to the host."""

    try:
        from langchain.tools import ToolRuntime, tool
    except ImportError as error:  # pragma: no cover - exercised without the extra
        raise LangChainIntegrationError(
            "install jev-frame[langchain] to use the LangChain integration"
        ) from error

    decide = client.as_callable(judgment)

    async def invoke(
        runtime: ToolRuntime[LangChainDecisionContext], **arguments: Any
    ) -> tuple[str, DecisionResult]:
        host = runtime.context
        if not isinstance(host, LangChainDecisionContext):
            raise LangChainIntegrationError(
                "ToolRuntime context must be LangChainDecisionContext"
            )
        inputs = host.input_factory(arguments)
        if not isinstance(inputs, DecisionInputs):
            raise LangChainIntegrationError("input_factory must return DecisionInputs")
        result = await decide(inputs, host.decision_context)
        return (
            json.dumps(serialize_decision_result(result), sort_keys=True),
            result,
        )

    # ToolNode resolves annotations from module globals, while ToolRuntime is kept
    # optional and imported locally, so bind the concrete injection marker directly.
    invoke.__annotations__["runtime"] = ToolRuntime[LangChainDecisionContext]
    return tool(
        name,
        description=description,
        args_schema=args_schema,
        response_format="content_and_artifact",
    )(invoke)


def required_checkpoint_node(
    checkpoint: RequiredCheckpoint,
    proposal_factory: Callable[[StateT], ActionProposal],
    *,
    output_key: str = "checkpoint",
) -> Callable[[StateT], Awaitable[dict[str, CheckpointRecord]]]:
    """Return a host-routed LangGraph node that checks the current action digest."""

    if not isinstance(checkpoint, RequiredCheckpoint):
        raise LangChainIntegrationError("checkpoint must be a RequiredCheckpoint")
    if not callable(proposal_factory):
        raise LangChainIntegrationError("proposal_factory must be callable")
    if type(output_key) is not str or not output_key:
        raise LangChainIntegrationError("output_key must be a non-empty string")

    async def check(state: StateT) -> dict[str, CheckpointRecord]:
        proposal = proposal_factory(state)
        if not isinstance(proposal, ActionProposal):
            raise LangChainIntegrationError(
                "proposal_factory must return an ActionProposal"
            )
        record = await checkpoint.check(proposal)
        if not record.accepts(proposal):
            raise RequiredCheckpointRejected(
                f"required checkpoint {record.checkpoint_id!r} rejected the action"
            )
        return {output_key: record}

    return check
