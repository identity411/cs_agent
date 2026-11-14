# Badcase：首拍回调加载全图导致 tick 0 fault、席位整场不动

Status: **已实现并随 `1114-v0.17` 提交：`main` v13 / `account2` v16 admission `passed` 并激活；本地 130/130 unittest 通过，正式对局待验证**
Date: 2026-11-14
Submission: [1113-v0.16](../submissions/1113-v0.16/README.md) · [1114-v0.17](../submissions/1114-v0.17/README.md)
Related specs: [maps.md](./maps.md)（首拍地图描述）· [agent-interface.md](./agent-interface.md)（`phase` / 购买 / 动作合同）· [baseline-compatibility.md](./baseline-compatibility.md)（首拍字段与导航来源）· [11-12-pathing-routes.md](./11-12-pathing-routes.md)（nav 图构建与 A*）· [11-12-stuck-at-spawn.md](./11-12-stuck-at-spawn.md)（卡住的区分）· [11-12-match-observability.md](./11-12-match-observability.md)（fault 指标）· [11-13-t-route-rotation.md](./11-13-t-route-rotation.md)（v0.16 首拍新增路线初始化）· [agx-match-query skill](../../.claude/skills/agx-match-query/SKILL.md)（公开回放取证）

## 0. 文档目的

记录 2026-11-13 16:00 UTC 对局 `20228083-ddc7-4fd1-b8d2-ee1c01398cc2` 中“两个席位整场完全没有动作”的 badcase，并给出可实施的修复方案。

本文只使用公开回放、公开事件和本地静态地图；不声称拥有平台的私有运行日志或 `fault_code`。对根因的判定分级为“直接原因已确认 / 触发原因最可能 / 平台侧仍待确认”。

## 1. 结论

1. **不是卡住，也不是路线/A* 问题**：`main` 和 `account2` 的两个席位在 **R0 tick 0** 各收到一个 `fault`，之后被平台以 neutral control 接管，整场 20 回合没有购买、没有移动、没有开火。
2. **直接原因已确认**：公开事件在 `match_tick=0`、`round_index=0` 连续记录 3 个 `fault`：seat 5、seat 7、seat 8。两个属于本仓库账户（account2 seat 5、main seat 8）；公开帧显示两人存活、`speed=0`、`activity=idle`，一直停在 T 出生点。
3. **触发原因最可能**：v0.16 在本仓库 `act()` 的**首个回调**里同时做了三件重工作：
   - `load_map()` 构建 Mirage nav 图（2544 节点 / 6381 边）；
   - 新增的 `_sync_route_memory()` 第一次调用会 `import mirage_replay`（1410 帧轨迹）并初始化路线权重；
   - 然后才进入 buy 分支返回购买动作。

   官方 Python 模板明确提示：首拍 observation 很大，**地图图构建必须延后到后续 callback**，让 JSON 解码和图构建使用不同预算。首拍同时完成这些工作，容易触发首拍 callback 超时/异常，从而在 tick 0 被 fault。
4. **平台侧仍待确认**：公开 `fault` 事件没有 `fault_code` 或原因字段，无法区分 timeout、exception、illegal output 或 worker exit。本文不把“首拍超时”写成已证实结论，只列为最强假设。
5. **修复方向（已实现）**：首拍只保存地图和廉价元数据，nav 图在后续 buy 回调中**分块构建**；路线权重同步推迟到图 ready 之后；`init()` 按官方模板 `gc.disable()`。已随 `1114-v0.17` 提交并激活。

## 2. 对局与证据

### 2.1 对局身份

| 项目 | 值 |
| --- | --- |
| match / job | `20228083-ddc7-4fd1-b8d2-ee1c01398cc2` |
| 地图 | `mirage-cs2-v54` |
| 时间 | 2026-11-13 16:00–16:20 UTC |
| 结果 | team 0 **13–7** team 1 |
| 版本 | v0.16（main version `12`、account2 version `15`，bundle `2d473d997b99…`，entry code hash `2d473d997b99`） |
| 本仓库席位 | main：seat 8（0-based）= team 1 = 第 9 个玩家；account2：seat 5 = team 1 = 第 6 个玩家 |
| 回放 | `https://agx.cool/#/jobs/20228083-ddc7-4fd1-b8d2-ee1c01398cc2` |

