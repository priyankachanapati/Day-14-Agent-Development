"""Activity 3 - tests of the workflow router (scripted model, no API calls)."""

import asyncio

import pytest

from activity3_workflows.router import HANDLERS, Classification, ScriptedLLM, classify, gate, handle_request, parallel_demo


def run(coro):
    return asyncio.run(coro)


@pytest.mark.parametrize(
    "text,category",
    [("I was charged twice on my invoice", "billing"), ("My VPN shows an error", "tech"), ("Where is the canteen?", "other")],
)
def test_requests_are_routed_to_the_matching_handler(text, category):
    r = run(handle_request(ScriptedLLM(latency=0), text))
    assert r["classification"]["category"] == category and r["handler"] == HANDLERS[category].__name__ and r["fallback"] is None


@pytest.mark.parametrize(
    "raw",
    [
        '{"category": "refunds", "confidence": 0.5, "reason": "x y z"}',  # unexpected category
        '{"category": "tech", "confidence": 7, "reason": "too confident"}',  # out of range
        '{"category": "tech"}',  # missing fields
        "billing, probably",
    ],
)  # not JSON
def test_invalid_classifier_output_falls_back_to_other(raw):
    cls, fallback = run(classify(ScriptedLLM(latency=0, classify_override=raw), "anything"))
    assert cls.category == "other" and fallback and "routed to 'other'" in fallback


def test_schema_accepts_valid_output():
    assert (
        Classification.model_validate_json('{"category": "billing", "confidence": 0.8, "reason": "invoice"}').category
        == "billing"
    )


def test_gate_blocks_refund_promises_and_empty_replies():
    assert gate("Your refund has been approved.")[0] is False
    assert gate("   ")[0] is False
    assert gate("The billing team will review the charge.") == (True, "ok")


def test_asyncio_gather_runs_handlers_concurrently():
    p = run(parallel_demo(ScriptedLLM(latency=0.3), {"billing": "duplicate charge", "tech": "wifi drops"}))
    assert p["sequential_s"] >= 0.55 and p["parallel_s"] < 0.45 and p["speedup"] > 1.5
    assert p["results"] == p["sequential_results"]  # same answers, only faster
