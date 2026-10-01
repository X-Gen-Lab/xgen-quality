# 2026-10-01 CI 修复记录

## 首次远端失败

- [quality Windows 运行](https://github.com/X-Gen-Lab/xgen-quality/actions/runs/36803213206) 实际执行 82 项 Python 测试，9 个失败、5 个错误。Windows 临时目录使用 `RUNNER~1` 短路径，Runner 规范化为长路径；测试夹具却将未规范化路径直接传给内部检查或比较，导致路径相对化与相等断言失败。Linux 同轮通过。
- [CRC 运行](https://github.com/X-Gen-Lab/xgen-crc/actions/runs/36803242001) 日志确认 `QUALITY_REPOSITORY` 为空，五个 C 组件在相同工具准备步骤停止，还未执行编译测试。

## 改动与本地回归

测试夹具统一解析临时路径，并增加根目录及文件路径别名、重复输入、范围与文本报告回归。生产路径规则、范围限制和文本门禁不变；隔离 wheel 消费仍使用真正安装的包。修复后的本地 Windows 测试 83/83 通过，保留 5 项隔离 wheel 消费。

共享 C 组件工作流模板显式使用已发布的 `X-Gen-Lab/xgen-quality` 作为默认源，允许仓库变量覆盖。消费者继续固定完整提交，不改为追随 main；memory / containers 的 status 来源采用相同约定。该默认只属于显式 CI 准备阶段，不会在检查或生产构建中自动下载。

本地覆盖率采集 `src/xgen_quality`：行 510/521，分支 251/260，分别通过 80% 门槛。报告位于 `out/reports/ci-repair-coverage.json`。最新远端结果必须按本次提交对应 Actions 运行核验；本文中的首次失败不能被当作修复后的状态。
