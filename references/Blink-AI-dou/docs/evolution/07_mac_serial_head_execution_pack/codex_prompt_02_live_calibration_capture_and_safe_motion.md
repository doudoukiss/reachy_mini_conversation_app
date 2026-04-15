# Codex Prompt 02 — 构建 live calibration、motion gate 与安全动作 smoke

先阅读：

- `AGENTS.md`
- `PLAN.md`
- `docs/embodiment_runtime.md`
- `docs/development_guide.md`
- `src/embodied_stack/body/driver.py`
- `src/embodied_stack/body/calibration.py`
- `src/embodied_stack/body/serial/driver.py`
- `src/embodied_stack/body/serial/health.py`
- `src/embodied_stack/shared/contracts/body.py`
- `src/embodied_stack/body/profiles/robot_head_v1.json`

然后实现 **真实 calibration + live motion gate + safe bench motion** 的完整工作流。

## 背景

当前仓库已经有 live motion gate，但还缺少顺手的开发体验。
现在需要把真实头部从“可读”推进到“可安全小幅动作”。

硬件事实：
- 11 个 STS3032
- 0–4095 一圈
- 2047 是中位
- profile 中已有真实 joint / id / range / direction baseline

## 你要构建的内容

1. 完整的 calibration capture/save 流程：
   - 把 template calibration 升级为 saved/captured calibration
   - 默认保存到 `runtime/calibrations/robot_head_live_v1.json`
   - 清楚记录 transport、port、baud、joint_records、notes、timestamps

2. 明确的 motion arm 机制：
   - 没有 arm，不允许 live motion
   - 可以通过 CLI `--arm-live-motion`
   - 建议加入 arm 过期或 session-bound 机制
   - console/runtime 也要能看到 arm state

3. 新增 safe motion 命令：
   - `move-joint`
   - `sync-move`
   - `write-neutral`
   - `safe-idle`
   - `torque-on`
   - `torque-off`
   - `semantic-smoke`（可先做最小版本）

4. 所有 live target 必须：
   - 经过 joint range clamp
   - 使用已保存 calibration
   - 清楚返回 rejected / clamped / sent / failed 状态

5. motion artifact：
   - `runtime/serial/motion_reports/*.json`
   - 每次动作记录：
     - command family
     - target(s)
     - clamped result
     - before/after readback
     - health
     - request/response hex
     - outcome
     - notes

6. 丰富 failure message：
   - calibration_template
   - transport_unhealthy
   - missing_port
   - no_arm
   - out_of_range
   - timeout
   - power_suspected
   - reply_id_mismatch
   - write_failed

7. 文档和 runbook 更新

## 约束

- 保持 live motion gate 严格
- 没有 saved calibration 时，不允许 live motion
- 不要直接让 AI 自动大范围动作
- 必须保留 dry_run / fixture_replay 下的测试覆盖
- 不要破坏现有 bodyless / virtual_body 路径

## Definition of Done

- 能保存真实 calibration 文件
- 能在 Mac 上做单关节小幅动作
- 能做小范围 sync move
- 失败时能明确告诉开发者原因
- 有可留档 artifact

## Validation

至少运行：

```bash
uv run pytest
PYTHONPATH=src uv run python -m embodied_stack.body.calibration --transport dry_run write-neutral
```

并给出 live serial 实际命令示例，但不要假装硬件一定在线。

## 最终回复格式

请返回：
1. 改了哪些文件
2. live calibration 怎么保存
3. arm 机制怎么工作
4. 新增了哪些 bench motion 命令
5. 哪些风险仍需人工 bench 验证
