# 验收门槛与发布清单

## Gate 1：Mac 串口链路打通

必须满足：

- 能列出可用 port
- 能扫描 IDs 1-11
- 能自动或手动确定正确 baud
- 能读出当前 position
- 生成 bring-up artifact

未通过则禁止进入 motion 阶段。

---

## Gate 2：真实 calibration 可保存

必须满足：

- 保存非 template calibration
- calibration 文件中 joint_records 完整
- profile 与 calibration 不冲突
- live motion enabled 条件可达成

未通过则禁止 runtime live takeover。

---

## Gate 3：单机与小组动作 smoke

必须满足：

- 单机关节小动作成功
- 回中位成功
- 至少一组多机 sync move 成功
- health poll 在动作前后可读
- 失败时有明确分类

未通过则禁止 semantic animation。

---

## Gate 4：runtime 接管成功

必须满足：

- `desktop_serial_body` 可启动
- `/console` 可见真实 serial state
- runtime body command 能落到真实头部
- failure 时 fallback honest

未通过则禁止默认在本地 companion 中启用 live body。

---

## Gate 5：semantic head action 可用

必须满足：

- `look_left/right/up/down`
- `blink_soft`
- `listen_attentively`
- `friendly`
- `thinking`
- `safe_idle`

在真实头部上表现可信，并有 artifact 支撑。

---

## Gate 6：runbook 与开发流程完善

必须满足：

- 新开发者可按文档跑通
- 有明确排错顺序
- bench artifact 自动保存
- Make/CLI/workflow 清晰

---

## Release Checklist

- [ ] `uv run pytest` 通过
- [ ] dry_run / fixture_replay serial tests 通过
- [ ] live serial doctor 在 Mac 上通过
- [ ] calibration 文件已保存并版本正确
- [ ] single-joint smoke 通过
- [ ] grouped sync smoke 通过
- [ ] console serial panel 正常
- [ ] runtime snapshot 含 body live state
- [ ] body failure honest degradation 验证通过
- [ ] semantic smoke 至少 5 个动作成功
- [ ] runbook 已写完
- [ ] artifact 目录结构稳定
