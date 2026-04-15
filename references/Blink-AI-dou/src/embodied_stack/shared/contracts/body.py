from __future__ import annotations

from ._common import CharacterProjectionProfile, BaseModel, BodyDriverMode, Field, datetime, model_validator, utc_now


class BodyPose(BaseModel):
    head_yaw: float = Field(default=0.0, ge=-1.0, le=1.0)
    head_pitch: float = Field(default=0.0, ge=-1.0, le=1.0)
    head_roll: float = Field(default=0.0, ge=-1.0, le=1.0)
    eye_yaw: float = Field(default=0.0, ge=-1.0, le=1.0)
    eye_pitch: float = Field(default=0.0, ge=-1.0, le=1.0)
    upper_lids_open: float = Field(default=1.0, ge=0.0, le=1.0)
    lower_lids_open: float = Field(default=1.0, ge=0.0, le=1.0)
    upper_lid_left_open: float | None = Field(default=None, ge=0.0, le=1.0)
    upper_lid_right_open: float | None = Field(default=None, ge=0.0, le=1.0)
    lower_lid_left_open: float | None = Field(default=None, ge=0.0, le=1.0)
    lower_lid_right_open: float | None = Field(default=None, ge=0.0, le=1.0)
    brow_raise_left: float = Field(default=0.0, ge=0.0, le=1.0)
    brow_raise_right: float = Field(default=0.0, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def resolve_asymmetric_fields(self) -> "BodyPose":
        if self.upper_lid_left_open is None:
            self.upper_lid_left_open = self.upper_lids_open
        if self.upper_lid_right_open is None:
            self.upper_lid_right_open = self.upper_lids_open
        if self.lower_lid_left_open is None:
            self.lower_lid_left_open = self.lower_lids_open
        if self.lower_lid_right_open is None:
            self.lower_lid_right_open = self.lower_lids_open
        self.upper_lids_open = (self.upper_lid_left_open + self.upper_lid_right_open) / 2.0
        self.lower_lids_open = (self.lower_lid_left_open + self.lower_lid_right_open) / 2.0
        return self


class HeadJointProfile(BaseModel):
    joint_name: str
    servo_ids: list[int] = Field(default_factory=list)
    neutral: int
    raw_min: int
    raw_max: int
    positive_direction: str
    enabled: bool = True
    notes: list[str] = Field(default_factory=list)


class HeadCouplingRule(BaseModel):
    name: str
    description: str
    affected_joints: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class HeadProfile(BaseModel):
    profile_name: str = "robot_head_v1"
    profile_version: str = "blink_head_profile/v1"
    transport_boundary_version: str = "semantic_body_transport/v1"
    servo_family: str = "feetech_sts3032"
    baud_rate: int = 115200
    auto_scan_baud_rates: list[int] = Field(default_factory=lambda: [115200, 1000000])
    neutral_pose_label: str = "looking_forward_normal_expression"
    joints: list[HeadJointProfile] = Field(default_factory=list)
    coupling_rules: list[HeadCouplingRule] = Field(default_factory=list)
    default_transition_ms: int = Field(default=160, ge=40, le=2000)
    minimum_transition_ms: int = Field(default=80, ge=0, le=2000)
    neutral_recovery_ms: int = Field(default=220, ge=40, le=4000)
    safe_speed: int | None = None
    safe_speed_ceiling: int | None = None
    safe_acceleration: int | None = None
    safe_idle_torque_off: bool = True
    source_path: str | None = None
    source_format: str | None = None
    notes: list[str] = Field(default_factory=list)
    pending_bench_confirmations: list[str] = Field(default_factory=list)


class JointCalibrationRecord(BaseModel):
    joint_name: str
    servo_ids: list[int] = Field(default_factory=list)
    neutral: int
    raw_min: int
    raw_max: int
    current_position: int | None = None
    mirrored_direction_confirmed: bool | None = None
    error: str | None = None
    notes: list[str] = Field(default_factory=list)


class HeadCalibrationRecord(BaseModel):
    schema_version: str = "blink_head_calibration/v2"
    profile_name: str
    profile_version: str | None = None
    profile_path: str | None = None
    transport_boundary_version: str | None = None
    calibration_kind: str = "saved"
    author: str | None = None
    transport_mode: str | None = None
    transport_port: str | None = None
    baud_rate: int | None = None
    timeout_seconds: float | None = None
    transport_confirmed_live: bool | None = None
    provenance_source: str | None = None
    safe_speed: int | None = None
    safe_acceleration: int | None = None
    joint_records: list[JointCalibrationRecord] = Field(default_factory=list)
    coupling_validation: dict[str, str] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)
    recorded_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class ExpressionRequest(BaseModel):
    expression_name: str
    intensity: float = Field(default=1.0, ge=0.0, le=1.0)
    note: str | None = None


