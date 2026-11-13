# 规范：开火距离分层（近距扫射 / 中距只点头点射 / 远距慢速只点头点射）

Status: **已随 `1113-v0.10` 提交；`main` v6 / `account2` v9 admission `passed` 并激活；本地 82/82 unittest 通过；待新对局验证**
Date: 2026-11-13
Submission: [1113-v0.10](../submissions/1113-v0.10/README.md)
Related specs: [11-13-nevaio-r9-fire-discipline.md](./11-13-nevaio-r9-fire-discipline.md)（刹停门；本文取代其“90 m 仍扫射”的验收）· [11-12-advance-holds.md](./11-12-advance-holds.md)（§3.2 BRAKE / §6 TAP）· [11-12-match-observability.md](./11-12-match-observability.md)（开火 / 命中回填）

## 1. 需求

badcase：看到人直接扫射，不管远近。用户要求：

1. **站得足够近才扫射**，否则点射；
2. 扫射距离以 **Mirage A 点中央 → 警家（CT 出生点）** 为界；
3. 中距离点射 **只点头**，每 **0.7 s** 点一次；
4. 超过近距的 **1.5 倍** 仍然开火，同样只点头，但频次降为 **1 s 一发**。

## 2. 距离定义

| 量 | 值 |
| --- | --- |
| Mirage A 点中央 | `(44.67, 88.18, 15.43)`（`walklab/src/map-fixtures/mirage_static.json` 的 `sites[A].center`） |
| 警家（CT 出生点） | 8 个 defend 出生垫均值 `(51.80, 56.41, 13.16)`；单垫距离 28.4–38.0 m |
| **近距扫射门 `SPRAY_RANGE`** | **32.5 m**（实测水平距离 32.56 m） |
| **快速点射边界 `TAP_RANGE`** | **48.75 m**（`1.5 × SPRAY_RANGE`） |
| **快速点射间隔 `TAP_INTERVAL_TICKS`** | **42 ticks**（60 Hz × 0.7 s；决策 20 Hz，即每 14 次决策一发） |
| **远距点射间隔 `LONG_TAP_INTERVAL_TICKS`** | **60 ticks**（60 Hz × 1.0 s） |

## 3. 开火分层

`fire_mode(distance_xy, parts)` 只看水平距离与当前合法视线采样：

| 距离 | 模式 | 瞄准点 | 扳机 |
| --- | --- | --- | --- |
| `≤ 32.5 m` 且 `chest/abdomen` 可见 | `spray` | `chest`（否则 `head` / `abdomen`） | 步枪连续；手枪仍按现有 trigger 节奏 |
| `≤ 32.5 m` 但只有 `head` 可见 | `tap` | `head` | 仅 `head` 可见时开火，每 42 ticks 一发 |
| `32.5 < d ≤ 48.75 m` | `tap` | `head` | 仅 `head` 可见时开火，每 42 ticks 一发 |
| `> 48.75 m` | `tap_long` | `head` | 仅 `head` 可见时开火，每 60 ticks 一发 |

共同前提（沿用 [11-13-nevaio-r9-fire-discipline.md](./11-13-nevaio-r9-fire-discipline.md)）：

- BRAKE：`grounded` 且水平速度 `≤ STOP_SPEED (1.0 m/s)` 才允许开火；
- 看到敌人立即停止 `move_forward` / `move_right`；
- 对准容差：`tap` / `tap_long` 用 `TAP_ALIGN = 0.02 rad`（约 1.1°），`spray` 用 `SPRAY_ALIGN = 0.04 rad`（约 2.3°）；
- `combat_move()` 的移动阶段仍然 `fire=False`。

“只点头”落地为：`tap` / `tap_long` 模式即使 `chest` 可见，只要 `head` 不在 `parts` 里就不扣扳机；远距离只跟头，不再扫射身体。

## 4. 实现

`agent.py`：

- 常量：`SPRAY_RANGE = 32.5`、`TAP_RANGE = 1.5 * SPRAY_RANGE`、`TAP_INTERVAL_TICKS = 42`、`LONG_TAP_INTERVAL_TICKS = 60`；移除旧的 `CLOSE_SPRAY_RANGE = 20.0` 与 15-tick 点射节奏。
- 新增模块函数 `fire_mode(distance_xy, parts)`，返回 `spray` / `tap` / `tap_long`。
- `combat()`：按模式选瞄准部位与对准容差；两种点射模式都要求 `head_visible`，分别使用 42 / 60 tick cadence；`combat_hold` 对两种点射置真。

## 5. 验收

单元测试（`tests/test_movement.py`，全部通过）：

- `test_fire_bands_follow_mirage_a_to_ct_spawn`：32.5 / 48.75 m 边界，`tap` / `tap_long` 与 head-only 近距 → `tap`；
- `test_mid_range_taps_head_on_a_0_7_second_cadence`：40 m 头部目标，点射间隔 ≥ 42 ticks；
- `test_body_only_target_never_fires_outside_spray_band`：40 m / 50 m 只有 `chest` → 不开火（只点头）；
- `test_beyond_1_5x_spray_range_taps_head_once_per_second`：50 m 头部目标，点射间隔 ≥ 60 ticks，全程不移动；
- `test_close_body_sprays_inside_the_band`：10 m 身体可见 → 扫射开火；
- 原有刹停 / 空中禁火测试保持通过。

待下一场正式对局回填：

- 中远距离开火事件只命中头部（公开事件 `hit` 部位）；
- 0.7 s / 1 s 两档点射的实际间隔；
- 近距扫射占比与整体命中率变化；
- nevaio R9 的 90.6 m 场景不再出现扫射，改为 1 s 一发的头部点射。
