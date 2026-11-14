# Badcase + 规范：T 进攻录制路线入口/跟随卡死与通用 action layer

Status: **已定位并由 P0–P4 修复于本轮工作区；本地 `187/187` 测试通过（6 skipped），正式提交/对局待回填。** P0–P4 指：倒退意图卡死检测、T 进攻入口接入 `link_to_route(first)`、跟随偏离重接 + cursor 进度看门狗、无进展路线降权、`LinkState` 通用化与日志统一。
Date: 2026-11-14
Submission: 待提交
Related specs: [11-14-route-linker.md](./11-14-route-linker.md)（通用 A* 链接器；本文把它从 CT 回防扩展到 T 进攻入口与跟随阶段）· [11-13-t-route-rotation.md](./11-13-t-route-rotation.md)（路线权重轮换；本文新增“无进展”失败）· [11-12-pathing-routes.md](./11-12-pathing-routes.md)（A* / 卡住恢复）· [11-12-stuck-at-spawn.md](./11-12-stuck-at-spawn.md)（A* 出生点卡住）· [11-12-mirage-spawn-jump.md](./11-12-mirage-spawn-jump.md)（T 出生点西侧拐角；其修复只覆盖 `move()`）· [11-14-pro-demo-walklab-pipeline.md](./11-14-pro-demo-walklab-pipeline.md)（Mirage T demo 路线）· [agx-match-query skill](../../.claude/skills/agx-match-query/SKILL.md)（公开回放取证）

## 0. 文档目的

记录 2026-11-13 20:00 UTC 对局 `439a8cec-6655-4993-987a-f7afddaffe9f` 中 **seat 5 在多个回合原地冻结约 112 秒、0 发射、0 死亡**的 badcase，并把修复抽象成可复用的 action layer：

```text
战术层（Tactic）      动作层（Action / Segment）           轨迹层（Route）
选点 / 选路 / 轮换  →  link(A*) → follow → terminal  →   ATTACKS / PAIRS / RETAKES / POSTPLANT
```

本文只使用公开回放、公开事件和本地静态地图；不声称拥有平台的私有决策日志。

## 1. 结论

1. **不是普通贴墙滑动，也不是旧的 A* 出生点卡住**：seat 5 跟随的是 Mirage T demo 路线 `A_palace_R4_ay0k`；agent 在出生点用“最近帧”方式**中途切入路线**，从车道北侧约 1 m 处开始追 2.5 m 前瞻点，直接切进 T 出生点西侧拐角的碰撞体。
2. **直接原因已确认**：录制路线在该段是**倒退走 + 回头预瞄**（yaw 从 -2.956 翻到 0.125）。`follow_trajectory()` 忠实复刻 → `move_forward≈-0.99`。`avoid_replay_block()` 用 `move_forward <= 0.2` 判断“原地瞄准”，把倒退当成停顿，每拍重置看门狗，导致侧移与 A* 回退**永远不会触发**。
3. **轮换复读**：agent 活到回合结束但从未完成路线；`_finalize_route_round()` 只在“死亡+输回合”时降权，neutral 让 `route_last_failed=False`，下一回合继续粘住同一条 `A_palace`。
4. **修复方向（已实现）**：
   - P0：卡住检测改用总移动意图 `hypot(move_forward, move_right)`；
   - P1：T 进攻路线入口接入 `link_to_route()`，`entry_policy=first` + 入口半径 0.6 m（`ATTACK_ENTRY_RADIUS`），先 A* 到 `frames[0]`；
   - P2：跟随偏离车道 >0.8 m 时 A* 重接到当前帧（停止半径 0.4 m）；高意图下 cursor 2.5 s 不前进则放弃回放、回退 A*；
   - P3：放弃/无进展的路线计为失败，权重 ×0.5；
   - P4：链接器状态抽成 `LinkState`，攻击/回防共用，日志统一 `segment/route`。

## 2. 对局与证据

