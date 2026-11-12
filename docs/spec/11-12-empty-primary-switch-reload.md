# Badcase：空弹主武器不切枪、不换弹

Status: **2026-11-12 对局已观察：A/C 未出现，B 出现；该场主瓶颈是卡住（见 [11-12-stuck-at-spawn.md](./11-12-stuck-at-spawn.md)）**
Date: 2026-11-12
Related specs: [agent-interface.md](./agent-interface.md)（`me.weapons`、动作槽、`reload_until` / `shot_ready`）· [baseline-compatibility.md](./baseline-compatibility.md)（“武器干弹”高风险项）· [fps-bomb.md](../rules/fps-bomb.md)（回合与保留装备）· [agx-match-query skill](../../.claude/skills/agx-match-query/SKILL.md)（对局/回放查询）

> **2026-11-12 对局结论（match `da110811-9f35-4c86-9492-b322b1302391`，seat 7）**：R10 主武器为 `m4a1 20/60`，空仓换弹后 reserve 40，没有 `0/0`，因此 **A 未出现**；R10 空仓换弹期间 `active_slot` 始终为 0、没有切 usp，**B 出现**；换弹完成 `62409` 后 `reload_until=null` 并恢复开火，**C 未出现**。该场真正的瓶颈是出生点/近点卡住：14/24 回合 0 发射，详见 [11-12-stuck-at-spawn.md](./11-12-stuck-at-spawn.md)。

## 变更记录

### 2026-11-12
- 创建 badcase。静态确认 [agent.py](../../agent.py) 的选槽与 `ready` 逻辑；用合成 observation 复现 A/B/C 三种表现。
- 正式对局 `da110811-9f35-4c86-9492-b322b1302391` 取证：A/C 未出现，B 出现；该场主瓶颈是出生点卡住，见 [11-12-stuck-at-spawn.md](./11-12-stuck-at-spawn.md)。

## 0. 文档目的

把“空弹主武器不切枪、不换弹”固化为可复现、可判定的 badcase，供 demo / 对局验证：

- 给出最小复现状态；
- 说明 demo 里要记录哪些 observation 字段、怎样判定现象成立；
- 区分**已确认的代码行为**与**需要实测的引擎语义**；
- 给出修复后的验收标准。

本文不重新定义合同字段；字段语义以 [`agent-interface.md`](./agent-interface.md) 为准。

## 1. 结论

`act()` 选择武器槽时只看“0 号槽是否存在”，不看“0 号槽是否还能开火”（`agent.py:224-225`）；`combat()` 的 `ready` 只看 `ammo` 与 `reload_until`（`agent.py:126-127`）。因此有三种相关表现：

| 场景 | 主武器状态 | 当前代码行为 | 结果 |
| --- | --- | --- | --- |
| **A** | `ammo=0, reserve=0` | 固定 `weapon_slot=0`；不发 `reload` | 空枪；不切副武器/刀；不开火 |
| **B** | `ammo=0, reserve>0` | 固定 `weapon_slot=0`；发 `reload` | 换弹期间仍占 0 槽；有可见敌人时不会先用副武器 |
| **C** | `ammo>0`，但 `reload_until` 是过去的 tick | `not gun["reload_until"]` 为假 | `ready=false`，可能永远不开火（**待实测**引擎是否保留过去 tick） |
| **D** | `ammo>0, reload_until=null` | 正常 | 瞄准对齐后 `fire=true`（对照） |

> 术语说明：严格说，**B 里代码是会发 `reload` 的**；“不会换弹”不是指所有空弹情况。A 是确定的行为缺陷（没有备弹可换时也不会切枪）；B 是相关观察项（代码会换弹，但换弹期间不切枪，是否算缺陷取决于切换是否会取消换弹）；C 是待实测的引擎语义风险（换弹完成后可能不再开火）。demo 记录时请把 A/B/C 分开。

## 2. 最小复现状态

