# 规范：职业 demo 轨迹从 Walklab review 到 agent 跟随

Status: **Mirage CT 手录路线和用户指定的 Mirage T demo 候选已注册到 agent，并随 `1114-v0.18` 提交（`main` v14 / `account2` v17 admission `passed` 并激活）；其他职业 demo 仍只供 Walklab review。实战通行性未验证。**
Date: 2026-11-14
Submission: [1114-v0.18](../submissions/1114-v0.18/README.md)
Related: [Walklab route intake](../../.agents/skills/walklab-routes/SKILL.md) · [职业 demo CT 回防](./11-13-pro-demo-routes.md) · [T 方多路线选择](./11-13-t-route-rotation.md) · [路径与控制](./11-12-pathing-routes.md)

## 1. 背景与边界

手工在 Walklab 录制的 `walklab-v2` JSON 同时包含世界坐标、视角、按键和鼠标增量。职业 demo 能提供选手实际走过的位置与视角，却不能可靠还原其原始 WASD、Shift、Space 和鼠标输入。两种来源可以共用**按位置与视角跟随**的运行时模型，不要求先把 demo 反推成一段能在 Walklab 物理引擎中逐键重演的输入。

本批 review 数据由 `scripts/pro_demo_walklab.py` 从 MOUZ NXT vs URSA match 2393178 的 Dust2/Mirage demo 生成，位于 `walklab/public/routes/dust2-pro.json` 和 `mirage-pro.json`。筛选窗口内选手不得死亡；开火、造成或受到伤害均允许。帧保存原始视角经坐标系转换后的 yaw/pitch，`keys: []`、`mouse: [0, 0]` 表示输入未知，**不表示选手没有移动、冲刺或转动鼠标**。来源 demo、选手、回合、tick 和 SHA-256 随轨迹保留。Walklab 的命名、重命名、回放和导出只用于人工 review；回放直接设置 pose，不执行地图碰撞或 agent 控制。

职业 demo 数据与用户手录路线是不同来源。Mirage CT 实战路线以用户手录 JSON 为准；职业 demo 仅在用户按 route ID 明确指定后才进入比赛候选，其他仍供 Walklab review。运行时对 map hash 做精确门控。

## 2. 转换链与决策

```text
职业 demo → 选取存活窗口、转换坐标/视角 → Walklab review JSON
          → 人工确认战术类别、起终点、预瞄与异常片段
          → 校验地图 ID/hash、编译位置/视角帧及必要的移动提示
          → 按阵营/目标/起点注册 agent 候选 → 实战轨迹对比
```

`walklab-routes` skill 的手录路径以 `scripts/build_r3_replays.py` 为参考：校验 `walklab-v2`、地图 ID/几何哈希、连续 tick、有限数值和 20 Hz，输出 `(x, y, z, yaw, pitch, key_mask)`；T 带包路线还需目标包点和距包点 12 m 的 `CARRIER_CUTOFF`。当前职业 demo review JSON 是 **16 Hz**，不能原样通过该编译器的 20 Hz 校验。接入时可以在保留时间语义的前提下重采样到 20 Hz，或实现明确支持 16 Hz 的 demo 编译路径；不得只把 `hz` 改成 20 或丢弃来源 tick 后假称等时重放。运行时按距离找目标帧和前瞻点，原始采样间隔不会自动成为移动速度命令。

`agent.py:follow_trajectory()` 根据**实时位置**寻找相邻轨迹帧，朝前瞻目标移动，并根据记录的 yaw/pitch 计算视角速率。录制的 WASD 方向只占移动方向的 30% 前馈，位置目标占 70%；鼠标 delta 不参与该控制。`ShiftLeft` 和 `Space` 分别提供 sprint 与 jump 提示。因此 demo 的空按键仍可作为位置/视角目标，但会失去这两种提示，不能据此声称复杂台阶和跳点可走。编译时只对确有证据的冲刺、跳跃片段添加提示，并记录推断依据；无法确定的片段应保留未知并进入实测核验。

## 3. 注册与验收