### 2.1 对局身份

| 项目 | 值 |
| --- | --- |
| match / job | `439a8cec-6655-4993-987a-f7afddaffe9f` |
| 地图 | `mirage-cs2-v54` |
| 时间 | 2026-11-13 20:00–20:17 UTC |
| 结果 | team 0 **13–1** team 1 |
| 版本 | version 14 = [`1114-v0.18`](../submissions/1114-v0.18/README.md)，entry code hash `1c9eb25a7f30` |
| 本仓库席位 | **seat 5 (0-based) = team 1 = 第 6 个玩家**（`himesena`，`is_mine`） |
| 回放 | `https://agx.cool/#/jobs/439a8cec-6655-4993-987a-f7afddaffe9f` |

### 2.2 现象：同一坐标整回合静止

公开帧（24 fps）中 seat 5 的位置、yaw、速度：

| viewer 回合 | round_index | 静止位置 | 开始静止 | 持续 | yaw | 开火 | 存活 |
| --- | --- | --- | --- | ---: | ---: | ---: | --- |
| 第 1 回合 | 0 | `(89.69, 133.15, 15.74)` | 回合开始后约 9 s | ~112 s | 0.125 | 0 | 是 |
| 第 2 回合 | 1 | 同一坐标 | 约 9 s | ~112 s | 0.125 | 0 | 是 |
| 第 4 回合 | 3 | 同一坐标 | 约 9 s | ~112 s | 0.125 | 0 | 是 |
| 第 3 回合 | 2 | A ramp `(61.2, 124)` 附近 | 约 18 s 后 | 至回合结束 | 1.93↔2.85 | 0 | 是 |

后三列证据来自 `frames --round N`：冻结期间 `speed≈0.00`、`vx/vy≈0`，手持满弹手枪（`pistol 20/60`），公开事件中该席位 0 `fire`、0 次被击杀。

### 2.3 路线与卡点几何

- 选中路线：`A_palace_R4_ay0k`（466 帧，16 Hz，`carrier_cutoff=459`）。
- 本地用 v0.18 正式快照逐帧重放，`replay_cursor` 停在 **37**；2.5 m 前瞻目标是第 **44** 帧：

```text
37 (89.566, 132.155, 15.835, yaw -2.956)
40 (88.465, 132.482, 15.835, yaw -3.730)
43 (87.493, 132.981, 15.734, yaw  0.125)   <-- 录制玩家回头预瞄
44 (87.142, 133.027, 15.734, yaw  0.125)   <-- 前瞻目标
```

- agent 实际位置 `(89.686, 133.152)`：
  - 距第 37 帧 **1.00 m**（北偏）；
  - 在 x≈88.5 处，前瞻直线 y≈133.09，而录制车道 y≈132.48，**北偏约 0.6 m**；
  - 直行方向被 T 出生点西侧拐角碰撞体挡住，速度归零。
- 逐拍动作（本地重放）：`move_forward≈-0.99`、`move_right≈-0.14`、`yaw_rate≈0`，与公开帧 yaw 0.125 完全一致。

### 2.4 为什么出生点入口会切角

`follow_trajectory()`（`agent.py:227`）从 `cursor` 开始，在 80 帧窗口内取**最近的帧**（`agent.py:231-237`），然后沿polyline累加 2.5 m 取前瞻点（`agent.py:254-258`）。

- R1 出生于 pad 6 `(96.71,135.58)`，A_palace 第 0 帧在 `(97.08,130.89)`，相距 4.71 m；
- 但 0–80 帧窗口内更近的帧在 `(94.5–92.3, 131.6–132.2)`，于是 agent 从离车道 1–2 m 的北侧直接加入；
- 录制车道的门口在 y≈132.2–132.5，agent 的追点直线在 y≈133.1，切进北侧拐角。

### 2.5 为什么轮换没有换路

本地连续重放（同一 `Player` 跨回合）日志：

