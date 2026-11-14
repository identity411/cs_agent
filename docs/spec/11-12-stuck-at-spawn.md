# Badcase：出生点/近点卡住导致整回合不交战

Status: **2026-11-12 对局已确认；修复已提交为 `1112-v0.02` / version 2。v0.02 回填：防守侧到点 19/19、真卡死降到 12.5%；但 dust2 T 侧仍有 5 回合卡死，见 [11-12-match-observability.md](./11-12-match-observability.md)。v0.03 已加入 A* / dust2 attackRoutes / patrol，待新对局回填**
Date: 2026-11-12
Related specs: [11-12-empty-primary-switch-reload.md](./11-12-empty-primary-switch-reload.md)（空弹切枪；本场 A/C 未出现）· [11-14-first-tick-fault.md](./11-14-first-tick-fault.md)（tick 0 fault 与路径卡住的区分）· [maps.md](./maps.md)（nav 来源不证明可通行）· [baseline-compatibility.md](./baseline-compatibility.md)（地图/卡住恢复）· [agx-submit skill](../../.claude/skills/agx-submit/SKILL.md)（提交与回放来源）

## 变更记录

### 2026-11-12
- 创建 badcase。用 2026-11-12 10:00–12:00 UTC 的正式对局回放（match `da110811-9f35-4c86-9492-b322b1302391`）确认：seat 7 在多个回合位置不动、0 发射；R7 的 yaw 精确指向回退节点 `ct`。
- 修复 `agent.py` 的路径点选择、卡住恢复与转向逻辑；新增 `tests/test_movement.py`。

## 0. 文档目的

本 badcase 记录“**在出生点/近点卡住，整回合不进入战斗**”这一现象，并给出可复现证据、根因和修复验收。它比空弹切枪更影响得分：2026-11-12 的对局中，seat 7 有 **14/24 回合 0 发射**，其中 11 回合存活且手持满弹主武器。

## 1. 结论

旧的 `move` 只把距离小于 **1.0 m** 的路径点视为已到达；在 nevaio 的 CT 出生点，seat 7 被碰撞/队友挡在 `ct`（118, 18）以北约 **1.56 m** 处。路径的第一点仍是 `ct`，所以 agent 转身向**南**走回 `ct`，而不是继续向北去 `rear_corner`。卡住 80 次后旧代码清空 path，再按“最近节点”重算，最近节点仍是 `ct`，于是同一循环反复发生。

R7 的帧数据给出了一个非常明确的证据：位置 `(117.67, 19.52)`、yaw `1.357 rad`，而 `atan2(-(18-19.52), 118-117.67) = 1.357`——**yaw 精确指向回退的 `ct`，不是前进方向**。

## 2. 对局数据

| 项目 | 值 |
| --- | --- |
| 比赛 | `2a97f94f-816a-52b7-b4b8-5925db160245` |
| 轮次 | 2026-11-12 10:00–12:00 UTC（`round_state=completed`；match 10:22:50 结束） |
| match / job | `da110811-9f35-4c86-9492-b322b1302391` |
| 地图 | `nevaio-r3-v54`（24 回合；A/B 两点） |
| 版本 | version 1，code hash `eb06a768569c`，entry `f81706cb-1aa5-54e6-9e4b-e1199ca25820` |
| 结果 | team 0 **13–11** 胜；team 1（seat 7）负 |
| 排名 | 第 28 / 29（查询时；此前为 27），rating **950.32**，1 场，胜率 0% |
| 回放 | `https://agx.cool/#/jobs/da110811-9f35-4c86-9492-b322b1302391` |
| 公开回放 | `public_static` 32,692 B；`public_events` 1,831,609 B / 5,553 条；`public_frames` 1,558 块 ≈1.63 GB |

## 3. 现象与证据

### 3.1 整回合 0 发射

seat 7 在以下回合 `fire` 事件数为 0：

```
R1, R3, R5, R7, R8, R9, R14, R16, R17, R19, R20, R21, R22, R23
```

共 14 回合。其中 R1、R7、R8、R9、R14、R16、R17、R19、R20、R22、R23 共 11 回合**存活**且没有死亡；这些回合一发未开。

### 3.2 R7：位置与 yaw 指向回退节点

