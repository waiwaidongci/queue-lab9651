import {FormEvent,useState} from 'react';
import {useNavigate} from 'react-router-dom';
import {ArrowRight} from 'lucide-react';
import {useResearchData} from '../hooks/useResearch';
import {useAuth} from '../stores/auth';
import {useAction} from '../hooks/useAction';
import {createScenario,ScenarioPayload} from '../api/scenarios';
import {createRun} from '../api/runs';
import {ProfileSelector} from '../components/ProfileSelector';
import {PriorityConfig} from '../components/PriorityConfig';
import {Notice} from '../components/common/Notice';
import {number,percent} from '../utils/format';
import {TicketClass,WindowConfig} from '../types/domain';

export function Configure(){
  const s=useResearchData(),{user}=useAuth(),a=useAction(),navigate=useNavigate();
  const [pid,setPid]=useState(0),[scenarioName,setScenarioName]=useState('');
  const [servers,setServers]=useState(2),[service,setService]=useState(2.5);
  const [mode,setMode]=useState<'fcfs'|'priority'>('fcfs');
  const [totalRate,setTotalRate]=useState(0.6);
  const [ticketClasses,setTicketClasses]=useState<TicketClass[]>([
    {code:'URG',name:'紧急票',level:'urgent',arrival_share:0.25,mean_service_minutes:3},
    {code:'STD',name:'普通票',level:'normal',arrival_share:0.75,mean_service_minutes:4},
  ]);
  const [windowConfigs,setWindowConfigs]=useState<WindowConfig[]>([
    {code:'W1',name:'通办窗',allowed:['URG','STD']},{code:'W2',name:'专办窗',allowed:['STD']},
  ]);
  const [sid,setSid]=useState(0),[name,setName]=useState(''),[customers,setCustomers]=useState(3000),
    [warmup,setWarmup]=useState(500),[replications,setReplications]=useState(20),[seed,setSeed]=useState(2026);
  const profile=s.profiles.find(p=>p.id===pid)||s.profiles[0];
  const scenarios=s.scenarios.filter(x=>x.profile_id===profile?.id);
  const scenario=scenarios.find(x=>x.id===sid)||scenarios[0];
  const readOnly=user?.role==='viewer';

  function syncWindowsCount(nextServers:number){
    setServers(nextServers);
    setWindowConfigs(prev=>{
      if(nextServers<=prev.length)return prev.slice(0,nextServers);
      const codes=ticketClasses.map(c=>c.code);
      const extra=Array.from({length:nextServers-prev.length},(_,k)=>(
        {code:`W${prev.length+k+1}`,name:'',allowed:[...codes]}));
      return [...prev,...extra];
    });
  }

  function create(e:FormEvent){
    e.preventDefault();
    a.execute(async()=>{
      const payload:ScenarioPayload={name:scenarioName,profile_id:profile!.id,servers,mean_service_minutes:service,mode};
      if(mode==='priority'){
        payload.total_arrival_rate=totalRate;
        payload.ticket_classes=ticketClasses;
        payload.windows=windowConfigs;
      }
      const x=await createScenario(payload);
      setSid(x.id);setScenarioName('');await s.refresh();
    });
  }

  function run(e:FormEvent){
    e.preventDefault();
    a.execute(async()=>{
      const r=await createRun({name,scenario_id:scenario!.id,customers,warmup,replications,seed,confidence:.95});
      navigate('/results?run='+r.id);
    });
  }

  const priorityLoad=mode==='priority'?totalRate*ticketClasses.reduce((v,c)=>v+(Number(c.arrival_share)||0)*(Number(c.mean_service_minutes)||0),0):0;
  const canSubmitPriority=mode==='fcfs'||(Math.abs(ticketClasses.reduce((v,c)=>v+(Number(c.arrival_share)||0),0)-1)<1e-6
    &&ticketClasses.length>=2&&windowConfigs.length===servers
    &&ticketClasses.every(c=>c.code&&windowConfigs.some(w=>w.allowed.includes(c.code)))
    &&windowConfigs.every(w=>w.code&&w.allowed.length>0)&&priorityLoad<servers);

  return <div className="page"><div className="page-title"><div><p className="eyebrow">SCENARIO & EXECUTION / 03</p><h1>情景与运行<span>冻结参数，再进行独立重复试验。</span></h1></div></div>
    <Notice message={s.error||a.error} retry={s.refresh}/>
    <div className="editor-grid">
      <section>
        <ProfileSelector profiles={s.profiles} value={profile?.id||0} onChange={id=>{setPid(id);setSid(0)}}/>
        <form onSubmit={create}>
          <div className="form-heading"><span>01</span><h2>建立服务情景</h2></div>
          <label>情景名称<input aria-label="情景名称" value={scenarioName} onChange={e=>setScenarioName(e.target.value)} minLength={2} required placeholder="例如：上午双窗口复核" disabled={readOnly}/></label>
          <div className="mode-switch">
            <button type="button" className={mode==='fcfs'?'mode-btn active':'mode-btn'} onClick={()=>setMode('fcfs')} disabled={readOnly}>旧单队列 FCFS（M/M/c）</button>
            <button type="button" className={mode==='priority'?'mode-btn active':'mode-btn'} onClick={()=>setMode('priority')} disabled={readOnly}>多票种抢占优先级</button>
          </div>
          {mode==='fcfs'?<div className="form-row">
            <label>服务台数量<input aria-label="服务台数量" type="number" min="1" max="20" value={servers} onChange={e=>setServers(Number(e.target.value))}/></label>
            <label>单台平均服务 / 分钟每人<input aria-label="平均服务分钟" type="number" min="0.01" max="120" step="0.01" value={service} onChange={e=>setService(Number(e.target.value))}/></label>
          </div>:
          <div className="form-row">
            <label>窗口数量（=服务台 c）<input aria-label="窗口数量" type="number" min="1" max="20" value={servers} onChange={e=>syncWindowsCount(Number(e.target.value))}/></label>
            <label>占位平均服务（兼容旧字段，分钟）<input aria-label="占位平均服务" type="number" min="0.01" max="120" step="0.01" value={service} onChange={e=>setService(Number(e.target.value))}/></label>
          </div>}
          {mode==='priority'&&<PriorityConfig classes={ticketClasses} windows={windowConfigs} totalRate={totalRate}
            onClasses={setTicketClasses} onWindows={setWindowConfigs} onTotalRate={setTotalRate} readOnly={readOnly}/>}
          {readOnly?<p className="role-note">观察员可以查看参数，建立情景与仿真需要分析员权限。</p>:
            <button className="outline" disabled={a.busy||!canSubmitPriority}>保存服务情景</button>}
        </form>

        <form className="run-form" onSubmit={run}>
          <div className="form-heading"><span>02</span><h2>独立重复仿真</h2></div>
          <label>使用服务情景<select aria-label="使用服务情景" value={scenario?.id||''} onChange={e=>setSid(Number(e.target.value))}>
            {scenarios.map(x=><option key={x.id} value={x.id}>{x.name} / {x.servers}窗 / {x.mode==='priority'?'多票种抢占':(x.stable?'稳态可研究':'无稳态')}</option>)}
          </select></label>
          {scenario&&(scenario.mode==='priority'
            ?<div className="scenario-preview"><span>λ {number(scenario.effective_arrival_rate)} / {scenario.ticket_classes.length} 票种 / {scenario.window_configs.length} 窗</span><b>多票种抢占 · 无单一解析值，仅仿真</b></div>
            :<div className={'scenario-preview '+(scenario.stable?'':'warning')}><span>λ {number(scenario.arrival_rate)} / μ {number(scenario.service_rate)} / ρ {percent(scenario.utilization)}</span><b>{scenario.stable?'满足稳态条件':'lambda ≥ c*mu，不可运行'}</b></div>)}
          <label>试验名称<input aria-label="试验名称" value={name} onChange={e=>setName(e.target.value)} minLength={2} required placeholder="例如：上午独立20重复" disabled={readOnly}/></label>
          <div className="form-row">
            <label>每次生成票数<input aria-label="生成票数" type="number" min="500" max="10000" value={customers} onChange={e=>setCustomers(Number(e.target.value))}/></label>
            <label>剔除前warmup张票<input aria-label="暖机票数" type="number" min="0" max="5000" value={warmup} onChange={e=>setWarmup(Number(e.target.value))}/></label>
          </div>
          <div className="form-row">
            <label>独立重复数<input aria-label="独立重复数" type="number" min="5" max="40" value={replications} onChange={e=>setReplications(Number(e.target.value))}/></label>
            <label>根随机种子<input aria-label="随机种子" type="number" min="0" max="2147483647" value={seed} onChange={e=>setSeed(Number(e.target.value))}/></label>
          </div>
          <p className="caption">每次重复独立到达/服务随机流；95% t区间基于重复均值。至少保留100张，总生成票不超过250000。</p>
          {readOnly?<p className="role-note">观察员可以查看参数，建立情景与仿真需要分析员权限。</p>:
            <button className="primary" disabled={a.busy||!scenario||(scenario.mode!=='priority'&&!scenario.stable)}>提交容量试验 <ArrowRight size={16}/></button>}
        </form>
      </section>
      <aside className="method-panel">
        <span className="eyebrow">METHOD SECTION / 01</span>
        {mode==='priority'?<>
          <h2>多票种，<br/>急件可抢占。</h2>
          <ol>
            <li><b>空窗分配目标</b><p>先使急件开工数最多，再使总开工数最多；同级先到先办。</p></li>
            <li><b>抢占与续办</b><p>急件可抢占普通票窗口；被中断票保留剩余服务量，可换兼容窗口续办，每次中断计一次抢占。</p></li>
            <li><b>同刻次序与解析边界</b><p>同刻完成先于到达；含抢占、异速与受限窗口，无单一 M/M/c 解析值，仅给有限仿真与 t 区间。</p></li>
          </ol>
        </>:<>
          <h2>一条队列，<br/>多台先到先服务。</h2>
          <ol>
            <li><b>Erlang-C是稳态解析</b><p>Poisson到达、指数服务和无限等待空间；λ必须小于cμ。</p></li>
            <li><b>暖机按顾客序剔除</b><p>每次从空系统开始，去掉前warmup位顾客，再统计保留顾客。</p></li>
            <li><b>t区间按独立重复</b><p>同一次队列里的等待有关联，不能把全部顾客当独立样本算区间。</p></li>
          </ol>
        </>}
      </aside>
    </div>
  </div>;
}
