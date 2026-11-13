# cs_agent

FPS 竞赛的规则型 baseline agent（“complete starter” 完整版本）。

## 快速开始

`agent.py` 仅依赖 Python 标准库，平台加载时需要两个入口：

```python
def init(context): ...
def act(observation): ...
```

本仓库的 `agent.py` 已包含这两个入口，直接作为提交文件即可。

## 多账户（多开）

在 repo 根 `.env` 里把新账户写成 `RSI_ACCOUNT_<NAME>_API_KEY`，可选 `_AGENT_ID`、`_URL`、`_COMPETITION_ID`；原有 `RSI_ACCOUNT_API_KEY` / `RSI_AGENT_ID` 自动作为默认账户 `main`。也兼容编号写法：`RSI_ACCOUNT_API_KEY_2` 会作为账户 `account2`（可选 `RSI_ACCOUNT_AGENT_ID_2` / `RSI_AGENT_ID_2`）。完整模板见 [`.env.example`](.env.example)。账户名以字母开头，只含字母、数字、下划线；key 也可以放在 macOS Keychain 的 `agx-api-key-<name>`。

```dotenv
RSI_URL=https://your-agx-instance.example
RSI_COMPETITION_ID=2a97f94f-816a-52b7-b4b8-5925db160245
RSI_COMPETITION_FPS=2a97f94f-816a-52b7-b4b8-5925db160245
RSI_COMPETITION_RACING=1eb91364-950b-5725-aa4b-3501b16860ec
RSI_ACCOUNT_API_KEY=main-account-key
RSI_AGENT_ID=
RSI_ACCOUNT_ALICE_API_KEY=alice-account-key
RSI_ACCOUNT_ALICE_AGENT_ID=          # 可省略，提交时自动发现
RSI_ACCOUNT_COMPETITION_ID_2=2a97f94f-816a-52b7-b4b8-5925db160245
RSI_ACCOUNTS=main,alice              # 可选：显式顺序，也用于 Keychain-only 账户
```

以后不用再粘 UUID：`--competition-id fps|racing` 或 `--game-id fps|racing` 会从 `RSI_COMPETITION_<GAME>` 解析；`RSI_ACCOUNT_<NAME>_COMPETITION_ID` 可以写 UUID 或别名。工具不会打印 key，只输出 `sha256:<12位>` 指纹。查看账户和只读状态：

```sh
python3 .claude/skills/agx-submit/scripts/agx_submit.py accounts --json
python3 .claude/skills/agx-submit/scripts/agx_submit.py accounts --check
# 赛车；只写游戏名，不写比赛 UUID：
python3 .claude/skills/agx-submit/scripts/agx_submit.py accounts --check --game-id racing
# CS：
python3 .claude/skills/agx-submit/scripts/agx_submit.py accounts --check --game-id fps
python3 .claude/skills/agx-match-query/scripts/agx_matches.py round --account alice --game-id fps
```

按账户收集战绩 / 排名 / 对局数据（只读；默认收集全部账户）：

```sh
python3 .claude/skills/agx-match-query/scripts/agx_matches.py collect --replays
python3 .claude/skills/agx-match-query/scripts/agx_matches.py collect --account alice --json
python3 .claude/skills/agx-match-query/scripts/agx_matches.py collect --game-id racing --replays
```

数据写在 repo 根的 `data/accounts/`（gitignored）：每账户 `snapshot.json`、`snapshots/<UTC>.json` 历史、可选的 `matches/<match_id>/` 公开回放；根目录 `index.json` 汇总。

批量提交同一 ZIP（先不带 `--yes` 查看只读计划，再确认执行）：

```sh
python3 .claude/skills/agx-submit/scripts/agx_submit.py build --submission-dir . --output /tmp/agx-agent.zip
python3 .claude/skills/agx-submit/scripts/agx_submit.py submit --all-accounts --zip /tmp/agx-agent.zip
python3 .claude/skills/agx-submit/scripts/agx_submit.py submit --all-accounts --zip /tmp/agx-agent.zip \
  --yes --receipt-out /tmp/agx-receipt.json
# 赛车或其他比赛只加 --game-id；账户默认比赛由 RSI_ACCOUNT_<NAME>_COMPETITION_ID 决定：
python3 .claude/skills/agx-submit/scripts/agx_submit.py submit --account account2 \
  --game-id racing --zip /path/to/racing-agent.zip
```

