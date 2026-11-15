import {TicketClass,WindowConfig,TicketLevel} from '../types/domain';

interface Props{
  classes:TicketClass[];
  windows:WindowConfig[];
  totalRate:number;
  onClasses:(v:TicketClass[])=>void;
  onWindows:(v:WindowConfig[])=>void;
  onTotalRate:(v:number)=>void;
  readOnly?:boolean;
}

export function PriorityConfig({classes,windows,totalRate,onClasses,onWindows,onTotalRate,readOnly}:Props){
  const shareSum=classes.reduce((a,c)=>a+(Number(c.arrival_share)||0),0);
  const shareOk=Math.abs(shareSum-1)<1e-6;
  function patchClass(i:number,patch:Partial<TicketClass>){
    onClasses(classes.map((c,j)=>j===i?{...c,...patch}:c));
  }
  function addClass(){
    onClasses([...classes,{code:`T${classes.length+1}`,name:'',level:'normal',arrival_share:0,mean_service_minutes:3}]);
  }
  function removeClass(i:number){onClasses(classes.filter((_,j)=>j!==i));}
  function toggleAllowed(wi:number,code:string){
    onWindows(windows.map((w,j)=>{
      if(j!==wi)return w;
      const has=w.allowed.includes(code);
      return {...w,allowed:has?w.allowed.filter(x=>x!==code):[...w.allowed,code]};
    }));
  }
  function patchWindow(i:number,patch:Partial<WindowConfig>){onWindows(windows.map((w,j)=>j===i?{...w,...patch}:w));}
  function addWindow(){onWindows([...windows,{code:`W${windows.length+1}`,name:'',allowed:classes.map(c=>c.code)}]);}
  function removeWindow(i:number){onWindows(windows.filter((_,j)=>j!==i));}
  const classCodes=classes.map(c=>c.code);
  const everyTicketServed=classCodes.every(code=>windows.some(w=>w.allowed.includes(code)));
  const weightedMean=classes.reduce((a,c)=>a+(Number(c.arrival_share)||0)*(Number(c.mean_service_minutes)||0),0);
  const offeredLoad=totalRate*weightedMean;
  const capacity=windows.length;
  return (
    <div className="priority-config">
      <div className="form-heading"><span>01b</span><h2>多票种与窗口配置</h2></div>
      <label>总到达率 λ（请求/分钟，混合泊松）
        <input aria-label="总到达率" type="number" min="0.000001" max="1000" step="0.01" value={totalRate}
          onChange={e=>onTotalRate(Number(e.target.value))} disabled={readOnly}/>
      </label>

      <div className="config-block">
        <div className="config-block-head"><h3>票种（到达占比 / 服务时长 / 等级）</h3>
          {!readOnly&&<button type="button" className="text-link" onClick={addClass}>+ 新增票种</button>}
        </div>
        <div className="ticket-rows">
          <div className="ticket-row ticket-row-head"><span>票种 code</span><span>名称</span><span>等级</span><span>到达占比</span><span>平均服务 min</span><span></span></div>
          {classes.map((c,i)=>(
            <div className="ticket-row" key={i}>
              <input aria-label={`票种code ${i}`} value={c.code} onChange={e=>patchClass(i,{code:e.target.value})} disabled={readOnly}/>
              <input aria-label={`票种名称 ${i}`} value={c.name??''} placeholder="名称" onChange={e=>patchClass(i,{name:e.target.value})} disabled={readOnly}/>
              <select aria-label={`票种等级 ${i}`} value={c.level} onChange={e=>patchClass(i,{level:e.target.value as TicketLevel})} disabled={readOnly}>
                <option value="normal">普通 normal</option>
                <option value="urgent">紧急 urgent</option>
              </select>
              <input aria-label={`到达占比 ${i}`} type="number" min="0" max="1" step="0.05" value={c.arrival_share}
                onChange={e=>patchClass(i,{arrival_share:Number(e.target.value)})} disabled={readOnly}/>
              <input aria-label={`平均服务 ${i}`} type="number" min="0.001" max="120" step="0.1" value={c.mean_service_minutes}
                onChange={e=>patchClass(i,{mean_service_minutes:Number(e.target.value)})} disabled={readOnly}/>
              {!readOnly&&<button type="button" className="text-link danger" onClick={()=>removeClass(i)}>删除</button>}
            </div>
          ))}
        </div>
        <p className={'caption '+(shareOk?'':'warning-text')}>占比合计 {shareSum.toFixed(4)}（须等于 1.0000）{shareOk?' ✓':' ✗'}</p>
      </div>

      <div className="config-block">
        <div className="config-block-head"><h3>窗口与可办票种</h3>
          {!readOnly&&<button type="button" className="text-link" onClick={addWindow}>+ 新增窗口</button>}
        </div>
        <div className="window-rows">
          <div className="window-row window-row-head"><span>窗口 code</span><span>名称</span><span>可办票种（勾选）</span><span></span></div>
          {windows.map((w,i)=>(
            <div className="window-row" key={i}>
              <input aria-label={`窗口code ${i}`} value={w.code} onChange={e=>patchWindow(i,{code:e.target.value})} disabled={readOnly}/>
              <input aria-label={`窗口名称 ${i}`} value={w.name??''} placeholder="名称" onChange={e=>patchWindow(i,{name:e.target.value})} disabled={readOnly}/>
              <div className="allowed-toggles">
                {classCodes.map(code=>(
                  <label key={code} className={'toggle '+(w.allowed.includes(code)?'on':'off')}>
                    <input type="checkbox" checked={w.allowed.includes(code)} onChange={()=>toggleAllowed(i,code)} disabled={readOnly}/>
                    {code}
                  </label>
                ))}
              </div>
              {!readOnly&&<button type="button" className="text-link danger" onClick={()=>removeWindow(i)}>删除</button>}
            </div>
          ))}
        </div>
        <p className={'caption '+(everyTicketServed?'':'warning-text')}>
          {everyTicketServed?'每个票种至少有一个可办窗口 ✓':'存在无可办窗口的票种 ✗'}
        </p>
      </div>

      <div className={'load-guard '+(offeredLoad<capacity?'':'warning')}>
        <span>加权平均服务 {weightedMean.toFixed(3)} min · 总负荷 {offeredLoad.toFixed(3)} / 窗口能力 {capacity}</span>
        <b>{offeredLoad<capacity?'负荷低于能力，可运行':'总负荷 ≥ 窗口能力，队列无稳态将被拒绝'}</b>
      </div>
      <p className="caption">规则：空窗先使急件开工最多、再使总开工最多，同级先到先办；急件可抢占普通票，被中断票保留剩余服务量并可换兼容窗口续办；同刻完成先于到达。</p>
    </div>
  );
}
