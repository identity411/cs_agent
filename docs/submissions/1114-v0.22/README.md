# 1114-v0.22

- **日期**：2026-11-14
- **比赛 ID**：`2a97f94f-816a-52b7-b4b8-5925db160245`
- **合同**：rsi-fps-5.5
- **状态**：main v18 / account2 v21 admission passed and activated; entry code hash b2f874a6d0df
- **快照**：advance_holds.py, agent.py, borgo_replay.py, dust2_b_replay.py, dust2_replay.py, dust2_user_ct_routes.py, dust2_user_t_routes.py, map_patches.py, mirage_replay.py, mirage_user_ct_routes.py, mirage_user_t_routes.py, molo_replay.py, nevaio_replay.py, nevaio_user_ct_routes.py, nevaio_user_t_routes.py, pro_retakes.py（见同目录文件）

## 改动说明

### Nevaio 用户录制 T/CT 路线

新增 12 条用户 Walklab 录制（`walklab-v2`、20 Hz、`nevaio-r3-v54`、几何哈希 `78137c32…`），编译为：

- T 进攻 4 条：`A_mid` / `A_long` / `B_mid` / `B_long`，与旧 `legacy` A 路线共同参与包点过滤和失败权重轮换。
- CT 开局 4 组：`A_mid` / `A_long` / `B_mid` / `B_long`。源录制没有独立守点段，`hold` 为 opening 最后一帧，`holdMode = "final_pose"`：到点后原地保持录制位置与视角。
- CT 回防 4 条：`A_to_B_mid/long`、`B_to_A_mid/long`，两个方向都有候选。

数据与编译：

- `recordings/nevaio_t/`、`recordings/nevaio_ct/`：12 份源 JSON 与 manifest；源文件不进入提交 ZIP。
- `scripts/build_nevaio_routes.py`：校验格式、地图 ID/几何哈希、20 Hz、连续 tick、有限 pose、键位、位移和包点距离；输出 zlib + ascii85 内嵌帧并记录每条源 SHA-256。
- `nevaio_user_t_routes.py`、`nevaio_user_ct_routes.py`：生成模块。

运行时：

- `agent.py` 的 `user_t_routes()` / `user_ct_routes()` 按地图 ID + 静态哈希分发 Nevaio。
- `recorded_route_options()` 的用户路线追加改为通用逻辑，Dust2/Mirage 候选顺序不变。
- 旧 `nevaio_replay.py` 的 `SITE = "A"` 不再固定 T 计划；用户候选跨 A/B 时 `recorded_site()` 返回 `None`，A 回合 3 条候选、B 回合 2 条。
- CT 开局沿用现有 opening → hold → 下包回防状态机；回防复用 `choose_retake()`。

测试：

- 新增 `tests/test_nevaio_user_routes.py`（12 项）；全量 219 通过、6 skipped；`git diff --check` 通过。
- 编译产物与外部提供的 12 条编译结果逐帧一致；与源 JSON 抽样逐帧核对。
- 未实走验证：门洞、台阶、碰撞和末帧守点是否适合实战仍需对局回填。

### 同版本包含的本地修复

- `follow_trajectory()` 允许移动帧推进到同坐标的静止尾段，修复 Mirage CT opening 到 hold 边界被误判卡住的问题（见 [11-14-ct-idle-handoff.md](../../spec/11-14-ct-idle-handoff.md)）。
- 掉包恢复同时接受 `bomb.state` 的 `world` 与 `dropped`，仍要求 T、未携包和合法 position（见 [11-14-training-extra-findings.md](../../spec/11-14-training-extra-findings.md) §1）。
- 放弃后的攻击路线恢复统一进入 `_start_attack_rejoin()` / `follow_attack_link()`，不再绕过 8 s 接路超时（同上 §2）。
- Dust2 中门夹 B 路线 `B_mid_doors_20261114` 与 `B_car_hold` 首次随本版本进入快照（HEAD 已提交，v0.21 快照未包含）。

## 对应规范

- [11-14-nevaio-user-routes.md](../../spec/11-14-nevaio-user-routes.md) — 12 条源录制、manifest、编译校验、CT 末帧静止守点与运行时选择。
- [11-14-active-recorded-routes.md](../../spec/11-14-active-recorded-routes.md) — 当前启用录制轨迹清单。
- [11-13-t-route-rotation.md](../../spec/11-13-t-route-rotation.md) — Nevaio 五条 T 候选的权重轮换。

## 上传回执

- main：bundle `1e7913ee-54bd-4c36-a40f-5e724001142a`，admission `passed`，version `18` 激活（entry `f81706cb-1aa5-54e6-9e4b-e1199ca25820`）。
- account2：bundle `933bb846-154d-4793-9741-6cb538977305`，admission `passed`，version `21` 激活（entry `a23486ad-a765-51b7-b2a9-b090b2d2e48f`）。
- 两个 entry 的 `code_hash_short` 均为 `b2f874a6d0df`，与 ZIP SHA-256 `b2f874a6d0df03f5364a5bbc953a176219d4c6736ae22d965120da578685b2ed` 前缀一致。

## 验证情况

- 本地 `python3 -m unittest discover -s tests -q`：219 通过、6 skipped；`git diff --check` 通过。
- 编译帧与源 JSON 抽样逐帧一致；与外部提供的 12 条编译结果逐帧一致。
- 上传、准入与激活成功不等于完整对局、比分或胜利；实走碰撞、视线、末帧守点与实战效果待回填。
