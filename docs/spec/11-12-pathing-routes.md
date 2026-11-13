# 规范：A* 寻路、地图进攻路线与移动/战斗控制

Status: **2026-11-13 Dust2 用户轨迹跟随随 `1113-v0.06`（account2 v5）、VIP 狗洞 crouch / 推进预瞄锚点随 `1113-v0.07`（account2 v6）提交并激活；原有 `1112-v0.04` 仍为 main version 4。全量 unittest 66/66 通过；正式对局效果待验证。**
Date: 2026-11-12
Related specs: [1112-v0.03](../submissions/1112-v0.03/README.md)（提交快照）· [1113-v0.05](../submissions/1113-v0.05/README.md)（Dust2 用户轨迹跟随）· [1113-v0.06](../submissions/1113-v0.06/README.md)（原地准星帧修正）· [1113-v0.09](../submissions/1113-v0.09/README.md)（Mirage 录制轨迹）· [11-12-advance-holds.md](./11-12-advance-holds.md)（下游：寻路之后的推进点 / 预瞄角 / 刹停）· [11-12-mirage-spawn-jump.md](./11-12-mirage-spawn-jump.md)（Mirage R6/R10 与 CT A 卡台阶）· [11-12-match-observability.md](./11-12-match-observability.md)（卡死/到点/回防指标）· [11-12-stuck-at-spawn.md](./11-12-stuck-at-spawn.md)（出生点卡住）· [11-12-site-center-hold.md](./11-12-site-center-hold.md)（包点中心 hold）· [maps.md](./maps.md)（nav / bot_waypoints 边界）· [agent-interface.md](./agent-interface.md)（动作字段）

## 0. 目标

让 T 方能够：

1. **走出去**：从出生点快速离开，不在近点/墙角反复卡住；
2. **去包点**：按地图作者给的进攻路线（例如 dust2 的 A 大、A 小、中门、B 洞、B 门）到达包点；
3. **杀敌**：遇到敌人时不要整回合站桩，能在推进/交火之间切换；
4. **埋下包**：拿包的人进入 `plant_zones` 下包，队友在附近掩护；
5. **下包后守包**：T 方去 watch 点，而不是停在炸弹脚下。

## 1. 分层

```text
目标层：选包点 / 选进攻路线 / 谁拿包
   ↓
规划层：A*（距离权重 + 执行反馈边代价）+ attackRoutes lane
   ↓
控制层：sprint/walk + 路径点跟踪 + stuck 跳过
   ↓
战斗层：combat strafe + 战斗超时恢复
   ↓
目标动作：plant_zones 下包 / post-plant watch / CT defuse
```

## 2. 规划层

### 2.1 A* 替代无权 BFS

`route()` / `_astar()`：

- 节点仍是公开 `map.nav.nodes`；
- 边权 = 两节点欧氏距离 × `(1 + edge_penalty)`；
- 启发式 = 当前节点到目标点的欧氏距离；
- 使用 `heapq`；
- 末尾追加精确 goal（site center / 炸弹 / plant 点 / watch 点）。

这解决“边数最少但绕远”的问题，但**不解决 nav 边实际不可走**；后者靠边代价和卡住恢复。

### 2.2 执行反馈边代价

- 卡住/跳过当前路径点时，给 `(from,to)` 边加 `+4.0` 惩罚，上限 `8.0`；
- 成功通过一条边时乘 `0.8` 衰减；
- 惩罚跨回合保留（同一张图内学习），不因换目标清空；
- `blocked` 仍是硬跳过，按位置记录；换目标/回合时清空。

### 2.3 source-adjacency 反向边

`maps.md` 明确说反向边、跨出生点拼接等要实测。当前实现：

- `walk` 双向；
- `drop` 单向；
- `ladder` 跳过；
- `source-adjacency` 默认**不合成反向边**（`USE_REVERSE_SOURCE_EDGES = False`）。
  - 原因：实测 dust2 A 路线曾选中一条 `+3.07 m` 的“反向边”，很可能是从高台跳下而不是可走上去的坡；合成反向边会把 agent 送进不可达位置。

### 2.4 dust2 进攻路线

`map.bot_waypoints.attackRoutes`（当前公开数据里只有 dust2 有）：

| route key | 中文口径 | 点序列 |
| --- | --- | --- |
| `A_long` | A 大 | `long -> A` |
| `A_split` | A 小 / 中门 | `mid -> short -> A` |
| `B_long` | B 洞 / b2 | `tunnels -> bEntry -> B` |
| `B_split` | B 门 / 中门 | `mid -> doors -> B` |

选择规则（`route_lane_points()`）：

