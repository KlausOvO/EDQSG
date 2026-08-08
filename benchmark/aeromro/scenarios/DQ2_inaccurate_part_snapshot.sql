USE AeroMRO_EDQSG;
GO
DECLARE @RatePct decimal(5,2)=5.00, @Seed int=20260724, @Scenario nvarchar(80)=N'DQ2-INACCURATE-SNAPSHOT';
DROP TABLE IF EXISTS #targets;
SELECT inventory_transaction_id INTO #targets FROM aero.inventory_transaction
WHERE ABS(CONVERT(bigint,CHECKSUM(CONCAT(inventory_transaction_id,N':',@Seed)))) % 10000 < @RatePct*100;
UPDATE x SET part_name_snapshot=CONCAT(N'错误名称-',x.inventory_transaction_id)
FROM aero.inventory_transaction x JOIN #targets t ON t.inventory_transaction_id=x.inventory_transaction_id;
INSERT dq.benchmark_defect_label(scenario_id,defect_domain,indicator_id,defect_type,target_table,target_column,target_key,severity,causal_parent_scenario_id,expected_effect,random_seed)
SELECT @Scenario,'DATA','DQ2',N'权威值不匹配',N'aero.inventory_transaction',N'part_name_snapshot',CONVERT(nvarchar(100),inventory_transaction_id),@RatePct/100,NULL,N'降低准确性并形成SG7-DQ2路径证据',@Seed FROM #targets;
GO
