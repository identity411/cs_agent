# CT 防守 peek loop

Status: **已随 `1113-v0.15` 提交，`main` v11 / `account2` v14 admission `passed` 并激活；本地 105/105 unittest 通过；待新对局验证**
Date: 2026-11-13
Submission: [1113-v0.15](../submissions/1113-v0.15/README.md)

CT 在炸弹未下包、没有可见敌人且到达包点附近时，使用固定站位和离散瞄点循环：

| 地图 | 包点 | 循环 |
| --- | --- | --- |
| Mirage | A | A boxes：A ramp / palace → jungle / connector |
| Mirage | B | B short cover：market → apartments / short |
| Dust2 | A | A back cover：long A → short / cat |
| Dust2 | B | B back cover：tunnels → upper / short |

每个瞄点默认停留约 2.8 秒。瞄点切换期间站位保持不动；如果定义了多个站位，会在该站位的瞄点完成后移动到下一个站位，再从第一个瞄点开始。发现敌人时暂停循环并进入战斗逻辑，目标消失后继续当前瞄点。

这些点使用本地静态地图导航节点和已有职业 demo 的包点附近 CT 站位/视角片段整理而成。demo 里的视角会受交火、投掷物和队友遮挡影响，因此这里保留的是稳定的入口检查顺序，不是逐 tick 的录制回放。正式对局仍需检查碰撞和视线。

实现：`advance_holds.DefendHold`、`agent.py:defend_hold_target()`。
