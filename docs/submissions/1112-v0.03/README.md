# 1112-v0.03

- **日期**：2026-11-12
- **比赛 ID**：`2a97f94f-816a-52b7-b4b8-5925db160245`
- **合同**：rsi-fps-5.5
- **状态**：submitted; admission passed; `main` version 3，`account2` version 2 已激活
- **快照**：agent.py（见同目录文件）

## 改动说明

- **R2 包点 hold 修复**：`act` 在无敌人、未下包且不拿包时使用公开 `bot_waypoints` 的 `hold` / `watch` 点巡逻，不再把 site center 当终点；连续约 2 秒没有位移时切换下一个点。
- **A* 寻路**：用距离权重 + 启发式的 A* 替代 BFS；路径末尾仍追加精确 goal；`source-adjacency` 反向边默认关闭，避免把高台跳下当成可走坡。
- **执行反馈边代价**：卡住/跳过路径点时给边加惩罚，成功通过时衰减；惩罚跨回合保留，帮助绕开实际不可走的 nav 边。
- **dust2 进攻路线**：使用 `attackRoutes` 的 A 大 / A 小 / B 洞 / B 门 lane；拿包的人走最快 lane，其余人按 lane 长度和席位分散；进入包点附近后切换 hold/watch patrol。
- **移动与目标动作**：sprint / walk、路径点弹出、stuck 跳过；`plant_zones` 下包点；T 下包后去 watch 点。
- **战斗控制**：看见敌人时在瞄准未对齐/未 ready 时左右 strafe，不再无条件冻结；连续约 1.5 秒未开火进入约 1 秒的边推进边瞄准/开火窗口。
- **本地验证**：`python3 -m py_compile agent.py` 通过；`python3 -m unittest discover -s tests -v` 40/40 通过；`tests.test_movement` 12/12 通过；真实 dust2 static 路径冒烟测试通过。
- **仍未验证**：新对局完整表现（T 侧 R13/R14/R15/R17/R19 是否不再卡在出生点、到点时间、下包/守包、命中率）；空弹主武器切枪/换弹 badcase 仍未修复。
- **快照**：`agent.py` 32,683 bytes，sha256 `93ca977f86f7a7772c1f6a5d4d718ab9f3e3ae6112a2b6cf2e4fc500efe73c79`；ZIP sha256 `07f6516dfb129befc21a182f8807b740c6c85cb2603473d49b64bdc62270a07d`。
- **线上（main）**：bundle `909c42de-3493-4051-a707-1c6abae6f096`，admission `passed`；version `3` 已激活（`6e26846f-f98a-4bd9-bc94-5c92d028d48c`），entry `f81706cb-1aa5-54e6-9e4b-e1199ca25820`。
- **线上（account2）**：同一 ZIP，bundle `e1653ff8-47cc-4e08-aa52-560ede822f93`，admission `passed`；version `2` 已激活（`69b61375-fcb1-428b-962a-093b1e0c527b`），entry `a23486ad-a765-51b7-b2a9-b090b2d2e48f`。版本号按账户独立。

## 提交结果

| 项目 | 值 |
| --- | --- |
| `bundle_id` | `909c42de-3493-4051-a707-1c6abae6f096` |
| `version_id` | `6e26846f-f98a-4bd9-bc94-5c92d028d48c` |
| `number` | `3` |
| `admission` | `passed` |
| `bundle_sha256` | `07f6516dfb129befc21a182f8807b740c6c85cb2603473d49b64bdc62270a07d` |
| `agent.py` sha256 | `93ca977f86f7a7772c1f6a5d4d718ab9f3e3ae6112a2b6cf2e4fc500efe73c79` |
| `entry` | `f81706cb-1aa5-54e6-9e4b-e1199ca25820`，网页显示 `version.number = 3`、`code_hash_short = 07f6516dfb12` |
| `Idempotency-Key` | `9f968068-ddd3-4ccd-949e-7cd29ffcefd6` |

`account2` 使用同一 ZIP 提交：

| 项目 | 值 |
| --- | --- |
| `bundle_id` | `e1653ff8-47cc-4e08-aa52-560ede822f93` |
| `version_id` | `69b61375-fcb1-428b-962a-093b1e0c527b` |
| `number` | `2`（account2 独立编号） |
| `admission` | `passed` |
| `bundle_sha256` | `07f6516dfb129befc21a182f8807b740c6c85cb2603473d49b64bdc62270a07d` |
| `entry` | `a23486ad-a765-51b7-b2a9-b090b2d2e48f`，网页显示 `version.number = 2`、`code_hash_short = 07f6516dfb12` |
| `Idempotency-Key` | `1ffaa4cd-fcbd-4fb3-9087-542d33d54952` |

调用顺序：`POST .../bundles` → 轮询 `GET .../bundles/{id}`（`admission = passed`）→ `POST .../competitions/{id}/versions`（已激活）。

## 对应规范

- [`docs/spec/11-12-site-center-hold.md`](../../spec/11-12-site-center-hold.md) — R2 包点中心 hold 的复现与 patrol 修复。
- [`docs/spec/11-12-pathing-routes.md`](../../spec/11-12-pathing-routes.md) — A*、执行反馈边代价、dust2 `attackRoutes`、sprint / 战斗超时 / plant zone。
- [`docs/spec/11-12-stuck-at-spawn.md`](../../spec/11-12-stuck-at-spawn.md) — 出生点卡住；v0.03 继续针对 dust2 T 侧残留。
- [`docs/spec/11-12-empty-primary-switch-reload.md`](../../spec/11-12-empty-primary-switch-reload.md) — 仍未修复的空弹切枪 / 换弹 badcase。
- [`docs/spec/README.md`](../../spec/README.md#提交版本与改动说明) — 版本表登记。

## 验证情况

- 已验证：`py_compile` 通过；`python3 -m unittest discover -s tests -v` 40/40；`tests.test_movement` 12/12；真实 dust2 / nevaio / borgo static 路径冒烟测试通过。
- 已验证（线上）：ZIP 上传、admission `passed`；`main` version `3`、`account2` version `2` 激活；两个 entry 均显示 `code_hash_short = 07f6516dfb12`。
- **未验证**：新版本在下一轮正式对局的完整表现、比分、回放与长期排名；admission 通过不代表完整对局成功。
- 已知未修：空弹主武器不切枪 / `reload_until` 语义等，见 [`baseline-compatibility.md`](../../spec/baseline-compatibility.md) 与空弹 badcase。
