import json
from src.config.database import Base,engine,SessionLocal
from src.models import User,QueueStudy,ArrivalProfile,ServiceScenario,SimulationRun,CapacityNote
from src.models import TicketClassConfig,ServiceWindow
from src.utils.security import hash_password
from src.services.run_service import create_snapshot
from src.services.comparison_service import calculate_run

def seed():
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        for role,name in [("admin","陆潮 · 运营研究负责人"),("analyst","季遥 · 排队分析员"),("viewer","沈帆 · 窗口观察员")]:
            email=role+"@zhanqiao.demo"
            if not db.query(User).filter_by(email=email).first():db.add(User(email=email,name=name,role=role,password_hash=hash_password("Zhanqiao2026!")))
        studies=[]
        for code,name in [('Q-01','东栈桥 · 船舶票证窗口'),('Q-02','西栈桥 · 靠泊资料窗口')]:
            study=db.query(QueueStudy).filter_by(code=code).first()
            if not study:study=QueueStudy(code=code,name=name,description="匿名票证请求的容量研究，固定Poisson到达与指数服务假设，不用于实时人员调度。",source="pier-window-parameters-202611.json");db.add(study);db.flush()
            studies.append(study)
        profiles=[]
        for i,(code,name,rate) in enumerate([('AP-AM','上午常态',.45),('AP-PM','午后集中',.7),('AP-PEAK','靠泊集中时段',1.05)]):
            profile=db.query(ArrivalProfile).filter_by(code=code).first()
            if not profile:profile=ArrivalProfile(code=code,name=name,study_id=studies[0 if i<2 else 1].id,arrival_rate=rate,description="每分钟请求数lambda；仅作恒定到达率的模拟配置，不是真实预测。");db.add(profile);db.flush()
            profiles.append(profile)
        scenarios=[]
        for i,profile in enumerate(profiles):
            for servers in [2,3]:
                code=f"SC-{i+1}-{servers}";scenario=db.query(ServiceScenario).filter_by(code=code).first()
                if not scenario:scenario=ServiceScenario(code=code,name=f"{profile.name} · {servers}台服务",profile_id=profile.id,servers=servers,mean_service_minutes=2.5 if i==0 else 1/.45,owner="季遥 · 排队分析员",mode="fcfs");db.add(scenario);db.flush()
                scenarios.append(scenario)
        # 多票种抢占优先级演示情景：普通票/急件混流，通办窗与专办窗混用。
        pcode="SC-PRIORITY-1";priority_scenario=db.query(ServiceScenario).filter_by(code=pcode).first()
        if not priority_scenario:
            base=profiles[0]
            priority_scenario=ServiceScenario(code=pcode,name="通办专办混用 · 急件抢占试验",profile_id=base.id,servers=3,mean_service_minutes=4.0,owner="季遥 · 排队分析员",mode="priority",total_arrival_rate=.6);db.add(priority_scenario);db.flush()
            for c in [
                {"code":"URG","name":"紧急票","level":"urgent","arrival_share":.25,"mean_service_minutes":3.0},
                {"code":"STD","name":"普通标准票","level":"normal","arrival_share":.55,"mean_service_minutes":4.0},
                {"code":"SPEC","name":"专办普通票","level":"normal","arrival_share":.20,"mean_service_minutes":5.0},
            ]:
                db.add(TicketClassConfig(scenario_id=priority_scenario.id,**c))
            for w in [
                {"code":"W-ALL","name":"一号通办窗","allowed":["URG","STD","SPEC"]},
                {"code":"W-MIX","name":"二号通办窗","allowed":["URG","STD"]},
                {"code":"W-SPEC","name":"三号专办窗","allowed":["SPEC"]},
            ]:
                db.add(ServiceWindow(scenario_id=priority_scenario.id,code=w["code"],name=w["name"],allowed=w["allowed"]))
            scenarios.append(priority_scenario)
        if not db.query(SimulationRun).filter_by(name="上午双窗口 · 基准独立重复").first():
            scenario=scenarios[0];snapshot=create_snapshot(db,scenario);result=calculate_run(db,snapshot,3000,500,20,2026,.95)
            run=SimulationRun(name="上午双窗口 · 基准独立重复",scenario_id=scenario.id,customers=3000,warmup=500,replications=20,seed=2026,confidence=.95,input_snapshot=snapshot,status="completed",result=result,owner="季遥 · 排队分析员");db.add(run);db.flush()
            db.add(CapacityNote(run_id=run.id,title="上午窗口容量观察底稿",interpretation="已区分稳态解析和有限顾客仿真，暖机与t区间仅描述模拟均值误差。",proposal="保留到达/服务假设，追加高负荷参数试验后再讨论现场窗口配置。",status="approved",owner="季遥 · 排队分析员",reviewer="陆潮 · 运营研究负责人",review_note="批准容量研究归档；不作为现场等待承诺或自动排班指令。"))
        # 多票种基准运行（较小规模，保证演示环境快速完成）。
        if not db.query(SimulationRun).filter_by(name="急件挤占 · 多票种基准重复").first():
            snapshot=create_snapshot(db,priority_scenario)
            result=calculate_run(db,snapshot,1500,300,10,2026,.95)
            run=SimulationRun(name="急件挤占 · 多票种基准重复",scenario_id=priority_scenario.id,customers=1500,warmup=300,replications=10,seed=2026,confidence=.95,input_snapshot=snapshot,status="completed",result=result,owner="季遥 · 排队分析员");db.add(run);db.flush()
            db.add(CapacityNote(run_id=run.id,title="急件抢占普通票观察底稿",interpretation="多票种混流含抢占续办，无适用单一解析值；按票种核对累计等待、抢占次数与服务量守恒。",proposal="调整急件占比与窗口可办票种后重复试验，观察普通票等待对抢占的敏感度。",status="approved",owner="季遥 · 排队分析员",reviewer="陆潮 · 运营研究负责人",review_note="批准多票种研究归档；服务量守恒核对通过，不作为现场等待承诺。"))
        db.commit();print(json.dumps({m.__tablename__:db.query(m).count() for m in [User,QueueStudy,ArrivalProfile,ServiceScenario,TicketClassConfig,ServiceWindow,SimulationRun,CapacityNote]},ensure_ascii=False))
if __name__=="__main__":seed()
