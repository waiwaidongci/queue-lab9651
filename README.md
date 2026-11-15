# 栈桥窗口排队研究席 · QUEUE LAB

用Erlang-C稳态解析和独立重复FCFS仿真，分别研究匿名票证窗口的等待与容量假设；另提供多票种、通办/专办窗口混用的抢占式优先级仿真，量化急件对普通票的挤占。

## 业务与权限

码头服务研究所有16位运营分析员。以往用平均服务时长乘排队人数估等待，忽略系统饱和、空系统启动和随机误差。上游是到达/服务参数底稿，本应用替代排队机制研究和容量试验段，下游是运营容量讨论，不控制真实窗口或自动排班。

| 角色 | 权限 | 典型动作 |
|---|---|---|
| admin / 运营研究负责人 | 六页读写、研究备注、创建情景/运行、批准/退回 | 核对容量建议和适用边界 |
| analyst / 排队分析员 | 六页阅读、创建情景/运行、提交建议；不能审批或改研究备注 | 比较解析与有限仿真 |
| viewer / 窗口观察员 | 六页只读，仅获批完成运行可导出 | 阅读与下载研究CSV |

所有角色导出都要求对应运行完成且有获批建议。批准是研究底稿归档，不是现场等待时间或服务水平承诺。

## 快速启动

```bash
cp .env.example .env
docker compose up -d --build
docker compose ps
docker compose exec -T backend python -m scripts.seed_demo
```

