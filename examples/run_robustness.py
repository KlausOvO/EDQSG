"""蒙特卡洛稳健性分析示例。"""

import json
from dataclasses import asdict

from edqsg import EDQSGModel
from edqsg.simulation import SimulationFactory

factory = SimulationFactory(seed=123)
model = EDQSGModel()
indicators = factory.indicators()
calibrated = model.coupling_calibrator.calibrate_many(factory.coupling_calibrations())
result = model.robustness(
    indicators=indicators,
    dq_weights=factory.equal_weights("DQ"),
    sg_weights=factory.equal_weights("SG"),
    coupling_relations=calibrated,
    governance_templates=factory.governance_templates(),
    iterations=100,
    perturbation=0.10,
    seed=2026,
)
print(json.dumps(asdict(result), ensure_ascii=False, indent=2))
