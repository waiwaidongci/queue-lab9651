import {Run,isPriorityResult} from '../types/domain';import {number,percent} from '../utils/format';
export function QueueSummary({run}:{run:Run}){const r=run.result;
  if(isPriorityResult(r)){
    const snap=r.input_snapshot;
    return <div className="queue-summary priority">
      <div><span className="eyebrow">{snap.study?.code} / 多票种抢占</span><h3>{snap.scenario?.name??run.name}</h3>
      <p>λ {number(r.total_arrival_rate)} 请求/min · {r.ticket_classes.length} 票种 · {r.windows.length} 窗 · 抢占 {r.total_preemptions} 次</p></div>
      <div><span>有限仿真平均等待（分钟）</span><b>{number(r.wait_interval.mean)}</b><small>无单一稳态解析值 · 重复均值{Math.round(r.wait_interval.confidence*100)}% t区间</small></div>
    </div>;
  }
  return <div className="queue-summary"><div><span className="eyebrow">{r.input_snapshot.study.code} / {r.input_snapshot.profile.name}</span><h3>{r.input_snapshot.scenario.name}</h3><p>λ {r.analytical.arrival_rate} 请求/min · {r.analytical.servers} 台 · 每台平均服务 {number(r.input_snapshot.scenario.mean_service_minutes,2)} min</p></div><div><span>稳态利用率 ρ</span><b>{percent(r.analytical.utilization)}</b><small>λ &lt; cμ / 稳态条件满足</small></div></div>;}
