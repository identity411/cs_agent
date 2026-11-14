# 1113-v0.16

- **日期**：2026-11-13
- **比赛 ID**：`2a97f94f-816a-52b7-b4b8-5925db160245`
- **合同**：rsi-fps-5.5
- **状态**：main submitted; admission passed; version 12 activated · account2 submitted; admission passed; version 15 activated
- **快照**：advance_holds.py, agent.py, borgo_replay.py, dust2_b_replay.py, dust2_replay.py, map_patches.py, mirage_replay.py, molo_replay.py, nevaio_replay.py, pro_retakes.py（见同目录文件）

## 改动说明

T 方多路线权重轮换（[11-13-t-route-rotation.md](../../spec/11-13-t-route-rotation.md)）：

- `recorded_route_options()` 支持同一地图多条命名路线；Dust2 现有 `legacy` 与 `B_site_20261113` 两条候选。
- 每席位独立记忆权重：本回合跟随的录制路线上死亡且本队输掉回合 → 权重 ×0.5（下限 0.1）；成功到点/下包 → 权重恢复并粘滞；CT 回合、下包后死亡不参与轮换。
- 新增 `dust2_b_replay.py`（706 帧，B 点，`CARRIER_CUTOFF=588`）。

开火节奏与回放细节（[11-13-fire-range-bands.md](../../spec/11-13-fire-range-bands.md)）：

- 点射节奏统一为每 0.6 s 一发（原 0.7 s / 1.0 s 两档）；近距扫射门槛不变。
- 录制回放帧新增 jump 位解析（mask 32），支持含跳跃的路线。
- Walklab 本地点位持久化与 CT 录制入口属于本地工具改动，不随 ZIP 提交。

本地 `python3 -m unittest discover -s tests` **126/126** 通过；新版本正式对局效果待下一场回填。

## 对应规范

- [11-13-t-route-rotation.md](../../spec/11-13-t-route-rotation.md) — T 方多路线权重轮换与 Dust2 B 点路线。
- [11-13-fire-range-bands.md](../../spec/11-13-fire-range-bands.md) — 点射节奏统一为 0.6 s 一发。
- [11-12-pathing-routes.md](../../spec/11-12-pathing-routes.md) — 录制轨迹跟随与 jump 位解析。

## 验证情况

见 `metadata.json` 的 `status` 与 `api_result`；不要仅凭上传或准入成功声称完整对局通过。
