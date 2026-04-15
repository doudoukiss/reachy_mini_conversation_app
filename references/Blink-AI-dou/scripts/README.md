# Scripts

The repository keeps scripts intentionally light.

Main runnable entry point:
- `PYTHONPATH=src uv run python -m embodied_stack.sim.scenario_runner`

Operational launcher entry points now live under the Python package:

- `PYTHONPATH=src uv run python -m embodied_stack.demo.tethered serve`
- `PYTHONPATH=src uv run python -m embodied_stack.demo.tethered status`
- `PYTHONPATH=src uv run python -m embodied_stack.demo.tethered reset`

Maintained shell helper:

- `bash scripts/serial_head_live_observation.sh`

That script is the operator-facing real-head observation sequence for the current Mac serial setup. It exercises direct probes, sync groups, and semantic actions sequentially and writes artifacts under `runtime/serial/manual_validation/`.
