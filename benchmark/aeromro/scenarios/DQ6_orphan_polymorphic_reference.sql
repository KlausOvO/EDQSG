USE AeroMRO_EDQSG;
GO
DECLARE @RatePct decimal(5,2)=5.00, @Seed int=20260724, @Scenario nvarchar(80)=N'DQ6-ORPHAN-REFERENCE';
DROP TABLE IF EXISTS #targets;
SELECT inventory_transaction_id INTO #targets FROM aero.inventory_transaction
WHERE reference_type='RECEIPT'
  AND ABS(CONVERT(bigint,CHECKSUM(CONCAT(inventory_transaction_id,N':',@Seed)))) % 10000 < @RatePct*100;
UPDATE x SET reference_id=900000000+x.inventory_transaction_id
FROM aero.inventory_transaction x JOIN #targets t ON t.inventory_transaction_id=x.inventory_transaction_id;
INSERT dq.benchmark_defect_label(scenario_id,defect_domain,indicator_id,defect_type,target_table,target_column,target_key,severity,causal_parent_scenario_id,expected_effect,random_seed)
SELECT @Scenario,'DATA','DQ6',N'逻辑孤儿记录',N'aero.inventory_transaction',N'reference_id',CONVERT(nvarchar(100),inventory_transaction_id),@RatePct/100,NULL,N'物理外键无法覆盖多态单据关系；逻辑外键规则应发现',@Seed FROM #targets;
GO
