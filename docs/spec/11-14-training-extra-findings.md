# 本人决策日志追加排查：掉包识别与恢复接路

日期：2026-11-14。使用 `agx-training-debug`，沿用 [CT 静止尾段取证](11-14-ct-idle-handoff.md) 的对局、账号、冻结版本和数据边界。

对局 `5203e37d-f663-44db-9bfc-3580bb63cb8d`，main v17 / `1114-v0.21`，himesena，seat 3（0-based）= 网页第 4 个玩家、team 0，Mirage。使用已收到的 37,564 条完整决策；HTTP/1.1 再下载仍断开，未取得 `export_complete`，以下不是全局完整导出统计。

冻结 agent.py 按原观察顺序重放，原始 action 的显式字段在 1e-9 数值容差内全部吻合；所有这些决策 `fault=false`，action 显式字段与 applied_action 均一致。因此以下是策略逻辑问题，未观察到平台拒绝或更改这些动作。

## 1. 实际掉包状态 world 未触发恢复（已本地修复）

第 13 回合，tick 67863 首次出现合法 `bomb.state="world"`、`carrier=null` 和明确 position。角色未携包、当时没有可见敌人。直至 tick 73308，存活 live 决策中共 1788 条有这一状态（20 Hz 决策约合 89.4 秒，非连续时间跨度统计）。

旧代码只匹配 `state == "dropped"`。已有恢复测试也全部用自造的 dropped 字段，因此尽管测试通过，正式日志的 world 状态不会触发恢复，角色继续执行原进攻计划。该回合公开事件结果为 timeout。

修复接受 `(world, dropped)`，仍要求 T、未携包、有合法 position。没有位置和 CT 的边界保持不触发。用冻结状态在 tick 67863 分叉执行修复版本，确认 `bomb_recovery_started=True`、导航目标等于日志给出的炸弹位置。这里只证明决策目标修正，不保证最终可达或拾取成功。

## 2. 放弃后恢复路线绕过 A* 接路超时（已本地修复）

第 17 回合，A_main_R6_Flierax 路线曾在 tick 99225 触发正常接路超时并放弃；脱离后又重新恢复。tick 100173 至 103707 的 1179 条存活 live 决策一直保持 `replay_rejoin_index=316`，约 59 秒，位置反复停在 `(68.906,129.594)` 附近。预期重接帧为 `(67.2809,120.331,17.2322)`。

原因：旧恢复分支直接 `return self.move(...)`，发生在 `follow_attack_link()` 之前，既不进入其 8 秒超时，也不会运行后面的轨迹游标看门狗。`link.entered` 还保持 True。初始接路的超时本身有效，恢复接路却走了另一套无超时分支。

修复将待恢复帧交给 `_start_attack_rejoin()`，清掉旧标志，再由 `follow_attack_link()` 管理 A*、进入与超时。不会修改 A* 搜索算法。用 tick 100176 的冻结决策前状态分叉，确认修复后 `link.entered=False`、`started_tick=100176`，进入有超时的接路流程。回归测试在位置不动的情况下推进 480 tick，确认放弃接路而非无限重试。

## 3. CT 偏离录制路线后的精确重接（下一项实走重点）

第 6、10 回合 A_1 都在 cursor 112 附近放弃，tick 分别为 28989 / 50199，位置约 `(43.333,72.638,15.530)`；录制当前帧是 `(40.4848,72.1403,15.7328)`，水平差约 2.9 m。两次都没有可见敌人，放弃时游标看门狗已累计 69 ticks。

CT follower 在偏离超过 6 m 时才回退 A*；0.8–6 m 的偏离仍直接按录制前视点纠偏。T follower 已有更小偏离触发精确重接的逻辑，CT 没有同样的过程。该差异与重复坏例值得优先实走验证，但公开观察不足以区分墙体、动态队友阻挡和三维台阶，暂不把调整阈值当作已验证修复。

## 验证与复现

两个新增回归分别先失败，再修复通过；完整 unittest 共 207 项，6 skipped，其余通过。上述改动已随 `1114-v0.22` 提交并激活（main v18 / account2 v21，code hash `b2f874a6d0df`）；当前全量测试 219 通过、6 skipped。没有模拟修复后的反事实物理轨迹。

原始片段、紧凑统计和复现脚本在 gitignored 的 `data/analysis/5203e37d-f663-44db-9bfc-3580bb63cb8d/main/`：`verify_extra.py`、`extra-findings.json`、`extra-abandons.json`、`extra-round-stats.json`。从仓库根运行该脚本即可重新核对冻结动作和两个修复分叉的状态；需保留该目录的本人日志。