- `--agent-id` / `--idempotency-key` 只能用于单账户；批量时每个账户用自己的 agent id，并自动生成稳定的幂等 key。
- 批量 preflight 任一账户失败时不会上传任何账户；执行阶段某一账户失败会继续其他账户，最后退出码为 2。
- `--receipt-out` 记录每账户的 bundle / admission / version / entry，不含 key。
- 上传、准入、激活成功都不等于完整对局、比分或排名。多账户参与前请先确认平台/赛事规则允许。

## 文件结构

| 路径 | 说明 |
| --- | --- |
| `agent.py` | baseline：地图寻路、购买、瞄准射击、下包 / 拆包 |
| `map_patches.py` | 地图修补抽象层：soft hazard、台阶跳阈值；agent 只调用 `for_map()` |
| `scripts/` | 本地复现 / nav 模拟脚本（R2 包点 hold、`simulate_nav.py`） |
| `tests/` | 本地回归测试（A* / 攻击路线 / 移动 / 路径点 / 卡住恢复 / 战斗超时） |
| `docs/` | 规范、规则、badcase 与提交版本快照 |
| `.claude/skills/agx-submit/` | Python 提交与归档 skill |
| `.claude/skills/agx-match-query/` | 只读对局 / 公开回放查询与报告 skill |
| `.env.example` | 单账户 / 多账户 `.env` 模板（`.env` 本身 gitignored） |
| `data/` | `collect` 生成的按账户数据（gitignored） |

## baseline

规则型 baseline：地图 A* 寻路、dust2 进攻路线（A 大 / A 小 / B 洞 / B 门）、sprint / 战斗超时、前进跳 / 台阶跳、购买、几何瞄准、下包 / 拆包与卡住恢复。地图相关的 hazard / 台阶阈值在 `map_patches.py` 的 `MapPatch` 里，`agent.py` 通过 `map_patches.for_map(map_id)` 读取抽象结果。接口字段与官方合同见 [`docs/spec/agent-interface.md`](docs/spec/agent-interface.md)，已知差异见 [`docs/spec/baseline-compatibility.md`](docs/spec/baseline-compatibility.md)，寻路与路线见 [`docs/spec/11-12-pathing-routes.md`](docs/spec/11-12-pathing-routes.md)。

## 说明

- `agent.py` 保留原 baseline 的结构与缩进；2026-11-12 针对正式对局里的出生点卡住问题修改了路径点选择、卡住恢复与转向逻辑，详见 [`docs/spec/11-12-stuck-at-spawn.md`](docs/spec/11-12-stuck-at-spawn.md)。当前版本又把 BFS 改为 A*，并加入 dust2 attackRoutes、R2 包点 patrol、sprint、战斗超时、plant zone 与前进跳 / 台阶跳，见 [`docs/spec/11-12-pathing-routes.md`](docs/spec/11-12-pathing-routes.md)；已随 v0.03/v0.04 提交/激活，尚未用新对局验证。
- v0.04 在 v0.03 之上加入 **post-v0.03 修正**：T 方 pre-plant patrol 振荡、dust2/Mirage 旧卡点 soft hazard（移到 `map_patches.py`）、前进跳 / 台阶跳、**临时 T 兜底（`round_tick>=40 s` 仍未下包就直接去 CT 出生点）**；已提交/激活，仍需新对局验证（`scripts/simulate_nav.py` 仅本地）。Mirage R6/R10 与 CT A 台阶证据见 [`docs/spec/11-12-mirage-spawn-jump.md`](docs/spec/11-12-mirage-spawn-jump.md)。
- 2026-11-12 14:00 UTC v0.03 对局（Mirage，`d24bd037…`）：main seat 3（team 0，13–9 胜），account2 seat 9（team 1，9–13 负）；main CT 侧 R13/15/17/19/21 在 `(42.8,66.4)` 附近卡住，当前工作区已加 Mirage soft hazard，nav 模拟可绕开。
- Dust2 T 方已接入用户录制的 2002 帧轨迹闭环跟随：按实时位置与准星纠偏，原地预瞄逐拍推进，可见敌人时停下交火，偏离路线时使用 A* 接回；仅在 Dust2 静态哈希匹配时启用。详见 [`1113-v0.06`](docs/submissions/1113-v0.06/README.md)；当前全量测试 59/59 通过，正式对局效果仍待验证。
- 2026-11-13 开火距离分层：只有近距（≤ Mirage A 中央→警家 32.5 m）且身体可见才扫射；中距只点头、每 42 ticks（0.7 s）点一发；超过 1.5×（48.75 m）仍只点头，但降为每 60 ticks（1 s）一发。见 [`docs/spec/11-13-fire-range-bands.md`](docs/spec/11-13-fire-range-bands.md)；本地 82/82 测试通过，待新对局验证。
- 2026-11-13 战斗稳定性：18-tick 战斗记忆桥接可见性闪烁、目标锁防止 25 m/48 m 目标来回跳、战斗不再蹲起；录制轨迹 20 ticks 无进度即侧移绕开卡住的队友，连续失败后放弃路线回退 A*。见 [`docs/spec/11-13-combat-stability.md`](docs/spec/11-13-combat-stability.md)；本地 86/86 测试通过。

