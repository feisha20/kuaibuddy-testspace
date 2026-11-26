# 可复用测试数据

只保存人工构造、非敏感、可重复使用的样例和数据生成代码。真实客户信息、会话导出、账号与凭据不得进入此目录。

`dialogue-example.json` 是基础对话用例的虚构输入示例，字段仅为本地样例格式，不是 KuaiBuddy API 请求结构。使用前需结合正式需求确认场景；不包含预设的“真实模型输出”。

`kb-suite-001-report-sample.json` 是配合 [kb-suite-001-report.html](../templates/kb-suite-001-report.html) 与 [render_suite_report.py](../scripts/render_suite_report.py) 使用的非敏感四态结构样例（`kb-suite-001-report.v1`），用于演示单/多/全量用例结果如何映射至固定 HTML 报告面板；所有字段均为虚构脱敏示例。
