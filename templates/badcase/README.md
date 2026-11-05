# Badcase HTML 模板

打开 `index.html`，默认展示虚构案例。导入 UTF-8 JSON 后可搜索、筛选、查看时间线并复制当前案例的 Bug 描述。数据仅在页面处理，刷新恢复示例；不发送网络请求，不保存导入数据。复制前请检查并脱敏。

将 `示例数据.json` 复制到当前 Run 的 `artifacts/`，按实际情况填写，然后通过页面「导入 JSON」选择。真实数据放在 `.runtime/`，不要提交 Git。

报告字段：`title`、`environment`、`period`、`timezone`、`note`、`cases`。每个案例的 `id` 必须是唯一非空字符串；其他字段包括 `title`、`priority`、`type`、`status`、`prompt`、`description`、`startTime`、`endTime`、`duration`、`runId`、`sessionId`、`cause`、`evidence`、`suggestion`。`timeline` 为数组，每步支持 `time`、`step`、`tool`、`command`、`result`。缺少的字段显示「未提供」。

提示词和工具结果应忠于证据；`cause` 中分别标明事实和待验证推断。`duration` 应注明是否为消息可见跨度。