1. 只保留终点是目标包点的 route；
2. 估算“当前位置到第一个 lane 点 + lane 段长度”；
3. **拿包的人走最快 lane**；
4. 不拿包的人如果两条 lane 长度相差 ≤20%，按 `(seat + round_index) % n` 分散；
5. 每回合 / 每个包点缓存一次选择；
6. 进入 `site.radius` 内后不再走 lane；T 方下包前不使用 patrol（避免在 `radius+12` 边界来回切 goal），下包后才用 `watch<site>_T`。

没有 `attackRoutes` 的地图（nevaio/borgo）回退到 A* 直达 site center；不硬编码地图路线。

### 2.5 旧卡点 soft hazard 与 `map_patches.py`

所有地图坐标和阈值都不再写在 `agent.py`。根目录 `map_patches.py` 的 `MapPatch` 是 agent 读取的抽象修补层：

```python
patch = map_patches.for_map(map_id)   # 未知地图返回中性 EMPTY
patch.hazards                         # ((x, y, radius), ...)
patch.step_jump_height                # 台阶跳高度
patch.step_jump_radius                # 台阶跳水平距离
```

当前种子：

- dust2 T 侧 `(83.4, 88.2)`：v0.02 R13 起卡住；
- dust2 CT A 点入口 `(160.63, 125.71)`：R7 在 `(160.63,125.71)` 与 `(158.9,119.2)` 之间反复上下坡；
- Mirage CT A 入口 `(42.8, 66.4)`：v0.03 对局 seat 3 在 R13/15/17/19/21 停在 `(42.8,66.4,14.3)` 附近，速度约 0.01，A 点中心在 `(44.67,88.18)`，始终没上去。

规则：

- 半径内的 nav 节点，其所有入射/出射边初始惩罚 = `EDGE_PENALTY_MAX`；
- 这是 **soft penalty**，不是硬禁行；没有替代路径时 A* 仍可走；
- 目的是让 `A_split` 这类原本经过 244/307 附近的分支优先绕开；`A_long` 本来就不经过该点；
- 如果后续碰撞级验证证明该点可走，应降低/删除这个种子，避免过度绕路；
- 新增地图修补只改 `map_patches.py`，不改 `agent.py` 的地图分支。
- 低矮通道（蹲行狗洞）用 `MapPatch.crouch_gates` 描述；`agent.traverse_gate()` 会 `crouch=True` 直行通过并**禁止跳跃**，穿过后重新 A*。Mirage VIP `(75.3,66.2)` 的取证见 [11-13-mirage-vip-doghole.md](./11-13-mirage-vip-doghole.md)。

### 2.6 本地 nav 模拟

`scripts/simulate_nav.py` 使用平台自己的 `public_static`（2242 nodes / 6275 edges）作为固定输入，20 Hz 运动学推进 agent 动作；它不是碰撞模拟，但可以重复验证：

- 目标/路线是否连通；
- goal 是否在 near-site 边界振荡；
- 注入旧卡点/圆形障碍后是否还能绕开；
- 到点时间是否在回合预算内。

## 3. 控制层

- 路径点弹出：距离 < 2.0、已被 blocked、或在下一个点反方向且 < 4.0；
- 目标在身后（`|error| > 1.2`）时原地转向，`forward=0`；
- **sprint / walk**：
  - 无可见敌人、离 goal > 20 m、体力够 → `walk=False, sprint=True`，输入 1.0；
  - 接近包点 / patrol / 交火 / 体力不足 → `walk=True`；
- stuck：
  - `stuck > 20`：后退 + 横移 + 跳；
  - `stuck > 80` 或 `wp_ticks > 60`：当前点加入 blocked、边加惩罚、跳过并重路由；
- 最终 goal 在脚下（<0.6 m）时保持位置，不再对零向量原地转。

### 3.1 前进跳 / 台阶跳

旧 `stuck` 只检查“位置有没有变”。碰撞滑动会让位置每拍都变，但 agent 在原地/墙边左右摩擦，`stuck` 永远不累计，跳跃恢复不触发；Mirage R6 的带包 seat 2 就是这样滑了 100+ 秒。

现在：

