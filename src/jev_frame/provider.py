from __future__ import annotations

import asyncio
import inspect
import math
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType, TracebackType
from typing import Any, Protocol, Self

import httpx2
from typesafe_sdk import (
    AsyncTypeSafeClient,
    Choice,
    JSONContent,
    Noul,
    NoulCriteria,
    RetryPolicy,
    Score,
    SystemOneResponse,
    TypeSafeAPIConnectionError,
    TypeSafeAPIError,
    TypeSafeAPIResponseValidationError,
    TypeSafeAPITimeoutError,
    TypeSafeAuthenticationError,
    TypeSafeError,
    TypeSafeInternalServerError,
    TypeSafeRateLimitError,
)
from typesafe_sdk import ChoiceAnswer as SDKChoiceAnswer
from typesafe_sdk import NoulAnswer as SDKNoulAnswer
from typesafe_sdk import Question as SDKQuestion
from typesafe_sdk import ScoreAnswer as SDKScoreAnswer

from .compiler import CompiledQuestion
from .definitions import (
    ChoiceAnswer,
    NoulAnswer,
    PrimitiveAnswer,
    ProviderError,
    ProviderTimeoutError,
    ResponseValidationError,
    ScoreAnswer,
    Usage,
    UsageCoverage,
)

PROBABILITY_SUM_TOLERANCE = 1e-3


class AsyncSystemOneClient(Protocol):
    async def system_one(
        self,
        state: JSONContent,
        questions: Mapping[str, SDKQuestion],
        *,
        model: str | None = None,
        retry: RetryPolicy | None = None,
        timeout: float | httpx2.Timeout | None = None,
    ) -> SystemOneResponse: ...

    async def aclose(self) -> None: ...


class AttemptStatus(str, Enum):
    STARTED = "started"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    RESPONSE_REJECTED = "response_rejected"


@dataclass(frozen=True, slots=True)
class ProviderAttempt:
    id: str
    number: int
    status: AttemptStatus
    code: str | None = None
    request_id: str | None = None


AttemptAdmission = Callable[[ProviderAttempt], Awaitable[None] | None]
Sleep = Callable[[float], Awaitable[None]]


class ProviderDispatchError(ProviderError):
    def __init__(
        self,
        code: str,
        attempts: tuple[ProviderAttempt, ...],
        request_id: str | None = None,
    ) -> None:
        self.code = code
        self.attempts = attempts
        self.request_id = request_id
        detail = f"provider request failed ({code}, attempts={len(attempts)})"
        if request_id is not None:
            detail += f" (request_id={request_id})"
        super().__init__(detail)


class ProviderRequestTimeout(ProviderTimeoutError):
    def __init__(self, attempts: tuple[ProviderAttempt, ...]) -> None:
        self.code = "timeout"
        self.attempts = attempts
        super().__init__(f"provider request timed out (attempts={len(attempts)})")


class ProviderResponseError(ResponseValidationError):
    def __init__(
        self,
        code: str,
        attempts: tuple[ProviderAttempt, ...],
        question_id: str | None = None,
        request_id: str | None = None,
    ) -> None:
        self.code = code
        self.attempts = attempts
        self.question_id = question_id
        self.request_id = request_id
        detail = f"provider response rejected ({code})"
        if question_id is not None:
            detail += f" for question {question_id}"
        if request_id is not None:
            detail += f" (request_id={request_id})"
        super().__init__(detail)


@dataclass(frozen=True, slots=True)
class ProviderBatch:
    answers: Mapping[str, PrimitiveAnswer]
    requested_model: str
    returned_model: str | None
    request_id: str | None
    usage: Usage
    attempts: tuple[ProviderAttempt, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "answers", MappingProxyType(dict(self.answers)))


class _InvalidResponse(Exception):
    def __init__(self, code: str, question_id: str | None = None) -> None:
        self.code = code
        self.question_id = question_id


def _request_id(value: Any) -> str | None:
    try:
        request_id = value.request_id
    except (AttributeError, TypeSafeError):
        return None
    return request_id if type(request_id) is str and request_id else None


def _probability(value: float, question_id: str) -> float:
    if (
        type(value) not in {int, float}
        or not math.isfinite(value)
        or not 0 <= value <= 1
    ):
        raise _InvalidResponse("invalid_probability", question_id)
    return float(value)


def _probabilities(
    values: Mapping[Any, float], expected: set[Any], question_id: str
) -> dict[Any, float]:
    if set(values) != expected:
        raise _InvalidResponse("probability_keys_mismatch", question_id)
    checked = {key: _probability(value, question_id) for key, value in values.items()}
    if not math.isclose(
        sum(checked.values()),
        1.0,
        rel_tol=0.0,
        abs_tol=PROBABILITY_SUM_TOLERANCE,
    ):
        raise _InvalidResponse("probabilities_not_normalized", question_id)
    return checked


