# Badcase：到达包点后站在中心不动（R2）

Status: **2026-11-12 已用公开帧复现；patrol 修复随 `1112-v0.03` 提交/激活，待新对局验证**
Date: 2026-11-12
Related specs: [1112-v0.03](../submissions/1112-v0.03/README.md)（提交快照）· [11-12-stuck-at-spawn.md](./11-12-stuck-at-spawn.md)（出生点/近点卡住）· [11-12-match-observability.md](./11-12-match-observability.md)（卡死/到点指标）· [11-12-pathing-routes.md](./11-12-pathing-routes.md)（A* / attackRoutes / patrol）· [maps.md](./maps.md)（dust2 参数与 `bot_waypoints`）· [agx-match-query skill](../../.claude/skills/agx-match-query/SKILL.md)（公开帧复现）

## 0. 文档目的

按用户定义：**一个回合基本停在一个点就算卡死**，不要求“没到 A/B 点”。本 badcase 记录 seat 3 在
`36cf9b6c-78ec-469f-b008-daca03bf0e73` 的 R2 到达 B 点后停在 B 中心、整段不再移动的现象，并给出地图参数、复现和修复。

## 1. 对局与证据

| 项目 | 值 |
| --- | --- |
| match | `36cf9b6c-78ec-469f-b008-daca03bf0e73` |
| 地图 | `dust2-cs2-v54` |
| 回合 | R2（start 15120，end 22380） |
| 席位 | seat 3，team 0，CT/defend |
| B 点参数 | center `[167.3735, 60.2617, 20.2032]`，radius `6.3` |
| 到达 B | tick 16920（约冻结结束后 24 s） |

公开帧在 B 中心附近的稳定段：

| tick | 位置 | yaw | speed | 武器 | 事件 |
| ---: | --- | ---: | ---: | --- | --- |
| 21000 | `(167.37, 60.24, 20.13)` | 0.431 | 1.43 | m4a1 20/60 | 0 发 |
| 21120 | `(167.37, 60.24, 20.13)` | 0.431 | 1.43 | m4a1 20/60 | 0 发 |
| 21240 | `(167.36, 60.24, 20.13)` | 0.431 | 1.43 | m4a1 20/60 | 0 发 |
| 21360 | `(167.36, 60.24, 20.13)` | 0.431 | 1.43 | m4a1 20/60 | 0 发 |
| 21600 | `(167.37, 60.23, 20.13)` | 0.431 | 1.43 | m4a1 20/60 | 0 发 |

位置基本等于 B 点 center；速度不为 0，但实际位移为 0。按用户定义，这就是卡死。

## 2. 地图参数

来自公开 `public_static`：

```text
site B center = [167.3735, 60.2617, 20.2032], radius = 6.3
bot_waypoints.holdB = [
  [169.0, 54.0, 20.8], [168.0, 62.0, 20.3],
  [170.0, 66.0, 20.4], [165.0, 57.0, 20.3]
]
bot_waypoints.watchB_CT = [
  [157.0, 57.0, 21.5], [166.0, 70.0, 23.0], [156.0, 72.0, 21.0]
]
```

缓存位置：`data/accounts/main/matches/36cf9b6c-78ec-469f-b008-daca03bf0e73/static.json`（gitignored）。

## 3. 复现（本地）

用 R2 tick 21000 的公开帧（seat 3，B center，yaw 0.431，m4a1 20/60，无可见敌人）构造 observation，调用修复前/后的 `agent.act`：

- **修复前**：`goal = site.center`，`path = [[167.37, 60.26, 20.20]]`；目标就是脚下，`move_forward=0`、`move_right≈0.72`、`yaw_rate=-1`；角色原地转向/侧移，位置不变。
- **修复后**：`goal = holdB[0] = [169.0, 54.0, 20.8]`，动作有前进/转向；到达后切到 `holdB[1]` 等，不再停在 B 中心。

用缓存 `static.json` 重跑真实 R2 帧：

```sh
python3 scripts/reproduce_r2_patrol.py
```

回归测试：

```sh
python3 -m unittest tests.test_movement -v
```

- `test_site_center_uses_patrol_waypoints`：B 中心目标不是 center，而是 `holdB[0]`；到达后切到 `holdB[1]`。
- `test_patrol_advances_when_position_is_blocked`：位置连续不动时，patrol 会切换下一个点，而不是永远守同一个点。

## 4. 根因

1. `act` 对防守方的默认目标是 `site["center"]`；到达中心后目标与脚下重合。
2. `move` 对零向量目标仍计算 `atan2`/`forward`/`strafe`，产生原地转向/侧移；引擎位置不变。
3. 没有“站点 hold/patrol”状态；虽然 `stuck`/`wp_ticks` 会清 path，但下一帧 `route` 又从当前位置生成同一个 center 目标，形成“原地不动”的循环。
4. 地图已经提供 `bot_waypoints.holdB` / `watchB_CT`，旧代码完全没有使用。

## 5. 修复

`agent.py`：

- `load_map` 保存公开 `bot_waypoints`。
- `patrol_points(site, side)` 优先使用 `holdA/holdB`，再使用 `watchA_CT` / `watchB_CT`（进攻方用 `watchA_T` / `watchB_T`）；地图没有 waypoints 时保持旧行为。
- 在 `act` 中，当炸弹未安装、自己没有携带炸弹、没有可见敌人时，把目标从 site center 改成当前 patrol 点；到达 2.5 m 内就切下一个点。
- 若连续约 2 s 位置不变，直接切下一个 patrol 点（避免某个点被碰撞卡住）。
- 每回合/换图/换边重置 patrol 状态。

## 6. 验收

- [x] `python3 -m py_compile agent.py`。
- [x] `python3 -m unittest tests.test_movement -v` 6/6。
- [x] 真实 dust2 B center 帧：修复后 `goal` 变为 `holdB[0]`，不再是 site center。
- [ ] 新对局：seat 3 到达 B/A 后不再整段停在同一个点；若 patrol 点也卡住，记录位置/回合。
- [ ] 不引入明显“离开包点/绕远”的副作用；patrol 点仍围绕 A/B。

## 7. 待确认

1. `holdB` 点在实际碰撞世界是否可达；当前有一个 2 s 超时切点，但若全部点都不可达，仍可能回到中心。
2. patrol 是否会让防守方离开包点过远，影响安放/拆包；当前只在无敌人/无目标时巡逻。
3. 用户定义的“一直呆在一个点”是否需要更严格的连续位置方差指标；见 [11-12-match-observability.md](./11-12-match-observability.md) 的卡死口径。
4. 对手队 inactive 是另一条数据质量问题；本 badcase 只针对 seat 3 的站点 hold。
