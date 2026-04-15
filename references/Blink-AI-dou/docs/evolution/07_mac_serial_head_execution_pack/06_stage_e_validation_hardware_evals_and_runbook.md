# Stage E：验证、硬件回归、排错 runbook、产品化 Mac 工作流

## 本阶段目标

让这条 Mac → live serial → real head 的路径，不是“今天调通了”，而是：

- 下周还能复现
- 换人还能跑
- 故障能快速定位
- 结果可比较
- 后续能接入更强 AI runtime 与 embodied product path

---

## 本阶段要交付什么

### 1. hardware-aware test / smoke 分层
建议分成三类：

#### A. 普通 CI 永远跑
- dry_run
- fixture_replay
- protocol encode/decode
- compiler
- calibration schema
- console state
- runtime fallback

#### B. 本机 bench smoke 手动跑
- ping 1-11
- read-position 1-11
- write-neutral
- single-joint motion
- semantic smoke
- safe idle

#### C. live hardware 才跑的 opt-in 套件
例如：
```bash
BLINK_RUN_LIVE_SERIAL_TESTS=1 uv run pytest -m live_serial
```

### 2. artifact 标准化
bench 与 runtime 都要自动导出：

- bringup report
- calibration snapshot
- motion report
- console snapshot
- body telemetry
- request/response history
- failure summary

### 3. 明确的 Mac 开发流程
形成固定工作流：

1. 插线
2. `blink-serial-doctor`
3. `body-calibration scan`
4. `body-calibration read-position`
5. `body-calibration write-neutral`
6. `body-calibration semantic-smoke`
7. `uv run blink-appliance` 或 `uv run local-companion`
8. console 观察 / artifact 导出

### 4. 故障排查 runbook
要形成一个明确的优先级表：

#### 链路类
- 找不到 port
- 打不开 port
- baud 不对
- ping 超时

#### 运动类
- calibration template
- motion 未 arm
- torque off
- target out of range
- multi-servo power sag

#### 表现类
- mirrored eyelid / brow 方向不对
- neck pitch/roll 耦合不自然
- eye pitch 和 eyelid coupling 太夸张
- readback 偏差过大

### 5. 文档与 make/CLI 整合
增加：

- `docs/serial_head_mac_runbook.md`
- `make serial-doctor`
- `make serial-bench`
- `make serial-neutral`
- `make serial-companion`

---

## 建议实现细节

### A. live serial tests 必须 opt-in
不能让普通 CI 因为没有硬件而失败。

### B. benchmark 不只看“能动”
还要记录：
- latency
- success/failure
- readback drift
- clamp count
- degraded count

### C. 调试日志必须 machine-readable
既要 human-friendly，也要有 JSON。

### D. 把 Windows FD 的价值降级为 reference
保留一份文档说明：
- 当 Mac 路径异常时，FD 可以作为硬件 sanity check
- 但正式开发仍以 Mac CLI/runtime 为主

---

## 本阶段成功标准

### 成功 1：新开发者可复现
另一个人拿到硬件和仓库，能按 runbook 跑通。

### 成功 2：故障可定位
遇到问题时知道先查哪一层，而不是到处试。

### 成功 3：bench 有证据
每次调试都有 artifact。

### 成功 4：AI runtime 与真实头部形成稳定工作流
而不是“靠命令行偶然发一帧能动”。

---

## 本阶段 Codex 重点

- 产品化开发流程
- world-class 的可观测性、可追溯性、可回归
- 让 Mac 成为真正主开发环境