### 2.2 fault 事件

公开事件 `public_events` 的第一批事件如下（按 `event_id` 排序）：

```text
1–30   match_tick=0  item_create / cash：seat 0–9
31     match_tick=0  economy_round_start
32     match_tick=0  fault  seat 5   <-- account2
33     match_tick=0  fault  seat 7   <-- 非本仓库账户
34     match_tick=0  fault  seat 8   <-- main
35–50  match_tick=1  cash / buy：seat 0–4、6、9（没有 5/7/8）
51     match_tick=0  round_start
```

- seat 5 和 seat 8 **没有任何 buy 事件**；
- 两人整场 `shots=0`、`hits=0`、`kills=0`、`deaths=0`；
- seat 7 与两个本仓库席位在同一 tick fault，可能是运行同一份代码的队友，也可能是平台同批问题；公开回放无法确认。

### 2.3 公开帧

seat 5 在 tick 0 位于 `(94.46, 129.06, 15.83)`，seat 8 位于 `(96.71, 135.58, 15.78)`，均为 Mirage T 出生点，`alive=true`、`speed=0.0`、`activity=idle`、默认 pistol。整场 20 回合位置几乎不变，从未购买、移动或开火。

这与 [11-12-stuck-at-spawn.md](./11-12-stuck-at-spawn.md) 的“卡住”形态不同：

| 形态 | 本 badcase | 路径卡住 |
| --- | --- | --- |
| 是否购买 | **没有 buy** | 通常会买 |
| 是否移动 | 从 tick 0 起 `speed=0`、idle | 有移动意图，速度/位置反复 |
| 公开事件 | **tick 0 fault** | 通常没有 fault |
| 范围 | 整个席位被禁用 | 单个路径点/回合内恢复 |

### 2.4 同轮其他对局

同一 16:00 UTC 轮次的其他公开对局 fault 数：

| match | fault 数 | 时间 |
| --- | ---: | --- |
| `20228083…`（本局） | **3** | seat 5/7/8，均在 tick 0 |
| `3a8a4c8a…` | 0 | — |
| `a210a7bc…` | 0 | — |
| `bd2dcee5…` | 2 | seat 5 tick 0；seat 9 后续 |
| `c5ba85bf…` | 1 | seat 3 后续 |

这说明该轮平台并非完全稳定；但本局两个确认运行 v0.16 的席位在同一 tick fault，仍与首拍实现高度相关。平台侧原因需要 `fault_code` / 运行日志才能排除。

## 3. 时间线与代码路径

v0.16 的 `agent.act()` 首拍执行顺序（简化）：

```text
act(o)
  if "map" in o:
      load_map(o["map"])          # 2544 nodes + 6381 edges + reverse set
  _sync_route_memory(o)           # 首次 import mirage_replay / 初始化权重
  round reset
  _note_route_success / death
  if phase == "buy":
      return self.buy(o)          # {"buy": "armor"} 等
```

首拍 observation 同时带有完整 `map`；运行时还要完成 JSON 解码。官方 Python 模板把这一过程拆开：

```python
if "map" in o:
    self.pending_map = o["map"]
# The opening observation is large. Build the navigation graph on a
# later buy callback so JSON decoding and graph work use separate budgets.
if self.pending_map is not None and ("map" not in o or o["phase"] == "live"):
    self.load_map(self.pending_map)
    self.pending_map = None
```

模板还提示首拍应尽快返回，把重活留到后续 callback；其 `init()` 同时调用 `gc.disable()`，避免大型公开地图被 GC 反复扫描。

## 4. 本地验证

用本局导出的公开静态地图（`public_static`，1.08 MB）和真实 T 出生点构造首拍 observation：

- `load_map()` 本地约 **1.5 ms**；
- 首拍 `act()` 约 **2.7 ms**，返回 `{"buy": "armor"}`，没有异常；
- 冷启动 import `agent` 约 **2.1 ms**，import `mirage_replay` 约 **0.3 ms**。

