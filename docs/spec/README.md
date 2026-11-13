# 技术规范

本目录记录实现 FPS agent 所依赖的官方技术契约。

依据：AGX「多人爆破 · AI 助手开发指南」，合同 `rsi-fps-5.5`（2026-11-12 版）。该指南声明为**闭门候选合同**：只有赛事与已接受投稿明确选择它时才适用；历史对局保留自己的合同。文档存在或本地成功都不表示赛事已开放。

## 变更记录

### 2026-11-12
- **关联规范**：[agent-interface.md](agent-interface.md)、[maps.md](maps.md)、[baseline-compatibility.md](baseline-compatibility.md)、[agx-submit skill](../../.claude/skills/agx-submit/SKILL.md)。
- **背景**：线上 FPS 比赛使用 `rsi-fps-5.5` Python runtime；需要一份精简的本地合同与提交记录，避免重复官网/平台级文档。
- **决策点**：只保留 FPS 专用规范；运行时预算与上传流程放在 skill；不落盘完整武器目录，价格与限额以官方冻结目录为准。
- **新增 badcase**：[11-12-economy-rotation-combat.md](11-12-economy-rotation-combat.md) — v0.01 对局中经济 / 转点 / 走路 / 蹲射 / 换弹 5 类非卡住问题；v0.02 未覆盖。
- **新增可观测性规范**：[11-12-match-observability.md](11-12-match-observability.md) — 定义参战 / 开火 / 命中 / 卡死 / 回防指标与变好/变坏判定；首批回填 v0.01 ×1 场 vs v0.02 ×2 场。
- **新增寻路规范**：[11-12-pathing-routes.md](11-12-pathing-routes.md) — A* + 执行反馈边代价 + dust2 attackRoutes + sprint/战斗超时/plant zone；已随 v0.03 提交/激活。v0.04 又加入前进跳 / 台阶跳，并把地图坐标和阈值移到根目录 `map_patches.py`（`MapPatch` 抽象）；详见 [11-12-mirage-spawn-jump.md](11-12-mirage-spawn-jump.md)。
- **新增推进点规范**：[11-12-advance-holds.md](11-12-advance-holds.md) — 寻路之后的推进点（跑—停—打—跑、预瞄点/预瞄角度、hold/刹停参数、nevaio 五条 lane 实测数据）；取证自 `da110811` 的 seat 3（网页 Seat 4）；未实现，v0.05 候选。
- **v0.03 提交**：[`1112-v0.03`](../submissions/1112-v0.03/README.md) — 包含 A*、dust2 attackRoutes、R2 包点 patrol、sprint / 战斗超时 / plant zone；`main` version `3`、`account2` version `2` 均 admission `passed` 并激活。
- **v0.04 提交**：[`1112-v0.04`](../submissions/1112-v0.04/README.md) — 前进跳 / 台阶跳、`map_patches.py`、Mirage / dust2 soft hazard、T 方 pre-plant patrol 振荡修复与临时 40 s → CT spawn 兜底；`main` version `4`、`account2` version `3` 均 admission `passed` 并激活。

