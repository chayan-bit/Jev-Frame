import asyncio
import json
import unittest
from collections.abc import Callable
from typing import Any

import httpx2
from typesafe_sdk import AsyncTypeSafeClient, Noul, RetryPolicy, TypeSafeError

from jev_frame import (
    AttemptStatus,
    ChoiceAnswer,
    CompiledOption,
    CompiledQuestion,
    NoulAnswer,
    ProviderDispatchError,
    ProviderRequestTimeout,
    ProviderResponseError,
    ScoreAnswer,
    TypeSafeProvider,
    UsageCoverage,
)


def questions() -> tuple[CompiledQuestion, ...]:
    return (
        CompiledQuestion(
            routing_id="q-choice",
            judgment_id="choice",
            primitive="choice",
            instructions="Choose for subject record.",
            subjects=("record",),
            evidence=("catalog",),
            dependencies=(),
            options=(
                CompiledOption("a", "Candidate A"),
                CompiledOption("b", "Candidate B"),
            ),
        ),
        CompiledQuestion(
            routing_id="q-noul",
            judgment_id="noul",
            primitive="noul",
            instructions="Assess subject claim.",
            subjects=("claim",),
            evidence=("source",),
            dependencies=(),
            true_description="The claim is supported.",
            false_description="The claim is not supported.",
        ),
        CompiledQuestion(
            routing_id="q-score",
            judgment_id="score",
            primitive="score",
            instructions="Score subject urgency.",
            subjects=("urgency",),
            evidence=("message",),
            dependencies=(),
            score_levels=("low", "medium", "high"),
        ),
    )


def response_body() -> dict[str, Any]:
    return {
        "model": "jev-test-2026-09-18",
        "answers": {
            "q-choice": {
                "type": "choice",
                "choice": "b",
                "confidence": 0.8,
                "probabilities": {"a": 0.2, "b": 0.8},
            },
            "q-noul": {"type": "noul", "noul": 1e-9},
            "q-score": {
                "type": "score",
                "score": 1.7,
                "confidence": 0.9,
                "legend": {"0": "low", "1": "medium", "2": "high"},
                "probabilities": {"0": 0.1, "1": 0.1, "2": 0.8},
            },
        },
        "usage": {"input_tokens": 12, "output_tokens": 3},
    }


def provider_for(
    handler: Callable[[httpx2.Request], Any],
    *,
    max_attempts: int = 1,
    sleep: Callable[[float], Any] | None = None,
) -> TypeSafeProvider:
    async def no_sleep(_: float) -> None:
        return None

    return TypeSafeProvider(
        api_key="offline-test-key",
        default_model="jev-default",
        max_attempts=max_attempts,
        transport=httpx2.MockTransport(handler),
        base_url="https://typesafe.invalid",
        sleep=no_sleep if sleep is None else sleep,
    )


