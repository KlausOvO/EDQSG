USE AeroMRO_EDQSG;
GO
IF EXISTS(SELECT 1 FROM sys.indexes WHERE object_id=OBJECT_ID(N'aero.part_instance') AND name=N'UX_part_instance_serial')
    DROP INDEX UX_part_instance_serial ON aero.part_instance;
INSERT dq.benchmark_defect_label(scenario_id,defect_domain,indicator_id,defect_type,target_table,target_column,target_key,severity,causal_parent_scenario_id,expected_effect,random_seed)
VALUES(N'SG3-DROP-SERIAL-UQ','SCHEMA','SG3',N'关键唯一约束缺失',N'aero.part_instance',N'serial_number',NULL,1.0,NULL,N'降低键与约束完整性；允许重复序列号传播到DQ4',20260724);
GO