## 文档

- [`docs/spec/`](docs/spec/README.md)：技术规范（合同 `rsi-fps-5.5`、观测 / 动作、地图、冻结目录）
- [`docs/rules/`](docs/rules/README.md)：FPS 爆破模式赛制
- [`docs/submissions/`](docs/submissions/README.md)：每次提交的代码快照与改动说明
- [`.claude/skills/agx-submit/`](.claude/skills/agx-submit/SKILL.md)：提交、预算 / 故障语义与归档流程
- [`.claude/skills/agx-match-query/`](.claude/skills/agx-match-query/SKILL.md)：对局 / 公开回放查询、席位统计与 badcase 取证
- [`docs/spec/baseline-compatibility.md`](docs/spec/baseline-compatibility.md)：当前 baseline 与官方合同的差异
- [`docs/spec/11-12-empty-primary-switch-reload.md`](docs/spec/11-12-empty-primary-switch-reload.md)：空弹主武器切枪 / 换弹 badcase
- [`docs/spec/11-12-stuck-at-spawn.md`](docs/spec/11-12-stuck-at-spawn.md)：出生点卡住 / 整回合不交战 badcase
- [`docs/spec/11-12-site-center-hold.md`](docs/spec/11-12-site-center-hold.md)：到达包点后停在中心不动（R2）badcase
- [`docs/spec/11-12-pathing-routes.md`](docs/spec/11-12-pathing-routes.md)：A* 寻路、dust2 进攻路线、sprint / 战斗超时 / plant zone、前进跳 / 台阶跳、临时 T 40 s 未下包 → CT spawn 兜底
- [`docs/spec/11-12-mirage-spawn-jump.md`](docs/spec/11-12-mirage-spawn-jump.md)：Mirage R6/R10 出生点滑动卡住、CT A 台阶与前进跳修复
- [`docs/spec/11-12-economy-rotation-combat.md`](docs/spec/11-12-economy-rotation-combat.md)：v0.01 对局的 5 类非卡住 badcase（经济 / 转点 / 走路 / 蹲射 / 换弹）
- [`docs/spec/11-12-match-observability.md`](docs/spec/11-12-match-observability.md)：对局可观测性指标（参战 / 命中 / 卡死 / 回防）与版本对比判定
- [`docs/spec/11-13-fire-range-bands.md`](docs/spec/11-13-fire-range-bands.md)：开火距离分层（近距扫射 / 中距只点头点射 0.7 s / 远距只点头点射 1 s）
- [`docs/spec/11-13-combat-stability.md`](docs/spec/11-13-combat-stability.md)：可见性闪烁下的战斗记忆 / 目标锁 / 不蹲起，录制路线被队友堵住的侧移与放弃

## 提交状态