class GazeRequest(BaseModel):
    target: str | None = None
    yaw: float | None = Field(default=None, ge=-1.0, le=1.0)
    pitch: float | None = Field(default=None, ge=-1.0, le=1.0)
    intensity: float = Field(default=1.0, ge=0.0, le=1.0)
    note: str | None = None


class GestureRequest(BaseModel):
    gesture_name: str
    intensity: float = Field(default=1.0, ge=0.0, le=1.0)
    repeat_count: int = Field(default=1, ge=1, le=8)
    note: str | None = None


class AnimationRequest(BaseModel):
    animation_name: str
    intensity: float = Field(default=1.0, ge=0.0, le=1.0)
    repeat_count: int = Field(default=1, ge=1, le=8)
    loop: bool = False
    note: str | None = None


class BodyKeyframe(BaseModel):
    keyframe_name: str | None = None
    pose: BodyPose = Field(default_factory=BodyPose)
    duration_ms: int = Field(default=120, ge=0)
    hold_ms: int = Field(default=0, ge=0)
    transient: bool = False
    semantic_name: str | None = None
    motion_envelope: str | None = None
    kinetics_profile: str | None = None
    note: str | None = None


class AnimationTimeline(BaseModel):
    animation_name: str
    keyframes: list[BodyKeyframe] = Field(default_factory=list)
    repeat_count: int = Field(default=1, ge=1, le=8)
    loop: bool = False
    note: str | None = None


class VirtualBodyPreview(BaseModel):
    gaze_direction: str | None = None
    gaze_summary: str | None = None
    neck_pose: str | None = None
    lid_state: str | None = None
    brow_state: str | None = None
    current_animation_name: str | None = None
    semantic_name: str | None = None
    source_name: str | None = None
    alias_used: bool = False
    alias_source_name: str | None = None
    transition_profile: str | None = None
    safe_idle_compatible: bool = True
    head_yaw: float = Field(default=0.0, ge=-1.0, le=1.0)
    head_pitch: float = Field(default=0.0, ge=-1.0, le=1.0)
    head_roll: float = Field(default=0.0, ge=-1.0, le=1.0)
    eye_yaw: float = Field(default=0.0, ge=-1.0, le=1.0)
    eye_pitch: float = Field(default=0.0, ge=-1.0, le=1.0)
    left_eye_open: float = Field(default=1.0, ge=0.0, le=1.0)
    right_eye_open: float = Field(default=1.0, ge=0.0, le=1.0)
    brow_left: float = Field(default=0.0, ge=0.0, le=1.0)
    brow_right: float = Field(default=0.0, ge=0.0, le=1.0)
    clamp_notes: list[str] = Field(default_factory=list)
    coupling_notes: list[str] = Field(default_factory=list)
    outcome_notes: list[str] = Field(default_factory=list)
    summary: str | None = None