- 每条候选保留稳定名称、来源哈希、阵营、战术类别、起点和目标点；地图 ID/hash 必须匹配。T 进攻路线按目标包点注册，并保留带包者 12 m 截止、A* 下包及交火暂停/续走。CT 开局守点和回防按各自触发条件注册，不套用 T 带包规则。
- 编译检查帧序、坐标/视角有限值、起终点、相邻帧间距与朝向突变；抽样对照 demo 和 Walklab JSON，确认重采样没有改变路径和预瞄的关键节点。
- 在对应平台地图让 agent **实际移动**：逐帧记录位置、视角、卡住/跳跃/碰撞事件，与 demo 分段比较。重点检查台阶、门洞、掩体、跳点和预瞄偏差；遇敌暂停后还须检查能否回到路线。
- Walklab pose 回放、导航点距离、编译通过和无死亡筛选都只支持“可 review 的示范数据”结论。只有平台角色完成实走并通过逐段检查，才能把具体路线标为已验证可复刻；不同 CS2/平台地图构建版本仍需记录为误差来源。

职业 demo 仍是带名称和来源的 Walklab review 轨迹；Mirage CT 用户录制路线已完成编译与注册，但没有宣称已经实战验证。

## 4. 两段式组合（2026-11-14）

本批目录增加独立的守点片段：CT 到达 A/B/中路等区域后、下包前的存活窗口，以及 T 下包后在 A/B 附近的存活窗口。片段要求连续采样、停留在对应区域、存在实际移动或视角变化；每个类别最多保留两条。Dust2 的 CT 守 A、A 小、中门、B 与 T 守包 A/B 均有样本；Mirage 的 CT 守 A、连接、中路、B 与 T 守包 A/B 均有样本。每段继续保留 demo、选手、回合、tick 和视角。

组合不复制或拼接帧。`walklab-combination-v1` 清单引用两条原始 route ID：CT 为 `opening → hold`（同 `area`），T 为 `attack → postplant_hold`（同 `targetSite`）。只有守点片段首尾水平距离 ≤2.5 m 才作为循环候选；清单记录第一段终点到循环段起点的 `joinDistance`、循环首尾的 `loopClosureDistance` 与 `joinMode: live_navigation`。Walklab 的分段回放直接切换 pose，**不模拟两段之间的移动**，也不证明该循环可以在碰撞世界中闭合。

实战状态机为：CT 未下包时选择站位对应的守区路线，执行 `opening → hold loop`；循环用实时位置重新接向首帧，不重置角色位置。遇敌交由现有战斗逻辑；下包、死亡、回合/地图切换时退出。持续卡住时回退 A*/hold。T 的组合仍只在 Walklab review 中，尚未接入 agent。当前仅 Mirage CT 已按此逻辑注册。

## 5. Mirage CT 手录库（2026-11-14）

`recordings/mirage_ct/manifest.json` 显式定义 A/B 各三组开局与守点配对，以及两条 B→A 回防。原始 Walklab JSON 缺少 purpose/site metadata，因此清单是来源追溯和配对依据，不能由文件名自动分类。`scripts/build_mirage_ct_routes.py` 校验 Mirage 几何 hash、20 Hz、连续 tick、pose/key 合法性、开局到守点的 ≤0.2 m 接点及守点 loop 首尾 ≤1 m，并生成 `mirage_user_ct_routes.py`。Space 映射为跳跃提示；空按键守点仍可用位置/视角跟随。

Mirage CT `B_3` 的终点是靠近超市的 B 区二箱（约 `103.41, 49.26, 17.68`）。实战反馈表明当前碰撞下无法跳上去，因此比赛选路暂时排除 `B_3`（`MIRAGE_DISABLED_CT_PAIRS = frozenset({"B_3"})`，随 `1114-v0.19` 提交）；录制和编译数据保留供 Walklab review，B 点仍在 `B_1/B_2` 间轮换。重新启用需先在平台地图完成实际通行验证。

