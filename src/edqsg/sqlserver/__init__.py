"""EDQSG SQL Server只读自动评价扩展。"""

from .adapter import SQLServerAdapter
from .config import (
    BusinessKeyRule,
    CustomSQLRule,
    DomainRule,
    FreshnessRule,
    LifecycleControlRule,
    LogicalForeignKeyRule,
    RelationshipControlRule,
    MasterDataConsistencyRule,
    MasterDataGroup,
    RequiredColumnRule,
    SupplementalEvidenceRule,
    TableModelRule,
    SQLServerAssessmentConfig,
    SQLServerConnectionConfig,
    SQLServerRuleConfig,
    SQLServerScanConfig,
    SQLServerVisualizationConfig,
)
from .pipeline import SQLServerAssessmentPipeline
from .reporting import SQLServerPipelineResult

__all__ = [
    "SQLServerAdapter",
    "SQLServerAssessmentPipeline",
    "SQLServerPipelineResult",
    "SQLServerAssessmentConfig",
    "SQLServerConnectionConfig",
    "SQLServerScanConfig",
    "SQLServerRuleConfig",
    "SQLServerVisualizationConfig",
    "RequiredColumnRule",
    "BusinessKeyRule",
    "FreshnessRule",
    "DomainRule",
    "CustomSQLRule",
    "LogicalForeignKeyRule",
    "RelationshipControlRule",
    "TableModelRule",
    "MasterDataGroup",
    "MasterDataConsistencyRule",
    "LifecycleControlRule",
    "SupplementalEvidenceRule",
]
