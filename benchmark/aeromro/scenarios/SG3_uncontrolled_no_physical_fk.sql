USE AeroMRO_EDQSG;
GO
/* 非受控缺口：删除物理外键，仅保留文档约定，不存在有效替代控制。 */
IF EXISTS(
    SELECT 1 FROM sys.foreign_keys
    WHERE parent_object_id=OBJECT_ID(N'aero.inventory_transaction') AND name=N'FK_tx_part'
)
    ALTER TABLE aero.inventory_transaction DROP CONSTRAINT FK_tx_part;

UPDATE dq.relationship_control_registry
SET enforcement_modes=N'documentation_only',
    control_coverage=0.50,
    control_reliability=0.50,
    operating_effectiveness=0.50,
    exception_approved=0,
    exception_reason=NULL,
    performance_evidence_id=NULL,
    review_due_date=NULL,
    minimum_control_score=0.75
WHERE relationship_id=N'REL-TX-PART';

INSERT dq.benchmark_defect_label(
    scenario_id,defect_domain,indicator_id,defect_type,target_table,target_column,
    target_key,severity,causal_parent_scenario_id,expected_effect,random_seed
)
VALUES(
    N'SG3-UNCONTROLLED-NO-FK',N'SCHEMA',N'SG3',N'关系完整性控制不足',
    N'aero.inventory_transaction',N'part_id',NULL,1.0,NULL,
    N'SG3关系控制有效度应显著下降并触发关键关系底线，根因不表述为单纯缺少外键',20260725
);
GO
