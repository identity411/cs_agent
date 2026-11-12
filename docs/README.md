# 文档

本目录保存本仓库（FPS「多人枪战：爆破模式」agent）的开发参考。

| 目录 | 内容 |
| --- | --- |
| [`spec/`](spec/README.md) | 技术规范：合同、观测 / 动作、地图、冻结目录 |
| [`rules/`](rules/README.md) | FPS 爆破模式赛制 |
| [`submissions/`](submissions/README.md) | 每次提交的完整代码快照、改动说明与元数据 |

## 资料状态

- `rules/fps-bomb.md` 与 `spec/` 下的合同文档：据 AGX「多人爆破 · AI 助手开发指南」，合同 `rsi-fps-5.5`（2026-11-12 版）整理。
- 平台通用说明与投掷物完整机制以 AGX 官网 / 官方指南为准，不在本仓库重复。
- 官方指南声明这是**闭门候选合同**，不表示赛事已开放；历史对局保留自己的合同。
- [`spec/baseline-compatibility.md`](spec/baseline-compatibility.md) 记录当前 `agent.py` 与该合同的差异。修正前不要假设 baseline 可直接使用。
- 2026-11-12：baseline 已作为 [`v001-first-python-submission`](submissions/v001-first-python-submission/README.md) 通过 Python 提交准入并激活版本 1；这不等于完整对局或得分成功。

`map.nav` 在完整五图 / 对局中的行为，以及正式对局验收仍待核实；见 [`spec/README.md`](spec/README.md) 的待补清单。
