# 规范：当前启用的录制轨迹清单

Status: **截至 `1114-v0.21`（`main` v17 / `account2` v20），并包含工作区尚未提交的 Dust2 中门夹 B 路线与 B 车位守包（待提交版本）。本文只盘点 `agent.act()` 实际可达的轨迹；编译存在但未接入的候选单独标注。**
Date: 2026-11-14
Submission: [1114-v0.21](../submissions/1114-v0.21/README.md)
Related: [轨迹链接器](./11-14-route-linker.md) · [T 路线轮换](./11-13-t-route-rotation.md) · [录制回放卡死修复](./11-14-replay-follow-wedge.md) · [Dust2 CT 车位路线](./11-14-dust2-ct-car-routes.md) · [Mirage CT/T 用户路线](./11-14-pro-demo-walklab-pipeline.md) · [职业 demo 回防](./11-13-pro-demo-routes.md)

## 0. 结论

- 五张图都有 T 进攻录制轨迹；Dust2 三条、Mirage 六条（五条用户 T + 一条 legacy），Borgo/Molo/Nevaio 各一条。
- CT 「走位 opening + 守位 hold」用户路线只在 Dust2 与 Mirage 启用。
- CT 回防轨迹只有 Mirage B→A 两条；Dust2 下包后仍走 A*。
- `pro_retakes.py` 里编译了 Dust2/Mirage 的职业 demo 回防，但 `agent.act()` 没有调用点（只有 `agent.pro_retake_routes()` 定义和测试），**当前不生效**。
- 所有轨迹都以「地图 ID + 静态几何哈希」精确门控；不匹配时回退原有 A*，不会跨图误用。

## 1. 启用判定与优先级

| 阶段 | 触发条件 | 选择函数 | 轨迹来源 |
| --- | --- | --- | --- |
| T 进攻（未下包） | `side == attack`、未下包、未掉包恢复 | `_select_recorded_route()` | `recorded_route_options()` |
| T 守包（已下包） | `side == attack`、已下包、目标包点有录制 hold | `follow_t_postplant()` | `user_t_routes()` |
| CT 防守（未下包） | `side == defend`、未下包、本轮未放弃 | `choose_ct_recorded()` → `follow_ct_recorded()` | `user_ct_routes()` |
| CT 回防（已下包） | `side == defend`、已下包、目标包点为 A/B | `choose_retake()` → `follow_retake()` | `user_ct_routes()` 的 `RETAKES` |

优先级：

```text
CT 防守：录制 pair（opening → hold） > advance_holds 的 defend_hold / anchor
CT 回防：用户录制回防 > A* 直奔炸弹（pro demo 回防当前不参与）
T 进攻：按权重选中的录制轨迹 > A*
```

地图 ID/哈希、阵营、包点任一不匹配时不注册该候选；未知地图保持原有 A* 行为。

## 2. T 进攻轨迹

帧格式 `(x, y, z, yaw, pitch, key_mask)`。`legacy` 是该图在 `recorded_route_info()` 中注册的默认轨迹；`site=None` 表示不限制包点，任何进攻回合都可能被选中。

### 2.1 Dust2（`dust2-cs2-v54`，hash `b0c30852…`）

| 名称 | site | 帧数 | carrier cutoff | 来源 |
| --- | --- | ---: | ---: | --- |
| `legacy` | 不限 | 2002 | 2001（到末帧） | `dust2_replay.py`（源 SHA `57473976…`） |
| `B_site_20261113` | B | 706 | 588 | `dust2_b_replay.py`（源 SHA `26f11dc3…`） |
| `B_mid_doors_20261114` | B | 720 | 719（`route_end`） | `dust2_user_t_routes.py`（中门夹 B，源 SHA `37c08ecd…`） |

- 选 A 时只有 `legacy`；选 B 时三条参与权重轮换。
- `legacy` 没有真实带包截止点（cutoff 在末帧），带包者会跟完整条路线；`B_site_20261113` 在距 B 包点 ≤12 m 的第 588 帧交给 A* 下包。
- `B_mid_doors_20261114` 最近只到距 B 包点中心 12.66 m（终点 15.84 m），因此 cutoff 取末帧、`carrier_cutoff_kind = "route_end"`：带包者跟完整条路线后由 A* 完成下包。

### 2.2 Mirage（`mirage-cs2-v54`，hash `ef93849…`）