### 2026-11-13
- **v0.05 提交**：[`1113-v0.05`](../submissions/1113-v0.05/README.md) — 将 Dust2 用户录制的 2002 帧轨迹转为位置/视角闭环跟随；仅 `account2` version `4` admission `passed` 并激活。
- **v0.06 提交**：[`1113-v0.06`](../submissions/1113-v0.06/README.md) — 原地准星帧逐拍跟随修正版；仅 `account2` version `5` admission `passed` 并激活，替代 account2 v4。
- **v0.07 提交**：[`1113-v0.07`](../submissions/1113-v0.07/README.md) — Mirage VIP 狗洞 crouch 穿越、`advance_holds.py` 推进/预瞄锚点（§4.1–4.4 + 多地图 CT A）、Mirage CT A 瞄准 A ramp 并 hold；仅 `account2` version `6` admission `passed` 并激活。
- **推进/预瞄锚点**：实现 `advance_holds.py` + `move(aim=…)`；§4.1–4.4 的 nevaio 锚点落地，CT A 锚点覆盖 dust2/mirage/nevaio/borgo，molo 用 nav 通用回退。
- **Mirage VIP 狗洞**：`(75.3,66.2)` 低通道需要蹲下；新增 `CrouchGate` + `traverse_gate()`，通道内 `crouch=True` 且禁止跳跃，修复卡住跳与狗洞冲突。见 [11-13-mirage-vip-doghole.md](11-13-mirage-vip-doghole.md)。
- **v0.08 提交**：[`1113-v0.08`](../submissions/1113-v0.08/README.md) — `fbd4b6bf` R9 公开帧确认 CT 出生点台阶卡脚 + 90 m 扫射；实现 `STOP_SPEED` 刹停门、远距离 head-only 点射、带包人 40 s 兜底豁免、Mirage A/B 守包 spot/look（不再转圈）和 nevaio `warm_hall` hazard + 回合清 edge penalty；`main` version `5`、`account2` version `7` admission `passed` 并激活。见 [11-13-nevaio-r9-fire-discipline.md](11-13-nevaio-r9-fire-discipline.md) 与 [11-13-post-plant-holds.md](11-13-post-plant-holds.md)。
- **v0.09 提交**：[`1113-v0.09`](../submissions/1113-v0.09/README.md) — Mirage 用户录制 1410 帧进攻轨迹，仅在地图 ID/哈希匹配时启用位置与准星反馈跟随；`account2` version `8` admission `passed` 并激活。
- **开火距离分层**：[11-13-fire-range-bands.md](11-13-fire-range-bands.md) — 近距（≤ Mirage A 中央→警家 32.5 m）才扫射；否则点射，且只点头、每 42 ticks（0.7 s）一发；超过 1.5×（48.75 m）仍只点头，但降为每 60 ticks（1 s）一发。取代 [11-13-nevaio-r9-fire-discipline.md](11-13-nevaio-r9-fire-discipline.md) 中“远距离扫射”的验收；本地 82/82 测试通过。
- **CT 防守 peek loop**：[11-13-ct-defensive-peeks.md](11-13-ct-defensive-peeks.md) — Mirage/Dust2 A/B 固定站位轮看两个主要入口；未下包时启用，发现敌人暂停，炸弹下包后切回回防/拆包逻辑。随 v0.15 提交，本地 105/105 测试通过。
- **v0.10 提交**：[`1113-v0.10`](../submissions/1113-v0.10/README.md) — 开火距离分层随包提交；同时把 main 从 v5 更新到含 v0.09 Mirage 轨迹的版本。`main` version `6`、`account2` version `9` admission 均 `passed` 并激活，entry code hash `09a4bfac4aaa`；待新对局验证。
- **战斗稳定性**：[11-13-combat-stability.md](11-13-combat-stability.md) — `5466919c` R19（`round_index 18`）击杀第一人后可见性闪烁导致目标/蹲起/移动抽搐；R18（`round_index 17`）录制路线被卡住的队友堵在 T 出生点 114 s。新增 18-tick 战斗记忆、目标锁、移除战斗蹲起、录制轨迹无进度侧移与暂时放弃；A* 脱离卡点且仍靠近路线时自动接回录制帧。本地 88/88 测试通过。
- **v0.11 提交**：[`1113-v0.11`](../submissions/1113-v0.11/README.md) — 战斗稳定性修复随包提交；`main` version `7`、`account2` version `10` admission 均 `passed` 并激活，entry code hash `a77f1c7e5b22`；待新对局验证。
- **v0.12 提交**：[`1113-v0.12`](../submissions/1113-v0.12/README.md) — A* 脱离卡点且距剩余录制路线 ≤8 m 时自动接回前向录制帧；`main` version `8`、`account2` version `11` admission 均 `passed` 并激活，entry code hash `d0bfe8b88034`；本地 88/88 测试通过，待新对局验证。
- **v0.13 提交**：[`1113-v0.13`](../submissions/1113-v0.13/README.md) — Borgo、Molo、Nevaio 三条用户录制轨迹接入；带包者在目标包点前 12 m 切换 A* 下包，下包后守包。`main` version `9`、`account2` version `12` admission 均 `passed` 并激活，entry code hash `6445465bb5ae`；待新对局验证。
- **v0.14 提交**：[`1113-v0.14`](../submissions/1113-v0.14/README.md) — Dust2/Mirage 职业 demo CT 对侧下包回防路线接入；全程冲刺跟随示范位置和视角，遇敌暂停交战后续走，路线结束直奔炸弹，实际卡住才用 A* 脱困。`main` version `10`、`account2` version `13` admission 均 `passed` 并激活，entry code hash `fcc52013a804`；待新对局验证。见 [11-13-pro-demo-routes.md](11-13-pro-demo-routes.md)。
- **v0.15 提交**：[`1113-v0.15`](../submissions/1113-v0.15/README.md) — Mirage/Dust2 A/B CT 防守 peek loop：`advance_holds.DefendHold` + `agent.defend_hold_target()`，未下包时固定站位轮看两个入口，遇敌暂停、下包后切回回防。`main` version `11`、`account2` version `14` admission 均 `passed` 并激活，entry code hash `b6de28e989ad`；本地 105/105 测试通过，待新对局验证。见 [11-13-ct-defensive-peeks.md](11-13-ct-defensive-peeks.md)。