```text
route map=mirage-cs2-v54 seat=5 round=0 exec=A_palace_R4_ay0k result=neutral weight=1.00
route map=mirage-cs2-v54 seat=5 round=1 exec=A_palace_R4_ay0k result=neutral weight=1.00
```

`_finalize_route_round()`（`agent.py:766-792`）只有在 `route_death_pending` 且本队输掉回合时才降权；本 case 不死亡 → neutral → 权重保持 1.0、`route_last_failed=False`。`_select_recorded_route()`（`agent.py:708`）因此继续粘住 `route_last`。

## 3. 根因（代码定位）

| # | 位置 | 问题 |
| --- | --- | --- |
| 1 | `agent.py:227-258` `follow_trajectory()` | 出生点用最近帧中途加入；2.5 m 前瞻是直线弦，不检查与车道 polyline 的偏离，凹角处切墙。 |
| 2 | `agent.py:1906-1950` `avoid_replay_block()` | `agent.py:1928` 用 `move_forward <= 0.2` 判定“录制原地瞄准”。倒退（-0.99）被误判为停顿，anchor 每拍重置，`replay_avoid_attempts` 永远到不了 4。 |
| 3 | `agent.py:2574` | 仅当距当前帧 > **6 m** 才 A* 重接；本次只偏 1 m，重接不触发。 |
| 4 | `agent.py:766-792` `_finalize_route_round()` | 只把“死亡+输回合”计为失败；活着卡死 → neutral → 永久复读。 |

补充：`11-12-mirage-spawn-jump.md` 的“净进度 + 前进跳”修复只在 `move()`（A* 模式）里；录制回放跟随完全不经过该恢复逻辑。

## 4. 复现方式

```sh
python3 .claude/skills/agx-match-query/scripts/agx_matches.py report \
  --match-id 439a8cec-6655-4993-987a-f7afddaffe9f

python3 .claude/skills/agx-match-query/scripts/agx_matches.py frames \
  --match-id 439a8cec-6655-4993-987a-f7afddaffe9f --seat 5 --round 0 --every 5
```

本地重放（v0.18 快照 + 公开帧）：

- 第 0/1 回合均复现 `A_palace_R4_ay0k`、cursor 37、`move_forward≈-0.99` 持续到回合结束；
- 第 2 回合从 pad 1 进入，能过门口，但在 A ramp `(61.2,124)` 来回震荡（z 15.73↔15.94，速度 0.2↔6.1）；
- 把 `avoid_replay_block()` 的意图判定改为总向量后，约 10 s 内 attempt 升到 5，`replay_done/replay_abandoned=True`，回退 A*。

## 5. 设计：战术层 / 动作层 / 轨迹层

### 5.1 Route（轨迹层，已存在）

沿用 [11-14-route-linker.md](./11-14-route-linker.md) §1.1：`frames` + `site` + `carrier_cutoff` + `terminal_hold`。Mirage T 继续使用 `mirage_user_t_routes.ATTACKS`；本次不改录制数据。

### 5.2 Action / Segment（动作层）

新增 `LinkState`（`agent.py`）：

```text
link.segment        "attack" | "retake" | "opening" | "postplant"
link.route_name     路线名
link.frames         当前段帧
link.entry_frame    选定入口帧下标
link.candidates     [(A* 代价, 帧下标), ...]
link.choice         当前使用到第几个候选
link.started_tick   接路开始 tick
link.entered        是否已进入跟随
link.fail_logged    是否已记录最终失败
```

`retake_*` 旧字段保留为 `LinkState` 的 property 别名，兼容现有测试与日志；CT 回防行为不变。

### 5.3 入口策略

