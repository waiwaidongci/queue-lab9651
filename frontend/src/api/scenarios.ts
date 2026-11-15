import {request} from './client';import {Scenario,TicketClass,WindowConfig} from '../types/domain';
export const getScenarios=()=>request<Scenario[]>('/scenarios');
export interface ScenarioPayload{name:string;profile_id:number;servers:number;mean_service_minutes:number;mode?:'fcfs'|'priority';total_arrival_rate?:number|null;ticket_classes?:TicketClass[];windows?:WindowConfig[]}
export const createScenario=(data:ScenarioPayload)=>request<Scenario>('/scenarios',{method:'POST',body:JSON.stringify(data)});