## 实测状态（2026-11-12）

- 比赛 `2a97f94f-816a-52b7-b4b8-5925db160245` 在 `agx.cool` 上为 `game_id=fps`、`rules_version=rsi-fps-5.5`、状态 `open`；账号已报名，Python agent 为 `11a0f0db-afda-4a57-a2f4-36ed0462085e`。
- Python 提交路径已实测：`python-agent-v1` ZIP → admission `passed` → 版本 `1` 激活；网页参赛条目 `f81706cb-1aa5-54e6-9e4b-e1199ca25820` 显示 `version.number = 1`。详见 [`../submissions/1112-v0.01/README.md`](../submissions/1112-v0.01/README.md)。
- 2026-11-12：出生点卡住修复版已提交，admission `passed`，version `2` 激活（entry 显示 `version.number = 2`、`code_hash_short = 033716bdfb0c`）。详见 [`../submissions/1112-v0.02/README.md`](../submissions/1112-v0.02/README.md)；12:00 UTC 两场已回填，见 [11-12-match-observability.md](11-12-match-observability.md)，长期验证仍待完成。
- 2026-11-12：A* / attackRoutes / patrol / 战斗控制版已提交到 `main` 和 `account2`，admission 均 `passed`；`main` version `3`、`account2` version `2` 激活（两者 entry 均显示 `code_hash_short = 07f6516dfb12`）。详见 [`../submissions/1112-v0.03/README.md`](../submissions/1112-v0.03/README.md)；待下一场正式对局回填。
- 2026-11-12 15:31 UTC：前进跳 / 台阶跳 / `map_patches.py` / Mirage 修正版已提交到 `main` 和 `account2`，admission 均 `passed`；`main` version `4`、`account2` version `3` 激活（两者 entry 的 `code_hash_short = 765af129d095`）。详见 [`../submissions/1112-v0.04/README.md`](../submissions/1112-v0.04/README.md)；待下一场正式对局回填。
- 2026-11-13 00:06 CST：Dust2 用户录制轨迹跟随版仅提交到 `account2`，admission `passed`、version `4` 激活，entry `code_hash_short = b91f85504c7b`。详见 [`../submissions/1113-v0.05/README.md`](../submissions/1113-v0.05/README.md)；正式对局效果待验证。
- 2026-11-13 00:14 CST：Dust2 录制轨迹原地准星帧逐拍修正版仅提交到 `account2`，admission `passed`、version `5` 激活，entry `code_hash_short = c00849609e14`。详见 [`../submissions/1113-v0.06/README.md`](../submissions/1113-v0.06/README.md)；正式对局效果待验证。
- `/api/openapi.json` **不列出** `/api/v1/python-submissions` 路由；实测端点、预算与故障语义见 [agx-submit skill](../../.claude/skills/agx-submit/SKILL.md)。
- `GET /api/v1/games/fps` 的 `example_code` / `baselines` 是 JavaScript 参考，不代表提交语言；Python 以 `GET /api/v1/python-submissions/templates/fps` 的 `profile` / `files` 为准。

## 源码定位

| 合同 / 机制 | 源码 |
| --- | --- |
| 赛制 / CPU | `rsi/fps_v54_contract.py:7` |
| 回合转换 / 时钟 | `rsi/games/fps_v54_rounds.py:9` |
| 经济选择 / 结算 | `rsi/games/fps_v54_economy_rules.py:22` |
| 选图 / 后端 | `rsi/games/fps_v54_maps.py:38` |
| 公开地图 / 观察 | `rsi/games/fps_v54.py:730` |
| 全部动作字段 | `rsi/games/fps_v54_actions.py:9` |
| 安放 / 拆除 | `rsi/games/fps_v54_objective.py:11` |
| 十席冻结 / 故障 / 比分 | `rsi/games/fps_v4.py:1077` |
| 流 / 执行限额 | `rsi/runtime/stream_profiles.py:450` |
| Python 适配 / 合法批次 | `rsi/python_runtime/adapters/fps54.py:1` |
| Python CPU profile | `rsi/python_integration/profiles.py:25` |
| SDK 本地钩子 | `sdk/python-agent/games/fps54/hook.py:5` |
| ZIP API / 历史 | `rsi/python_submissions/api.py:1` |

