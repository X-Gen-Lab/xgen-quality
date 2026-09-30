# 开发与验证

采用 [工程规范声明](docs/standards.md)。新行为先增加有效失败测试，记录命令、退出码和原因，再实现并回归；保留原有 28 项门禁回归。Python 工具使用 unittest，组件 C/C++ 测试继续使用 GoogleTest。

以下命令在本仓根目录运行，使用 Python 3.12。先创建隔离环境并激活；Windows 激活 `out/venv/Scripts/Activate.ps1`，POSIX 激活 `out/venv/bin/activate`。

```text
python -m venv out/venv
```

显式联网准备构建后端，版本直接读取 pyproject.toml；此步骤与实际检查分开：

```text
python -c "import pathlib,subprocess,sys,tomllib; p=tomllib.loads(pathlib.Path('pyproject.toml').read_text('utf-8')); subprocess.run([sys.executable,'-m','pip','install',*p['build-system']['requires']],check=True)"
python -m pip wheel --no-build-isolation --wheel-dir out/wheelhouse .
```

wheelhouse 包含当前操作系统和 Python ABI 的包及全部固定依赖。离线环境从 wheelhouse 安装本地 wheel；以下是当前版本的产物名，升级时与包版本一起变更：

```text
python -m pip install --no-index --find-links out/wheelhouse out/wheelhouse/xgen_quality-0.1.0-py3-none-any.whl
python -m pip check
python -m unittest discover -s tests -v
python -m xgen_quality --root . text
python -m pre_commit run --all-files
```

仅重建本包时使用 `python -m pip wheel --no-index --no-deps --no-build-isolation --wheel-dir out/wheelhouse .`。构建后端必须已准备；缺失时构建明确失败，不在检查中自动修复。

`tests/test_wheel.py` 会真实构建 wheel，创建临时 venv，通过 `--no-index --no-deps` 安装并用 `python -I` 消费。此定向测试只验证不需要外部工具的入口和包资源；完整依赖安装另由上述步骤及 CI 验证。测试不依赖固定兄弟仓库，不访问网络。

`tools/quality.py` 是本仓薄入口；只依赖已显式安装的包。开发时可以显式设置 PYTHONPATH 为本仓 src 调试，但它不能代替隔离 wheel 消费验证。CI 使用相同入口，Windows / Linux 执行计划见 `.github/workflows/ci.yml`；没有远端执行记录时不写“CI 已通过”。

量化本仓 Python 源码时，显式安装 pyproject.toml 的 `project.optional-dependencies.dev` 固定依赖，然后运行：

```text
python -c "import pathlib,subprocess,sys,tomllib; p=tomllib.loads(pathlib.Path('pyproject.toml').read_text('utf-8')); subprocess.run([sys.executable,'-m','pip','install',*p['project']['optional-dependencies']['dev']],check=True)"
python -m coverage run --branch --source=src/xgen_quality -m unittest discover -s tests -v
python -m coverage report -m
python -m coverage json -o out/reports/python-coverage.json
```

门禁分别计算 `covered_lines / num_statements` 和 `covered_branches / num_branches`，各至少 80%，拒绝零分母；CI 保存含未覆盖行/分支的完整 JSON。不用 coverage.py 的合计百分比代替两个独立指标，不把子进程的 wheel 测试调用自动计为已采集的源码覆盖。

更新 policy.json、模板或依赖版本时，检查相应命令的实际版本，执行负例和至少两个消费者的入口测试，记录破坏性变更。模板同步采用复制后审阅差异，不由检查命令自动覆盖配置。源码许可状态见 [PROVENANCE.md](PROVENANCE.md)，公开发布前须确认授权。