从公开帧抽样（`t` 为回放秒，`match_tick = t × 60` 附近）：

| 时间 | 位置 | yaw | 速度 | 手持 | 结果 |
| --- | --- | --- | --- | --- | --- |
| 630 s | `(117.65, 19.42)` | -1.437 | 1.93 | `m4a1 20/60` | 向北移动 |
| 635 s | `(117.67, 19.52)` | 0.962 | 1.93 | `m4a1 20/60` | 转向南 |
| 640–740 s | `(117.67, 19.52)` | 1.357 | 1.9–2.9 | `m4a1 20/60` | 位置不变，0 发 |

R7 的路径（goal=A，site 中心 `[112, 90, 2.4]`）按旧代码为：

```
ct (118,18) -> rear_corner (118,22) -> equipment (118,66)
-> equipment_n (118,90,2.4) -> A (112,90,2.4) -> goal
```

agent 在 `(117.67,19.52)` 时到 `ct` 的距离是 **1.56 m**，大于旧阈值 1.0 m，所以 `ct` 不会被弹出；目标 yaw 恰好是 1.357。它就这样在出生点附近反复转向/顶墙，直到回合结束。

### 3.3 其他采样

- **R8**：12:40–14:10（t=760/800/850 s）位置一直是 `(117.9, 18.9)`，0 发。
- **R22**：39:10（t=2350 s）位置 `(20.4, 110.1)`，T 出生点附近，0 发。
- **R1**：135–200 s 内 y 从 18.9 到 30.2，只前进约 11 m；速度显示 ~1.9 m/s，属于贴着墙缓慢滑动/绕路。

### 3.4 地图连通性

`nevaio-r3-v54` 的 walk-only 导航图有 38 个节点、40 条 walk 边、2 条 ladder、2 条 drop。从 T/CT 出生点 BFS 都能到达 A/B；ladder 只影响 `look_top` 区域。所以这不是“站点不可达”，而是**路径点选择/卡住恢复**的问题。注意 `maps.md` 的边界：source-adjacency 不证明直线路径可通行，碰撞/队友仍可能挡住。

## 4. 复现方式

优先使用 `agx-match-query` skill 读取公开回放：

```sh
python3 .claude/skills/agx-match-query/scripts/agx_matches.py report \
  --match-id da110811-9f35-4c86-9492-b322b1302391 --seat 7
```

查看 R7/R8 的逐帧状态：

```sh
python3 .claude/skills/agx-match-query/scripts/agx_matches.py frames \
  --match-id da110811-9f35-4c86-9492-b322b1302391 \
  --seat 7 --round 7 --every 5
```

在 web viewer 中直接打开回放链接，定位到 R7 约 10:30–12:20、R8 约 12:40–14:10、R22 约 39:10。

## 5. 根因（旧 `agent.py`）

1. **1 m 到达半径太小**：`move` 只弹出 `distance(pos, path[0]) < 1.0` 的路径点；在碰撞/队友把 agent 挡在 1.5–2.5 m 外时，agent 把“上一节点”当成目标，转身往回走。
2. **重路由选最近节点**：`route` 从 agent 当前位置找最近节点；卡住清空 path 后，最近节点仍是身后的 `ct`，于是重复同一条路径。
3. **卡住恢复只清 path**：旧代码在 `stuck > 80` 时 `self.path = []`，没有跳过阻塞点/记录阻塞边，导致“清空→同一条路→再次卡住”。
4. **没有进度看门狗**：每 tick 只比较 `distance(pos, last_position) > 0.01`；贴墙缓慢滑动可以一直重置 `stuck`，永远不触发恢复。
5. **转向时仍向前走**：旧的 `move_forward = 0.75 * cos(error)` 在目标位于身后时会给负值，agent 一边转一边向反方向走，容易顶进碰撞体。
6. **地图语义**：nav 边来自公开邻接，不保证两点直线可走；碰撞/队友仍会阻挡。修复不能假设“节点直连=可走直线”。

## 6. 修复（2026-11-12 已提交为 `1112-v0.02` / version 2）

提交快照与 receipts 见 [`../submissions/1112-v0.02/README.md`](../submissions/1112-v0.02/README.md)。`agent.py`：