class CharacterPresenceShellState(BaseModel):
    surface_state: str = "idle"
    headline: str = "Idle"
    expression_name: str = "neutral"
    gaze_target: str = "look_forward"
    gesture_name: str | None = None
    animation_name: str | None = None
    motion_hint: str = "settled"
    warmth: float = Field(default=0.5, ge=0.0, le=1.0)
    curiosity: float = Field(default=0.0, ge=0.0, le=1.0)
    listening_active: bool = False
    speaking_active: bool = False
    interruption_active: bool = False
    slow_path_active: bool = False
    message: str | None = None
    detail: str | None = None
    semantic_summary: str | None = None
    source_signals: list[str] = Field(default_factory=list)
    pose: BodyPose = Field(default_factory=BodyPose)


class CharacterSemanticIntent(BaseModel):
    surface_state: str = "idle"
    expression_name: str = "neutral"
    gaze_target: str = "look_forward"
    gesture_name: str | None = None
    animation_name: str | None = None
    motion_hint: str = "settled"
    warmth: float = Field(default=0.5, ge=0.0, le=1.0)
    curiosity: float = Field(default=0.0, ge=0.0, le=1.0)
    listening_active: bool = False
    speaking_active: bool = False
    interruption_active: bool = False
    slow_path_active: bool = False
    safe_idle_requested: bool = False
    detail: str | None = None
    semantic_summary: str | None = None
    source_signals: list[str] = Field(default_factory=list)
    pose: BodyPose = Field(default_factory=BodyPose)
    generated_at: datetime = Field(default_factory=utc_now)


class CharacterProjectionStatus(BaseModel):
    profile: CharacterProjectionProfile = CharacterProjectionProfile.NO_BODY
    avatar_enabled: bool = False
    robot_head_enabled: bool = False
    robot_head_allowed: bool = False
    robot_head_applied: bool = False
    outcome: str = "idle"
    blocked_reason: str | None = None
    semantic_summary: str | None = None
    intent: CharacterSemanticIntent | None = None
    notes: list[str] = Field(default_factory=list)
    updated_at: datetime = Field(default_factory=utc_now)


class CompiledBodyFrame(BaseModel):
    frame_name: str | None = None
    pose: BodyPose = Field(default_factory=BodyPose)
    servo_targets: dict[str, int] = Field(default_factory=dict)
    duration_ms: int = Field(default=120, ge=0)
    hold_ms: int = Field(default=0, ge=0)
    transient: bool = False
    motion_envelope: str | None = None
    kinetics_profile: str | None = None
    requested_speed: int | None = None
    requested_acceleration: int | None = None
    tuning_lane: str | None = None
    transition_profile: str | None = None
    safe_idle_compatible: bool = True
    compiler_notes: list[str] = Field(default_factory=list)
    preview: VirtualBodyPreview | None = None


class CompiledAnimation(BaseModel):
    animation_name: str
    frames: list[CompiledBodyFrame] = Field(default_factory=list)
    loop: bool = False
    total_duration_ms: int = Field(default=0, ge=0)
    kinetics_profiles_used: list[str] = Field(default_factory=list)
    requested_speed: int | None = None
    requested_acceleration: int | None = None
    tuning_lane: str | None = None
    grounding: str | None = None
    recipe_name: str | None = None
    motif_name: str | None = None
    primitive_steps: list[str] = Field(default_factory=list)
    expressive_steps: list[str] = Field(default_factory=list)
    step_kinds: list[str] = Field(default_factory=list)
    sequence_step_count: int | None = None
    structural_action: str | None = None
    expressive_accents: list[str] = Field(default_factory=list)
    stage_count: int | None = None
    returns_to_neutral: bool = False
    primary_actuator_group: str | None = None
    support_actuator_groups: list[str] = Field(default_factory=list)
    max_active_families: int | None = None
    compiler_notes: list[str] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=utc_now)


class ServoHealthRecord(BaseModel):
    servo_id: int
    joint_name: str
    current_position: int | None = None
    target_position: int | None = None
    torque_enabled: bool | None = None
    voltage: int | None = None
    voltage_raw: int | None = None
    voltage_volts: float | None = None
    load: int | None = None
    current: int | None = None
    temperature: int | None = None
    moving: bool | None = None
    power_health_classification: str | None = None
    error_bits: list[str] = Field(default_factory=list)
    last_poll_status: str = "unknown"
    reason_code: str = "unknown"
    status_summary: str | None = None
    last_command_outcome: str | None = None