- 用 `wp_progress += last_d - d` 累计净进度；达到 `WAYPOINT_PROGRESS=0.4` 才清零。左右摩擦净进度≈0，仍会累计 `wp_ticks`；
- `wp_ticks >= JUMP_AFTER_TICKS=12`（约 0.6 s）、朝向对齐、`grounded`、冷却（`JUMP_COOLDOWN_TICKS=24` match tick）结束时，**向前跳**并保持 `move_forward>0`；
- 每个 waypoint 最多 `JUMP_ATTEMPTS=3` 次前进跳；之后才跳过该点并加边惩罚；
- 下一个 waypoint 比脚底高 ≥ `map_patch.step_jump_height`（默认 0.8 m）、水平 ≤ `map_patch.step_jump_radius`（默认 2.5 m）时，直接台阶跳；
- `stuck > STUCK_AFTER` 时先尝试朝 waypoint 前进跳，跳不了才退回后退 + 横移。

Mirage 证据与两个已知台阶见 [11-12-mirage-spawn-jump.md](./11-12-mirage-spawn-jump.md)。

## 4. 战斗层

- 有可见敌人时进入 combat，但不再无条件站桩：
  - 瞄准已对齐且枪 ready → `crouch=True`，开火；
  - 未对齐/未 ready → `crouch=False`，左右 strafe（0.35，每 0.5 s 换向）；
- **战斗超时**：连续 90 个 match tick（约 1.5 s）没有开火 → 进入 60 tick（约 1 s）的 `combat_move` 窗口；这不是纯移动，而是**保持瞄准/开火**的同时沿当前路径以 0.35 输入推进；之后再重新进入正常交战；
- 若在 `combat_move` 期间开火，立即清掉冷却，下一拍回到正常交战；
- 不改变原有瞄准/弹道逻辑，只改变“看见敌人就冻结”的行为。

## 5. 目标动作

- **T 拿包**：goal = `plant_point(site)`；进入 `plant_zones` 多边形后 `use="plant"`；
  - 有可见敌人且距离 ≤20 m 时先打，敌人远/不可见时下包；
  - 无 `plant_zones` 的地图回退到 site center 半径 × 0.5。
- **T 不拿包**：优先跟 `bomb.site`；没有 site 时用 `teammates.zone` 的 A/B 多数；再回退 seat 奇偶（不用隐藏/会移动的 `bomb.position` 做目标，避免来回换点）。到点后用 `watch<site>_T` / `hold<site>` patrol。
- **T 下包后**：去 `watch<site>_T` 中离炸弹最近的点；没有 watch 时保持距炸弹 8 m 内慢转；有敌人先打。
- **CT**：
  - 未下包：去 site center，近点后用 `hold` / `watch_CT` patrol；
  - 已下包：goal = 炸弹位置；无可见敌人或引信 <10 s 时 `use="defuse"`，否则先交战；
  - 回防仍受 sprint 速度影响，下一轮用 `agx_observe.py` 验证到位率。

### 5.1 临时 T 兜底：40 s 未下包 → CT spawn

**这是临时逻辑，不是长期战术。** 比赛初期各家的 nav 数据/碰撞都不稳定，agent 容易卡在自家出生点；为了避免整回合卡死，T 方在 `round_tick >= 2400`（40 s，60 Hz，包含 freeze time）仍未下包时，直接改目标为 CT 出生点：

- 条件：`side == "attack"`、`bomb.state != "planted"`、**`me.carrying_bomb == false`**、`round_tick >= TEMP_T_CT_FALLBACK_TICKS`、地图有 CT spawn；
- **带包人豁免**（2026-11-13）：自己带包时兜底不生效，目标仍是 `plant_point(site)`；在 plant zone 内且安全时直接下包，下包后进入守包 hold；不带包的队友仍按兜底去 CT spawn；
- 一旦炸弹下包，立即恢复 T post-plant watch；2026-11-13 起改用 `advance_holds.PlantHold` 的掩体 spot + 离散 look 循环，不再原地 `yaw_rate=0.15` 转圈（见 [11-13-post-plant-holds.md](./11-13-post-plant-holds.md)）；
- CT 方、已下包回合不受影响；
- 代码常量 `TEMP_T_CT_FALLBACK_TICKS` 和注释都标了 `TEMPORARY`，后续 nav 边验证完成、卡死率下降后应删除；
- 地图没有 `spawns` / `spawn_pads_by_side` 时自动禁用。

## 6. 代码位置

| 逻辑 | 位置 |
| --- | --- |
| A* / via 路线 | `agent.py` `_astar()` / `route()` |
| 边代价 | `agent.py` `_penalize_edge()` / `_decay_edge()` / `edge_penalty` |
| 进攻路线 | `agent.py` `route_lane_points()` |
| 选包点 | `agent.py` `choose_site()` |
| plant 区 | `agent.py` `plant_point()` / `in_plant_zone()` |
| patrol | `agent.py` `patrol_points()` / `watch_point()` |
| sprint / stuck / 前进跳 / 台阶跳 | `agent.py` `move()` |
| 地图修补（hazard / 台阶阈值） | `map_patches.py` `MapPatch` / `for_map()` |
| 临时 T 40 s → CT spawn 兜底 | `agent.py` `TEMP_T_CT_FALLBACK_TICKS` / `act()` / `_first_spawn()` |
| combat strafe / 超时 | `agent.py` `combat()` / `act()` |

