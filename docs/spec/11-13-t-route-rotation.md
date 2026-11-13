# 规范：T 方多路线 replay 与失败权重轮换

Status: **已实现（2026-11-13）；本地 123/123 unittest 通过，待提交 / 新对局验证**
Date: 2026-11-13
Related specs: [11-12-pathing-routes.md](./11-12-pathing-routes.md)（录制轨迹跟随 / A* 回退）· [11-13-pro-demo-routes.md](./11-13-pro-demo-routes.md)（多条回防路线的编译方式）· [11-12-match-observability.md](./11-12-match-observability.md)（到点 / 下包指标）· [agent-interface.md](./agent-interface.md)（`me.alive` / `round_index` / `round_wins` / `bomb` / `teammates`）· [agx-match-query skill](../../.claude/skills/agx-match-query/SKILL.md)（回放取证）

## 1. 需求

badcase：T 方每回合都走同一条录制进攻路线。如果这条路线被对手架死，agent 每次都在同一位置被打死，下一回合仍然走同一条路线。

用户要求：

1. 同一张地图的 replay 可以包含**多条有名字的路线**；
2. T 方每回合下包前按“权重最高优先”选路；
3. 在本回合实际跟随的路线上**死亡，并且本队输掉该回合** → 该路线权重下降（×0.5，下限 0.1）；
4. 下一回合优先选择权重最高的其他路线；
5. 某条路线成功（到达包点 / 完成下包）→ 权重恢复，并保持这条路线，直到它再次失败；
6. 死亡但队友赢下该回合**不降权**；CT 回合、下包后死亡不参与轮换。

当前只有 Dust2 配置了两条候选路线（`legacy` + `B_site_20261113`）；其他地图仍是单路线，机制对它们行为不变。以后编译进更多录制即可自动生效。

## 2. 现状

| 现状 | 位置 |
| --- | --- |
| 每个 replay 模块导出单条 `ROUTE` / `SITE` / `CARRIER_CUTOFF` | `borgo_replay.py`、`molo_replay.py`、`nevaio_replay.py`、`dust2_replay.py`、`mirage_replay.py`、`dust2_b_replay.py` |
| `recorded_route_options()` 组装候选列表；目前只有 Dust2 追加第二条 | `agent.py` |
| `selected_replay` 每回合选一次，回合内不换路 | `agent.py` `act()` |
| 跨回合路线权重、死亡/成功记录 | 本次新增 |

`recorded_route_info()` / `recorded_route()` / `recorded_site()` 保留为单路线兼容别名；轨迹跟随、卡点恢复、带包截止帧、战斗暂停等现有行为不变。

## 3. 路线数据模型

`recorded_route_options(map_id, geometry_hash)` 返回按**战术优先顺序**排列的元组，每项：

| 字段 | 含义 |
| --- | --- |
| `name` | 路线唯一名，模块内稳定（如 `legacy`、`B_site_20261113`） |
| `site` | 路线目标包点，必须是 `map.sites` 的 id；`None` 表示不限制包点 |
| `frames` | `(x, y, z, yaw, pitch, input_mask)` 帧元组 |
| `carrier_cutoff` | 带包者距目标包点 ≤12 m 时退出轨迹、改走 A* 下包的帧下标 |

声明顺序决定失败后的轮转顺序。单路线地图返回一元组，行为与之前完全一致。

新增路线目前通过在 `recorded_route_options()` 中加入模块选项完成；多录制编译为 `ROUTES` 的通用格式留作后续扩展（见 §12）。

## 4. 运行时状态

每个席位是独立进程，路线记忆是**每席位私有**的。`Player` 新增以下字段：

| 状态 | 含义 |
| --- | --- |
| `route_memory_key` | `(map_id, static_schema_hash)`；变化时清空权重 |
| `route_scores` | 路线名 → 权重，未记录时默认 1.0 |
| `route_success` | 最近一次成功的路线名（粘滞） |
| `route_last` | 最近一次实际开始跟随的路线名 |
| `route_last_failed` | 该路线是否刚失败（选路时跳过粘滞） |
| `route_attempt` | 本回合实际执行的路线名 |
| `route_started` | 本回合是否已真正开始跟随录制路线 |
| `route_reached` | 本回合是否已到点 / 下包 / 完成带包交接 |
| `route_death_pending` | 本回合是否已在路线上死亡（等待回合结算） |
| `route_start_wins` / `route_start_team` | 回合开始时的 `round_wins` 快照与队伍下标 |

