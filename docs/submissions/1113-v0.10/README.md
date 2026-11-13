# 1113-v0.10

- **日期**：2026-11-13
- **比赛 ID**：`2a97f94f-816a-52b7-b4b8-5925db160245`
- **合同**：unknown
- **状态**：main submitted; admission passed; version 6 activated · account2 submitted; admission passed; version 9 activated
- **快照**：advance_holds.py, agent.py, dust2_replay.py, map_patches.py, mirage_replay.py（见同目录文件）

## 改动说明

# 1113-v0.10

- **日期**：2026-11-13
- **比赛 ID**：`2a97f94f-816a-52b7-b4b8-5925db160245`
- **合同**：rsi-fps-5.5
- **状态**：main submitted; admission passed; version 6 activated · account2 submitted; admission passed; version 9 activated
- **快照**：advance_holds.py, agent.py, dust2_replay.py, map_patches.py, mirage_replay.py（见同目录文件）

## 改动说明

开火距离分层（[11-13-fire-range-bands.md](../../spec/11-13-fire-range-bands.md)）：

- 近距 **≤ 32.5 m**（Mirage A 点中央→警家实测 32.56 m）且 `chest/abdomen` 可见 → 扫射；
- 中距 **≤ 48.75 m**（1.5×扫射门）→ 只点头点射，每 **42 ticks（0.7 s）** 一发；
- 远距 **> 48.75 m** → 仍只点头点射，但降为每 **60 ticks（1 s）** 一发；
- `head` 不在 `parts` 中时点射不扣扳机；沿用 `STOP_SPEED` 刹停门与移动/开火互斥；
- 移除旧 `CLOSE_SPRAY_RANGE=20.0` 与 15-tick 点射节奏。

本 ZIP 同时包含工作区中 v0.09 的 Mirage 1410 帧录制轨迹（`mirage_replay.py`）：main 从 version 5 一举更新到 v0.09 + 本改动，account2 从 version 8 更新。

本地 `python3 -m unittest discover -s tests` **82/82** 通过。正式对局效果（尤其远距 1 s 头部点射命中率）待新对局回填。

## 上传结果

- ZIP SHA-256：`09a4bfac4aaa181b8b8383cc4f1814042ea068a73dac55b5ba8d6a382e551753`
- main：bundle `b8c9f303-5bf8-4969-9e0e-2380140d2ada`，version 6，entry code hash `09a4bfac4aaa`
- account2：bundle `c8b0cb21-45ac-44f6-98fd-60df1535e00a`，version 9，entry code hash `09a4bfac4aaa`

## 对应规范

- [11-13-fire-range-bands.md](../../spec/11-13-fire-range-bands.md)

## 验证情况

见 `metadata.json` 的 `status` 与 `api_result`；不要仅凭上传或准入成功声称完整对局通过。

## 对应规范

TODO: 在受影响的 `docs/spec/*.md` 中加入本版本引用，并在
`docs/spec/README.md` 的版本表登记本版本。

## 验证情况

见 `metadata.json` 的 `status` 与 `api_result`；不要仅凭上传或准入成功声称完整对局通过。
