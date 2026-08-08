/* Run only after scenarios/SG6_duplicate_part_table.sql. */
USE AeroMRO_EDQSG;
GO
DECLARE @part int=(SELECT MIN(part_id) FROM aero.part_master_copy);
UPDATE aero.part_master_copy SET part_name=N'副本独立修改后的名称' WHERE part_id=@part;
INSERT dq.benchmark_defect_label(scenario_id,defect_domain,indicator_id,defect_type,target_table,target_column,target_key,severity,causal_parent_scenario_id,expected_effect,random_seed)
VALUES(N'P-SG6-DQ5-COPY-CONFLICT','COUPLING','DQ5',N'重复表独立更新冲突',N'aero.part_master_copy',N'part_name',CONVERT(nvarchar(100),@part),0.9,N'SG6-DUPLICATE-PART-TABLE',N'验证SG6表冗余向DQ5一致性问题传播',20260724);
GO
