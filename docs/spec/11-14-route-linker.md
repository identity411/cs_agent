# 规范：轨迹段与通用链接器

Status: **本轮 review 修订随 `1114-v0.23` 提交并激活：main v19 / account2 v22，admission 均 `passed`，entry code hash `03f89d9cd787`；本地 233 项测试通过（6 skipped），实战效果待回填。历史 P1 已随 `1114-v0.19` 提交：main v15 / account2 v18，entry code hash `55bff79bffe0`。**
Date: 2026-11-14
Submission: [1114-v0.19](../submissions/1114-v0.19/README.md)
Related: [11-13-pro-demo-routes.md](./11-13-pro-demo-routes.md)（对侧下包回防）· [11-14-pro-demo-walklab-pipeline.md](./11-14-pro-demo-walklab-pipeline.md)（两段式组合）· [11-12-pathing-routes.md](./11-12-pathing-routes.md)（A* / 卡住恢复）· [11-13-combat-stability.md](./11-13-combat-stability.md)（录制路线遇敌暂停）· [11-14-replay-follow-wedge.md](./11-14-replay-follow-wedge.md)（把链接器扩展到 T 进攻入口与跟随偏离重接；本文的 P1 状态不变）

## 0. 结论先行

把所有录制内容统一抽象成**轨迹段（Route）**：只有起点、终点和中间帧，不关心它是开局、守点、回防还是进攻。

把两段轨迹接起来只需要一个**通用链接器（Linker）**：

```text
Route A 的终点 / 当前实时位置
        ↓  A* 导航（唯一默认方式）
Route B 的入口帧
```

链接期间不考虑掩体、预瞄、战术 lane、进场朝向，只考虑“用最短时间进入 B”。**越早进入预定轨迹越好。**

这样 CT 守点 → 回防、开局 → 守点、回防 → 炸弹、T 进攻 → 守包，全部复用同一套逻辑；不需要为每一对路线录 connector。

## 1. 抽象

### 1.1 轨迹段

```text
Route = {
  name, side, purpose, site,      # 可选元数据，只用于选择，不参与链接算法
  frames: [(x, y, z, yaw, pitch, key_mask), ...],
  loop: bool,                     # hold 循环：末帧接回首帧，不触发跨段链接
  entry_policy: first | earliest | window,
  window_fraction: 0.1,          # window 默认前 10%，向上取整至少一帧
}
```

- **起点** = `frames[0]`，**终点** = `frames[-1]`；
- `loop=True` 的轨迹没有“终点 → 下一段”的语义，它自己闭环；
- 其他轨迹都是一次性的有向段；
- 现有 `PAIRS.opening`、`PAIRS.hold`、`RETAKES`、T `ATTACKS`、T `POSTPLANT` 都可以分别看作一条轨迹段。

### 1.2 链接

```text
Link(A → B) = 从当前实时位置（通常是 A 的终点）
              导航到 B 的入口帧
              然后从该入口帧开始跟随 B
```

- 链接是**纯导航**，不录帧、不加战术约束；
- 默认使用现有 A*（`agent.move()` / `route()`），允许 sprint；
- 链接过程中遇敌仍由现有战斗逻辑暂停/恢复；
- 一旦进入 B 的 `entry_radius`，立即设置 B 的 cursor，开始跟随 B；
- 链接失败才考虑回退（见 §3.4）。

## 2. 入口策略：怎样算“越早进入”

`entry_policy` 决定允许从轨迹的哪一帧进入：

| 策略 | 行为 | 适用 |
| --- | --- | --- |
| `first` | 只允许从 `frames[0]` 进入 | 起点有战术含义（回防入口、进攻第一预瞄点） |
| `earliest` | 允许任意帧，选 **A* 路径代价最小** 的可达帧 | 纯移动段；越早进入越好（推荐默认） |
| `window` | 只允许前 N% 的帧，选代价最小的 | 既想早点进，又不想跳过关键开头 |

关键点：

