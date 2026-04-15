.PHONY: install test validate acceptance-inventory acceptance-quick acceptance-full acceptance-rc acceptance-manual-local acceptance-hardware acceptance-investor-show-quick acceptance-investor-show-full acceptance-investor-show-hardware run-brain run-console run-edge run-sim dry-run smoke demo-checks multimodal-demo-checks tethered-smoke demo-up demo-reset demo-status investor-show-dry investor-show investor-show-virtual investor-show-cue-smoke investor-show-v3 investor-show-v3-live investor-show-v4 investor-show-v4-live investor-show-v5 investor-show-v5-live investor-show-v6 investor-show-v6-live investor-show-v7 investor-show-v7-live investor-show-v8 investor-show-v8-live investor-show-reset servo-showcase-dry servo-showcase-live servo-showcase-bench motion-config-audit usable-range-audit serial-doctor serial-bench serial-neutral serial-companion action-plane-validate browser-runtime-smoke workflow-replay-smoke action-export-inspect local-companion-certify local-companion-burn-in local-companion-failure-drills local-companion-soak local-companion-stress stabilize-fast stabilize-full stabilize-live-local

UV := uv
BLINK_SERVO_BAUD ?= 1000000
BLINK_HEAD_PROFILE ?= src/embodied_stack/body/profiles/robot_head_v1.json
BLINK_HEAD_CALIBRATION ?= runtime/calibrations/robot_head_live_v1.json
SERIAL_IDS ?= 1-11
SERIAL_JOINT ?= head_yaw
SERIAL_JOINT_DELTA ?= 40
SERIAL_SEMANTIC_ACTION ?= look_left
SERIAL_PORT_FLAG = $(if $(BLINK_SERIAL_PORT),--port $(BLINK_SERIAL_PORT),)
LIVE_WRITE_FLAG = $(if $(filter 1 true yes on,$(BLINK_CONFIRM_LIVE_WRITE)),--confirm-live-write,)

install:
	$(UV) sync --dev

test:
	$(UV) run pytest

validate:
	$(UV) run pytest
	PYTHONPATH=src $(UV) run python -m embodied_stack.sim.scenario_runner --dry-run

acceptance-inventory:
	$(UV) run blink-acceptance inventory

acceptance-quick:
	$(UV) run blink-acceptance quick

acceptance-full:
	$(UV) run blink-acceptance full

acceptance-rc:
	$(UV) run blink-acceptance rc

acceptance-manual-local:
	$(UV) run blink-acceptance manual-local

acceptance-hardware:
	$(UV) run blink-acceptance hardware

acceptance-investor-show-quick:
	$(UV) run blink-acceptance investor-show-quick

acceptance-investor-show-full:
	$(UV) run blink-acceptance investor-show-full

acceptance-investor-show-hardware:
	$(UV) run blink-acceptance investor-show-hardware

run-brain:
	$(UV) run uvicorn embodied_stack.brain.app:app --reload --port 8000

run-console: run-brain

run-edge:
	$(UV) run uvicorn embodied_stack.edge.app:app --reload --port 8010

run-sim:
	PYTHONPATH=src $(UV) run python -m embodied_stack.sim.scenario_runner

dry-run:
	PYTHONPATH=src $(UV) run python -m embodied_stack.sim.scenario_runner --dry-run

smoke:
	PYTHONPATH=src $(UV) run python -m embodied_stack.demo.smoke

demo-checks:
	PYTHONPATH=src $(UV) run python -m embodied_stack.demo.checks

multimodal-demo-checks:
	PYTHONPATH=src $(UV) run python -m embodied_stack.demo.multimodal_checks

tethered-smoke:
	PYTHONPATH=src $(UV) run python -m embodied_stack.demo.tethered

demo-up:
	PYTHONPATH=src $(UV) run python -m embodied_stack.demo.tethered serve

demo-reset:
	PYTHONPATH=src $(UV) run python -m embodied_stack.demo.tethered reset

demo-status:
	PYTHONPATH=src $(UV) run python -m embodied_stack.demo.tethered status

