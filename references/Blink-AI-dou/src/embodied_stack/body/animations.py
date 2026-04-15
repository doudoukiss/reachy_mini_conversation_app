from __future__ import annotations

from embodied_stack.shared.contracts.body import AnimationTimeline, BodyKeyframe, BodyPose

from .library import apply_pose_overrides, expression_pose, gaze_pose
from .semantics import (
    CANONICAL_ANIMATIONS,
    LEGACY_ANIMATIONS,
    accepted_expression_names,
    accepted_gaze_names,
    accepted_gesture_names,
    normalize_animation_name,
    normalize_gesture_name,
)


def gesture_timeline(
    name: str,
    *,
    anchor_pose: BodyPose | None = None,
    neutral_pose: BodyPose | None = None,
    intensity: float = 1.0,
    repeat_count: int = 1,
) -> AnimationTimeline:
    normalized = normalize_gesture_name(name).canonical_name
    neutral = neutral_pose.model_copy(deep=True) if neutral_pose is not None else BodyPose()
    anchor = anchor_pose.model_copy(deep=True) if anchor_pose is not None else neutral.model_copy(deep=True)
    frames = _gesture_keyframes(normalized, anchor_pose=anchor, neutral_pose=neutral, intensity=intensity)
    return AnimationTimeline(animation_name=normalized, keyframes=frames, repeat_count=max(1, repeat_count))


def animation_timeline(
    name: str,
    *,
    anchor_pose: BodyPose | None = None,
    neutral_pose: BodyPose | None = None,
    intensity: float = 1.0,
    repeat_count: int = 1,
    loop: bool = False,
) -> AnimationTimeline:
    normalized = normalize_animation_name(name).canonical_name
    neutral = neutral_pose.model_copy(deep=True) if neutral_pose is not None else BodyPose()
    anchor = anchor_pose.model_copy(deep=True) if anchor_pose is not None else neutral.model_copy(deep=True)

    if normalized in accepted_gesture_names():
        timeline = gesture_timeline(
            normalized,
            anchor_pose=anchor,
            neutral_pose=neutral,
            intensity=intensity,
            repeat_count=repeat_count,
        )
        timeline.loop = loop
        return timeline

    if normalized in accepted_gaze_names():
        if normalized == "look_down_briefly":
            down_pose = gaze_pose("look_down_briefly", intensity=intensity, base_pose=anchor, neutral_pose=neutral)
            return AnimationTimeline(
                animation_name=normalized,
                keyframes=[
                    BodyKeyframe(keyframe_name="start", pose=anchor, duration_ms=80),
                    BodyKeyframe(keyframe_name="look_down", pose=down_pose, duration_ms=150, hold_ms=120),
                    BodyKeyframe(
                        keyframe_name="recover",
                        pose=gaze_pose("look_forward", base_pose=anchor, neutral_pose=neutral),
                        duration_ms=130,
                    ),
                ],
                repeat_count=max(1, repeat_count),
                loop=loop,
            )
        target_pose = gaze_pose(normalized, intensity=intensity, base_pose=anchor, neutral_pose=neutral)
        return AnimationTimeline(
            animation_name=normalized,
            keyframes=[
                BodyKeyframe(keyframe_name="start", pose=anchor, duration_ms=80),
                BodyKeyframe(keyframe_name=normalized, pose=target_pose, duration_ms=160, hold_ms=120),
            ],
            repeat_count=max(1, repeat_count),
            loop=loop,
        )

    if normalized in accepted_expression_names():
        target_pose = expression_pose(normalized, intensity=intensity, base_pose=anchor, neutral_pose=neutral)
        return AnimationTimeline(
            animation_name=normalized,
            keyframes=[BodyKeyframe(keyframe_name=normalized, pose=target_pose, duration_ms=180, hold_ms=160)],
            repeat_count=max(1, repeat_count),
            loop=loop,
        )

    frames = _animation_keyframes(normalized, anchor_pose=anchor, neutral_pose=neutral, intensity=intensity)
    return AnimationTimeline(
        animation_name=normalized if normalized in {*CANONICAL_ANIMATIONS, *LEGACY_ANIMATIONS} else "recover_neutral",
        keyframes=frames,
        repeat_count=max(1, repeat_count),
        loop=loop,
    )


