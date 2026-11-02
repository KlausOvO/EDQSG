"""R03-X1-B1 tests. This does not assert real-world validity of risk policy."""
import pytest
from edqsg import EDQSGModel, Evidence, Indicator, Domain, EvidenceType
from edqsg.admission import FormalAdmissionPolicy, CriticalRuleRequirement


def item(name, domain, observability=1, rating=96, certainty=1.0):
    return Indicator(name, name, domain, evidences=(Evidence(
        evidence_id=f'{name}-E', evidence_type=EvidenceType.DATA,
        source='controlled-R03-X1-B1', coverage=certainty,
        authority=certainty,timeliness=certainty,repeatability=certainty,
        business_fit=certainty, sample_coverage=1,
        rule_observability=observability, observed_score=rating,
    ),))


def policy(critical=('DQ1',)):
    return FormalAdmissionPolicy(
        policy_id='TEST-RISK-001', scope='受控测试场景',
        basis='仅用于验证策略机制；不是论文实际业务规则登记',
        critical_rules=(CriticalRuleRequirement('BL-TEST', tuple(critical)),),
    )


def items(dq1_obs, dq3_obs=1.0, sg_obs=1.0):
    return [item('DQ1',Domain.DATA_QUALITY,dq1_obs),
            item('DQ3',Domain.DATA_QUALITY,dq3_obs),
            item('SG3',Domain.STRUCTURAL_GOVERNANCE,sg_obs)]


def run(dq1_obs, pol=None, dq3_obs=1.0, sg_obs=1.0):
    return EDQSGModel().evaluate_formal(
        items(dq1_obs,dq3_obs,sg_obs),
        {'DQ1':.5,'DQ3':.5},{'SG3':1},
        admission_policy=pol or policy(),
    )


def codes(out):
    return {i.code for i in out.issues}


def test_review_but_not_excluded_critical_withheld():
    outcome=run(.6)
    assert not outcome.issued
    assert outcome.report is None
    assert 'CRITICAL_EVIDENCE_INSUFFICIENT' in codes(outcome)
    assert 'DQ1' in outcome.review_indicator_ids
    assert 'DQ1' not in outcome.excluded_indicator_ids


def test_critical_excluded_other_good_withheld():
    out=run(.3)
    assert not out.issued
    assert 'CRITICAL_EVIDENCE_INSUFFICIENT' in codes(out)
    assert 'DQ1' in out.excluded_indicator_ids


def test_no_global_dq1_critical_rule():
    # DQ1 is not automatically critical; explicit scope-specific rules apply.
    out=run(.3,policy(('DQ3',)))
    assert out.issued
    assert out.report is not None
    assert out.report.overall_grade.value=='优'
    assert 'DQ1' in out.excluded_indicator_ids


def test_critical_evidence_sufficient_issues_grade():
    out=run(.9)
    assert out.issued and out.report is not None
    assert out.issues==()


def test_review_boundary_is_rejected():
    out=run(.7)
    assert not out.issued
    assert 'CRITICAL_EVIDENCE_INSUFFICIENT' in codes(out)


def test_only_noncritical_review_does_not_block():
    out=run(.95,policy(('DQ1',)),dq3_obs=.6)
    assert out.issued
    assert 'DQ3' in out.review_indicator_ids


def test_domain_without_participants_withheld():
    out=run(.2,dq3_obs=.2)
    assert not out.issued
    assert 'DQ_DOMAIN_EXCLUDED' in codes(out)


def test_other_domain_without_participants_withheld():
    out=run(.95,sg_obs=.2)
    assert not out.issued
    assert 'SG_DOMAIN_EXCLUDED' in codes(out)


def test_valid_no_relevant_rules_explicit():
    p=FormalAdmissionPolicy('P0','scope','reviewed no risk inventory applicable',
                            no_relevant_critical_rules=True)
    out=run(.3,p)
    assert out.issued


def test_no_policy_implicitly_forbidden():
    with pytest.raises(TypeError): run(.9,pol='not-a-policy')


def test_unspecified_critical_policy_invalid():
    p=FormalAdmissionPolicy('X','scope','basis')
    with pytest.raises(ValueError,match='须登记关键规则'):
        run(.95,p)


def test_wrong_indicator_rejected_before_grade():
    with pytest.raises(ValueError, match='未提交指标'):
        run(.95,policy(('DQ99',)))


def test_duplicate_rule_rejected():
    r=CriticalRuleRequirement('X',('DQ1',))
    p=FormalAdmissionPolicy('X','scope','basis',(r,r))
    with pytest.raises(ValueError,match='关键规则标识重复'):
        run(.95,p)


def test_legacy_evaluate_unchanged():
    model=EDQSGModel()
    # Regression: original model would issue a grade on partial Q coverage.
    report=model.evaluate(items(.3),{'DQ1':.5,'DQ3':.5},{'SG3':1})
    assert report.overall_grade.value=='优'
    assert 'DQ1' in report.excluded_indicator_ids


def test_critical_conflict_withheld():
    # Two opposed, credible assessments should exceed the conflict review threshold.
    e1=Evidence('e1', EvidenceType.DATA, 's1', 1,1,1,1,1,
                belief_degrees=(1,0,0,0,0))
    e2=Evidence('e2', EvidenceType.DATA, 's2', 1,1,1,1,1,
                belief_degrees=(0,0,0,0,1))
    dq1=Indicator('DQ1','DQ1',Domain.DATA_QUALITY,(e1,e2))
    fused=EDQSGModel().evidence_engine.fuse(dq1)
    assert fused.review_state=='conflict'
    other=[item('DQ3',Domain.DATA_QUALITY),item('SG3',Domain.STRUCTURAL_GOVERNANCE)]
    out=EDQSGModel().evaluate_formal([dq1]+other,{'DQ1':.5,'DQ3':.5},{'SG3':1},admission_policy=policy())
    assert not out.issued
    assert 'CRITICAL_EVIDENCE_CONFLICT' in codes(out)


def test_policy_provenance_required():
    p=FormalAdmissionPolicy('X','scope','',(CriticalRuleRequirement('R',('DQ1',)),))
    with pytest.raises(ValueError,match='依据'):
        run(.9,p)
