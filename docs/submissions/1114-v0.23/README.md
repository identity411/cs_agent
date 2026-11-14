# 1114-v0.23

- **日期**：2026-11-14
- **比赛 ID**：`2a97f94f-816a-52b7-b4b8-5925db160245`
- **合同**：rsi-fps-5.5
- **状态**：main v19 / account2 v22 admission passed and activated; entry code hash 03f89d9cd787
- **快照**：advance_holds.py, agent.py, borgo_replay.py, dust2_b_replay.py, dust2_replay.py, dust2_user_ct_routes.py, dust2_user_t_routes.py, map_patches.py, mirage_replay.py, mirage_user_ct_routes.py, mirage_user_t_routes.py, molo_replay.py, nevaio_replay.py, nevaio_user_ct_routes.py, nevaio_user_t_routes.py, pro_retakes.py（见同目录文件）

## 改动说明

### 轨迹链接器 review 修订

本版本只改 `agent.py` 的链接/接路行为，不新增或修改路线数据；Nevaio、Mirage、Dust2 路线与上一版一致。

- **总接路预算**：新增 `LINK_TOTAL_TIMEOUT_TICKS = 720`（约 12 s），跨所有候选入口累计，重试不重置；单候选仍保留 8 s 超时。战斗暂停只暂停计时，不清零已用预算。
- **入口高度门控**：新增 `LINK_ENTRY_HEIGHT_TOLERANCE = 1.0 m`；`link_to_route()` 与攻击/回防入口判断同时要求 XY 半径内和高度差达标，避免把另一层楼误当成入口，同时允许小坡差。
- **`first` 不再静默跳过起点**：攻击入口起点不可达时放弃该录制路线并回退 A*，不再降级为最近可达帧；`window` 候选改为按路线长度取前 10%（至少 1 帧），替代固定 48 帧。
- **入口排序计入学习代价**：`_rank_entries()` 的 A* 路径代价加入失败边惩罚与反向边惩罚，与运行时的边反馈一致。
- **回防跟随修正**：已进入回防轨迹后不再返回旧入口；到轨迹末帧转 A* 炸弹时保留已有寻路进度；已进入后的跟随时长不受 8 s 接路超时限制。
- **测试**：`tests/test_route_linker.py` 新增 14 项回归，覆盖总预算、候选重试、战斗暂停、跨层入口、窗口比例、边代价排序、回防末帧交接等；全量 233 通过、6 skipped，`git diff --check` 通过。
- **边界**：准入/激活成功不等于完整对局或胜利；高度容差、总预算与边代价排序仍需正式对局回填。

## 对应规范

- [11-14-route-linker.md](../../spec/11-14-route-linker.md) — 轨迹段与通用链接器的总预算、入口高度门控、候选排序与回防交接。
- [11-14-active-recorded-routes.md](../../spec/11-14-active-recorded-routes.md) — 当前启用录制轨迹清单。
- [11-14-replay-follow-wedge.md](../../spec/11-14-replay-follow-wedge.md) — T 进攻入口与偏离重接背景。

## 上传回执

- main：bundle `35ed5f22-752f-481f-a42e-b697d9535b00`，admission `passed`，version `19` 激活（entry `f81706cb-1aa5-54e6-9e4b-e1199ca25820`）。
- account2：bundle `b5927af7-5099-428a-8191-91082b736540`，admission `passed`，version `22` 激活（entry `a23486ad-a765-51b7-b2a9-b090b2d2e48f`）。
- 两个 entry 的 `code_hash_short` 均为 `03f89d9cd787`，与 ZIP SHA-256 `03f89d9cd787ae89243c93d4b8cc75e465c88664bd59fe21e3bbe72e3dcaf7f9` 前缀一致。

## 验证情况

- 本地 `python3 -m unittest discover -s tests -q`：233 通过、6 skipped；`git diff --check` 通过。
- 相对 v0.22 只有 `agent.py` 变化（`7eec28c0…`），其余 15 个提交文件哈希不变。
- 上传、准入与激活成功不等于完整对局、比分或胜利；高度容差、12 s 总预算与边代价排序的实战效果待回填。
