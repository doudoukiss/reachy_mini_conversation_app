# 仓库改动地图（Codex 实施范围）

## 1. 必改模块

### `src/embodied_stack/body/serial/transport.py`
用于增强：
- live serial doctor 支持
- richer request/response history
- 更好的 failure classification
- 可选 port 枚举辅助

### `src/embodied_stack/body/serial/health.py`
用于增强：
- richer sync read
- 电压 / 温度 / 速度 / 负载 / moving / 状态位
- 更贴近 FD/bench 的健康视图

### `src/embodied_stack/body/calibration.py`
用于增强：
- doctor / suggest-env / move-joint / sync-move / semantic-smoke / arm
- 输出 artifact
- 更好的 calibration capture UX

### `src/embodied_stack/body/driver.py`
用于增强：
- live motion gate 的错误信息
- 真实 head takeover 的状态反馈
- 更好的 command outcome

### `src/embodied_stack/body/compiler.py`
用于增强：
- 真实头部的 semantic tuning
- bench-confirm 后的行为映射
- blink/listen/friendly/thinking 等动作质量

### `src/embodied_stack/desktop/app.py`
用于增强：
- console 的 serial body 状态
- runtime snapshot
- body bench panel / API

### `src/embodied_stack/desktop/cli.py`
用于增强：
- local companion / appliance 下 serial body 的控制与状态呈现
- serial doctor / bench shortcuts（如合适）

### `src/embodied_stack/config.py`
用于增强（如有必要）：
- serial arm / doctor / bench artifact path 等配置

---

## 2. 可能新增模块

### `src/embodied_stack/body/serial/doctor.py`
若不想把所有逻辑塞进 calibration CLI，可以单独拆出去。

### `src/embodied_stack/body/serial/runbook.py`
若希望把 diagnosis / suggestions 抽成可重用函数。

### `docs/serial_head_mac_runbook.md`
建议新增。

### `scripts/`
可新增：
- `serial_doctor.sh`
- `serial_bench.sh`

---

## 3. 建议新增测试

### `tests/body/test_serial_health_live_mapping.py`
- richer health decode
- status bits mapping
- voltage/temp/current decode

### `tests/body/test_calibration_cli_live_smoke.py`
- arm gate
- saved calibration requirement
- semantic smoke request validation

### `tests/desktop/test_serial_console_state.py`
- console 是否正确显示 serial health / live motion enabled / calibration status

### `tests/desktop/test_runtime_serial_takeover.py`
- runtime 对 serial failure 的 honest degradation
- snapshot / artifact

### `tests/body/test_semantic_head_live_compile.py`
- 用真实 profile 验证 look / blink / listen / brow 等编译结果

---

## 4. 建议新增文档与工件目录

### 文档
- `docs/serial_head_mac_runbook.md`
- `docs/serial_head_safety_checklist.md`

### runtime artifact
- `runtime/serial/bringup_report.json`
- `runtime/serial/health_snapshot.json`
- `runtime/serial/motion_reports/`
- `runtime/calibrations/robot_head_live_v1.json`

---

## 5. 不应该碰的边界

这轮不要让以下模块直接碰 raw serial packet：

- `brain/`
- `brain/tools.py` 里的高层 reasoning 逻辑
- planner / skill / memory 层
- high-level dialogue routing

raw packet 只应停留在：

- `body/serial/protocol.py`
- `body/serial/transport.py`
- `body/serial/driver.py`

---

## 6. 代码风格要求

- 优先“无聊但稳定”的代码
- 所有 live serial 改动都要能在 dry_run/fixture_replay 下测试
- 错误分类要稳定、机器可读
- artifact 要可读、可 diff、可归档