| 链路 | `entry_policy` | 入口半径 | 说明 |
| --- | --- | ---: | --- |
| T 进攻 ATTACKS | `first` | 0.6 m | 出生点/开局预瞄有战术含义；先 A* 到 `frames[0]` |
| CT 回防 RETAKES | `earliest` | 6.0 m | 允许按 A* 代价中途进入（已验收） |
| CT 开局 PAIRS.opening | `first` | 6.0 m | 编译期接点 ≤0.2 m；保持现状 |
| T 下包守包 POSTPLANT | `first` | 6.0 m | 已用 A* 接路 |

T 进攻入口的实测（当前工作区）：

```text
pad 6 (96.71,135.58) -> A* 路径 [(97.0,133.36) -> (96.56,130.11) -> (97.08,130.89)]
pad 5 (92.66,132.03) -> A* 路径 [(94.46,129.06) -> (96.56,130.11) -> (97.08,130.89)]
```

入口 A* 走出生点内部节点并落在 `frames[0]`，不再从北侧切入墙角。

### 5.4 跟随阶段：偏离重接

`follow_trajectory()` 之后检查到当前 cursor 帧的平面距离：

```text
distance(pos, frames[cursor]) > REPLAY_REJOIN_RADIUS (0.8 m)
  -> link_to_route(cursor, entry_radius=REPLAY_JOIN_RADIUS (0.4 m))
  -> 进入 0.4 m 后清空 A* 路径/目标，继续 follow
```

- 正常贴线时距离通常 <0.5 m，不触发；
- 本次卡点距第 37 帧 1.00 m，会触发 A* 到 `(89.57,132.16)`，绕开北侧拐角；
- 旧的 6 m 阈值仅保留为 `maybe_rejoin_replay()` 的“放弃后接回”条件。

### 5.5 跟随阶段：cursor 进度看门狗

```text
intent = hypot(move_forward, move_right)
intent <= 0.2            -> 录制停顿：不累计，重置窗口
cursor 前进 >= 4 帧       -> 刷新窗口
高意图持续 150 ticks(2.5s) 且 cursor 未前进 >=4 帧
                          -> 放弃回放，回退 A*，标记 route_stalled
```

它独立于方向，覆盖“位置在动但 cursor 不前进”的震荡（例如第 3 回合 A ramp）。

### 5.6 轮换：无进展计为失败

`_finalize_route_round()` 新增：

```text
elif route_stalled:
    result = "stalled"
    weight = max(ROUTE_WEIGHT_MIN, weight * ROUTE_WEIGHT_FAILURE)  # 0.5
    route_last_failed = True
```

`route_stalled` 由 P0 的放弃、P2 的看门狗放弃设置；只在 `route_started and not route_reached` 时标记。成功到点/下包仍走 success 分支，不受影响。

### 5.7 统一日志

```text
link map=mirage-cs2-v54 seat=5 round=0 segment=attack route=A_palace_R4_ay0k
     mode=astar result=entered entry=0/466 join_dist=4.71
```

保留 `pair=/retake=` 字段给 CT 回防，新增 `segment=/route=`；攻击与回防共用同一链接器。

## 6. 改动清单

| 改动 | 位置 |
| --- | --- |
| `LinkState` + `retake_*` 兼容属性 | `agent.py` |
| `avoid_replay_block()` 总意图判定 | `agent.py` |
| `choose_route_entry(policy=...)` / `_entry_pool()` | `agent.py` |
| T 进攻入口 `link_to_route(first, 0.6 m)` | `agent.py` `act()` replay 分支 |
| 偏离重接 / cursor 看门狗 / `route_stalled` | `agent.py` |
| 无进展降权 | `agent.py` `_finalize_route_round()` |
| 回归测试 | `tests/test_replay_wedge.py`、`tests/test_route_linker.py`（兼容） |
| 规范索引 | `docs/spec/README.md`、`11-14-route-linker.md` |

## 7. 验证

本地（2026-11-14）：

