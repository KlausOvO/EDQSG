USE AeroMRO_EDQSG;
GO
IF COL_LENGTH(N'aero.part_master',N'applicable_type_codes') IS NULL
    ALTER TABLE aero.part_master ADD applicable_type_codes nvarchar(1000) NULL;
GO
UPDATE p SET applicable_type_codes=x.codes
FROM aero.part_master p
CROSS APPLY (SELECT STRING_AGG(t.type_code,N',') AS codes FROM aero.part_applicability a JOIN aero.aircraft_type t ON t.aircraft_type_id=a.aircraft_type_id WHERE a.part_id=p.part_id) x;
INSERT dq.benchmark_defect_label(scenario_id,defect_domain,indicator_id,defect_type,target_table,target_column,target_key,severity,causal_parent_scenario_id,expected_effect,random_seed)
VALUES(N'SG2-MULTIVALUE-APPLICABILITY','SCHEMA','SG2',N'多值字段与重复事实',N'aero.part_master',N'applicable_type_codes',NULL,0.75,NULL,N'降低表模型合理性；后续修改将诱发适用关系不一致',20260724);
GO
