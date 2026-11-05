---
name: kb-bug-analyse
description: 在 KuaiBuddy 测试工作区根据 runId、会话或禅道 Bug，以 Langfuse、ELK 和代码证据核查工具调用及运行异常。
---

# KuaiBuddy 运行与问题分析

用于核查授权环境中某次运行的工具调用、模型、异常及时间线，也可分析禅道 Bug。先读取工作区 AGENTS.md、README.md 和 docs/project.md，按本次任务确认环境、账号权限、数据范围和外部操作授权。本技能是从本机技能脱敏适配的项目副本，不包含凭据及浏览器登录态。

## 配置与产物

- Python 使用 `python3`，标准库；脚本默认读取工作区根目录 `.env.observability`（由 `.gitignore` 忽略），已有进程环境变量优先；变量名见 [config.example.env](config.example.env)。不得打印配置、密钥或 Authorization，也不从其他项目复制凭据或登录态。
- 用户于 2026-11-05 说明：KuaiBuddy 生产与预生产共用 Langfuse trace 和 ELK 观测信息。该说明不代表两种业务环境相同，也不自动授权访问生产数据；运行归属需结合业务环境、runId、sessionId、时间及可用环境标识核实。
- 观测配置映射：生产环境和预生产环境均使用 `--env prd`（读取 `KB_LANGFUSE_PRD_*`、`KB_ELK_PRD_*`）；独立测试环境使用 `--env test`（读取对应 `*_TEST_*`）。来源：用户于 2026-11-05 提供的本机配置备注；实际连接和权限按本次任务核实。
- 脚本中的 `--env` 指观测配置组，不单独证明业务运行环境。生产与预生产共享观测数据，须通过明确的业务环境、runId、sessionId、时间和可用的环境标识核实归属；不得因使用 `prd` 配置而越权查询生产业务数据，也不能擅自跨环境扫描。`dev` 映射需另行核实。
- 产物输出到当前 Run 的 `artifacts/` 或 `logs/`，探索草稿放 `.runtime/scratch/`；日志、会话、提示词可能含敏感数据，访问和归档遵循工作区规则。不要输出到 Downloads 或提交 Git。
- 禅道 Bug 通过项目内 `zentao-qa` 技能只读查询。禅道评论不属于此副本的能力；发送消息或回填须有明确授权和受支持的工具，不得自行调用个人技能的评论脚本。

## 方法

1. 明确 runId、sessionId、环境和时间范围；没有这些信息时先检查本次运行记录。测试核查可从运行事件、工具调用和结果入手，不要求先存在 Bug。
2. 用 Langfuse 观察结构、模型、工具、状态和时间；用目标 runId / sessionId 精确关联。按需在同一环境基于缩小的时间窗查询 ELK；日志相关性不是因果证明。缺少记录时分别报告未采集、无权限、未命中和执行失败。
3. 只有需要定位原因时，结合目标版本的应用层及 AgentScope 框架源码；不要预设异常一定发生在某一层。路径和部署版本需按本次核实，不能从其他项目导入凭据或假定历史路径有效。
4. 测试结论分别列出事实、分析推断和证据缺口；记录真实标识、查询条件、时间和证据位置。未验证的模型判断不得写成已确认根因。
5. 结束分析或探索时，按 [知识积累流程](../../../docs/knowledge-workflow.md) 检索已有资产并记录候选，区分一次性现象、可复用经验和待验证推断。

## 脚本入口

从仓库根目录调用脚本，下面 `<当前Run>` 必须替换为当前运行目录。以下示例适用于生产或预生产共用的观测配置，不包含任何凭据：

```bash
python3 .agents/skills/kb-bug-analyse/scripts/runid_probe.py --env prd --run-id <runId>
python3 .agents/skills/kb-bug-analyse/scripts/langfuse_fetch.py --env prd --run-id <runId> --output-dir <当前Run>/artifacts
python3 .agents/skills/kb-bug-analyse/scripts/elk_search.py --env prd --keywords <runId> --time-from <开始时间> --time-to <结束时间> --output-dir <当前Run>/logs
```

`runid_probe.py` 用于只读探测；`langfuse_fetch.py` 用 observations 游标分页并区分主运行和旁路；`elk_search.py` 支持关键词、logger 和级别。logger 名在部分部署中可能为缩写，须以实际日志为准。缺少配置时应报错，不自动回退其他环境。

本副本的 Langfuse 脚本当前只整理结构、时间、模型及状态，**未请求也未输出 input/output**，因此不能仅靠它证明工具的参数或具体结果。部分部署支持通过 observations 的 `io` 字段获取输入输出，需在确认权限、服务能力及脱敏要求后选择受支持的方法；不可断言该服务一定没有这些字段。判断工具是否实际执行，应优先使用可用的工具事件、授权后的 trace 输入输出或日志，并明确证据限制。

本技能不自动发送对话、执行产品测试或写入禅道。任何测试执行、生产数据访问和外部写入均按用户授权及工作区规范进行。