investor-show-dry:
	BLINK_BODY_SEMANTIC_TUNING_PATH=runtime/body/semantic_tuning/robot_head_investor_show_v8.json $(UV) run local-companion performance-dry-run investor_expressive_motion_v8 --proof-backend-mode deterministic_show

investor-show:
	BLINK_BODY_SEMANTIC_TUNING_PATH=runtime/body/semantic_tuning/robot_head_investor_show_v8.json $(UV) run local-companion performance-show investor_expressive_motion_v8 --proof-backend-mode deterministic_show --reset-runtime

investor-show-virtual:
	BLINK_RUNTIME_MODE=desktop_virtual_body BLINK_BODY_DRIVER=virtual BLINK_BODY_SEMANTIC_TUNING_PATH=runtime/body/semantic_tuning/robot_head_investor_show_v8.json $(UV) run local-companion performance-show investor_expressive_motion_v8 --proof-backend-mode deterministic_show --reset-runtime

investor-show-cue-smoke:
	BLINK_BODY_SEMANTIC_TUNING_PATH=runtime/body/semantic_tuning/robot_head_investor_show_v8.json $(UV) run local-companion performance-show investor_expressive_motion_v8 --cue guarded_close_right_run --cue guarded_close_left_run --cue playful_peek_right_run --cue bright_reengage_run --no-narration --proof-backend-mode deterministic_show --reset-runtime

investor-show-v3:
	BLINK_BODY_SEMANTIC_TUNING_PATH=runtime/body/semantic_tuning/robot_head_investor_show_v3.json $(UV) run local-companion performance-show investor_head_motion_v3 --proof-backend-mode deterministic_show --reset-runtime

investor-show-v3-live:
	PYTHONPATH=src $(UV) run python -m embodied_stack.body.calibration --transport live_serial $(SERIAL_PORT_FLAG) --baud $(BLINK_SERVO_BAUD) --profile $(BLINK_HEAD_PROFILE) --calibration $(BLINK_HEAD_CALIBRATION) arm-live-motion --ttl-seconds 300
	BLINK_RUNTIME_MODE=desktop_serial_body BLINK_BODY_DRIVER=serial BLINK_SERIAL_TRANSPORT=live_serial BLINK_SERIAL_PORT="$(BLINK_SERIAL_PORT)" BLINK_SERVO_BAUD="$(BLINK_SERVO_BAUD)" BLINK_HEAD_PROFILE="$(BLINK_HEAD_PROFILE)" BLINK_HEAD_CALIBRATION="$(BLINK_HEAD_CALIBRATION)" BLINK_BODY_SEMANTIC_TUNING_PATH=runtime/body/semantic_tuning/robot_head_investor_show_v3.json $(UV) run local-companion performance-show investor_head_motion_v3 --proof-backend-mode deterministic_show --reset-runtime

investor-show-v4:
	BLINK_BODY_SEMANTIC_TUNING_PATH=runtime/body/semantic_tuning/robot_head_investor_show_v4.json $(UV) run local-companion performance-show investor_eye_motion_v4 --proof-backend-mode deterministic_show --reset-runtime

investor-show-v4-live:
	PYTHONPATH=src $(UV) run python -m embodied_stack.body.calibration --transport live_serial $(SERIAL_PORT_FLAG) --baud $(BLINK_SERVO_BAUD) --profile $(BLINK_HEAD_PROFILE) --calibration $(BLINK_HEAD_CALIBRATION) arm-live-motion --ttl-seconds 300
	BLINK_RUNTIME_MODE=desktop_serial_body BLINK_BODY_DRIVER=serial BLINK_SERIAL_TRANSPORT=live_serial BLINK_SERIAL_PORT="$(BLINK_SERIAL_PORT)" BLINK_SERVO_BAUD="$(BLINK_SERVO_BAUD)" BLINK_HEAD_PROFILE="$(BLINK_HEAD_PROFILE)" BLINK_HEAD_CALIBRATION="$(BLINK_HEAD_CALIBRATION)" BLINK_BODY_SEMANTIC_TUNING_PATH=runtime/body/semantic_tuning/robot_head_investor_show_v4.json $(UV) run local-companion performance-show investor_eye_motion_v4 --proof-backend-mode deterministic_show --reset-runtime

