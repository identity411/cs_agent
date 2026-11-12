# 规范：推进点（Advance Holds）——寻路之后的“跑—停—打—跑”与预瞄角

Status: **2026-11-12 定义；未实现，v0.05 候选。样本为 1 场 / 24 回合（`da110811` 的 seat 3，网页 Seat 4），需下一场 nevaio 对局回填**
Date: 2026-11-12
Related specs: [11-12-pathing-routes.md](./11-12-pathing-routes.md)（上游：A* / attackRoutes）· [11-12-match-observability.md](./11-12-match-observability.md)（验收口径）· [11-12-stuck-at-spawn.md](./11-12-stuck-at-spawn.md)（反例）· [11-12-site-center-hold.md](./11-12-site-center-hold.md)（到点后行为）· [maps.md](./maps.md)（nav / yaw 约定）· [agent-interface.md](./agent-interface.md)（动作字段）

## 0. 目标与非目标

**目标**：A* 和 `attackRoutes` 只回答“从出生点走到包点”；本规范回答**沿路怎么推进**：

1. 在哪些点停；
2. 停的时候准星压哪条线（预瞄角 / 预瞄点）；
3. 什么时候继续走；
4. 看到敌人时如何先刹停再开火。

**非目标**：

- 不替代 A*、`attackRoutes`、`map_patches.py`；推进点是**寻路之后**的控制层。
- 不复制取证对象的卡死/被动问题；反例见 §8。
- 不把公开回放当作私有决策轨迹；本规范只使用公开帧 / 公开事件能观测到的行为。

## 1. 取证来源与结论

| 项 | 值 |
| --- | --- |
| 对局 | `da110811-9f35-4c86-9492-b322b1302391`（`nevaio-r3-v54`，24 回合，team 0 13–11 胜） |
| 对象 | 数据 **seat 3** = 网页 **Seat 4**（viewer 为 1-based），team 0，T 方起始 |
| 数据 | 61,278 帧 public_frames（24 Hz）+ 5,553 条 public_events |
| 回放 | `https://agx.cool/#/jobs/da110811-9f35-4c86-9492-b322b1302391` |

该 seat 的可观测行为（仅作参考上限，不作为目标值）：

- 127 发 / 76 中（59.8%）/ 24 杀 13 死 / 3208 伤害；爆头 14/76（18.4%，全场最高）。
- **walk=0%**，活跃回合平均速度 4.5–5.5 m/s。
- 站定开枪 81 发、76.5% 命中；全速跑动开枪 40 发、17.5% 命中；62/76 个命中（约 82%）来自站定。
- 82% 的交火在开第一枪时速度 <1 m/s；从 5.5 m/s 刹到 0 约 0.1–0.2 s。
- 54% 的交火在开火前 0.5 s 内 yaw 漂移 ≤3°；59% 的敌人在开火前 0.5 s 已在准星 ±5° 内。
- T 方 A 大路线 28–34 s 到 A；R2/R4/R5/R6/R11 五个回合逐点重复同一路线，outpost/outpost_e 的预瞄角稳定在 -30°/-43°，最后一跳在 -66°～-82°。

## 2. 数据模型

推进点属于“地图数据”，不写进 `agent.py` 核心里。建议新增根目录 `advance_holds.py`（与 `map_patches.py` 同级、同样只返回抽象数据），或把 `advance_holds` 字段并入 `map_patches.MapPatch`。**推荐独立模块**，因为它是路线/战术数据，不是地图修补。

```python
AdvancePoint = {
    "node": "outpost",          # nav 节点 id；用于到达判定
    "stop": (66.0, 111.7),      # 可选：实测停点；缺省用 node 坐标
    "aim": (123.0, 77.8),       # 必填：定义预瞄线的远点（xy）
    "aim_z": 1.64,              # 可选：预瞄高度；缺省按敌方头部 1.64 m
    "hold": 0.0,                # 无敌人时停留秒数；0 = 到点即继续
    "walk_in": False,           # 只在最后进场/守点时走
    "role": "advance",          # advance | anchor | utility
    "note": "A 大 P1，60–66 m",
}

AdvanceLane = {
    "map_id": "nevaio-r3-v54",
    "side": "attack",           # attack | defend
    "site": "A",
    "name": "A_long",           # 与 attackRoutes 的 key 对齐时可复用
    "points": [AdvancePoint, ...],
}

AdvanceMap = {
    "map_id": "nevaio-r3-v54",
    "lanes": {                  # key = (side, site, name)
        ("attack", "A", "A_long"): AdvanceLane,
        ...
    },
}
```

