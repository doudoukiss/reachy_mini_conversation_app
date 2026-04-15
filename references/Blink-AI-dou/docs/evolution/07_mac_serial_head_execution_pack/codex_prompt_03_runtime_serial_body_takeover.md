# Codex Prompt 03 — 让 desktop runtime / console 真正接管 live serial 头部

先阅读：

- `AGENTS.md`
- `PLAN.md`
- `README.md`
- `docs/embodiment_runtime.md`
- `docs/development_guide.md`
- `src/embodied_stack/desktop/`
- `src/embodied_stack/body/driver.py`
- `src/embodied_stack/body/serial/driver.py`
- `src/embodied_stack/shared/contracts/body.py`
- `src/embodied_stack/config.py`

然后实现 **desktop_serial_body 的真正可用化**。

## 背景

当前仓库已经支持：
- desktop_bodyless
- desktop_virtual_body
- desktop_serial_body

但 serial body 仍然更像 landing zone，而不是 developer daily-use path。
现在需要把它升级成：
- console 可见
- runtime 可用
- failure honest
- artifact 完整

## 你要构建的内容

1. 把 live serial 状态变成 runtime first-class state：
   - port
   - baud
   - transport_mode
   - transport_healthy
   - confirmed_live
   - calibration_status
   - live_motion_enabled
   - arm state
   - last body command outcome

2. console 中新增 body / serial 面板：
   - scan / ping / read-health
   - write-neutral
   - safe-idle
   - arm/disarm live motion
   - semantic smoke trigger
   - per-joint target / feedback / servo health

3. runtime snapshot / episode export 中加入 live serial 状态：
   - port
   - body mode
   - calibration file
   - motion enabled state
   - last body outcome
   - degraded reason

4. honest degradation：
   - 串口断开后，AI 对话继续可用
   - body action 被拒绝时，console 和 runtime 都明确显示
   - 不得假装动作成功

5. `desktop_serial_body` 启动文档与默认流程：
   - 给出推荐 env
   - 给出最小启动命令
   - 给出从 doctor 到 runtime takeover 的流程

6. 为 serial body 增加 focused tests：
   - runtime state exposure
   - console payload
   - artifact completeness
   - degraded behavior

## 约束

- 不要让 serial failure 影响整个 local companion 主循环
- 不要破坏 bodyless / virtual body
- 不要在 runtime 中偷偷绕过 motion gate
- 仍然保持 semantic body commands 在上层，raw serial 在下层

## Definition of Done

- `desktop_serial_body` 模式可清楚呈现 live serial 状态
- console 能看到 body live status 与 body health
- runtime 能接管真实头部
- failure honest and recoverable
- session artifact 可用于后续 debug

## Validation

至少运行：

```bash
uv run pytest
uv run blink-appliance --no-open-console
```

如增加新的 console endpoint，也请给出 curl/浏览器验证方式。

## 最终回复格式

请返回：
1. 改了哪些文件
2. console 新增了哪些状态和操作
3. runtime snapshot 新增了哪些字段
4. 串口断开时系统会怎么表现
5. 还有哪些地方建议下一轮继续增强