| 名称 | site | 帧数 | carrier cutoff | 备注 |
| --- | --- | ---: | ---: | --- |
| `legacy` | 不限 | 1410 | 1409（到末帧） | `mirage_replay.py`，源 SHA `4623aad2…` |
| `A_palace_R4_ay0k` | A | 466 | 459 | 用户 T demo |
| `A_connector_R8_opdust` | A | 480 | 474 | 用户 T demo |
| `A_main_R6_Flierax` | A | 549 | 540 | 用户 T demo |
| `B_short_R14_karnez` | B | 786 | 774 | 源轨迹从第 640 帧起截取 |
| `B_apps_R13_Salazar` | B | 469 | 256 | `terminal_hold=True`；第 267 帧拼接 Walklab 续段 |

- 选 A 时 4 条候选（`legacy` + 3 条 A）；选 B 时 3 条（`legacy` + 2 条 B）。
- 只有 `B_apps_R13_Salazar` 在路线末段保留“守包”参数：`terminal_hold=True` 时到达末帧后原地保持录制视角，不再回 A*。

### 2.3 Borgo / Molo / Nevaio

| 地图 | 名称 | site | 帧数 | carrier cutoff | 来源 |
| --- | --- | --- | ---: | ---: | --- |
| `borgo-r3-v54` | `legacy` | A | 1113 | 1006 | `borgo_replay.py`，源 SHA `e39e134e…` |
| `molo-r3-v54` | `legacy` | B | 1345 | 1210 | `molo_replay.py`，源 SHA `a8431127…` |
| `nevaio-r3-v54` | `legacy` | A | 803 | 703 | `nevaio_replay.py`，源 SHA `bb935ebf…` |

这三张图的轨迹自带固定包点，`choose_site()` 会通过 `recorded_site()` 直接把包点定到轨迹的 site，因此每回合只有这一条候选。

### 2.4 选择与执行规则

- **站点过滤**：候选 `site ∈ (None, 当前选点)`；`None` 匹配任意包点。
- **权重轮换**（`ROUTE_WEIGHT_*`）：成功 → 权重 +0.5（上限 1.0）并保持；在路线上死亡且本队该回合未得分 → ×0.5；整回合存活但未完成且被判定停滞 → ×0.5。最低 0.1。
- **平票时的确定性**：保留上一回合仍在跑的路线；失败后从候选环里的下一条开始；无历史时按距离 + `(round_index + 1) % n` 打破平局。
- **入口**：`ATTACK_ENTRY_POLICY = "first"`、`ATTACK_ENTRY_RADIUS = 0.6 m`。先用 A* 走到 `frames[0]`，不允许就近切中段；起点不可达时才退化为最近可达帧。
- **带包**：轨迹在 `carrier_cutoff + 1` 帧处截断；实时位置到目标包点 ≤12 m 时提前结束回放，交 A* 下包。
- **偏离/卡住**：偏离当前车道 >0.8 m 用 A* 重接该帧；高移动意图持续 2.5 s 无 cursor 进展 → 放弃回放并回退 A*；遇敌时暂停链接超时与 cursor 看门狗。

### 2.5 T 守包轨迹

| 地图 | 包点 | 名称 | 帧数 | 来源 |
| --- | --- | --- | ---: | --- |
| Mirage | A | `A_hold_R4_Flierax` | 129 | `mirage_user_t_routes.POSTPLANT` |
| Dust2 | B | `B_car_hold` | 230 | `dust2_user_t_routes.POSTPLANT`，复用 CT `B_1` 守车位的 hold 帧（源 `side: defend`） |

Mirage A 下包后使用该 hold；Dust2 B 下包后使用与 CT B 车位相同的守位循环。其余包点没有录制守包，继续使用通用的 `post_plant_target()` spot/look 逻辑。

## 3. CT 防守轨迹（opening + hold 配对）

CT pair 由 `opening`（从 CT 出生点到守点）与 `hold`（守点小范围循环）两段组成。`choose_ct_recorded()` 按站点过滤后按 `seat % len(options)` 分配。

### 3.1 Dust2

| 名称 | site | opening 帧数 | hold 帧数 | 备注 |
| --- | --- | ---: | ---: | --- |
| `A_1` | A | 216 | 98 | 守 A 车位，距包点中心约 25.7 m |
| `B_1` | B | 312 | 230 | 守 B 车位，距包点中心约 22.8 m |

### 3.2 Mirage

| 名称 | site | opening 帧数 | hold 帧数 | 状态 |
| --- | --- | ---: | ---: | --- |
| `A_1` | A | 328 | 237 | 启用 |
| `A_2` | A | 296 | 147 | 启用 |
| `A_3` | A | 310 | 177 | 启用 |
| `B_1` | B | 496 | 180 | 启用 |
| `B_2` | B | 401 | 442 | 启用 |
| `B_3` | B | 386 | 437 | **禁用**（`MIRAGE_DISABLED_CT_PAIRS`，two-box 攀爬在平台碰撞中不可通过） |

### 3.3 执行规则

