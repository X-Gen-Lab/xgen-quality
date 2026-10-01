# 共享质量工具实施记录

实施日期：2026-10-01。工作包：S1 / 共享质量工具提取；分支 `feat/shared-quality`。这是本地实施记录，不代表远端发布或 Linux CI 已通过。

## 需求、设计与任务

三个独立 C 组件需要共享同一套质量规则，原 CRC 自有 runner 不能继续被复制到每仓。此次把实现、默认工具策略和受控模板提取为独立 Python 包；组件只保留明确根目录的薄入口和模块配置，生产 CMake / ARM 依赖保持独立。

包版本 0.1.0，规范版本 1.0.0。入口为 `python -m xgen_quality --root PATH ...` 或 `main(arguments=None, root=PATH)`。配置字段和路径约束见 README；工作目录、第三方工具或消费者兄弟目录不决定仓库身份。

任务按以下顺序完成：

1. 从 CRC `7fe1d15` 复制 runner、默认配置和 28 项回归，实际执行行为基线。
2. 为显式根目录、多模块 public / production 输入、默认策略合并、版本和配置拒绝规则编写失败测试。
3. 参数化入口与输入，保留原有文本、格式、测试、静态分析、Doxygen 和覆盖率规则。
4. 打包 policy 与模板，验证隔离 wheel 安装；新增安装来源与配置来源分离的报告契约。
5. 量化 Python 行/分支，补命令、报告及失败传播测试，将相同门禁加入自身 CI。
6. 明确依赖准备、离线消费、来源授权与未执行事项；组件接入由各组件的实施记录承接。

## TDD 与验证证据

| 阶段 | 实际命令 / 输入 | 结果与原因 | 本地原始证据 |
| --- | --- | --- | --- |
| 迁移基线 | CRC `python -m unittest discover -s tools/tests -v` | 28/28，退出 0；执行在切换薄入口之前 | out/reports/migration-baseline.txt |
| 参数化 RED | 迁入的原 runner 加消费契约，`python -m unittest discover -s tests -v` | 41 项执行，退出 1；旧 root 参数不支持、模块路径写死、版本/缺配置校验缺失；原 28 项仍通过 | out/reports/shared-package-red.txt |
| 安装 RED | 已准备后端，真实构建 wheel 并用 `--no-index --no-deps` 安装到临时 venv | 47 项执行，退出 1；包缺模板，报告缺 installation；不是工具缺失或下载失败 | out/reports/wheel-consumer-red.txt |
| 初次 GREEN | 同一源代码和 wheel 消费测试 | 47/47，退出 0；实际安装包包含策略、模板与入口 | out/reports/shared-package-green.txt |
| 回归与量化 | `coverage run --branch --source=src/xgen_quality -m unittest discover -s tests` | 66/66，退出 0；有效补测配置、Git 默认选文件、文本失败、CTest 清单、真实生产数据库过滤、命令分派与报告失败 | out/reports/python-coverage.json |

RED 仅在对应目标行为缺失时认定；Windows 测试 fixture 的默认 CRLF 和路径分隔符断言问题在实现阶段被修正，没有将其算作有效 RED，也没有放宽生产文本门禁。

Python 覆盖率工具为 coverage.py 7.10.7，采集范围为 `src/xgen_quality` 全部 Python 文件，无排除行：行 **384/394，97.46%**；分支 **184/188，97.87%**。完整 JSON 保留未执行行和分支；wheel 子进程测试单独验证安装行为，本次没有将其未采集的覆盖硬算进上述分子。

CI 分别检查行与分支至少 80%，拒绝零分母；不以 coverage.py 的混合百分比替代。Python 没有用 C gcovr 生成函数覆盖率声明。原 28 项不是重复复制到组件：它们只保留在本包，组件执行自身行为与安装测试。

## 构建与离线消费

实际创建独立 venv，按 pyproject.toml 显式准备 setuptools 80.9.0，构建 `xgen_quality-0.1.0-py3-none-any.whl`。同一 wheelhouse 保存 20 项精确版本的 Python 依赖；使用 `--no-index --find-links` 完成全依赖安装。轮子文件摘要记录在 `out/reports/wheel-manifest.json`，最终提交后按源码版本重新生成可发布产物。

定向 wheel 回归使用全新 venv 和 `python -I`，从不相邻、含空格的消费者目录运行，验证模块入口、薄 launcher、错误版本失败及包资源存在。CLI 不依赖源仓库 src 或固定兄弟目录。

包内模板的来源由 PROVENANCE.md 记录；C 组件 CI 模板保存本次根代理已统一的受控快照。消费者使用仓库变量加固定 provider SHA 获取代码，变量未准备时失败。`quality_source.revision` 只表示声明，wheel 安装实际 URL / 归档 hash 分开报告。

## 交付边界

本地 Windows Python 3.12 的测试、打包与消费已有证据；Linux / Windows 远端工作流已配置但尚未运行。本仓尚未设置远端、创建发布 tag 或发布到包索引。源码授权沿用来源的未确认状态，未臆造开源许可。

CRC / bytes / status 的真实检查、覆盖率与生产构建由各自实施记录证明；本包测试不能替代组件或整机验收。MCU 资源、App / Boot 和硬件验证不属于主机质量包的运行能力。
