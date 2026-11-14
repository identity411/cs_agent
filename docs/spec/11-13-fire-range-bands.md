# 规范：开火距离分层（近距扫射 / 中距只点头点射 / 远距只点头点射）

Status: **点射版已随 `1113-v0.10` 提交；0.6 s 统一节奏随 `1113-v0.16` 提交（`main` v12 / `account2` v15 admission `passed` 并激活）；本地 126/126 unittest 通过，待新对局验证**
Date: 2026-11-13
Submission: [1113-v0.10](../submissions/1113-v0.10/README.md) · [1113-v0.16](../submissions/1113-v0.16/README.md)
Related specs: [11-13-nevaio-r9-fire-discipline.md](./11-13-nevaio-r9-fire-discipline.md)（刹停门；本文取代其“90 m 仍扫射”的验收）· [11-12-advance-holds.md](./11-12-advance-holds.md)（§3.2 BRAKE / §6 TAP）· [11-12-match-observability.md](./11-12-match-observability.md)（开火 / 命中回填）

## 1. 需求

badcase：看到人直接扫射，不管远近；远距单发点射 DPS 太低，对枪打不过别人。2026-11-13 曾把中远距改为三连发，实验后回退。用户要求：

1. **站得足够近才扫射**，否则点射；
2. 扫射距离以 **Mirage A 点中央 → 警家（CT 出生点）** 为界；
3. 中距离点射 **只点头**，每 **0.6 s** 点一次；
4. 超过近距的 **1.5 倍** 仍然开火，同样只点头，节奏同样是 **0.6 s 一发**。

## 2. 距离定义

| 量 | 值 |
| --- | --- |
| Mirage A 点中央 | `(44.67, 88.18, 15.43)`（`walklab/src/map-fixtures/mirage_static.json` 的 `sites[A].center`） |
| 警家（CT 出生点） | 8 个 defend 出生垫均值 `(51.80, 56.41, 13.16)`；单垫距离 28.4–38.0 m |
| **近距扫射门 `SPRAY_RANGE`** | **32.5 m**（实测水平距离 32.56 m） |
| **快速点射边界 `TAP_RANGE`** | **48.75 m**（`1.5 × SPRAY_RANGE`） |
| **点射间隔 `TAP_INTERVAL_TICKS`** | **36 ticks**（60 Hz × 0.6 s；决策 20 Hz，即每 12 次决策一发） |

中距与远距共用同一个 0.6 s 间隔。

## 3. 开火分层

`fire_mode(distance_xy, parts)` 只看水平距离与当前合法视线采样：

| 距离 | 模式 | 瞄准点 | 扳机 |
| --- | --- | --- | --- |
| `≤ 32.5 m` 且 `chest/abdomen` 可见 | `spray` | `chest`（否则 `head` / `abdomen`） | 步枪连续；手枪仍按现有 trigger 节奏 |
| `≤ 32.5 m` 但只有 `head` 可见 | `tap` | `head` | 仅 `head` 可见时开火，每 36 ticks 一发 |
| `32.5 < d ≤ 48.75 m` | `tap` | `head` | 仅 `head` 可见时开火，每 36 ticks 一发 |
| `> 48.75 m` | `tap_long` | `head` | 仅 `head` 可见时开火，每 36 ticks 一发 |

共同前提（沿用 [11-13-nevaio-r9-fire-discipline.md](./11-13-nevaio-r9-fire-discipline.md)）：

- BRAKE：`grounded` 且水平速度 `≤ STOP_SPEED (1.0 m/s)` 才允许开火；
- 看到敌人立即停止 `move_forward` / `move_right`；
- 对准容差：`tap` / `tap_long` 用 `TAP_ALIGN = 0.02 rad`（约 1.1°），`spray` 用 `SPRAY_ALIGN = 0.04 rad`（约 2.3°）；
- `combat_move()` 的移动阶段仍然 `fire=False`。

“只点头”落地为：`tap` / `tap_long` 模式即使 `chest` 可见，只要 `head` 不在 `parts` 里就不扣扳机；远距离只跟头，不再扫射身体。

## 4. 实现

`agent.py`：

- 常量：`SPRAY_RANGE = 32.5`、`TAP_RANGE = 1.5 * SPRAY_RANGE`、`TAP_INTERVAL_TICKS = 36`、`TAP_ALIGN = 0.02`；移除三连发实验的 `BURST_RANGE` / `BURST_SHOTS` / `BURST_SHOT_TICKS` / `BURST_INTERVAL_TICKS` / `BURST_ALIGN` / `RECOIL_COMPENSATION`。
- `fire_mode()` 返回 `spray` / `tap` / `tap_long`。
- `combat()`：按模式选瞄准部位与对准容差；两种点射模式都要求 `head_visible`，共用 36 tick cadence；`combat_hold` 对两种点射置真。
- 同时移除 `recoil_offset()`、`weapon_ready()`、`_note_shot()` 与 `combat_burst_shots` 状态。

## 5. 验收

单元测试（`tests/test_movement.py`，全部通过）：

- `test_fire_bands_follow_mirage_a_to_ct_spawn`：32.5 / 48.75 m 边界，`tap` / `tap_long` 与 head-only 近距 → `tap`；
- `test_mid_range_taps_head_on_a_0_6_second_cadence`：40 m 头部目标，射击 tick 为 `0, 36, 72, 108`（0.6 s 间隔），全程不移动；
- `test_body_only_target_never_fires_outside_spray_band`：40 m / 50 m 只有 `chest` → 不开火（只点头）；
- `test_long_range_taps_head_on_the_same_0_6_second_cadence`：50 m 头部目标，同样每 36 ticks 一发；
- `test_pistol_taps_head_on_the_same_0_6_second_cadence`：无主武器时 40 m 头部目标每 36 ticks 单发；
- `test_close_body_sprays_inside_the_band`：10 m 身体可见 → 扫射开火；
- 原有刹停 / 空中禁火测试保持通过。

待下一场正式对局回填：

- 中远距离开火事件只命中头部（公开事件 `hit` 部位）；
- 0.6 s 点射的实际间隔；
- 近距扫射占比与整体命中率变化；
- nevaio R9 的 90.6 m 场景不再出现扫射，改为 0.6 s 一发的头部点射。