def _gesture_keyframes(
    name: str,
    *,
    anchor_pose: BodyPose,
    neutral_pose: BodyPose,
    intensity: float,
) -> list[BodyKeyframe]:
    intensity = max(0.0, min(1.0, intensity))
    if name in {"blink", "blink_soft", "blink_slow"}:
        closed_level = 0.18 if name == "blink_soft" else 0.1 if name == "blink_slow" else 0.08
        close_duration = 110 if name == "blink_slow" else 80
        recover_duration = 110 if name == "blink_slow" else 70
        closed = apply_pose_overrides(
            anchor_pose,
            upper_lid_left_open=max(0.0, closed_level - (0.1 * intensity if name == "blink_soft" else 0.0)),
            upper_lid_right_open=max(0.0, closed_level - (0.1 * intensity if name == "blink_soft" else 0.0)),
            lower_lid_left_open=max(0.0, closed_level + 0.02),
            lower_lid_right_open=max(0.0, closed_level + 0.02),
        )
        return [
            BodyKeyframe(keyframe_name="start", pose=anchor_pose, duration_ms=40),
            BodyKeyframe(keyframe_name="closed", pose=closed, duration_ms=close_duration, transient=True),
            BodyKeyframe(keyframe_name="recover", pose=anchor_pose, duration_ms=recover_duration),
        ]
    if name == "double_blink":
        closed = apply_pose_overrides(
            anchor_pose,
            upper_lid_left_open=max(0.0, 0.08 - 0.06 * intensity),
            upper_lid_right_open=max(0.0, 0.08 - 0.06 * intensity),
            lower_lid_left_open=max(0.0, 0.14 - 0.02 * intensity),
            lower_lid_right_open=max(0.0, 0.14 - 0.02 * intensity),
            brow_raise_left=min(1.0, neutral_pose.brow_raise_left + 0.08 * intensity),
            brow_raise_right=min(1.0, neutral_pose.brow_raise_right + 0.08 * intensity),
        )
        return [
            BodyKeyframe(keyframe_name="start", pose=anchor_pose, duration_ms=30),
            BodyKeyframe(keyframe_name="blink_one", pose=closed, duration_ms=72, hold_ms=58, transient=True),
            BodyKeyframe(keyframe_name="recover_one", pose=anchor_pose, duration_ms=68),
            BodyKeyframe(keyframe_name="blink_two", pose=closed, duration_ms=72, hold_ms=58, transient=True),
            BodyKeyframe(keyframe_name="recover_two", pose=anchor_pose, duration_ms=90),
        ]
    if name == "double_blink_emphasis":
        closed = apply_pose_overrides(
            anchor_pose,
            upper_lid_left_open=max(0.0, 0.08 - 0.06 * intensity),
            upper_lid_right_open=max(0.0, 0.08 - 0.06 * intensity),
            lower_lid_left_open=max(0.0, 0.08),
            lower_lid_right_open=max(0.0, 0.08),
            brow_raise_left=min(1.0, neutral_pose.brow_raise_left + 0.12 * intensity),
            brow_raise_right=min(1.0, neutral_pose.brow_raise_right + 0.12 * intensity),
        )
        return [
            BodyKeyframe(keyframe_name="start", pose=anchor_pose, duration_ms=35),
            BodyKeyframe(keyframe_name="blink_one", pose=closed, duration_ms=70, hold_ms=45, transient=True),
            BodyKeyframe(keyframe_name="recover_one", pose=anchor_pose, duration_ms=65),
            BodyKeyframe(keyframe_name="blink_two", pose=closed, duration_ms=70, hold_ms=45, transient=True),
            BodyKeyframe(keyframe_name="recover_two", pose=anchor_pose, duration_ms=80),
        ]
    if name == "wink_left":
        wink = apply_pose_overrides(
            anchor_pose,
            upper_lid_left_open=max(0.0, 0.02),
            lower_lid_left_open=max(0.0, 0.08),
            upper_lid_right_open=anchor_pose.upper_lid_right_open,
            lower_lid_right_open=anchor_pose.lower_lid_right_open,
            brow_raise_left=min(1.0, neutral_pose.brow_raise_left + 0.14 * intensity),
        )
        return [
            BodyKeyframe(keyframe_name="start", pose=anchor_pose, duration_ms=40),
            BodyKeyframe(keyframe_name="wink_left", pose=wink, duration_ms=120, hold_ms=80, transient=True),
            BodyKeyframe(keyframe_name="recover", pose=anchor_pose, duration_ms=90),
        ]
    if name == "wink_right":
        wink = apply_pose_overrides(
            anchor_pose,
            upper_lid_right_open=max(0.0, 0.02),
            lower_lid_right_open=max(0.0, 0.08),
            upper_lid_left_open=anchor_pose.upper_lid_left_open,
            lower_lid_left_open=anchor_pose.lower_lid_left_open,
            brow_raise_right=min(1.0, neutral_pose.brow_raise_right + 0.14 * intensity),
        )
        return [
            BodyKeyframe(keyframe_name="start", pose=anchor_pose, duration_ms=40),
            BodyKeyframe(keyframe_name="wink_right", pose=wink, duration_ms=120, hold_ms=80, transient=True),
            BodyKeyframe(keyframe_name="recover", pose=anchor_pose, duration_ms=90),
        ]
    if name == "acknowledge_light":
        leveled_anchor = apply_pose_overrides(
            anchor_pose,
            head_pitch=max(anchor_pose.head_pitch, 0.012),
        )
        settle_direction = -1.0 if anchor_pose.head_yaw > 0.02 else 1.0
        affirm = apply_pose_overrides(
            leveled_anchor,
            head_yaw=max(-1.0, min(1.0, leveled_anchor.head_yaw + (0.09 * intensity * settle_direction))),
            head_pitch=min(1.0, leveled_anchor.head_pitch + (0.014 * intensity)),
            head_roll=max(-1.0, min(1.0, leveled_anchor.head_roll + (0.05 * intensity * settle_direction))),
            eye_pitch=min(1.0, leveled_anchor.eye_pitch + 0.1 * intensity),
            brow_raise_left=min(1.0, neutral_pose.brow_raise_left + 0.06 * intensity),
            brow_raise_right=min(1.0, neutral_pose.brow_raise_right + 0.06 * intensity),
        )
        settle = apply_pose_overrides(
            leveled_anchor,
            head_yaw=max(-1.0, min(1.0, leveled_anchor.head_yaw + (0.045 * intensity * settle_direction))),
            head_pitch=min(1.0, leveled_anchor.head_pitch + (0.008 * intensity)),
            head_roll=max(-1.0, min(1.0, leveled_anchor.head_roll + (0.02 * intensity * settle_direction))),
            eye_pitch=min(1.0, leveled_anchor.eye_pitch + 0.04 * intensity),
        )
        return [
            BodyKeyframe(keyframe_name="start", pose=leveled_anchor, duration_ms=30),
            BodyKeyframe(keyframe_name="affirm", pose=affirm, duration_ms=70, hold_ms=28),
            BodyKeyframe(keyframe_name="settle", pose=settle, duration_ms=60),
            BodyKeyframe(keyframe_name="recover", pose=leveled_anchor, duration_ms=70),
        ]
    if name in {"playful_peek_left", "playful_peek_right"}:
        direction = -1.0 if name.endswith("left") else 1.0
        peek = apply_pose_overrides(
            anchor_pose,
            head_yaw=max(-1.0, min(1.0, anchor_pose.head_yaw + 0.22 * intensity * direction)),
            head_roll=max(-1.0, min(1.0, anchor_pose.head_roll + 0.12 * intensity * direction)),
            eye_yaw=max(-1.0, min(1.0, anchor_pose.eye_yaw + 0.2 * intensity * direction)),
            brow_raise_left=min(1.0, neutral_pose.brow_raise_left + (0.08 * intensity if direction < 0 else 0.02 * intensity)),
            brow_raise_right=min(1.0, neutral_pose.brow_raise_right + (0.08 * intensity if direction > 0 else 0.02 * intensity)),
        )
        settle = apply_pose_overrides(
            anchor_pose,
            head_yaw=max(-1.0, min(1.0, anchor_pose.head_yaw + 0.1 * intensity * direction)),
            head_roll=max(-1.0, min(1.0, anchor_pose.head_roll + 0.04 * intensity * direction)),
            eye_yaw=max(-1.0, min(1.0, anchor_pose.eye_yaw + 0.08 * intensity * direction)),
        )
        return [
            BodyKeyframe(keyframe_name="start", pose=anchor_pose, duration_ms=40),
            BodyKeyframe(keyframe_name=name, pose=peek, duration_ms=105, hold_ms=55),
            BodyKeyframe(keyframe_name="settle", pose=settle, duration_ms=85),
            BodyKeyframe(keyframe_name="recover", pose=anchor_pose, duration_ms=90),
        ]
    if name == "nod_small":
        down = apply_pose_overrides(anchor_pose, head_pitch=max(-1.0, anchor_pose.head_pitch - 0.04 * intensity))
        up = apply_pose_overrides(
            anchor_pose,
            head_pitch=min(1.0, anchor_pose.head_pitch + 0.02 * intensity),
            brow_raise_left=min(1.0, neutral_pose.brow_raise_left + 0.04 * intensity),
            brow_raise_right=min(1.0, neutral_pose.brow_raise_right + 0.04 * intensity),
        )
        return [
            BodyKeyframe(keyframe_name="start", pose=anchor_pose, duration_ms=60),
            BodyKeyframe(keyframe_name="nod_down", pose=down, duration_ms=95),
            BodyKeyframe(keyframe_name="nod_up", pose=up, duration_ms=85),
            BodyKeyframe(keyframe_name="recover", pose=anchor_pose, duration_ms=90),
        ]
    if name == "nod_medium":
        down = apply_pose_overrides(anchor_pose, head_pitch=max(-1.0, anchor_pose.head_pitch - 0.08 * intensity))
        up = apply_pose_overrides(anchor_pose, head_pitch=min(1.0, anchor_pose.head_pitch + 0.03 * intensity))
        return [
            BodyKeyframe(keyframe_name="start", pose=anchor_pose, duration_ms=70),
            BodyKeyframe(keyframe_name="nod_down", pose=down, duration_ms=110),
            BodyKeyframe(keyframe_name="nod_up", pose=up, duration_ms=95),
            BodyKeyframe(keyframe_name="recover", pose=anchor_pose, duration_ms=100),
        ]
    if name == "tilt_curious":
        direction = 1.0 if anchor_pose.head_roll <= 0 else -1.0
        tilted = apply_pose_overrides(
            anchor_pose,
            head_yaw=max(-1.0, min(1.0, anchor_pose.head_yaw + (0.08 * intensity * direction))),
            head_roll=max(-1.0, min(1.0, anchor_pose.head_roll + (0.18 * intensity * direction))),
            eye_pitch=min(1.0, anchor_pose.eye_pitch + 0.06 * intensity),
            brow_raise_left=min(1.0, neutral_pose.brow_raise_left + 0.08 * intensity),
            brow_raise_right=min(1.0, neutral_pose.brow_raise_right + 0.12 * intensity),
        )
        return [
            BodyKeyframe(keyframe_name="start", pose=anchor_pose, duration_ms=80),
            BodyKeyframe(keyframe_name="tilt", pose=tilted, duration_ms=160, hold_ms=120),
            BodyKeyframe(keyframe_name="recover", pose=anchor_pose, duration_ms=120),
        ]
    if name in {"tilt_soft_left", "tilt_soft_right"}:
        direction = -1.0 if name.endswith("left") else 1.0
        tilted = apply_pose_overrides(
            anchor_pose,
            head_roll=max(-1.0, min(1.0, anchor_pose.head_roll + (0.14 * intensity * direction))),
            head_yaw=max(-1.0, min(1.0, anchor_pose.head_yaw + (0.05 * intensity * direction))),
        )
        return [
            BodyKeyframe(keyframe_name="start", pose=anchor_pose, duration_ms=80),
            BodyKeyframe(keyframe_name=name, pose=tilted, duration_ms=150, hold_ms=100),
            BodyKeyframe(keyframe_name="recover", pose=anchor_pose, duration_ms=120),
        ]
    return [BodyKeyframe(keyframe_name=name, pose=anchor_pose, duration_ms=120)]