1. “越早”按 **A* 路径代价** 算，不按直线距离算。直线更近但需要绕墙/上坡的帧，不应该赢。
2. 候选帧不全量扫描。P1 的实现：
   - 按实时位置到帧的平面距离排序，取最多 4 个彼此间隔 ≥24 帧的候选；
   - 再补上 `frames[0]`，保证“回到起点”始终是候选；
   - 每个候选跑一次 `_astar()`，计入路径长度、失败边惩罚及反向边惩罚，取总代价最小者；代价相同取帧下标更小的；
   - 只在链接开始时计算一次，失败重试时用已排序的候选列表。
3. 如果允许 `earliest`，agent 可能从 B 的中段进入，从而跳过 B 的开头。当前 CT 回防默认使用这条策略（24 帧是候选间隔，不是允许跳过的最大帧数），因为目标是“尽快进入轨迹”。
4. 如果当前处于 LINKING，且已在 B 的 `entry_radius`（`RETAKE_JOIN_DISTANCE = 6 m`）内：
   - 同时要求高度差 ≤1.0 m；满足后立即设置 cursor 到选定入口帧并开始跟随，不再寻路。
5. P1 参数：

| 常量 | 值 | 含义 |
| --- | ---: | --- |
| `RETAKE_JOIN_DISTANCE` | 6.0 m | 进入轨迹 / 从 A* 切到跟随的距离 |
| `RETAKE_ENTRY_JOIN_RADIUS` | 20.0 m | 没有经过 origin site 时仍允许接路的预筛距离 |
| `RETAKE_DECISION_TICKS` | 180（3 s） | 下包后持续重选回防路线的时间窗 |
| `RETAKE_LINK_TIMEOUT_TICKS` | 480（8 s） | 单个入口接路超时 |
| `RETAKE_ENTRY_STRIDE` | 24 帧 | 候选入口之间的最小间隔 |
| `RETAKE_ENTRY_CANDIDATES` | 4 + 起点 | 最多 5 个候选；起点已包含时不重复 |
| `LINK_TOTAL_TIMEOUT_TICKS` | 720（12 s） | 所有候选共用的接路预算，重试不重置 |
| `LINK_ENTRY_HEIGHT_TOLERANCE` | 1.0 m | 入口高度差容差，允许小坡差、拒绝跨层 |

## 3. 链接器

### 3.1 接口

```python
def link_to_route(self, o, pos, action, frames,
                  entry_index=0,
                  entry_radius=RETAKE_JOIN_DISTANCE,
                  via_key=None) -> Action | None
```

返回 `None` 表示已进入入口半径，调用方应开始 `follow_trajectory()`；否则返回 `move()` 生成的动作。

相关状态：

```text
retake_entry_frame       选定的入口帧下标
retake_entry_candidates  [(A* 代价, 帧下标), ...]，按代价排序
retake_entry_choice      当前使用到候选列表的第几项
retake_link_started      当前入口开始接路的 match tick
retake_entry_logged      是否已经真正进入轨迹
retake_fail_logged       是否已经记录最终失败
```

### 3.2 每拍流程

```text
if 处于 LINKING 且 XY 距目标入口帧 <= entry_radius 且高度差 <= 1.0 m:
    设置 target_route.cursor = entry_frame
    退出链接，开始 follow_trajectory(target_route)
else:
    用现有 move() 向入口帧移动（sprint=true）
    如果 move() 无法生成路径 / 无位移超过 REPLAY_BLOCK_TICKS:
        尝试下一个候选入口帧
    如果所有候选都失败:
        走 fallback（§3.4）
```

注意：

- 链接期间不调用 `follow_trajectory()`，也不读目标轨迹的 yaw/pitch；进入后再读。
- 链接期间不改变目标轨迹的 cursor；避免边链接边“预读”导致进入时跳帧。
- 进入 B 后不再回头补 A 的剩余帧；A 已经结束或被 trigger 打断。
- 如果链接路径意外穿过 B 的轨迹（几何上更早接触），这不算“进入”，除非选定的入口帧在 `entry_radius` 内；否则会出现“路过但不进入”的抖动。`earliest` 策略通过选最近的合法帧来避免这个问题。

