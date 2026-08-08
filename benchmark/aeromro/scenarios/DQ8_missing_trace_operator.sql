USE AeroMRO_EDQSG;
GO
DECLARE @RatePct decimal(5,2)=5.00, @Seed int=20260724, @Scenario nvarchar(80)=N'DQ8-MISSING-OPERATOR';
DROP TABLE IF EXISTS #targets;
SELECT inventory_transaction_id INTO #targets FROM aero.inventory_transaction
WHERE ABS(CONVERT(bigint,CHECKSUM(CONCAT(inventory_transaction_id,N':',@Seed)))) % 10000 < @RatePct*100;
UPDATE x SET operator_id=NULL FROM aero.inventory_transaction x JOIN #targets t ON t.inventory_transaction_id=x.inventory_transaction_id;
INSERT dq.benchmark_defect_label(scenario_id,defect_domain,indicator_id,defect_type,target_table,target_column,target_key,severity,causal_parent_scenario_id,expected_effect,random_seed)
SELECT @Scenario,'DATA','DQ8',N'操作责任人缺失',N'aero.inventory_transaction',N'operator_id',CONVERT(nvarchar(100),inventory_transaction_id),@RatePct/100,NULL,N'降低业务链可追溯性',@Seed FROM #targets;
GO
