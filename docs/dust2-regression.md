# Dust2 固定地图与卡点回归

固定输入是 [`../tests/fixtures/dust2_static.json`](../tests/fixtures/dust2_static.json)：从本账户 Dust2 对局 `36cf9b6c-78ec-469f-b008-daca03bf0e73` 的公开 `static.json` 原样复制。SHA-256：`8145524e36f1ea0351533c031e500ee144ba61ee4b0d3239875eb03f8d01c44a`。地图 ID `dust2-cs2-v54`，包含 2242 个导航节点、6275 条边、双方各 8 个出生点及攻击路线。该夹具与本平台 agent 的首拍 `map` 同结构、同坐标系。

每次改动 `agent.py` 后先运行：

```sh
python3 -m unittest tests.test_dust2_regression -v
python3 scripts/dust2_regression.py --agent agent.py
```

命令会在固定地图的 16 个出生点调用 agent，确认都能生成路径与导航动作。返回码 0 表示这项静态检查通过。

新对局结束后，对指定回合导出公开帧，再检测实际位置轨迹：

```sh
python3 .claude/skills/agx-match-query/scripts/agx_matches.py frames \
  --match-id MATCH_ID --seat SEAT --round ROUND --out /tmp/dust2-frames.jsonl
python3 scripts/dust2_regression.py \
  --trace /tmp/dust2-frames.jsonl --seat SEAT
```

轨迹检查忽略非 `live` 阶段和死亡帧。连续至少 300 tick（5 秒）局限在起点 1.5 米内时，报告 `suspected_traps`；最大位移不超过 0.25 米标为 `stationary`，否则标为 `local_loop`。异常返回码为 1，报告含起止 tick、位置和范围。持枪守点或等待队友也可能被报告，需要结合该回合目标和战斗事件核实。

本夹具的 `collision` 仅是三角网格文件名与哈希引用，本仓库没有对应二进制碰撞数据或权威物理引擎。因此静态检查不能证明 agent 一定能跨台阶、走过门或绕开障碍；新算法是否在这些地方卡住，须在真实对局位置帧上检查。CS2 原版 `de_dust2.nav` 是另一套版本和坐标，不应直接替换本平台的 `map`。
