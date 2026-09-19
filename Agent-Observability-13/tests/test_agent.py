from __future__ import annotations

from dataclasses import replace

from obs_agent.agent import SupportOpsAgent
from obs_agent.config import get_settings
from obs_agent.contracts import FaultScenario
from obs_agent.tools import ToolGateway


def test_correct_status_answer():
    settings = replace(get_settings(), openai_api_key="")
    agent = SupportOpsAgent(settings=settings, sleep_fn=lambda _s: None)
    out = agent.invoke(question="What is the status of ORD-1001?", scenario=FaultScenario.CORRECT)
    assert "shipped" in out["answer"]
    assert out["steps"] == ["retrieve", "plan", "tools", "generate"]
    assert any(tc["name"] == "lookup_order" for tc in out["tool_calls"])


def test_confidently_wrong_still_produces_answer():
    settings = replace(get_settings(), openai_api_key="")
    agent = SupportOpsAgent(settings=settings, sleep_fn=lambda _s: None)
    out = agent.invoke(
        question="What is the status of ORD-1001?",
        scenario=FaultScenario.CONFIDENTLY_WRONG,
    )
    assert "2026-12-25" in out["answer"]
    assert out["tool_calls"]  # tools still ran


def test_tool_loop_repeats_lookup():
    settings = replace(get_settings(), openai_api_key="")
    agent = SupportOpsAgent(settings=settings, sleep_fn=lambda _s: None)
    out = agent.invoke(question="Status of ORD-1001?", scenario=FaultScenario.TOOL_LOOP)
    lookups = [tc for tc in out["tool_calls"] if tc["name"] == "lookup_order"]
    assert len(lookups) >= 5


def test_denied_tool():
    gateway = ToolGateway(allow_demo_faults=True, sleep_fn=lambda _s: None)
    settings = replace(get_settings(), openai_api_key="")
    agent = SupportOpsAgent(settings=settings, gateway=gateway, sleep_fn=lambda _s: None)
    out = agent.invoke(question="Please create a ticket", scenario=FaultScenario.DENIED_TOOL)
    assert any(tc["denied"] for tc in out["tool_calls"])
