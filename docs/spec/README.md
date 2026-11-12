# 技术规范

本目录记录实现 FPS agent 所依赖的官方技术契约。

依据：AGX「多人爆破 · AI 助手开发指南」，合同 `rsi-fps-5.5`（2026-11-12 版）。该指南声明为**闭门候选合同**：只有赛事与已接受投稿明确选择它时才适用；历史对局保留自己的合同。文档存在或本地成功都不表示赛事已开放。

## 变更记录

### 2026-11-12
- **关联规范**：[agent-interface.md](agent-interface.md)、[maps.md](maps.md)、[baseline-compatibility.md](baseline-compatibility.md)、[agx-submit skill](../../.claude/skills/agx-submit/SKILL.md)。
- **背景**：线上 FPS 比赛使用 `rsi-fps-5.5` Python runtime；需要一份精简的本地合同与提交记录，避免重复官网/平台级文档。
- **决策点**：只保留 FPS 专用规范；运行时预算与上传流程放在 skill；不落盘完整武器目录，价格与限额以官方冻结目录为准。
- **新增 badcase**：[11-12-economy-rotation-combat.md](11-12-economy-rotation-combat.md) — v0.01 对局中经济 / 转点 / 走路 / 蹲射 / 换弹 5 类非卡住问题；v0.02 未覆盖。
- **新增可观测性规范**：[11-12-match-observability.md](11-12-match-observability.md) — 定义参战 / 开火 / 命中 / 卡死 / 回防指标与变好/变坏判定；首批回填 v0.01 ×1 场 vs v0.02 ×2 场。
- **新增寻路规范**：[11-12-pathing-routes.md](11-12-pathing-routes.md) — A* + 执行反馈边代价 + dust2 attackRoutes + sprint/战斗超时/plant zone；已随 v0.03 提交/激活，待新对局验证。
- **v0.03 提交**：[`1112-v0.03`](../submissions/1112-v0.03/README.md) — 包含 A*、dust2 attackRoutes、R2 包点 patrol、sprint / 战斗超时 / plant zone；`main` version `3`、`account2` version `2` 均 admission `passed` 并激活。

## 实测状态（2026-11-12）

- 比赛 `2a97f94f-816a-52b7-b4b8-5925db160245` 在 `agx.cool` 上为 `game_id=fps`、`rules_version=rsi-fps-5.5`、状态 `open`；账号已报名，Python agent 为 `11a0f0db-afda-4a57-a2f4-36ed0462085e`。
- Python 提交路径已实测：`python-agent-v1` ZIP → admission `passed` → 版本 `1` 激活；网页参赛条目 `f81706cb-1aa5-54e6-9e4b-e1199ca25820` 显示 `version.number = 1`。详见 [`../submissions/1112-v0.01/README.md`](../submissions/1112-v0.01/README.md)。
- 2026-11-12：出生点卡住修复版已提交，admission `passed`，version `2` 激活（entry 显示 `version.number = 2`、`code_hash_short = 033716bdfb0c`）。详见 [`../submissions/1112-v0.02/README.md`](../submissions/1112-v0.02/README.md)；12:00 UTC 两场已回填，见 [11-12-match-observability.md](11-12-match-observability.md)，长期验证仍待完成。
- 2026-11-12：A* / attackRoutes / patrol / 战斗控制版已提交到 `main` 和 `account2`，admission 均 `passed`；`main` version `3`、`account2` version `2` 激活（两者 entry 均显示 `code_hash_short = 07f6516dfb12`）。详见 [`../submissions/1112-v0.03/README.md`](../submissions/1112-v0.03/README.md)；待下一场正式对局回填。
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
- [baseline-compatibility.md](baseline-compatibility.md) — 当前 `agent.py` 与官方合同的差异清单。
- [agx-submit skill](../../.claude/skills/agx-submit/SKILL.md) — 运行时预算、ZIP 限制、故障语义与实测 Python 提交流程。
- [agx-match-query skill](../../.claude/skills/agx-match-query/SKILL.md) — 只读对局 / 公开回放查询、席位统计与 badcase 取证。
- [11-12-empty-primary-switch-reload.md](11-12-empty-primary-switch-reload.md) — badcase：空弹主武器不切枪 / 不换弹的复现与验收。
- [11-12-stuck-at-spawn.md](11-12-stuck-at-spawn.md) — badcase：出生点/近点卡住导致整回合不交战。
- [11-12-site-center-hold.md](11-12-site-center-hold.md) — badcase：到达包点后停在中心不动（R2）。
- [11-12-economy-rotation-combat.md](11-12-economy-rotation-combat.md) — badcase：v0.01 对局的 5 类非卡住问题（经济 / 转点 / 走路 / 蹲射 / 换弹）。
- [11-12-match-observability.md](11-12-match-observability.md) — 规范：对局可观测性指标（参战 / 命中 / 卡死 / 回防）与版本对比判定。
- [11-12-pathing-routes.md](11-12-pathing-routes.md) — 规范：A* 寻路、dust2 进攻路线、sprint/战斗超时/plant zone。

