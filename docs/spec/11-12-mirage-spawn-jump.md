# Badcase：Mirage T 出生点 / CT A 入口的“滑动卡住”与向前跳跃

Status: **已定位；前进跳 / 台阶跳、地图修补独立在 `map_patches.py`，已随 `1112-v0.04` 提交/激活；待下一场正式对局验证**
Date: 2026-11-12
Related specs: [11-12-pathing-routes.md](./11-12-pathing-routes.md) · [11-12-stuck-at-spawn.md](./11-12-stuck-at-spawn.md) · [11-12-match-observability.md](./11-12-match-observability.md)

## 1. 证据

对局：`d24bd037-4981-42e5-bd85-7db8d0ce2495`（Mirage，v0.03）。
- `main`：seat 3，team 0，13–9 胜；
- `account2`：seat 9，team 1，9–13 负。

公开帧里的 bomb 对象可以直接读到带包人：

```json
{"id":"r6:bomb","state":"held","carrier":2}
{"id":"r10:bomb","state":"held","carrier":1}
```

因此 **R6 带包的是 seat 2，R10 带包的是 seat 1；seat 3（main）两回合都没有带包**。R10 seat 3 从 T 出生点去了 B，并在 `(93.69, 51.71)` 被击杀；R10 的 A 下包是 seat 1 完成的。

## 2. R6：T 方整队没有走出出生点

R6：`round_start=45066`，`freeze_end=45426`，`live_end=52326`，team 0 进攻，最后 `timeout`（CT 胜）。公开事件在 R6 没有任何 `fire` / `hit` / `kill`，只有 CT seat 8 在 `48816` 的 fault。

公开帧位置（每 4 s 采样）：

| tick | seat 0 | seat 1 | seat 2（带包） | seat 3（main） | seat 4 |
| --- | --- | --- | --- | --- | --- |
| 45426 | (95.1,134.2) | (96.6,130.1) | (99.9,130.5) | (92.6,132.0) | (101.0,132.7) |
| 46626 | (115.8,119.7) | (96.0,133.8) | (93.7,132.4) | (89.6,134.1) | (90.7,131.6) |
| 47826 | (115.6,119.7) | (96.0,133.8) | (93.6,132.4) | (89.6,134.5) | (90.8,131.6) |
| 50226 | (115.6,119.7) | (96.0,133.8) | (92.6,132.4) | (89.7,132.4) | (90.9,131.6) |
| 52326 | (115.7,119.7) | (96.0,133.9) | (92.7,132.6) | (89.7,132.4) | (90.7,131.6) |

带包的 seat 2 从 `46434` 起在 `y≈132.41` 上做 `x=92.3 ↔ 93.6` 的左右滑动，一直持续到回合结束；全回合 `grounded=True`，`z≈15.79`，**没有出现跳跃**。

## 3. R10：同一个拐角，带包的 seat 1 跳出来了

R10：`round_start=74685`，`freeze_end=75045`，live 结束 `81945`。带包人 seat 1（出生 pad 4，`95.14,134.16`）的公开帧：

| tick | 位置 | 说明 |
| --- | --- | --- |
| 75189 | (92.55,132.65,15.80) | 进入同一拐角 |
| 75237–75573 | (92.14,132.50,15.79) | 停住约 10 s |
| 75333 / 75381 | 速度 4.64，随后 `grounded=False` | 起跳 |
| 75621 | (91.06,132.40,17.21)，`grounded=False` | 跳到约 1.4 m 高 |
| 75717 | (90.52,133.88,15.75) | 越过障碍/台阶 |
| 76101 | (89.44,130.87,15.83) | 从西侧出口离开 |
| 76485 | (72.34,126.70,13.30) | 进入 A ramp / palace 方向 |
| 79972 | `plant_start`，site A | seat 1 下包 |
| 82551 | `bomb_explode` | A 点爆炸，team 0 胜 |

结论：R6 和 R10 走的是同一个 T 出生点西侧拐角；区别不是“带包逻辑”，而是 **R10 的带包人跳了一下并向前走，R6 的带包人只左右滑动、从未起跳**。R6 的 seat 2 在滑动过程中每拍位置都在变，旧的 `stuck` 判定只检查“位置有没有变”，因此永远不累计；等到 waypoint 超时就直接换点，跳跃恢复没有机会触发。

## 4. CT → A：两个台阶/坎

R13（`freeze_end=98373`）main seat 3 是 CT，从 `(51.23,58.55,13.21)` 出发，v0.03 的 A* 路径先向 A ramp 走：

- 到 `(39.35,65.21,14.31)` 后沿台阶滑动到 `(42.8,66.4,14.31)`，速度 0.02–0.1；
- `101493` 附近起跳（`z=15.75`），落到 `(43.41,67.59,14.51)`；
- `102693` 再起跳（`z=15.96`），到 `(42.98,73.62,15.73)`；
- 之后路线折回 `(41.83,64.08)`，并沿东侧绕行，在 `(74.56,62.31,14.72)` 再次停住到回合结束。