class BodyMotionControlSettingRecord(BaseModel):
    configured_value: int | None = None
    effective_value: int | None = None
    source: str | None = None
    applied: bool = False
    verified: bool = False
    readback_value: int | None = None
    readback_by_servo: dict[str, int] = Field(default_factory=dict)
    note: str | None = None


class BodyMotionControlAuditRecord(BaseModel):
    profile_safe_speed: int | None = None
    profile_safe_acceleration: int | None = None
    calibration_safe_speed: int | None = None
    calibration_safe_acceleration: int | None = None
    speed: BodyMotionControlSettingRecord = Field(default_factory=BodyMotionControlSettingRecord)
    acceleration: BodyMotionControlSettingRecord = Field(default_factory=BodyMotionControlSettingRecord)
    transport_mode: str | None = None
    transport_confirmed_live: bool | None = None
    addressed_servo_ids: list[int] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class BodyCalibrationJointAuditRecord(BaseModel):
    joint_name: str
    raw_min: int
    raw_max: int
    neutral: int
    profile_raw_min: int
    profile_raw_max: int
    profile_neutral: int
    neutral_margin_percent: float = 0.0
    suspicious_neutral: bool = False
    suspicion_reason: str | None = None
    notes: list[str] = Field(default_factory=list)


class BodyUsableRangeAuditRecord(BaseModel):
    calibration_source_path: str | None = None
    calibration_kind: str | None = None
    using_profile_fallback: bool = False
    suspicious_joint_names: list[str] = Field(default_factory=list)
    joints: list[BodyCalibrationJointAuditRecord] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class BodyCommandOutcomeRecord(BaseModel):
    command_type: str
    requested_action_name: str | None = None
    canonical_action_name: str | None = None
    source_action_name: str | None = None
    outcome_status: str = "accepted"
    accepted: bool = True
    rejected: bool = False
    clamped: bool = False
    transport_mode: str | None = None
    reason_code: str | None = None
    detail: str | None = None
    outcome_notes: list[str] = Field(default_factory=list)
    executed_frame_count: int | None = None
    executed_frame_names: list[str] = Field(default_factory=list)
    per_frame_duration_ms: list[int] = Field(default_factory=list)
    per_frame_hold_ms: list[int] = Field(default_factory=list)
    elapsed_wall_clock_ms: float | None = None
    final_frame_name: str | None = None
    peak_compiled_targets: dict[str, int] = Field(default_factory=dict)
    peak_normalized_pose: dict[str, float] = Field(default_factory=dict)
    tuning_lane: str | None = None
    kinetics_profiles_used: list[str] = Field(default_factory=list)
    grounding: str | None = None
    recipe_name: str | None = None
    motif_name: str | None = None
    primitive_steps: list[str] = Field(default_factory=list)
    expressive_steps: list[str] = Field(default_factory=list)
    step_kinds: list[str] = Field(default_factory=list)
    sequence_step_count: int | None = None
    structural_action: str | None = None
    expressive_accents: list[str] = Field(default_factory=list)
    stage_count: int | None = None
    returned_to_neutral: bool = False
    remaining_margin_percent_by_family: dict[str, float] = Field(default_factory=dict)
    clamp_reasons: list[str] = Field(default_factory=list)
    fault_classification: str | None = None
    power_health_classification: str | None = None
    suspect_voltage_event: bool = False
    readback_implausible: bool = False
    confirmation_read_performed: bool = False
    confirmation_result: str | None = None
    preflight_passed: bool | None = None
    preflight_failure_reason: str | None = None
    idle_voltage_snapshot: dict[str, dict[str, object]] = Field(default_factory=dict)
    motion_control: BodyMotionControlAuditRecord | None = None
    usable_range_audit: BodyUsableRangeAuditRecord | None = None
    generated_at: datetime = Field(default_factory=utc_now)


