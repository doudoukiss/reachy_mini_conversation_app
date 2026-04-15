# Codex Prompt 04 — 构建真实头部语义动作库与行为 smoke

先阅读：

- `AGENTS.md`
- `PLAN.md`
- `src/embodied_stack/body/semantics.py`
- `src/embodied_stack/body/library.py`
- `src/embodied_stack/body/animations.py`
- `src/embodied_stack/body/compiler.py`
- `src/embodied_stack/body/profiles/robot_head_v1.json`
- `src/embodied_stack/shared/contracts/body.py`
- 相关 tests

然后围绕真实 11 轴头部，构建一套 **可 bench、可回归、可扩展** 的语义动作库。

## 背景

当前仓库已经有 semantic body surface：
- gaze
- expression
- gesture
- animation

现在要把它从 virtual-first 提升为 **real-head-ready**。

## 你要构建的内容

1. 以真实头部规则为中心，校正 compiler / tuning：
   - head_yaw
   - head_pitch_pair_a / b
   - eyelid mirrored direction
   - eye pitch/yaw
   - brow mirrored direction

2. 让以下动作在真实头部路径上变成 first-class:
   - `look_forward`
   - `look_left`
   - `look_right`
   - `look_up`
   - `look_down_briefly`
   - `blink_soft`
   - `wink_left`
   - `wink_right`
   - `listen_attentively`
   - `friendly`
   - `thinking`
   - `concerned`
   - `safe_idle`
   - `recover_neutral`

3. 新增 bench-only semantic smoke 工具：
   - CLI 或 console 均可
   - 至少支持对单个 semantic action 做 live bench 测试
   - 记录 compiled joints、clamp、targets、outcome

4. 引入轻量 tuning 层：
   - eye-to-lid coupling coefficient
   - brow symmetry correction
   - neck pitch/roll weighting
   - action intensity scaling

5. 增加 tests：
   - compiler 输出符合真实 profile
   - mirrored joints 行为正确
   - semantic smoke request validation 正确
   - dry_run / fixture_replay 下可回归

6. 更新文档：
   - 说明哪些动作已 bench-ready
   - 哪些动作还只是 virtual quality
   - 不要夸大真实头部能力

## 约束

- planner / AI 不得直接碰 servo ID 和 raw register
- 不要把 tuning 写死在 brain 层
- 不要为了做出炫酷动作而破坏可维护性
- 优先让基础 gaze / eyelid / brow 表现正确、可预测

## Definition of Done

- 真实头部至少有一套基础 gaze + blink + listen + brow + neutral 动作库
- compiler 输出可解释
- semantic smoke 有 artifact
- tests 足够覆盖基础语义动作

## Validation

至少运行：

```bash
uv run pytest
```

并给出 3–5 个推荐的 live bench semantic smoke 命令示例。

## 最终回复格式

请返回：
1. 改了哪些文件
2. 新增或修正了哪些 semantic actions
3. tuning 层放在哪
4. semantic smoke 怎么跑
5. 哪些动作还需要真人 bench 微调
