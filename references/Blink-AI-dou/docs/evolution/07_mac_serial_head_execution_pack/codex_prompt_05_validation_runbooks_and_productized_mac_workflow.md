# Codex Prompt 05 — 验证体系、runbook、产品化 Mac 工作流

先阅读：

- `AGENTS.md`
- `PLAN.md`
- `README.md`
- `docs/development_guide.md`
- `docs/embodiment_runtime.md`
- `tests/`
- 本执行包中的所有 stage 文档

然后把这条 Mac → live serial → real head 的路径产品化成一套 **可复制、可回归、可维护** 的工作流。

## 背景

当前已经有：
- serial protocol / transport
- calibration CLI
- desktop runtime / console
- semantic body layer

现在要做的是让这套链路具备 world-class 的工程品质：

- 明确分层
- 明确 artifact
- 明确测试
- 明确 runbook
- 明确 failure order

## 你要构建的内容

1. 分层验证体系：
   - 普通 CI 永远跑的 dry_run / fixture tests
   - 本机 bench smoke
   - opt-in live hardware tests

2. artifact 结构标准化：
   - `runtime/serial/bringup_report.json`
   - `runtime/serial/health_snapshot.json`
   - `runtime/serial/motion_reports/`
   - `runtime/calibrations/robot_head_live_v1.json`
   - session/runtime snapshot 中的 body live data

3. runbook：
   - 新增 `docs/serial_head_mac_runbook.md`
   - 内容包括：
     - 接线与 port 识别
     - doctor
     - scan
     - read-health
     - calibration capture
     - single joint smoke
     - sync smoke
     - semantic smoke
     - runtime takeover
     - failure order

4. make / CLI workflow：
   - 例如：
     - `make serial-doctor`
     - `make serial-neutral`
     - `make serial-bench`
     - `make serial-companion`
   - 或者等价脚本 / documented commands

5. release checklist：
   - 清楚列出什么时候可以说 “Mac 已经成为主开发环境”
   - 清楚列出什么时候才可以让 AI 自动发 body actions

6. 不要删除 Windows FD 相关参考，但要明确降级为 fallback/reference path

## 约束

- 不要让 live hardware tests 污染普通 CI
- 不要引入无法在无硬件环境下运行的默认流程
- 不要用模糊语言描述验证结果
- 所有文档都要能帮助未来新开发者复现

## Definition of Done

- 有明确 runbook
- 有明确 artifact
- 有明确测试层次
- 有明确 Make/CLI 路径
- Mac 主开发流程可复现
- 真实头部集成不再依赖口口相传

## Validation

至少运行：

```bash
uv run pytest
```

并列出你新增的 developer commands。

## 最终回复格式

请返回：
1. 改了哪些文件
2. 新增了哪些 runbook / make / script
3. 测试如何分层
4. artifact 如何组织
5. 这一轮完成后，开发者如何从插线到 runtime takeover
