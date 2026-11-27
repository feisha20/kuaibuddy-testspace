# 可复用测试脚本

当前没有已验证的业务自动化脚本，不预置模拟成功的测试。

新增脚本时说明对应任务、用例、运行命令、依赖、环境参数、断言依据、退出码和数据清理方式。使用 `python3` 运行 Python 脚本；沿用后续确认的项目框架，不预先引入依赖。

脚本输出定向至 `.runtime/tasks/<TASK_ID>/<RUN_ID>/`，凭据通过受控的本地配置或环境变量提供，不写入源码、参数示例或日志。一次性探索脚本先留在 `.runtime/`，验证并经确认后再沉淀。

## 已登记脚本

> 本目录暂不单独存放独立报告脚本；原报告校验/渲染器与固定模板已并入共享技能 [kb-suite-runner](../../.agents/skills/kb-suite-runner/SKILL.md)（与同仓库 `kb-test-execution` 保持 `scripts/` + `assets/` 同构）。

### [render_suite_report.py](../../.agents/skills/kb-suite-runner/scripts/render_suite_report.py)
- **关联用例**：[KB-SUITE-001.md](../cases/KB-SUITE-001.md)（自动以该 Markdown 为单一事实源解析能力域、标准化能力标签与全部回归用例目录）
- **固定模板**：[kb-suite-001-report.html](../../.agents/skills/kb-suite-runner/assets/kb-suite-001-report.html)
- **用途**：解析 `--suite`（默认 `tests/cases/KB-SUITE-001.md`）并交叉校验 3.1/3.2/第 4 节自洽性，校验 `kb-suite-001-report.v1` JSON 数据（支持单个用例、多用例局部组合或全量用例；支持传多个 `--data` 合并），并将**目录数据（`#kb-suite-catalog`）**与**运行数据（`#kb-report-data`）**安全注入固定 HTML 模板生成可离线打开的单文件交互报告。
- **依赖与运行环境**：仅依赖 macOS / Linux `python3`（3.9+ 标准库），无需第三方包。
- **常用命令**：
  ```bash
  # 仅校验 KB-SUITE-001.md 目录结构自洽性
  python3 .agents/skills/kb-suite-runner/scripts/render_suite_report.py --check-suite

  # 基于 Markdown 测试集直接生成交互式浏览 HTML（0 已执行用例）
  python3 .agents/skills/kb-suite-runner/scripts/render_suite_report.py --preview-suite --out .runtime/scratch/suite-view.html

  # 刷新模板默认兜底目录快照
  python3 .agents/skills/kb-suite-runner/scripts/render_suite_report.py --sync-template

  # 仅校验报告数据结构（按当前测试集目录动态验证用例 ID）
  python3 .agents/skills/kb-suite-runner/scripts/render_suite_report.py --data tests/data/kb-suite-001-report-sample.json --validate-only

  # 单次/局部/全量渲染输出至当前 Run 的 artifacts/
  python3 .agents/skills/kb-suite-runner/scripts/render_suite_report.py \
    --data .runtime/requests/<中文请求概要>/<RUN_ID>/artifacts/report-data.json \
    --out  .runtime/requests/<中文请求概要>/<RUN_ID>/artifacts/report.html

  # 多次局部执行结果合并输出为总览面板（后传入的同 Case 覆盖前者）
  python3 .agents/skills/kb-suite-runner/scripts/render_suite_report.py --data runA.json --data runB.json --out merged-report.html
  ```
- **断言与校验依据**：校验 Markdown 测试集 3.1/3.2/第 4 节标签与用例交叉一致性；校验 `schemaVersion == "kb-suite-001-report.v1"`、`meta` 必填字段（`suiteId`/`runId`/`env`）、`cases[*].id` 动态属于当前测试集目录且无重复、`status` 属于 `passed`/`failed`/`blocked`/`not_run`；转义 `</` 防 `<script>` 提前闭合。
- **退出码**：`0` 校验/渲染成功；`1` JSON 或 Schema 校验失败；`2` 参数缺失或模板/文件 I/O 错误。
- **数据清理**：脚本仅读取非敏感结构化数据并写出至指定 `--out`（建议位于 `.runtime/`），不写入任何外部系统或业务数据库。
