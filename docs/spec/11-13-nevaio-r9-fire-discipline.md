# Badcase：nevaio R9 台阶卡脚 + 远距离扫射（刹停 / 点射）

Status: **已用 account2 `fbd4b6bf` 公开帧/事件确认；刹停门与远距离点射随 `1113-v0.08` 提交，`main` v5 / `account2` v7 admission `passed` 并激活；75/75 测试通过；待新对局验证**
Date: 2026-11-13
Related specs: [11-12-advance-holds.md](./11-12-advance-holds.md)（§3.2 BRAKE / §6 STOP_SPEED / TAP）· [11-12-pathing-routes.md](./11-12-pathing-routes.md)（A* / edge penalty / map patch）· [11-12-stuck-at-spawn.md](./11-12-stuck-at-spawn.md)（出生点卡住）· [agx-match-query skill](../../.claude/skills/agx-match-query/SKILL.md)（公开帧取证）

## 1. 对局与证据

| 项 | 值 |
| --- | --- |
| match | `fbd4b6bf-d9b4-4082-8cd9-a3451a32fd44` |
| 地图 | `nevaio-r3-v54` |
| 回合 | R9（defend/CT；round start tick 42147，live end tick 49407） |
| 席位 | seat 0（0-based）= team 0 = 第 1 个玩家 |
| 版本 | v0.07 / version 6 |
| 结果 | 4–13 负 |

公开帧（`frames`）关键观察：

| tick | 位置 | 速度 / 状态 | 事件 |
| ---: | --- | --- | --- |
| 42147–43968 | `(117.30,18.04,0)` 位置不变 | speed 2.0–4.7，反复 `grounded=False` / `vz>0` | 在 CT 出生点西出口原地滑动 + 跳跃约 28 s |
| 43199（约剩余 1:37） | `(117.30,18.04,0)` | speed 4.27，airborne | 用户指出的 1:37 卡脚时刻 |
| 43618–43636 | `(117.30,18.04,0)` | 静止/在空中 | 对 90.6 m 外 seat 7 连开 4 枪 M4A1（`fire` 事件 43618/43624/43630/43636），即“直接扫射” |
| 43968–44128 | 从 `(117.30,18.04)` 移动到 `(107.5,20.0)` | 水平速度恢复 5.7 | 终于从台阶挤出去 |
| 44314–44326 | `(90.0,22.0)` → `(89.6,22.2)` | 移动中开火 | 对 38 m 外 seat 9 连开 3 枪并击杀 |

R7 同一出生点也整回合卡住：tick 33738–33750 位置 `(118.09,18.03)`，速度方向 `(-4.7,+1.4)`，说明 R7/R9 都在往 `warm_hall`（86,18）西出口挤。

## 2. 根因

1. **没有刹停门**：旧 `combat()` 在准星未对齐时给 `move_right` 侧移，`combat_move()` 还会在开枪的同一 tick 设置移动；公开帧里因此出现“滑动中扫射”。规范 [11-12-advance-holds.md](./11-12-advance-holds.md) §3.2 早已定义 `STOP_SPEED=1.0`，但代码未实现。
2. **远距离仍按扫射扳机**：旧代码只要主武器 `weapon_slot=0` 就每 tick `fire=True`，没有 head-only / 距离判断。
3. **CT 出生点路线被 stale edge penalty 推向 `warm_hall`**：`edge_penalty` 跨回合累积。用真实 nevaio static 复盘：
   - 干净状态：A* 对 CT→B 已经走 `ct → rear_corner → rear_door → B`（74 m）；
   - 如果之前回合把 rear 边学成 `EDGE_PENALTY_MAX`，A* 改走 `ct → warm_hall → warm_gate → rear_door → B`，与 R7/R9 的向西运动一致；
   - 只加 warm_hall hazard 而不清旧惩罚，A* 会绕出 187.8 m 的 `A → ladder → B` 大圈。

## 3. 修复

`agent.py`：

- 新增 `STOP_SPEED=1.0`、`CLOSE_SPRAY_RANGE=20.0`、`TAP_INTERVAL_TICKS=15`、`TAP_ALIGN=0.02`、`SPRAY_ALIGN=0.04`。
- `combat()`：
  - 看到敌人立即 `move_forward=0`、`move_right=0`、`sprint=False`；
  - `parts` 只有 head → 瞄头；`head_only` 或水平距离 > 20 m → tap 模式，单发点射（间隔 ≥ 15 ticks）；
  - 近距离且 `chest`/`abdomen` 可见 → spray 模式；
  - 两种模式都要求 `grounded` 且 `speed <= STOP_SPEED` 才 `fire=True`；
  - 使用独立的 `combat_tap_tick` 维持点射节奏，不复用战斗超时时间戳。
- `combat_move()` 强制 `fire=False` 再移动：移动与开火互斥，同时保留超时后的反卡死推进。
- 回合切换时 `edge_penalty.clear()` + `_apply_map_hazards()`：清除上个回合的学习惩罚，保留永久地图 hazard。

`map_patches.py`：

- 新增 `nevaio-r3-v54` 的 soft hazard `(86.0,18.0,4.0)`（`warm_hall` 节点），CT→B 改走 rear_corner；CT→A 仍是 `ct → rear_corner → equipment → equipment_n`（72.2 m，不变）。

## 4. 验收

- 公开帧复现：R9 的 90.6 m head-only 场景，本地构造 observation 后：
  - airborne/speed>1 时 `fire=False`、不移动；
  - speed=0 时按 15 tick 间隔单发；
  - 整个过程 `move_forward=0`、`move_right=0`。
- 单元测试：`test_long_range_head_only_taps_without_moving`、`test_combat_does_not_fire_while_airborne_or_moving`、`test_combat_brakes_then_resumes_path`、`test_nevaio_hazard_forces_rear_corner_route`、`test_round_reset_clears_learned_penalties_but_keeps_hazards`。
- 真实 nevaio static：`ct→warm_gate` / `ct→B` 均走 `rear_corner`，且 `edge_penalty[(ct,warm_hall)] = 8.0`。
- 待下一场正式对局回填：站定开火占比、远距离 head-only 命中、CT 出生点 10 s 内离开、R9 不再原地跳 28 s。
