# cs_agent

FPS 竞赛的规则型 baseline agent（“complete starter” 完整版本）。

## 快速开始

`agent.py` 仅依赖 Python 标准库，平台加载时需要两个入口：

```python
def init(context): ...
def act(observation): ...
```

本仓库的 `agent.py` 已包含这两个入口，直接作为提交文件即可。

## 文件结构

| 路径 | 说明 |
| --- | --- |
| `agent.py` | baseline：地图寻路、购买、瞄准射击、下包 / 拆包 |
| `docs/` | 规范、规则与提交版本快照 |
| `.claude/skills/agx-submit/` | Python 提交与归档 skill |

## baseline

规则型 baseline：地图 BFS 寻路、购买、几何瞄准、下包 / 拆包与卡住恢复。接口字段与官方合同见 [`docs/spec/agent-interface.md`](docs/spec/agent-interface.md)，已知差异见 [`docs/spec/baseline-compatibility.md`](docs/spec/baseline-compatibility.md)。

## 说明

- `agent.py` 按原 baseline（3 部分、共 177 行）逐行还原，保留原文件结构与缩进。
- 除按轮次选点外没有随机性，适合作为对照基线。

## 文档

- [`docs/spec/`](docs/spec/README.md)：技术规范（合同 `rsi-fps-5.5`、观测 / 动作、地图、冻结目录）
- [`docs/rules/`](docs/rules/README.md)：FPS 爆破模式赛制
- [`docs/submissions/`](docs/submissions/README.md)：每次提交的代码快照与改动说明
- [`.claude/skills/agx-submit/`](.claude/skills/agx-submit/SKILL.md)：提交、预算 / 故障语义与归档流程
- [`docs/spec/baseline-compatibility.md`](docs/spec/baseline-compatibility.md)：当前 baseline 与官方合同的差异

## 提交状态

- 2026-11-12：`1112-v0.01` 通过 Python ZIP admission，版本 `1` 已激活。详见 [`docs/submissions/1112-v0.01/README.md`](docs/submissions/1112-v0.01/README.md)。
- 这只表示上传 / 准入 / 激活成功，不代表完整对局、比分或排名。