- [x] `python3 -m py_compile agent.py`
- [x] `python3 -m unittest discover -s tests`：**187/187 通过**（6 skipped）；新增 `tests/test_replay_wedge.py` 8 项
- [x] 倒退意图（`move_forward=-0.99, move_right=-0.14`）在 `REPLAY_BLOCK_TICKS` 后触发侧移
- [x] T 进攻出生点入口选择 `frames[0]`，`follow_attack_link()` 的 A* 目标为第 0 帧
- [x] 距第 37 帧 1.0 m 时触发 A* 重接：`goal=(89.57,132.15,15.84)`（正是第 37 帧），动作由倒退 `-0.99` 变为横向回接
- [x] 高意图 2.5 s cursor 不前进时放弃回放并标记 `route_stalled`
- [x] `route_stalled` 回合结束时权重 ×0.5、`route_last_failed=True`
- [x] 连续重放 R0→R1：R0 日志 `result=stalled weight=0.50`，R1 改选 `A_connector_R8_opdust`（不再复读 A_palace）
- [x] CT 回防/链接器既有测试不回归

注意：开环重放用的是公开帧中的旧位置，agent 的 A* 动作不会改变帧，因此会触发 `link_timeout`；这是验证回退链路的预期结果，不是正式对局行为。

## 8. 验收与待回填

- [ ] 正式对局中 T 进攻不再出现“存活 + 满弹主武器 + 整回合 0 发射 + 同一坐标静止 >20 s”
- [ ] 入口/重接日志出现 `segment=attack result=entered`，无 `blocked/timeout` 长尾
- [ ] 无进展路线在下一回合被替换，不再连续复读
- [ ] A ramp 类“位置震荡但 cursor 不前进”的形态被看门狗捕获

## 9. 证据记录

| 日期 | 来源 | 席位 | 观测 | 结论 |
| --- | --- | --- | --- | --- |
| 2026-11-14 | `439a8cec…` public frames | 5 | R1/R2/R4 `(89.69,133.15)`, yaw 0.125, speed 0, 0 发, 存活 | 录制回放整回合冻结 |
| 2026-11-14 | `439a8cec…` public frames | 5 | R3 `(61.2,124)` 震荡，z 15.73↔15.94 | cursor 不前进的震荡形态 |
| 2026-11-14 | v0.18 快照重放 | 5 | route=`A_palace_R4_ay0k`, cursor 37, 目标帧 44, `move_forward≈-0.99` | 倒退 + 前瞻切角确认 |
| 2026-11-14 | v0.18 快照重放 | 5 | `result=neutral weight=1.00` 连续回合 | 轮换未降权确认 |
| 2026-11-14 | 当前工作区 | — | first+0.6 m：A* 经出生点节点落到 `frames[0]` | 入口修复可行 |
| 2026-11-14 | 本地补丁实验 | — | 总意图判定后 attempt→5、`replay_abandoned=True` | P0 有效 |
| 2026-11-14 | 当前工作区 + 公开帧 | 5 | 卡点 `(89.69,133.15)` 改为 A* 目标 `(89.57,132.15)`，不再倒退顶墙 | P1/P2 有效 |
| 2026-11-14 | 当前工作区连续重放 | 5 | R0 `result=stalled weight=0.50`；R1 改选 `A_connector_R8_opdust` | P3 有效 |
| 2026-11-14 | `unittest discover` | — | 187/187 通过（6 skipped） | 无回归 |

## 10. 非目标与待确认

- 不去改写录制轨迹本身（例如把 A_palace 的倒退段改成正走）；本次只改入口/跟随/恢复/轮换。
- 不追求完全复刻职业 demo 的倒退预瞄；若后续发现倒退段在碰撞世界不可走，再考虑重录或把它标记为 `forward_only`。
- 入口 A* 依赖 nav 图；若某出生 pad 到 `frames[0]` 不可达，回退为候选帧 + `earliest`，并在日志记录 `unreachable`。
- 平台侧 `fault_code` 仍不可见；本文不涉及 tick 0 fault（见 [11-14-first-tick-fault.md](./11-14-first-tick-fault.md)）。
