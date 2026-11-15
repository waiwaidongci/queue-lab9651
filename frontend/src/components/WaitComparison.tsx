import {Result,isPriorityResult} from '../types/domain';import {number,percent} from '../utils/format';
export function WaitComparison({result:r}:{result:Result}){
  if(isPriorityResult(r)){
    return <div className="wait-comparison priority">
      <div><span>解析值</span><b className="na">不适用</b><small>{r.analytical_note.slice(0,26)}…</small></div>
      <div><span>有限顾客仿真均值 / 分钟</span><b>{number(r.wait_interval.mean)}</b><small>重复均值{Math.round(r.wait_interval.confidence*100)}% t区间 [{number(r.wait_interval.lower)}, {number(r.wait_interval.upper)}]</small></div>
    </div>;
  }
  return <div className="wait-comparison"><div><span>稳态解析 Wq / 分钟</span><b>{number(r.analytical.mean_wait_minutes)}</b><small>等待概率 {percent(r.analytical.wait_probability)}</small></div><div><span>有限顾客仿真均值 / 分钟</span><b>{number(r.wait_interval.mean)}</b><small>重复均值{Math.round(r.wait_interval.confidence*100)}% t区间 [{number(r.wait_interval.lower)}, {number(r.wait_interval.upper)}]</small></div></div>;}
