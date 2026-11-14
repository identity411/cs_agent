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
| `1113-v0.07` | 2026-11-13 | 已提交；admission passed；account2 v6（VIP 狗洞 crouch / 推进预瞄锚点 / Mirage CT A） | [README](1113-v0.07/README.md) |
| `1113-v0.08` | 2026-11-13 | 已提交；admission passed；main v5 / account2 v7（刹停点射 / 带包 40 s 豁免 / Mirage 守包 hold / nevaio 出生点 hazard） | [README](1113-v0.08/README.md) |
| `1113-v0.09` | 2026-11-13 | 已提交；admission passed；account2 v8（Mirage 录制轨迹跟随） | [README](1113-v0.09/README.md) |
| `1113-v0.10` | 2026-11-13 | 已提交；admission passed；main v6 / account2 v9（开火距离分层：近距扫射 / 中距只点头 0.7 s / 远距只点头 1 s） | [README](1113-v0.10/README.md) |
| `1113-v0.11` | 2026-11-13 | 已提交；admission passed；main v7 / account2 v10（战斗记忆 / 目标锁 / 不蹲起；录制路线被队友堵住侧移与放弃） | [README](1113-v0.11/README.md) |
| `1113-v0.12` | 2026-11-13 | 已提交；admission passed；main v8 / account2 v11（暂时放弃录制路线；A* 脱离卡点且仍靠近路线时自动接回） | [README](1113-v0.12/README.md) |
| `1113-v0.13` | 2026-11-13 | 已提交；admission passed；main v9 / account2 v12（Borgo、Molo、Nevaio 用户录制路线） | [README](1113-v0.13/README.md) |
| `1113-v0.14` | 2026-11-13 | 已提交；admission passed；main v10 / account2 v13（Dust2、Mirage CT 职业 demo 回防路线） | [README](1113-v0.14/README.md) |
| `1113-v0.15` | 2026-11-13 | 已提交；admission passed；main v11 / account2 v14（Mirage/Dust2 A/B CT 防守 peek loop） | [README](1113-v0.15/README.md) |
| `1113-v0.16` | 2026-11-13 | 已提交；admission passed；main v12 / account2 v15（T 方多路线权重轮换 + Dust2 B 路线 / 点射 0.6 s） | [README](1113-v0.16/README.md) |
| `1114-v0.17` | 2026-11-13 | 已提交；admission passed；main v13 / account2 v16（首拍分块加载 nav，修复 tick 0 fault） | [README](1114-v0.17/README.md) |
| `1114-v0.18` | 2026-11-13 | 已提交；admission passed；main v14 / account2 v17（后坐力 / 掉包恢复 / 购买预算 / Mirage CT 与 T 路线） | [README](1114-v0.18/README.md) |
| `1114-v0.19` | 2026-11-14 | 已提交；admission passed；main v15 / account2 v18（通用轨迹链接器 / CT 守点→回防 A* 接路 / B_3 禁用） | [README](1114-v0.19/README.md) |
| `1114-v0.20` | 2026-11-14 | 已提交；admission passed；main v16 / account2 v19（T 进攻入口 A* 接路 / 偏离重接 / cursor 看门狗 / 无进展降权） | [README](1114-v0.20/README.md) |