def _sdk_question(question: CompiledQuestion) -> SDKQuestion:
    if not question.dispatchable:
        raise ProviderResponseError("question_not_dispatchable", ())
    if question.primitive == "choice":
        return Choice(
            instructions=question.instructions,
            criteria={item.key: item.description for item in question.options},
        )
    if question.primitive == "noul":
        criteria = NoulCriteria()
        if question.true_description is not None:
            criteria["true"] = question.true_description
        if question.false_description is not None:
            criteria["false"] = question.false_description
        return Noul(
            instructions=question.instructions,
            criteria=criteria or None,
        )
    if question.primitive == "score":
        return Score(
            instructions=question.instructions,
            criteria=list(question.score_levels),
        )
    raise ProviderResponseError("unsupported_primitive", (), question.routing_id)


def _choice_answer(question: CompiledQuestion, answer: SDKChoiceAnswer) -> ChoiceAnswer:
    expected = {item.key for item in question.options}
    if answer.choice not in expected:
        raise _InvalidResponse("unknown_candidate", question.routing_id)
    probabilities = _probabilities(answer.probabilities, expected, question.routing_id)
    confidence = _probability(answer.confidence, question.routing_id)
    return ChoiceAnswer(answer.choice, probabilities, confidence)


def _noul_answer(question: CompiledQuestion, answer: SDKNoulAnswer) -> NoulAnswer:
    return NoulAnswer(_probability(answer.noul, question.routing_id))


def _score_answer(question: CompiledQuestion, answer: SDKScoreAnswer) -> ScoreAnswer:
    expected = set(range(len(question.score_levels)))
    probabilities = _probabilities(answer.probabilities, expected, question.routing_id)
    if set(answer.legend) != expected or any(
        answer.legend[index] != description
        for index, description in enumerate(question.score_levels)
    ):
        raise _InvalidResponse("score_legend_mismatch", question.routing_id)
    if (
        type(answer.score) not in {int, float}
        or not math.isfinite(answer.score)
        or not 0 <= answer.score <= len(question.score_levels) - 1
    ):
        raise _InvalidResponse("invalid_score", question.routing_id)
    confidence = _probability(answer.confidence, question.routing_id)
    return ScoreAnswer(
        float(answer.score),
        question.score_levels,
        tuple(probabilities[index] for index in range(len(question.score_levels))),
        confidence,
    )


def _validate_answers(
    response: SystemOneResponse, questions: Sequence[CompiledQuestion]
) -> dict[str, PrimitiveAnswer]:
    by_id = {question.routing_id: question for question in questions}
    if set(response.answers) != set(by_id):
        missing = set(by_id) - set(response.answers)
        question_id = min(missing) if missing else None
        raise _InvalidResponse("answer_ids_mismatch", question_id)
    validated: dict[str, PrimitiveAnswer] = {}
    for question_id, question in by_id.items():
        answer = response.answers[question_id]
        if question.primitive == "choice" and isinstance(answer, SDKChoiceAnswer):
            validated[question_id] = _choice_answer(question, answer)
        elif question.primitive == "noul" and isinstance(answer, SDKNoulAnswer):
            validated[question_id] = _noul_answer(question, answer)
        elif question.primitive == "score" and isinstance(answer, SDKScoreAnswer):
            validated[question_id] = _score_answer(question, answer)
        else:
            raise _InvalidResponse("primitive_type_mismatch", question_id)
    return validated


def _usage(response: SystemOneResponse, attempts: int, questions: int) -> Usage:
    input_tokens = response.usage.input_tokens
    output_tokens = response.usage.output_tokens
    if any(
        value is not None and (type(value) is not int or value < 0)
        for value in (input_tokens, output_tokens)
    ):
        raise _InvalidResponse("invalid_usage")
    if input_tokens is not None and output_tokens is not None:
        coverage = UsageCoverage.COMPLETE
    elif input_tokens is not None or output_tokens is not None:
        coverage = UsageCoverage.PARTIAL
    else:
        coverage = UsageCoverage.UNKNOWN
    return Usage(coverage, input_tokens, output_tokens, attempts, attempts * questions)


def _error_code(error: TypeSafeError) -> str:
    if isinstance(error, TypeSafeAuthenticationError):
        return "authentication"
    if isinstance(error, TypeSafeRateLimitError):
        return "rate_limited"
    if isinstance(error, TypeSafeAPITimeoutError):
        return "timeout"
    if isinstance(error, TypeSafeAPIConnectionError):
        return "connection"
    if isinstance(error, TypeSafeAPIResponseValidationError):
        return "sdk_response_invalid"
    if isinstance(error, TypeSafeAPIError):
        return "http_error"
    return "sdk_error"


def _retryable(error: TypeSafeError) -> bool:
    return (isinstance(error, TypeSafeAPIError) and error.status == 408) or isinstance(
        error,
        (
            TypeSafeRateLimitError,
            TypeSafeInternalServerError,
            TypeSafeAPIConnectionError,
        ),
    )


def _retry_after(error: TypeSafeError, fallback: float) -> float:
    if isinstance(error, TypeSafeRateLimitError) and error.retry_after_ms is not None:
        return error.retry_after_ms / 1000
    return fallback


