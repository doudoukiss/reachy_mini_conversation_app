"""Tests for semantic tooling and legacy compatibility wrappers."""

from __future__ import annotations

import importlib
import sys
from types import ModuleType
from unittest.mock import MagicMock

import pytest

import reachy_mini_conversation_app.config as config_mod
import reachy_mini_conversation_app.prompts as prompts_mod
from reachy_mini_conversation_app.config import DEFAULT_PROFILES_DIRECTORY, config
from reachy_mini_conversation_app.robot_brain.adapters.mock_adapter import MockRobotAdapter
from reachy_mini_conversation_app.robot_brain.runtime import RobotBrainRuntime
from reachy_mini_conversation_app.tools.core_tools import ToolDependencies
from reachy_mini_conversation_app.tools.dance import Dance
from reachy_mini_conversation_app.tools.go_neutral import GoNeutral
from reachy_mini_conversation_app.tools.head_tracking import HeadTracking
from reachy_mini_conversation_app.tools.move_head import MoveHead
from reachy_mini_conversation_app.tools.observe_scene import ObserveScene
from reachy_mini_conversation_app.tools.orient_attention import OrientAttention
from reachy_mini_conversation_app.tools.perform_motif import PerformMotif
from reachy_mini_conversation_app.tools.play_emotion import PlayEmotion
from reachy_mini_conversation_app.tools.report_robot_status import ReportRobotStatus
from reachy_mini_conversation_app.tools.set_attention_mode import SetAttentionMode
from reachy_mini_conversation_app.tools.set_expression_state import SetExpressionState


def _reload_core_tools() -> ModuleType:
    """Reload core_tools after monkeypatching config-driven profile selection."""
    for module_name in list(sys.modules):
        if module_name.startswith("reachy_mini_conversation_app.tools."):
            sys.modules.pop(module_name, None)
    sys.modules.pop("reachy_mini_conversation_app.tools.core_tools", None)
    return importlib.import_module("reachy_mini_conversation_app.tools.core_tools")


def _build_semantic_deps() -> ToolDependencies:
    """Build tool dependencies backed by the mock robot runtime."""
    runtime = RobotBrainRuntime(MockRobotAdapter(), default_mode="mock")
    return ToolDependencies(
        reachy_mini=None,
        movement_manager=MagicMock(),
        robot_runtime=runtime,
    )


@pytest.mark.asyncio
async def test_semantic_tools_execute_against_mock_runtime() -> None:
    """The semantic tool layer should work end-to-end in pure mock mode."""
    deps = _build_semantic_deps()

    attention = await SetAttentionMode()(deps, mode="face_tracking")
    orient = await OrientAttention()(deps, target="left")
    expression = await SetExpressionState()(deps, state="friendly")
    motif = await PerformMotif()(deps, motif="guarded_close_left", intensity="medium")
    observation = await ObserveScene()(deps, question="What is in front of you?")
    neutral = await GoNeutral()(deps)
    status = await ReportRobotStatus()(deps)

    assert attention["status"] == "completed"
    assert attention["state"]["attention_mode"] == "face_tracking"
    assert orient["action_type"] == "orient_attention"
    assert orient["status"] == "completed"
    assert expression["state"]["persistent_state"] == "friendly"
    assert motif["details"]["motif"] == "guarded_close_left"
    assert observation["observation"]["visible_objects"] == ["desk", "laptop", "operator"]
    assert neutral["state"]["persistent_state"] == "neutral"
    assert status["capabilities"]["backend"] == "mock"


def test_capability_aware_specs_reflect_configured_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    """Semantic tool specs should advertise the configured semantic capability surface."""
    monkeypatch.setattr(config, "ROBOT_BACKEND", "mock")

    attention_spec = SetAttentionMode().spec()
    expression_spec = SetExpressionState().spec()
    motif_spec = PerformMotif().spec()

    assert "face_tracking" in attention_spec["description"]
    assert attention_spec["parameters"]["properties"]["mode"]["enum"] == [
        "manual",
        "face_tracking",
        "idle_scan",
        "disabled",
    ]
    assert "friendly" in expression_spec["description"]
    assert expression_spec["parameters"]["properties"]["state"]["enum"][0] == "neutral"
    assert "guarded_close_left" in motif_spec["description"]
    assert motif_spec["parameters"]["properties"]["motif"]["enum"] == [
        "guarded_close_left",
        "guarded_close_right",
    ]


@pytest.mark.asyncio
async def test_legacy_wrappers_delegate_to_semantic_runtime() -> None:
    """Legacy Reachy-shaped tools should now wrap semantic actions when runtime is present."""
    deps = _build_semantic_deps()

    move_result = await MoveHead()(deps, direction="left")
    tracking_result = await HeadTracking()(deps, start=True)

    assert move_result["legacy_tool"] == "move_head"
    assert move_result["action_type"] == "orient_attention"
    assert move_result["status"] == "completed"
    assert tracking_result["legacy_tool"] == "head_tracking"
    assert tracking_result["action_type"] == "set_attention_mode"
    assert tracking_result["state"]["attention_mode"] == "face_tracking"


@pytest.mark.asyncio
async def test_reachy_only_legacy_tools_report_unsupported_on_mock_backend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reachy-only legacy tools should stop pretending to be portable."""
    monkeypatch.setattr(config, "ROBOT_BACKEND", "mock")
    deps = ToolDependencies(reachy_mini=None, movement_manager=MagicMock())

    dance_result = await Dance()(deps, move="random")
    emotion_result = await PlayEmotion()(deps, emotion="joy")

    assert dance_result["status"] == "unsupported"
    assert "Reachy-only legacy tool" in dance_result["summary"]
    assert emotion_result["status"] == "unsupported"
    assert "Reachy-only legacy tool" in emotion_result["summary"]


def test_robot_brain_default_profile_loads_semantic_prompt_and_tools(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The new robot_brain_default profile should resolve to semantic tools and prompt text."""
    monkeypatch.setattr(config_mod.config, "REACHY_MINI_CUSTOM_PROFILE", "robot_brain_default")
    monkeypatch.setattr(config_mod.config, "PROFILES_DIRECTORY", DEFAULT_PROFILES_DIRECTORY)
    monkeypatch.setattr(config_mod.config, "TOOLS_DIRECTORY", None)
    monkeypatch.setattr(config_mod.config, "AUTOLOAD_EXTERNAL_TOOLS", False)

    core_tools_mod = _reload_core_tools()
    instructions = prompts_mod.get_session_instructions()

    assert "semantic robot-brain shell" in instructions
    assert "observe_scene" in core_tools_mod.ALL_TOOLS
    assert "set_expression_state" in core_tools_mod.ALL_TOOLS
    assert "go_neutral" in core_tools_mod.ALL_TOOLS
