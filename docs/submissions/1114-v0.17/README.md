# 1114-v0.17

- **日期**：2026-11-13
- **比赛 ID**：`2a97f94f-816a-52b7-b4b8-5925db160245`
- **合同**：rsi-fps-5.5
- **状态**：main submitted; admission passed; version 13 activated · account2 submitted; admission passed; version 16 activated
- **快照**：advance_holds.py, agent.py, borgo_replay.py, dust2_b_replay.py, dust2_replay.py, map_patches.py, mirage_replay.py, molo_replay.py, nevaio_replay.py, pro_retakes.py（见同目录文件）

## 改动说明

修复 v0.16 首拍 tick 0 fault，见 [11-14-first-tick-fault.md](../../spec/11-14-first-tick-fault.md)：

- 首拍收到 `map` 时只执行 `begin_map_load()`：保存 `map_id` / `sites` / `waypoints` / `plant_zones` / `map_patch` / `advance` 与 nav 引用，重置每图状态；**不构建 nav 图、不 import 轨迹模块**。
- 后续 buy 回调按 `MAP_BUILD_CHUNK=512` 项分块构建 nodes / edges；Mirage 2544 节点 + 6381 边约 18 个决策拍完成，远早于 live。
- 全部构建完成后再执行 `_apply_map_hazards()` 并置 `map_ready=True`；`_sync_route_memory()` 只在 `map_ready` 后调用。
- `route()` 入口在 `map_ready=False` 时先补完剩余构建，禁止在部分 nav 图上做 A*；首个 observation 就是 live 时一次性构建。
- `init()` 增加 `gc.disable()`，与官方模板一致。
- 默认 `USE_REVERSE_SOURCE_EDGES=False` 时跳过 `original` set 的全量遍历。

本地 `python3 -m unittest discover -s tests` **130/130** 通过；新增 `tests/test_first_callback.py` 覆盖首拍不建图、分块上限、live 首拍立即完成、`route()` 兜底。正式对局效果待下一场回填。

## 对应规范

- [11-14-first-tick-fault.md](../../spec/11-14-first-tick-fault.md) — 首拍分块加载 nav，避免 tick 0 fault。
- [11-12-pathing-routes.md](../../spec/11-12-pathing-routes.md) — 地图加载与 A* 寻路。
- [11-13-t-route-rotation.md](../../spec/11-13-t-route-rotation.md) — 路线权重同步后置到 `map_ready` 之后。

## 验证情况

见 `metadata.json` 的 `status` 与 `api_result`；不要仅凭上传或准入成功声称完整对局通过。
