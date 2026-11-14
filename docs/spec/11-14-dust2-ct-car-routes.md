# 规范：Dust2 CT A/B 车位用户录制路线

Status: **已随 `1114-v0.21` 提交：`main` v17 / `account2` v20 admission 均 `passed` 并激活，entry code hash `86b46df3e37a`；本地 `195/195` 测试通过（6 skipped）。实走碰撞、视线与实战效果待回填。**
Date: 2026-11-14
Submission: [1114-v0.21](../submissions/1114-v0.21/README.md)
Related: [Walklab route intake](../../.agents/skills/walklab-routes/SKILL.md) · [职业 demo 两段式管线](./11-14-pro-demo-walklab-pipeline.md) · [轨迹链接器](./11-14-route-linker.md) · [路径与控制](./11-12-pathing-routes.md)

## 1. 数据与配对

四段用户 Walklab 录制均为 `walklab-v2`、20 Hz、`side: defend`、地图 `dust2-cs2-v54`、几何哈希 `b0c308526d55e56e3a50a5ecf9bdd1b70a02daf560a9a8157931f3b340fb8d66`，源文件位于 `recordings/dust2_ct/`，不进入提交 ZIP。

| 名称 | 包点 | opening（走位） | hold（守位） | 帧数 |
| --- | --- | --- | --- | --- |
| `A_1` | A | `dust2 ct 走a 车位.json` | `dust2 ct 守a车位.json` | 216 / 98 |
| `B_1` | B | `dust2 ct 走b车位.json` | `dust2 ct 守b车位.json` | 312 / 230 |

两条 opening 都从 CT 出生点 `(157.1595, 108.0804)` 出发；opening 终点与对应 hold 首帧完全重合（0.0 m）。hold 是循环片段，首尾闭合误差 A 0.75 m、B 1.49 m，环路时 agent 会走完这段缺口而不是跳帧。

守点位于 A/B 车位，距夹具包点中心分别约 25.7 m / 22.8 m；本批没有录制回防路线，`RETAKES = {}`。

## 2. 编译

`scripts/build_dust2_ct_routes.py` 以 `recordings/dust2_ct/manifest.json` 和 `tests/fixtures/dust2_static.json` 为输入，生成 `dust2_user_ct_routes.py`：

```sh
python3 -m scripts.build_dust2_ct_routes \
  recordings/dust2_ct/manifest.json tests/fixtures/dust2_static.json \
  dust2_user_ct_routes.py
```

校验项：

- `format == "walklab-v2"`、`mapId`/`mapHash` 与静态夹具完全一致、`hz == 20`、`side == "defend"`；
- tick 从 0 连续递增；位置/`yaw`/`pitch` 为有限数值；按键属于 `KeyW/KeyA/KeyS/KeyD/ShiftLeft/Space`；
- opening 有实际位移（> 0.5 m），opening 终点距 hold 首帧 ≤ 0.2 m，hold 首尾闭合 ≤ 2.0 m；
- pair 名称唯一、来源文件名安全、`site` 只能是 A/B；
- 每份源 JSON 的 SHA-256 写入生成模块。

输出帧为 `(x, y, z, yaw, pitch, key_mask)`，位置/视角保留 4 位小数，整段以 zlib + ascii85 内嵌，满足 256 KiB 单文件与 1 MiB 源码总量限制。

## 3. 运行时注册与选择

- `agent.user_ct_routes()` 按地图 ID 与静态哈希分发：Dust2 命中 `dust2_user_ct_routes.PAIRS/RETAKES`，Mirage 候选保持不变。
- CT 防守且未下包时，`choose_ct_recorded()` 按当前所选包点过滤 `pair["site"]`；每个包点当前各一条候选，seat 分配不影响结果。
- `follow_ct_recorded()` 先跟 opening；到达末帧后切 `hold` 并循环。遇敌暂停/续走、偏离重接、卡住脱困与最终放弃沿用既有 CT 录制路线逻辑；放弃后回退到原有 A*/守点行为。
- 下包后 `follow_ct_recorded()` 被 `not planted` 守卫停止；Dust2 暂无录制回防，`choose_retake()` 不发车，回落到原有 A* 回防。
- 地图 ID/哈希不匹配、未注册地图或未知包点保持原有行为。

## 4. 限制与待验证

- 编译与单元测试只证明格式、帧序、配对和选择逻辑；**不证明**实走碰撞、视线、站位强度或对枪效果。
- A/B 车位距包点中心的实际战术意义需实战复核；如需更靠近默认下包点的守位，应补充 hold 录制。
- 本批没有 Dust2 CT 回防；若需要跨点回防，按 [Walklab route intake](../../.agents/skills/walklab-routes/SKILL.md) 录制 `purpose: "retake"` 数据并扩展现有 `RETAKES` 注册。
