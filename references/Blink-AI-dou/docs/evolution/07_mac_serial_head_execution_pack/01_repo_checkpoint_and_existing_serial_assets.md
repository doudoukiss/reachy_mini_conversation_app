# 仓库检查点：当前已经有哪些和串口头部接管直接相关的能力

## 1. 结论

当前仓库并不是“还没有真实头部支持”。

恰恰相反，仓库里已经有一套很好的 **serial landing zone**，只是还没有打磨成“可持续 bench / 可持续 live development”的状态。

---

## 2. 直接相关的已有资产

### A. 头部 profile 已经存在
`src/embodied_stack/body/profiles/robot_head_v1.json`

它已经定义了：

- servo family = `feetech_sts3032`
- baud rate = `115200`
- auto scan baud rates = `[115200, 1000000]`
- 11 个 joint
- neutral = `2047`
- raw_min / raw_max
- mirrored brow / eyelid / neck coupling notes

这和你现在提供的真实头部说明已经高度对齐。

### B. Feetech 协议层已经实现
`src/embodied_stack/body/serial/protocol.py`

已有：

- ping
- read
- write
- sync write
- sync read
- recovery
- reset
- 小端 16-bit pack/unpack
- checksum
- status decode

这意味着真正缺的不是协议，而是 **使用协议的工程化流程**。

### C. Transport 已经分层
`src/embodied_stack/body/serial/transport.py`

已有：

- `dry_run`
- `fixture_replay`
- `live_serial`

而且 live serial 已经通过 `pyserial` 打开真实串口。

### D. Body bridge 已经存在
`src/embodied_stack/body/serial/driver.py`

`FeetechBodyBridge` 已经能：

- 把 compiled animation 发送到 sync_write
- torque off safe idle
- poll health

### E. 校准 CLI 已经存在
`src/embodied_stack/body/calibration.py`

已有命令逻辑：

- `scan`
- `ping`
- `read-position`
- `write-neutral`
- `dump-profile-calibration`
- `capture-neutral`

这非常关键，因为这意味着下一步是**增强它**，而不是重写。

---

## 3. 当前的关键限制

### 限制 1：live motion gate 很严格
这是对的，但还不够好用。

当前逻辑下，live serial motion 需要：

- `transport.status.mode == live_serial`
- `transport.confirmed_live == True`
- calibration 存在
- calibration 不是 template
- calibration schema 正确

这条门控是对的，应该保留。

但开发体验上，还需要：

- 更明确地告诉用户“为什么不能动”
- 更容易把 template 升级成真实 captured calibration
- 更明显地把 live motion enabled 状态展示到 console 和 CLI

### 限制 2：health 读数还不够丰富
当前 `health.py` 主要读：

- present position
- torque switch

但根据 STS 手册，真实 bench 调试需要更丰富的数据：
- 当前位置
- 当前速度
- 当前负载
- 当前电压
- 当前温度
- 状态位
- 当前电流（如果支持）

所以需要补足 richer health polling。

### 限制 3：缺少面向 Mac 的串口 doctor 体验
当前有 calibration CLI，但缺少一个真正面向开发者的：

- 列出可用串口
- 自动扫波特率
- 报告在线 ID
- 输出建议 env
- 判断当前是否能进入 live motion

### 限制 4：没有完整“真实头部 takeover”路径
现在有 bodyless / virtual / serial landing zone，但还缺：

- 明确的 stage-by-stage 接管顺序
- 单机 → 多机 → semantic action 的可执行路径
- 对本地 companion / console 的整合和可视化

---

## 4. 当前升级的最佳策略

不是“大改架构”。

而是基于当前资产做四件事：

1. **补齐 Mac 串口 bring-up 体验**
2. **补齐 live calibration + safe motion**
3. **补齐 desktop runtime / console 对 live serial 的整合**
4. **补齐 semantic head behavior library + hardware eval**

---

## 5. 不变的架构边界

这次升级必须坚持以下边界：

- `brain/` 不碰 raw servo register
- `body/` 负责 semantic → joint target
- `body/serial/` 负责 joint target → packet / readback
- `desktop/` 负责 local runtime orchestration, console, device health, operator flow
- tests 必须继续覆盖 dry_run / fixture_replay，live hardware tests 只能是显式 opt-in

---

## 6. 这轮改动成功后，仓库应该呈现什么样子

- 任何新开发者拿到 Mac + URT-1 + 头部后，可以通过 README/runbook 在 30 分钟内跑通 ping/read/neutral
- 任何一次 bench session 都自动留下 artifact
- live serial path 可以被 console 和 CLI 透明观测
- Blink-AI 能逐步接管真实 11 轴头部，而不是永远停留在 virtual body