### 3.3 轨迹结束 / 触发

| 事件 | 行为 |
| --- | --- |
| A 正常到末帧 | 若配置了 next route，链接到 B；否则执行现有 fallback（A* 到目标 / hold） |
| 外部 trigger（下包、炸弹掉落、回合阶段） | 立即中断 A，链接到对应 B；不等待 A 走完 |
| B 是 loop | 到末帧后 cursor 归零，继续循环；不触发下一段 |
| B 是普通段 | 到末帧后执行 B 配置的 fallback 或下一条 link |
| 看到敌人 | 现有战斗逻辑暂停移动；战斗记忆结束后继续当前 link / 当前轨迹 |

### 3.4 失败与回退

```text
入口不可达 / 卡住 / 单候选超时
  → 总接路预算未用尽时尝试下一个合法候选（最多 5 个，含起点）
  → 仍不可达：A* 到当前 objective（炸弹 / 包点 / 拆包位）
  → 记录 timeout / unreachable / blocked，并写明原因
```

- 卡住阈值沿用 `REPLAY_BLOCK_TICKS = 20`；一次链接最多重试 4 个备选入口帧（含补充起点），避免每拍全量 A*。
- 链接超时 `RETAKE_LINK_TIMEOUT_TICKS = 480`（8 s）后放弃当前入口；所有候选都失败或累计接路达到 12 s 则放弃该轨迹，直接 A* 到 objective。
- 下包后的 3 s 选路窗口内仍可重新选择轨迹；一旦选定轨迹并开始接路，只在候选入口之间重试，不再换轨迹。
- 原地转向不计为卡住：`_retake_turning()` 在光标目标仍在身后时重置卡住计时；真正无位移才进入重试。

### 3.5 观测

```text
link map=mirage-cs2-v54 seat=2 round=7 pair=B_2 retake=B_to_A_1
     mode=astar result=entered entry=38/687 join_dist=6.63
```

需要聚合：

- `pair` / `retake` 轨迹名、入口帧 / 总帧数；
- 起点到入口的距离（`join_dist`）与耗时；
- 是否重试过入口帧、最终结果（selected / entered / retry / blocked / timeout / unreachable / missing / out_of_range / same_site）；
- 进入轨迹后是否再次被卡住/放弃。

## 4. 应用到现有链路

| 链路 | A（来源） | B（目标） | 入口策略 | 现状 |
| --- | --- | --- | --- | --- |
| CT 开局 → 守点 | opening | hold | `first` | 编译期接点 ≤0.2 m；仍走 pair 直接切段，未改 |
| CT 守点 → 回防 | hold（循环） | retake | `earliest` | **已接入链接器：A* 接路，允许中途进入；Mirage B 守点命中第 31/38 帧** |
| CT 回防 → 炸弹 | retake | 炸弹 / 拆包点（伪轨迹） | `earliest` | 已改为 A* 到炸弹 |
| CT 同点下包 | hold | 守点/拆包动作 | `first` | `choose_retake()` 记录 `same_site`，直接 A* 到炸弹 |
| T 进攻 → 下包 | attack | plant point（伪轨迹） | `earliest` | 带包者 12 m 截止不变；出生点入口已改接 `link_to_route(first, 1.0 m)`，见 [11-14-replay-follow-wedge.md](./11-14-replay-follow-wedge.md) |
| T 下包 → 守包 | plant point | postplant | `first` | `follow_t_postplant()` 已用 A* 接路 |
| T demo → 手录衔接 | demo | handoff | `first` | 已按顺序拼接 |

Mirage CT 守点 → B→A 回防的实测缺口（正是链接器要覆盖的距离）：

| 守点 | hold 终点到 B 点中心 | 到 B→A 首帧最近距离 |
| --- | ---: | ---: |
| B_1 | 5.02 m | 5.14 m |
| B_2 | 11.61 m | 11.07 m |
| B_3 | 4.18 m | 3.83 m |

