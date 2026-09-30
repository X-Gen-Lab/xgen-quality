# 仓库工作约定

- 始终使用简体中文与用户沟通；先读 CONTRIBUTING.md、docs/standards.md 和 PROVENANCE.md。
- 本仓是主机开发工具，不是 MCU 运行库；不引入组件生产依赖，不复制 roadmap 规范正文。
- 新行为和缺陷修复遵循真实 Red / Green / Refactor，工具测试使用 Python unittest；纯迁移先验证基线。
- 共享默认工具版本和范围由包内 policy.json 维护；Python 分发依赖由 pyproject.toml 精确固定，不手写第二份 requirements。
- 消费者显式提供根目录和配置；不能猜固定兄弟仓库路径，检查不得隐式下载、改写或暂存源码。
- Nexus 模板是受控副本，保留来源；更新通过可审阅差异同步，不静默覆盖消费者补充。
- 未确认完整源码许可证，不自行添加 MIT 或 SPDX 授权；本地检查、远端 CI、公开发布分别记录。
