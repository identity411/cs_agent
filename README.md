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

## baseline 策略

1. **地图与寻路**：从 `map["nav"]` 读取节点和边；`walk` 边双向，其他边（如 `ladder`）单向。就近吸附到节点后 BFS，输出「目标点 + 沿途节点坐标」路径。
2. **购买（buy 阶段）**：
   - 防守方没有拆弹器且现金 ≥ 400：买 `defusekit`
   - 主武器为空：进攻买 `ak47`（2700），防守买 `m4a1`（2900）
   - 护甲 < 50 且现金 ≥ 650：买 `armor`
3. **战斗**：锁定最近的可见敌人；按头 / 胸 / 腹高度、敌人是否蹲伏和自身眼高修正俯仰；补偿 `aim_punch`；手枪点射、步枪连发；`|yaw|`、`|pitch|` 足够小才开火。
4. **移动与脱困**：沿路径朝下一个航点移动（`walk=True`）；位置停滞超过 20 tick 后左右侧移并周期性跳跃，超过 80 tick 清空路径重新寻路。
5. **目标**：按 `(round_index + seat % 2) % len(sites)` 选点；进攻方带包进点即下包（`use="plant"`）；防守方在炸弹安装后靠近到 2m 内拆包（`use="defuse"`）。

## 用到的观测 / 动作字段

> 以下整理自 `agent.py` 的实际用法，字段完整定义以官方文档为准。

观测：`map.sites`、`map.nav.nodes/edges`、`me`（位置、朝向、蹲伏、武器、护甲、现金、携包等）、`visible`、`bomb`、`side`、`phase`、`round_index`、`seat`、`match_tick`。

动作：`move_forward`、`move_right`、`yaw_rate`、`pitch_rate`、`jump`、`crouch`、`walk`、`fire`、`weapon_slot`、`reload`、`use`、`buy`。

> 官方合同 `rsi-fps-5.5` 的完整字段见 [`docs/spec/agent-interface.md`](docs/spec/agent-interface.md)；当前 baseline 与合同的差异见 [`docs/spec/baseline-compatibility.md`](docs/spec/baseline-compatibility.md)。

## 说明

- `agent.py` 按原 baseline（3 部分、共 177 行）逐行还原，保留原文件结构与缩进。
- 除按轮次选点外没有随机性，适合作为对照基线。

## 文档

- [`docs/spec/`](docs/spec/README.md)：技术规范（合同 `rsi-fps-5.5`、观测 / 动作、地图、目录、预算与提交）
- [`docs/rules/`](docs/rules/README.md)：比赛规则（平台参赛规则、MR12、经济、目标、投掷物）
- [`docs/submissions/`](docs/submissions/README.md)：每次提交的代码快照与改动说明
- [`docs/spec/baseline-compatibility.md`](docs/spec/baseline-compatibility.md)：当前 baseline 与官方合同的差异