class BodyCommandAuditRecord(BaseModel):
    command_id: str | None = None
    command_type: str
    semantic_family: str | None = None
    requested_action_name: str | None = None
    canonical_action_name: str | None = None
    source_action_name: str | None = None
    alias_used: bool = False
    alias_source_name: str | None = None
    compiled_targets: dict[str, int] = Field(default_factory=dict)
    clamped_joints: list[str] = Field(default_factory=list)
    before_readback: dict[str, int] = Field(default_factory=dict)
    after_readback: dict[str, int] = Field(default_factory=dict)
    transport_status: dict[str, object] = Field(default_factory=dict)
    health_summary: dict[str, dict[str, object]] = Field(default_factory=dict)
    outcome_status: str = "accepted"
    reason_code: str | None = None
    detail: str | None = None
    fallback_used: bool = False
    report_path: str | None = None
    tuning_path: str | None = None
    executed_frame_count: int | None = None
    executed_frame_names: list[str] = Field(default_factory=list)
    per_frame_duration_ms: list[int] = Field(default_factory=list)
    per_frame_hold_ms: list[int] = Field(default_factory=list)
    elapsed_wall_clock_ms: float | None = None
    final_frame_name: str | None = None
    peak_compiled_targets: dict[str, int] = Field(default_factory=dict)
    peak_normalized_pose: dict[str, float] = Field(default_factory=dict)
    tuning_lane: str | None = None
    kinetics_profiles_used: list[str] = Field(default_factory=list)
    grounding: str | None = None
    recipe_name: str | None = None
    motif_name: str | None = None
    primitive_steps: list[str] = Field(default_factory=list)
    expressive_steps: list[str] = Field(default_factory=list)
    step_kinds: list[str] = Field(default_factory=list)
    sequence_step_count: int | None = None
    structural_action: str | None = None
    expressive_accents: list[str] = Field(default_factory=list)
    stage_count: int | None = None
    returned_to_neutral: bool = False
    remaining_margin_percent_by_family: dict[str, float] = Field(default_factory=dict)
    clamp_reasons: list[str] = Field(default_factory=list)
    fault_classification: str | None = None
    power_health_classification: str | None = None
    suspect_voltage_event: bool = False
    readback_implausible: bool = False
    confirmation_read_performed: bool = False
    confirmation_result: str | None = None
    preflight_passed: bool | None = None
    preflight_failure_reason: str | None = None
    idle_voltage_snapshot: dict[str, dict[str, object]] = Field(default_factory=dict)
    motion_control: BodyMotionControlAuditRecord | None = None
    usable_range_audit: BodyUsableRangeAuditRecord | None = None
    notes: list[str] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=utc_now)


class MotionKineticsProfile(BaseModel):
    speed: int | None = Field(default=None, ge=0, le=1023)
    acceleration: int | None = Field(default=None, ge=0, le=150)
    duration_scale: float = Field(default=1.0, ge=0.1, le=4.0)
    hold_scale: float = Field(default=1.0, ge=0.0, le=4.0)
    notes: list[str] = Field(default_factory=list)


class SignedAxisBand(BaseModel):
    negative_limit: float = Field(default=1.0, ge=0.0, le=1.0)
    positive_limit: float = Field(default=1.0, ge=0.0, le=1.0)


class RatioDeviationBand(BaseModel):
    negative_limit: float = Field(default=1.0, ge=0.0, le=1.0)
    positive_limit: float = Field(default=1.0, ge=0.0, le=1.0)
    transient_negative_limit: float | None = Field(default=None, ge=0.0, le=1.0)
    transient_positive_limit: float | None = Field(default=None, ge=0.0, le=1.0)