- `WAYPOINT_RADIUS = 2.0`、`BEHIND_RADIUS = 4.0`：弹出已到达的路径点，以及“在下一个路径点反方向且距离较近”的路径点。R7 的 `ct` 会在第一帧被弹出，目标变成 `rear_corner`。
- `TURN_IN_PLACE = 1.2`：目标在身后时原地转向，不再倒退走。
- `blocked` 集合 + `_advance_waypoint()`：卡住时**跳过当前路径点**（记录为 blocked），保留剩余路径；path 空了再重路由，并过滤 blocked 点。
- `NO_PROGRESS_AFTER = 60` / `STUCK_SKIP = 80`：按“到当前路径点的最好距离”做进度看门狗；3 秒没有接近就跳过该点，而不是每 tick 凭微小位移重置。
- `nearest_node` 排除 blocked 路径点，避免重路由又选中身后节点。
- `stuck` 只在“有移动意图但位置不动”时累加；转向/恢复时不会误判。
- 每回合/换地图/换 goal 时清空 path、blocked 和进度状态。

测试：

```sh
python3 -m unittest discover -s tests -v
```

`tests/test_movement.py` 覆盖：

1. R7 位置不再回退到 `ct`，path[0] 为 `rear_corner`；
2. 出生点路径从前进节点开始；
3. 持续卡住时会跳过 blocked 路径点，不回到同一循环；
4. 空地正常前进无回归。

用真实 R7 帧重建 observation 后，修复版的第一拍为 `path[0]=[118,22,0]`、`yaw_rate=-1.0`（转向北），而不是旧版的 `yaw_rate=0`、`move_forward=+0.75`（向南）。

## 7. 验收

- [x] `python3 -m py_compile agent.py` 通过。
- [x] `python3 -m unittest discover -s tests -v` 4/4 通过。
- [x] 真实 R7 帧（t=650 s，seat 7）不再回退到 `ct`。
- [x] 已提交并激活为 `1112-v0.02` / version 2（admission `passed`；entry 显示 `version.number = 2`）。
- [ ] 新版本在下一轮正式对局中：seat 7 不再出现“存活 + 满弹主武器 + 整回合 0 发射”的卡住形态。
- [ ] 新对局 R7/R8 等价场景中，agent 能离开出生点/近点并到达目标区域。
- [ ] 不引入明显的路径穿透/绕远；如出现，记录回合、位置、时间并回填本文。

## 8. 待确认

1. R7 的阻挡是碰撞几何、队友、还是两者叠加？公开帧的速度显示 agent 在尝试移动，但位置完全不变；需要 web viewer/碰撞调试确认。
2. `nav` 的 `ct -> rear_corner` 直线在真实碰撞世界是否可走？如果不可走，2 m 半径只是把目标换到更远的节点，仍可能需要绕行。
3. 跳过 blocked 路径点后，剩余路径点是否仍然合理？当前保留剩余路径并在 path 空时重路由；需要在多张图上验证会不会绕远。
4. 修复对正常交战/下包路径的影响：目前只改了移动控制，不改变战斗/目标逻辑；仍需新对局回归。
5. 空弹切枪 badcase：本场 A/C 未出现，B 出现；不是本场主瓶颈，见 [11-12-empty-primary-switch-reload.md](./11-12-empty-primary-switch-reload.md)。

## 9. 证据记录

| 日期 | 场景 | 来源 | seat | round / tick | 观测 | 结论 | 备注 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 2026-11-12 | 正式对局 | public replay `da110811…` | 7 | R7 / 39000 | pos (117.67,19.52), yaw 1.357, m4a1 20/60, 0 发 | 卡住确认 | yaw 精确指向 `ct` |
| 2026-11-12 | 正式对局 | public replay `da110811…` | 7 | R8 / 45600 | pos (117.9,18.9), 0 发 | 卡住确认 | 在同一出生点附近 |
| 2026-11-12 | 正式对局 | public replay `da110811…` | 7 | R22 / 141000 | pos (20.4,110.1), 0 发 | 疑似卡住 | T 出生点；需 viewer 确认 |
| 2026-11-12 | 合成回归 | `tests/test_movement.py` | 7 | R7 | 修复后 path[0]=rear_corner, yaw_rate=-1.0 | 修复验证 | 4/4 测试通过 |
