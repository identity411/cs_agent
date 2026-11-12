# 1112-v0.04

- **日期**：2026-11-12
- **比赛 ID**：`2a97f94f-816a-52b7-b4b8-5925db160245`
- **合同**：rsi-fps-5.5
- **状态**：submitted; admission passed; main version 4; account2 version 3
- **快照**：agent.py, map_patches.py（见同目录文件）

## 改动说明

- **前进跳 / 台阶跳**：`move()` 用“向当前 waypoint 的净进度”代替逐帧位移判断 `stuck`，避免碰撞滑动时位置每拍变化、进度却为零；净进度不足 0.4 m 持续 12 tick 且朝向对齐时向前跳，最多 3 次；下一个 waypoint 高出当前脚底 ≥0.8 m、水平 ≤2.5 m 时直接台阶跳；stuck 恢复先尝试前进跳，再退回后退/横移。
- **Mirage 修复**：针对 R6 T 出生点西侧 `(90,132)` 的整队滑动和 R10 同一拐角、CT→A 的 `(42.8,66.4)` / `(74.6,62.3)` 台阶，加入 soft hazard 与前进跳；详见 `docs/spec/11-12-mirage-spawn-jump.md`。
- **地图修补独立**：新增根目录 `map_patches.py`，把地图 hazard 坐标与台阶跳阈值放进 `MapPatch`，`agent.py` 只调用 `map_patches.for_map(map_id)`，不在核心逻辑里写地图分支；`build` 随 ZIP 打包 `agent.py` + `map_patches.py`。
- **T 方 pre-plant 振荡修复**：T 下包前不再在 site center / patrol 点之间切换，避免 dust2 A 回合在 near-site 边界来回切 goal；patrol 现在只用于 CT 防守。
- **临时 T 兜底**：T 方 `round_tick >= 40 s` 仍未下包时直接以 CT 出生点为目标，强制离开出生点；只到本回合结束，下包后恢复正常守包逻辑。这是临时兜底，nav 卡死率下降后应删除。
- **地图 soft hazard**：dust2 `(83.4,88.2)` / `(160.63,125.71)`、Mirage `(42.8,66.4)` 作为软边惩罚，不封死路线；未知地图返回中性 `EMPTY`。
- **本地验证**：`py_compile` 通过；全量 unittest 53/53；`tests.test_movement` 18/18；Mirage/dust2 nav 模拟通过。
- **仍未验证**：新对局完整表现；临时兜底是竞速期权宜；`holdB` / 台阶跳在真实碰撞世界的可达性；空弹主武器切枪/换弹仍未修复。
- **快照**：`agent.py` 38,449 bytes，sha256 `8c4e62465d015825707e3e82eb5d9bbaab93db6aa23f58304ecc751b5bc4ad96`；`map_patches.py` 1,520 bytes，sha256 `c11bc9ca5c5f3cd479c7e9681909d563c55d0fbc814ee3b36e73e5bbfb916265`；ZIP sha256 `765af129d095ac51336d4a406bbc2895cfa8f144d932c1f82c8eee0b6bd6b9c2`。
- **线上**：`main` bundle `084f2c9a-3f24-4047-9095-4a9e7b1adf3f`，version `4` 激活（`1249516b-4903-4ccd-bbf0-53ce2ffa4d1d`），entry `f81706cb-1aa5-54e6-9e4b-e1199ca25820`；`account2` bundle `0d78da3e-3321-4a90-87c5-fe6319c6e057`，version `3` 激活（`aa194a43-d341-496c-ad5f-3fdf71ea9410`），entry `a23486ad-a765-51b7-b2a9-b090b2d2e48f`。两者 admission 均 `passed`。

## 提交结果

| 账户 | 版本 | bundle | version_id | entry |
| --- | ---: | --- | --- | --- |
| `main` | 4 | `084f2c9a-3f24-4047-9095-4a9e7b1adf3f` | `1249516b-4903-4ccd-bbf0-53ce2ffa4d1d` | `f81706cb-1aa5-54e6-9e4b-e1199ca25820` |
| `account2` | 3 | `0d78da3e-3321-4a90-87c5-fe6319c6e057` | `aa194a43-d341-496c-ad5f-3fdf71ea9410` | `a23486ad-a765-51b7-b2a9-b090b2d2e48f` |

两个账户的 `admission` 均为 `passed`，entry 均显示 `code_hash_short = 765af129d095`；版本号按账户独立。

## 对应规范

- [`docs/spec/11-12-mirage-spawn-jump.md`](../../spec/11-12-mirage-spawn-jump.md) — Mirage R6/R10 出生点滑动卡住、CT A 台阶与前进跳。
- [`docs/spec/11-12-pathing-routes.md`](../../spec/11-12-pathing-routes.md) — A*、attackRoutes、前进跳 / 台阶跳、`map_patches.py`、临时 T 兜底。
- [`docs/spec/11-12-stuck-at-spawn.md`](../../spec/11-12-stuck-at-spawn.md) — 出生点 / 近点卡住。
- [`docs/spec/11-12-site-center-hold.md`](../../spec/11-12-site-center-hold.md) — 包点中心 hold 与 patrol。
- [`docs/spec/11-12-empty-primary-switch-reload.md`](../../spec/11-12-empty-primary-switch-reload.md) — 仍未修复的空弹切枪 / 换弹。
- [`docs/spec/baseline-compatibility.md`](../../spec/baseline-compatibility.md) — 与官方合同的已知差异。
- [`docs/spec/README.md`](../../spec/README.md#提交版本与改动说明) — 版本表登记。

## 验证情况

- 已验证（本地）：`py_compile` 通过；全量 unittest 53/53；`tests.test_movement` 18/18；Mirage / dust2 nav 模拟通过。
- 已验证（线上）：两个账户 ZIP 上传、admission `passed`、version `4` / `3` 激活；entry 显示 `code_hash_short = 765af129d095`。
- **未验证**：新版本在下一轮正式对局的完整表现、比分、回放与长期排名；admission 通过不代表完整对局成功。
- 已知未修：空弹主武器不切枪 / `reload_until` 语义等，见空弹 badcase。
- 临时兜底：T 方 40 s 未下包 → CT 出生点，仅用于当前比赛，nav 卡死率下降后应删除。