## 索引

- [agent-interface.md](agent-interface.md) — 生命周期、合法观测、完整动作合同。
- [maps.md](maps.md) — 五图、选图哈希、坐标与地图描述缓存。
- [baseline-compatibility.md](baseline-compatibility.md) — 当前 `agent.py` 与官方合同的差异清单。
- [agx-submit skill](../../.claude/skills/agx-submit/SKILL.md) — 运行时预算、ZIP 限制、故障语义与实测 Python 提交流程。
- [agx-match-query skill](../../.claude/skills/agx-match-query/SKILL.md) — 只读对局 / 公开回放查询、席位统计与 badcase 取证。
- [11-12-empty-primary-switch-reload.md](11-12-empty-primary-switch-reload.md) — badcase：空弹主武器不切枪 / 不换弹的复现与验收。
- [11-12-stuck-at-spawn.md](11-12-stuck-at-spawn.md) — badcase：出生点/近点卡住导致整回合不交战。
- [11-12-site-center-hold.md](11-12-site-center-hold.md) — badcase：到达包点后停在中心不动（R2）。
- [11-12-economy-rotation-combat.md](11-12-economy-rotation-combat.md) — badcase：v0.01 对局的 5 类非卡住问题（经济 / 转点 / 走路 / 蹲射 / 换弹）。
- [11-12-match-observability.md](11-12-match-observability.md) — 规范：对局可观测性指标（参战 / 命中 / 卡死 / 回防）与版本对比判定。
- [11-12-pathing-routes.md](11-12-pathing-routes.md) — 规范：A* 寻路、dust2 进攻路线、sprint/战斗超时/plant zone、前进跳 / 台阶跳、`map_patches.py`、临时 T 40 s → CT spawn 兜底。
- [11-12-advance-holds.md](11-12-advance-holds.md) — 规范：寻路之后的推进点（跑—停—打—跑、预瞄点/预瞄角度、hold/刹停参数、nevaio 五条 lane 实测数据）。
- [11-12-mirage-spawn-jump.md](11-12-mirage-spawn-jump.md) — badcase：Mirage R6/R10 出生点滑动卡住与 CT A 台阶；前进跳修复。
- [11-13-mirage-vip-doghole.md](11-13-mirage-vip-doghole.md) — badcase：Mirage VIP 狗洞需蹲下，卡住跳与其冲突；crouch 穿越修复。
- [11-13-nevaio-r9-fire-discipline.md](11-13-nevaio-r9-fire-discipline.md) — badcase：nevaio R9 台阶卡脚 + 远距离扫射；刹停门 / 点射 + `warm_hall` hazard + 回合清 edge penalty。
- [11-13-fire-range-bands.md](11-13-fire-range-bands.md) — 规范：开火距离分层（近距扫射 / 中距只点头点射 0.7 s / 远距只点头点射 1 s）；扫射门取 Mirage A 中央→警家 32.5 m，快速点射边界 48.75 m。
- [11-13-combat-stability.md](11-13-combat-stability.md) — badcase：R19 可见性闪烁导致第二目标抽搐；R18 录制路线被队友堵死。战斗记忆 / 目标锁 / 不蹲起 / 路线侧移与放弃。
- [11-13-post-plant-holds.md](11-13-post-plant-holds.md) — 规范：T 守包 hold（不转圈）+ 带包人 40 s 兜底豁免；Mirage A/B spot/look 数据。
- [11-13-pro-demo-routes.md](11-13-pro-demo-routes.md) — 规范：Dust2/Mirage 职业 demo CT 对侧下包回防路线（v0.14）。
- [11-13-ct-defensive-peeks.md](11-13-ct-defensive-peeks.md) — 规范：Mirage/Dust2 A/B CT 防守固定站位与入口轮看（v0.15）。

> 完整武器 / 装备 / 投掷物数值不落盘,以官方冻结目录为准。

## Badcase 记录

badcase 采用 `MM-DD-<theme>.md` 命名；新 badcase 按日期追加，不改旧文件。每条记录最小状态、demo 复现步骤、判定标准与验收，证据由 demo / 对局回填。