**约定**：

- `aim` 存**世界坐标**，不存 yaw。运行时用 `atan2(-(aim_y - y), aim_x - x)` 得到引擎 yaw；引擎 yaw 与世界 yaw 符号相反（`maps.md`：正 yaw 面向 `(cos yaw, -sin yaw)`）。
- `aim_z` 缺省时按“敌方脚底 + 1.64 m 头部”计算；在 A 平台（脚底 2.4）守地面通道时，这自然得到约 **-2°** 的俯角，不需要硬编码 pitch。
- 所有数据必须绑定 `map_id` 与 `static_schema_hash`；地图变化时整组失效（与 `attackRoutes` 同口径）。

### 2.1 路线选择优先级

1. `map.bot_waypoints.attackRoutes`（官方地图数据）优先；
2. 没有官方 lane 的地图（nevaio / borgo / molo）使用 `advance_holds` 的 lane；
3. 两者都没有时回退到现有 A* 直达 site center，不应用推进点。

推进点只在所选 lane 的节点命中时生效；A* 临时绕路时不强行使用。

## 3. 控制状态机

在 `act()` 的目标/战斗判定之后、`move()` 之前插入推进层：

```text
RUN    沿当前 lane 跑向下一推进点；进入 PREAIM_DISTANCE 后 yaw 锁到 aim
  │  看到敌人
  ▼
BRAKE  零移动输入，速度降到 < STOP_SPEED（1.0 m/s）
  │  速度达标且瞄准对齐
  ▼
ENGAGE 现有 combat()：点射/短点；不前进、不走、不蹲（默认）
  │  敌人消失 / 超时
  ▼
RESUME 继续下一个推进点（不回到上一个点）
```

无敌人时：

```text
RUN → 到点（距离 < STOP_RADIUS）
    → hold > 0（anchor / crossing）：保持 aim，hold 秒后继续
    → hold = 0（普通 advance）：不停留，直接 RUN 下一个点
```

优先级（从高到低）：**目标动作（plant / defuse）> 可见敌人 > 到达推进点后的 hold > 沿路 RUN**。目标动作和战斗沿用现有实现；本规范只新增 RUN/BRAKE/HOLD 的预瞄与刹停逻辑。

### 3.1 RUN：跑，但准星压线

- `walk=False`；`sprint` 仅在距离 > `SPRINT_DISTANCE` 且有体力时使用（现有逻辑保留）。
- 与 waypoint 的距离进入 `PREAIM_DISTANCE`（建议 20 m）后，yaw 目标从“路径方向”切换为 `aim` 方向。
- 移动输入按**路径方向相对当前 yaw**分解，允许侧身/倒退跑：

```python
path_dir = math.atan2(-(wp_y - y), wp_x - x)
delta = angle(path_dir - me["yaw"])
move_forward = math.cos(delta)          # 允许 <0 时先转身
move_right = -math.sin(delta)
aim_dir = math.atan2(-(aim_y - y), aim_x - x)
yaw_rate = clip(angle(aim_dir - me["yaw"]) / 0.15)
```

- 如果 `abs(delta) > 2π/3`（waypoint 在身后），先按路径方向转身，暂停预瞄，避免倒着跑进墙。
- 参考对象的中位 yaw-速度夹角是 22°，不是 90° 纯横移；如果引擎对 `move_right` 有速度惩罚，优先用 `move_forward` 保持速度，把预瞄角控制在 45° 以内，超过时先转身再继续预瞄。

### 3.2 BRAKE：见到敌人先刹停