| 字段 | 要求 |
| --- | --- |
| `phase` | `live`（购买阶段不会触发 `combat`） |
| `me.alive` | `true` |
| `me.blind_ticks` | `0`（否则 `act` 不走 `combat`） |
| `me.weapons[0]` | 存在；A/B 为 `ammo=0`；A 额外 `reserve=0`，B 为 `reserve>0` |
| `me.weapons[1]` | 存在且 `ammo>0`（用来判断是否真的“没有可切的枪”） |
| `me.weapons[2]` | 存在（刀，用作最后的 fallback） |
| `me.active_slot` | 记录观测值，不要假定一定等于代码选择的槽 |
| `me.switch_until` / `me.reload` | 记录；用于判断是否正在切枪/换弹 |
| `visible` | 至少一个可见敌人，`parts` 含 `chest` / `head`，距离适中且无遮挡 |
| 瞄准 | 让 `abs(yaw)` / `abs(pitch)` 足够小，排除“没瞄准所以没开火”的干扰 |
| `map.sites` / `map.nav` | 非空，先排除地图异常导致的崩溃 |

如果 demo 环境不提供“把备弹打空”或“直接设置 `reserve=0`”的入口，可以使用合成 observation 或本地 Arena 覆盖；在记录里注明用的是真实对局还是合成状态。

## 3. Demo 复现步骤

1. 进入一个 `live` 回合，记录 `seat`、`round_index`、`match_tick`、`phase`、`active_slot`。
2. 把主武器打到 `ammo=0`：
   - **A**：继续把 `reserve` 打到 `0`；
   - **B**：保留 `reserve>0`，观察 `reload` 是否发出以及何时完成。
3. 让一个敌人进入 `visible`，把准星对准其 `chest` / `head`，保持至少 20 个决策 tick（20 Hz 下约 1 秒）。
4. 每个决策 tick 同时打印 **observation 和 action**，不要只打印 action：

```python
for _ in range(20):
    obs = observe()              # demo / 本地 probe 的观察
    action = agent.act(obs)
    me = obs["me"]
    print({
        "tick": obs["match_tick"],
        "active_slot": me.get("active_slot"),
        "w0": me["weapons"][0],
        "w1": me["weapons"][1],
        "switch_until": me.get("switch_until"),
        "reload": me.get("reload"),
        "action": {k: action.get(k) for k in
                   ("weapon_slot", "reload", "fire", "move_forward")},
        "receipts": obs.get("receipts"),
    })
```

5. 记录引擎是否自动切枪：`me.active_slot` 是否变化、`switch_until` 是否变化、`receipts` 是否有拒绝回执。**如果引擎自动切到副武器，但 action 仍然请求 0 槽，也要记录**——这说明代码在跟引擎对抗，不是“没有问题”。
6. 对 **C**：在 `reload` 完成后记录 `weapons[0].reload_until`、`me.reload`、`match_tick`，再让敌人可见，观察 `fire` 是否恢复。若 `reload_until` 已变成 `null`，C 不会出现；若保留过去的 tick，C 成立。
7. 记录 demo / 对局的来源（比赛 ID、回放、本地 probe、合成 observation），避免把合成结果当成正式对局结果。

## 4. 判定标准

### 4.1 现象成立

- **A 成立**：连续 ≥5 个决策 tick（约 250 ms）满足：
  - `me.weapons[0].ammo == 0`
  - `me.weapons[0].reserve == 0`
  - `me.weapons[1].ammo > 0`
  - `action.weapon_slot == 0`
  - `action.reload` 缺失或 `false`
  - `action.fire == false`

  这时应切枪却仍拿着空主武器，即可确认。

- **B 观察项（不一定算 badcase）**：`reload` 进行期间 `action.weapon_slot` 始终为 0、没有切到有弹的副武器；或 `reload` 完成后（`ammo>0`）仍然不开火。**是否算缺陷取决于切换是否会取消换弹**（第 8 节第 2 条）：引擎允许边换边切而代码不切，记为可改进；切枪会取消换弹，则 B 是策略取舍，但必须有明确策略，不能一直占着空枪。
- **C 成立**：`ammo>0`、`reload_until` 是过去的 tick、瞄准对齐，但 `fire` 始终为 `false`。先确认引擎是否真的保留过去 tick；如果引擎会清成 `null`，C 不成立。

### 4.2 “被引擎掩盖”也要记录

