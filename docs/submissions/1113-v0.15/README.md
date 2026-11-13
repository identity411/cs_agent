# 1113-v0.15

- **日期**：2026-11-13
- **比赛 ID**：`2a97f94f-816a-52b7-b4b8-5925db160245`
- **合同**：unknown
- **状态**：main submitted; admission passed; version 11 activated · account2 submitted; admission passed; version 14 activated
- **快照**：advance_holds.py, agent.py, borgo_replay.py, dust2_replay.py, map_patches.py, mirage_replay.py, molo_replay.py, nevaio_replay.py, pro_retakes.py（见同目录文件）

## 改动说明

# 1113-v0.15

- **日期**：2026-11-13
- **比赛 ID**：`2a97f94f-816a-52b7-b4b8-5925db160245`
- **合同**：rsi-fps-5.5
- **状态**：main submitted; admission passed; version 11 activated · account2 submitted; admission passed; version 14 activated
- **快照**：advance_holds.py, agent.py, borgo_replay.py, dust2_replay.py, map_patches.py, mirage_replay.py, molo_replay.py, nevaio_replay.py, pro_retakes.py（见同目录文件）

## 改动说明

CT 防守 peek loop（[11-13-ct-defensive-peeks.md](../../spec/11-13-ct-defensive-peeks.md)）：

- `advance_holds.DefendHold`：Mirage A/B、Dust2 A/B 各一个固定站位与两个入口瞄点，默认每个瞄点停留约 2.8 s；
- `agent.py:defend_hold_target()`：CT 在炸弹未下包、无可见敌人且到达站位时，按站位/瞄点循环；敌人出现暂停循环并进入现有战斗逻辑，敌人消失后继续当前瞄点；换回合重置；
- 下包后不再使用防守循环，继续走现有回防/拆弹逻辑；
- Mirage A：A boxes，A ramp/palace → jungle/connector；Mirage B：B short cover，market → apartments/short；Dust2 A：A back，long A → short/cat；Dust2 B：B back，tunnels → upper/short。

本地 `python3 -m unittest discover -s tests` **105/105** 通过。正式对局效果待下一场回填。

## 上传结果

- ZIP SHA-256：`b6de28e989ad62e2c946e2a5e33e0d5213711bca351859655651756cb1cd5b75`
- main：bundle `d5a51958-d75d-48a1-beaf-b1d79db05336`，version 11，entry code hash `b6de28e989ad`
- account2：bundle `41f7046d-950e-4273-833a-294700414d76`，version 14，entry code hash `b6de28e989ad`

## 对应规范

- [11-13-ct-defensive-peeks.md](../../spec/11-13-ct-defensive-peeks.md)

## 验证情况

见 `metadata.json` 的 `status` 与 `api_result`；不要仅凭上传或准入成功声称完整对局通过。

## 对应规范

TODO: 在受影响的 `docs/spec/*.md` 中加入本版本引用，并在
`docs/spec/README.md` 的版本表登记本版本。

## 验证情况

见 `metadata.json` 的 `status` 与 `api_result`；不要仅凭上传或准入成功声称完整对局通过。