- `move_forward=0`、`move_right=0`（引擎摩擦会在大约 0.1–0.2 s 内把速度降到 <1 m/s）。
- 保持 yaw/pitch 追敌；`speed > STOP_SPEED` 时 `fire=False`，即使准星已对齐。
- 这样站定开枪的命中率才接近参考值（76.5%），而不是跑动开枪的 17.5%。

### 3.3 HOLD：到点后的固定角

- **普通 advance 点 `hold=0`**：参考对象不在推进点等待；它是跑到点上、看见敌人才刹停开火，打完立刻继续（R5 的三个点都是这样）。所以推进点的“停”由 BRAKE 触发，不是由 `hold` 触发。
- `hold` 只对 `role="anchor"` 或显式标注的 crossing 点使用；anchor 的参考停留是 5–10 s。**不要**照抄参考对象 68–96 s 的整回合架点（会造成 0 影响回合，见 §8）。
- anchor 每隔 `REPEEK_TICKS`（建议 5 s）在两个预瞄点之间切换一次，或按兵线/炸弹状态重选，避免一直盯死一条线。
- 如果实现上需要一个“到位后扫一眼”的动作，crossing 点最多给 0.5–1 s，不要变成站桩。

## 4. Nevaio 推进点表（本规范的核心数据）

以下 `stop` / `aim` / yaw 均为实测（世界系 yaw 由 `atan2(dy, dx)` 计算；引擎 yaw 取反）。时间来自 2 s 采样的路线序列，仅作参考。表中 `aim` 的第三列只标注该线所在层高，用于估算 pitch；运行时仍按 `aim_z`（缺省为敌方头部 1.64 m）计算。

### 4.1 T 方 A 大（`A_long`，R2/R4/R5/R6/R11）

| # | node | stop（参考） | aim | 预瞄 world yaw | pitch | 参考到达 | hold |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | `ts` | (20,110,0) | — | 出生朝向 | 0 | 0 s | 0 |
| 2 | `wind_gate` | (20,122,0) | — | — | 0 | 2 s | 0 |
| 3 | `specimen` | (42,110,0) | — | — | 0 | 6 s | 0 |
| 4 | `wind_wall` | (66,122,0) | — | — | 0 | 8 s | 0 |
| 5 | `outpost` | (66.0,111.7,1.2) | (123.0,77.8,1.2) | **-30.8°** | 0 | 12 s | 0（见敌才停） |
| 6 | `outpost_e` | (92.4,108.0,1.2) | (123.0,79.3,1.2) | **-43.2°** | 0 | 18 s | 0（见敌才停） |
| 7 | `observation` | (98.4,89.7,2.4) | (123.0,34.3,0) | **-66.1°** | **约 -2.3°** | 22 s | 0（见敌才停） |
| 8 | `A` | (112,90,2.4) | site center | 随目标 | — | 28–34 s | — |

要点：

- 以 R5 为例，三个停点的 yaw 从 **-30.8° → -43.2° → -66.1°** 逐段贴近 A 点，不是随机扫视；这是“每一段路一个固定角”的核心。R2/R4 在最后一跳会转到 -75°～-82°（仍在同一条 A 大走廊）。
- 参考对象**不在推进点等待**：18.6 s 在 outpost 2 发、24.4 s 在 outpost_e 2 发拿 1 杀、29.8 s 到 observation 打 7 发拿 2 杀；每个点开火前 0.5 s 速度仍是 5.5 m/s，看到敌人才刹停。所以数据里的 `hold` 是 0，停火由 BRAKE 负责。
- 到达 A 的 28–34 s 是“跑 + 停 + 打”的节奏；同样从 T 出生点到 A，我们 v0.01 的 seat 7 因为全程 walk 需要 60 s 甚至到不了。

### 4.2 T 方中门（`A_mid`，R0/R10，样本少）

