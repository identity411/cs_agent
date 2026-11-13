# 1113-v0.14

- **日期**：2026-11-13
- **比赛 ID**：`2a97f94f-816a-52b7-b4b8-5925db160245`
- **合同**：rsi-fps-5.5
- **状态**：main v10 / account2 v13 activated; admission passed
- **快照**：advance_holds.py, agent.py, borgo_replay.py, dust2_replay.py, map_patches.py, mirage_replay.py, molo_replay.py, nevaio_replay.py, pro_retakes.py（见同目录文件）

## 改动说明

Dust2/Mirage CT 对侧下包回防使用职业 demo 路线：按当前位置选择方向和起点，全程冲刺跟随位置与视角；遇敌暂停交战，战后续走。示范帧结束后直奔实时炸弹坐标拆包；引信时间不足仍沿示范路线跑，仅实际卡住才用 A* 脱困。地图 ID 与几何哈希校验，未匹配时保持原有寻路。104 项单元测试通过；正式对局效果待验证。

## 对应规范

[Dust2 / Mirage 职业 demo 回防路线](../../spec/11-13-pro-demo-routes.md)。

## 上传结果

- ZIP SHA-256：`fcc52013a8046706a45aa16e5425ea5de77bea460e1e2dadcce183f0e97e7787`。
- main：bundle `f83da39e-dc10-4726-9171-54e28714f8e2`，version 10 已激活。
- account2：bundle `473bd959-fd25-4db6-bda7-c9f87f30e89e`，version 13 已激活。
- 两个 bundle 的 admission 均为 `passed`，entry code hash 均为 `fcc52013a804`。

## 验证情况

见 `metadata.json` 的 `status` 与 `api_result`；不要仅凭上传或准入成功声称完整对局通过。
