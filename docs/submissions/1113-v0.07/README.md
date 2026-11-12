# 1113-v0.07

- **日期**：2026-11-13（Asia/Shanghai）
- **比赛 ID**：`2a97f94f-816a-52b7-b4b8-5925db160245`
- **合同**：rsi-fps-5.5
- **状态**：account2 submitted; admission passed; version 6 activated
- **快照**：agent.py, advance_holds.py, map_patches.py, dust2_replay.py

## 改动

- **Mirage VIP 狗洞（crouch-only）**：`(75.3, 66.2)` 的低通道新增
  `map_patches.CrouchGate` 与 `agent.traverse_gate()`。进入通道后
  `crouch=True`、直行、**禁止 jump**，穿过后清空路径重新 A*；修复
  T（40 s 兜底）与 CT（CT spawn→A）在此反复起跳、整回合卡住的问题。
  取证见 `docs/spec/11-13-mirage-vip-doghole.md`。
- **推进 / 预瞄锚点**：新增 `advance_holds.py`；`move(aim=...)` 将预瞄
  yaw/pitch 与移动方向解耦。`11-12-advance-holds.md` §4.1–§4.4 的
  nevaio 数据已落地；CT A 锚点覆盖 dust2 / mirage / nevaio / borgo，
  molo 使用 nav 通用回退（site 最近节点 + 离 CT spawn 最远的邻居）。
- **Mirage CT A 防守**：锚点 `(51.5, 87.3, 15.55)`，准星锁 A ramp
  `(52, 99, 15.43)`；到达后零移动保持瞄准，不再把视野全放在箱子上并
  把背身漏给 A 大。
- **aim 高度**：所有 lane/anchor 的 aim z 视为该预瞄线层高，运行时加
  敌方头部高度 1.64 m，避免把准星压在地面。

## 验证与限制

- 全量 unittest 66/66 通过；`py_compile`、`git diff --check` 通过。
- Mirage nav 模拟（无碰撞网格）：CT spawn→A 为 `holding`，途中蹲行穿过
  VIP 狗洞；T→A 25.6 s、T→B 32.9 s 均 reached。
- dust2 / nevaio / borgo 的 CT A 与 T 路线 nav 模拟无回归；dust2 有官方
  patrol 时仍走 patrol。
- **未验证**：真实碰撞世界下蹲行速度、顶板高度与 gate 半径；正式对局
  的 CT A hold 命中率与 T 到点时间需要下一轮回填。

## 提交

- 仅提交 `account2`，FPS 合同 `rsi-fps-5.5`。ZIP SHA-256
  `06da5faa817a054cb869d35c9c2c927ea8e2b67242a5856ed0cbb39576ae4100`。
- bundle `274133f0-bea7-4ad5-a80c-8d077f565d63`，admission `passed`；
  account2 version 6 `d41cc5d9-f229-4022-a72b-ec768735fea6` 已激活，
  entry code hash `06da5faa817a`。

## 对应规范

- [11-13-mirage-vip-doghole.md](../../spec/11-13-mirage-vip-doghole.md)
- [11-12-advance-holds.md](../../spec/11-12-advance-holds.md)
- [11-12-pathing-routes.md](../../spec/11-12-pathing-routes.md)

## 验证情况

见 `metadata.json` 的 `status` 与 `api_result`；上传/准入/激活成功不代表完整对局或得分成功。

## 对应规范

TODO: 在受影响的 `docs/spec/*.md` 中加入本版本引用，并在
`docs/spec/README.md` 的版本表登记本版本。

## 验证情况

见 `metadata.json` 的 `status` 与 `api_result`；不要仅凭上传或准入成功声称完整对局通过。