[前端](http://localhost:18220)，[API文档](http://localhost:19220/docs)。Nginx去掉`/api/`前缀代理给FastAPI，直接后端接口不加该前缀。

| 邮箱 | 密码 | 角色 |
|---|---|---|
| admin@zhanqiao.demo | Zhanqiao2026! | admin |
| analyst@zhanqiao.demo | Zhanqiao2026! | analyst |
| viewer@zhanqiao.demo | Zhanqiao2026! | viewer |

恰好frontend/backend/worker/db/redis五服务，全部有健康检查与健康依赖。PostgreSQL16、Redis7分别命名卷，backend/worker共享JSON产物卷。worker按队列执行Python计算并刷新心跳。初次ORM metadata建表，迁移目录是索引示例；后续结构升级需审查迁移。

## 输入单位与种子

时间统一**分钟**。到达率λ为请求/分钟，服务输入为单台平均分钟/人，对应每台服务率`μ=1/平均服务分钟`，总容量为cμ请求/分钟。不要把每小时到达率直接输入λ，也不要把平均服务分钟当μ。

`pier-window-parameters-202611.json`为合成参数底稿：东/西栈桥两个研究，3份到达配置λ=.45/.70/1.05，6份双台/三台服务情景。上午平均服务2.5分钟，另两配置为1/.45分钟。集中时段双台情景ρ>1，故意保留用于展示“无稳态”拒绝；其余5份满足稳态条件。预置基准运行实际生成3000顾客/暖机500/20独立重复、seed2026，并有获批研究建议。

seed按邮箱、研究code、到达配置code、服务情景code、基准运行name查重，只补缺失，不覆盖已有备注。启动`SEED_DEMO=true`自动执行，失败记日志不阻断。研究备注可由admin修改；真实seed保留修改验收在外置测试目录。

## 一天剧本

1. 09:00 季遥以analyst登录，核对午后λ=.7请求/分钟、每台平均服务2.2222分钟。
2. 创建“午后双窗口复核”，c=2，检查总容量约.9请求/分钟、ρ约77.78%。
3. 创建3000顾客、前500顾客暖机、20重复、根种子2026的容量试验。
4. worker先求稳态Erlang-C，再为每次重复生成独立到达/服务随机流，按FCFS处理服务完成事件。
5. 09:05 阅读稳态平均等待3.402778分钟，与有限顾客重复均值及t区间对照。
6. 检查20次重复、首个重复中顾客#501起的事件时刻，不把同队列顾客当独立样本算区间。
7. 提交增加第三窗口、检验到达/服务分布的后续容量假设。
8. 陆潮以admin审阅，说明稳态与有限时段、暖机偏差和现场验证边界，批准或退回。
9. 沈帆以viewer下载20行重复CSV；参数快照、根种子和完整结果通过运行API/共享JSON保存。

## 两种计算的边界

**Erlang-C稳态解析**：M/M/c，Poisson到达、独立同速指数服务、无限等待空间、FCFS。必须`λ<cμ`，否则运行422拒绝，不给伪稳态指标。令a=λ/μ、ρ=a/c：

```
p0 = 1 / [sum(a^n/n!, n=0..c-1) + a^c/(c!*(1-rho))]
P(wait) = a^c/(c!*(1-rho)) * p0
Wq = P(wait)/(c*mu-lambda)
W = Wq+1/mu; Lq=lambda*Wq
```

实现用递推项避免直接大阶乘，支持1–20台、每分钟率[1e-6,1000]。服务均值API限制[.001,120]分钟，防止倒数溢出。参考[Tufts排队论课程资料](https://www.cs.tufts.edu/comp/250P/classpages/queue.html)。

**有限顾客FCFS事件仿真**：每次重复从空系统开始。到达间隔和服务时长分别由独立指数随机流生成；按到达顺序从最早服务完成时刻堆选台，`start=max(arrival,earliest completion)`，再入堆真实完成时刻，同刻按顾客序和服务台编号稳定处理。保留前面顾客对系统状态的影响，只从统计样本中剔除每次的前warmup位顾客，不重置系统或按分钟删暖机。

每次生成总顾客数N，统计N−warmup位；每个重复独立。NumPy SeedSequence(root).spawn(R)，每次再spawn到达和服务两个子流，结果记录spawn_key。事件抽样只用于展示，均值计算使用全部保留顾客。

**t区间**：以R个独立重复的平均等待`m_r`计算`mean(m) ± t_(R-1,(1+confidence)/2)*sd(m)/sqrt(R)`，不是对全部顾客算独立样本区间。使用[SciPy Student t](https://docs.scipy.org/doc/scipy-1.15.1/reference/generated/scipy.stats.t.html)分位数，默认为95%。这是重复均值近似区间，不含参数误差、模型失配或暖机偏差，不作精确有限覆盖承诺。区间未经非负截断；零重复方差明确标degenerate并提示不能证明无不确定性。

窗口忙碌率取首个保留顾客到达到全部顾客服务完成的窗口，汇总各服务区间与窗口的交集/可用服务台时间，含暖机顾客剩余工作与尾部排空。它与稳态ρ不同。有限顾客模拟均值也不必等于稳态公式；高负荷时500顾客暖机可能远远不足。

单任务500–10000顾客、暖机0–5000且保留至少100人、5–40重复、总顾客最多250000。拒绝无稳态、非法率/服务台/时长、过量任务、错误暖机。固定种子/快照支持复算；输入hash覆盖研究/到达/服务完整快照、顾客/暖机/重复/根种子/置信水平及方法版本。worker使用持久化快照，不读取后续被改动的来源备注。

## 多票种抢占优先级仿真（通办/专办混用）

旧FCFS容量试验只有同质单队列，看不出急件挤占。情景可切换为`priority`模式，按票种配置**到达占比（合计=1）、平均服务时长、普通normal/紧急urgent等级**，并为每个窗口配置**可办票种**（通办窗可办多种、专办窗只办指定票种）。

**调度规则（确定性、纯标准库实现，无新依赖）**：

1. 空窗分配按层级目标：先用票种—窗口二分图**最大基数匹配使急件开工数最多**，再对剩余空窗匹配普通票使总开工数最多；在同为最大基数的匹配中，同级按到达先后（同刻按全局票序）先到先办。
2. 急件到达且无兼容空窗时，在“兼容且正服务普通票”的窗口上对等待急件做最大匹配抢占；**急件不抢占急件**。
3. 被中断普通票**保留剩余服务量**、计一次抢占，回到等待并可在任意兼容窗口（含其他窗口）续办。
4. 事件同刻时**服务完成先于到达**；每张票的等待是其所有未在窗内接受服务时段之和（含被抢占后的再等待）。

**随机流与护栏**：按票种占比混合的Poisson到达、逐票种独立指数服务；根种子按`(重复号, 流号)`派生独立`random.Random`子流（流0到达、流1服务），冻结快照与种子即可逐位复算。顾客/暖机/重复/总量护栏与FCFS路径一致；另在入队前做粗负荷护栏（加权平均服务×总到达率 < 窗口数），过载直接422拒绝，不制造无限增长队列。

**报告与解析边界**：按票种给出累计等待、平均/最大等待、等待比例、**抢占次数/被抢占票数、完成数**及服务需求与已服务量；总体给出重复均值t区间（无SciPy时用标准库正则化不完全beta反解Student-t分位数）。多票种、异速服务、窗口可办受限且含抢占续办，**不存在可直接套用的单一M/M/c Erlang-C解析值**，结果中`analytical=null`并显式说明。每次重复与跨重复均输出**服务量守恒核对**（初始需求=已服务+剩余、全时域窗口忙碌与已服务逐分钟对齐，缺口应为0/浮点误差级），获批CSV含票种级、守恒块与重复级三段，可离线核对。

**旧单队列仍可读**：`mode=fcfs`（默认）走原Erlang-C + FCFS路径与原CSV导出；历史运行快照无`mode`字段时按fcfs处理，旧数据与导出格式不变。

## 页面与工程

六页：容量总览、输入核对、情景与运行、等待对照、建议审阅、试验留痕。QueueStudy / ArrivalProfile / ServiceScenario / SimulationRun / CapacityNote五实体贯穿模型、schema、service、route、前端API/store及页面，User/Audit为横切；多票种模式另由TicketClassConfig（票种）与ServiceWindow（窗口可办票种）两个关联实体承载。

| 部分 | 技术 |
|---|---|
| 后端 | Python3.11 / FastAPI / SQLAlchemy / NumPy / SciPy |
| 前端 | React18 / TypeScript / Vite6.4.6 / Lucide |
| 数据 | PostgreSQL16 / Redis7 AOF |
| UI | 水工橘施工纸、栈桥断面线；IBM Plex Mono + Noto Sans SC |

```
backend/src/{models,schemas,services,controllers,routes,middlewares,utils,constants,config}
backend/src/{main.py,worker.py}
backend/scripts/seed_demo.py
backend/migrations/001_initial.sql
frontend/src/{api,stores,types,components,hooks,pages,router,utils,constants}
```

QueueSummary/WaitComparison在首页、结果、建议共用，ReplicationChart跨首页/结果，ProfileSelector在配置复用；DataTable/Notice/StatusBadge、useAction/useResearchData、format各自分工。角色枚举`backend/src/constants/roles.py`、运行枚举`status.py`对应`frontend/src/constants/enums.ts`，路由/worker真实使用。JWT8小时、PBKDF2-SHA256、每次数据库角色授权。审计覆盖登录、备注、情景、运行和建议审批；错误与登录限流为两个中间件。

## 配置与开发

| 变量 | 默认 | 说明 |
|---|---|---|
| COMPOSE_PROJECT_NAME | queue-lab | 命名隔离 |
| FRONTEND_PORT | 18220 | 前端 |
| BACKEND_PORT | 19220 | 后端 |
| DB_PORT | 17720 | PostgreSQL宿主映射 |
| JWT_SECRET | local-queue-lab-change-this-key | 本地演示值，部署前更换 |
| SEED_DEMO | true | 自动seed |

本地Python3.11安装requirements，设置DATABASE_URL/REDIS_URL，`cd backend && uvicorn src.main:app --reload`并另起`python -m src.worker`。前端`npm install && npm run dev`，本地为`/api`配置反向代理；标准演示以Compose为准。

```bash
docker compose down -v --remove-orphans
```

外置测试/截图/TESTING在`../../test-artifacts/gb-0016/`。源码不含日志、截图或测试报告；.env、缓存忽略提交。

## 已知差异

合成恒定参数，无真实到达轨迹导入，不实现非平稳到达、放弃、有限排队空间。FCFS路径不实现优先级；多票种路径实现两级（普通/紧急）抢占但不支持多级动态优先级、票种改派或人员技能学习。多票种无稳态解析值，仅有限仿真与重复均值t区间。有限顾客从空系统开始并排空，默认暖机不足以证明稳态。t区间仅重复均值近似、不会解释模型偏差。单worker无running自动恢复/事务outbox/多实例锁，中断需重提；登录限流单进程。metadata首建表不是完整迁移链，字体网络不可用时回退。不执行现场排班。

## License

MIT，见LICENSE。