因此：

- **不是确定性的地图解析异常**：本地用真实 Mirage static + 首拍 buy observation 可以正常返回。
- 仍无法排除**首拍 callback 预算紧张**：正式环境有 JSON 解码、首次 import、调度抖动和宿主机负载；本地 2–3 ms 不代表正式环境同样快。
- 也无法排除 **worker 启动失败 / 平台侧 fault**；公开回放不提供 `fault_code`。

## 5. 解决方案（已实现并随 v0.17 提交）

### 5.1 目标

1. 首拍回调只做廉价工作：保存地图引用、读取 `sites` / `waypoints` / `plant_zones`，返回购买动作；
2. nav 图在后续 buy 回调中**分块构建**，不一次性阻塞；
3. 路线模块 import 和路线权重初始化推迟到地图 ready 之后；
4. live 开始前必须 ready；若 live 先到，允许一次性补完，保证 A* 正确；
5. 线上不再出现“一个 tick 异常导致整场席位禁用”。

### 5.2 推荐方案：首拍最小化 + 分块构建

状态机：

```text
收到 map:
  begin_map_load(row)
    - map_id / sites / waypoints / plant_zones / map_patch / advance
    - 保存 nav nodes/edges 引用与下标
    - nodes={}, edges={}, map_ready=False
    - 重置 path / combat / patrol 等每图状态
  # 本拍不构建 nav

后续每拍:
  advance_map_load(MAP_BUILD_CHUNK=512)
    - 先按节点下标填充 nodes / edges 空邻接表
    - 再按边下标填充 edges（ladder 跳过；默认不构造 reverse set）
    - 全部完成后: _apply_map_hazards(); map_ready=True
  if map_ready:
    sync_route_memory(o)   # 此时才 import replay 模块

寻路:
  route(...) 前若 !map_ready:
    补完剩余构建（兜底；正常在 buy 阶段已完成）
```

预算估算（Mirage）：

- 2544 节点 + 6381 边 = 8925 项；
- 每拍 512 项 ≈ **18 个决策拍**；
- buy 阶段约 360 tick / 20 Hz = **约 120 个决策拍**，远早于 live；
- 首个收到地图的 callback 不做图工作，后续每拍工作量有上限。

正确性兜底：

- 第一次 live 回调如果 `map_ready=False`，用一次性大预算补完（与官方模板的 live 分支一致）；
- `route()` / `nearest_node()` 入口检查 `map_ready`，未 ready 时先补完，禁止在部分图上做 A*；
- 无 nav 的地图直接 `map_ready=True`，不进入分块流程。

本地实测（2026-11-14，Mirage live static）：

- 首拍 buy `act` 约 **0.014 ms**，`nodes == {}`、`map_ready=False`；
- 第 **18** 个决策拍 ready，`nodes=2544`、路线权重 `legacy` 已初始化；
- 单拍新增节点/边不超过 `MAP_BUILD_CHUNK=512`；
- Dust2 / Mirage / Borgo / Molo / Nevaio 的分块结果与 `load_map()` 全量结果一致（nodes、edges、edge_penalty、sites 均相同）。

### 5.3 配套修改

| 修改 | 目的 |
| --- | --- |
| `init()` 调用 `gc.disable()` | 与官方模板一致，避免大型 acyclic 地图被循环 GC 扫描 |
| `_sync_route_memory()` 只在 `map_ready` 后调用 | 首拍不 import `mirage_replay` / 不初始化路线权重 |
| 默认 `USE_REVERSE_SOURCE_EDGES=False` 时跳过 `original` set 全量遍历 | 少一次 6381 条边的 pass；只有 opt-in 时才构造 |
| `load_map()` 保留为立即全量接口 | 离线 probe / 单元测试兼容；运行时改用 `begin_map_load` + `advance_map_load` |
| 可选：`act()` 顶层 try/except 返回 `{}` 并只向 stderr 打印一次栈 | 防御性兜底，避免单 tick 异常直接禁用整场；本次未实现，留作后续 |

