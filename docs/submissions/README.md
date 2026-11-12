# 提交版本快照

每个版本一个目录，命名 `MMDD-vX.YY`：

- baseline：`1112-v0.00`
- 后续提交：`1112-v0.01`、`v0.02`……
- 目录内含该次可提交的完整文件树、`README.md`（改动说明）和 `metadata.json`（合同、状态、文件哈希、提交回执）。

旧版本不改；修正用新版本。新版本在 [`docs/spec/README.md`](../spec/README.md) 的版本表登记，并在受影响的 spec 中回链。

## 版本

| 版本 | 日期 | 状态 | 改动说明 |
| --- | --- | --- | --- |
| `1112-v0.00` | 2026-11-12 | baseline，未提交 | [README](1112-v0.00/README.md) |
| `1112-v0.01` | 2026-11-12 | 已提交；admission passed；version 1 | [README](1112-v0.01/README.md) |
| `1112-v0.02` | 2026-11-12 | 已提交；admission passed；version 2（出生点卡住修复） | [README](1112-v0.02/README.md) |
| `1112-v0.03` | 2026-11-12 | 已提交；admission passed；main v3 / account2 v2（A* / attackRoutes / patrol / 战斗控制） | [README](1112-v0.03/README.md) |
| `1112-v0.04` | 2026-11-12 | 已提交；admission passed；main v4 / account2 v3（前进跳 / 台阶跳 / map_patches / Mirage） | [README](1112-v0.04/README.md) |
| `1113-v0.05` | 2026-11-13 | 已提交；admission passed；account2 v4（Dust2 录制轨迹闭环跟随） | [README](1113-v0.05/README.md) |
| `1113-v0.06` | 2026-11-13 | 已提交；admission passed；account2 v5（原地准星帧逐拍回放） | [README](1113-v0.06/README.md) |
