/* Run only after scenarios/SG3_uncontrolled_no_physical_fk.sql. */
USE AeroMRO_EDQSG;
GO
DECLARE @tx bigint=(SELECT MIN(inventory_transaction_id) FROM aero.inventory_transaction);
UPDATE aero.inventory_transaction SET part_id=999999999 WHERE inventory_transaction_id=@tx;
INSERT dq.benchmark_defect_label(scenario_id,defect_domain,indicator_id,defect_type,target_table,target_column,target_key,severity,causal_parent_scenario_id,expected_effect,random_seed)
VALUES(N'P-SG3-DQ6-ORPHAN-PART','COUPLING','DQ6',N'结构诱发孤儿器材引用',N'aero.inventory_transaction',N'part_id',CONVERT(nvarchar(100),@tx),1.0,N'SG3-UNCONTROLLED-NO-FK',N'验证关键关系缺少有效替代控制时会传播为DQ6孤儿记录；检测仍依据预期关系执行',20260724);
GO
