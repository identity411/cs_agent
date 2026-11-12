# Agent 接口

> 依据：AGX「多人爆破 · AI 助手开发指南」，合同 `rsi-fps-5.5`（2026-11-12 版）。原文声明这是闭门候选合同：只有赛事与已接受投稿明确选择该合同时才适用，历史对局保留自己的合同。
>
> 当前 `agent.py` 是旧 baseline，与本文的差异见 [`baseline-compatibility.md`](baseline-compatibility.md)；在实测首拍前不要假设它已完全适配。

## 生命周期

提交 ZIP 的根目录必须有 `agent.py`。平台为十个席位分别加载独立策略实例（正式路径是十个独立常驻 P01 进程），入口：

```python
def init(context): ...
def act(observation): ...
```

`init(context)` 只保证收到：

| 键 | 含义 |
| --- | --- |
| `seed` | 本席公开的策略随机域；不能用来重建选图或其他隐藏抽样 |
| `weights_dir` | 解包目录 |
| `contract_id` | `rsi-fps-5.5` |
| `seat` | 0–9 |
| `role` | 0 |

`act(observation)` 返回普通 JSON 兼容对象；`{}` 合法，缺失字段补中性默认值。NumPy 标量需显式转成 Python 数值。stdout 留给协议，调试写 stderr。

## 合法观测

每席收到独立 JSON，不接收 `arena.frame()` 或全知录像。集合可能为空；只在特定状态存在的子字段，先检查再用。

### 顶层字段

| 字段 | 含义 |
| --- | --- |
| `rules_version`, `seat`, `team`, `side`, `role` | 合同身份；`side` 为 `attack` / `defend`，`role` 为 0 |
| `match_tick`, `round_index`, `round_tick`, `phase`, `phase_remaining_ticks` | 整数时钟；`phase` 为 `buy`、`live`、`post` 或终局 `finished` |
| `round_wins`, `alive_by_team`, `attack_team` | 固定队伍公开比分、存活数、进攻队伍 |
| `period`, `overtime_number`, `win_target` | 默认 `regulation`、`0`、`13`；加时只有可信合同可启用 |
| `buy_deadline_tick`, `loss_level` | 绝对购买截止 tick 与己队败补档位 |
| `me` | 自身状态 |
| `teammates` | 其余队友的 `seat`、`alive`、`cash`、`zone` 与允许的装备 |
| `visible` | 当前可见敌人的合法姿态 |
| `sounds` | 仅听到的 `{type, direction, distance_band}` |
| `heard` | 空的历史兼容集合；应读 `sounds` |
| `bomb` | 仅允许知道的炸弹状态；隐藏位置不能作为目标坐标 |
| `world_items` | 可见掉落物 `{id, kind, position}` |
| `messages`, `receipts` | 允许的队友通信与自己的动作 / 经济回执 |
| `map_id`, `static_schema_hash`, 首次 `map` | 静态身份与仅首次下发的描述 |

### `me`

`me` 包含：

- 运动与姿态：`x/y/z`、`yaw/pitch`、`vx/vy/vz`、`crouch`、`lean_offset`、`grounded`、`sprinting`、`stamina`
- 生存：`hp`、`armor`、`helmet`、`alive`、`blind_ticks`
- 武器与库存：`ammo`、`reload`、`recoil`、`weapon_status`、`weapons`、`active_slot`、`slots`、`throwables`、`throwable_kinds`
- 时钟与状态：`pickup_ready_tick`、`switch_until`、`throw_ready`、`ads_progress`
- 目标与经济：`cash`、`carrying_bomb`、`has_kit`

候选合同还在 `me` 中增加：`walk`、`quiet`、`duck`、`zoom_level`、`ladder_id`、`movement_mode`、`shot_ready`。

关键约定：

- `me.weapons` 按三个**动作槽**排列：0 主武器、1 副武器、2 刀；空槽可能为 `null`，读弹药前先检查当前武器。
- `active_slot` 是 `me.weapons` 的下标，不是武器目录里的 `slot`。
- 单把武器含 `id`、`ammo`、`reserve`、`shot_ready`、`reload_until`、`recoil_pitch`、`recoil_yaw`、`shots`、`last_shot`，以及本人账本、后坐、扳机与装填状态。
- `reload_until` 是结束 tick 或 `null`；`me.reload` 是剩余秒数。
- `shot_ready`、`switch_until`、`pickup_ready_tick`、`throw_ready` 都是绝对物理 tick 阈值；应比较 `match_tick >= threshold`，不能把任何非零数字当作「已就绪」。
- 渲染用的 `zoom_fov` 不是额外策略输入。

### `visible`

敌人条目只提供 `seat / team / x / y / z / yaw / pitch / crouch / lean / parts / weapon`：

- `weapon` 是当前持枪的外观 ID 或 `null`，属于合法信息。
- 不提供敌人弹药、生命、现金及其余库存。
- `parts` 为 `head / chest / abdomen`，只是当前合法视线采样，不保证未来命中，也不证明遮挡、穿透或完整弹道模型。

### `sounds`

- `direction`：`self / unknown / left / right / center`；立体声不能区分前后。
- `distance_band`：`self / unknown / near / mid / far`；普通有位置的声音 `near < 8 m`、`mid < 20 m`，否则 `far`；仅滤波的提示保留 `unknown`。
- 不提供发声席位、队伍、方位角或精确声源。
- `heard` 是空的历史兼容字段，不能套用旧声音枚举 / 距离阈值。

