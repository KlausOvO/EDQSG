USE AeroMRO_EDQSG;
GO
DECLARE @RatePct decimal(5,2)=5.00, @Seed int=20260724, @Scenario nvarchar(80)=N'DQ4-DUP-CERT-RECEIVED';
DROP TABLE IF EXISTS #targets;
SELECT receipt_line_id INTO #targets FROM aero.receipt_line
WHERE ABS(CONVERT(bigint,CHECKSUM(CONCAT(receipt_line_id,N':',@Seed)))) % 10000 < @RatePct*100;
UPDATE r SET certificate_no_received=N'DUPLICATE-RECEIVED-CERT' FROM aero.receipt_line r JOIN #targets t ON t.receipt_line_id=r.receipt_line_id;
INSERT dq.benchmark_defect_label(scenario_id,defect_domain,indicator_id,defect_type,target_table,target_column,target_key,severity,causal_parent_scenario_id,expected_effect,random_seed)
SELECT @Scenario,'DATA','DQ4',N'业务标识重复',N'aero.receipt_line',N'certificate_no_received',CONVERT(nvarchar(100),receipt_line_id),@RatePct/100,NULL,N'降低业务唯一性；数据库未设置该业务唯一约束',@Seed FROM #targets;
GO