## 7. 验证

```sh
python3 -m py_compile agent.py
python3 -m unittest tests.test_movement -v
python3 -m unittest discover -s tests -v
```

当前本地结果：

- `tests.test_movement` 18/18 通过（含前进跳 / 台阶跳 / `map_patches` 接线 / 临时 T 兜底）；
- 真实 dust2 static：T 方 seat 0–4 会分散到 `A_long/A_split`、`B_long/B_split`；拿包的人走最快 lane；
- dust2 T→A 路径约 166 units、T→B 约 152 units（无合成反向边）；
- nevaio/borgo 无 `attackRoutes`，A* 直达 site；路径约 58–124 units。
- 全量 unittest 53/53（18 movement + 28 account/batch + 7 dust2 regression）。

### 7.1 本地可重复 nav 模拟

用仓库里固定保存的 dust2 `public_static`（`tests/fixtures/dust2_static.json`，2242 nav nodes / 6275 edges，平台同坐标系）做固定输入：

```sh
python3 scripts/simulate_nav.py
python3 scripts/simulate_nav.py --legacy-stuck
python3 scripts/simulate_nav.py --agent docs/submissions/1112-v0.03/agent.py
```

`--legacy-stuck` 会把 v0.02 R13 的卡死位置 `(83.4, 88.2)` 作为半径 1.8 m 的圆形障碍注入。T 侧结果（20 Hz 运动学模型，无真实碰撞）：

| 回合 | 目标 | 路线 | 结果 | 模拟用时 |
| --- | --- | --- | --- | ---: |
| R13 | A | A_long | reached | 49.8 s |
| R14 | B | B_long | reached | 37.6 s |
| R15 | A | A_long | reached | 49.8 s |
| R17 | A | A_long | reached | 49.8 s |
| R19 | A | A_long | reached | 49.8 s |

- 注入旧卡点后，A rounds 仍能到达：A_long 本来就不经过 244/307 附近；A_split 分支通过 seeded hazard（见 2.2/2.5）绕开。
- **本地模拟发现并修正了一个真实代码问题**：T 方 pre-plant 的 near-site patrol 与 attack lane 会在 `site.radius+12` 边界来回切换 goal，导致在 A 点外侧反复转圈；现在 T 方下包前不再 patrol，via 只在 `site.radius` 内关闭。
- **v0.03 快照对照**：用同一个模拟器跑 `docs/submissions/1112-v0.03/agent.py`，A rounds（R13/15/17/19）在 120 s 内 **timeout**（B R14 正常）；当前工作区全部 `reached`。所以 v0.03 的“A 点外侧转圈”是本地可复现的代码问题，不是纯碰撞问题。

CT 侧也可以用同一脚本：

```sh
python3 scripts/simulate_nav.py --side defend
python3 scripts/simulate_nav.py --side defend --site B --round 2
# 从 B 中心开始，专门看 site-center hold
python3 scripts/simulate_nav.py --side defend --site B --round 2 \
  --start 167.37,60.24,20.13
```

已测 CT 结果：

- dust2 CT 出生点 → B：current 18.2 s，v0.03 18.2 s；A：12.4 s。
- dust2 R2 B 中心 hold：v0.02 在 60 s 内最大位移 **0.07 m**（真卡）；v0.03/current 最大位移 **4.21 m**，patrol 点会轮转（site-center hold 已修）。
- dust2 CT A 点入口：v0.02 R7 公开帧显示 agent 在 `(160.63,125.71,20.71)` 与约 `(158.9,119.2,18.8)` 之间每 2–4 s 来回一趟，持续到回合结束；这是 CT 侧的第二个卡死形态（上坡/台阶碰撞，不是 B 中心 hold）。
- 当前 A* 的 CT→A 路径离该旧点最近约 **5.03 m**（v0.02 旧 BFS 路径约 3.44 m），并对该点种了 soft hazard；能否真正避开台阶仍取决于碰撞世界。
- nevaio CT R7–R10：current nav 模拟 26.2 s 到点；v0.01/v0.02 nav 模拟约 51 s。**真实碰撞未知**，不能据此判断 nevaio 旧 CT 出生点卡死是否修复。
- Mirage CT A 点（2026-11-12 14:00 v0.03 对局 `d24bd037…`，main seat 3）：R13/15/17/19/21 公开帧停在 `(42.8,66.4,14.3)`，A 点 `(44.67,88.18)` 约 22 units 外；v0.03 A* 路径离该旧点最近约 **3.92 m**。当前工作区加了 Mirage soft hazard 后路径最近约 **14.69 m**，nav 模拟 CT→A 22.4 s reached；真实台阶碰撞仍待验证。
- 2026-11-12 14:00 UTC 的 v0.03 Mirage 对局（`d24bd037…`）已结束。R6 带包人是 seat 2，整队卡在 T 出生点、0 次开火；R10 带包人 seat 1 在同一拐角跳出来后下包 A。R13 的 CT seat 3 在 A ramp 与东侧 `(74.6,62.3)` 两次卡台阶。详见 [11-12-mirage-spawn-jump.md](./11-12-mirage-spawn-jump.md)。
- 已下载 `/assets/fps-v54-cs2/mirage/reconstruction.json`（2.7 MB，73,152 个三角形分类 / 1,717 个 source volume）；`mirage-positions.f32`、`mirage-materials.u8`、`mirage-walked-nav.json` 在公开 API 上均为 404。

