# 预算、打包与提交

> 依据：官方指南合同 `rsi-fps-5.5` 的第 8–10 节与当前值表。这里的上限是准入与运行要求，不替代正式整局验收。

## 运行时预算

| 项目 | 当前值 |
| --- | --- |
| 每席整局累计 CPU | 64 s（最多 24 回合，含初始化） |
| 每席每回合折算 | 2.6666666666666665 s/round |
| 初始化 | 2 s |
| 普通回调 | 50 ms |
| 父进程 CPU / wall | 软/硬 3300/3301 CPU s；wall 3300 s |
| 独立验证预算 | 300 s |
| 时钟 | 物理 60 Hz；决策 20 Hz（每 3 tick）；录像 24 Hz |

- 64 s 是整局总账，不在每回合或半场重新发放，也不能向别席转账；较短对局不产生额外额度。
- 初始化与普通回调仍受累计账本限制。
- 父进程 profile、验证预算与策略 CPU 额度分开，不能相加当作策略预算。
- Python 内存与调用次数按可信冻结 P01 profile 执行；旧 JavaScript heap 上限不代表 Python RSS。
- 模拟游戏时钟与宿主 wall 不同。

## 故障与弃权

- 超时、累计耗尽、异常、畸形输出、非法动作、输出超限、OOM、worker 退出走**参赛者故障**路径：记录故障、禁用该席策略、后续使用中性控制。
- 合法但当前不可用的购买 / 交互是**回执拒绝**，不等同故障。
- 全席失败时，Python runner 产出明确的全席弃权终局：故障照记、不改 rating；各席计入胜率样本，胜场信用为零。
- 可信运行时错误作为平台失败向上传播，不能伪装为中性动作。
- 截断或宿主杀掉的任务不能算平局；只有完整打成 12:12 才能平局。
- 把运行当验收证据前，须检查完成状态、故障、父进程用量回执与冻结身份。

## 打包

ZIP 根必须有 `agent.py`；允许辅助 `.py` 模块、根 `design.json` 与数值 `.npz` 权重。本赛省略 `design` 或使用 `{}`。

权重读取方式：

```python
from pathlib import Path
import numpy as np

weights = np.load(Path(context["weights_dir"]) / "weights/model.npz", allow_pickle=False)
```

不能提交 venv、requirements、wheel、原生库或 pickle。

| 项目 | 上限 |
| --- | --- |
| ZIP | 64 MiB |
| 解包 | 128 MiB |
| ZIP 条目 | 64 |
| 单源码 / design 文件 | 256 KiB |
| 源码 / design 合计 | 1 MiB |
| NPZ 文件 | 64 MiB |
| 实际张量 | 64 MiB |
| 请求 / 响应帧 | 1 MiB / 64 KiB |

其余准入校验见官方共享 Python 打包说明。

## 本地十席驱动

先准备好经过校验的原生产物，把下面的脚本保存为**投稿目录外**的本地脚本，在开发环境仓库根运行。它只加载自己信任的策略；每席拥有独立模块状态，由 `Arena` 在推进 tick 前冻结观察。

```python
import importlib.util
import sys
import time
import types
from pathlib import Path

from rsi.games.fps_v54 import Arena
from rsi.runtime.seat_seed import derive_seat_seed


class LocalPolicy:
    def __init__(self, seat, match_seed):
        path = Path("my-submission/agent.py").resolve()
        name = f"local_seat_{seat}"
        package = types.ModuleType(name)
        package.__path__ = [str(path.parent)]
        sys.modules[name] = package
        spec = importlib.util.spec_from_file_location(name + ".agent", path)
        self.module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = self.module
        spec.loader.exec_module(self.module)
        self.module.init({
            "seed": derive_seat_seed(match_seed, seat, "rsi-fps-5.5"),
            "weights_dir": str(path.parent),
            "contract_id": "rsi-fps-5.5",
            "seat": seat,
            "role": 0,
        })

    def act(self, observation):
        return self.module.act(observation)


seed = 7
policies = [LocalPolicy(seat, seed) for seat in range(10)]
arena = Arena(seed, config={})
deadline = time.monotonic() + 3300
try:
    while not arena.over:
        if time.monotonic() >= deadline:
            raise TimeoutError("Incomplete local match; no score")
        arena.step(policies)
        arena.drain_events()
    print(arena.result())
finally:
    arena.close()
```

- 直接 Python 驱动不提供进程隔离或正式 CPU 计费，不能加载未知投稿。
- 同一 ZIP 可以初始化十次，但每席必须有自己的状态与 context，不能共享策略席位内存。
- 超时抛错，不伪造完成比分。

## 构建、校验与本地评估

在开发环境装好项目依赖，从仓库根执行：

```sh
mkdir -p output
PYTHONPATH=sdk/python-agent/src python -m agx_agent build my-submission --output output/agent.zip
PYTHONPATH=sdk/python-agent/src python -m agx_agent validate output/agent.zip
```

安装 SDK 后，`evaluate fps54` 会自动发现已安装的十席钩子；显式命令为：

```sh
PYTHONPATH=sdk/python-agent/src:sdk/python-agent python -m agx_agent evaluate fps54 \
  output/agent.zip output/agent.zip output/agent.zip output/agent.zip output/agent.zip \
  output/agent.zip output/agent.zip output/agent.zip output/agent.zip output/agent.zip \
  --seed 7 --hook games.fps54.hook:HOOK
```

- 该钩子导入候选 `Arena`，要求引擎预期位置已有校验过的原生产物，不会自动编译；缺模块 / 产物属于环境准备失败，不是评估失败比分。
- 本地评估只运行自己的代码，不复现正式沙箱、父进程 CPU 计费、上传准入或正式完整对局回执。
- 覆盖检查应通过可信 probe 遍历五图与双方，保留实际完成状态、源码 / bundle hash、地图、故障和用量。
- 短 probe 或 ZIP 校验成功不等于打完一局。

## 上传

只有赛事显示此 Python 合同时，才通过 Python 编辑器上传 ZIP，等待准入，并选择已接受的**不可变**版本参与未来对局。

- 上传：`POST /api/v1/python-submissions/agents/{agent_id}/bundles`，带 `Idempotency-Key`
- 历史：`GET /api/v1/python-submissions/agents/{agent_id}/bundles`
- 不确定结果的重试保持同一个 key 与字节；网页写操作需要 CSRF。
- 核对 `admission`、`fault_code`、`contract_id`、`rules_version`、bundle hash 与接受版本身份。
- 旧 JavaScript JSON 源码上传是另一条路径；报名、准入、完整对局彼此独立。
- 文档存在或本地成功均不表示赛事开放。
