USE AeroMRO_EDQSG;
GO
DROP TABLE IF EXISTS aero.part_master_copy;
SELECT * INTO aero.part_master_copy FROM aero.part_master;
CREATE INDEX IX_part_master_copy_part_number ON aero.part_master_copy(part_number);
INSERT dq.benchmark_defect_label(scenario_id,defect_domain,indicator_id,defect_type,target_table,target_column,target_key,severity,causal_parent_scenario_id,expected_effect,random_seed)
VALUES(N'SG6-DUPLICATE-PART-TABLE','SCHEMA','SG6',N'功能与内容重复表',N'aero.part_master_copy',NULL,NULL,0.85,NULL,N'降低表冗余控制；独立更新后将诱发DQ5冲突',20260724);
GO