如果引擎在空弹时自动切到副武器，而 `action.weapon_slot=0` 被忽略或被拒绝：

- 结论写“现象被引擎自动纠正/拒绝”，不要写“代码没问题”；
- 附上 `active_slot`、`switch_until`、`receipts`；
- 因为一旦引擎版本变化或取消自动纠正，代码仍会回到空枪状态。

### 4.3 排除项

- 只是瞄准未收敛（`abs(yaw)` / `abs(pitch)` ≥ 阈值）导致 `fire=false`，不算本 badcase；
- `blind_ticks > 0`、`phase != live`、死亡、地图异常导致的 `{}`，不算；
- 只观察 `action` 不观察 `active_slot` / `receipts`，不足以判定“是否被引擎掩盖”。

## 5. 代码路径与根因

### 5.1 当前代码

选槽与换弹（`agent.py:224-228`）：

```python
slot = 0 if m["weapons"][0] is not None else 1
gun = m["weapons"][slot]
action = {"weapon_slot": slot}
if gun and gun["ammo"] == 0 and gun["reserve"]:
    action["reload"] = True
```

开火就绪（`agent.py:126-127`）：

```python
ready = bool(gun and gun["ammo"]
             and not gun["reload_until"])
```

### 5.2 根因

1. **“存在”被当成“可用”**：只要 `weapons[0]` 不是 `None`，就永远选 0 槽，不检查 `ammo` / `reserve`。
2. **没有 fallback**：主武器空弹时不会切 1 槽（副武器）或 2 槽（刀）。
3. **`reload_until` 用真值判断**：合同说它是绝对结束 tick 或 `null`，当前写法在“结束后保留过去 tick”的实现下会永久压制开火。
4. **忽略就绪阈值**：`shot_ready`、`switch_until` 未参与 `ready`；切枪/换弹后的最早开火时机可能被错过或请求被拒。
5. **忽略 `active_slot`**：每 tick 都按自己的判断发 `weapon_slot`，可能与引擎自动切枪互相打架。
6. **相关但非本 badcase**：弹匣只剩 1 发时不提前换弹，会在交火中被迫空仓；这属于策略问题，不是“空弹后不切枪”。

## 6. 修复建议（不改战术）

1. **按可用性选槽**，不要按“槽位是否存在”选：

```python
def pick_slot(me):
    guns = me["weapons"]
    for slot in (0, 1):          # 主武器、副武器
        gun = guns[slot]
        if gun and (gun.get("ammo", 0) > 0 or gun.get("reserve", 0) > 0):
            return slot
    return 2                     # 刀

def is_reloading(gun, tick):
    until = gun.get("reload_until")
    return until is not None and tick < until

def ready(gun, me, tick):
    return bool(
        gun and gun.get("ammo", 0) > 0
        and not is_reloading(gun, tick)
        and tick >= (gun.get("shot_ready") or 0)
        and tick >= (me.get("switch_until") or 0)
    )
```

2. **A 场景**：主武器 `ammo=0, reserve=0` 时切 1 槽（如果副武器有弹），否则切 2 槽；不要发 `reload`，也不要在空枪上发 `fire`。
3. **B 场景**：先 probe 一条语义——**切枪是否取消换弹**：
   - 如果取消：安全时留在 0 槽换完，交火中切副武器；
   - 如果不取消：换弹后立刻切副武器，换完后切回。
   两种策略都要求“有弹的副武器可用时，不长时间占着空主武器”。
4. **C 场景**：用 `match_tick < gun["reload_until"]` 或 `me.reload > 0` 判断是否仍在换弹，不用真值；换弹完成后立即重新评估 `ready`。
5. 每 tick 重新评估，不要一轮锁定一个槽；用 `active_slot` 读取引擎当前状态，用 `switch_until` 避免反复横跳。
6. 增加测试（合成 observation 即可）覆盖 A/B/C/D，尤其是“副武器有弹”和“换弹完成”两条边界。

## 7. 验收标准