| 日期 | 文件 | 状态 |
| --- | --- | --- |
| 2026-11-12 | [11-12-empty-primary-switch-reload.md](11-12-empty-primary-switch-reload.md) | 对局已观察：A/C 未出现，B 出现；待新对局验证 |
| 2026-11-12 | [11-12-stuck-at-spawn.md](11-12-stuck-at-spawn.md) | 对局已确认；v0.02 防守侧已改善，dust2 T 侧仍有卡死（见可观测性规范） |
| 2026-11-12 | [11-12-site-center-hold.md](11-12-site-center-hold.md) | R2 已复现；patrol 修复随 v0.03 提交/激活，待新对局验证 |
| 2026-11-12 | [11-12-economy-rotation-combat.md](11-12-economy-rotation-combat.md) | 对局已确认（v0.01）；v0.02 回防启动改善、到位仍 0（见可观测性规范） |
| 2026-11-12 | [11-12-mirage-spawn-jump.md](11-12-mirage-spawn-jump.md) | R6（带包 seat 2）/ R10（带包 seat 1）与 CT A 台阶已用公开帧确认；前进跳随 v0.04 提交/激活，待新对局验证 |
| 2026-11-13 | [11-13-mirage-vip-doghole.md](11-13-mirage-vip-doghole.md) | account2 `dc5d2841` 公开帧确认；crouch 穿越随 v0.07 提交/激活，待新对局验证 |
| 2026-11-13 | [11-13-nevaio-r9-fire-discipline.md](11-13-nevaio-r9-fire-discipline.md) | account2 `fbd4b6bf` R9 公开帧确认（tick 42147–44326）；刹停/点射 + nevaio hazard 本地实现，75/75 测试通过，待提交/新对局验证 |

## 提交版本与改动说明

每次提交的代码快照和改动说明在 [`../submissions/`](../submissions/README.md)。规范与版本的对应关系：

| 版本 | 改动说明 | 影响的规范 |
| --- | --- | --- |
| `1112-v0.00` | [1112-v0.00/README.md](../submissions/1112-v0.00/README.md) | [baseline-compatibility.md](baseline-compatibility.md) |
| `1112-v0.01` | [1112-v0.01/README.md](../submissions/1112-v0.01/README.md) | [agx-submit skill](../../.claude/skills/agx-submit/SKILL.md), [baseline-compatibility.md](baseline-compatibility.md) |
| `1112-v0.02` | [1112-v0.02/README.md](../submissions/1112-v0.02/README.md) | [11-12-stuck-at-spawn.md](11-12-stuck-at-spawn.md), [11-12-empty-primary-switch-reload.md](11-12-empty-primary-switch-reload.md), [agx-match-query skill](../../.claude/skills/agx-match-query/SKILL.md) |
| `1112-v0.03` | [1112-v0.03/README.md](../submissions/1112-v0.03/README.md) | [11-12-pathing-routes.md](11-12-pathing-routes.md), [11-12-site-center-hold.md](11-12-site-center-hold.md), [11-12-stuck-at-spawn.md](11-12-stuck-at-spawn.md), [baseline-compatibility.md](baseline-compatibility.md) |
| `1112-v0.04` | [1112-v0.04/README.md](../submissions/1112-v0.04/README.md) | [11-12-pathing-routes.md](11-12-pathing-routes.md), [11-12-mirage-spawn-jump.md](11-12-mirage-spawn-jump.md), [11-12-stuck-at-spawn.md](11-12-stuck-at-spawn.md), [11-12-site-center-hold.md](11-12-site-center-hold.md), [baseline-compatibility.md](baseline-compatibility.md) |
| `1113-v0.05` | [1113-v0.05/README.md](../submissions/1113-v0.05/README.md) | [11-12-pathing-routes.md](11-12-pathing-routes.md) |
| `1113-v0.06` | [1113-v0.06/README.md](../submissions/1113-v0.06/README.md) | [11-12-pathing-routes.md](11-12-pathing-routes.md) |
| `1113-v0.07` | [1113-v0.07/README.md](../submissions/1113-v0.07/README.md) | [11-12-advance-holds.md](11-12-advance-holds.md), [11-13-mirage-vip-doghole.md](11-13-mirage-vip-doghole.md), [11-12-pathing-routes.md](11-12-pathing-routes.md) |
| `1113-v0.08` | [1113-v0.08/README.md](../submissions/1113-v0.08/README.md) | [11-13-nevaio-r9-fire-discipline.md](11-13-nevaio-r9-fire-discipline.md), [11-13-post-plant-holds.md](11-13-post-plant-holds.md), [11-12-advance-holds.md](11-12-advance-holds.md), [11-12-pathing-routes.md](11-12-pathing-routes.md) |
| `1113-v0.09` | [1113-v0.09/README.md](../submissions/1113-v0.09/README.md) | [11-12-pathing-routes.md](11-12-pathing-routes.md) |
| `1113-v0.10` | [1113-v0.10/README.md](../submissions/1113-v0.10/README.md) | [11-13-fire-range-bands.md](11-13-fire-range-bands.md) |
| `1113-v0.11` | [1113-v0.11/README.md](../submissions/1113-v0.11/README.md) | [11-13-combat-stability.md](11-13-combat-stability.md), [11-13-fire-range-bands.md](11-13-fire-range-bands.md) |
| `1113-v0.12` | [1113-v0.12/README.md](../submissions/1113-v0.12/README.md) | [11-13-combat-stability.md](11-13-combat-stability.md) |
| `1113-v0.13` | [1113-v0.13/README.md](../submissions/1113-v0.13/README.md) | [11-12-pathing-routes.md](11-12-pathing-routes.md) |
| `1113-v0.14` | [1113-v0.14/README.md](../submissions/1113-v0.14/README.md) | [11-13-pro-demo-routes.md](11-13-pro-demo-routes.md) |
| `1113-v0.15` | [1113-v0.15/README.md](../submissions/1113-v0.15/README.md) | [11-13-ct-defensive-peeks.md](11-13-ct-defensive-peeks.md) |

