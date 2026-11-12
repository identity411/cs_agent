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
| `tests/` | 本地回归测试（移动 / 路径点 / 卡住恢复） |
| `docs/` | 规范、规则、badcase 与提交版本快照 |
| `.claude/skills/agx-submit/` | Python 提交与归档 skill |
| `.claude/skills/agx-match-query/` | 只读对局 / 公开回放查询与报告 skill |
| `.env.example` | 单账户 / 多账户 `.env` 模板（`.env` 本身 gitignored） |
| `data/` | `collect` 生成的按账户数据（gitignored） |

## baseline

规则型 baseline：地图 BFS 寻路、购买、几何瞄准、下包 / 拆包与卡住恢复。接口字段与官方合同见 [`docs/spec/agent-interface.md`](docs/spec/agent-interface.md)，已知差异见 [`docs/spec/baseline-compatibility.md`](docs/spec/baseline-compatibility.md)。

## 说明

- `agent.py` 保留原 baseline 的结构与缩进；2026-11-12 针对正式对局里的出生点卡住问题修改了路径点选择、卡住恢复与转向逻辑，详见 [`docs/spec/11-12-stuck-at-spawn.md`](docs/spec/11-12-stuck-at-spawn.md)。
- 除按轮次选点外没有随机性，适合作为对照基线；移动回归见 `python3 -m unittest discover -s tests -v`。

## 文档

- [`docs/spec/`](docs/spec/README.md)：技术规范（合同 `rsi-fps-5.5`、观测 / 动作、地图、冻结目录）
- [`docs/rules/`](docs/rules/README.md)：FPS 爆破模式赛制
- [`docs/submissions/`](docs/submissions/README.md)：每次提交的代码快照与改动说明
- [`.claude/skills/agx-submit/`](.claude/skills/agx-submit/SKILL.md)：提交、预算 / 故障语义与归档流程
- [`.claude/skills/agx-match-query/`](.claude/skills/agx-match-query/SKILL.md)：对局 / 公开回放查询、席位统计与 badcase 取证
- [`docs/spec/baseline-compatibility.md`](docs/spec/baseline-compatibility.md)：当前 baseline 与官方合同的差异
- [`docs/spec/11-12-empty-primary-switch-reload.md`](docs/spec/11-12-empty-primary-switch-reload.md)：空弹主武器切枪 / 换弹 badcase
- [`docs/spec/11-12-stuck-at-spawn.md`](docs/spec/11-12-stuck-at-spawn.md)：出生点卡住 / 整回合不交战 badcase
- [`docs/spec/11-12-economy-rotation-combat.md`](docs/spec/11-12-economy-rotation-combat.md)：v0.01 对局的 5 类非卡住 badcase（经济 / 转点 / 走路 / 蹲射 / 换弹）

## 提交状态

- 2026-11-12：`1112-v0.01` 通过 Python ZIP admission，版本 `1` 已激活。详见 [`docs/submissions/1112-v0.01/README.md`](docs/submissions/1112-v0.01/README.md)。
- 2026-11-12：首场正式对局结束（`nevaio-r3-v54`，team 1 11–13 负）；公开回放发现出生点卡住导致 14/24 回合 0 发射。修复版已作为 [`1112-v0.02`](docs/submissions/1112-v0.02/README.md) 提交，admission `passed`，version `2` 已激活，待新对局验证。
- 上述版本与状态只跟踪 `main` 账户；其他账户用 `accounts --check`、`collect` 或批量提交的 `--receipt-out` 查看。
- 上传 / 准入 / 激活成功不代表完整对局、比分或排名。
