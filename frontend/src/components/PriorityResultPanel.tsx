import {PriorityResult} from '../types/domain';
import {DataTable} from './common/DataTable';
import {number,percent} from '../utils/format';

export function PriorityResultPanel({r}:{r:PriorityResult}){
  const cons=r.conservation;
  return <div className="priority-results">
    <div className="section-heading"><h2>按票种结果（跨重复汇总）</h2><span>累计等待 · 抢占次数 · 完成数</span></div>
    <DataTable head={['票种','等级','到达占比','平均服务 min','平均到达','平均完成','累计等待 min','平均等待 min','等待比例','抢占次数','被抢占票数','服务需求 min','已服务 min']}>
      {r.per_ticket_summary.map(c=><tr key={c.ticket}>
        <td><b>{c.ticket}</b><small>{r.ticket_classes.find(x=>x.code===c.ticket)?.name??''}</small></td>
        <td><span className={'level-badge '+c.level}>{c.level==='urgent'?'紧急':'普通'}</span></td>
        <td>{percent(c.arrival_share)}</td>
        <td>{number(c.mean_service_minutes,2)}</td>
        <td>{number(c.mean_arrivals,1)}</td>
        <td>{number(c.mean_completed,1)}</td>
        <td>{number(c.cumulative_wait_minutes,1)}</td>
        <td>{number(c.mean_wait_minutes,3)}</td>
        <td>{percent(c.wait_probability)}</td>
        <td className="mono strong">{c.preemptions}</td>
        <td>{number(c.preempted_jobs,0)}</td>
        <td>{number(c.mean_service_demand_minutes,1)}</td>
        <td>{number(c.mean_served_minutes,1)}</td>
      </tr>)}
    </DataTable>

    <div className="section-heading"><h2>服务量守恒核对</h2><span>初始需求 = 已服务 + 剩余；窗口忙碌逐分钟对齐</span></div>
    <div className={'conservation-card '+(cons.all_replications_balanced?'safe':'warning')}>
      <div><span>全部重复守恒</span><b>{cons.all_replications_balanced?'通过 ✓':'未通过 ✗'}</b></div>
      <div><span>平均初始服务需求 min</span><b>{number(cons.mean_total_service_demand_minutes,2)}</b></div>
      <div><span>平均已服务 min</span><b>{number(cons.mean_served_minutes,2)}</b></div>
      <div><span>平均剩余 min</span><b>{number(cons.mean_remaining_minutes,4)}</b></div>
      <div><span>全时域窗口忙碌 min</span><b>{number(cons.mean_window_busy_minutes_full_horizon,2)}</b></div>
      <div><span>最大需求缺口（绝对值）</span><b>{number(cons.max_abs_demand_gap,9)}</b></div>
      <div><span>最大忙碌缺口（绝对值）</span><b>{number(cons.max_abs_busy_gap,9)}</b></div>
    </div>

    <div className="section-heading"><h2>独立重复明细（总体）</h2><span>暖机{r.warmup} / 每次保留{r.retained_per_replication}张</span></div>
    <DataTable head={['重复','平均等待 min','平均系统 min','等待比例','抢占次数','忙碌率','观察窗口 min','守恒平衡','到达/服务子流键']}>
      {r.replications.map(x=><tr key={x.replication}>
        <td>R{x.replication}</td>
        <td>{number(x.overall.mean_wait_minutes,4)}</td>
        <td>{number(x.overall.mean_system_minutes,4)}</td>
        <td>{percent(x.overall.wait_probability)}</td>
        <td className="mono strong">{x.overall.preemptions}</td>
        <td>{percent(x.overall.busy_fraction_window)}</td>
        <td>{number(x.overall.window_minutes,1)}</td>
        <td><span className={x.conservation.balanced?'safe':'warning'}>{x.conservation.balanced?'平衡':'异常'}</span></td>
        <td className="mono">{x.arrival_spawn_key.join('.')} / {x.service_spawn_key.join('.')}</td>
      </tr>)}
    </DataTable>

    <div className="section-heading"><h2>首个重复的票事件抽样</h2><span>含被抢占票的换窗续办轨迹，抽样展示</span></div>
    <DataTable head={['全局序','票种','等级','到达 min','首次开工','完成 min','使用窗口','等待 min','抢占次数','服务需求 min']}>
      {r.sample_customers.slice(0,20).map(c=><tr key={c.seq}>
        <td>#{c.seq}</td><td>{c.ticket}</td>
        <td><span className={'level-badge '+c.level}>{c.level==='urgent'?'急':'普'}</span></td>
        <td>{number(c.arrival,2)}</td><td>{number(c.first_start,2)}</td><td>{number(c.completion,2)}</td>
        <td className="mono">{c.windows_used.join('→')}</td>
        <td>{number(c.wait,3)}</td><td className="mono">{c.preemptions}</td><td>{number(c.service_demand,2)}</td>
      </tr>)}
    </DataTable>
    <p className="caption">{r.assumptions}</p>
    <p className="caption analytic-na">{r.analytical_note}</p>
    <p className="caption">{r.rng_note}</p>
    <p className="fingerprint">输入SHA256 {r.input_hash}</p>
  </div>;
}
