USE AeroMRO_EDQSG;
GO
DECLARE @RatePct decimal(5,2)=10.00, @Seed int=20260724, @Scenario nvarchar(80)=N'DQ7-STALE-PART';
DROP TABLE IF EXISTS #targets;
SELECT part_id INTO #targets FROM aero.part_master
WHERE ABS(CONVERT(bigint,CHECKSUM(CONCAT(part_id,N':',@Seed)))) % 10000 < @RatePct*100;
UPDATE p SET updated_at=DATEADD(day,-900,SYSUTCDATETIME()),updated_by=N'legacy_job'
FROM aero.part_master p JOIN #targets t ON t.part_id=p.part_id;
INSERT dq.benchmark_defect_label(scenario_id,defect_domain,indicator_id,defect_type,target_table,target_column,target_key,severity,causal_parent_scenario_id,expected_effect,random_seed)
SELECT @Scenario,'DATA','DQ7',N'更新超期',N'aero.part_master',N'updated_at',CONVERT(nvarchar(100),part_id),@RatePct/100,NULL,N'降低时效性',@Seed FROM #targets;
GO
