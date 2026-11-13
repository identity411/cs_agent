# 规范：守包 hold（不转圈）+ 带包人 40 s 兜底豁免

Status: **`advance_holds.PlantHold/PlantSpot/PlantLook` + Mirage A/B 数据随 `1113-v0.08` 提交，`main` v5 / `account2` v7 admission `passed` 并激活；75/75 测试通过；坐标待下一场正式对局验证**
Date: 2026-11-13
Related specs: [11-12-advance-holds.md](./11-12-advance-holds.md)（BRAKE / hold 参数）· [11-12-pathing-routes.md](./11-12-pathing-routes.md)（临时 T 40 s → CT spawn 兜底）· [11-12-site-center-hold.md](./11-12-site-center-hold.md)（CT patrol hold）· [11-12-match-observability.md](./11-12-match-observability.md)（守包/参战验收）· [maps.md](./maps.md)

## 0. 问题

1. T 方下包后，`agent.py` 在 `planted and side == "attack"` 且接近 goal 时直接返回 `yaw_rate=0.15`，导致原地无限转圈。Mirage `bot_waypoints` 为空，`watch_point()` 返回 `None`，goal 就是炸弹位置，转圈尤其明显。
2. T 方 40 s 未下包的临时兜底 `ct_fallback` 没有排除带包人，优先级还高于 `carrying_bomb → plant_point`：带包人 40 s 后会放弃下包去 CT 出生点。

## 1. 目标

- **任何守点都不连续转圈**：站到掩体 spot，按离散 look 角度逐个观察可能出人的入口；dwell 到期再切换。
- 炸弹已下（T 方）：
  - **Mirage A**：在箱子旁边守，依次看警家（CT spawn）、jungle、拱门（arch）。
  - **Mirage B**：在沙发等，然后小 loop 到 B 小掩体，来回看超市和 B 小。
  - 其他地图：用 `bot_waypoints` 的 T watch/hold 点或炸弹位置作为 spot，look 在 CT retake 方向与炸弹之间离散切换；没有 authored 数据也不转圈。
- **带包人优先下包**：`ct_fallback` 对 `carrying_bomb` 不成立；带包人目标始终是 `plant_point(site)`，在 plant zone 内且安全时立即 `use="plant"`；下包后进入上述守包 hold。

## 2. 数据模型（`advance_holds.py`）

```python
PlantLook(aim, aim_z=None, dwell_ticks=180)   # aim_z 是绝对瞄准高度
PlantSpot(stop, looks)                        # 掩体点 + 该点的观察序列
PlantHold(name, site, spots)                  # 多个 spot 组成小 loop
AdvanceMap(..., plant_holds={"A": PlantHold(...)})  # plant_hold(site)
```

- 与 `AdvancePoint` / `AdvanceAnchor` 不同，`PlantLook.aim[2]` **已经是绝对瞄准高度（地面 + 1.64 m 头部）**，运行时不再加 `HEAD_HEIGHT`。
- `dwell_ticks` 使用 match tick（约 64/s）；默认 180 tick ≈ 2.8 s。
- agent 只存 index（`post_plant_spot` / `post_plant_look`），不修改数据对象。

## 3. Mirage 守包数据

坐标来自 account2 `125a716a-27d2-4d5e-a3b1-a967892842c3` 的实际下包/下包后站位，以及公开 nav 节点；属于近似值，下一场验证碰撞/LOS。

### A 点：箱子旁边

| 项 | 值 | 来源 |
| --- | --- | --- |
| spot | `(48.6, 89.8, 15.43)` | R2/R8/R10/R11 下包点 `(48.8,90.5)/(49.6,91.7)` 附近；nav 节点 1846 |
| look 1 | CT spawn `(51.4, 52.9, 14.7)` | 警家 retake 方向；CT spawn 实际站位 `(51.4,52.9)` |
| look 2 | jungle `(62.3, 75.5, 17.5)` | nav 节点 1324 |
| look 3 | arch `(55.6, 79.5, 17.9)` | nav 节点 1651/1752 |

### B 点：沙发 + B 小小 loop

| 项 | 值 | 来源 |
| --- | --- | --- |
| spot 1（沙发） | `(109.4, 54.1, 15.7)` | R3 seat 3 下包后站位 `(109.4,54.1)`；距 B 下包点 `(108.1,50.7)` 约 3.6 m |
| look 1 | market `(98.0, 66.0, 17.5)` | 超市方向（nav window 附近） |
| look 2 | B short `(94.0, 51.0, 17.5)` | B 小/西侧入口 |
| spot 2（B 小掩体） | `(98.6, 50.5, 15.8)` | R3 seat 1 下包后站位 `(98.6,50.5)` |
| look | market `(98.0, 66.0, 17.5)` | 从 B 小回看超市 |

循环顺序：`沙发(market) → 沙发(B short) → B 小(market) → 沙发(market) …`。

## 4. 执行（`agent.py`）

- 每回合重置 `post_plant_*` 状态；authored 计划固定从用户指定的沙发/箱子 spot 起步（spot=0），初始 look 按 `seat % len(looks)` 分散；通用计划也从 spot 0 起。
- `post_plant_target()` 只在该 spot 上（`POST_PLANT_RADIUS=2.0`）且无可见敌人时推进 dwell；战斗会重置 dwell，战斗结束后继续看当前角度。
- 到 spot 后调用现有 `hold_aim()` 瞄准当前 look，**不再使用 `yaw_rate=0.15`**。
- 若 10 s（`POST_PLANT_TIMEOUT_TICKS=640`）仍未到达 authored spot，自动降级为“炸弹位置 + CT/炸弹离散 look”，避免新增长时间卡死。
- 无 authored hold 的地图：`patrol_points(site,"attack")` 中距炸弹 ≤12 m 的点作为 spot；没有就守炸弹位置；look 在 CT spawn 与炸弹之间切换。

## 5. 验收

- 单元测试：
  - `test_mirage_post_plant_a_watches_ct_jungle_arch`：look 0→1→2→0，全程不移动、yaw_rate ≠ 0.15；
  - `test_mirage_post_plant_b_loops_sofa_and_short`：沙发两个 look 后切到 B 小 spot，再切回；
  - `test_generic_post_plant_hold_does_not_spin`：无 authored 数据也不转圈；
  - `test_t_fallback_exempts_bomb_carrier` / `test_t_carrier_plants_after_40s_in_zone`：带包人 40 s 后去 plant point/直接下包，不再去 CT spawn。
- 真实 Mirage static 复核：A spot / B 沙发 / B small 均可从 T spawn 寻路到达（101 m / 142.6 m / 149.3 m）。
- 待下一场正式对局回填：
  - 转圈指标：守包阶段连续 `yaw_rate` 是否只在瞄准收敛期出现；
  - A 箱子 spot、B 沙发/B 小 spot 是否贴墙、被箱子挡 LOS；
  - 带包人 40 s 后是否 100% 选择下包而不是 CT spawn。
