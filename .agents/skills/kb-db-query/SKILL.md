---
name: kb-db-query
description: 通过 DBX MCP 只读查询指定环境的 KuaiBuddy 业务数据库，适用于查记录、核对字段、按条件统计、跨表对账和按模型汇总等。用户指定本技能时，直接使用 DBX MCP。
---

# KuaiBuddy 数据库查询

用户给出目标环境和要查的数据后，直接用 DBX MCP 完成查询，无需再次确认工具。若缺少会影响结果的环境或查询目标，先根据当前对话补齐，仍无法确定时再询问。

需要询问环境时，使用下表的选项文案和顺序。用户说“开发”即选择 DKF，说“测试”即选择 TKF。

| 环境选项 | DBX 连接 | 说明 |
|---|---|---|
| 生产/预生产 | `kuaibuddy-生产` | 共用业务库 `buddy_agent` |
| DKF（开发环境） | `kuaibuddy-dkf` | 开发环境 |
| TKF（测试环境） | `kuaibuddy-tkf` | 测试环境 |

## 调用 DBX MCP

先找当前会话中已挂载的 `dbx` 服务。在 Codex 中可直接使用已暴露的 `dbx_*` 工具。在 DeepSeek Harness 中，若工具通过 `call_mcp_tool` 暴露，先查看 `dbx` 的工具列表和参数定义，再选择服务 `dbx` 和实际工具名（例如 `dbx_execute_query`）。按宿主的调用 schema 填外层字段，把下表参数作为 DBX 工具的入参对象传入。

| DBX 工具 | 入参示例 |
|---|---|
| `dbx_list_connections` | `{}` |
| `dbx_list_databases` | `{"connection_name":"kuaibuddy-生产"}` |
| `dbx_list_tables` | `{"connection_name":"kuaibuddy-生产","database":"buddy_agent"}` |
| `dbx_describe_table` | `{"connection_name":"kuaibuddy-生产","database":"buddy_agent","table":"sessions"}` |
| `dbx_execute_query` | `{"connection_name":"kuaibuddy-生产","database":"buddy_agent","sql":"SELECT 1 AS ok"}` |

`dbx_list_connections` 无需连接参数。其余工具填写该列表确认的 `connection_name`，也可用 `connection_id`。`dbx` 是 MCP 服务名，`buddy_agent` 是数据库名。查询 SQL 必须放在 `sql` 字段。表中的 `SELECT 1` 仅演示参数格式。正式查询直接填写本次只读 SQL。

遇到 `missing field sql`，检查 `sql` 是否放在工具的入参对象内。遇到 `CONNECTION_NOT_FOUND`，先核对是否传了 `connection_name` 或 `connection_id`，再用连接列表核对值。修正对应字段后再重试。

## 查询步骤

1. 调用 `dbx_list_connections` 核对所选连接。每次查询显式传入所选连接和业务数据库。
2. 按需调用 `dbx_list_databases`、`dbx_list_tables` 和 `dbx_describe_table` 核对库、表、字段、关联键和枚举；已确认且仍适用的结构可以复用。DBX 不可用、连接不存在或权限不足时说明具体卡点。
3. 使用 `dbx_execute_query` 执行单条只读 SQL。生产或预生产的专属统计须使用已核实的环境字段，或可信来源提供的会话、运行标识限定范围。缺少区分依据时，说明无法按环境单独统计；用户明确要查共享库整体时，可按共享库口径汇总。明细仅选择必要字段，用明确过滤条件和行数上限；统计优先在库内聚合。按需求确认时间字段及其实际存储时区。用户说“昨天”等相对日期时，默认按北京时间解释，使用从当天零点（含）到次日零点（不含）的区间，并转换为目标字段的存储时区。
4. 给出结果，注明环境、时间范围、筛选和统计口径。结果为空、字段缺失或记录不完整时直接说明。按需对账，涉及账号或原始对话等敏感字段时仅回传完成任务所需的信息。

例如，`$kb-db-query 查共享库昨天的用户对话缓存命中率，按模型汇总`。可参考 `buddy_agent` 的 `session_model_call_usage` 与 `sessions`，按 `session_id` 关联，使用 `sessions.source = 0` 筛选用户对话，按用量的 `created_at` 和 `model_id` 聚合。缓存输入是总输入的子集，用 `SUM(input_cached_tokens) / NULLIF(SUM(input_tokens), 0)` 计算比例。总输入为零时标记无法计算。
