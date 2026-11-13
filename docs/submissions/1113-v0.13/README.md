# 1113-v0.13

- **日期**：2026-11-13
- **比赛 ID**：`2a97f94f-816a-52b7-b4b8-5925db160245`
- **合同**：rsi-fps-5.5
- **状态**：main version 9 activated; account2 version 12 activated; admission passed
- **快照**：advance_holds.py, agent.py, borgo_replay.py, dust2_replay.py, map_patches.py, mirage_replay.py, molo_replay.py, nevaio_replay.py（见同目录文件）

## 改动说明

Borgo(A)、Molo(B)、Nevaio(A) 用户录制轨迹按地图 ID/哈希启用；带包者距目标包点 12 m 或到截止帧时退出轨迹，A* 进入下包区，下包后使用既有守包逻辑。三图录制分别 1113/1345/803 帧，源 SHA-256 记录在 replay 模块。三图切换测试 3/3 与移动回归 49/49 通过；正式对局效果待验证。

## 对应规范

[A* 寻路、地图进攻路线与移动/战斗控制](../../spec/11-12-pathing-routes.md)。

## 上传结果

- ZIP SHA-256：`6445465bb5ae5330dd896b885427a65cdcd0ae883564cc595b1e88b507957831`。
- main：bundle `ef2804b7-6043-4f46-860a-40eef6dbf33f`，version 9 已激活。
- account2：bundle `7ea9ed0c-c74e-4a63-899b-00360a89f69a`，version 12 已激活。
- 两个 bundle 的 admission 均为 `passed`，entry code hash 均为 `6445465bb5ae`。

## 验证情况

见 `metadata.json` 的 `status` 与 `api_result`；不要仅凭上传或准入成功声称完整对局通过。
