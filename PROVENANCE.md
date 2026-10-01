# 来源与授权记录

质量检查实现迁移自本地 xgen-crc 提交 `7fe1d15` 的 `tools/quality.py`、`tools/quality.json` 和 `tools/tests/test_quality.py`。迁移前真实执行 28 项回归全部通过；配置参数化、包入口、安装来源记录与消费测试为本次新增。

Python 依赖精确版本源自同一 CRC 基线的 20 项工具依赖，集中迁入 pyproject.toml；pip 分发版本和外部工具实际版本有所区别，例如 clang-tidy 包 `19.1.0.1` 提供 LLVM `19.1.0`。依赖仍保留各自上游许可证，未复制其源码到本包。

`.clang-format`、`.editorconfig` 模板通过 CRC 受控副本取自 Nexus `7a203266082ad1f655b6686713b2b7950ba31ec6`。副本仅调整配置标题和验证工具版本注释，格式选项保持一致；`.clang-tidy` 和 Doxyfile 从 CRC 质量试点调整为模块中立模板。

`templates/c-component-ci.yml` 来自本次共享工具接入期间 CRC 的本地配置快照；它本身不是已在远端运行的证据。三个 C 组件可按 [模板说明](src/xgen_quality/templates/README.md) 受控同步，后续模板归本仓维护。

CRC 来源记录没有确认完整源码许可证。本次迁移没有新增授予开源许可证，也没有将 roadmap 的 MIT 许可证套用到本仓。未创建 LICENSE / SPDX 声明；正式公开发布前由仓库所有者确认授权范围和版权说明。

2026-10-01 本地空行规范增补在上述基线上增加 `SeparateDefinitionBlocks: Always`、`KeepEmptyLines` 三项 false 与 `LineEnding: LF`，其余格式选项保留。公开头结构空行检查由本仓新增，范围和 TDD 证据见 [检查说明](docs/header-spacing.md)。

本轮同时将当前 `.clang-format` 标题统一为 X-Gen，验证版本明确为 19.1.5；保留上游注释的描述属于首次导入记录，当前配置标题及新增规则以本轮增补为准。
