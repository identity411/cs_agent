# Badcase：Mirage VIP 狗洞（需蹲下的低通道）与卡住跳冲突

Status: **已定位并修复；随 `1113-v0.07` 提交到 account2 version 6 并激活；account2 `dc5d2841` 公开帧取证；待正式对局验证**
Date: 2026-11-13
Related specs: [11-12-mirage-spawn-jump.md](./11-12-mirage-spawn-jump.md) · [11-12-pathing-routes.md](./11-12-pathing-routes.md) · [11-12-advance-holds.md](./11-12-advance-holds.md) · [maps.md](./maps.md)

## 1. 结论

Mirage 通往 VIP 的通道在平台坐标约 `(75.3, 66.2)`，是一条**必须蹲下通过的“狗洞”**。v0.04 的卡住/跳跃恢复只会在原地向前跳，无法越过低矮的顶板：

- 玩家在 `(75.3, 66.56, 15.73)` 朝向约 `yaw=1.7`（南）持续低速（0.07–0.1 m/s）；
- 反复 `jump`，z 在 `15.7 ↔ 17.2` 之间上下，x/y 几乎不变；
- 全程 `crouch=False`；`stand_blocked` 没有暴露低顶信息，因此 agent 误以为是普通台阶/滑动卡住。

T 方 40 s 兜底路线（A → CT spawn）和 CT 方 CT spawn → A 的 A* 最短路线都会经过这里，所以同一处会同时影响 T 和 CT。

## 2. 证据

对局 `dc5d2841-b5f6-4272-b420-af05806a33dd`（Mirage，account2 seat 7，v0.04）。

R12 / R14 / R15 中 seat 7 进入 `(75.3, 66.6)` 后：

| tick（R14） | 位置 | yaw | speed | jump | z |
| --- | --- | --- | --- | --- | --- |
| 109558 | (75.43, 66.65) | 1.05 | 5.70 | false | 15.73 |
| 109568 | (75.93, 66.56) | 0.81 | 0.01 | false | 15.73 |
| 109608 | (75.93, 66.57) | 0.83 | 0.00 | **true** | 16.09 |
| 109623 | (75.93, 66.57) | 0.84 | 0.00 | false | 17.12 |
| 110xxx | (76.3, 66.6) | ~1.7 | ~0.0 | 反复 | 15.8–17.2 |

- R12 在 `(75.3, 66.56)` 处连续跳约 9 次，之后仍卡在附近；
- R14 在 `(76.3, 66.6)` 处一直跳到回合结束；
- R15 同样在该通道内反复起跳，直到回合结束；
- 方向始终朝南（yaw≈1.5–1.7），说明路线方向正确，问题是**低顶禁止站立/跳跃通过**。

## 3. 修复

### 3.1 数据：`map_patches.CrouchGate`

```python
CrouchGate("vip_dog_hole", (75.3, 66.2, 15.83), (0.0, -1.0), 2.4)
```

- `center`：通道中心；`axis`：通道法线（此处为南北向）；
- 只有当前 goal 在通道另一侧、且玩家在 `radius` 内时才触发；
- 数据仍放在 `map_patches.py`，`agent.py` 不写地图坐标分支。

### 3.2 控制：`agent.Player.traverse_gate()`

- 触发后**清空当前路径**，朝通道另一侧对齐；
- `crouch=True`、`walk=True`、`move_forward>0`、`move_right=0`；
- **完全不发 `jump`**，并跳过该处的普通卡住/跳跃恢复；
- 穿过通道（越过中心 ≥1 m）后清空路径，从另一侧重新 A*；
- 200 个动作仍未穿过则本回合禁用该 gate，避免无限跳。

### 3.3 回归测试

- `test_mirage_doghole_is_crossed_crouched_without_jump`：通道内必须 `crouch=True` 且不发 `jump`；穿过后恢复普通移动。
- 现有 `test_step_up_waypoint_triggers_forward_jump` 仍通过：真正的台阶跳逻辑不受影响。

## 4. 验证

- 全量 unittest 通过（见 `tests/test_movement.py`）。
- nav 模拟（无碰撞）：
  - Mirage CT spawn → A：`holding`，路线先经过 VIP 狗洞，`crouch=True` 穿过；
  - Mirage T spawn → A/B：25.6 s / 32.9 s reached；
  - dust2 / nevaio / borgo 的 CT A 与 T 路线无回归。
- 未验证：真实碰撞世界下蹲速、顶板高度与 gate 半径是否完全匹配；需下一场正式对局回填。

## 5. 验收

- [ ] Mirage CT/T 经过 `(75.3, 66.2)` 时出现 `crouch=True` 且整段无 `jump`。
- [ ] 通过后能继续到 A/CT spawn，不再在通道内整回合起跳。
- [ ] 其他地图的台阶跳 / 卡住恢复不退化。