class TypeSafeProvider:
    """Official TypeSafe SDK transport with framework-owned retry accounting."""

    def __init__(
        self,
        client: AsyncSystemOneClient | None = None,
        *,
        api_key: str | None = None,
        default_model: str | None = None,
        max_attempts: int = 1,
        retry_delay: float = 0.5,
        transport: httpx2.AsyncBaseTransport | None = None,
        base_url: str | None = None,
        sleep: Sleep = asyncio.sleep,
    ) -> None:
        if type(max_attempts) is not int or max_attempts < 1:
            raise ValueError("max_attempts must be a positive integer")
        if (
            type(retry_delay) not in {int, float}
            or not math.isfinite(retry_delay)
            or retry_delay < 0
        ):
            raise ValueError("retry_delay must be finite and nonnegative")
        if client is not None and any(
            value is not None for value in (api_key, default_model, transport, base_url)
        ):
            raise ValueError(
                "client ownership cannot be mixed with client construction"
            )
        self._owns_client = client is None
        self._client: AsyncSystemOneClient = (
            AsyncTypeSafeClient(
                api_key=api_key,
                model=default_model,
                retry=RetryPolicy(max_retries=0),
                transport=transport,
                base_url=base_url,
            )
            if client is None
            else client
        )
        self._max_attempts = max_attempts
        self._retry_delay = float(retry_delay)
        self._sleep = sleep
        self._closed = False

    @property
    def owns_client(self) -> bool:
        return self._owns_client

    async def evaluate(
        self,
        *,
        state: JSONContent,
        questions: Sequence[CompiledQuestion],
        requested_model: str,
        operation_id: str,
        timeout: float | None = None,
        admit_attempt: AttemptAdmission | None = None,
        max_attempts: int | None = None,
    ) -> ProviderBatch:
        if self._closed:
            raise ProviderDispatchError("provider_closed", ())
        if type(requested_model) is not str or not requested_model.strip():
            raise ValueError("requested_model must be a non-empty string")
        if type(operation_id) is not str or not operation_id.strip():
            raise ValueError("operation_id must be a non-empty string")
        if timeout is not None and (
            type(timeout) not in {int, float}
            or not math.isfinite(timeout)
            or timeout <= 0
        ):
            raise ValueError("timeout must be finite and positive")
        limit = self._max_attempts if max_attempts is None else max_attempts
        if type(limit) is not int or limit < 1 or limit > self._max_attempts:
            raise ValueError("max_attempts must be within the provider limit")
        if not questions:
            raise ValueError("at least one compiled question is required")
        question_ids = [question.routing_id for question in questions]
        if len(question_ids) != len(set(question_ids)):
            raise ValueError("compiled question routing IDs must be unique")
        sdk_questions = {
            question.routing_id: _sdk_question(question) for question in questions
        }
        attempts: list[ProviderAttempt] = []
        for number in range(1, limit + 1):
            attempt_id = f"{operation_id}:{number}"
            started = ProviderAttempt(attempt_id, number, AttemptStatus.STARTED)
            if admit_attempt is not None:
                admitted = admit_attempt(started)
                if inspect.isawaitable(admitted):
                    await admitted
            try:
                response = await self._client.system_one(
                    state,
                    sdk_questions,
                    model=requested_model,
                    retry=RetryPolicy(max_retries=0),
                    timeout=timeout,
                )
            except asyncio.CancelledError:
                raise
            except TypeSafeError as error:
                code = _error_code(error)
                request_id = _request_id(error)
                attempts.append(
                    ProviderAttempt(
                        attempt_id,
                        number,
                        AttemptStatus.FAILED,
                        code,
                        request_id,
                    )
                )
                if _retryable(error) and number < limit:
                    await self._sleep(_retry_after(error, self._retry_delay))
                    continue
                records = tuple(attempts)
                if isinstance(error, TypeSafeAPITimeoutError):
                    raise ProviderRequestTimeout(records) from None
                if isinstance(error, TypeSafeAPIResponseValidationError):
                    raise ProviderResponseError(
                        code, records, request_id=request_id
                    ) from None
                raise ProviderDispatchError(code, records, request_id) from None

            request_id = _request_id(response)
            try:
                answers = _validate_answers(response, questions)
                if type(response.model) is not str or not response.model.strip():
                    raise _InvalidResponse("missing_returned_model")
                usage = _usage(response, len(attempts) + 1, len(questions))
            except _InvalidResponse as error:
                attempts.append(
                    ProviderAttempt(
                        attempt_id,
                        number,
                        AttemptStatus.RESPONSE_REJECTED,
                        error.code,
                        request_id,
                    )
                )
                raise ProviderResponseError(
                    error.code,
                    tuple(attempts),
                    error.question_id,
                    request_id,
                ) from None
            attempts.append(
                ProviderAttempt(
                    attempt_id,
                    number,
                    AttemptStatus.SUCCEEDED,
                    request_id=request_id,
                )
            )
            records = tuple(attempts)
            return ProviderBatch(
                answers,
                requested_model,
                response.model,
                request_id,
                usage,
                records,
            )
        raise AssertionError("positive attempt limit guarantees return or raise")

    async def aclose(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._owns_client:
            await self._client.aclose()

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self.aclose()