| node | stop（参考） | aim | 预瞄 world yaw | 参考 |
| --- | --- | --- | --- | --- |
| `specimen_s` | (42.4,88.7,0) | (66.7,87.3,1.2) | **-3.4°** | R0 18.0 s，1 发 |
| `mid` | (63.1,84.0,1.2) | (128.0,91.5,2.4) | **6.6°** | R0 22.3 s，13 发 5 中 |
| `clean_e` 西侧 | (98.8,66.3,2.4) | (123.0,75.4,1.2) | **20.8°** | R0 34.2 s，2 发 2 中；实测点离 `clean_e`(112,66) 约 13 m |
| `A` | (112,90,2.4) | site center | — | R0 38.1 s 到 A |

中门样本只有 2 个回合，且 R0 后半段有绕路；先按“参考”使用，等第二场回填。

### 4.3 T 方 B 线（`B_drill`，R3/R10）

| node | stop（参考） | aim | 预瞄 world yaw | 参考 |
| --- | --- | --- | --- | --- |
| `maintenance` | (64,52,1.2) | — | — | R3 16 s 经过 |
| `maintenance_e` | (76,52,0) | — | — | R3 20 s |
| `drill_e` | (76,40.6,0) | (123.0,58.8,0) | **21.2°** | R10 29.1 s，5 发 2 中 1 杀 |
| `drill_entry` | (55.9,33.9,0) | (42.4,8.0,0) | **-117.5°** | R0 55.3 s，1 发 1 杀 |
| `B` | (52,26,0) | site center | — | R3 31.4 s 到 B |

### 4.4 CT 方 A 锚点（`A_anchor`，R13/R15/R16/R18/R23）

| node | stop（参考） | aim | 预瞄 world yaw | pitch | 参考到达 | hold（建议） |
| --- | --- | --- | --- | --- | --- | --- |
| `ct` | (118,18,0) | — | — | 0 | 0 s | 0 |
| `rear_corner` | (118,22,0) | — | — | 0 | 2 s | 0 |
| `front_drop` | (112,58,0) | — | — | 0 | 6 s | 0 |
| `equipment` | (118,66,0) | — | — | 0 | 10 s | 0 |
| `equipment_n` | (118,89.9,2.4) | (40.0,127.0,0) | **154.3–155.1°** | **约 -2.4°** | 12 s | 5–10 s（参考 8.4 s） |
| `A` | (112.8,92.5,2.4) | (40.0,127.0,0) | **154.9°** | **约 -2.4°** | 14 s | 5–10 s（参考从 A 平台/A 点射击） |

备选守点（同一 A 区，按敌人来向切换）：

| node | aim | 预瞄 world yaw | pitch | 说明 |
| --- | --- | --- | --- | --- |
| `front_ladder_top` | (82.6,118.0,1.2) | **117.3°** | 约 -1.8° | 守 outpost/observation 交叉；两段交火相隔 31 s 仍是 117° |
| `front_ladder_base` | (112.1,100.0,2.4) | **89.8°** | 约 +0.4° | 守 A 点横线，39.5 m |

> **注意**：`front_ladder_base → front_ladder_top` 的爬梯路径在参考对象上连续 3 个回合卡死（见 §8）。`front_ladder_base` 只作为**平地守点**使用；不要生成跨 `front_drop → front_ladder_*` 的爬梯路径。

### 4.5 CT 方 B 锚点（`B_anchor`，R18/R20/R22）

| node | aim | 预瞄 world yaw | pitch | 说明 |
| --- | --- | --- | --- | --- |
| `warm_hall` | — | — | 0 | 从 CT 出生点出发 |
| `warm_gate` | — | — | 0 | |
| `B` | site center | — | — | 先到 B/后点 |
| `drill_entry` | (18.0,47.7,0) | **162.6°** | 约 -0.6° | B 口长线；参考 R18 停 68 s |

### 4.6 道具配合（不是推进点的替代）

参考对象在“不看的线”上丢道具：

- R4（T）：烟封 CT（118,65.6），燃烧瓶清 A 点（109.9,92.1），然后下包。
- R17（CT）：燃烧弹 + 烟都落在 observation（95.5,90.2），封 T 的 A 观察位。
- R20/R22（CT）：燃烧弹 + 烟落在 B 入口（26–28,26），再转 A。

