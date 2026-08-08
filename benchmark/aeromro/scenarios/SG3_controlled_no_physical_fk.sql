USE AeroMRO_EDQSG;
GO
/* 受控例外：删除物理外键，但保留实时应用校验、小时级审计、审批和性能证据。 */
IF EXISTS(
    SELECT 1 FROM sys.foreign_keys
    WHERE parent_object_id=OBJECT_ID(N'aero.inventory_transaction') AND name=N'FK_tx_part'
)
    ALTER TABLE aero.inventory_transaction DROP CONSTRAINT FK_tx_part;

UPDATE dq.relationship_control_registry
SET enforcement_modes=N'application_validation,scheduled_audit',
    control_coverage=0.99,
    control_reliability=0.98,
    operating_effectiveness=0.99,
    exception_approved=1,
    exception_reason=N'高并发库存事务写入经压力测试后不启用物理外键，写入前实时校验并按小时全量审计',
    performance_evidence_id=N'PERF-TX-PART-2026-001',
    owner_name=N'航材库存系统组',
    review_due_date='2027-01-31',
    minimum_control_score=0.75
WHERE relationship_id=N'REL-TX-PART';

INSERT dq.benchmark_defect_label(
    scenario_id,defect_domain,indicator_id,defect_type,target_table,target_column,
    target_key,severity,causal_parent_scenario_id,expected_effect,random_seed
)
VALUES(
    N'SG3-CONTROLLED-NO-FK',N'SCHEMA',N'SG3',N'无物理外键受控例外',
    N'aero.inventory_transaction',N'part_id',NULL,0.0,NULL,
    N'不应仅因物理外键缺失触发低分或底线；应依据替代控制、审批证据和孤儿率评价',20260725
);
GO
