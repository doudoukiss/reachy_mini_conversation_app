from __future__ import annotations

from embodied_stack.config import Settings
from embodied_stack.shared.contracts import (
    AgentValidationStatus,
    CommandType,
    RobotCommand,
    ValidationOutcomeRecord,
)


_ALLOWED_COMMAND_TYPES = {
    CommandType.SPEAK,
    CommandType.DISPLAY_TEXT,
    CommandType.SET_LED,
    CommandType.SET_EXPRESSION,
    CommandType.SET_GAZE,
    CommandType.SET_HEAD_POSE,
    CommandType.PERFORM_GESTURE,
    CommandType.PERFORM_ANIMATION,
    CommandType.SAFE_IDLE,
    CommandType.STOP,
}


class EmbodiedActionPolicy:
    def __init__(self, *, settings: Settings) -> None:
        self.settings = settings

    def build_commands(self, intent: str, reply_text: str | None) -> list[RobotCommand]:
        if self.settings.uses_desktop_runtime:
            return self._build_desktop_commands(intent, reply_text)
        return self._build_legacy_commands(intent, reply_text)

    def _build_legacy_commands(self, intent: str, reply_text: str | None) -> list[RobotCommand]:
        commands: list[RobotCommand] = []

        if intent == "greeting":
            commands.append(RobotCommand(command_type=CommandType.SET_LED, payload={"color": "blue"}))
            commands.append(
                RobotCommand(
                    command_type=CommandType.SET_HEAD_POSE,
                    payload={"head_yaw_deg": 8.0, "head_pitch_deg": 0.0},
                )
            )
        elif intent in {"wayfinding", "events", "faq", "capabilities", "feedback", "perception_query"}:
            commands.append(RobotCommand(command_type=CommandType.SET_LED, payload={"color": "green"}))
        elif intent in {"operator_handoff", "operator_handoff_pending", "operator_handoff_unavailable"}:
            commands.append(RobotCommand(command_type=CommandType.SET_LED, payload={"color": "amber"}))
        elif intent == "operator_handoff_accepted":
            commands.append(RobotCommand(command_type=CommandType.SET_LED, payload={"color": "blue"}))
        elif intent == "operator_handoff_resolved":
            commands.append(RobotCommand(command_type=CommandType.SET_LED, payload={"color": "green"}))
        elif intent == "safe_idle":
            commands.append(RobotCommand(command_type=CommandType.SET_LED, payload={"color": "amber"}))
            commands.append(RobotCommand(command_type=CommandType.STOP, payload={"reason": "safe_idle"}))
        elif intent in {"attention", "clarify", "listening", "attract_prompt", "queue_wait", "crowd_reorientation"}:
            commands.append(RobotCommand(command_type=CommandType.SET_LED, payload={"color": "white"}))

        if reply_text:
            commands.append(RobotCommand(command_type=CommandType.DISPLAY_TEXT, payload={"text": reply_text}))
            commands.append(RobotCommand(command_type=CommandType.SPEAK, payload={"text": reply_text}))

        return commands

    def _build_desktop_commands(self, intent: str, reply_text: str | None) -> list[RobotCommand]:
        commands: list[RobotCommand] = []

        if intent == "greeting":
            commands.append(RobotCommand(command_type=CommandType.SET_LED, payload={"color": "blue"}))
            commands.append(RobotCommand(command_type=CommandType.SET_EXPRESSION, payload={"expression": "friendly"}))
            commands.append(RobotCommand(command_type=CommandType.SET_GAZE, payload={"target": "look_at_user"}))
            commands.append(RobotCommand(command_type=CommandType.PERFORM_GESTURE, payload={"gesture": "nod_small"}))
        elif intent in {"wayfinding", "events", "faq", "capabilities", "feedback", "perception_query"}:
            commands.append(RobotCommand(command_type=CommandType.SET_LED, payload={"color": "green"}))
            commands.append(RobotCommand(command_type=CommandType.SET_EXPRESSION, payload={"expression": "listen_attentively"}))
            commands.append(RobotCommand(command_type=CommandType.SET_GAZE, payload={"target": "look_forward"}))
        elif intent in {"operator_handoff", "operator_handoff_pending", "operator_handoff_unavailable"}:
            commands.append(RobotCommand(command_type=CommandType.SET_LED, payload={"color": "amber"}))
            commands.append(RobotCommand(command_type=CommandType.SET_EXPRESSION, payload={"expression": "thinking"}))
        elif intent == "operator_handoff_accepted":
            commands.append(RobotCommand(command_type=CommandType.SET_LED, payload={"color": "blue"}))
            commands.append(RobotCommand(command_type=CommandType.SET_EXPRESSION, payload={"expression": "listen_attentively"}))
        elif intent == "operator_handoff_resolved":
            commands.append(RobotCommand(command_type=CommandType.SET_LED, payload={"color": "green"}))
            commands.append(RobotCommand(command_type=CommandType.SET_EXPRESSION, payload={"expression": "friendly"}))
        elif intent == "safe_idle":
            commands.append(RobotCommand(command_type=CommandType.SET_LED, payload={"color": "amber"}))
            commands.append(RobotCommand(command_type=CommandType.SAFE_IDLE, payload={"reason": "safe_idle"}))
        elif intent in {"attention", "clarify", "listening", "attract_prompt", "queue_wait", "crowd_reorientation", "safe_degraded_response"}:
            commands.append(RobotCommand(command_type=CommandType.SET_LED, payload={"color": "white"}))
            commands.append(RobotCommand(command_type=CommandType.SET_EXPRESSION, payload={"expression": "listen_attentively"}))
            commands.append(RobotCommand(command_type=CommandType.SET_GAZE, payload={"target": "look_forward"}))

        if reply_text:
            commands.append(RobotCommand(command_type=CommandType.DISPLAY_TEXT, payload={"text": reply_text}))
            commands.append(RobotCommand(command_type=CommandType.SPEAK, payload={"text": reply_text}))

        return commands

    def prepend_stop_command(self, commands: list[RobotCommand], *, reason: str) -> list[RobotCommand]:
        return [RobotCommand(command_type=CommandType.STOP, payload={"reason": reason}), *commands]

    def validate_commands(self, commands: list[RobotCommand]) -> list[ValidationOutcomeRecord]:
        invalid_types = [command.command_type.value for command in commands if command.command_type not in _ALLOWED_COMMAND_TYPES]
        if invalid_types:
            return [
                ValidationOutcomeRecord(
                    validator_name="semantic_body_policy",
                    status=AgentValidationStatus.BLOCKED,
                    detail="non_semantic_command_detected",
                    notes=invalid_types,
                )
            ]
        return [
            ValidationOutcomeRecord(
                validator_name="semantic_body_policy",
                status=AgentValidationStatus.APPROVED,
                detail="semantic_command_plan_ok",
            )
        ]
