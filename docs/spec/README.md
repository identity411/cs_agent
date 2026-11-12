# 技术规范

本目录记录实现 FPS agent 所依赖的官方技术契约。

依据：AGX「多人爆破 · AI 助手开发指南」，合同 `rsi-fps-5.5`（2026-11-12 版）。该指南声明为**闭门候选合同**：只有赛事与已接受投稿明确选择它时才适用；历史对局保留自己的合同。文档存在或本地成功都不表示赛事已开放。

## 实测状态（2026-11-12）

- 比赛 `2a97f94f-816a-52b7-b4b8-5925db160245` 在 `agx.cool` 上为 `game_id=fps`、`rules_version=rsi-fps-5.5`、状态 `open`；账号已报名，Python agent 为 `11a0f0db-afda-4a57-a2f4-36ed0462085e`。
- Python 提交路径已实测：`python-agent-v1` ZIP → admission `passed` → 版本 `1` 激活；网页参赛条目 `f81706cb-1aa5-54e6-9e4b-e1199ca25820` 显示 `version.number = 1`。详见 [`../submissions/v001-first-python-submission/README.md`](../submissions/v001-first-python-submission/README.md)。
- `/api/openapi.json` **不列出** `/api/v1/python-submissions` 路由；实测端点、预算与故障语义见 [agx-submit skill](../../.claude/skills/agx-submit/SKILL.md)。
- `GET /api/v1/games/fps` 的 `example_code` / `baselines` 是 JavaScript 参考，不代表提交语言；Python 以 `GET /api/v1/python-submissions/templates/fps` 的 `profile` / `files` 为准。

## 源码定位

| 合同 / 机制 | 源码 |
| --- | --- |
| 赛制 / CPU | `rsi/fps_v54_contract.py:7` |
| 回合转换 / 时钟 | `rsi/games/fps_v54_rounds.py:9` |
| 经济选择 / 结算 | `rsi/games/fps_v54_economy_rules.py:22` |
| 选图 / 后端 | `rsi/games/fps_v54_maps.py:38` |
| 公开地图 / 观察 | `rsi/games/fps_v54.py:730` |
| 全部动作字段 | `rsi/games/fps_v54_actions.py:9` |
| 安放 / 拆除 | `rsi/games/fps_v54_objective.py:11` |
| 十席冻结 / 故障 / 比分 | `rsi/games/fps_v4.py:1077` |
| 流 / 执行限额 | `rsi/runtime/stream_profiles.py:450` |
| Python 适配 / 合法批次 | `rsi/python_runtime/adapters/fps54.py:1` |
| Python CPU profile | `rsi/python_integration/profiles.py:25` |
| SDK 本地钩子 | `sdk/python-agent/games/fps54/hook.py:5` |
| ZIP API / 历史 | `rsi/python_submissions/api.py:1` |

## 索引

- [agent-interface.md](agent-interface.md) — 生命周期、合法观测、完整动作合同。
- [maps.md](maps.md) — 五图、选图哈希、坐标与地图描述缓存。
- [fps54-catalogue.json](fps54-catalogue.json) — 冻结武器 / 装备 / 投掷物完整数据（规范化键名）。
- [baseline-compatibility.md](baseline-compatibility.md) — 当前 `agent.py` 与官方合同的差异清单。
- [agx-submit skill](../../.claude/skills/agx-submit/SKILL.md) — 运行时预算、ZIP 限制、故障语义与实测 Python 提交流程。

## 提交版本与改动说明

每次提交的代码快照和改动说明在 [`../submissions/`](../submissions/README.md)。规范与版本的对应关系：

| 版本 | 改动说明 | 影响的规范 |
| --- | --- | --- |
| `v000-baseline` | [v000-baseline/README.md](../submissions/v000-baseline/README.md) | [baseline-compatibility.md](baseline-compatibility.md) |
| `v001-first-python-submission` | [v001-first-python-submission/README.md](../submissions/v001-first-python-submission/README.md) | [agx-submit skill](../../.claude/skills/agx-submit/SKILL.md), [baseline-compatibility.md](baseline-compatibility.md) |

## 待补 / 待核实

- [ ] `map.nav` 在全部五图 / 完整对局中的可用性（首次 admission 已通过，但没有覆盖完整地图和回合一局）
- [ ] 完整正式对局、比分与回放的验收结果（当前仅验证上传 / 准入 / 激活）

> 官方指南中的源码行号仅用于核对语义，不是运行时依赖。不要从全知录像或训练导出重建观察。