比赛 `439a8cec-6655-4993-987a-f7afddaffe9f` 第 14 回合（`round_index=13`）中，CT seat 5（网页第 6 个玩家）沿 `A_3` 去 jungle 时在约 `(58.86, 79.98, 15.63)` 停滞，对应录制帧约为 `(59.08, 80.96, 15.63)`；公开位置显示反复侧移，周围 3 m 无其他存活玩家。公开地图的 `collision` 只给三角网格文件描述符，agent 不能从观察直接射线查询左右墙。CT 开局以录制帧号的实际推进判断是否卡住，不能把横向抖动算作进展；卡住后根据轨迹切线与当前位置的偏移先试反方向斜前进约 0.4 s，再试另一侧，保持原录制视角。仍未推进则该回合放弃录制路线并转入通用寻路，避免下一帧重选同一路线。该恢复尚待新比赛实走验证；永久改写局部轨迹仍需成功绕过的实际位置轨迹与耗时对比。

职业 demo retake 不作为比赛候选。Mirage CT 下包回防只有用户录制的 B→A 两条候选；其他无匹配路线的情况使用既有寻路。脚本编译成功和 route 注册只证明数据接通，不能证明门洞、台阶、掩体碰撞或预瞄已通过实走验收。

## 6. 用户指定的 Mirage T 路线（2026-11-14）

`recordings/mirage_t/manifest.json` 按 route ID 精确选入 R4 ay0k（A 二楼）、R8 opdust（拱门夹 A）、R6 Flierax（A 大）、R14 karnez（B 小）、R13 Salazar（B 二楼），以及 R4 Flierax 的 A 守包片段。B 小从其 16 Hz 片段第 640 帧开始，即该片段起点后 40 秒；截取点仍在 T 出生区附近。`scripts/build_mirage_t_routes.py` 保留 16 Hz 位置/视角，不伪造键鼠输入，输出 `mirage_user_t_routes.py` 并保存 demo 目录和手录衔接段的 SHA-256。

B 二楼 demo 终点平面位置与 `recordings/mirage_t/b_apps_drop_handoff.json` 起点一致，高度相差约 2.7 m；后者是 20 Hz 手录跳下段。拼接只表示按顺序跟随，不证明角色能通过平台碰撞。非带包者到衔接段终点后原地保持末帧视角；带包者仍在距离 B 点 12 m 内切换 A* 寻路并下包。A 守包片段仅在观察到 A 点已下包后启动并循环。其余 demo 轨迹不进入赛场候选。

## 7. 录制路线爬升辅助（2026-11-14）

职业 demo 的 pitch 是视角，不是跳跃/攀爬输入。`follow_trajectory()` 在水平目标仍需前进，且前瞻轨迹点相对当前位置至少升高 0.1 m、升高量/水平距离达到 8% 时追加 jump 提示；例如 2.5 m 前瞻距离中上升约 0.2 m 会触发。原始 key mask 中显式的 Space 提示仍有效。平台碰撞不允许通过时，仍依赖卡住恢复/后续寻路；坡度阈值和跳跃节奏需要结合实际比赛日志继续调校。

公开回放 `545311d9-03e9-4c56-ae11-bec46d5d180c` 的第 3 回合（`round_index=2`）给出两个局部碰撞样本。T A 大路线在约 `(60.69, 110.31, 14.31)` 停滞，随后跃至 `z≈15.5` 才继续；CT 出门去 A 的 API seat 0（网页第 1 个玩家）在约 `(38.75, 65.01, 14.31)` 长时间停滞，seat 2（网页第 3 个玩家）也在约 `(39.12, 64.42, 14.31)` 反复停住/跃起。CT `A_1` 录制路线的中心线在该处约 `x=40.3`，因此仍保留实时位置纠偏。针对 T A 大及 CT A 开局路线在这些小范围坐标，跟随器会提前给出 jump 提示；运行时仅在落地、继续移动、且距上次跳跃至少 24 match ticks 时发一个跳跃脉冲。CT 在这个坡面最多多等三次跳跃冷却，随后仍回退寻路。公开 replay 不含私有动作，故这些坐标和跳跃前后的位移是碰撞现象的证据，不是原 agent 按键的直接记录。
