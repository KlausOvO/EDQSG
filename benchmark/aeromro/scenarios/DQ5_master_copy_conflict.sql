USE AeroMRO_EDQSG;
GO
DECLARE @RatePct decimal(5,2)=5.00, @Seed int=20260724, @Scenario nvarchar(80)=N'DQ5-MASTER-CONFLICT';
DROP TABLE IF EXISTS #targets;
SELECT inventory_transaction_id INTO #targets FROM aero.inventory_transaction
WHERE ABS(CONVERT(bigint,CHECKSUM(CONCAT(inventory_transaction_id,N':',@Seed)))) % 10000 < @RatePct*100;
UPDATE x SET part_number_snapshot=CONCAT(N'OLD-',x.part_number_snapshot)
FROM aero.inventory_transaction x JOIN #targets t ON t.inventory_transaction_id=x.inventory_transaction_id;
INSERT dq.benchmark_defect_label(scenario_id,defect_domain,indicator_id,defect_type,target_table,target_column,target_key,severity,causal_parent_scenario_id,expected_effect,random_seed)
SELECT @Scenario,'DATA','DQ5',N'跨表主数据不一致',N'aero.inventory_transaction',N'part_number_snapshot',CONVERT(nvarchar(100),inventory_transaction_id),@RatePct/100,NULL,N'降低一致性并增加主数据权威风险',@Seed FROM #targets;
GO