第二个停点附近有 `(74.94,64.32,15.83)` 的 nav 节点：水平 2.0 m、垂直 **+1.11 m**，是一个典型的需要跳上去的台阶。旧代码只有在 `stuck > 20` 且 `stuck % 12 == 0` 时才跳，而且跳跃时是“后退 + 横移”；如果它在滑动，stuck 不累计，就永远不会向前跳。

## 5. 修复（当前工作区）

`agent.py` `move()`：

1. **净进度代替瞬时位移**：用 `wp_progress += last_d - d` 累计“向当前 waypoint 靠近了多少”，只有累计 ≥ `WAYPOINT_PROGRESS=0.4` 才清零；左右滑动不会再把 `wp_ticks` 一直重置。
2. **无进度前进跳**：`wp_ticks >= JUMP_AFTER_TICKS=12`（约 0.6 s）且朝向已对齐、grounded、冷却结束（`JUMP_COOLDOWN_TICKS=24` 个 match tick），设置 `jump=True`，并保持 `move_forward>0`（前进跳），每个 waypoint 最多 `JUMP_ATTEMPTS=3` 次；之后才跳过该 waypoint 并加边惩罚。
3. **台阶跳**：下一个 waypoint 比当前脚底高 ≥ `STEP_JUMP_HEIGHT=0.8`、水平距离 ≤ `STEP_JUMP_RADIUS=2.5` 时，直接 `jump=True` 并取消 walk（按向前速度移动）。CT 东侧 `(74.56,62.31) → (74.94,64.32)` 就会触发。
4. **stuck 恢复先向前跳**：`stuck > STUCK_AFTER` 时先尝试“朝 waypoint 前进跳”，跳不了才退回原来的后退 + 横移 + 跳。
5. **地图修补独立**：Mirage / dust2 的 hazard 坐标、台阶跳阈值都放进根目录 `map_patches.py` 的 `MapPatch`；`agent.py` 只调用 `map_patches.for_map(map_id)` 读取抽象结果，不再在 agent 核心里写地图分支或坐标。`build` 默认打包根目录 `*.py`，`map_patches.py` 会随 ZIP 一起提交。

没有把本次修复说成碰撞级证明：`static.json` 只带 collision 的路径/SHA，`mirage-positions.f32` / `mirage-materials.u8` / `mirage-walked-nav.json` 在公开 API 上都返回 404；本地只能做 nav 级模拟。已下载的 `data/maps/mirage/reconstruction.json`（2.7 MB，73,152 个三角形的分类和 1,717 个 source volume）是渲染/重建元数据，不是碰撞网格本体。

## 6. 验证与待验收

```sh
python3 -m py_compile agent.py
python3 -m unittest discover -s tests -v          # 53/53
python3 scripts/simulate_nav.py --map data/accounts/main/matches/d24bd037-4981-42e5-bd85-7db8d0ce2495/static.json --side attack --site A --round 6 --seat 2 --carrying
python3 scripts/simulate_nav.py --map data/accounts/main/matches/d24bd037-4981-42e5-bd85-7db8d0ce2495/static.json --side defend --site A --round 13 --seat 3 --start 51.23,58.55,13.21
```

当前结果：测试 53/53；nav 模拟 T→A 26.0 s、CT→A 22.4 s（都是 reached，无碰撞网格）。

新增回归：
- `test_step_up_waypoint_triggers_forward_jump`：下一个节点高 1.2 m 时必须向前跳；
- `test_sliding_stall_jumps_forward_instead_of_waiting`：位置左右滑动、净进度为 0 时也要触发前进跳；
- `test_stuck_recovery_tries_forward_jump_before_backoff`：stuck 恢复先前进跳，不是先后退；
- `test_map_patch_hazards_are_applied_by_map_id`：agent 通过 `map_patches.for_map()` 读取 hazard；未知地图得到中性默认值。

另外，当前工作区有一个**临时兜底**：T 方 `round_tick>=40 s` 仍未下包时直接去 CT 出生点，见 [11-12-pathing-routes.md](./11-12-pathing-routes.md) 5.1。它不是长期战术，nav 卡死率下降后应删除。

待新正式对局验证：
- [ ] Mirage T 出生点西侧（约 `(90,132)`）不再整回合卡住；带包人能离开出生点。
- [ ] Mirage CT→A 的两个台阶（约 `(42.8,66.4)`、`(74.6,62.3)`）能跳过去，或能及时 reroute。
- [ ] R6/R10 类回合的带包人能在 40 s 内进入 A/B 或明确转点，不再 120 s timeout。
- [ ] 临时兜底触发后 75 s 内能到 CT 出生点（nav 模拟从 Mirage T spawn pad3 约 40 s）。