建议：推进点到达后，如果本回合还有对应投掷物且该线不是本点视线，按 `utility` 子类型丢一次；不要让道具占用推进时间。

## 5. 与现有实现的接入点

| 位置 | 改动 |
| --- | --- |
| 新模块 `advance_holds.py` | `for_map(map_id)` 返回 `AdvanceMap`；数据表见 §4；未知地图返回空。 |
| `Player.__init__` | 增加 `self.advance_lane`、`self.advance_index`、`self.hold_until`、`self.preaim`。 |
| `load_map()` | 读取 `advance_holds.for_map(row.get("id"))`；校验 `static_schema_hash`；地图变化时与 `attackRoutes` 一起清空。 |
| `route_lane_points()` | 保持官方 `attackRoutes` 优先级；没有官方 lane 时，从 `advance_holds` 取同一 `(side, site, name)` 的 lane。 |
| `act()`（无敌人分支） | 在 `move()` 前选择当前推进点；到点且 `hold>0` 时返回 hold 动作（`move_forward=0, move_right=0, walk=False`，yaw/pitch 保持 aim）；hold 结束再 `move()`。 |
| `move()` | 预瞄时把 yaw 目标从 path 方向改为 aim 方向；移动输入按 `delta = path_dir - me["yaw"]` 分解（§3.1）；`walk=not sprint` 改为默认 `walk=False`，只在 `walk_in`/hold 时 `walk=True`。 |
| `combat()` | 见敌且 `speed > STOP_SPEED` 时先零移动输入、`fire=False`；速度达标后再进入现有对齐/开火。默认不蹲。 |

**为什么 `walk` 要改**：`move()` 目前是 `walk=not sprint`，非 sprint 段默认走路（约 1.8 m/s）；参考对象是 `walk=False` 的 5.5 m/s 默认跑。推进点数据再准，走路也会把 28–34 s 的到点时间拖到 60 s 以上。

**为什么 yaw 要单独锁**：`move()` 现在让 yaw 追 waypoint；推进点要求“人是跑着、准星压在线上”。yaw 和移动方向分离后，才能复现参考对象 22° 中位 yaw-速度夹角和 79% 跑动时间角速度 <10°/s 的行为。

## 6. 默认参数

| 参数 | 建议值 | 依据 |
| --- | --- | --- |
| `PREAIM_DISTANCE` | 20 m | 进入该距离后锁 aim；参考在 outpost 前已压 -30° |
| `STOP_SPEED` | 1.0 m/s | 站定命中率 76.5% vs 跑动 17.5% |
| `STOP_RADIUS` | 3.0 m | 现有 `WAYPOINT_RADIUS` 2.0 m 的略宽版本 |
| `HOLD_ADVANCE` | 0 s | 参考每个推进点打 1–7 发即走，不停留 |
| `HOLD_CROSS` | 0.5–1 s（可选） | observation / front_ladder_top 这类交叉口；参考对象实际也是见敌才停 |
| `HOLD_ANCHOR` | 5–10 s | 不要照抄 68–96 s |
| `REPEEK_TICKS` | 5 s | anchor 在两预瞄点/两条线之间切换 |
| `TAP` | 1–4 发/组 | 参考 burst 中位数 1 |
| `PREAIM_TOL` | ±3° | 54% 交火在开火前 0.5 s 漂移 ≤3° |
| `HEAD` | 1.64 m | 与现有 `combat()` 的 `heights["head"]` 一致 |
| `EYE` | 1.62 m | 与现有 `combat()` 一致 |
| `SEN_ENEMY_REACTION` | ≤0.35 s | 参考 0.27 s（15° 锥代理口径） |

## 7. 验收指标

优先用现有 `agx_observe.py` + `frames`；新增指标建议：