class OperatingBandPolicy(BaseModel):
    head_yaw_ratio: float = Field(default=1.0, ge=0.0, le=1.0)
    neck_pitch_ratio: float = Field(default=1.0, ge=0.0, le=1.0)
    neck_tilt_ratio: float = Field(default=1.0, ge=0.0, le=1.0)
    neck_tilt_negative_reference_raw: int | None = None
    neck_tilt_positive_reference_raw: int | None = None
    eye_yaw_ratio: float = Field(default=1.0, ge=0.0, le=1.0)
    eye_pitch_ratio: float = Field(default=1.0, ge=0.0, le=1.0)
    upper_lid_held_ratio: float = Field(default=1.0, ge=0.0, le=1.0)
    lower_lid_held_ratio: float = Field(default=1.0, ge=0.0, le=1.0)
    brow_held_ratio: float = Field(default=1.0, ge=0.0, le=1.0)
    transient_lid_ratio: float = Field(default=1.0, ge=0.0, le=1.0)
    transient_brow_ratio: float = Field(default=1.0, ge=0.0, le=1.0)
    notes: list[str] = Field(default_factory=list)


class DerivedOperatingBand(BaseModel):
    head_yaw: SignedAxisBand = Field(default_factory=SignedAxisBand)
    head_pitch: SignedAxisBand = Field(default_factory=SignedAxisBand)
    head_roll: SignedAxisBand = Field(default_factory=SignedAxisBand)
    eye_yaw: SignedAxisBand = Field(default_factory=SignedAxisBand)
    eye_pitch: SignedAxisBand = Field(default_factory=SignedAxisBand)
    upper_lid: RatioDeviationBand = Field(default_factory=RatioDeviationBand)
    lower_lid: RatioDeviationBand = Field(default_factory=RatioDeviationBand)
    brow: RatioDeviationBand = Field(default_factory=RatioDeviationBand)
    notes: list[str] = Field(default_factory=list)


class SemanticActionDescriptor(BaseModel):
    family: str
    canonical_name: str
    aliases: list[str] = Field(default_factory=list)
    smoke_safe: bool = False
    rollout_stage: str | None = None
    description: str | None = None
    tuning_override_active: bool = False
    grounding: str | None = None
    primary_actuator_group: str | None = None
    support_actuator_groups: list[str] = Field(default_factory=list)
    returns_to_neutral: bool = False
    max_active_families: int | None = None
    tempo_variant: str | None = None
    implementation_kind: str | None = None
    hardware_support_status: str | None = None
    evidence_source: str | None = None
    structural_units_used: list[str] = Field(default_factory=list)
    expressive_units_used: list[str] = Field(default_factory=list)
    hold_supported: bool = False
    release_policy: str | None = None
    sequencing_rule: str | None = None
    safe_tuning_lane: str | None = None
    alias_source: str | None = None


class GroundedExpressionCatalogEntry(BaseModel):
    canonical_name: str
    family: str
    implementation_kind: str
    hardware_support_status: str = "supported"
    evidence_source: str | None = None
    description: str | None = None
    sequencing_rule: str | None = None
    hold_supported: bool = False
    release_policy: str | None = None
    safe_tuning_lane: str | None = None
    structural_units_used: list[str] = Field(default_factory=list)
    expressive_units_used: list[str] = Field(default_factory=list)
    aliases: list[str] = Field(default_factory=list)
    alias_source: str | None = None
    constraints: list[str] = Field(default_factory=list)


class GroundedExpressionCatalogExport(BaseModel):
    schema_version: str = "blink_grounded_expression_catalog/v1"
    supported_structural_units: list[str] = Field(default_factory=list)
    supported_expressive_units: list[str] = Field(default_factory=list)
    supported_persistent_states: list[str] = Field(default_factory=list)
    supported_motifs: list[str] = Field(default_factory=list)
    alias_mapping: dict[str, str] = Field(default_factory=dict)
    entries: list[GroundedExpressionCatalogEntry] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=utc_now)


