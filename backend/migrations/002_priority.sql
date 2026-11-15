-- 002：多票种抢占优先级情景的增量结构。
-- 新库由 SQLAlchemy metadata 直接建表；已部署库按本文件做幂等升级（PostgreSQL 16）。

ALTER TABLE service_scenarios
    ADD COLUMN IF NOT EXISTS mode TEXT NOT NULL DEFAULT 'fcfs';
ALTER TABLE service_scenarios
    ADD COLUMN IF NOT EXISTS total_arrival_rate DOUBLE PRECISION NULL;

CREATE TABLE IF NOT EXISTS ticket_class_configs (
    id BIGSERIAL PRIMARY KEY,
    scenario_id BIGINT NOT NULL REFERENCES service_scenarios (id),
    code TEXT NOT NULL,
    name TEXT NOT NULL,
    level TEXT NOT NULL,
    arrival_share DOUBLE PRECISION NOT NULL,
    mean_service_minutes DOUBLE PRECISION NOT NULL
);

CREATE TABLE IF NOT EXISTS service_windows (
    id BIGSERIAL PRIMARY KEY,
    scenario_id BIGINT NOT NULL REFERENCES service_scenarios (id),
    code TEXT NOT NULL,
    name TEXT NOT NULL,
    allowed JSONB NOT NULL
);

CREATE INDEX IF NOT EXISTS ticket_class_scenario_idx ON ticket_class_configs (scenario_id);
CREATE INDEX IF NOT EXISTS service_window_scenario_idx ON service_windows (scenario_id);
