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
