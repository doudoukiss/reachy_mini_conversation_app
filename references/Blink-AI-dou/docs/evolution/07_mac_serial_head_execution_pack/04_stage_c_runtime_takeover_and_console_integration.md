# Stage C：让 desktop runtime / console 真正接管 live serial 头部

## 本阶段目标

把前两个阶段的 bench 能力接到 Blink-AI 的日常运行面：

- `desktop_serial_body`
- local companion
- browser console
- runtime snapshot
- honest fallback

最终效果是：

> 你不再只是跑几个 CLI 命令，而是能让整个 Blink-AI runtime 带着真实头部一起工作。

---

## 本阶段要交付什么

### 1. serial body 成为 first-class runtime mode
完善：

- `desktop_serial_body`
- `serial_body` embodiment profile
- live body health snapshot
- connect / disconnect / arm / disarm / safe idle

### 2. console 显示 live serial 关键信息
在 `/console` 中清楚展示：

- body driver mode
- serial transport mode
- port
- baud
- transport healthy
- confirmed live
- calibration status
- live motion enabled
- last command outcome
- per-joint target
- per-joint readback
- per-servo health

### 3. runtime 允许显式 body 接管
当你启动：

```bash
uv run blink-appliance
```

或

```bash
uv run local-companion
```

在指定 env 下能运行真实头部模式：

```bash
BLINK_RUNTIME_MODE=desktop_serial_body
BLINK_BODY_DRIVER=serial
BLINK_SERIAL_TRANSPORT=live_serial
BLINK_SERIAL_PORT=/dev/cu.usbserial-XXXX
BLINK_SERVO_BAUD=115200
BLINK_HEAD_PROFILE=src/embodied_stack/body/profiles/robot_head_v1.json
BLINK_HEAD_CALIBRATION=runtime/calibrations/robot_head_live_v1.json
```

### 4. body failure 不拖垮 AI runtime
如果串口掉了、舵机断开、motion gate 失效：

- AI 对话仍可继续
- console 明确提示 body degraded
- body 命令转为 honest rejection / safe idle
- 不得假装真实动作已经执行

---

## 建议实现细节

### A. runtime 中的 serial state manager
建议集中管理：

- port / baud / timeout
- confirmed_live
- calibration loaded
- arm state
- last successful poll
- degraded reason

### B. console 中新增 body bench panel
在 operator console 中增加：

- scan
- ping
- read health
- write neutral
- safe idle
- arm live motion
- disarm live motion
- run semantic smoke

### C. runtime snapshot artifact
每次 local companion / appliance session 导出时，记录：

- runtime mode
- body mode
- live serial status
- calibration file
- arm state
- motion enabled state
- last body command outcome
- body degraded reasons

### D. body command 审计
每个 semantic body command 都应留下：

- request semantic name
- compiled targets
- clamped joints
- transport result
- readback result
- whether fallback occurred

---

## 本阶段成功标准

### 成功 1：console 可见
打开 `/console`，可以清楚看到 live serial 运行状态。

### 成功 2：runtime 可接管
在 `desktop_serial_body` 下，Blink-AI 发出的 body 命令能真的让头部动作。

### 成功 3：失败 honest
拔掉串口或断电后，AI 系统继续活着，但 body 状态明确 degraded。

### 成功 4：artifact 完整
session 导出后能从 artifact 看出：
- 当时是否真在 live serial
- body 是否健康
- 发了什么动作
- 是否成功
- 是否 fallback

---

## 失败时排查顺序

1. CLI smoke 能动，但 runtime 不动
2. runtime 能动，但 console 不显示真实状态
3. console 状态对，但导出 artifact 不完整
4. 串口断开后 runtime 卡死
5. AI 误以为 body 成功执行，实际上失败

---

## 本阶段 Codex 重点

- 让 `desktop_serial_body` 真正 usable
- 优先可观测性和 honest degradation
- 不要把 body failure 扩散到整个 companion runtime
