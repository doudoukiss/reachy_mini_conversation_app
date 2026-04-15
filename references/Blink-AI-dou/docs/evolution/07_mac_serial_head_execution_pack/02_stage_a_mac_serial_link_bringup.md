# Stage A：Mac 串口链路打通（先打通，再谈动作）

## 本阶段目标

在 **不让 AI 直接驱动真实动作** 的前提下，先把 Mac 作为主开发环境的链路完全打通。

你要得到的是：

- Mac 能识别串口设备
- Blink-AI 能确认哪个 port 是机器人
- 能自动探测 baud
- 能 ping ID 1–11
- 能 read current position
- 能输出一份可留档的 bring-up 报告

---

## 为什么要先做这一阶段

因为你现在的开发风险已经从“协议不会写”变成了：

- port 搞错
- baud 搞错
- 某个舵机掉线
- Mac 连接不稳定
- 串口被别的程序占用
- 实际 live serial 不健康但 runtime 没说清楚

这些都必须在 motion 之前排干净。

---

## Stage A 的功能范围

### 1. 新增 Mac serial doctor CLI
建议命名：

- `blink-serial-doctor`
- 或复用 / 扩展 `body-calibration doctor`

它至少要支持：

- 列出当前可用串口
- 标注推荐使用的 `/dev/cu.*`
- 指定 port/baud 扫描
- `--auto-scan-baud`
- 指定 ID 范围，例如 `--ids 1-11`
- 输出 JSON 报告到 `runtime/serial/bringup_report.json`

### 2. 扩展 live scan / ping / read-position
现有 calibration CLI 已有基础逻辑，但需要更方便的开发者 UX：

- `scan`
- `ping`
- `read-position`
- `read-health`
- `suggest-env`

### 3. 记录 request/response artifact
每次 bring-up 都应该保存：

- port
- baud
- timeout
- ids tested
- ids replied
- per-id ping result
- per-id current position
- raw serial request/response hex history
- failure reason
- timestamp

### 4. `desktop_serial_body` 只允许 read-only bring-up
在这个阶段：
- 可以 live read
- 可以确认 transport
- 不要默认开放 live motion

---

## 建议实现细节

### A. 串口枚举
在 Mac 上同时列出：

- `/dev/cu.*`
- `/dev/tty.*`

并优先推荐 `/dev/cu.*` 作为主动发起通信的开发路径。

### B. baud 扫描策略
默认先试：

1. profile 指定 baud
2. `auto_scan_baud_rates`
3. 用户显式传入 baud

### C. richer health read
建议实现一个 bench-friendly 的 sync read：

- 从 `0x38` 起读多个字节
- 至少返回：
  - position
  - speed
  - load
  - voltage
  - temperature
  - status
  - moving
  - current（若可读）

### D. 输出建议 env
doctor 成功后，应输出建议：

```bash
BLINK_RUNTIME_MODE=desktop_serial_body
BLINK_BODY_DRIVER=serial
BLINK_SERIAL_TRANSPORT=live_serial
BLINK_SERIAL_PORT=/dev/cu.usbserial-XXXX
BLINK_SERVO_BAUD=115200
BLINK_HEAD_PROFILE=src/embodied_stack/body/profiles/robot_head_v1.json
BLINK_HEAD_CALIBRATION=runtime/calibrations/robot_head_live_v1.json
```

---

## 成功标准

本阶段完成后，你应该能在 Mac 上做到：

### CLI 成功
```bash
uv run blink-serial-doctor --port /dev/cu.usbserial-XXXX --ids 1-11 --auto-scan-baud
```

返回结果应明确：

- 哪个 baud 有效
- 哪些 ID 在线
- 当前位置是否可读
- transport 是否 healthy
- 是否允许进入下一阶段

### Artifact 成功
`runtime/serial/bringup_report.json` 存在，并包含完整细节。

### 无动作成功
这阶段不要求舵机运动，只要求 Mac 完整读通真实总线。

---

## 失败时排查顺序

1. port 不存在
2. port 打不开 / busy
3. ping 全失败
4. 只有部分 ID 回复
5. read-position 超时
6. 同一条总线在静态读可行，但 read-health 不稳定
7. report 不完整或无法复现

---

## 本阶段 Codex 重点

- 优先改善 CLI 与 artifact
- 不要在这里引入太多语义动作
- 不要把控制逻辑直接埋进 AI runtime
- 先把 developer bring-up experience 做到可靠