- **这不是碰撞级证明**：`static.json` 的 `collision.positions` 只有网格文件路径/SHA/三角形数和 basis/offset，**没有 f32 数据本身**；本地无法复现真实高度场/台阶/箱子碰撞。nav 模拟只能证明路径连通、目标切换和软 hazard 恢复，不能保证正式对局不卡。

## 8. 待验证 / 已知限制

- `v0.03` 已提交/激活；`v0.04` 已把 T 方 pre-plant patrol 关闭、dust2/Mirage soft hazard、前进跳 / 台阶跳、`map_patches.py` 提交/激活（`scripts/simulate_nav.py` 仅本地，不随 ZIP）。
- 尚未跑新对局；所有效果需用下一场正式对局和 `agx_observe.py` 回填。
- 没有可用的碰撞网格文件；static 只有引用。nav 边仍可能不可走，边代价只能事后学习。
- `map_patches.py` 里的 hazard 是从公开帧单次卡死位置种下的 soft penalty；如果碰撞验证显示该点其实可走，应降低/删除，避免过度绕路。
- 临时 T 兜底（40 s 未下包 → CT spawn）是为了绕开早期 nav/碰撞卡死，不是正常战术；2026-11-13 起带包人已豁免（见 §5.1），不带包的队友仍可能被拉去 CT spawn；nav 卡死率下降后应删除 `TEMP_T_CT_FALLBACK_TICKS` 分支。
- `source-adjacency` 反向边默认关闭；若后续实测可走，再逐图开启。
- `plant_point` 目前优先选 zone 内离 site center 最近的 nav 节点；若该点被挡，仍可能走不到。
- CT 还没有 dust2 `ctRoleLane`/`ctRoles` 的进攻性分路；本轮先解决 T 方“出去/到点/下包”。
- 战斗超时是行为兜底，不保证命中率；下一轮要同时看参战率和命中率。
- patrol 仍依赖 `bot_waypoints`；nevaio/borgo 到包点中心后仍是 hold，不是巡逻。

## 9. 验收

- [x] A* 距离权重测试（少数边但更长的路不会被选）。
- [x] dust2/attackRoutes lane 选择 + sprint 测试。
- [x] `bomb.site` 覆盖 seat 奇偶测试。
- [x] plant_zones 下包测试。
- [x] combat strafe + 超时恢复测试。
- [x] 真实 dust2/nevaio/borgo static 路径冒烟测试。
- [x] 前进跳 / 台阶跳 / `map_patches` 接线测试。
- [x] 临时 T 兜底：40 s 未下包去 CT spawn；下包后/CT 方不触发；带包人 2026-11-13 起豁免。
- [x] 2026-11-13：`combat()` 增加 `STOP_SPEED` 刹停门与远距离 tap；T post-plant 改用 `PlantHold` spot/look，不再原地转圈。
- [ ] 新对局：dust2 T 侧 R13/R14/R15/R17/R19 不再“未到点且离出生点 <20 units”。
- [ ] 新对局：T 方有开火/交战回合比例不低于 v0.02；到点时间中位数 <40 s。
- [ ] 新对局：拿包回合能进 plant zone 下包；下包后不再停在炸弹 8 m 内慢转（本地已用 PlantHold 修复，待回填）。
- [ ] 新对局：Mirage T 出生点西侧 / CT A 台阶不再整回合卡住（见 `11-12-mirage-spawn-jump.md`）。
