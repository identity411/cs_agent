# 当前 baseline 与官方合同的差异

> 对照对象：本仓库 `agent.py`（177 行 baseline，commit `57fb246`）与官方指南合同 `rsi-fps-5.5`。这是**静态审阅**，没有在真实首拍或本地 Arena 上验证；实际字段与语义以首次合法观察、裁判回执和官方源码为准。
>
> **2026-11-12 更新**：`agent.py` 已针对正式对局中的出生点卡住修复移动 / 路径点 / 卡住恢复（见 [`11-12-stuck-at-spawn.md`](./11-12-stuck-at-spawn.md)），行号与移动行为已变化；本文件其余合同差异仍以修复前的 177 行 baseline 为对照，武器 / 瞄准 / 目标交互差异未变。
>
> 版本：`1112-v0.00`（[快照与改动说明](../submissions/1112-v0.00/README.md)）。`1112-v0.01` 是同一份代码的首次 Python ZIP 提交（[提交结果](../submissions/1112-v0.01/README.md)），admission `passed`、版本 1 已激活；下表的差异**仍未修复**，准入通过不代表完整对局或得分成功。

## 变更记录

### 2026-11-12
- **关联规范**：[agent-interface.md](agent-interface.md)、[agx-submit skill](../../.claude/skills/agx-submit/SKILL.md)、[1112-v0.01](../submissions/1112-v0.01/README.md)。
- **背景**：baseline 与线上 Python 合同存在字段 / 语义差异；`1112-v0.01` 已按原样通过 admission，但未验证完整对局。
- **决策点**：先提交基线做流程验证；不把准入当成绩；按高风险项优先修复后再发下一版。

## 结论

当前 baseline 输出的动作字段基本落在官方动作合同内（`move_forward` / `move_right` / `yaw_rate` / `pitch_rate` / `fire` / `reload` / `weapon_slot` / `use` / `buy` 等），但观察与武器状态有几处关键假设可能不成立。最高优先级是：**`map.nav` 结构、`aim_punch` 字段、`reload_until` 语义、下包 / 拆包条件**。

## 高风险（可能导致不工作）

| 位置 | baseline 的假设 | 官方合同 | 影响 / 处理 |
| --- | --- | --- | --- |
| `load_map` / `route` | `map["nav"]["nodes"]`、`map["nav"]["edges"]` 一定存在，且 `walk` 边可双向通行 | 首拍描述明确包含 `sites`、`spawns`、`meshes`、`route_landmarks`、`plant_zones` 等；`source-adjacency` 只是导航来源，不证明边可通行 | 1112-v0.01 admission 通过说明首拍路径未崩溃，但五图 / 完整对局仍未验证。若没有 `nav` 会直接 `KeyError`；不要仅凭几何邻接当作可通行图 |
| `combat` | 武器有 `aim_punch: {yaw, pitch}` | 合法武器字段是 `recoil_pitch` / `recoil_yaw`，没有 `aim_punch` | `.get("aim_punch", {})` 会静默返回空字典，当前等于完全不做后坐力补偿；应改用官方字段 |
| `combat` | 只要 `reload_until` 为假值就算不在换弹 | `reload_until` 是绝对结束 tick 或 `null`；`me.reload` 是剩余秒数 | 若换弹结束后该字段仍保留过去 tick，baseline 会永远不满足 `not reload_until`，从而不再开火。应显式比较 `match_tick`，或读 `me.reload` |
| `act` 下包 | 距站点 `center` 小于 `radius * 0.5` 就发 `use="plant"` | 裁判要求脚点在站点 / `plant_zones` 内，存活、着地、速度 ≤ 0.1 m/s、持续 `use="plant"` 180 tick | 位置判定可能不符；应使用 `plant_zones`，并确保交互期间静止 |
| `act` 拆包 | 距炸弹 < 2.0 m 就发 `use="defuse"` | 距离严格 < 2.8 m；有钳 300 tick、无钳 600 tick；同样要求存活、着地、速度限制与持续 use | 2.0 m 比官方更严格，可能错过合法拆包位置；也要确认自己在拆包期间保持静止 |
| 开火 / 换弹 | 只看 `ammo`、`reserve`、`reload_until` | 还有 `shot_ready`、`switch_until` 等绝对 tick 阈值 | 过早的请求会被裁判拒绝，不致命，但会浪费交火 tick；应按阈值判断 |

## 中风险（行为偏差）