class ProviderTests(unittest.IsolatedAsyncioTestCase):
    async def test_sdk_validates_api_keys_early_without_echoing_them(self) -> None:
        sentinel = "JF22_SYNTHETIC_KEY"
        with self.assertRaises(TypeSafeError) as caught:
            AsyncTypeSafeClient(api_key=f"{sentinel} invalid")
        self.assertNotIn(sentinel, str(caught.exception))
        self.assertNotIn(sentinel, repr(caught.exception))

        async with AsyncTypeSafeClient(api_key=sentinel) as client:
            self.assertNotIn(sentinel, repr(client))

    async def test_wire_shape_and_primitive_semantics(self) -> None:
        payloads: list[dict[str, Any]] = []

        async def handler(request: httpx2.Request) -> httpx2.Response:
            payloads.append(json.loads(request.content))
            return httpx2.Response(
                200,
                headers={"x-typesafe-request-id": "request-1"},
                json=response_body(),
            )

        async with provider_for(handler) as provider:
            result = await provider.evaluate(
                state={"text": "fixture"},
                questions=questions(),
                requested_model="jev-requested",
                operation_id="operation",
            )

        self.assertEqual(len(payloads), 1)
        self.assertEqual(payloads[0]["model"], "jev-requested")
        self.assertEqual(payloads[0]["questions"]["q-noul"]["type"], "noul")
        self.assertEqual(
            payloads[0]["questions"]["q-noul"]["criteria"]["true"],
            "The claim is supported.",
        )
        self.assertEqual(result.requested_model, "jev-requested")
        self.assertEqual(result.returned_model, "jev-test-2026-09-18")
        self.assertEqual(result.request_id, "request-1")
        self.assertIs(result.usage.coverage, UsageCoverage.COMPLETE)
        self.assertEqual(result.usage.provider_attempts, 1)
        self.assertEqual(result.usage.submitted_questions, 3)
        self.assertEqual(result.attempts[0].status, AttemptStatus.SUCCEEDED)
        choice = result.answers["q-choice"]
        noul = result.answers["q-noul"]
        score = result.answers["q-score"]
        self.assertIsInstance(choice, ChoiceAnswer)
        self.assertIsInstance(noul, NoulAnswer)
        self.assertIsInstance(score, ScoreAnswer)
        assert isinstance(noul, NoulAnswer)
        assert isinstance(score, ScoreAnswer)
        self.assertEqual(noul.probability_yes, 1e-9)
        self.assertEqual(score.score, 1.7)
        self.assertEqual(score.legend, ("low", "medium", "high"))

    async def test_semantically_invalid_answers_reject_the_batch(self) -> None:
        cases: dict[str, Callable[[dict[str, Any]], None]] = {
            "unknown_candidate": lambda body: body["answers"]["q-choice"].update(
                choice="outside"
            ),
            "missing_answer": lambda body: body["answers"].pop("q-noul"),
            "invalid_distribution": lambda body: body["answers"]["q-choice"].update(
                probabilities={"a": 0.4, "b": 0.4}
            ),
            "wrong_type": lambda body: body["answers"].update(
                {
                    "q-noul": {
                        "type": "choice",
                        "choice": "a",
                        "confidence": 1.0,
                        "probabilities": {"a": 0.5, "b": 0.5},
                    }
                }
            ),
        }
        for expected, mutate in cases.items():
            with self.subTest(expected):
                body = response_body()
                mutate(body)

                async def handler(
                    _: httpx2.Request, response: dict[str, Any] = body
                ) -> httpx2.Response:
                    return httpx2.Response(
                        200,
                        headers={"x-typesafe-request-id": "bad-response"},
                        json=response,
                    )

                async with provider_for(handler) as provider:
                    with self.assertRaises(ProviderResponseError) as caught:
                        await provider.evaluate(
                            state="fixture",
                            questions=questions(),
                            requested_model="jev-test",
                            operation_id=expected,
                        )
                code = caught.exception.code
                if expected == "missing_answer":
                    self.assertEqual(code, "answer_ids_mismatch")
                elif expected == "invalid_distribution":
                    self.assertEqual(code, "probabilities_not_normalized")
                elif expected == "wrong_type":
                    self.assertEqual(code, "primitive_type_mismatch")
                else:
                    self.assertEqual(code, expected)
                self.assertEqual(
                    caught.exception.attempts[0].status,
                    AttemptStatus.RESPONSE_REJECTED,
                )

    async def test_nan_and_sdk_structural_failure_are_sanitized(self) -> None:
        bodies = [
            json.dumps(response_body()).replace('"noul": 1e-09', '"noul": NaN'),
            json.dumps(response_body()).replace('"confidence": 0.8,', ""),
        ]
        expected = ("invalid_probability", "sdk_response_invalid")
        for content, code in zip(bodies, expected, strict=True):
            with self.subTest(code):

                async def handler(
                    _: httpx2.Request, response: str = content
                ) -> httpx2.Response:
                    return httpx2.Response(
                        200,
                        headers={"x-typesafe-request-id": "invalid"},
                        content=response.encode(),
                    )

                async with provider_for(handler) as provider:
                    with self.assertRaises(ProviderResponseError) as caught:
                        await provider.evaluate(
                            state="fixture",
                            questions=questions(),
                            requested_model="jev-test",
                            operation_id=code,
                        )
                self.assertEqual(caught.exception.code, code)
                self.assertNotIn("NaN", str(caught.exception))

    async def test_retries_are_bounded_and_each_attempt_is_admitted_once(self) -> None:
        calls = 0
        admitted: list[str] = []

        async def handler(_: httpx2.Request) -> httpx2.Response:
            nonlocal calls
            calls += 1
            if calls < 3:
                return httpx2.Response(
                    429,
                    headers={"retry-after": "0"},
                    json={"error": "slow down"},
                )
            return httpx2.Response(
                200,
                headers={"x-typesafe-request-id": "request-retried"},
                json=response_body(),
            )

        async def admit(attempt: Any) -> None:
            admitted.append(attempt.id)

        async with provider_for(handler, max_attempts=3) as provider:
            result = await provider.evaluate(
                state="fixture",
                questions=questions(),
                requested_model="jev-test",
                operation_id="retry",
                admit_attempt=admit,
            )

        self.assertEqual(calls, 3)
        self.assertEqual(admitted, ["retry:1", "retry:2", "retry:3"])
        self.assertEqual(
            [attempt.status for attempt in result.attempts],
            [AttemptStatus.FAILED, AttemptStatus.FAILED, AttemptStatus.SUCCEEDED],
        )
        self.assertEqual(result.usage.submitted_questions, 9)

    async def test_retry_exhaustion_timeout_and_authentication_are_typed(self) -> None:
        async def rate_limited(_: httpx2.Request) -> httpx2.Response:
            return httpx2.Response(429, json={"error": "private rate detail"})

        async with provider_for(rate_limited, max_attempts=2) as provider:
            with self.assertRaises(ProviderDispatchError) as caught:
                await provider.evaluate(
                    state="fixture",
                    questions=questions(),
                    requested_model="jev-test",
                    operation_id="rate",
                )
        self.assertEqual(caught.exception.code, "rate_limited")
        self.assertEqual(len(caught.exception.attempts), 2)
        self.assertNotIn("private rate detail", str(caught.exception))

        async def timeout(request: httpx2.Request) -> httpx2.Response:
            raise httpx2.ReadTimeout("private timeout detail", request=request)

        async with provider_for(timeout) as provider:
            with self.assertRaises(ProviderRequestTimeout):
                await provider.evaluate(
                    state="fixture",
                    questions=questions(),
                    requested_model="jev-test",
                    operation_id="timeout",
                )

        calls = 0

        async def unauthorized(_: httpx2.Request) -> httpx2.Response:
            nonlocal calls
            calls += 1
            return httpx2.Response(401, json={"error": "secret-value"})

        async with provider_for(unauthorized, max_attempts=3) as provider:
            with self.assertRaises(ProviderDispatchError) as auth:
                await provider.evaluate(
                    state="fixture",
                    questions=questions(),
                    requested_model="jev-test",
                    operation_id="auth",
                )
        self.assertEqual(calls, 1)
        self.assertEqual(auth.exception.code, "authentication")
        self.assertNotIn("secret-value", str(auth.exception))

    async def test_unknown_usage_is_not_zero(self) -> None:
        body = response_body()
        body["usage"] = {"input_tokens": None, "output_tokens": None}

        async def handler(_: httpx2.Request) -> httpx2.Response:
            return httpx2.Response(200, json=body)

        async with provider_for(handler) as provider:
            result = await provider.evaluate(
                state="fixture",
                questions=questions(),
                requested_model="jev-test",
                operation_id="usage",
            )

        self.assertIs(result.usage.coverage, UsageCoverage.UNKNOWN)
        self.assertIsNone(result.usage.input_tokens)
        self.assertIsNone(result.usage.output_tokens)

    async def test_client_ownership_and_cancellation_cleanup(self) -> None:
        calls = 0

        async def handler(_: httpx2.Request) -> httpx2.Response:
            nonlocal calls
            calls += 1
            return httpx2.Response(200, json=response_body())

        client = AsyncTypeSafeClient(
            api_key="offline-test-key",
            retry=RetryPolicy(max_retries=0),
            transport=httpx2.MockTransport(handler),
            base_url="https://typesafe.invalid",
        )
        provider = TypeSafeProvider(client)
        await provider.aclose()
        response = await client.system_one(
            "fixture",
            {"q": Noul(instructions="Is this a fixture?")},
            retry=RetryPolicy(max_retries=0),
        )
        self.assertEqual(response.model, "jev-test-2026-09-18")
        self.assertEqual(calls, 1)
        await client.aclose()

        admitted: list[str] = []

        async def cancelled(_: httpx2.Request) -> httpx2.Response:
            raise asyncio.CancelledError

        async def admit(attempt: Any) -> None:
            admitted.append(attempt.id)

        async with provider_for(cancelled) as owned:
            with self.assertRaises(asyncio.CancelledError):
                await owned.evaluate(
                    state="fixture",
                    questions=questions(),
                    requested_model="jev-test",
                    operation_id="cancel",
                    admit_attempt=admit,
                )
            self.assertTrue(owned.owns_client)
        self.assertEqual(admitted, ["cancel:1"])


if __name__ == "__main__":
    unittest.main()
