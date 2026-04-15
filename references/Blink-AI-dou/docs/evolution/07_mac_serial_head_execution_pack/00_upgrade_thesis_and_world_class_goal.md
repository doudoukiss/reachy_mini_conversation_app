# 升级总纲：Mac Live Serial Head Bring-up / Embodied Takeover

## 1. 核心问题

现在硬件已经在 Windows 的 `fd.exe` 下完成了通电与动作测试，说明：

- 电源整体可用
- 总线整体可用
- 舵机 ID / 波特率 / 基础通信大体可用
- 这套 11 个 STS3032 的头部并不是“只存在于纸面上”

所以接下来最重要的问题，不再是“舵机能不能动”，而是：

> Blink-AI 现有软件栈如何稳定、可调试、可持续地接管这台真实头部，并且把 Mac 变成主开发环境。

---

## 2. World-class 标准下，这一轮应该追求什么

不是单纯追求“在 Mac 上也能发一帧串口包”。

而是要建立一条 world-class 的 **embodiment development spine**：

1. **硬件发现明确**
   - 哪个 port 是机器人
   - 当前 baud 是否正确
   - 哪些 ID 在线
   - 每个 ID 的反馈如何

2. **运动门控安全**
   - live serial motion 只有在 transport confirmed + saved calibration + explicit arm 后才允许
   - 所有 motion 都有 clamp、范围检查、出错中止

3. **调试路径分层**
   - dry_run
   - fixture_replay
   - live_serial
   - virtual_body
   - bodyless

4. **语义高于协议**
   - 程序写 `look_at_user` / `blink_soft` / `listen_attentively`
   - body 层再编译到 joint target
   - serial 层最后才变成 Feetech bytes

5. **bench 可追溯**
   - 每一次 bring-up、scan、read、neutral write、motion smoke 都留下 artifact
   - 失败可追查 request/response hex、port、baud、calibration、joint target、last outcome

6. **Mac 是主开发环境**
   - Windows FD 仅用于对照和救援
   - 主要 CLI / console / validation / runtime 都在 Mac 工作

---

## 3. 当前仓库已经具备哪些基础

当前仓库已经有：

- `src/embodied_stack/body/serial/protocol.py`
  - Feetech 协议打包、校验、读写、sync read/write
- `src/embodied_stack/body/serial/transport.py`
  - dry_run / fixture_replay / live_serial transport
- `src/embodied_stack/body/serial/driver.py`
  - `FeetechBodyBridge`
- `src/embodied_stack/body/calibration.py`
  - scan / ping / read_position / dump / capture_neutral / write_neutral
- `src/embodied_stack/body/profiles/robot_head_v1.json`
  - 已经存在 11 轴配置
- `src/embodied_stack/desktop/`
  - 已有 desktop runtime / console / appliance / local companion

也就是说，这次不是从 0 开始，而是：

> 把已有的 serial landing zone 升级为真正的 live hardware development path。

---

## 4. 当前真正缺的是什么

当前缺的是“开发脊柱”而不是“协议实现”：

- Mac 端串口发现与 doctor 体验不够好
- console 对 live serial health 的表达还不够强
- 缺少 bench-friendly 的单机 / 多机 smoke 路径
- calibration 需要更明确地区分 template 与 live-captured
- 需要把你给出的 11 轴物理规则正式固化成可验证的 semantic 行为库
- 缺少硬件故障的 runbook、artifact、优先级清晰的排错顺序

---

## 5. 这一轮完成后的产品状态

完成后应该达到：

### 对开发者
- Mac 插上 URT-1 / 串口板后，能一条命令识别 port、扫描在线 ID、读位置、出报告
- 能一条命令写回 neutral
- 能一条命令做 safe blink / look left / look right / nod / brow raise 等 bench 动作
- 能在 console 里看到 live serial 状态

### 对 Blink-AI runtime
- `desktop_serial_body` 成为可靠模式
- local companion / console / body layer 能直接驱动真实头部
- 失败时保留 virtual/bodyless fallback，不影响本地 AI 系统继续工作

### 对未来 embodied robot
- 语义动作层已经具备
- live serial head 已接通
- 后续只需在安全前提下继续扩展表达、teacher mode、数据飞轮、策略学习桥接

---

## 6. 这轮不该做什么

这轮不要做：

- 不受控地直接让 LLM 生成 raw servo packet
- 把 Windows FD 当成正式开发工具链
- 一上来就做复杂表情动画而跳过 calibration 和 health
- 没有 explicit arm 就开放 live motion
- 没有 artifact 就做硬件调试
- 把 Mac runtime 和真实头部耦合到无法 bodyless/virtual fallback

---

## 7. 升级命名建议

建议把这轮对外与对内都统一命名为：

## Stage 7 — Mac Live Serial Body Bring-up and Real Head Takeover
