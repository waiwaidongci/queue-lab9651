-- New databases bootstrap metadata; apply reviewed schema migrations for upgrades.
CREATE INDEX IF NOT EXISTS scenario_profile_idx ON service_scenarios (profile_id);
CREATE INDEX IF NOT EXISTS note_run_status_idx ON capacity_notes (run_id,status);

-- 多票种抢占优先级：票种配置与窗口配置（002 增量）。
CREATE INDEX IF NOT EXISTS ticket_class_scenario_idx ON ticket_class_configs (scenario_id);
CREATE INDEX IF NOT EXISTS service_window_scenario_idx ON service_windows (scenario_id);