- `choose_ct_recorded()` 只在该回合第一次调用时固定 pair；被判定卡住/放弃后本轮不再重选，回退 `advance_holds` 的防守 hold 或 nav anchor。
- `follow_ct_recorded()` 从 `frames[0]` 开始时若距离 >6 m，先用 A* 移动到起点；之后按实时位置和视角跟随。
- opening 到末帧后切 `hold` 并循环；hold 是原地/小范围守位，不触发路线结束。
- 20 tick（约 0.33 s）无进展 → 侧移绕行；连续 2 次仍无进展 → 放弃整组 pair。Mirage 的已知攀爬点在放弃前允许跳点重试。
- 下包后 `follow_ct_recorded()` 立即停止（`not planted` 守卫），交给 `choose_retake()`；没有用户录制回防的地图直接回退 A*。

## 4. CT 回防轨迹

| 地图 | 方向 | 名称 | 帧数 | 来源 |
| --- | --- | --- | ---: | --- |
| Mirage | B→A | `B_to_A_1` | 687 | `mirage_user_ct_routes.RETAKES` |
| Mirage | B→A | `B_to_A_2` | 634 | `mirage_user_ct_routes.RETAKES` |
| Dust2 | — | 无 | — | 下包后 A* 直奔炸弹 |

- `choose_retake()` 只在已下包、目标包点为 A/B 时触发；方向由炸弹包点与对侧 origin 推出（当前只有 `B_to_A`）。
- 选择距离实时位置最近的候选；若实时位置在对侧 origin 半径内，或距任一候选入口 ≤20 m，则开始接路。
- 接路使用 `entry_policy="earliest"`：按 A* 路径代价最多比较 4 个间隔 ≥24 帧的候选，允许从轨迹中段进入。
- 8 s 接路超时会重试候选帧，最终失败则回退 A* 到炸弹；跟随结束后同样 A* 奔向炸弹。

### 4.1 未启用的职业 demo 回防

`pro_retakes.py` 保留了以下编译结果，`agent.pro_retake_routes()` 可读取，但 `act()` 没有调用：

| 地图 | A→B | B→A |
| --- | ---: | ---: |
| Dust2 | 3 | 3 |
| Mirage | 3 | 2 |

这些数据目前只用于 `tests/test_pro_demo_routes.py` 和 Walklab review，不是运行时候选。若后续启用，需要先在 `choose_retake()` 中定义与用户回防的优先关系。

## 5. 地图矩阵

| 地图 | T 进攻 | T 守包 | CT opening/hold | CT 回防 |
| --- | --- | --- | --- | --- |
| Dust2 | `legacy` + `B_site_20261113` + `B_mid_doors_20261114` | B：`B_car_hold` | `A_1` / `B_1` | —（A*） |
| Mirage | `legacy` + 5 条用户 T | A：`A_hold_R4_Flierax` | A1–A3 / B1–B2（B3 禁用） | `B_to_A_1/2` |
| Borgo | `legacy`（A） | — | — | — |
| Molo | `legacy`（B） | — | — | — |
| Nevaio | `legacy`（A） | — | — | — |

Borgo/Molo/Nevaio 的 CT 未下包阶段仍使用 `advance_holds`（Borgo A anchor、Molo/Nevaio 通用 anchor），这不是录制轨迹。

## 6. 源码与数据位置

| 内容 | 位置 | 是否入包 |
| --- | --- | --- |
| T 单图轨迹（5 图） | 根目录 `*_replay.py` | 是 |
| Dust2 T 第二路线 | `dust2_b_replay.py` | 是 |
| Mirage T 用户路线 | `mirage_user_t_routes.py` | 是 |
| Dust2 T 用户路线 + B 守包 | `dust2_user_t_routes.py` | 是（待提交） |
| Mirage CT pair + 回防 | `mirage_user_ct_routes.py` | 是 |
| Dust2 CT pair | `dust2_user_ct_routes.py` | 是 |
| 职业 demo 回防（未启用） | `pro_retakes.py` | 是 |
| 用户源录制 JSON / manifest | `recordings/**`、`walklab/public/routes/**` | 否（未跟踪） |

## 7. 验证状态

- 本地 `python3 -m unittest discover -s tests -q`：202 通过、6 skipped（2026-11-14，含未提交的 Dust2 T 改动）。
- Mirage CT pair、Mirage T 用户路线、Dust2 B 路线已进入正式提交；Dust2 CT 车位路线随 v0.21 首次提交。
- 编译与单元测试只证明格式、配对、门控和选择逻辑；**实走碰撞、视线、卡住率与胜率提升仍需用 `agx-match-query` 回填**。
- Dust2 CT 车位距包点中心较远（约 23–26 m），实战是否合适需要下一轮对局评估。