| 指标 | 目标 | 参考 |
| --- | --- | --- |
| T A 大到点时间 | ≥70% 回合 ≤35 s | 参考 28–34 s；v0.01 seat 7 60 s/到不了 |
| 推进段跑动占比 | ≥70% live 时间 speed>4 | 参考 95–100% 移动、4.5–5.5 m/s |
| 站定开火占比 | ≥60% | 参考 63.8% <1 m/s；越高越好 |
| 站定命中率 | ≥60% | 参考 76.5% |
| 跑动开火占比 | ≤20% | 参考 31.5%，且仅 17.5% 命中 |
| 预瞄漂移 ≤3° 的交火占比 | ≥50% | 参考 54% |
| 敌进 15° 锥 → 开火 | ≤0.35 s | 参考 0.27 s |
| 卡死 | 不新增 >10 s 的 spawn/ladder/corner 卡死 | 参考对象有 3 个 T 回合整回合卡死，**不可接受** |
| 0 发射回合 | ≤25% | 参考 33%（8/24，部分因卡死） |

验收时按 [11-12-match-observability.md](./11-12-match-observability.md) 的规则逐回合标注；A/B 到点、卡死、回防分开统计。

## 8. 反例：这个对象不能照抄的部分

- **出生点卡死**：R7/R8/R9 在 T 出生点（x≈18.4, y=110）速度 5+ 但整回合位移 <0.4 m；R12/R21 在 CT 出生点；R19 在 `rear_corner(118,23.5)`；R17 在 `equipment(117.6,75.7)`。这正是 [11-12-stuck-at-spawn.md](./11-12-stuck-at-spawn.md) 的现象。
- **爬梯卡死**：R14/R20/R22 在 `front_ladder_base(112,60.6)`，z 在 0↔0.44 循环、pitch≈72° 盯梯子，持续 57–70 s。**不要把这条爬梯路线写进推进 lane**；`front_ladder_base` 只作平地守点。
- **整回合架点**：R16 在 `front_ladder_top` 停 96 s、R18 在 `drill_entry` 停 68 s；如果敌人不来就是 0 影响回合。推进点必须带 `hold` 上限和 `REPEEK`。
- **跑动开枪**：40 发全速射击只有 17.5% 命中；推进层必须先 BRAKE 再 ENGAGE。
- **数据不要硬编码**：所有坐标/角度绑定 `map_id` + `static_schema_hash`；地图更新时整组失效。

## 9. 复现与数据来源

```sh
# 帧 + 事件（只读公开回放）
python3 .claude/skills/agx-match-query/scripts/agx_matches.py frames \
  --match-id da110811-9f35-4c86-9492-b322b1302391 --seat 3 --round 5 --every 5
python3 .claude/skills/agx-match-query/scripts/agx_matches.py events \
  --match-id da110811-9f35-4c86-9492-b322b1302391 --seat 3
```

本文数据是公开投影：`public_frames` 的 x/y/z/yaw/pitch/speed/weapon 与 `public_events` 的 fire/hit/kill；不包含私有决策轨迹。席位映射：viewer 的 `Seat {n}` = 数据 `seat n-1`。

## 10. 变更记录 / 待办

### 2026-11-12

- 创建规范。取证自 `da110811` 的 seat 3（网页 Seat 4），24 回合 / 61,278 帧。
- 定义推进点数据模型、RUN/BRAKE/HOLD 状态机、nevaio 五条 lane 的参考数据与验收指标。
- 未实现；建议作为 v0.05 的寻路下游层，先做 `advance_holds.py` + `move()` 预瞄 + `combat()` 刹停三件事。

待办：

- [ ] 实现 `advance_holds.py` 与 nevaio 五条 lane 数据。
- [ ] `move()` 默认 `walk=False`，预瞄 yaw 与移动方向解耦。
- [ ] `combat()` 增加 `STOP_SPEED` 刹停门。
- [ ] 单元测试：预瞄 yaw 符号、A 平台俯角、hold 后继续、见敌刹停。
- [ ] 下一场 nevaio 对局回填到点时间/跑动占比/站定命中率/卡死。
- [ ] 评估 `bot_waypoints.attackRoutes` 与本地 lane 的优先级是否需要按地图配置。