## 5. 对当前代码的改动

### P1：抽出链接器，替换 CT 回防的直线转向（已实现）

1. 新增 `link_to_route()`：A* 到入口帧，`entry_radius` 内切 `follow_trajectory()`。
2. `follow_retake()` 中距入口 >6 m 的直线转向全部删除，改为 `link_to_route()` + A*；`retake_direct()` 已移除。
3. 回防选路可重试：下包后 3 s 窗口内允许重新选入口/轨迹，不再第一拍一票否决。
4. 回防末帧 → 炸弹改为链接器（A* 到炸弹）。
5. 下包时不再无条件清空 `ct_recorded_pair`；`follow_ct_recorded()` 本来就有 `not planted` 门控，pair 保留用于交接日志。
6. 日志按 §3.5。

实现落点：

| 改动 | 位置 |
| --- | --- |
| 链接器 `link_to_route()` | `agent.py` |
| 入口候选 / A* 代价选择 `choose_route_entry()` / `_entry_candidates()` | `agent.py` |
| 入口重试 `_retry_retake_entry()` | `agent.py` |
| 回防选路 3 s 窗口 / 同点 / 缺失方向 | `agent.py` `choose_retake()` |
| A* 接路 + 中途重接 + 末段 A* 到炸弹 | `agent.py` `follow_retake()` |
| 战斗期间暂停链接超时 | `agent.py` `act()` |
| 单测 | `tests/test_route_linker.py`、`tests/test_mirage_user_ct.py` |

本地验证（2026-11-14）：

- Mirage B_1：hold 终点距回防起点 5.14 m，直接选中轨迹第 38 帧（3.91 m），当拍进入；
- Mirage B_2：hold 终点距回防起点 11.50 m，选中轨迹第 38 帧（6.63 m），用 A* 接路；
- Mirage B_3：hold 终点距回防起点 4.16 m，选中轨迹第 31 帧（3.70 m），当拍进入；
- `python3 -m unittest discover -s tests -q`：177/177 通过（6 skipped）。

### P2：让轨迹可组合

1. 数据层允许轨迹声明 `next` / `trigger`，或由运行时按阵营/包点/阶段选择下一条轨迹；
2. `loop` 标记区分 hold 循环和一次性段；
3. `entry_policy` 进入编译数据；
4. 旧的完整 opening/retake 仍可直接使用，不需要重录。

### P3（可选）：录制链接段

只有实测证明 A* 链接不可接受时才做：

- 为特别难走的 4–15 m 缺口录短段（跳点、狗洞、窄口）；
- 链接器优先使用该段，否则 A*；
- 不要求每对轨迹都录。

## 6. 验收

- [x] Mirage B_1/B_2/B_3 守点 → B→A 轨迹：3 s 内选路，入口命中轨迹第 31/38 帧，A* 接路进入；本地单测通过；
- [x] 链接器选择 A* 路径代价最小的入口，而不是固定第 0 帧；中途进入已用 B_1/B_3 用例覆盖；
- [x] 入口不可达时尝试下一个候选帧，最终回退 A* 到炸弹，日志带 `retry` / `timeout` / `unreachable`；
- [x] 回防末帧 → 炸弹使用 A*，不再直线转向；
- [x] 同点下包不走 cross-site retake；
- [x] 旧轨迹格式和现有 T postplant 接路行为不变（全量 177/177 通过，6 skipped）；
- [ ] 实战回填链接耗时、失败原因、入口帧分布、回防到位率。

## 7. 已确认 / 待调参

| # | 决策 | 结论 / 建议 |
| --- | --- | --- |
| 1 | 默认入口策略 | **已确认：允许中途进入**；P1 对回防使用 `earliest`（A* 路径代价最小） |
| 2 | 是否允许中途进入轨迹 | **已确认允许**；如果某条轨迹开头有必须执行的战术动作，后续可加 `first` 标记 |
| 3 | 是否录链接段 | 先不录；P1 纯 A*，实战不行再补 |
| 4 | 链接超时 | 当前 8 s；实战回填后调整 |
| 5 | 失败回退 | 下一个候选帧 → A* 到 objective；不再单独走“轨迹终点”一步 |

