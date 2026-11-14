# 1114-v0.20

- **日期**：2026-11-14
- **比赛 ID**：`2a97f94f-816a-52b7-b4b8-5925db160245`
- **合同**：rsi-fps-5.5
- **状态**：main v16 / account2 v19 activated; admission passed
- **快照**：advance_holds.py, agent.py, borgo_replay.py, dust2_b_replay.py, dust2_replay.py, map_patches.py, mirage_replay.py, mirage_user_ct_routes.py, mirage_user_t_routes.py, molo_replay.py, nevaio_replay.py, pro_retakes.py（见同目录文件）

## 改动说明

# 1114-v0.20

- **日期**：2026-11-14
- **比赛 ID**：`2a97f94f-816a-52b7-b4b8-5925db160245`
- **合同**：rsi-fps-5.5
- **状态**：main v16 / account2 v19 admission `passed` 并激活；entry code hash `741a35ac2c2d`

## 改动说明：T 进攻录制路线入口/跟随卡死修复（P0–P4，见 [11-14-replay-follow-wedge.md](../../spec/11-14-replay-follow-wedge.md)）

坏例：`439a8cec`（Mirage，v0.18）seat 5 在 R1/R2/R4 同一坐标 `(89.69,133.15)` 静止约 112 s、0 发射、0 死亡。agent 从出生点北侧中途切入 `A_palace` 录线，录制的倒退帧（`move_forward≈-0.99`）被旧看门狗当成瞄准停顿，且“活着无进展”轮换记为 neutral，连续复读同一条路线。

- **P0**：`avoid_replay_block()` 改用总移动意图 `hypot(move_forward, move_right) <= 0.2` 判定停顿；倒退/横移不再重置看门狗。
- **P1**：T 进攻入口接入 `link_to_route()`，`entry_policy=first` + `ATTACK_ENTRY_RADIUS=0.6 m`：每回合先 A* 到 `frames[0]`，不再就近切中段。
- **P2**：跟随偏离当前车道帧 >0.8 m 时 A* 重接该帧（0.4 m 停止）；高意图 2.5 s cursor 不前进则放弃回放、回退 A*；战斗期间暂停链接超时与 cursor 窗口。
- **P3**：`_finalize_route_round()` 新增 `stalled`：无进展路线权重 ×0.5、`route_last_failed=True`，下一回合换路。
- **P4**：新增 `LinkState`，攻击/回防共用链接器；`retake_*` 保留 property 别名；日志统一 `segment=/route=/pair=/retake=`。

## 验证

- `python3 -m py_compile agent.py` 通过。
- `python3 -m unittest discover -s tests`：**187/187 通过（6 skipped）**；新增 `tests/test_replay_wedge.py` 8 项。
- 公开帧回放：入口 A* 目标为第 0 帧 `(97.08,130.89)`；卡点改为回接第 37 帧 `(89.57,132.15)`；连续重放 R0 `result=stalled weight=0.50`，R1 改选 `A_connector_R8_opdust`。
- dust2 nav 模拟（含带包）仍 `reached`，无回归。

## 对应规范

- [11-14-replay-follow-wedge.md](../../spec/11-14-replay-follow-wedge.md) — badcase + action layer / LinkState / 入口策略 / 重接 / 看门狗 / 无进展降权。
- [11-14-route-linker.md](../../spec/11-14-route-linker.md) — 通用 A* 链接器。
- [11-13-t-route-rotation.md](../../spec/11-13-t-route-rotation.md) — 路线权重轮换；新增 stalled 失败。

## 上传回执

- main：bundle `561e796b-a83f-4258-a37d-d707045d90f3`，admission `passed`，version `16` 激活。
- account2：bundle `560bb670-2a56-410d-a1a4-1b86bbe12d23`，admission `passed`，version `19` 激活。
- ZIP SHA-256：`741a35ac2c2d2d7ead6d2c0459425a6b5a5459c0ba3cbca1f5f5e1ff2c2ebafc`。
- admission/激活不等于完整对局或胜负；实战效果待下一场回填。

## 对应规范

TODO: 在受影响的 `docs/spec/*.md` 中加入本版本引用，并在
`docs/spec/README.md` 的版本表登记本版本。

## 验证情况

见 `metadata.json` 的 `status` 与 `api_result`；不要仅凭上传或准入成功声称完整对局通过。