investor-show-v5:
	BLINK_BODY_SEMANTIC_TUNING_PATH=runtime/body/semantic_tuning/robot_head_investor_show_v5.json $(UV) run local-companion performance-show investor_lid_motion_v5 --proof-backend-mode deterministic_show --reset-runtime

investor-show-v5-live:
	PYTHONPATH=src $(UV) run python -m embodied_stack.body.calibration --transport live_serial $(SERIAL_PORT_FLAG) --baud $(BLINK_SERVO_BAUD) --profile $(BLINK_HEAD_PROFILE) --calibration $(BLINK_HEAD_CALIBRATION) arm-live-motion --ttl-seconds 300
	BLINK_RUNTIME_MODE=desktop_serial_body BLINK_BODY_DRIVER=serial BLINK_SERIAL_TRANSPORT=live_serial BLINK_SERIAL_PORT="$(BLINK_SERIAL_PORT)" BLINK_SERVO_BAUD="$(BLINK_SERVO_BAUD)" BLINK_HEAD_PROFILE="$(BLINK_HEAD_PROFILE)" BLINK_HEAD_CALIBRATION="$(BLINK_HEAD_CALIBRATION)" BLINK_BODY_SEMANTIC_TUNING_PATH=runtime/body/semantic_tuning/robot_head_investor_show_v5.json $(UV) run local-companion performance-show investor_lid_motion_v5 --proof-backend-mode deterministic_show --reset-runtime

investor-show-v6:
	BLINK_BODY_SEMANTIC_TUNING_PATH=runtime/body/semantic_tuning/robot_head_investor_show_v6.json $(UV) run local-companion performance-show investor_brow_motion_v6 --proof-backend-mode deterministic_show --reset-runtime

investor-show-v6-live:
	PYTHONPATH=src $(UV) run python -m embodied_stack.body.calibration --transport live_serial $(SERIAL_PORT_FLAG) --baud $(BLINK_SERVO_BAUD) --profile $(BLINK_HEAD_PROFILE) --calibration $(BLINK_HEAD_CALIBRATION) arm-live-motion --ttl-seconds 300
	BLINK_RUNTIME_MODE=desktop_serial_body BLINK_BODY_DRIVER=serial BLINK_SERIAL_TRANSPORT=live_serial BLINK_SERIAL_PORT="$(BLINK_SERIAL_PORT)" BLINK_SERVO_BAUD="$(BLINK_SERVO_BAUD)" BLINK_HEAD_PROFILE="$(BLINK_HEAD_PROFILE)" BLINK_HEAD_CALIBRATION="$(BLINK_HEAD_CALIBRATION)" BLINK_BODY_SEMANTIC_TUNING_PATH=runtime/body/semantic_tuning/robot_head_investor_show_v6.json $(UV) run local-companion performance-show investor_brow_motion_v6 --proof-backend-mode deterministic_show --reset-runtime

investor-show-v7:
	BLINK_BODY_SEMANTIC_TUNING_PATH=runtime/body/semantic_tuning/robot_head_investor_show_v7.json $(UV) run local-companion performance-show investor_neck_motion_v7 --proof-backend-mode deterministic_show --reset-runtime

investor-show-v7-live:
	PYTHONPATH=src $(UV) run python -m embodied_stack.body.calibration --transport live_serial $(SERIAL_PORT_FLAG) --baud $(BLINK_SERVO_BAUD) --profile $(BLINK_HEAD_PROFILE) --calibration $(BLINK_HEAD_CALIBRATION) arm-live-motion --ttl-seconds 300
	BLINK_RUNTIME_MODE=desktop_serial_body BLINK_BODY_DRIVER=serial BLINK_SERIAL_TRANSPORT=live_serial BLINK_SERIAL_PORT="$(BLINK_SERIAL_PORT)" BLINK_SERVO_BAUD="$(BLINK_SERVO_BAUD)" BLINK_HEAD_PROFILE="$(BLINK_HEAD_PROFILE)" BLINK_HEAD_CALIBRATION="$(BLINK_HEAD_CALIBRATION)" BLINK_BODY_SEMANTIC_TUNING_PATH=runtime/body/semantic_tuning/robot_head_investor_show_v7.json $(UV) run local-companion performance-show investor_neck_motion_v7 --proof-backend-mode deterministic_show --reset-runtime

