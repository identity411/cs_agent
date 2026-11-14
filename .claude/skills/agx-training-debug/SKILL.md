---
name: agx-training-debug
description: 排查 AGX 正式对局中的路线偏离、动作衔接、卡住或故障；下载本人 training.jsonl，绑定冻结版本，比较合法 observation、action 与 applied_action，并用公开回放核对结果。
---

# AGX 本人决策日志排查

目标是定位首次错误决策或状态切换，给出 job、账号、席位、冻结版本、回合和 match_tick 证据。仅查询、下载和本地分析；本 skill 不授权上传、激活或提交策略。

## 账户与数据获取

本仓库复用 `.claude/skills/agx-submit/scripts/agx_submit.py` 的 `load_dotenv()`、`resolve_account(name=...)`、`Client(account.base_url, account.key)`。从仓库根执行；只联系明确配置的 base URL，不输出 API key，不把 key 写进脚本、命令参数、报告或日志。公开回放查询可复用 `.claude/skills/agx-match-query/scripts/agx_matches.py`，具体命令读该目录的 `SKILL.md`。

先核实账号与席位，不能从公开参与者列表推断日志权限：

- `GET /api/v1/python-submissions/jobs/{job_id}/training-seats`
- `GET /api/v1/python-submissions/jobs/{job_id}/training.jsonl?seat={owned_seat}`
- `GET /api/v1/python-submissions/competitions/{competition_id}/history`：赛果、故障与 replay_available。

权限只覆盖当前账号实际拥有的冻结席位。404 可能是游客、他人席位或资源不可用；409 表示轨迹缺失/损坏；410 表示 30 天在线下载窗口到期，不能用公开权限绕过。归档状态不代表仍可在线下载。

下载支持 gzip。大日志应落本地 gitignored 的 `data/analysis/{job_id}/{account}/`，逐行读取，避免一次输出大文件。若标准库 `response.read()` 报 IncompleteRead 或 curl 报 HTTP/2 INTERNAL_ERROR，可有限重试（例如最多三次），必要时改用 HTTP/1.1。每次重试使用新临时文件，不把响应拼接到前次截断的 JSONL。密钥通过内存中的 HTTP header 或 curl 标准输入配置传递，避免 shell 插值。保留最后一次失败状态与不完整文件，报告覆盖范围。

## 导出校验与格式兼容

首行 `metadata` 绑定 job_id、seed、rules_version、participants 的 seat/team/version_id/source_hash。先比对目标账号和冻结版本，再分析。

末行必须有 `export_complete`，并核对其实际提供的行数、席位或完整性字段。缺少末行、截断 JSON 行、网络非零退出或计数不符，不能声称完整导出；已收到的完整 decision 行可用于定位该时间范围内的问题，但不能推断全局统计。metadata 的 `complete:false` 不单独判定最终导出失败，完成性要看尾记录与校验。

实际导出的 decision 行可能**没有 `type: decision`**。以 `observation` 与 `seat`/`step` 识别，其他行按实际 schema 区分 metadata、outcome、export_complete；不要因缺少 type 丢掉所有决策。本局实测字段为：

```json
{"seat":3,"step":0,"observation":{},"action":{},"applied_action":{},"fault":false}
```

`action` 是策略输出；`applied_action` 是平台应用的动作，可能补齐默认值或规范化。分别核对，不把字典缺省字段、数值浮点误差当成策略分歧。`fault` 要独立检查。`step` 不应先验等同 match_tick；FPS 对齐用 observation.match_tick、round_index、phase。

## 原因定位

1. 从用户链接提取 job_id，确认 account、seat（0-based）、网页第 seat+1 个玩家和 team。冻结版本以 metadata 的 version_id/source_hash 及赛事历史为准，不能拿当前工作区版本替代当局版本。
2. 用本人合法 observation 定位出错前后窗口：FPS 看 side、phase、round_index、bomb、me、visible、动作；先明确是开局路线、守位循环、下包回防还是战斗打断。
3. 从该版本代码的初始状态开始，按原决策顺序重放，包括 buy、死亡和回合边界；不要直接跳到问题 tick 而丢失内部状态。使用完整冻结模块集和原 init 上下文（如可获得）；确认模块解析路径，避免归档 agent.py 导入当前版本辅助模块。
4. 比较重放输出与原 action，再比较 applied_action。允许合理浮点容差及已知默认值差异，记录首个实质分歧；先验证重放可信，再解释推断出的内部状态。观察回放只复现决策，不等于重建物理模拟或证明修复后的实战结果。
5. 记录路线名、phase、cursor、entry、watchdog anchor/timer、detour 次数、abandoned、交火暂停、bomb 状态与分支返回值。优先找“上一帧仍正确，下一帧切错”的时刻，再检查前后的实际位置与动作。
6. 公开 `/replay/descriptor`、`/replay/index` 和分块 public_static/public_events/public_frames 可核对地图、碰撞结果、事件和画面。公开 frames 是约 24 Hz，不能与策略决策逐行对齐。全知录像仅做事后取证，不作为策略输入，也不逆造当时隐藏观察。

特别检查：moving→idle 的相同坐标帧是否让最近点搜索停在最后一帧移动键；原地预瞄是否误触卡住计时；opening→hold 与 loop 重置是否继续使用旧段动作或旧计时；交火是否暂停了对应路线的看门狗；放弃路线后是否转入通用 A*。这些是排查方向，不是未取证前的结论。

若修复代码，先写能复现实际边界的失败测试，再修复并跑相关回归。用记录下来的原观察重放可验证决策行为变化；修复后观察不会自动变为反事实世界，不能据此宣称新路线实走通过。

## 交付

用简短中文解释触发条件、错误状态切换和用户看到的结果，附少量关键 tick、回合及文件位置。区分日志直接证实、冻结代码重放推断和待实战验证。保存紧凑分析报告与重放脚本；不把完整日志或密钥提交到 Git。
