# Stage B：真实 calibration、motion gate 与安全动作

## 本阶段目标

从“读得通”升级到“能安全地小范围动作”。

但前提是：

- live transport confirmed
- 已有真实 calibration 文件
- motion 需要显式 arm
- 所有 live target 都经过 joint clamp 和 coupling 规则

---

## 为什么这一步关键

当前仓库已经有 live motion gate，但如果没有一套真正顺手的 calibration / arm / safe smoke 流程，你最后还是会回到 Windows FD。

所以这一阶段要做的不是“让它能动”，而是：

> 让它在 Mac 上以工程化方式、可追溯地、安全地动。

---

## 本阶段要交付什么

### 1. 保存真实 calibration
把 template calibration 升级成真实 calibration：

- 存到 `runtime/calibrations/robot_head_live_v1.json`
- 记录：
  - profile
  - port
  - baud
  - current position
  - per-joint neutral
  - per-joint raw_min/raw_max
  - coupling validation
  - notes
  - recorded_at / updated_at

### 2. 新增 guided bench motion CLI
建议支持：

- `arm-live-motion`
- `disarm-live-motion`
- `move-joint`
- `sync-move`
- `write-neutral`
- `safe-idle`
- `torque on/off`
- `bench-health`

### 3. 默认只允许“小动作 smoke”
初始 smoke 只允许：

- 单关节小位移
- 回中位
- 一组 eyelid/brow/eye/head 的小幅同步写

不允许：
- 大范围 sweep
- 未经 arm 的 animation
- 未经 calibration 的 live semantic action

### 4. 关节安全边界固化
结合你提供的 11 轴说明，把现有 profile 再 bench-confirm：

- ID1 头左右
- ID2/ID3 抬头低头与左右歪头耦合
- ID4/ID5/ID6/ID7 上下眼皮镜像关系
- ID8 眼球上下
- ID9 眼球左右
- ID10/ID11 眉毛镜像关系

### 5. 生成 bench artifact
每次 safe motion smoke 都记录：

- command family
- semantic / joint target
- clamped result
- request/response hex
- before/after position
- health before/after
- success/failure
- notes

---

## 建议实现细节

### A. calibration 必须是 saved/captured，而不是 template
当前 live bridge 的逻辑已经要求 non-template calibration 才允许 live motion。
这个门要保留。

要做的是把用户体验做好：

- 当 calibration 还是 template 时，明确告诉用户下一步做什么
- 提供一条命令把 live neutral 捕获并保存为正式 calibration

### B. single joint smoke
新增：

```bash
uv run body-calibration \
  --transport live_serial \
  --port /dev/cu.usbserial-XXXX \
  --baud 115200 \
  move-joint --joint head_yaw --target 2147 --arm-live-motion
```

这一步只对单个 joint 小范围动作。

### C. sync move smoke
新增：

```bash
uv run body-calibration \
  --transport live_serial \
  --port /dev/cu.usbserial-XXXX \
  --baud 115200 \
  sync-move --group eyes_forward_listen --arm-live-motion
```

### D. safe idle / torque strategy
建议在 bench 模式下明确支持：

- `safe-idle`：回中位或按 profile torque off
- `torque-off`
- `torque-on`

### E. arm 机制
live motion 不能只靠 transport confirmed。
还要有明确的 operator / CLI arm，例如：

- `--arm-live-motion`
- runtime 内单独按钮 / API
- auto-expire arm window（例如 60 秒）

---

## 本阶段成功标准

### 成功 1：Mac 能保存正式 calibration
`runtime/calibrations/robot_head_live_v1.json` 存在，且不是 template。

### 成功 2：Mac 能安全地做单机小动作
例如 head_yaw、eye_yaw、upper_lids 等能小幅移动并回中。

### 成功 3：Mac 能做小规模同步动作
例如：
- 双眼上下
- 双眼左右
- 双眉同步
- 双眼皮同步开闭

### 成功 4：失败可解释
失败时要明确知道是：

- transport unconfirmed
- calibration template
- target out of range
- write failed
- timeout
- health degraded
- power sag suspected

---

## 失败时排查顺序

1. calibration 还是 template
2. live motion 没 arm
3. joint target 超范围被 clamp/reject
4. 单机能动，多机一动就通信不稳
5. 动作前能读，动作后 read-health 异常
6. 实际方向与 profile 相反
7. 耦合关系未 bench-confirm，导致表情不对

---

## 本阶段 Codex 重点

- 优先做 `saved calibration + arm + safe smoke`
- 把失败解释写清楚
- 保持 dry_run / fixture_replay 对应路径
- 不要在这个阶段直接上复杂 AI 自动动作
