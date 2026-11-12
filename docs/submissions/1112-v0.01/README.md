# 1112-v0.01 — first-python-submission

- **日期**：2026-11-12
- **比赛 ID**：`2a97f94f-816a-52b7-b4b8-5925db160245`
- **合同**：`rsi-fps-5.5`
- **运行时**：`python-agent-v1`
- **状态**：已提交；admission `passed`；版本 `1` 已激活
- **快照**：`agent.py`，sha256 `eb94b88e287d62ebb858cc0b29134dd1f1e39c3d5e4b8b388fb7bb15d545018e`

## 提交结果

| 项目 | 值 |
| --- | --- |
| `agent_id` | `11a0f0db-afda-4a57-a2f4-36ed0462085e` |
| `bundle_id` | `cfbc03a1-83de-417e-a600-230cd60c6380` |
| `version_id` | `13e15473-f1ae-463b-8cd2-a0fa3498dab9` |
| `number` | `1` |
| `admission` | `passed` |
| `fault_code` | `null` |
| `bundle_sha256` | `eb06a768569c783232a1b6bbdb221f10c87f30fdb3a04561235be7174a6e5aaf` |
| `profile_digest` | `2ab9f9d47a6f1a326d2c04414710fbdcd9ff2a0ff16bf0b2769a24d08cf692c4` |
| `Idempotency-Key` | `d1981a3f-a7bf-42d6-bd5e-e478e829ddcd` |
| 网页参赛条目 `entry_id` | `f81706cb-1aa5-54e6-9e4b-e1199ca25820` |
| 网页显示版本 | `number: 1`，`code_hash_short: eb06a768569c` |

调用顺序：

1. `POST /api/v1/python-submissions/agents/11a0f0db-afda-4a57-a2f4-36ed0462085e/bundles`（二进制 ZIP）→ 201，`admission: queued`
2. `GET /api/v1/python-submissions/bundles/cfbc03a1-83de-417e-a600-230cd60c6380` → `running` → `passed`
3. `POST /api/v1/python-submissions/competitions/2a97f94f-816a-52b7-b4b8-5925db160245/versions` `{submission_id, auto_match: true}` → 200，返回 `version_id`

Python bundle history 显示 `number: 1`、`version_id`、`admission: passed`。网页对应的参赛条目也已确认：

```text
GET /api/v1/competitions/{id}/entries?agent_id=11a0f0db-...
→ version: { "number": 1, "code_hash_short": "eb06a768569c" }
```

`GET /api/v1/me/competitions` 的 `current_version` 仍为 `null`，这是汇总字段滞后；版本是否生效以参赛条目接口与 Python bundle history 为准。

## 改动说明

代码与 `1112-v0.00` 完全相同，未修改策略逻辑。本版本是一次真实的 Python ZIP 提交、准入和版本激活验证。

## 对应规范

- [`.claude/skills/agx-submit/SKILL.md`](../../../.claude/skills/agx-submit/SKILL.md) — 实测 Python 提交端点、回执字段、预算与提交结果。
- [`docs/spec/baseline-compatibility.md`](../../spec/baseline-compatibility.md) — 本版本沿用 baseline，已知差异仍未修复。
- [`docs/spec/README.md`](../../spec/README.md#提交版本与改动说明) — 版本表登记。

## 验证情况

- 已验证：ZIP 上传、Python admission 通过、版本 1 激活；网页参赛条目 `f81706cb...` 显示 `version.number = 1`。
- **未验证**：完整正式对局、比分、回放、长期排名。
- admission 通过说明首拍决策没有崩溃；它不覆盖五张地图、完整回合或交火/下包路径。
- 已知高风险假设仍未处理：`map.nav` 的完整可用性、`aim_punch` 与 `recoil_pitch/recoil_yaw` 的差异、`reload_until` 的绝对 tick 语义、下包 / 拆包条件。详见 `baseline-compatibility.md`。
