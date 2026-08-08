USE AeroMRO_EDQSG;
GO
DECLARE @RatePct decimal(5,2)=20.00, @Seed int=20260724, @Scenario nvarchar(80)=N'DQ3-INVALID-COUNTRY';
DROP TABLE IF EXISTS #targets;
SELECT manufacturer_id INTO #targets FROM aero.manufacturer
WHERE ABS(CONVERT(bigint,CHECKSUM(CONCAT(manufacturer_id,N':',@Seed)))) % 10000 < @RatePct*100;
UPDATE m SET country_code='ZZ' FROM aero.manufacturer m JOIN #targets t ON t.manufacturer_id=m.manufacturer_id;
INSERT dq.benchmark_defect_label(scenario_id,defect_domain,indicator_id,defect_type,target_table,target_column,target_key,severity,causal_parent_scenario_id,expected_effect,random_seed)
SELECT @Scenario,'DATA','DQ3',N'非法代码值',N'aero.manufacturer',N'country_code',CONVERT(nvarchar(100),manufacturer_id),@RatePct/100,NULL,N'降低规范性和值域符合率',@Seed FROM #targets;
GO
