# 1113-v0.12

- **日期**：2026-11-13
- **比赛 ID**：`2a97f94f-816a-52b7-b4b8-5925db160245`
- **合同**：unknown
- **状态**：main submitted; admission passed; version 8 activated · account2 submitted; admission passed; version 11 activated
- **快照**：advance_holds.py, agent.py, dust2_replay.py, map_patches.py, mirage_replay.py（见同目录文件）

## 改动说明

# 1113-v0.12

- **日期**：2026-11-13
- **比赛 ID**：`2a97f94f-816a-52b7-b4b8-5925db160245`
- **合同**：rsi-fps-5.5
- **状态**：main submitted; admission passed; version 8 activated · account2 submitted; admission passed; version 11 activated
- **快照**：advance_holds.py, agent.py, dust2_replay.py, map_patches.py, mirage_replay.py（见同目录文件）

## 改动说明

在 v0.11 的录制路线保护之上增加“A* 恢复后接回预设路线”：

- 录制轨迹连续 4 次侧移仍无法脱离时，只**暂时**放弃（`replay_done` / `replay_abandoned`），改用 A*；
- `maybe_rejoin_replay()`：A* 从卡住点移动 ≥ `REPLAY_RECOVER_DISTANCE`（3 m）后，若当前距剩余录制路线 ≤ `REPLAY_REJOIN_DISTANCE`（8 m），接回最近的前向录制帧；>3 m 时先用现有 A* rejoin 走位到该帧；
- 如果 A* 已远离录制路线（>8 m），保持 A*，避免为回到旧路线大幅倒退；
- `ct_fallback` 仍只在 `replay_abandoned` 时启用；成功接回后自动关闭。

本地固定位置仿真：20 ticks 无进度 → 侧移 → 4 次失败 → A*；新增单元测试验证 A* 脱离 3 m 且靠近路线时接回、未脱离/远离路线时不接回。`python3 -m unittest discover -s tests` **88/88** 通过。正式对局效果待下一场回填。

## 上传结果

- ZIP SHA-256：`d0bfe8b88034ce09822519f8ce155c1ec0fc771b3bbc133169e43dfec647cca4`
- main：bundle `fa601629-c00c-4ea1-bd8e-c15b021b0d5a`，version 8，entry code hash `d0bfe8b88034`
- account2：bundle `3a1f0b53-3103-4276-a47a-442f6ff21d11`，version 11，entry code hash `d0bfe8b88034`

## 对应规范

- [11-13-combat-stability.md](../../spec/11-13-combat-stability.md)

## 验证情况

见 `metadata.json` 的 `status` 与 `api_result`；不要仅凭上传或准入成功声称完整对局通过。

## 对应规范

TODO: 在受影响的 `docs/spec/*.md` 中加入本版本引用，并在
`docs/spec/README.md` 的版本表登记本版本。

## 验证情况

见 `metadata.json` 的 `status` 与 `api_result`；不要仅凭上传或准入成功声称完整对局通过。
