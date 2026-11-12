# 提交版本快照

本目录保存每次提交的**完整代码快照**和对应的**改动说明**。每个版本一个目录，目录名 `vNNN-<短标签>`；`v000` 是 baseline。

## 目录规范

```
vNNN-<label>/
├── README.md        # 改动说明：改了什么、为什么、影响哪些规范、验证情况
├── metadata.json    # 版本元数据：日期、源码提交、合同、状态、文件哈希
└── ...              # 该次提交的完整文件树（至少 agent.py；辅助模块 / 权重同结构）
```

- 快照必须是**可提交的完整文件树**，不是 diff。用 `cp` 或 `git archive` 从已提交的代码复制，保持逐字节一致。
- `README.md` 的「对应规范」一节必须链接到受影响的 `docs/spec/*.md`；同时在该规范中回链本版本的改动说明。
- `metadata.json` 记录 sha256，便于核对快照与上传 ZIP。
- 新版本按编号递增；未上传的草稿也要注明状态。
- 不要修改旧版本快照；修正用新版本。

## 版本列表

| 版本 | 日期 | 状态 | 改动说明 | 对应规范 |
| --- | --- | --- | --- | --- |
| `v000-baseline` | 2026-11-12 | baseline，未提交 | [README](v000-baseline/README.md) | [baseline-compatibility](../spec/baseline-compatibility.md) |
| `v001-first-python-submission` | 2026-11-12 | 已提交；admission passed；version 1 | [README](v001-first-python-submission/README.md) | [agx-submit skill](../../.claude/skills/agx-submit/SKILL.md), [baseline-compatibility](../spec/baseline-compatibility.md) |

## 新版本流程

1. 从当前提交的代码复制到 `vNNN-<label>/`。
2. 写 `README.md`：变更点、原因、验证（本地 probe / 对局 / 上传回执）。
3. 写 `metadata.json`：合同、源码提交、文件哈希、状态。
4. 在受影响的 `docs/spec` 文件中添加版本引用（例如「自 v001 起……」），并在 [`docs/spec/README.md`](../spec/README.md) 的版本表登记。
5. 上传后回填上传结果（`admission`、bundle hash、`fault_code` 等）。
