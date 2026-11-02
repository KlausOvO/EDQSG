from datetime import date
import json
from pathlib import Path
from edqsg.csvsource.profiler import _stale_rates,compute_metrics,build_indicators


def test_stale_rate_changes_only_when_reference_date_changes():
    tables={'items':[{'updated_at':'2026-07-01'}]}
    checks=[{'table':'items','column':'updated_at'}]
    assert _stale_rates(tables, checks, 90, reference_date=date(2026,9,21))==[0.0]
    assert _stale_rates(tables, checks, 90, reference_date=date(2026,11,2))==[1.0]

def test_reference_date_at_exact_boundary_is_not_stale():
    assert _stale_rates({'items':[{'updated_at':'2026-07-01'}]},[{'table':'items','column':'updated_at'}],90,date(2026,9,29))==[0.0]

def test_compute_metrics_date_is_explicit():
    config={'dq_rules':{'DQ7':{'checks':[{'table':'items','column':'updated_at'}]}},'stale_max_age_days':90}
    table={'items':[{'updated_at':'2026-07-01'}]}
    assert compute_metrics(config,table,reference_date=date(2026,9,21))['dq.DQ7.rate']==0
    assert compute_metrics(config,table,reference_date=date(2026,11,2))['dq.DQ7.rate']==1

def test_indicators_receive_ref_date_no_implicit_override():
    config={'dq_rules':{'DQ7':{'checks':[{'table':'items','column':'updated_at'}]}},'stale_max_age_days':90,'sg_extra':[{'indicator_id':'SG8','score':90}]}
    inds,metrics=build_indicators(config,{'items':[{'updated_at':'2026-07-01'}]},reference_date=date(2026,9,21))
    assert len(inds)==2 and metrics['dq.DQ7.rate']==0
