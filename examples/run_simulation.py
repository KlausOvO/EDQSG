"""随机模拟仅用于程序验证。"""

import json

from edqsg import EDQSGModel
from edqsg.simulation import SimulationFactory

factory = SimulationFactory(seed=123)
model = EDQSGModel()
report = model.evaluate(
    indicators=factory.indicators(),
    dq_weights=factory.equal_weights("DQ"),
    sg_weights=factory.equal_weights("SG"),
    coupling_calibrations=factory.coupling_calibrations(),
    governance_templates=factory.governance_templates(),
)
print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
