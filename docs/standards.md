# 工程规范采用声明

采用 xgen-roadmap `docs/standards` 规范 **1.0.0**，正文基线修订 `c018272a1bfa0a0ad0e811ceedcb22862640ed98`。后续 CRC 试点和共享工具接入补充以本仓实施记录及提供者最终提交追溯；不将本地版本号写成已发布 tag。

本仓属于八类模块中的“开发工具”，profile 为 Python 3.12 主机检查工具。适用仓库、依赖、TDD、报告和独立消费规则；本仓没有生产 C/C++、MCU 固件或公开 C API，不适用 GoogleTest 链接、Doxygen API 门禁和 MCU RAM / Flash 验收。它提供这些检查能力供 C/C++ 消费者使用。

正文由 roadmap 维护，本仓只保存实现、受控模板和实际验证证据。来源及权限事实见 [PROVENANCE.md](../PROVENANCE.md)。固定依赖由 pyproject.toml 定义；门禁实际工具版本由包内 policy.json 定义，不能用依赖安装成功代替工具运行版本验证。

本地、pre-commit 和 CI 通过安装包及薄入口共享规则。检查不联网；联网获取与构建后端准备必须显式运行。报告至少记录配置摘要、默认策略摘要、包版本、消费者 Git HEAD / 脏状态、实际命令、工具版本及退出状态。

覆盖率范围：gcovr 子命令测量消费者的真实 C/C++ 生产对象。本仓 Python 使用固定 coverage.py，对 `src/xgen_quality` 的全部 Python 源码测量行/分支，各自执行 80% 门禁；测试、依赖和模板文件不计入生产 Python 分母，不声明该工具未提供的函数指标。安装 wheel 的子进程测试单独记录，不假定自动合入源码覆盖率。

当前已在本地 Windows 验证源代码测试与真实 wheel 消费；Linux CI 配置待远端仓库建立后实际执行。完整状态与复现方式见 [实施记录](implementation-log.md)。
