# Codex Prompt 01 — 构建 Mac 串口 doctor 与 bring-up 工作流

先完整阅读这些文件：

- `AGENTS.md`
- `PLAN.md`
- `docs/embodiment_runtime.md`
- `docs/development_guide.md`
- `src/embodied_stack/body/profiles/robot_head_v1.json`
- `src/embodied_stack/body/serial/protocol.py`
- `src/embodied_stack/body/serial/transport.py`
- `src/embodied_stack/body/calibration.py`
- `src/embodied_stack/config.py`

然后实现一套面向 **Mac 主开发环境** 的串口 bring-up / doctor 工作流。

## 背景

当前仓库已经有：
- Feetech protocol
- dry_run / fixture_replay / live_serial transport
- calibration CLI
- desktop runtime / local companion

现在需要把这些资产升级成一条 **真实头部 bring-up 的第一阶段开发链路**。

机器人头部有 11 个 STS3032，当前硬件已在 Windows FD 下验证能上电、能动作。
软件主开发环境要迁移到 Mac。
本阶段不要求默认开放 live motion，只要求把 **链路读通并做好诊断**。

## 你要构建的内容

1. 构建一个 developer-friendly 的 Mac serial doctor 入口。
   - 可以是新 script，例如 `blink-serial-doctor`
   - 或者扩展 `body-calibration` CLI
   - 但 UX 必须清晰、可直接使用

2. 增加串口设备枚举功能：
   - 列出可用串口
   - 优先标注推荐的 `/dev/cu.*`
   - 输出 machine-readable 结果

3. 增强 bus scan：
   - 支持 `--ids 1-11`
   - 支持 `--auto-scan-baud`
   - 支持先试 profile 里的 baud，再试 auto-scan 候选
   - 结果要包含 per-baud / per-id 响应

4. 增强 read-only health bring-up：
   - 现有 `read-position` 保留
   - 新增 richer `read-health`
   - 至少要能返回：
     - position
     - speed
     - load
     - voltage
     - temperature
     - status bits
     - moving flag
     - current（如果可读）

5. 自动生成 bring-up artifact：
   - `runtime/serial/bringup_report.json`
   - 包含：
     - ports
     - chosen port
     - tested bauds
     - detected IDs
     - per-id read result
     - transport status
     - request/response hex history
     - suggestions

6. 增加 `suggest-env` 输出：
   - 根据成功结果给出推荐环境变量
   - 包括 `BLINK_RUNTIME_MODE=desktop_serial_body` 等

7. 文档化：
   - 更新 `README.md`
   - 更新 `docs/development_guide.md`
   - 新增 `docs/serial_head_mac_runbook.md` 的第一版

## 约束

- 不要让高层 brain/planner 直接接触 raw serial packet
- 不要在这一阶段默认允许 live motion
- 必须保留 dry_run / fixture_replay 测试路径
- 错误必须分类稳定、可读
- 优先 boring, maintainable code

## Definition of Done

- Mac 上可以一条命令完成 port 枚举、scan、ping、read-position/read-health
- 能输出 bring-up artifact
- 能明确告诉开发者下一步该做什么
- 所有无硬件测试仍可跑
- 文档可用

## Validation

至少运行：

```bash
uv run pytest
PYTHONPATH=src uv run python -m embodied_stack.body.calibration --transport dry_run scan --ids 1-11
```

如果你增加了新 CLI，也给出完整命令示例。

## 最终回复格式

请返回：
1. 改了哪些文件
2. 新增了哪些命令
3. `bringup_report.json` 结构是什么
4. 还没做、但建议下一步做什么
