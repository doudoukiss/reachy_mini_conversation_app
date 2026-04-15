# Stage D：语义头部动作库（让程序接管表达，而不是接管寄存器）

## 本阶段目标

让 Blink-AI 对真实头部的控制，从“能发 joint target”升级成“能发有意义的社交表达”。

也就是说：

- AI / planner / skill 不再关心 ID1、ID8、0x2A
- 它只发：
  - `look_at_user`
  - `look_left`
  - `look_right`
  - `look_up`
  - `look_down_briefly`
  - `blink_soft`
  - `wink_left`
  - `wink_right`
  - `listen_attentively`
  - `thinking`
  - `friendly`
  - `concerned`
  - `safe_idle`

而 body compiler 负责把这些编译成：
- joint-space pose
- compiled frame / timeline
- sync write payload
- safe readback

---

## 为什么这一步是 world-class 必需

world-class embodied system 的标志之一，就是：

> 高层 reasoning 与底层 actuator 控制严格分层。

如果未来你要：

- 换一版头部
- 调整限位
- 换 RS485
- 接 Jetson
- 甚至用 learned policy

都不应该让上层 AI 改 prompt 或改 servo address。

---

## 本阶段要交付什么

### 1. 以真实 11 轴规则校正语义库
基于你的硬件规则，bench-confirm 并固化：

- `head_yaw`
- `head_pitch_pair_a/b`
- mirrored eyelids
- eye pitch / yaw
- mirrored brows

### 2. 新增/完善 semantic actions
建议优先确保以下动作在真实头部上可用：

#### gaze
- `look_forward`
- `look_at_user`
- `look_left`
- `look_right`
- `look_up`
- `look_down_briefly`

#### expressions
- `neutral`
- `friendly`
- `thinking`
- `concerned`
- `confused`
- `listen_attentively`
- `safe_idle`

#### gestures
- `nod_small`
- `tilt_curious`
- `wink_left`
- `wink_right`

#### animations
- `recover_neutral`
- `micro_blink_loop`
- `scan_softly`
- `speak_listen_transition`

### 3. 新增 bench-only semantic smoke
在 live serial bench 模式下，允许：

- `semantic-smoke --action look_left`
- `semantic-smoke --action blink_soft`
- `semantic-smoke --action listen_attentively`

### 4. teacher bench mode
增加一个 lightweight teacher mode：

- 人工触发动作
- 记录效果好不好
- 必要时微调 intensity / lid coupling / brow coupling
- 把结果写入 calibration notes 或 action tuning artifact

---

## 建议实现细节

### A. 先保证“基础表情”正确，不追求花哨
优先追求：
- 方向正确
- 对称正确
- 眼皮配合正确
- 机械不撞
- readback 正常

### B. 为真实头部添加 tuning layer
不要直接改 semantic meaning。
建议在 body compiler 之上加一层 tuning：

- expression intensity multiplier
- eye-to-lid coupling coefficient
- brow asymmetry correction
- neck pitch/roll weighting

### C. 建立真实硬件回归用例
每个语义动作都应至少有：

- dry_run test
- fixture_replay test
- optional live hardware smoke

### D. 让动作可解释
每次 semantic 动作都能看到：

- semantic action name
- compiled joints
- clamped joints
- final raw targets
- post-readback summary

---

## 本阶段成功标准

### 成功 1：语义动作真实可见
至少：
- 左右看
- 上下看
- 眨眼
- attentive listen
- friendly / thinking / safe idle

在真实头部上表现可信。

### 成功 2：planner 仍然不接触 raw servo
高层模块仍然只用 semantic API。

### 成功 3：动作失败可解释
例如：
- eyelid mirrored direction wrong
- brow asymmetry
- target clamped
- live readback drift too large

### 成功 4：teacher mode 可留下调优数据
后续你可以基于真实 head 行为继续优化。

---

## 本阶段 Codex 重点

- 先把“社交头部”做对
- 不要过早追求复杂动画
- 保持 semantic / compiler / serial 三层边界清晰