class MotionEnvelope(BaseModel):
    head_yaw: float = Field(default=1.0, ge=0.0, le=1.0)
    head_pitch: float = Field(default=1.0, ge=0.0, le=1.0)
    head_roll: float = Field(default=1.0, ge=0.0, le=1.0)
    eye_yaw: float = Field(default=1.0, ge=0.0, le=1.0)
    eye_pitch: float = Field(default=1.0, ge=0.0, le=1.0)
    upper_lid_deviation: float = Field(default=1.0, ge=0.0, le=1.0)
    lower_lid_deviation: float = Field(default=1.0, ge=0.0, le=1.0)
    brow_deviation: float = Field(default=1.0, ge=0.0, le=1.0)
    transient_upper_lid_deviation: float | None = Field(default=None, ge=0.0, le=1.0)
    transient_lower_lid_deviation: float | None = Field(default=None, ge=0.0, le=1.0)
    transient_brow_deviation: float | None = Field(default=None, ge=0.0, le=1.0)
    pitch_roll_budget: float = Field(default=1.0, ge=0.0, le=2.0)


class SemanticActionTuningOverride(BaseModel):
    intensity_multiplier: float = Field(default=1.0, ge=0.0, le=2.0)
    pose_offsets: dict[str, float] = Field(default_factory=dict)
    upper_lid_coupling_scale: float | None = Field(default=None, ge=0.0, le=2.0)
    brow_asymmetry_correction: float | None = Field(default=None, ge=0.0, le=1.0)
    neck_pitch_weight: float | None = Field(default=None, ge=0.0, le=2.0)
    neck_roll_weight: float | None = Field(default=None, ge=0.0, le=2.0)
    motion_envelope: str | None = None
    kinetics_profile: str | None = None
    notes: list[str] = Field(default_factory=list)


class SemanticTuningRecord(BaseModel):
    schema_version: str = "blink_head_semantic_tuning/v1"
    profile_name: str
    calibration_path: str | None = None
    tuning_lane: str = "default_live"
    eye_lid_coupling_coefficient: float = Field(default=0.2, ge=0.0, le=1.0)
    eye_lid_coupling_threshold: float = Field(default=0.15, ge=0.0, le=1.0)
    brow_asymmetry_correction: float = Field(default=0.0, ge=0.0, le=1.0)
    neck_pitch_weight: float = Field(default=1.0, ge=0.0, le=2.0)
    neck_roll_weight: float = Field(default=1.0, ge=0.0, le=2.0)
    default_motion_envelope: str = "social"
    default_kinetics_profile: str = "social_shift"
    operating_band_policy: OperatingBandPolicy = Field(default_factory=OperatingBandPolicy)
    motion_envelopes: dict[str, MotionEnvelope] = Field(default_factory=dict)
    motion_kinetics_profiles: dict[str, MotionKineticsProfile] = Field(default_factory=dict)
    action_overrides: dict[str, SemanticActionTuningOverride] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)
    updated_at: datetime = Field(default_factory=utc_now)


class SemanticTeacherReviewRecord(BaseModel):
    review_id: str
    action: str
    family: str
    review: str
    note: str | None = None
    proposed_tuning_delta: dict[str, object] = Field(default_factory=dict)
    applied_tuning: bool = False
    tuning_path: str | None = None
    latest_command_audit: BodyCommandAuditRecord | None = None
    generated_at: datetime = Field(default_factory=utc_now)