### 5.4 备选方案

| 方案 | 优点 | 缺点 |
| --- | --- | --- |
| **A. 最小延后**：首拍只存 `pending_map`，下一拍一次性 `load_map` | 改动最小，符合官方模板 | 第二拍仍是一次性重活；宿主机抖动时仍可能超时 |
| **B. 分块构建（推荐）** | 每拍工作量有上限，buy 阶段足够完成 | 需要加状态机和 `map_ready` 守卫 |
| **C. 完全懒加载**：第一次 `route()` 前才构建 | 录制路线回合可能完全不需要 nav | 首次 A* 回调可能很重；live 首个决策风险更大 |

### 5.5 不采用的方案

- **首拍完全不保存地图**：地图只在首拍下发，之后只有 `map_id` / `static_schema_hash`，丢了就无法构建导航。
- **在首拍直接 `gc.disable()` 后仍全量 load**：只能降低 GC 抖动，不能消除首拍图构建和 import 的预算压力。

## 6. 验收

### 6.1 单元测试

- [x] 首拍带 `map` 的 buy observation：返回 `{"buy": "armor"}`，`nodes == {}`，`map_ready=False`，没有构建图；
- [x] 后续 buy 回调：每拍构建数量 ≤ `MAP_BUILD_CHUNK`，节点/边数量单调增加；
- [x] buy 结束前 `map_ready=True`，`nodes` / `edges` 与 `load_map()` 全量结果一致；
- [x] `map_ready=False` 时调用 `route()` 会先补完，再返回正常 A* 路径；
- [x] 首个 observation 就是 live 时仍能立即完成并寻路（兼容旧测试）；
- [x] 全量 `python3 -m unittest discover -s tests`：**130/130** 通过。

对应测试：`tests/test_first_callback.py`。

### 6.2 正式对局回填

- Mirage / Dust2 的 v0.17 席位不再出现 tick 0 `fault`；
- 公开帧在 buy 阶段出现 buy 事件，live 后出现移动；
- 参战 / 开火 / 到点指标按地图和攻防侧拆分，与 v0.16 对比；
- 若仍出现 fault，记录 `fault_code`（若平台可见）、seat、tick、地图，并回到本文第 4 节更新假设。

## 7. 证据记录

| 日期 | 来源 | 席位 | 观测 | 结论 |
| --- | --- | --- | --- | --- |
| 2026-11-14 | `20228083…` public events | 5 / 8 | `match_tick=0` `fault`，无 buy | 席位在首拍被禁用 |
| 2026-11-14 | `20228083…` public frames | 5 / 8 | 20 回合 `speed=0`、idle、0 发、0 死 | 不是路径卡住，是 neutral control |
| 2026-11-14 | 官方 Python 模板 | — | 注释要求把 nav 图构建延后到后续 callback | 首拍图构建是已知风险 |
| 2026-11-14 | 本地 Mirage static | — | 首拍 `act` 2.7 ms，返回 buy armor，无异常 | 非确定性解析异常；预算/平台仍待确认 |
| 2026-11-14 | 同轮 16:00 其他对局 | — | fault 0/0/2/1 | 平台同时存在不稳定，需 `fault_code` 才能定论 |
| 2026-11-14 | 本地 chunked 实现 | — | 首拍 0.014 ms、18 拍 ready、单拍 ≤512 | 修复实现与五图全量加载一致；随 v0.17 提交 |

## 8. 待确认

1. 平台是否提供 `fault_code` / worker 日志，能区分 timeout、exception、illegal action、worker exit？
2. 首拍 callback 的准确预算（是否与普通 callback 相同）？官方模板注释暗示首拍与后续 callback 的预算拆分很关键。
3. `MAP_BUILD_CHUNK` 的取值：512 已在本机五图验证；正式环境若仍有单拍压力，可调小到 256。
4. v0.16 已被 v0.17 替换（main v13 / account2 v16）；下一场需要确认 tick 0 fault 是否消失，并回填 buy / 移动 / 参战指标。
