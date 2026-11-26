# 可复用测试脚本

当前没有已验证的业务自动化脚本，不预置模拟成功的测试。

新增脚本时说明对应任务、用例、运行命令、依赖、环境参数、断言依据、退出码和数据清理方式。使用 `python3` 运行 Python 脚本；沿用后续确认的项目框架，不预先引入依赖。

脚本输出定向至 `.runtime/tasks/<TASK_ID>/<RUN_ID>/`，凭据通过受控的本地配置或环境变量提供，不写入源码、参数示例或日志。一次性探索脚本先留在 `.runtime/`，验证并经确认后再沉淀。

## 已登记脚本

### `tests/scripts/render_suite_report.py`
- **关联用例**：[KB-SUITE-001.md](../cases/KB-SUITE-001.md)（`CASE-01`～`CASE-10`，`#user-skill-crud`、`#image-gen` 等全部 23 个标签）
- **固定模板**：[kb-suite-001-report.html](../templates/kb-suite-001-report.html)
- **用途**：校验 `kb-suite-001-report.v1` JSON 数据（支持单个用例、多用例局部组合或全量 10 用例；支持传多个 `--data` 合并），并将数据注入固定 HTML 模板生成可离线打开的单文件交互报告。
- **依赖与运行环境**：仅依赖 macOS / Linux `python3`（3.9+ 标准库），无需第三方包。
- **常用命令**：
  ```bash
  # 仅校验数据结构
  python3 tests/scripts/render_suite_report.py --data tests/data/kb-suite-001-report-sample.json --validate-only

  # 单次/局部/全量渲染输出至当前 Run 的 artifacts/
  python3 tests/scripts/render_suite_report.py \
    --data .runtime/requests/<中文请求概要>/<RUN_ID>/artifacts/report-data.json \
    --out  .runtime/requests/<中文请求概要>/<RUN_ID>/artifacts/report.html

  # 多次局部执行结果合并输出为总览面板（后传入的同 Case 覆盖前者）
  python3 tests/scripts/render_suite_report.py --data runA.json --data runB.json --out merged-report.html
  ```
- **断言与校验依据**：校验 `schemaVersion == "kb-suite-001-report.v1"`、`meta` 必填字段（`suiteId`/`runId`/`env`）、`cases[*].id` 属于 `CASE-01`～`CASE-10` 且无重复、`status` 属于 `passed`/`failed`/`blocked`/`not_run`；转义 `</` 防 `<script>` 提前闭合。
- **退出码**：`0` 校验/渲染成功；`1` JSON 或 Schema 校验失败；`2` 参数缺失或模板/文件 I/O 错误。
- **数据清理**：脚本仅读取非敏感结构化数据并写出至指定 `--out`（建议位于 `.runtime/`），不写入任何外部系统或业务数据库。
