# 1112-v0.02

- **日期**：2026-11-12
- **比赛 ID**：`2a97f94f-816a-52b7-b4b8-5925db160245`
- **合同**：rsi-fps-5.5
- **状态**：submitted; admission passed; activated version 2
- **快照**：agent.py（见同目录文件）

## 改动说明

- **出生点卡住修复**：`move` 不再把 1.0 m 外的上一路径点当目标；路径点到达半径改为 2.0 m，并跳过位于下一路径点反方向且距离较近的节点。
- **卡住恢复**：卡住时把当前路径点加入 `blocked` 并推进，不再清空整条 path 后重选同一个最近节点；新增“到当前路径点 3 秒无进展就跳过”的进度看门狗。
- **转向**：目标在身后时原地转向，不再一边转一边倒退；转向期间不触发 unstick recovery。
- **测试**：新增 `tests/test_movement.py`，4/4 通过；用 2026-11-12 R7 真实回放帧验证修复版第一拍从 `path[0]=ct` 变为 `path[0]=rear_corner`。
- **线上**：bundle `e0cbafab-cb9a-4cb2-acf6-866a8de95ba7`，admission `passed`；version `2` 已激活（`5a0da38e-f845-4323-b80d-a51560e51e24`）。
- **仍未验证**：新对局实际表现；空弹切枪 badcase 仍未修复，见 `docs/spec/11-12-empty-primary-switch-reload.md`。

## 提交结果

| 项目 | 值 |
| --- | --- |
| `bundle_id` | `e0cbafab-cb9a-4cb2-acf6-866a8de95ba7` |
| `version_id` | `5a0da38e-f845-4323-b80d-a51560e51e24` |
| `number` | `2` |
| `admission` | `passed` |
| `bundle_sha256` | `033716bdfb0ccdbf859314ec47ffde597623d615478ef9da0df923c039a58ea2` |
| `agent.py` sha256 | `f32f3aec233fc6b47cdc657cd72447daac76b1720833f6ededc86dfbcce65db3` |
| `entry` | `f81706cb-1aa5-54e6-9e4b-e1199ca25820`，网页显示 `version.number = 2`、`code_hash_short = 033716bdfb0c` |
| `Idempotency-Key` | `d146966d-1849-47e1-ab29-f69cf72370ff` |

调用顺序：`POST .../bundles`（201，`queued`）→ 轮询 `GET .../bundles/{id}`（`running` → `passed`）→ `POST .../competitions/{id}/versions`（200，`version_id` 已返回）。

## 对应规范

- [`docs/spec/11-12-stuck-at-spawn.md`](../../spec/11-12-stuck-at-spawn.md) — 本版本修复的卡住 badcase、真实对局证据与验收标准。
- [`docs/spec/11-12-empty-primary-switch-reload.md`](../../spec/11-12-empty-primary-switch-reload.md) — 仍未修复的空弹切枪 badcase；本版本不改变该路径。
- [`docs/spec/README.md`](../../spec/README.md#提交版本与改动说明) — 版本表登记本版本。

## 验证情况

- 已验证：ZIP 上传、Python admission `passed`、version `2` 激活；competition entries 显示 `version.number = 2`、`code_hash_short = 033716bdfb0c`。
- 已验证（本地）：`python3 -m unittest discover -s tests -v` 4/4；用 2026-11-12 R7 公开回放帧验证修复版第一拍从 `path[0]=ct` 变为 `path[0]=rear_corner`。
- **未验证**：新版本在 12:00–14:00 UTC 下一轮的完整对局、比分、回放与长期排名；admission 通过不代表完整对局成功。
- 已知未修：空弹主武器不切枪 / `reload_until` 语义等，仍见 `baseline-compatibility.md` 与空弹 badcase。

## 赛后回填（2026-11-12 12:00 UTC）

- `main`（seat 3，`dust2-cs2-v54`）：13–8 胜；公开事件中全场 10 人合计 **0 个 `fire`**、0 命中、0 击杀，21 回合中 20 回合 timeout；仅 R20 下包 B 后爆炸。该场为 `lobby_zero_combat` 异常对局，**不能用于交火/命中结论**，但可用于移动/卡死观测：防守 12/12 到点，进攻 4/9 到点，R13/R14/R15/R17/R19 在 T 侧出生点附近卡死。
- **公开帧复现（2026-11-12）**：对手队 team 1 的 seats 5–9 在 R0/R1（T）与 R13（CT）两侧均不购买（cash 保持 800 / 4050、armor 0）、`speed=0`、`idle`、不移动；我方 seats 1/2/3 购买并移动，seat 0 fault、seat 4 idle。全场 0 交火主要是**对手队全队 inactive**，不是全局地图或我方移动代码冻结；该场也不能用于我方交火/命中结论。
- `account2`（seat 1，`borgo-r3-v54`）：13–6 胜；143 发 / 23 中（16.1%）/ 7 kill / 5 death；到点 14/19，回防启动 4/4、到位 0/4。
- 与 v0.01 的指标对比、判定门槛和逐回合证据见 [`docs/spec/11-12-match-observability.md`](../../spec/11-12-match-observability.md)。结论为混合：卡死/到点明显改善，交火参与未改善，命中率暂定下降，回防只改善启动、未改善到位。
- **仍未验证**：更多正常交火对局、长期排名；dust2 T 侧卡死是新发现的残留问题。