## 8. 非目标

- 不在链接期间做预瞄、掩体、peek、lane 约束；这些属于轨迹内部或后续扩展。
- 不要求轨迹首尾闭环（loop 除外）。
- 不解决“轨迹内部被卡住”的全部恢复策略；沿用现有 `REPLAY_BLOCK_TICKS` / A* 回退。
- 不把动作点、lane、approach 纳入本版核心；如果后续需要，可以作为轨迹元数据叠加，不改变链接器语义。


## 9. 2026-11-14 review 修订：阶段隔离与有界接路

本节约束优先于上文历史 P1 实现记录；当前只升级 CT retake 与 T attack 共用接路状态，CT opening/hold 和 T postplant 暂保留原调用链，不宣称已全部统一。

### 9.1 状态与所有权

`SELECT_ENTRY → LINKING → FOLLOWING → objective / DONE`；选路不可达、候选耗尽或总预算耗尽进入 FAILED，并交给现有 objective 回退。沿用 `LinkState.entry_frame` / `entered` / `fail_logged` 与调用方 done 标记表示阶段，不增加第二套可相互矛盾的状态字段。

- SELECT_ENTRY：按策略计算候选和排序，一次完成。
- LINKING：唯一允许检查旧入口距离、单入口 8 s 超时和候选重试的阶段。所有候选共用累计 12 s 导航预算；战斗暂停预算且保留暂停前已消耗的时间，重试只重置单入口计时。
- FOLLOWING：进入只初始化一次 cursor 并清空链接 A* 状态；不再检查旧入口，不重新启动链接计时。正常跟随超过 8 s 不能因此放弃。
- FOLLOWING 偏离时向当前 cursor 接路，不能退回最初入口；CT 继续使用自身无位移看门狗，T 继续使用现有进度看门狗。
- retake 到末帧后直接 A* 到炸弹；之后每拍继续此目标，不回头接轨迹入口，也不每拍清空 A* 路径或套用录制轨迹无位移看门狗；后续导航由 move 自身处理。
- `link_to_route()` 仍为底层导航函数（`None` 表示到达）；到达判定集中为 XY 半径 + 高度差 ≤1.0 m，T/CT 调用方不得另写仅 XY 的捷径。

### 9.2 策略与代价

- `first` 严格只含 frame 0。不可达必须显式失败，不默默切为 `first-fallback`。T 放弃录制路线并使用既有通用目标导航。
- `window` 默认前 10%，允许 `window_fraction` 指定 (0, 1]；使用 ceil，至少一帧。不可达也不越过窗口。
- `earliest` 保留最多四个分散候选 + 起点的有限采样；这是近似最优，并非全轨迹全局最优。
- 排序与 A* 边成本一致：几何长度 × (1 + 失败边惩罚 + 反向边惩罚)，额外计入起终点接入距离。防止反复选中已知撞墙的低几何长度入口。

### 9.3 回归验收

- 真 Mirage B→A 进入后前进超过 6 m，仍继续当前轨迹，不拉回入口。
- 连续移动且跟随超过 8 s 不触发接路超时；末帧连续两拍都朝炸弹导航。
- 同 XY、低 8 m 不能进入；低 0.7 m 的小坡差可以进入；T 和 CT 共用判定。
- first 起点断路时显式失败；window 在长短轨迹上按比例取帧。
- 候选重试不会重置 12 s 总预算；战斗等待不消耗预算。
- 已惩罚边影响候选排序，而非仅影响每条路径内部搜索。

阈值 1.0 m / 12 s 为本地初值，正式对局仍需用合法 training 决策日志核对坡道接入与回防耗时。

本轮本地验收：`python3 -m unittest discover -s tests -q` 共 233 项，无失败、6 skipped；新增 14 项回归，覆盖上述故障及连续回调。`git diff --check` 通过。修改尚未打包上传，正式对局效果待验证。