### `bomb`

- `state` 与 `fuse_end_tick` 始终存在；敌方隐藏信息可能只有 `unknown` 与 `null`。
- `id`、`carrier`、`position`、`site` 只在本队进攻或合法可见时提供；公开安装时钟不披露隐藏包点。
- `plant_progress` 仅属当前安放者；`defuse_progress`、`defuse_duration` 仅属当前拆除者。

### 不提供的信息

合同不包含 `scenario_seed`、`map.render`、敌人 HP / 现金 / 库存，以及全知 `audio_events` / `audio_ambient`。观众音频、全知帧与训练 / 录像导出均不授权扩大策略输入；不能从全知录像重建并冒充合法观察。

### 首拍示例

下面是官方 SDK 探针展示的首拍字段投影（不是完整回调输入；完整首拍另有 `me` 与静态 `map`）：

```json
{
  "seat": 0,
  "team": 0,
  "role": 0,
  "map_id": "dust2-cs2-v54",
  "static_schema_hash": "b0c308526d55e56e3a50a5ecf9bdd1b70a02daf560a9a8157931f3b340fb8d66",
  "match_tick": 0,
  "phase": "buy",
  "visible": [],
  "sounds": [],
  "bomb": {
    "state": "unknown",
    "fuse_end_tick": null
  }
}
```

`map` 只在首拍发送；之后的观察保留 `map_id` 与 `static_schema_hash`。缓存与身份核验见 [`maps.md`](maps.md)。

## 动作合同

返回 JSON 对象；`{}` 合法。缺字段补中性默认值；额外键、非有限数、用 bool 充数、错误枚举或类型非法，运行时**不会**替你裁剪越界值。

| 字段 | 类型 / 取值 | 说明 |
| --- | --- | --- |
| `move_forward`, `move_right`, `yaw_rate`, `pitch_rate`, `climb` | `[-1,1]` 有限数，默认 0 | 移动 / 转向 |
| `jump`, `crouch`, `duck`, `walk`, `fire`, `fire_secondary`, `reload`, `sprint`, `ads` | bool，默认 false | `duck` 是 `crouch` 别名 |
| `weapon_slot` | 整数 0/1/2，默认 1 | 0 主武器、1 副武器、2 刀 |
| `zoom_level` | 整数 0/1/2，默认 0 | 具体武器决定支持的倍率层 |
| `ladder` | `none / attach / detach`，默认 `none` | 梯子交互 |
| `buy` | `none` 或冻结目录 ID | 购买武器 / 装备 |
| `refund_item_id` | `null` 或合资格物品句柄 / 来源种类字符串 | 退款 |
| `drop` | 至多 128 字符的字符串 | `none` 或库存槽 / 炸弹请求 |
| `pickup_id` | `null` 或非空物品句柄，至多 128 字符 | 配合 `use="pickup"` |
| `use` | `none / plant / defuse / pickup` | 目标交互 |
| `throw` | `none / hegrenade / flashbang / smokegrenade / molotov / incgrenade / decoy` | 投掷物 |
| `throw_state` | `idle / prime / release / cancel`，默认 `idle` | 投掷阶段 |
| `throw_mode` | `full / lob / drop`，默认 `full` | 投掷力度 |
| `signal` | 整数 0–15，默认 0 | 队内信号 |
| `message` | 可选严格 `{kind, zone, value}` | `kind` 属于 `MESSAGE_KINDS`，`zone` 是首次 `map.route_landmarks` 的键，`value` 为整数 0–15 |

约束与语义：

- 资源冲突、缺装备、阶段限制、距离与冷却由引擎裁决。
- 冻结（`buy`）与 `post` 阶段禁用开火；装填和狙击枪射击会退镜。
- 投掷需遵守预备 / 释放 / 取消状态和力度；仅返回道具种类不证明成功投出。
- 语法合法但当前不可用的请求可产生**拒绝回执**，不一定记策略故障。

合法请求示例（彼此独立，不保证成功）：

```json
[
  {"buy": "armor"},
  {"use": "plant"},
  {"use": "defuse"},
  {"throw": "smokegrenade", "throw_state": "prime", "throw_mode": "lob"},
  {"throw": "smokegrenade", "throw_state": "release", "throw_mode": "lob"}
]
```

## Python 示例

官方最小生命周期示例（只演示协议，不包含寻路或战斗）：

```python
_map = None
_seat = None


def init(context):
    global _map, _seat
    if context["contract_id"] != "rsi-fps-5.5":
        raise ValueError("Unexpected contract")
    _map, _seat = None, context["seat"]


def act(observation):
    global _map
    if "map" in observation:
        _map = observation["map"]
    if not observation["me"]["alive"] or observation["phase"] != "live":
        return {}
    # Protocol example only: slow forward movement, no navigation or combat.
    return {"move_forward": 0.25, "walk": True}
```

## 相关文档

- [maps.md](maps.md) — 五图、选图、坐标与 `map` 结构
- [fps54-catalogue.json](fps54-catalogue.json) — 冻结武器 / 装备 / 投掷物
- [agx-submit skill](../../.claude/skills/agx-submit/SKILL.md) — 预算、打包、故障语义与 Python 上传
- [baseline-compatibility.md](baseline-compatibility.md) — 当前 `agent.py` 的差异
