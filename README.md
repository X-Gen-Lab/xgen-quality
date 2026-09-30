# xgen-quality

独立的主机质量工具包，版本 `0.1.0`，Python 3.12 及以上。它从 CRC 已验证的检查入口提取，供组件通过显式根目录调用；不进入 MCU 生产依赖。

当前为本地开发版本，未设置远端、未发布 tag 或公共包。规范正文由 xgen-roadmap 的 `docs/standards` 维护，采用范围见 [docs/standards.md](docs/standards.md)，来源和授权事实见 [PROVENANCE.md](PROVENANCE.md)。

支持文本、clang-format、CTest、cppcheck、clang-tidy、Doxygen 和 gcovr 检查。工具失败、错误版本、空测试、跳过测试、空覆盖率均阻断；检查阶段不安装依赖、不联网、不自动修改源码。安装与开发步骤见 [CONTRIBUTING.md](CONTRIBUTING.md)。

## 消费接口

消费者提交自己的 `tools/quality.json`，保留显式模块输入，不复制工具默认版本：

```json
{
  "schema_version": 1,
  "standard_version": "1.0.0",
  "quality_version": "0.1.0",
  "public_headers": ["include/xgen/bytes"],
  "production_directories": ["src"]
}
```

`public_headers` 支持目录或单个 `.h`；`production_directories` 是生产目录。路径必须相对消费者根目录，不允许越界、生成物或第三方排除目录。没有对应代码时可以显式写空数组；调用需要该输入的 docs / coverage / 静态分析仍会失败。检查所需文件缺失不会被当成通过。

可选 `test_label` 覆盖默认 `unit|integration`；`coverage` 可按 line / branch / function 提高默认 80% 门槛；`scope` 按字段替换选择规则，内建生成物/第三方排除项始终保留。未知字段、错误 schema / 标准 / 包版本均失败。

可选 `quality_source: {"revision": "实际提供者的完整 40 位 Git SHA"}` 用于 CI 固定源码来源；上述中文是说明，不是可用 SHA。报告将该声明单独列出，不证明当前安装来自此提交；实际 wheel 安装另记录发行元数据及 direct_url 的归档摘要。正式消费源码锁由提供者完成提交后填写，未发布时不编造远端地址。

CLI 必须明确根目录，相对文件名与构建目录均从该根解析，与调用时 cwd 无关：

```text
python -m xgen_quality --root /path/to/component text
python -m xgen_quality --root /path/to/component format
python -m xgen_quality --root /path/to/component test --build-dir out/host
python -m xgen_quality --root /path/to/component cppcheck --build-dir out/host
python -m xgen_quality --root /path/to/component tidy --build-dir out/host
python -m xgen_quality --root /path/to/component docs
python -m xgen_quality --root /path/to/component coverage --build-dir out/coverage
```

`text` / `format` 接受显式文件列表，含空格路径作为独立参数传递。无文件参数时选 Git 已跟踪与未忽略的自有文件；已记录删除可忽略，未知路径失败。`test` 另支持 `--label` 和 `--config`，`coverage` 支持 `--gcov-executable`。

薄入口 `tools/quality.py` 仅将自身仓库根目录交给已安装包：

```python
from pathlib import Path
from xgen_quality import main

if __name__ == "__main__":
    raise SystemExit(main(root=Path(__file__).resolve().parents[1]))
```

入口支持 `main(arguments=None, root=None)`；调用者同时提供 root 和不同的 `--root` 会失败。没有任何隐式兄弟目录或全局工作区搜索。

## 策略与报告

`src/xgen_quality/policy.json` 保存默认检查范围与工具实际版本；pyproject.toml 保存固定 Python 分发依赖，pip 包版本可能不同于其提供的二进制版本。cppcheck / Doxygen / CTest / 编译器由开发环境显式提供。`XGEN_CLANG_FORMAT`、`XGEN_CLANG_TIDY`、`XGEN_CPPCHECK`、`XGEN_DOXYGEN`、`XGEN_GCOVR` 可选择确切可执行文件，仍严格验证版本。

消费者根 `out/reports/quality-<command>.json` 记录版本、配置与默认策略摘要、Git HEAD / 脏状态、命令和状态。其他证据包括 CTest JUnit、Doxygen 输出、过滤后的编译数据库、覆盖率完整 JSON 及 summary；完整报告保留未覆盖行/分支。每个构建配置分别运行并归档，避免并发覆盖同名报告。

配置模板随 wheel 分发，见 [模板说明](src/xgen_quality/templates/README.md)。采用时复制并审阅差异，不让检查自动改写消费者。模板和默认策略升级随包版本发布；当前 0.1.0 仍是本地待发布基线。

打包依据：[PyPA pyproject 规范指南](https://packaging.python.org/en/latest/guides/writing-pyproject-toml/)、[setuptools 配置文档](https://setuptools.pypa.io/en/latest/userguide/pyproject_config.html)、[pip wheel 文档](https://pip.pypa.io/en/stable/cli/pip_wheel/)。