> 完整武器 / 装备 / 投掷物数值不落盘,以官方冻结目录为准。

## Badcase 记录

badcase 采用 `MM-DD-<theme>.md` 命名；新 badcase 按日期追加，不改旧文件。每条记录最小状态、demo 复现步骤、判定标准与验收，证据由 demo / 对局回填。

| 日期 | 文件 | 状态 |
| --- | --- | --- |
| 2026-11-12 | [11-12-empty-primary-switch-reload.md](11-12-empty-primary-switch-reload.md) | 对局已观察：A/C 未出现，B 出现；待新对局验证 |
| 2026-11-12 | [11-12-stuck-at-spawn.md](11-12-stuck-at-spawn.md) | 对局已确认；v0.02 防守侧已改善，dust2 T 侧仍有卡死（见可观测性规范） |
| 2026-11-12 | [11-12-site-center-hold.md](11-12-site-center-hold.md) | R2 已复现；patrol 修复随 v0.03 提交/激活，待新对局验证 |
| 2026-11-12 | [11-12-economy-rotation-combat.md](11-12-economy-rotation-combat.md) | 对局已确认（v0.01）；v0.02 回防启动改善、到位仍 0（见可观测性规范） |

## 提交版本与改动说明

每次提交的代码快照和改动说明在 [`../submissions/`](../submissions/README.md)。规范与版本的对应关系：

| 版本 | 改动说明 | 影响的规范 |
| --- | --- | --- |
| `1112-v0.00` | [1112-v0.00/README.md](../submissions/1112-v0.00/README.md) | [baseline-compatibility.md](baseline-compatibility.md) |
| `1112-v0.01` | [1112-v0.01/README.md](../submissions/1112-v0.01/README.md) | [agx-submit skill](../../.claude/skills/agx-submit/SKILL.md), [baseline-compatibility.md](baseline-compatibility.md) |
| `1112-v0.02` | [1112-v0.02/README.md](../submissions/1112-v0.02/README.md) | [11-12-stuck-at-spawn.md](11-12-stuck-at-spawn.md), [11-12-empty-primary-switch-reload.md](11-12-empty-primary-switch-reload.md), [agx-match-query skill](../../.claude/skills/agx-match-query/SKILL.md) |
| `1112-v0.03` | [1112-v0.03/README.md](../submissions/1112-v0.03/README.md) | [11-12-pathing-routes.md](11-12-pathing-routes.md), [11-12-site-center-hold.md](11-12-site-center-hold.md), [11-12-stuck-at-spawn.md](11-12-stuck-at-spawn.md), [baseline-compatibility.md](baseline-compatibility.md) |

## 待补 / 待核实

- [ ] `map.nav` 在全部五图 / 完整对局中的可用性（首次 admission 已通过，但没有覆盖完整地图和回合一局）
- [x] 首次正式对局、比分与回放（2026-11-12 `nevaio-r3-v54`，13–11 负；公开回放已取证）
- [ ] 出生点卡住修复后的新对局验证：seat 7 不再出现“存活 + 满弹主武器 + 整回合 0 发射”
- [ ] 5 类非卡住 badcase 的修复与下一场验收（见 [11-12-economy-rotation-combat.md](11-12-economy-rotation-combat.md)）
- [x] v0.02 对局可观测性回填（2 场 / 40 回合；卡死/到点改善、交火未改善、回防启动改善但到位 0；见 [11-12-match-observability.md](11-12-match-observability.md)）
- [ ] 新增 dust2 T 侧卡死 badcase 的修复与验收（R13/R14/R15/R17/R19）
- [ ] A* + attackRoutes + sprint/战斗超时/plant zone 的新对局验证（见 [11-12-pathing-routes.md](11-12-pathing-routes.md)）
- [ ] post-v0.03 修正（T pre-plant patrol 振荡、dust2 soft hazard、本地 nav 模拟器）提交/新对局验证（见 [11-12-pathing-routes.md](11-12-pathing-routes.md)）

> 官方指南中的源码行号仅用于核对语义，不是运行时依赖。不要从全知录像或训练导出重建观察。
