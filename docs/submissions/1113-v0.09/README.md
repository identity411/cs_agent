# 1113-v0.09

- **日期**：2026-11-13
- **比赛 ID**：`2a97f94f-816a-52b7-b4b8-5925db160245`
- **合同**：rsi-fps-5.5
- **状态**：account2 submitted; admission passed; version 8 activated
- **快照**：advance_holds.py, agent.py, dust2_replay.py, map_patches.py, mirage_replay.py（见同目录文件）

## 改动说明

Mirage 用户录制的 1410 帧轨迹编译为 mirage_replay.py。仅当比赛地图 ID 和 geometry_hash 均匹配 Mirage 且处于进攻方、未下包时启用；沿用位置/视角反馈、遇敌停下射击及脱离后重返轨迹。Dust2 轨迹继续按原地图触发。Mirage T 出生点至 A 点本地导航仿真 66.7 秒到达；78 项 unittest 通过。录制来源 SHA-256: 4623aad2fa101c7f57237fb5d84aed6fd988cef5e2a8cfaaa03837810afe6b92。正式碰撞与对局效果尚待比赛回放验证。ZIP SHA-256: d4c3684665e9e6eef4a20d78e935537c4ea2c878e2b2c89c90e59e05b21f09c0；bundle 77b34e16-ae07-42ee-bd3a-ff49916cf6be；account2 version 8 4af463a7-9945-45a8-ba65-887d3f1c65c8，entry code hash d4c3684665e9。

## 对应规范

- [11-12-pathing-routes.md](../../spec/11-12-pathing-routes.md)

## 验证情况

见 `metadata.json` 的 `status` 与 `api_result`；不要仅凭上传或准入成功声称完整对局通过。
