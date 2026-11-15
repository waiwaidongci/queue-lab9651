import {useState} from 'react';import {Link,useSearchParams} from 'react-router-dom';import {useResearchData} from '../hooks/useResearch';import {QueueSummary} from '../components/QueueSummary';import {ReplicationChart} from '../components/ReplicationChart';import {WaitComparison} from '../components/WaitComparison';import {PriorityResultPanel} from '../components/PriorityResultPanel';import {DataTable} from '../components/common/DataTable';import {StatusBadge} from '../components/common/StatusBadge';import {Notice} from '../components/common/Notice';import {number,percent} from '../utils/format';import {isPriorityResult} from '../types/domain';
export function Results(){const s=useResearchData(true),[params]=useSearchParams(),[selected,setSelected]=useState(Number(params.get('run'))||0),run=s.runs.find(r=>r.id===selected)||s.runs[0];
  const priority=run?.status==='completed'&&isPriorityResult(run.result);
  return <div className="page results-page"><div className="page-title"><div><p className="eyebrow">ANALYSIS & SIMULATION / 04</p><h1>等待对照<span>把稳态参考与有限顾客估计，放在同一把刻度上。</span></h1></div><Link className="outline" to={'/notes'+(run?'?run='+run.id:'')}>提交容量建议 →</Link></div><Notice message={s.error} retry={s.refresh}/><div className="run-picker"><label>运行档案<select aria-label="运行档案" value={run?.id||''} onChange={e=>setSelected(Number(e.target.value))}>{s.runs.map(r=><option key={r.id} value={r.id}>#{r.id} / {r.name} / {r.status}</option>)}</select></label>{run&&<StatusBadge status={run.status}/>}</div>
  {run?.status==='completed'?<>
    <QueueSummary run={run}/><WaitComparison result={run.result}/><ReplicationChart result={run.result}/>
    {priority?<PriorityResultPanel r={run.result as any}/>:<FcfsBody run={run}/>}
    <div className="result-guard"><b>{priority?'多票种抢占估计，无适用单一解析值。':'有限顾客估计，不是稳态公式的精确复现。'}</b><p>{run.result.ci_note} {run.result.finite_window_note}</p></div>
    {run.result.wait_interval.degenerate&&<Notice message="重复均值方差为零，t区间退化；不能把该区间当作无不确定性的证明。"/>}
    {!priority&&<p className="fingerprint">输入SHA256 {run.result.input_hash}</p>}
  </>:run?<div className="pending"><h2>{run.status==='failed'?'试验未能完成':'后台正在执行独立重复'}</h2><p>{run.error||'计算到达与服务完成事件，本页每2秒更新。'}</p></div>:<p className="empty">尚无运行，请先创建服务情景。</p>}
  </div>;}

function FcfsBody({run}:{run:any}){const r=run.result;return <>
  <div className="section-heading"><h2>独立重复明细</h2><span>暖机{run.warmup} / 每次保留{r.retained_per_replication}人</span></div>
  <DataTable head={['重复','平均等待 min','平均系统 min','等待比例','窗口忙碌率','观察窗口 min','到达/服务子流键']}>{r.replications.map((x:any)=><tr key={x.replication}><td>R{x.replication}</td><td>{number(x.mean_wait_minutes,4)}</td><td>{number(x.mean_system_minutes,4)}</td><td>{percent(x.wait_probability)}</td><td>{percent(x.busy_fraction_window)}</td><td>{number(x.window_minutes,1)}</td><td className="mono">{x.arrival_spawn_key.join('.')} / {x.service_spawn_key.join('.')}</td></tr>)}</DataTable>
  <div className="section-heading"><h2>首个重复的顾客事件抽样</h2><span>抽样展示，均值使用全部保留顾客</span></div>
  <DataTable head={['顾客序','到达 min','开始服务 min','完成 min','服务台','等待 min','到达后排队数']}>{r.sample_customers.slice(0,20).map((c:any)=><tr key={c.customer}><td>#{c.customer}</td><td>{number(c.arrival,2)}</td><td>{number(c.service_start,2)}</td><td>{number(c.completion,2)}</td><td>{c.server}</td><td>{number(c.wait,3)}</td><td>{c.queue_after_arrival}</td></tr>)}</DataTable>
  <p className="caption">{r.assumptions}</p>
</>;}