## 待补 / 待核实

- [ ] `map.nav` 在全部五图 / 完整对局中的可用性（首次 admission 已通过，但没有覆盖完整地图和回合一局）
- [x] 首次正式对局、比分与回放（2026-11-12 `nevaio-r3-v54`，13–11 负；公开回放已取证）
- [ ] 出生点卡住修复后的新对局验证：seat 7 不再出现“存活 + 满弹主武器 + 整回合 0 发射”
- [ ] 5 类非卡住 badcase 的修复与下一场验收（见 [11-12-economy-rotation-combat.md](11-12-economy-rotation-combat.md)）
- [x] v0.02 对局可观测性回填（2 场 / 40 回合；卡死/到点改善、交火未改善、回防启动改善但到位 0；见 [11-12-match-observability.md](11-12-match-observability.md)）
- [ ] 新增 dust2 T 侧卡死 badcase 的修复与验收（R13/R14/R15/R17/R19）
- [ ] A* + attackRoutes + sprint/战斗超时/plant zone 的新对局验证（见 [11-12-pathing-routes.md](11-12-pathing-routes.md)）
- [x] 推进点（Advance Holds）实现已随 v0.07 提交/激活；下一场正式对局的到点/预瞄回填仍待完成（见 [11-12-advance-holds.md](11-12-advance-holds.md)）
- [x] post-v0.03 修正已作为 v0.04 提交/激活（T pre-plant patrol 振荡、soft hazard、前进跳 / 台阶跳、`map_patches.py`）；待新对局验证（见 [11-12-pathing-routes.md](11-12-pathing-routes.md) 与 [11-12-mirage-spawn-jump.md](11-12-mirage-spawn-jump.md)）
- [ ] 开火距离分层的新对局验证：点射只打头、0.7 s / 1 s 两档节奏、近距扫射占比（见 [11-13-fire-range-bands.md](11-13-fire-range-bands.md)）
- [ ] 战斗稳定性回填：可见性闪烁期间不再移动/蹲起/换目标；出生点被队友堵住后 0.5 s 内侧移（见 [11-13-combat-stability.md](11-13-combat-stability.md)）
- [ ] CT 防守 peek loop 的新对局验证：未下包时按站位/瞄点轮看，遇敌暂停，下包后切回回防/拆包（见 [11-13-ct-defensive-peeks.md](11-13-ct-defensive-peeks.md)）
- [ ] Borgo/Molo/Nevaio 录制路线与 Dust2/Mirage CT 回防路线的正式对局验证（见 [11-13-pro-demo-routes.md](11-13-pro-demo-routes.md)）

> 官方指南中的源码行号仅用于核对语义，不是运行时依赖。不要从全知录像或训练导出重建观察。
