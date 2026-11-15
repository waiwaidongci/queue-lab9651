import {Result,isPriorityResult} from '../types/domain';import {number} from '../utils/format';
export function ReplicationChart({result:r}:{result:Result}){
  const priority=isPriorityResult(r);
  const values=r.replications.map(x=>priority?(x as any).overall.mean_wait_minutes:x.mean_wait_minutes);
  const analytic=priority?null:(r as any).analytical.mean_wait_minutes;
  const interval=r.wait_interval;
  const maximum=Math.max(...values,analytic??0,interval.upper)*1.2||1;
  const y=(v:number)=>215-v/maximum*175,x=(i:number)=>65+i/(values.length-1)*815;
  return <section className="replication-chart"><div className="section-top"><h3>独立重复的平均等待</h3><span>{r.replication_count} 次重复 / 每次保留{r.retained_per_replication}张</span></div><svg viewBox="0 0 940 260" aria-label="独立重复均值与等待对照">{[0,1,2,3,4].map(i=>{const v=maximum*i/4;return <g key={i}><line x1="65" x2="880" y1={y(v)} y2={y(v)} className="gridline"/><text x="55" y={y(v)+4} textAnchor="end">{number(v,2)}</text></g>})}{analytic!==null&&<line x1="65" x2="880" y1={y(analytic)} y2={y(analytic)} className="analytic-line"/>}<line x1="65" x2="880" y1={y(interval.mean)} y2={y(interval.mean)} className="simulation-line"/>{r.replications.map((p,i)=><g key={p.replication}><line x1={x(i)} x2={x(i)} y1={y(0)} y2={y(values[i])} className="replicate-bar"/><circle cx={x(i)} cy={y(values[i])} r="3" className="replicate-point"/>{(i===0||i===values.length-1||i===Math.floor(values.length/2))&&<text x={x(i)} y="240" textAnchor="middle">R{p.replication}</text>}</g>)}</svg><div className="chart-legend"><span><i/>重复均值 / 分钟</span>{analytic!==null&&<span className="analytic"><i/>Erlang-C稳态等待</span>}<span className="simulation"><i/>有限样本重复均值</span></div></section>;}
