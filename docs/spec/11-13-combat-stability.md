# Badcase：R19 第二目标抽搐 + R18 出生点被队友卡死

Status: **公开帧已确认；已随 `1113-v0.11` 提交，`main` v7 / `account2` v10 admission `passed` 并激活；本地 86/86 unittest 通过；待新对局验证**
Date: 2026-11-13
Submission: [1113-v0.11](../submissions/1113-v0.11/README.md)
Match: `5466919c-22aa-45f5-8b0c-fee9143708b0`（main，dust2-cs2-v54，2026-11-13 04:00 UTC，version 5 / v0.08）
Seat: **seat 4（0-based）= team 0 = 第 5 个玩家**
Related specs: [11-13-fire-range-bands.md](./11-13-fire-range-bands.md)（点射频率）· [11-12-pathing-routes.md](./11-12-pathing-routes.md)（录制轨迹）· [11-13-nevaio-r9-fire-discipline.md](./11-13-nevaio-r9-fire-discipline.md)（刹停）

> 用户口中的 R19 / R18 是网页 1-based 回合号；下文同时标注事件的 0-based `round_index`。

## 1. R19（round_index 18）：击杀第一人后对第二人抽搐

公开事件：

| tick | 事件 |
| ---: | --- |
| 133633–133651 | seat 4 用 AK 连续 4 发上身命中，击杀 seat 6 |
| 133663–133903 | seat 4 继续每约 9 ticks 开一枪（约 28 发），**0 命中** |
| 133906 | seat 4 空弹匣换弹 |
| 133966 | seat 8 一枪爆头击杀 seat 4 |

公开帧（seat 4，`round_index 18`）：

- 存活敌人只有 seat 9 在 **24.7 m**，其余 seat 5/7/8 在 **48–50 m**；
- 每 8–13 ticks 出现一次 `crouch=True → False`、yaw 在 **1.27 ↔ 1.38–1.47** 间摆动、pitch 在 **-0.22 ↔ -0.12** 间摆动、速度 0 → 1.0 m/s → 0；
- 对准角在两个簇之间切换：crouch 时对准 24.7 m 的 seat 9（误差 <1°），站立时对准 48–50 m 的 seat 5/7/8（误差 ~0–3°）；
- `walk` 标志在 `True/False` 间交替，说明 agent 在 **combat() 与录制轨迹移动之间来回切换**。

根因：

1. **可见性闪烁**：敌人半掩体探头时 `visible` 在 20 Hz 决策间反复变空。旧代码在每次 `visible` 为空的 tick 调用 `_reset_combat_state()`，清空 `combat_tap_tick` / 锁定目标，下一 tick 重新选最近的敌人，导致目标在 24.7 m 与 48 m 之间跳、点射节奏被打断、录制轨迹重新接管移动。
2. **无目标锁**：`min(visible)` 每 tick 重选最近敌人，两个距离不同的敌人交替可见时准星左右/上下大幅抖动。
3. **蹲起反馈环**：`crouch=bool(stable and aligned)` 会把 `m["crouch"]` 翻到下一 tick，而 `eye = 0.95 if m["crouch"] else 1.62`；瞄点高度突变 → `aligned` 翻转 → 又站起来，形成 20 Hz 蹲起 + pitch 抽搐。

### 修复

`agent.py`：

- `COMBAT_MEMORY_TICKS = 18`（0.3 s）：`visible` 为空但记忆未过期时，`combat_wait()` 保持上一战斗视角、`move_forward=0`、`fire=False`，**不重置**战斗状态与点射节奏。
- `_pick_target()`：锁定 `combat_target_seat`；目标重新可见时保持锁定；短暂不可见时保留最后位置（`combat_last_target`），只有在旧目标丢失且新目标 <10 m 且距离不到旧目标一半时才换目标。
- `combat()` 只在 `target_visible` 为真时开火；瞄准使用锁定目标的最后位置。
- `combat()` 不再蹲起（`crouch=False`），去掉 eye/alignment 反馈环。
- 点射改动（0.7 s / 1 s）本身不能解决该问题：节奏此前每个可见性空档都被重置，且抽搐来自目标/蹲起/移动切换，不是射击间隔。

## 2. R18（round_index 17）：录制轨迹被卡住的队友堵死

公开帧（seat 4，`round_index 17`）：

| tick | 观察 |
| ---: | --- |
| 124503–124893 | 购买冻结，全员在 T 出生点 |
| 124923–131763（回合结束） | seat 4 位置始终 `(76.8, 81.3)`，但速度 3.7–5.5 m/s；期间 seat 3 距离 **0.7 m**、seat 0 距离 **1.1 m**，两人也长时间停在原地 |
| 整回合 | 没有位移；agent 一直朝录制路线起点/下一节点推，被两名队友堵住 |

根因：录制轨迹跟随只检查“离路线点远不远”，没有“有移动输入但位置不变”的进度检测；队友位置不在 observation 的 `teammates` 里（合同只给 seat/alive/cash/zone/装备），所以只能靠位移反馈判断被堵。

### 修复

- `REPLAY_BLOCK_TICKS = 20`（0.33 s）：录制轨迹动作 `move_forward > 0.2` 但 20 ticks 内位移 <0.3 m → 判定被堵。
- `avoid_replay_block()`：向侧面 `move_right = ±0.9` 保持 24 ticks（0.4 s），每次触发换方向；随后重新跟随轨迹。
- `REPLAY_AVOID_ATTEMPTS = 4`：连续 4 次仍无法脱离时 `replay_done = True`、`replay_abandoned = True`，改用 A* 移动；`ct_fallback` 条件改为 `(not replay_active or replay_abandoned)`，40 s 未下包时仍可走 CT 出生点兜底。

## 3. 测试

- `test_combat_bridges_visibility_flicker_and_keeps_target`：可见性空档 2 次决策内保持不动、不开火、目标不变；
- `test_locked_target_does_not_flap_to_a_far_enemy`：近目标短暂不可见时不切换到 50 m 目标、不开火；
- `test_replay_sidesteps_when_blocked_by_a_teammate`：20 ticks 无进度后输出侧移，进度恢复后重置计时；
- `test_replay_abandons_route_after_repeated_blocks`：4 次失败后放弃录制轨迹；
- `test_dust2_replay_stops_for_enemy_then_resumes_from_same_cursor` 更新为等待战斗记忆过期后恢复轨迹。

## 4. 待回填

- R19 同类场景：可见性闪烁期间不再出现速度 >0 / 蹲起 / 目标切换；点射间隔保持 0.7 s 或 1 s。
- R18 同类场景：被队友堵住时 0.5 s 内出现侧移并脱离出生点；不超过 40 s 仍未下包时启用兜底。
- 公开事件回填：每回合 `fire` 间隔与 `hit` 部位分布。