def _animation_keyframes(
    name: str,
    *,
    anchor_pose: BodyPose,
    neutral_pose: BodyPose,
    intensity: float,
) -> list[BodyKeyframe]:
    if name == "boot_sequence":
        return [
            BodyKeyframe(keyframe_name="neutral", pose=expression_pose("neutral", neutral_pose=neutral_pose), duration_ms=180, hold_ms=60),
            BodyKeyframe(
                keyframe_name="friendly",
                pose=expression_pose("friendly", intensity, neutral_pose=neutral_pose),
                duration_ms=220,
                hold_ms=120,
            ),
            BodyKeyframe(
                keyframe_name="listen_attentively",
                pose=expression_pose("listen_attentively", intensity, neutral_pose=neutral_pose),
                duration_ms=220,
                hold_ms=160,
            ),
        ]
    if name == "idle_breathing_head":
        inhale = apply_pose_overrides(anchor_pose, head_pitch=min(1.0, anchor_pose.head_pitch + 0.03 * intensity))
        exhale = apply_pose_overrides(anchor_pose, head_pitch=max(-1.0, anchor_pose.head_pitch - 0.03 * intensity))
        return [
            BodyKeyframe(keyframe_name="start", pose=anchor_pose, duration_ms=220),
            BodyKeyframe(keyframe_name="inhale", pose=inhale, duration_ms=260, hold_ms=100),
            BodyKeyframe(keyframe_name="exhale", pose=exhale, duration_ms=260, hold_ms=100),
            BodyKeyframe(keyframe_name="recover", pose=anchor_pose, duration_ms=220),
        ]
    if name == "micro_blink_loop":
        blink = gesture_timeline(
            "blink_soft",
            anchor_pose=anchor_pose,
            neutral_pose=neutral_pose,
            intensity=intensity,
            repeat_count=2,
        )
        return blink.keyframes
    if name == "attention_settle":
        attentive = expression_pose("attentive_ready", intensity, base_pose=anchor_pose, neutral_pose=neutral_pose)
        listening = expression_pose("listen_attentively", intensity, base_pose=attentive, neutral_pose=neutral_pose)
        return [
            BodyKeyframe(keyframe_name="attentive_ready", pose=attentive, duration_ms=150, hold_ms=70),
            BodyKeyframe(keyframe_name="listen_attentively", pose=listening, duration_ms=180, hold_ms=120),
        ]
    if name == "thinking_settle":
        thinking = expression_pose("thinking", intensity, base_pose=anchor_pose, neutral_pose=neutral_pose)
        deep = expression_pose("thinking_deep", intensity, base_pose=thinking, neutral_pose=neutral_pose)
        return [
            BodyKeyframe(keyframe_name="thinking", pose=thinking, duration_ms=150, hold_ms=70),
            BodyKeyframe(keyframe_name="thinking_deep", pose=deep, duration_ms=180, hold_ms=120),
        ]
    if name == "micro_reorient":
        left = gaze_pose("micro_reorient_left", intensity=min(1.0, intensity), base_pose=anchor_pose, neutral_pose=neutral_pose)
        right = gaze_pose("micro_reorient_right", intensity=min(1.0, intensity), base_pose=anchor_pose, neutral_pose=neutral_pose)
        forward = gaze_pose("look_forward", base_pose=anchor_pose, neutral_pose=neutral_pose)
        return [
            BodyKeyframe(keyframe_name="start", pose=forward, duration_ms=70),
            BodyKeyframe(keyframe_name="micro_left", pose=left, duration_ms=110, hold_ms=70),
            BodyKeyframe(keyframe_name="micro_right", pose=right, duration_ms=110, hold_ms=70),
            BodyKeyframe(keyframe_name="recover", pose=forward, duration_ms=120),
        ]
    if name == "speak_listen_transition":
        friendly = expression_pose("friendly", intensity, base_pose=anchor_pose, neutral_pose=neutral_pose)
        listening = expression_pose("listen_attentively", intensity, base_pose=anchor_pose, neutral_pose=neutral_pose)
        return [
            BodyKeyframe(keyframe_name="speak_pose", pose=friendly, duration_ms=140, hold_ms=80),
            BodyKeyframe(keyframe_name="listen_pose", pose=listening, duration_ms=160, hold_ms=120),
        ]
    if name == "scan_softly":
        left = gaze_pose("left", intensity=min(1.0, intensity * 0.8), base_pose=anchor_pose, neutral_pose=neutral_pose)
        right = gaze_pose("right", intensity=min(1.0, intensity * 0.8), base_pose=anchor_pose, neutral_pose=neutral_pose)
        forward = gaze_pose("look_forward", base_pose=anchor_pose, neutral_pose=neutral_pose)
        return [
            BodyKeyframe(keyframe_name="start", pose=forward, duration_ms=80),
            BodyKeyframe(keyframe_name="scan_left", pose=left, duration_ms=160, hold_ms=90),
            BodyKeyframe(keyframe_name="scan_right", pose=right, duration_ms=180, hold_ms=90),
            BodyKeyframe(keyframe_name="recover", pose=forward, duration_ms=140),
        ]
    if name == "freeze_expression":
        return [BodyKeyframe(keyframe_name="freeze", pose=anchor_pose, duration_ms=120, hold_ms=240)]
    if name == "recover_neutral":
        settle = expression_pose("focused_soft", min(0.6, intensity), base_pose=anchor_pose, neutral_pose=neutral_pose)
        return [
            BodyKeyframe(keyframe_name="start", pose=anchor_pose, duration_ms=80),
            BodyKeyframe(keyframe_name="settle", pose=settle, duration_ms=140, hold_ms=60),
            BodyKeyframe(
                keyframe_name="neutral",
                pose=expression_pose("neutral", base_pose=settle, neutral_pose=neutral_pose),
                duration_ms=160,
                hold_ms=120,
            ),
        ]
    if name == "youthful_greeting":
        friendly = expression_pose("friendly", min(1.0, intensity), base_pose=anchor_pose, neutral_pose=neutral_pose)
        curious = expression_pose("curious_bright", min(1.0, intensity), base_pose=friendly, neutral_pose=neutral_pose)
        blink_frames = gesture_timeline(
            "double_blink",
            anchor_pose=curious,
            neutral_pose=neutral_pose,
            intensity=min(1.0, intensity),
        ).keyframes
        settle = expression_pose("friendly", min(0.9, intensity), base_pose=curious, neutral_pose=neutral_pose)
        return [
            BodyKeyframe(keyframe_name="friendly", pose=friendly, duration_ms=140, hold_ms=70),
            BodyKeyframe(keyframe_name="curious_bright", pose=curious, duration_ms=155, hold_ms=70),
            *blink_frames,
            BodyKeyframe(keyframe_name="friendly_settle", pose=settle, duration_ms=150, hold_ms=110),
        ]
    if name == "soft_reengage":
        focused = expression_pose("focused_soft", min(1.0, intensity), base_pose=anchor_pose, neutral_pose=neutral_pose)
        blink_frames = gesture_timeline(
            "double_blink",
            anchor_pose=focused,
            neutral_pose=neutral_pose,
            intensity=min(1.0, intensity),
        ).keyframes
        settle = expression_pose("friendly", min(0.78, intensity), base_pose=focused, neutral_pose=neutral_pose)
        return [
            BodyKeyframe(keyframe_name="focused_soft", pose=focused, duration_ms=150, hold_ms=70),
            *blink_frames,
            BodyKeyframe(keyframe_name="friendly_settle", pose=settle, duration_ms=150, hold_ms=120),
        ]
    if name == "playful_react":
        playful = expression_pose("playful", min(1.0, intensity), base_pose=anchor_pose, neutral_pose=neutral_pose)
        peek_name = "playful_peek_left" if anchor_pose.head_yaw >= 0 else "playful_peek_right"
        peek_frames = gesture_timeline(
            peek_name,
            anchor_pose=playful,
            neutral_pose=neutral_pose,
            intensity=min(1.0, intensity),
        ).keyframes
        recover = expression_pose("friendly", min(1.0, intensity), base_pose=playful, neutral_pose=neutral_pose)
        return [
            BodyKeyframe(keyframe_name="playful", pose=playful, duration_ms=140, hold_ms=65),
            *peek_frames,
            BodyKeyframe(keyframe_name="friendly", pose=recover, duration_ms=140, hold_ms=100),
        ]
    return [
        BodyKeyframe(
            keyframe_name="neutral",
            pose=expression_pose("neutral", neutral_pose=neutral_pose),
            duration_ms=180,
            hold_ms=120,
        )
    ]


__all__ = ["animation_timeline", "gesture_timeline"]
