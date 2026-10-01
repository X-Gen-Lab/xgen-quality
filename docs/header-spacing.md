# 公开头空行检查

本次为未发布的工具 0.1.0 / 工程规范 1.0.0 增补；使用实际工具 Git 提交固定实现。权威要求为 roadmap 的 `C-020`、`C-021` 和 `DOC-013`，本文件说明自动检查范围及本地证据。

`format` 保持只读：先使用固定的 clang-format 19.1.5 执行 `--dry-run --Werror`，然后仅对消费者 `public_headers` 声明范围中的本次选中文件执行结构空行检查。已有 pre-commit format 入口自动使用同一规则，无需新增 hook。格式检查失败不会改写文件，也不会暂存 Git 内容。

受控 `.clang-format` 使用 `SeparateDefinitionBlocks: Always`、`MaxEmptyLinesToKeep: 1`、`KeepEmptyLines` 三项均为 false、`LineEnding: LF`。实测 formatter 可以分隔函数、结构体和枚举定义，并处理文件首尾、块首与重复空行；它无法完整处理函数原型之间的独立 Doxygen 文档组、注释紧邻声明及 guard / includes / extern-C 段落边界。

补充检查只识别常见 C 公开头的明确词法结构：

- `C-020`：文件 Doxygen 与下一段、include guard 与内容、include 区与声明、extern-C 开关组与内容、独立 API 文档组之间一个空行；guard 两行及 extern-C 开关组内部连续。
- `DOC-013`：顶层独立 `/** ... \brief ... */` 或 `@brief` 块紧邻其直接声明，也支持直接注释的 `#define`。
- 前置普通契约注释与紧随的 Doxygen 属于同一组，在整个组的起点检查空行；后置 `NOLINTEND` 工具注释属于前一组。
- 字段、尾随 `/**<`、参数内注释、函数体内部以及注释正文的空白不按独立 API 组处理。宏续行、普通字符串、字符常量、原始字符串被当作不透明词法单元。

这是有限结构检查，不是 C/C++ 语法分析器。条件编译包裹声明、宏生成 API、任意 C++ 结构及其他非标准头模板由人工审阅。`C-021` 函数体内按校验、准备、执行、清理等语义分段属于人工建议，不能自动给每条语句加空行。检查通过不表示所有规范要求都已经自动证明。

诊断进入现有 `out/reports/quality-format.json` 的 `spacing_diagnostics`，包含 `path`、一基 `line`、`previous_line`、`rule`、`expected_blank_lines`、`message`。两行之间应当恰好存在给定数量的空白行。开发辅助接口为 `xgen_quality.spacing.check_header_spacing(text)`，返回同样字段但不含路径的只读诊断；它没有隐式修复功能。

本地 TDD：首项测试在旧 format 行为下实际因“未拒绝 API 组缺少空行”失败，RED 检查点为 `7bee4fb`。随后补充头模板、注释邻接、字段/函数体、宏/字符串、条件包装、配置范围及前置契约注释回归。测试和覆盖率结果记录在 `out/reports/blank-line-tests.txt`、`blank-line-coverage.json`。独立 wheel 安装测试从临时目录运行，不依赖兄弟源码路径；真实组件的采用证据由各自仓库维护。

本地 Windows / Python 3.12 验证为 82/82 测试通过，包含 15 项新增空行测试和隔离 wheel 的新检查器消费测试。全包生产 Python 行覆盖 510/521（97.89%），分支覆盖 251/260（96.54%），无排除行，各自超过 80%；未将隔离子进程未采集的执行计入分子。远端 CI 尚未运行。
