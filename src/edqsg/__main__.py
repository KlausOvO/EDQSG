"""命令行模拟演示入口。"""

import json

from .core import EDQSGModel
from .simulation import SimulationFactory


def main() -> None:
    factory = SimulationFactory(seed=123)
    model = EDQSGModel()
    report = model.evaluate(
        indicators=factory.indicators(),
        dq_weights=factory.equal_weights("DQ"),
        sg_weights=factory.equal_weights("SG"),
        coupling_calibrations=factory.coupling_calibrations(),
        governance_templates=factory.governance_templates(),
        metadata={"scenario": "simulation_only"},
    )
    print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