class BodyCapabilityProfile(BaseModel):
    driver_mode: BodyDriverMode = BodyDriverMode.VIRTUAL
    character_projection_profile: CharacterProjectionProfile = CharacterProjectionProfile.NO_BODY
    head_profile_name: str | None = None
    head_profile_path: str | None = None
    servo_family: str | None = None
    servo_count: int = 0
    present: bool = False
    connected: bool = False
    transport_mode: str | None = None
    transport_healthy: bool = False
    transport_error: str | None = None
    transport_reason_code: str | None = None
    transport_confirmed_live: bool | None = None
    transport_port: str | None = None
    transport_baud_rate: int | None = None
    transport_boundary_version: str | None = None
    supports_expression: bool = True
    supports_gaze: bool = True
    supports_gesture: bool = True
    supports_animation: bool = True
    supports_virtual_preview: bool = False
    supports_serial_transport: bool = False
    supports_readback: bool = False
    safe_idle_supported: bool = True
    calibration_path: str | None = None
    calibration_version: str | None = None
    calibration_status: str | None = None
    live_motion_enabled: bool = False
    supported_gaze_targets: list[str] = Field(default_factory=list)
    supported_expressions: list[str] = Field(default_factory=list)
    supported_gestures: list[str] = Field(default_factory=list)
    supported_animations: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class BodyState(BaseModel):
    driver_mode: BodyDriverMode = BodyDriverMode.VIRTUAL
    character_projection: CharacterProjectionStatus | None = None
    head_profile_name: str | None = None
    head_profile_path: str | None = None
    head_profile_version: str | None = None
    connected: bool = False
    present: bool = False
    transport_mode: str | None = None
    transport_healthy: bool = False
    transport_error: str | None = None
    transport_reason_code: str | None = None
    transport_confirmed_live: bool | None = None
    transport_port: str | None = None
    transport_baud_rate: int | None = None
    calibration_path: str | None = None
    calibration_version: str | None = None
    calibration_status: str | None = None
    live_motion_enabled: bool = False
    safe_idle_active: bool = False
    active_expression: str | None = None
    attention_state: str | None = None
    gaze_target: str | None = None
    last_gesture: str | None = None
    last_animation: str | None = None
    pose: BodyPose = Field(default_factory=BodyPose)
    servo_targets: dict[str, int] = Field(default_factory=dict)
    feedback_positions: dict[str, int] = Field(default_factory=dict)
    feedback_status: dict[str, int] = Field(default_factory=dict)
    servo_health: dict[str, ServoHealthRecord] = Field(default_factory=dict)
    active_timeline: AnimationTimeline | None = None
    current_frame: CompiledBodyFrame | None = None
    compiled_animation: CompiledAnimation | None = None
    virtual_preview: VirtualBodyPreview | None = None
    last_command_outcome: BodyCommandOutcomeRecord | None = None
    latest_command_audit: BodyCommandAuditRecord | None = None
    body_fault_classification: str | None = None
    body_fault_detail: str | None = None
    power_health_classification: str | None = None
    preflight_passed: bool | None = None
    preflight_failure_reason: str | None = None
    idle_voltage_snapshot: dict[str, dict[str, object]] = Field(default_factory=dict)
    live_motion_armed: bool = False
    arm_expires_at: datetime | None = None
    last_transport_poll_at: datetime | None = None
    clamp_notes: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    updated_at: datetime = Field(default_factory=utc_now)


__all__ = [
    "AnimationRequest",
    "AnimationTimeline",
    "CharacterProjectionStatus",
    "CharacterSemanticIntent",
    "CharacterPresenceShellState",
    "BodyCommandAuditRecord",
    "BodyCalibrationJointAuditRecord",
    "BodyCommandOutcomeRecord",
    "BodyMotionControlAuditRecord",
    "BodyMotionControlSettingRecord",
    "BodyDriverMode",
    "BodyCapabilityProfile",
    "BodyKeyframe",
    "BodyPose",
    "BodyState",
    "BodyUsableRangeAuditRecord",
    "CompiledAnimation",
    "CompiledBodyFrame",
    "ExpressionRequest",
    "GazeRequest",
    "GroundedExpressionCatalogEntry",
    "GroundedExpressionCatalogExport",
    "GestureRequest",
    "HeadCalibrationRecord",
    "HeadCouplingRule",
    "HeadJointProfile",
    "HeadProfile",
    "JointCalibrationRecord",
    "MotionKineticsProfile",
    "MotionEnvelope",
    "OperatingBandPolicy",
    "DerivedOperatingBand",
    "RatioDeviationBand",
    "ServoHealthRecord",
    "SemanticActionDescriptor",
    "SemanticActionTuningOverride",
    "SemanticTeacherReviewRecord",
    "SemanticTuningRecord",
    "SignedAxisBand",
    "VirtualBodyPreview",
]