- 2026-11-12：`1112-v0.01` 通过 Python ZIP admission，版本 `1` 已激活。详见 [`docs/submissions/1112-v0.01/README.md`](docs/submissions/1112-v0.01/README.md)。
- 2026-11-12：首场正式对局结束（`nevaio-r3-v54`，team 1 11–13 负）；公开回放发现出生点卡住导致 14/24 回合 0 发射。修复版已作为 [`1112-v0.02`](docs/submissions/1112-v0.02/README.md) 提交，admission `passed`，version `2` 已激活。
- 2026-11-12 12:00 UTC：v0.02 两场结束（main `dust2` 13–8、account2 `borgo` 13–6）。可观测性回填见 [`docs/spec/11-12-match-observability.md`](docs/spec/11-12-match-observability.md)：卡死/到点明显改善，交火参与未改善，回防启动改善但到位仍为 0；main 场公开事件为全场 0 交火异常 lobby，不用于交火结论。
- 2026-11-12 13:41 UTC：`1112-v0.03`（A* / dust2 attackRoutes / R2 包点 patrol / 战斗控制）提交到 `main` 和 `account2`；admission 均为 `passed`，`main` version `3`、`account2` version `2` 已激活。详见 [`docs/submissions/1112-v0.03/README.md`](docs/submissions/1112-v0.03/README.md)；本地 40/40 测试通过，待新对局验证。
- 2026-11-12：post-v0.03 本地 nav 模拟发现 **v0.03 在 dust2 A 回合会在 near-site patrol/via 边界来回切 goal，120 s 内 timeout**；已修（T 下包前不 patrol、via 到 `site.radius` 才关、dust2 旧卡点 soft hazard）。
- 2026-11-12 15:31 UTC：`1112-v0.04`（前进跳 / 台阶跳 / `map_patches.py` / Mirage / T 方兜底）提交到 `main` 和 `account2`；admission 均 `passed`，`main` version `4`、`account2` version `3` 已激活。详见 [`docs/submissions/1112-v0.04/README.md`](docs/submissions/1112-v0.04/README.md)；本地 53/53 测试通过，待新对局验证。
- 2026-11-13 00:14 CST：Dust2 录制轨迹跟随修正版 [`1113-v0.06`](docs/submissions/1113-v0.06/README.md) 仅提交到 `account2`；admission `passed`，account2 version `5` 已激活，`main` 仍为 version `4`。本地全量测试 59/59 通过。
- v0.01–v0.02 的状态只跟踪 `main` 账户；v0.03–v0.06 记录 `main` 和 `account2`。其他账户用 `accounts --check`、`collect` 或批量提交的 `--receipt-out` 查看。
- 2026-11-13：`1113-v0.08`（R9 刹停/点射、带包人 40 s 兜底豁免、Mirage A/B 守包 spot/look、nevaio `warm_hall` hazard + 回合清 edge penalty）提交到 `main` 和 `account2`；admission 均 `passed`，`main` version `5`、`account2` version `7` 已激活，entry code hash `4f12f28d10b7`。详见 [`docs/submissions/1113-v0.08/README.md`](docs/submissions/1113-v0.08/README.md)、[`11-13-nevaio-r9-fire-discipline.md`](docs/spec/11-13-nevaio-r9-fire-discipline.md) 与 [`11-13-post-plant-holds.md`](docs/spec/11-13-post-plant-holds.md)；本地 75/75 测试通过，待新对局验证。
- 2026-11-13：`1113-v0.10`（开火距离分层：近距扫射 / 中距只点头 0.7 s / 远距只点头 1 s，同时把 main 更新到含 v0.09 Mirage 轨迹的代码）提交到 `main` 和 `account2`；admission 均 `passed`，`main` version `6`、`account2` version `9` 已激活，entry code hash `09a4bfac4aaa`。详见 [`docs/submissions/1113-v0.10/README.md`](docs/submissions/1113-v0.10/README.md) 与 [`11-13-fire-range-bands.md`](docs/spec/11-13-fire-range-bands.md)；本地 82/82 测试通过，待新对局验证。
- 2026-11-13：`1113-v0.11`（18-tick 战斗记忆 / 目标锁 / 不蹲起；录制路线被队友堵住时侧移，连续失败放弃路线回退 A*）提交到 `main` 和 `account2`；admission 均 `passed`，`main` version `7`、`account2` version `10` 已激活，entry code hash `a77f1c7e5b22`。详见 [`docs/submissions/1113-v0.11/README.md`](docs/submissions/1113-v0.11/README.md) 与 [`11-13-combat-stability.md`](docs/spec/11-13-combat-stability.md)；本地 86/86 测试通过，待新对局验证。
- 上传 / 准入 / 激活成功不代表完整对局、比分或排名。
