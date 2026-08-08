USE AeroMRO_EDQSG;
GO
ALTER TABLE aero.warehouse DROP CONSTRAINT DF_warehouse_updated;
ALTER TABLE aero.warehouse DROP CONSTRAINT DF_warehouse_updater;
ALTER TABLE aero.warehouse DROP COLUMN updated_at,updated_by;
INSERT dq.benchmark_defect_label(scenario_id,defect_domain,indicator_id,defect_type,target_table,target_column,target_key,severity,causal_parent_scenario_id,expected_effect,random_seed)
VALUES(N'SG8-REMOVE-AUDIT','SCHEMA','SG8',N'生命周期审计字段缺失',N'aero.warehouse',N'updated_at,updated_by',NULL,0.8,NULL,N'降低生命周期控制与可追溯准备度',20260724);
GO
