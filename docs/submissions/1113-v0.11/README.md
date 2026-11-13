# 1113-v0.11

- **日期**：2026-11-13
- **比赛 ID**：`2a97f94f-816a-52b7-b4b8-5925db160245`
- **合同**：unknown
- **状态**：main submitted; admission passed; version 7 activated · account2 submitted; admission passed; version 10 activated
- **快照**：advance_holds.py, agent.py, dust2_replay.py, map_patches.py, mirage_replay.py（见同目录文件）

## 改动说明

# 1113-v0.11

- **日期**：2026-11-13
- **比赛 ID**：`2a97f94f-816a-52b7-b4b8-5925db160245`
- **合同**：rsi-fps-5.5
- **状态**：main submitted; admission passed; version 7 activated · account2 submitted; admission passed; version 10 activated
- **快照**：advance_holds.py, agent.py, dust2_replay.py, map_patches.py, mirage_replay.py（见同目录文件）

## 改动说明

基于 main 最新对局 `5466919c-22aa-45f5-8b0c-fee9143708b0`（dust2，seat 4 = team 0 = 第 5 个玩家）的两个公开帧 badcase：

1. **R19（`round_index 18`）第二目标抽搐**：击杀 seat 6 后，对 24.7 m 的 seat 9 与 48–50 m 的 seat 5/7/8 之间来回切目标；可见性闪烁时 `_reset_combat_state()` 重置点射节奏，agent 在 combat 与录制轨迹移动之间 20 Hz 切换，并伴随蹲起/pitch 摆动。
   - 新增 `COMBAT_MEMORY_TICKS=18`（0.3 s）战斗记忆：`visible` 短暂为空时 `combat_wait()` 保持视角、停步、禁火，不清空点射节奏；
   - `_pick_target()` 目标锁：目标短暂消失时保留最后位置，只有新目标 <10 m 且距离不到旧目标一半才换目标；
   - `combat()` 只在目标当前可见时开火，并移除战斗蹲起（消除 eye/alignment 反馈环）。
2. **R18（`round_index 17`）T 出生点被队友堵死**：seat 4 从 124923 到回合结束 131763 一直卡在 `(76.8, 81.3)`，速度 3.7–5.5 m/s，seat 3 / seat 0 距其 0.7 m / 1.1 m。录制轨迹跟随没有“有输入但无位移”检测。
   - `REPLAY_BLOCK_TICKS=20`：录制轨迹移动 20 ticks 无 0.3 m 进度即判定被堵；
   - `avoid_replay_block()` 侧移 ±0.9、持续 24 ticks，每次换方向；
   - 连续 4 次失败后放弃录制路线（`replay_abandoned`），回退 A*，并允许 40 s T 出生点兜底生效。

本地 `python3 -m unittest discover -s tests` **86/86** 通过。正式对局效果待下一场回填。

## 上传结果

- ZIP SHA-256：`a77f1c7e5b22dd67db789bef050088bce1f0561b8878533715f023ba44c019af`
- main：bundle `ae3a40d0-1c69-4c68-bf7b-4d5165f9afac`，version 7，entry code hash `a77f1c7e5b22`
- account2：bundle `10e01070-ad5e-4b6d-bd0f-1cac55fa9556`，version 10，entry code hash `a77f1c7e5b22`

## 对应规范

- [11-13-combat-stability.md](../../spec/11-13-combat-stability.md)
- [11-13-fire-range-bands.md](../../spec/11-13-fire-range-bands.md)

## 验证情况

见 `metadata.json` 的 `status` 与 `api_result`；不要仅凭上传或准入成功声称完整对局通过。

## 对应规范

TODO: 在受影响的 `docs/spec/*.md` 中加入本版本引用，并在
`docs/spec/README.md` 的版本表登记本版本。

## 验证情况

见 `metadata.json` 的 `status` 与 `api_result`；不要仅凭上传或准入成功声称完整对局通过。