- [ ] **A**：主武器 `0/0`、副武器有弹时，最多 2 个决策 tick 内 `action.weapon_slot` 变为 1；副武器无弹时变 2；不再对空主武器发 `fire`。
- [ ] **B**：不出现“既没有有效 `reload`、也不切枪、也不开火”的连续 tick；如果选择换弹，必须能在合理时间内完成并恢复开火；如果选择切枪，最多 2 个决策 tick 内切到有弹副武器。
- [ ] **C**：换弹完成后，瞄准对齐时 `fire` 在 2 个决策 tick 内恢复；不再被过去的 `reload_until` 永久压制。
- [ ] **D（回归）**：主武器有弹时仍选 0 槽；副武器有弹、主武器无弹时选 1 槽；两者都空时选 2 槽。
- [ ] demo / 合成测试记录里同时有 observation 与 action；若引擎自动切枪，记录中能看出代码是否在对抗。
- [ ] 不改变移动、寻路、下包/拆包等与本 badcase 无关的行为。

## 8. 待确认

1. 引擎是否会在主武器空弹时自动切副武器？是否会拒绝 `weapon_slot=0` 的请求？回执长什么样？
2. 切枪是否会取消正在进行的 `reload`？`reload_until` 是否会被清零？
3. 换弹结束后 `reload_until` 是 `null` 还是保留过去的 tick？`me.reload` 是剩余秒数还是 tick？
4. `shot_ready` / `switch_until` 是否确实是绝对物理 tick 阈值？单位与 `match_tick` 是否一致？
5. `weapons[1]` / `weapons[2]` 是否总是存在且非 `null`？刀是否始终可用？
6. 空弹时发 `fire` 是静默忽略、拒绝回执，还是触发自动换弹？
7. `reserve` 是否只在回合开始补满？回合中打空后要等到下一回合吗？
8. demo 环境能否直接把 `reserve` 设为 0，还是必须靠实际射击打空？
9. `weapon_slot` 是“请求”还是“绝对设置”？如果引擎忽略请求，修复后应如何验证？
10. 是否存在“切枪后 `switch_until` 禁止开火”的窗口？窗口多长？

## 9. 证据记录

| 日期 | 场景 | 来源（demo / 对局 / probe） | seat | round / tick | 观测（w0 / w1 / active_slot） | action（slot / reload / fire） | 结论 | 备注 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2026-11-12 | A/B/C | 正式对局 public replay `da110811-9f35-4c86-9492-b322b1302391` | 7 | R10 / 60004–65133 | `m4a1 20/60` → 空仓换弹（62224）→ `20/40`；`active_slot=0`；`usp 12/24` | 0 槽；空仓时 `reload=true`；换弹期间无切枪；62409 后恢复开火 | A 未出现；B 出现；C 未出现 | 该场主瓶颈是卡住，见 [11-12-stuck-at-spawn.md](./11-12-stuck-at-spawn.md) |
|  | A |  |  |  |  |  |  |  |
|  | B |  |  |  |  |  |  |  |
|  | C |  |  |  |  |  |  |  |

> 结论只写“成立 / 被引擎掩盖 / 不成立 / 未完成”，并附上最小证据；不要把“准入通过”或“单个 tick”当作完整对局证据。

## 附录 A：合成观测结果（2026-11-12）

用合成 observation 调用 `agent.act`，`match_tick=100`，瞄准已对齐，敌人位于 10 m 正前方，副武器有弹。结果：

| 场景 | 主武器状态 | 当前 action | 说明 |
| --- | --- | --- | --- |
| A | `ammo=0, reserve=0` | `weapon_slot=0, reload` 缺失, `fire=False` | 空枪；不切枪 |
| B | `ammo=0, reserve=30` | `weapon_slot=0, reload=True, fire=False` | 会换弹，但仍占 0 槽 |
| C | `ammo=30, reload_until=5`（`match_tick=100`） | `weapon_slot=0, reload` 缺失, `fire=False` | 过去的 tick 被当成“仍在换弹” |
| D | `ammo=30, reload_until=null` | `weapon_slot=0, fire=True` | 对照组，能正常开火 |

这些是**合成观测结果**，只证明代码路径；真实 demo 仍需按第 3、4 节记录。C 是否出现取决于引擎是否保留过去的 `reload_until`，因此标为待实测。