investor-show-v8:
	BLINK_BODY_SEMANTIC_TUNING_PATH=runtime/body/semantic_tuning/robot_head_investor_show_v8.json $(UV) run local-companion performance-show investor_expressive_motion_v8 --proof-backend-mode deterministic_show --reset-runtime

investor-show-v8-live:
	PYTHONPATH=src $(UV) run python -m embodied_stack.body.calibration --transport live_serial $(SERIAL_PORT_FLAG) --baud $(BLINK_SERVO_BAUD) --profile $(BLINK_HEAD_PROFILE) --calibration $(BLINK_HEAD_CALIBRATION) arm-live-motion --ttl-seconds 300
	BLINK_RUNTIME_MODE=desktop_serial_body BLINK_BODY_DRIVER=serial BLINK_SERIAL_TRANSPORT=live_serial BLINK_SERIAL_PORT="$(BLINK_SERIAL_PORT)" BLINK_SERVO_BAUD="$(BLINK_SERVO_BAUD)" BLINK_HEAD_PROFILE="$(BLINK_HEAD_PROFILE)" BLINK_HEAD_CALIBRATION="$(BLINK_HEAD_CALIBRATION)" BLINK_BODY_SEMANTIC_TUNING_PATH=runtime/body/semantic_tuning/robot_head_investor_show_v8.json $(UV) run local-companion performance-show investor_expressive_motion_v8 --proof-backend-mode deterministic_show --reset-runtime

investor-show-reset:
	$(UV) run local-companion reset --no-edge-reset

servo-showcase-dry:
	$(UV) run local-companion performance-dry-run robot_head_servo_range_showcase_v1

servo-showcase-live:
	PYTHONPATH=src $(UV) run python -m embodied_stack.body.calibration --transport live_serial $(SERIAL_PORT_FLAG) --baud $(BLINK_SERVO_BAUD) --profile $(BLINK_HEAD_PROFILE) --calibration $(BLINK_HEAD_CALIBRATION) arm-live-motion
	BLINK_RUNTIME_MODE=desktop_serial_body BLINK_BODY_DRIVER=serial BLINK_SERIAL_TRANSPORT=live_serial BLINK_SERIAL_PORT="$(BLINK_SERIAL_PORT)" BLINK_SERVO_BAUD="$(BLINK_SERVO_BAUD)" BLINK_HEAD_PROFILE="$(BLINK_HEAD_PROFILE)" BLINK_HEAD_CALIBRATION="$(BLINK_HEAD_CALIBRATION)" $(UV) run local-companion performance-show robot_head_servo_range_showcase_v1 --reset-runtime

servo-showcase-bench:
	@if [ "$(BLINK_CONFIRM_LIVE_WRITE)" != "1" ] && [ "$(BLINK_CONFIRM_LIVE_WRITE)" != "true" ]; then echo "Set BLINK_CONFIRM_LIVE_WRITE=1 before running the live servo showcase bench path."; exit 1; fi
	PYTHONPATH=src $(UV) run python -m embodied_stack.body.calibration --transport live_serial $(SERIAL_PORT_FLAG) --baud $(BLINK_SERVO_BAUD) --profile $(BLINK_HEAD_PROFILE) --calibration $(BLINK_HEAD_CALIBRATION) range-demo --sequence servo_range_showcase_v1 --preset servo_range_showcase_joint_envelope_v1 $(LIVE_WRITE_FLAG)

motion-config-audit:
	PYTHONPATH=src $(UV) run python -m embodied_stack.body.calibration --transport live_serial $(SERIAL_PORT_FLAG) --baud $(BLINK_SERVO_BAUD) --profile $(BLINK_HEAD_PROFILE) --calibration $(BLINK_HEAD_CALIBRATION) motion-config

