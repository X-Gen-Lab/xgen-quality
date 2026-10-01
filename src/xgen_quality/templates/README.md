# 受控配置模板

随 xgen-quality 0.1.0 分发；正文权威仍是 roadmap 工程规范 1.0.0。配置来源见包仓库 PROVENANCE.md。

- `.clang-format`、`.editorconfig`：X-Gen 源码排版与编辑器配置，选项与工程规范一致。
- `.clang-format` 明确使用 LF、清除文件/块首和文件末空行、最多保留一个空行、分隔独立定义；公开头的 API 文档组和注释邻接由现有 `format` 门禁补查，不增加另一个 hook。
- `.clang-tidy`：使用 clang-analyzer、bugprone、performance 检查，自有公开 include 头参与分析。
- `Doxyfile`：公开 API 严格检查模板；runner 根据消费者 public_headers 覆盖 INPUT，并先检查文件文档。
- `c-component-ci.yml`：C 组件 CI 快照，假设组件已有 host/release 预设、GoogleTest 消费及对应安装测试；需要审阅组件路径和任务后再采用。

消费者通过 `importlib.resources.files('xgen_quality').joinpath('templates', NAME)` 读取固定版本模板，复制后审阅 diff。记录采用版本与局部差异；本包不会在检查时修改消费者配置。

CI 模板默认显式获取 `X-Gen-Lab/xgen-quality`，允许用仓库变量 `XGEN_QUALITY_REPOSITORY` 覆盖为受控镜像。版本仍读取消费者 quality.json 的完整 `quality_source.revision`，不跟随默认分支。非空但无效的仓库覆盖、无效 revision 或不可读取的提交都必须失败；远端验证结果单独记录。

当前 `.clang-format` 标题统一为 X-Gen，验证版本为 19.1.5。快照导入时保留上游注释的描述属于历史基线，当前配置以新增空行规则和版本声明为准。