重置规则：

- 新比赛：`init()` 重建 `Player`，全部清空；
- 地图 / `static_schema_hash` 变化：清空权重与成功状态；
- 回合切换：只清 `route_attempt` / `route_started` / `route_reached` / `route_death_pending` 与回合快照，保留权重、`route_success`、`route_last`；
- 攻防互换（半场）：保留状态；只有 T 方回合参与选路。

## 5. 每回合选路

选路时机：`round_index` 变化后的第一个 attack / 未下包 tick，且 `selected_replay is None`。选定后缓存整回合，**禁止回合内换路**。

候选筛选（v1）：`option["site"] in (None, site_id)`，其中 `site_id` 来自现有 `choose_site()`。路线站点暂不反向驱动包点选择。

优先级：

1. `route_success` 在候选中 → 直接选它（成功后保持）；
2. 否则取权重最高的候选集合（容差 `ROUTE_WEIGHT_EPS`）；
3. `route_last` 在最高集合且 `route_last_failed` 为假 → 保持它；
4. 否则沿声明顺序从 `route_last` 之后环形找第一条最高权重路线（刚失败的路线自然被跳过；全部失败后继续轮转）；
5. 首次选路（无 `route_last`）：按出生点到首帧距离排序，取 `closest + 0.5 m` 内的并列项，用 `(round_index + 1) % len(tied)` 选择，保持原有首回合行为；
6. 没有候选 → 不启用录制轨迹，按现有 A* / attackRoutes 逻辑。

各席位进程独立记忆，不要求全队同步；Dust2 两条路线都以 B 为目标或与包点兼容，当前不会因分路阻塞下包。

## 6. 成功 / 失败判定

判定只使用合法观察字段：`me.alive`、`round_index`、`round_wins`、`team`、`bomb.state`、`bomb.site`、`map.sites`。

| 结果 | 触发条件 | 状态变化 |
| --- | --- | --- |
| **成功** | `route_started` 且存活，且（`replay_done` 且未 `replay_abandoned`，或 `bomb.state == "planted"` 且下包点与路线 `site` 一致；路线 `site` 为 `None` 时不限） | 立即：权重 `min(1.0, w + 0.5)`；`route_success = route_attempt`；清失败标记 |
| **死亡失败** | `route_started` 且未成功，首次看到 `me.alive == False`，未下包，T 方 | 只置 `route_death_pending`，不立即改权重 |
| **回合结算** | 下一回合切换时比较 `round_wins[team]` 快照与当前值 | `after == before` → 权重 ×0.5（下限 0.1），清同路线 `route_success`，标记 `route_last_failed`；`after > before` → 本队赢，不降权；字段缺失 / `after < before` → 中立 |
| **中立** | 存活但未到点 / 未下包；或死亡时路线未开始 | 不换路、不改权重 |

补充规则：

- **成功先于死亡**：先到点/下包后被打死仍算成功，不换路；先死亡后队友下包不能追认成功。
- **死亡去重**：同一回合 `me.alive` 可能持续为 `False`，只记一次。
- **死亡钩子位置**：必须在 `act()` 的 `me.alive` 提前返回之前执行。
- **下包后不算路线阶段**：`bomb.state == "planted"` 之后的死亡不触发换路。
- **卡点放弃**：`replay_abandoned` 但存活算中立；之后仍可能死亡，按死亡规则处理。
- **回合结果来源**：`round_wins` 是按队伍固定索引的公开比分；`team` 缺失或格式异常时不惩罚。

## 7. 权重更新

| 常量 | 值 | 含义 |
| --- | --- | --- |
| `ROUTE_WEIGHT_INITIAL` | 1.0 | 初始权重 / 成功上限 |
| `ROUTE_WEIGHT_FAILURE` | 0.5 | 失败乘数 |
| `ROUTE_WEIGHT_SUCCESS_GAIN` | 0.5 | 成功恢复量 |
| `ROUTE_WEIGHT_MIN` | 0.1 | 权重下限 |

示例（同一席位，两条路线 B / legacy）：

| 回合 | 执行 | 结果 | B 权重 | legacy 权重 | 下一回合 |
| --- | --- | --- | ---: | ---: | --- |
| R1 | B | 路线上死亡 + 本队输 | 0.50 | 1.00 | legacy |
| R2 | legacy | 路线上死亡 + 队友赢下 | 0.50 | 1.00 | legacy |
| R3 | legacy | 到点 / 下包 | 0.50 | 1.00 | legacy（粘滞） |
| R4 | legacy | 路线上死亡 + 本队输 | 0.50 | 0.50 | B（环转） |

