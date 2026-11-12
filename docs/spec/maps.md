# 地图与选择

> 依据：AGX「多人爆破 · AI 助手开发指南」，合同 `rsi-fps-5.5`。

## 变更记录

### 2026-11-12
- **关联规范**：[agent-interface.md](agent-interface.md)、[fps-bomb.md](../rules/fps-bomb.md)。
- **背景**：地图只在首拍下发；导航来源不证明可通行，路线与站点中心需要按实际碰撞和裁判条件验证。
- **决策点**：地图细节集中在本文件；`fps-bomb.md` 只链接不重复；不把几何邻接当作可行走图。

## 五张地图

| 显示名 | `map_id` |
| --- | --- |
| Dust2 | `dust2-cs2-v54` |
| Mirage | `mirage-cs2-v54` |
| Borgo | `borgo-r3-v54` |
| Molo | `molo-r3-v54` |
| Nevaio | `nevaio-r3-v54` |

## 选图

- 可信整数对局种子为整局选择一图：对 `rsi-fps-5.4:map:{seed}` 做 SHA-256，按大端整数对 5 取模，对应上表顺序。
- 五个等权轮换条目，不保证每五局严格各轮一次。
- 策略拿不到对局种子；`init.context.seed` 是独立的公开策略随机域，不能用来重建隐藏抽样。
- 配置严格为 `{}`，参赛者不能选图或后端。
- 只有可信本地 probe 可以用 `Arena(..., map_id=...)` 显式覆盖各图。

## 坐标与角度

- 单位：米；`x/y` 水平，`z` 向上。
- `yaw` / `pitch` 为弧度。
- 正 `yaw` 面向 `(cos(yaw), -sin(yaw))`；正 `pitch` 向上。

## 首拍描述与缓存

- `map` 只在首拍观察中下发；之后观察只有 `map_id` 与 `static_schema_hash`。
- 按 `map_id` 与 `static_schema_hash` 缓存首张地图；身份不符时停用旧路线。
- 公开描述保留 `id / bounds / meshes / spawns / sites` 及元数据，并新增 `geometry_hash / spawn_pads_by_side / route_landmarks / plant_zones`。
- 站点记录使用 `id / center / radius`；路线地标由站点 ID 映射到 `center`。
- `geometry_hash` 绑定原始描述符元数据，不能假定它与 `static_schema_hash` 相同。
- 碰撞网格引用不等于沙箱内可读取网格文件；`map.render` 不会发送。

## 导航与路线的边界

- `source-adjacency` 只是导航来源，不证明任一原始边可通行。
- Mirage 的材质 / 穿透重建不冒充原始源数据。
- 路线回执只覆盖其绑定的地图身份、起点、方向、点列与控制序列。四舍五入、简化、插值、反向边、跨出生点拼接、最近点接入、改变速度、临时跳跃与卡住恢复都要另行实测。
- 不能由几何邻接推导可跳跃性、Mirage 备用出口可用性或「能在引信结束前完成回防」。
- 队伍分路只是策略选择，不承诺队友执行相同程序。
- 站点 `center` 是公开几何锚点，不是从任意出生点可直接到达的路线；安放由裁判判断脚点是否在站点 / `plant_zones` 内。

## 碰撞世界

- 正式环境要求通过源码 / 二进制 / ABI 校验的 `NativeCollisionWorld`；缺失或陈旧产物会拒绝启动。
- 显式 reference 碰撞仅用于离线 probe。
- 本地后备实现与渲染网格都不能更改权威空间规则。

## 与 baseline 的关系

当前 `agent.py` 从 `map["nav"]["nodes"/"edges"]` 建图并做 BFS。官方公开描述是否包含这两个字段、以及它们的语义能否直接当可通行图使用，需要通过真实首拍确认；见 [`baseline-compatibility.md`](baseline-compatibility.md)。