investor-power-preflight:
	PYTHONPATH=src $(UV) run python -m embodied_stack.body.calibration --transport live_serial $(SERIAL_PORT_FLAG) --baud $(BLINK_SERVO_BAUD) --profile $(BLINK_HEAD_PROFILE) --calibration $(BLINK_HEAD_CALIBRATION) power-preflight

usable-range-audit:
	PYTHONPATH=src $(UV) run python -m embodied_stack.body.calibration --profile $(BLINK_HEAD_PROFILE) --calibration $(BLINK_HEAD_CALIBRATION) usable-range --sequence servo_range_showcase_v1 --preset servo_range_showcase_joint_envelope_v1

action-plane-validate:
	$(UV) run pytest tests/action_plane tests/brain/test_operator_console.py tests/brain/test_agent_os_tools.py tests/desktop/test_cli.py tests/demo/test_action_flywheel.py

browser-runtime-smoke:
	$(UV) run pytest tests/action_plane/test_browser_runtime.py -q

workflow-replay-smoke:
	$(UV) run pytest tests/action_plane/test_workflow_runtime.py tests/demo/test_action_flywheel.py -q

action-export-inspect:
	PYTHONPATH=src $(UV) run python -m embodied_stack.demo.action_plane_inspect

local-companion-certify:
	$(UV) run local-companion-certify

local-companion-burn-in:
	$(UV) run local-companion-burn-in

local-companion-failure-drills:
	$(UV) run local-companion-failure-drills

local-companion-soak:
	$(UV) run local-companion-burn-in

local-companion-stress:
	$(UV) run local-companion-failure-drills
	$(UV) run local-companion-burn-in

stabilize-fast: acceptance-quick

stabilize-full: acceptance-full

stabilize-live-local: acceptance-manual-local

serial-doctor:
	$(UV) run blink-serial-doctor $(SERIAL_PORT_FLAG) --baud $(BLINK_SERVO_BAUD) --ids $(SERIAL_IDS) --auto-scan-baud

serial-bench:
	@if [ "$(BLINK_CONFIRM_LIVE_WRITE)" != "1" ] && [ "$(BLINK_CONFIRM_LIVE_WRITE)" != "true" ]; then echo "Set BLINK_CONFIRM_LIVE_WRITE=1 to run live serial bench motion."; exit 1; fi
	$(UV) run blink-serial-bench --transport live_serial $(SERIAL_PORT_FLAG) --baud $(BLINK_SERVO_BAUD) --profile $(BLINK_HEAD_PROFILE) --calibration $(BLINK_HEAD_CALIBRATION) --ids $(SERIAL_IDS) --joint $(SERIAL_JOINT) --joint-delta $(SERIAL_JOINT_DELTA) --semantic-action $(SERIAL_SEMANTIC_ACTION) $(LIVE_WRITE_FLAG)

serial-neutral:
	@if [ "$(BLINK_CONFIRM_LIVE_WRITE)" != "1" ] && [ "$(BLINK_CONFIRM_LIVE_WRITE)" != "true" ]; then echo "Set BLINK_CONFIRM_LIVE_WRITE=1 before writing live neutral."; exit 1; fi
	PYTHONPATH=src $(UV) run python -m embodied_stack.body.calibration --transport live_serial $(SERIAL_PORT_FLAG) --baud $(BLINK_SERVO_BAUD) --profile $(BLINK_HEAD_PROFILE) --calibration $(BLINK_HEAD_CALIBRATION) write-neutral --duration-ms 800 $(LIVE_WRITE_FLAG)

serial-companion:
	BLINK_RUNTIME_MODE=desktop_serial_body BLINK_BODY_DRIVER=serial BLINK_SERIAL_TRANSPORT=live_serial BLINK_SERIAL_PORT="$(BLINK_SERIAL_PORT)" BLINK_SERVO_BAUD="$(BLINK_SERVO_BAUD)" BLINK_HEAD_PROFILE="$(BLINK_HEAD_PROFILE)" BLINK_HEAD_CALIBRATION="$(BLINK_HEAD_CALIBRATION)" $(UV) run blink-appliance