## 8. 边界情况

- 单路线地图：唯一候选永远被选中，权重变化不改变行为。
- 无匹配地图 / hash：候选为空，保持 A* / attackRoutes 回退。
- CT 回合、下包后死亡、路线尚未开始：不改权重、不换路。
- 成功路线本回合不在候选中（包点不同）：本轮忽略，`route_success` 保留到后续回合。
- 全部路线都失败：权重仍按最高优先，`route_last_failed` 使环转继续，不会锁死在一条路线。
- 权重记忆只在单场比赛进程内有效；新比赛由 `init()` 重置（跨比赛持久化见 §12）。

## 9. 观测与日志

`stdout` 保留给协议，轮换日志写 `stderr`，每条路线成功/结算时一行：

```text
route map=dust2-cs2-v54 seat=0 round=0 exec=B_site_20261113 result=death weight=0.50
route map=dust2-cs2-v54 seat=0 round=1 exec=legacy result=success weight=1.00
route map=dust2-cs2-v54 seat=0 round=2 exec=legacy result=neutral weight=1.00
```

回填时聚合：

- 每条路线的 attempts / deaths / arrivals / plants；
- 死亡 + 回合输后下一回合是否确实换路；
- 成功后是否保持同一路线；
- 换路前后 T 方到点率、下包率、存活到包点的比例；
- 路线死亡发生的 `round_tick` 分布。

## 10. 实现落点

| 改动 | 位置 |
| --- | --- |
| 权重常量与 `Player` 路线状态 | `agent.py` |
| `_sync_route_memory` / `_reset_route_memory` / `_reset_route_round` | `agent.py` |
| `_select_recorded_route()` 确定性选路 | `agent.py` |
| `_note_route_start()` / `_note_route_success()` / `_note_route_death()` / `_finalize_route_round()` | `agent.py` |
| 回合切换 + 死亡钩子（位于 `alive` 提前返回之前） | `agent.py` `act()` |
| 单元测试 | `tests/test_route_rotation.py` |

`recorded_route_options()` 与各 replay 模块保持现状；本次不改帧数据、不改包点选择、不改轨迹跟随。

## 11. 验收

### 11.1 单元测试（`tests/test_route_rotation.py`，全部通过）

- 初始选路保持原回合奇偶行为；
- 路线上死亡 + 本队输 → 权重 0.5，下一回合换到另一条路线；
- 路线上死亡 + 本队赢 → 权重不变、下回合保持原路线；
- 成功 → 权重恢复、`route_success` 粘滞；
- 下包时仍存活 → 成功且不因随后死亡降权；
- 两条路线都失败 → 继续环转；
- 权重下限 0.1、`round_wins` 缺失时中立；
- CT 回合 / 死亡不影响路线状态；
- 单路线地图行为不变；
- 地图 / hash 变化重置权重；
- 日志只写 stderr。

验证命令：`python -m unittest discover -s tests`（当前 123/123 通过）。

### 11.2 对局回填（提交后）

- 公开回放确认死亡 + 回合输后下一回合确实换路；
- 每条路线的尝试、死亡、到点、下包统计；
- 同一路段重复死亡次数下降；
- T 方到点率 / 下包率相对单路线版本的变化；
- 不能仅凭单元测试或准入成功声称效果已改善。

## 12. 后续可选扩展（不在本次范围）

- **更多实际路线**：Borgo `A_long` / `A_short` / `B_tunnel` 等需要先录制并编译为多路线模块，再接入 `recorded_route_options()`；当前只有 Dust2 有两条。
- **路线站点驱动包点**：带包者按当前路线 `site` 选择包点，非带包者向 `bomb.site` / 队友 zone 对齐；当前 v1 仍由 `choose_site()` 先决定包点再筛路线。
- **跨比赛持久化**：通过 `init(context)` 的 `weights_dir` 保存 / 读取路线权重，实现跨场学习；当前每场从 1.0 开始。
- **存活未到点也计失败**：超时、卡点未到点是否算路线失败，需要单独阈值。
- **队内路线通信**：通过 `signal` / `message` 广播当前路线或包点，减少各席位独立轮换造成的分路。
- **CT 回防路线轮换**：与本规范的 T 方进攻轮换分开设计。