| 位置 | baseline 的假设 | 官方合同 / 建议 |
| --- | --- | --- |
| 购买时机 | 只在 `phase == "buy"`（6 s）购买 | 购买窗口持续到回合起点后 1860 tick（31 s，含前 25 s live）；baseline 少用了 25 s |
| 购买内容 | 先买拆弹器，再买步枪，再买护甲 | 官方还有 `helmet`（价格随已有护甲变化）等；当前不买头盔，且防守方 800 开局先买拆弹器可能连护甲都买不起 |
| 目标优先级 | 下包 / 拆包优先于交火 | 官方在目标交互期间锁定移动与开火；优先级本身合法，但下包 / 拆包前不先清人风险高 |
| 目标部位高度 | 固定 head 1.64 / chest 1.18 / abdomen 0.88，敌人蹲下统一 × 0.6 | 官方说明 `parts` 是合法视线采样：`head` 为高度减 0.16 m，`chest` / `abdomen` 分别为高度的 0.65 / 0.3；相机高度另按站姿与蹲伏插值；也不保证未来命中。身高模型需按实际首拍校准 |
| 眼高 | 站立 1.62 / 蹲下 0.95 | 与官方投掷判定中的眼高一致；但蹲下动作有 1 tick 滞后（见下） |
| 蹲伏眼高 | 本 tick 计算用 `m["crouch"]`，同时发 `crouch=True` | 切换姿态时有一 tick 的瞄准高度误差 |
| 武器干弹 | 主武器槽存在就一直用 0 槽；打空且无备弹也不切枪 | 官方允许切到 1/2 槽（副武器 / 刀）；baseline 会拿着空枪 |
| 掉落炸弹 | 炸弹未 planted 时只去选点，不捡包 | 官方有 `world_items`、`pickup_id` 与自动拾取规则（< 2.3 m 可见）；当前不处理掉落包 |
| 队友 / 声音 / 通信 | 完全不使用 | 官方提供 `teammates`、`sounds`、`messages`、`signals`；当前 baseline 无法配合队友 |
| 地图身份 | 不校验 `map_id` / `static_schema_hash` | 官方要求按身份缓存；身份不符时应停用旧路线 |
| 契约身份 | `init` 忽略 `context` | 官方建议检查 `contract_id`；本地示例会在不匹配时抛错 |
| 梯子 | `load_map` 直接丢弃 `ladder` 边，也不发 `ladder` / `climb` 动作 | 官方动作合同包含 `ladder` 与 `climb`；某些区域可能不可达 |

## 与合同一致的部分

- 动作字段名与取值范围合法：`{}`、`move_forward`、`move_right`、`yaw_rate`、`pitch_rate`、`jump`、`crouch`、`walk`、`fire`、`reload`、`weapon_slot`、`use`、`buy`。
- 水平朝向使用 `atan2(-dy, dx)`，与官方「正 yaw 面向 `(cos(yaw), -sin(yaw))`」一致。
- 俯仰使用 `atan2(dz, 水平距离)`，正 pitch 向上，与官方一致。
- 站立 / 蹲下眼高 1.62 / 0.95 与官方投掷判定一致。
- 动作槽 0 主武器、1 副武器；`weapons[0]`、`weapons[1]` 的用法与官方动作槽一致（不是目录槽）。
- 购买 ID `ak47`、`m4a1`、`armor`、`defusekit` 存在，且 `ak47` 为 T、`m4a1` 为 CT、`defusekit` 为 CT，与基础价格一致。
- `phase`、`side`、`seat`、`round_index`、`match_tick`、`blind_ticks`、`carrying_bomb`、`has_kit`、`visible[].parts`、`bomb.state` 等字段都有合法来源。
- 每席独立进程/模块状态的前提下，模块级单例不会跨席共享；但同一进程内重复加载同一模块名会冲突。

## 建议修改顺序

1. 先跑一次可信本地 probe / 首拍检查，打印 `map` 顶层键、`me.weapons[0]` 的键、`bomb.state` 的取值与 `phase` 序列。
2. 修正 `reload_until`（按绝对 tick 比较或读 `me.reload`）与 `aim_punch` → `recoil_pitch` / `recoil_yaw`。
3. 把拆包距离改为 `< 2.8 m`；下包改用 `plant_zones`，并保证交互期间静止、着地、速度 ≤ 0.1 m/s。
4. 验证 / 重写 `map.nav` 寻路来源；必要时改用 `route_landmarks` 或预计算路线，并处理梯子 / 爬梯动作。
5. 在 `init` 中检查 `contract_id`，缓存并校验 `map_id` / `static_schema_hash`。
6. 扩展购买窗口与购买项（含头盔）；处理主武器干弹切枪、掉落炸弹拾取。
7. 校准瞄准部位高度；加入 `shot_ready` / `switch_until` 判断。
8. 视赛制需要再接入队友信息、声音、投掷物与通信。

> 本文件只记录差异，不改变 `agent.py`。修改前应先取得真实首拍 / 本地回执，避免按猜测改坏 baseline。
