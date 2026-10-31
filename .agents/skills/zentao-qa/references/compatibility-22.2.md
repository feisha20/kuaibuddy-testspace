# 禅道22.2兼容记录

核实日期：2026-10-19。目标站点：`http://pm.kuaishang.cn/zentao/`。版本22.2由用户提供，工具未从服务端独立检测版本。初期仅登录和读取；此后按用户明确要求，为需求8092新增了两条用例并回读确认关联、步骤、预期及需求版本。

## 实现依据

- 官方22.2标签：`zentaopms_22.2_20260527`。
- 测试任务原生父子关系依据[22.2任务表单](https://github.com/easysoft/zentaopms/blob/zentaopms_22.2_20260527/module/task/config/form.php)的parent字段和[任务模型](https://github.com/easysoft/zentaopms/blob/zentaopms_22.2_20260527/module/task/model.php)的updateParent逻辑。使用POST v2/tasks传入parent，回读子任务parent和父任务isParent，不通过任务描述模拟关联。
- 启动任务使用PUT v2/tasks/{id}/start。[22.2任务数据处理](https://github.com/easysoft/zentaopms/blob/zentaopms_22.2_20260527/module/task/zen.php)的buildTaskForStart明确将left=0的单人任务直接置为done，因此工具要求用户确认正数剩余工时，不凭空填入工时，也不把开始误操作为完成。
- [官方22.2执行结果实现](https://github.com/easysoft/zentaopms/blob/zentaopms_22.2_20260527/api/v1/entries/testresults.php)：结果读取和新增使用v1；testtask和version是查询参数，请求体steps包含result/real，步骤按顺序映射。
- [官方22.2测试单详情实现](https://github.com/easysoft/zentaopms/blob/zentaopms_22.2_20260527/api/v1/entries/testtask.php)：用例执行条目随详情返回，使用page/limit分页。
- [官方22.2关联用例控制器](https://github.com/easysoft/zentaopms/blob/zentaopms_22.2_20260527/module/testtask/control.php)：linkCase和batchRun为控制器动作，经v2动态路由调用，并非官方OpenAPI登记接口。关联使用PUT v2/testtasks/{id}/linkCase，表单case/version为对应数组；模型使用replace，因此工具在提交前排除已有关联，避免覆盖执行条目。整体报告使用PUT v2/testtasks/batchRun，查询参数依次为productID、orderBy、from=testtask、testtaskID；22.2写路由按位置映射参数，不能随意交换顺序。batchRun的results独立保存整体结果，steps可用空字符串保留步骤未知状态，reals保存来源说明。
- [官方SDK](https://github.com/easysoft/zentao-api)：仅用于核对API定义。MVP无SDK运行依赖，未采用22.5新增的用例模块等接口。
- [官方22.2 API路由](https://github.com/easysoft/zentaopms/blob/zentaopms_22.2_20260527/framework/api/router.class.php)：编辑操作会从原表单补齐省略字段；工具提交明确变更，并在提交前核对修改时间。该检查不是服务端原子条件更新，无法完全消除检查后发生的并发写入。
- 用例评审依据上述22.2动态路由及[官方testcase控制器](https://github.com/easysoft/zentaopms/blob/zentaopms_22.2_20260527/module/testcase/control.php)的review方法，使用 `PUT /testcases/{id}/review`；[表单](https://github.com/easysoft/zentaopms/blob/zentaopms_22.2_20260527/module/testcase/config/form.php)接收result/reviewedBy/comment，[数据处理](https://github.com/easysoft/zentaopms/blob/zentaopms_22.2_20260527/module/testcase/zen.php)将pass映射为normal并写入评审日期，[模型](https://github.com/easysoft/zentaopms/blob/zentaopms_22.2_20260527/module/testcase/model.php)记录Reviewed操作。这是源码核实的动态动作，不是官方OpenAPI清单中的已登记接口。

## 能力与验证层次

| 能力 | 适配接口 | 本轮真实验证 |
|---|---|---|
| 登录 | POST v2/users/login | 已成功，Token不输出 |
| 产品、项目 | GET v2/products、projects | 已成功 |
| 冲刺列表 | GET v2/projects/{id}/executions | 已成功 |
| 冲刺需求 | GET v2/executions/{id}/stories | 已成功，已检查空集合与非空清单、完整分页 |
| 需求正文与验收标准 | GET v2/stories/{id} | 已成功，spec/verify字段均可读取 |
| 用例列表和详情 | GET v2/{scope}/{id}/testcases、testcases/{id} | 已成功 |
| 测试单列表 | GET v2/{scope}/{id}/testtasks | 已成功 |
| 测试单及用例执行条目 | GET v1/testtasks/{id} | 已成功 |
| 用例执行历史 | GET v1/testcases/{id}/results | 已成功 |
| Bug详情和修改时间 | GET v2/bugs/{id} | 已成功 |
| 构建列表 | GET v2/executions/{id}/builds | 已成功，已检查空集合响应 |
| 新增用例 | POST v2/testcases | 已按用户要求新增两条用例并回读通过 |
| 用例评审通过 | PUT v2/testcases/{id}/review | 已按用户确认，将新增两条用例正式评审通过并回读状态、评审人和日期 |
| 冲刺测试主子任务创建 | POST v2/tasks，子任务传parent | 已按用户要求创建主任务与需求子任务，回读parent及isParent正确 |
| 启动叶子测试任务 | PUT v2/tasks/{id}/start | 官方22.2源码核对及本地模拟验证；实机启动35055成功，主任务35054同步进入doing |
| 测试单创建 | POST v2/testtasks | 本地模拟测试；公司写入未验证 |
| 编辑Bug描述 | PUT v2/bugs/{id} | 已将92694正文按实例默认[步骤]/[结果]/[期望]模板更新，回读通过 |
| Bug创建及创建时指派 | POST v2/bugs | 已创建调试Bug92694，回读assignedTo/responsible均linjt、bugLabel=other、story8092及构建3565 |
| 新增逐步执行结果 | POST v1/testcases/{id}/results | 调试模拟记录65958已保存，四步pass/pass/fail/blocked及实际情况回读一致；本次响应非JSON，经只读reconcile-result核实并标记账本verified，无重发 |
| 测试单追加关联用例 | PUT v2/testtasks/{id}/linkCase | 已追加33350、33351到测试单2624并回读条目38477、38478；原有33347、33348执行结果保留 |
| 用户整体结果报告 | PUT v2/testtasks/batchRun | 已按用户调试授权为33351写入整体fail，记录65957；四个步骤结果留空，来源明确标注模拟数据 |

不要使用v2 `/testtasks` 无范围列表：实机返回控制器风格的tasks等字段，和标准testtasks契约不同。本工具强制使用product/project/execution范围的列表。

HTTP入口可直连，HTTPS443端口本轮不可达；本机环境代理未能访问该站点，配置为仅本工具noProxy=true。工具保留HTTP的实际传输状态，不宣称HTTPS。

账号密码长期使用：已按用户明确要求，将密码保存在本机忽略目录的0600配置中。2026-10-19实机验证了账号密码登录，并在客户端使用无效Token触发HTTP401，自动登录一次后成功重试只读产品查询。未以真实业务写请求验证续期。相关41项本地测试通过，覆盖只读续期、无Token登录、错误密码停止、写请求不重发、凭据范围隔离及原有测试协作流程。

权限、字段必填、自定义流程会受实例配置影响。本地测试通过不代表公司写入权限和业务关联已验收；需要实际指定产品、冲刺、构建及允许的测试数据范围，才能开展写入验收。

2026-10-19补充评审兼容验证：评审接口省略reviewedDate时返回“评审时间应当为合法的日期”，工具现显式发送YYYY-MM-DD日期。失败请求经待评审状态、空评审字段和无Reviewed历史核实未生效后，保留核查证据恢复本地状态，再提交成功。需求8092下用例33350、33351已由linjt评审通过，日期2026-10-19；未产生测试执行结果。

用户指定新增用例默认评审通过，已加入创建后的正式评审流程。当前55项本地测试通过，覆盖默认评审、显式保留待评审、评审回读失败恢复、评审超时防重及日期校验。自动创建后评审流程的组合由本地模拟验证，真实站点已分别验证创建和正式评审。

2026-10-19主子任务实机验证：冲刺857下创建测试主任务35054，创建需求8092的测试子任务35055，子任务parent=35054，父任务isParent=1，两者均指派给linjt。工具未填入未经指定的预计工时和截止日期。当前58项本地测试通过，新增父子关系校验、跨冲刺/错误类型/已关闭父任务拦截及防重复提交验证。

启动任务防护补充：当前61项本地测试通过，覆盖正数剩余工时校验、实际开始时间、父任务联动、保留既有消耗和启动防重。用户确认剩余2小时后，2026-10-19 10:57:49实机启动任务35055成功；回读子任务与主任务35054均为doing，剩余均为2小时，已消耗均为0小时。未执行功能用例或写入执行结果。

2026-10-19执行流程验证：现有测试单2624原有33347、33348的历史pass结果未覆盖；追加33350、33351后，按用户明确授权写入33351的调试模拟失败结果65957（run38478）。未执行广告账户实际操作，未创建Bug，未改变工作任务消耗工时。当前70项本地测试通过，新增追加关联防覆盖、版本/范围冲突拦截、整体失败与步骤未知分离、超时防重及提交后仅回读恢复测试。逐步result.submit仍只有本地模拟验证，本次实机验证的是独立的result.report链路。

2026-10-19页面反馈修正：用户截图中记录65957只有整例失败，逐步结果及实际情况显示空白。API实际已保存real，但[22.2结果页](https://github.com/easysoft/zentaopms/blob/zentaopms_22.2_20260527/module/testtask/ui/results.html.php)对测试结果和实际情况两列均使用非空stepResult.result作为展示条件。不能把整体报告写入成功当作逐步展示验收。

按用户已授权的模拟调试，追加记录65958：四步结果分别pass、pass、fail、blocked，每步实际情况包含明确的调试模拟标记。result.submit增加simulation=true，模拟不传真实起止时间，真实结果仍要求原始时间。POST响应非JSON但结果已落库，经唯一key、run38478、version1及四步完整回读确认；reconcile-result仅修复本地账本为verified，没有再次提交。API保存已验证，展示规则已核对官方源码，未启动浏览器复查。76项本地测试通过，覆盖模拟标记、真实时间要求、来源标记丢失拦截以及响应异常后的只读账本恢复。

2026-10-19 Bug登记验证：按用户明确要求，依据模拟执行记录65958登记调试Bug92694，指派给linjt。官方OpenAPI包含assignedTo，工具此前白名单漏项已补齐。公司实例额外要求bugLabel[]、responsible；首次请求因此被拒绝，完整读取产品98的264条Bug确认无同标题记录，保留拒绝及查询证据后补齐字段，以变更后的新计划创建成功。原拒绝计划和账本仍保留，不能误重跑。bugLabel用数组提交、字符串回读时按集合核对；问题责任人不等于指派人，不在Skill中默认两者永远相同。

创建92694后服务端编辑器移除了重现步骤中相邻ol/p块间的一处换行，导致原严格比对报VERIFY_FAILED；工具现仅规范化相邻块间空白，保留正文和段内空格检查。同一submitted计划重跑仅回读并核验成功，无重复创建。81项本地测试通过，覆盖Bug指派、防重、负责人不一致拦截、自定义字段格式及富文本格式规范化。未启动浏览器验收；用例及执行结果的追溯编号写在Bug重现步骤，未声明原生用例外键关联。

2026-10-19模板修正：用户截图指出Bug92694正文未遵循禅道默认模板。GET v2/bugs/create实机返回bug.steps为[步骤]、[结果]、[期望]三段；API创建不会自动套入网页模板，之前Agent自行排版导致偏离。现Skill明确先读实例模板、按原栏目及顺序填入正文；已仅更新92694的steps，保留模拟标识和追溯信息。首次编辑的lastEditedDate为空是合法状态，工具允许expected.lastEditedDate为空字符串，但仍严格比较当前值；有并发变更时拒绝。82项本地测试通过，新增首次编辑空时间及并发保护验证。已回读正文，未启动浏览器复查。

2026-10-19详情精简修正：用户指出步骤中混入调试说明及前置条件。已将92694正文再次精简为三段：操作步骤、带简短模拟标记的异常现象、预期行为。移除详情中的独立前置条件段、调试说明和追溯清单；必要初始状态融入操作，来源关联保留在本机计划/记录。PUT仅修改steps，回读通过。Skill及命令示例已同步改正，此条取代先前将前置条件和追溯信息塞入模板栏目的做法。

2026-10-19截图上传验证：依据官方22.2 OpenAPI的POST /files及[module/file/control.php](https://github.com/easysoft/zentaopms/blob/zentaopms_22.2_20260527/module/file/control.php) ajaxUpload，新增bug.attach，通过multipart的file/objectType/objectID原生关联截图。实机将用户上一条Bug界面截图上传至92694，生成文件480568；PNG大小393087字节与Bug.files回读一致，objectType=bug、objectID=92694。随后独立bug.update将已返回同站点图片URL插入[结果]栏目，正文回读一致。未进行浏览器显示验证，图片来源为调试Bug界面，不是广告账户功能失败的真实截图。

当前90项本地测试通过，覆盖二进制multipart传输、源文件变更/大小/格式/文件名校验、目标需求约束、原生附件关联核验、超时不重传与提交后只回读。当前上传仅支持10MiB以内PNG，避免JPEG服务端压缩改变字节大小的未验证行为。图片、计划与本机凭据均不进入安装ZIP。

2026-10-19正文图片故障修复：用户截图证明此前只核验附件和正文引用不足以保证图片可读。上传响应url的index.php文件read路由实机返回HTTP200的HTML页（16527字节），附件元数据webPath则返回393087字节PNG，SHA256与原图完全一致。新增read bugimage，仅从目标Bug真实附件元数据选同站点data/upload路径，不带Token、不跟随跳转，检查PNG字节及SHA256。bug.attach回读也增加相同字节核验，返回可读取的url；响应原url另存uploadUrl供诊断。已将92694的img.src改为核验后的webPath，未重复上传480568。92项本地测试通过，新增HTTP200/HTML拒绝、静态请求不发送Token、地址范围限制及图片回读失败后不重传测试。PNG字节读取与正文保存已验证；未启动浏览器复查显示。
