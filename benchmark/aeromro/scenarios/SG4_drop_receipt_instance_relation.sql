USE AeroMRO_EDQSG;
GO
IF EXISTS(SELECT 1 FROM sys.foreign_keys WHERE parent_object_id=OBJECT_ID(N'aero.receipt_line') AND name=N'FK_receipt_line_instance')
    ALTER TABLE aero.receipt_line DROP CONSTRAINT FK_receipt_line_instance;
INSERT dq.benchmark_defect_label(scenario_id,defect_domain,indicator_id,defect_type,target_table,target_column,target_key,severity,causal_parent_scenario_id,expected_effect,random_seed)
VALUES(N'SG4-DROP-RECEIPT-INSTANCE-REL','SCHEMA','SG4',N'业务链关系缺失',N'aero.receipt_line',N'part_instance_id',NULL,0.9,NULL,N'降低关系清晰性和收货追溯能力',20260724);
GO
