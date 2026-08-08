"""SQL Server 系统目录元数据采集。

优先读取 ``sys.*`` 目录视图，而不是仅依赖 INFORMATION_SCHEMA，以获得主键、
外键可信状态、检查约束、时间表和扩展属性等完整结构证据。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from .adapter import QueryExecutor
from .config import SQLServerScanConfig


@dataclass(frozen=True)
class ColumnMetadata:
    schema: str
    table: str
    name: str
    ordinal: int
    data_type: str
    max_length: int
    precision: int
    scale: int
    is_nullable: bool
    is_identity: bool
    is_computed: bool
    default_definition: str | None
    description: str | None

    @property
    def qualified_name(self) -> str:
        return f"{self.schema}.{self.table}.{self.name}"


@dataclass(frozen=True)
class KeyConstraintMetadata:
    schema: str
    table: str
    name: str
    constraint_type: str  # PK / UQ
    columns: tuple[str, ...]


@dataclass(frozen=True)
class IndexMetadata:
    schema: str
    table: str
    name: str | None
    type_desc: str
    is_unique: bool
    is_primary_key: bool
    is_unique_constraint: bool
    is_disabled: bool


@dataclass(frozen=True)
class CheckConstraintMetadata:
    schema: str
    table: str
    name: str
    definition: str
    is_disabled: bool
    is_not_trusted: bool


@dataclass(frozen=True)
class ForeignKeyMetadata:
    name: str
    parent_schema: str
    parent_table: str
    parent_columns: tuple[str, ...]
    referenced_schema: str
    referenced_table: str
    referenced_columns: tuple[str, ...]
    is_disabled: bool
    is_not_trusted: bool
    delete_action: str
    update_action: str

    @property
    def parent_qualified_name(self) -> str:
        return f"{self.parent_schema}.{self.parent_table}"

    @property
    def referenced_qualified_name(self) -> str:
        return f"{self.referenced_schema}.{self.referenced_table}"


@dataclass
class TableMetadata:
    schema: str
    name: str
    description: str | None
    row_count: int
    temporal_type: int
    is_memory_optimized: bool
    columns: list[ColumnMetadata] = field(default_factory=list)
    keys: list[KeyConstraintMetadata] = field(default_factory=list)
    indexes: list[IndexMetadata] = field(default_factory=list)
    checks: list[CheckConstraintMetadata] = field(default_factory=list)

    @property
    def qualified_name(self) -> str:
        return f"{self.schema}.{self.name}"

    @property
    def primary_key(self) -> KeyConstraintMetadata | None:
        return next((item for item in self.keys if item.constraint_type == "PK"), None)

    @property
    def unique_constraints(self) -> tuple[KeyConstraintMetadata, ...]:
        return tuple(item for item in self.keys if item.constraint_type == "UQ")

    @property
    def is_heap(self) -> bool:
        return not any(
            item.type_desc in {"CLUSTERED", "CLUSTERED COLUMNSTORE"}
            and not item.is_disabled
            for item in self.indexes
        )


@dataclass(frozen=True)
class DatabaseMetadata:
    database_name: str
    server_name: str
    product_version: str
    edition: str
    collected_at: str
    tables: tuple[TableMetadata, ...]
    foreign_keys: tuple[ForeignKeyMetadata, ...]

    def table_map(self) -> dict[str, TableMetadata]:
        return {table.qualified_name: table for table in self.tables}


class SQLServerMetadataCollector:
    """从SQL Server系统目录采集结构元数据。"""

    def __init__(self, executor: QueryExecutor, scan: SQLServerScanConfig):
        self.executor = executor
        self.scan = scan

    def collect(self) -> DatabaseMetadata:
        server = self.executor.fetch_one(
            """
            -- EDQSG:SERVER_INFO
            SELECT
                DB_NAME() AS database_name,
                CAST(SERVERPROPERTY('ServerName') AS nvarchar(256)) AS server_name,
                CAST(SERVERPROPERTY('ProductVersion') AS nvarchar(128)) AS product_version,
                CAST(SERVERPROPERTY('Edition') AS nvarchar(256)) AS edition
            """
        ) or {}
        table_rows = self.executor.fetch_all(self._tables_sql())
        table_rows = self._filter_tables(table_rows)
        allowed = {(row["schema_name"], row["table_name"]) for row in table_rows}

        columns = self._collect_columns(allowed)
        keys = self._collect_keys(allowed)
        indexes = self._collect_indexes(allowed)
        checks = self._collect_checks(allowed)
        foreign_keys = self._collect_foreign_keys(allowed)

        tables: list[TableMetadata] = []
        for row in table_rows:
            key = (row["schema_name"], row["table_name"])
            tables.append(
                TableMetadata(
                    schema=key[0],
                    name=key[1],
                    description=row.get("description"),
                    row_count=int(row.get("row_count") or 0),
                    temporal_type=int(row.get("temporal_type") or 0),
                    is_memory_optimized=bool(row.get("is_memory_optimized")),
                    columns=columns.get(key, []),
                    keys=keys.get(key, []),
                    indexes=indexes.get(key, []),
                    checks=checks.get(key, []),
                )
            )
        return DatabaseMetadata(
            database_name=str(server.get("database_name") or ""),
            server_name=str(server.get("server_name") or ""),
            product_version=str(server.get("product_version") or ""),
            edition=str(server.get("edition") or ""),
            collected_at=datetime.now(timezone.utc).isoformat(),
            tables=tuple(tables),
            foreign_keys=tuple(foreign_keys),
        )

    @staticmethod
    def _tables_sql() -> str:
        return """
        -- EDQSG:TABLES
        SELECT
            s.name AS schema_name,
            t.name AS table_name,
            CONVERT(nvarchar(4000), ep.value) AS description,
            COALESCE(SUM(CASE WHEN p.index_id IN (0, 1) THEN p.rows ELSE 0 END), 0) AS row_count,
            t.temporal_type,
            t.is_memory_optimized
        FROM sys.tables AS t
        INNER JOIN sys.schemas AS s ON s.schema_id = t.schema_id
        LEFT JOIN sys.partitions AS p ON p.object_id = t.object_id
        LEFT JOIN sys.extended_properties AS ep
          ON ep.major_id = t.object_id
         AND ep.minor_id = 0
         AND ep.name = N'MS_Description'
        WHERE t.is_ms_shipped = 0
        GROUP BY s.name, t.name, ep.value, t.temporal_type, t.is_memory_optimized
        ORDER BY s.name, t.name
        """

    def _filter_tables(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        schema_set = set(self.scan.schemas)
        include = set(self.scan.include_tables)
        exclude = set(self.scan.exclude_tables)
        result: list[dict[str, Any]] = []
        for row in rows:
            schema = str(row["schema_name"])
            table = str(row["table_name"])
            qualified = f"{schema}.{table}"
            if schema_set and schema not in schema_set:
                continue
            if include and table not in include and qualified not in include:
                continue
            if table in exclude or qualified in exclude:
                continue
            result.append(row)
        if self.scan.max_tables is not None:
            result = result[: self.scan.max_tables]
        return result

    def _collect_columns(
        self, allowed: set[tuple[str, str]]
    ) -> dict[tuple[str, str], list[ColumnMetadata]]:
        rows = self.executor.fetch_all(
            """
            -- EDQSG:COLUMNS
            SELECT
                s.name AS schema_name,
                t.name AS table_name,
                c.name AS column_name,
                c.column_id AS ordinal_position,
                ty.name AS data_type,
                c.max_length,
                c.precision,
                c.scale,
                c.is_nullable,
                c.is_identity,
                c.is_computed,
                dc.definition AS default_definition,
                CONVERT(nvarchar(4000), ep.value) AS description
            FROM sys.tables AS t
            INNER JOIN sys.schemas AS s ON s.schema_id = t.schema_id
            INNER JOIN sys.columns AS c ON c.object_id = t.object_id
            INNER JOIN sys.types AS ty ON ty.user_type_id = c.user_type_id
            LEFT JOIN sys.default_constraints AS dc
              ON dc.parent_object_id = t.object_id
             AND dc.parent_column_id = c.column_id
            LEFT JOIN sys.extended_properties AS ep
              ON ep.major_id = t.object_id
             AND ep.minor_id = c.column_id
             AND ep.name = N'MS_Description'
            WHERE t.is_ms_shipped = 0
            ORDER BY s.name, t.name, c.column_id
            """
        )
        result: dict[tuple[str, str], list[ColumnMetadata]] = {}
        for row in rows:
            key = (str(row["schema_name"]), str(row["table_name"]))
            if key not in allowed:
                continue
            bucket = result.setdefault(key, [])
            if (
                self.scan.max_columns_per_table is not None
                and len(bucket) >= self.scan.max_columns_per_table
            ):
                continue
            bucket.append(
                ColumnMetadata(
                    schema=key[0],
                    table=key[1],
                    name=str(row["column_name"]),
                    ordinal=int(row["ordinal_position"]),
                    data_type=str(row["data_type"]),
                    max_length=int(row.get("max_length") or 0),
                    precision=int(row.get("precision") or 0),
                    scale=int(row.get("scale") or 0),
                    is_nullable=bool(row.get("is_nullable")),
                    is_identity=bool(row.get("is_identity")),
                    is_computed=bool(row.get("is_computed")),
                    default_definition=row.get("default_definition"),
                    description=row.get("description"),
                )
            )
        return result

    def _collect_keys(
        self, allowed: set[tuple[str, str]]
    ) -> dict[tuple[str, str], list[KeyConstraintMetadata]]:
        rows = self.executor.fetch_all(
            """
            -- EDQSG:KEYS
            SELECT
                s.name AS schema_name,
                t.name AS table_name,
                kc.name AS constraint_name,
                kc.type AS constraint_type,
                ic.key_ordinal,
                c.name AS column_name
            FROM sys.key_constraints AS kc
            INNER JOIN sys.tables AS t ON t.object_id = kc.parent_object_id
            INNER JOIN sys.schemas AS s ON s.schema_id = t.schema_id
            INNER JOIN sys.index_columns AS ic
              ON ic.object_id = t.object_id
             AND ic.index_id = kc.unique_index_id
            INNER JOIN sys.columns AS c
              ON c.object_id = ic.object_id
             AND c.column_id = ic.column_id
            ORDER BY s.name, t.name, kc.name, ic.key_ordinal
            """
        )
        grouped: dict[tuple[str, str, str, str], list[tuple[int, str]]] = {}
        for row in rows:
            key2 = (str(row["schema_name"]), str(row["table_name"]))
            if key2 not in allowed:
                continue
            key = (*key2, str(row["constraint_name"]), str(row["constraint_type"]))
            grouped.setdefault(key, []).append(
                (int(row["key_ordinal"]), str(row["column_name"]))
            )
        result: dict[tuple[str, str], list[KeyConstraintMetadata]] = {}
        for (schema, table, name, constraint_type), values in grouped.items():
            result.setdefault((schema, table), []).append(
                KeyConstraintMetadata(
                    schema=schema,
                    table=table,
                    name=name,
                    constraint_type=constraint_type,
                    columns=tuple(column for _, column in sorted(values)),
                )
            )
        return result

    def _collect_indexes(
        self, allowed: set[tuple[str, str]]
    ) -> dict[tuple[str, str], list[IndexMetadata]]:
        rows = self.executor.fetch_all(
            """
            -- EDQSG:INDEXES
            SELECT
                s.name AS schema_name,
                t.name AS table_name,
                i.name AS index_name,
                i.type_desc,
                i.is_unique,
                i.is_primary_key,
                i.is_unique_constraint,
                i.is_disabled
            FROM sys.tables AS t
            INNER JOIN sys.schemas AS s ON s.schema_id = t.schema_id
            INNER JOIN sys.indexes AS i ON i.object_id = t.object_id
            WHERE t.is_ms_shipped = 0 AND i.index_id > 0
            ORDER BY s.name, t.name, i.index_id
            """
        )
        result: dict[tuple[str, str], list[IndexMetadata]] = {}
        for row in rows:
            key = (str(row["schema_name"]), str(row["table_name"]))
            if key not in allowed:
                continue
            result.setdefault(key, []).append(
                IndexMetadata(
                    schema=key[0],
                    table=key[1],
                    name=row.get("index_name"),
                    type_desc=str(row["type_desc"]),
                    is_unique=bool(row.get("is_unique")),
                    is_primary_key=bool(row.get("is_primary_key")),
                    is_unique_constraint=bool(row.get("is_unique_constraint")),
                    is_disabled=bool(row.get("is_disabled")),
                )
            )
        return result

    def _collect_checks(
        self, allowed: set[tuple[str, str]]
    ) -> dict[tuple[str, str], list[CheckConstraintMetadata]]:
        rows = self.executor.fetch_all(
            """
            -- EDQSG:CHECKS
            SELECT
                s.name AS schema_name,
                t.name AS table_name,
                cc.name AS constraint_name,
                cc.definition,
                cc.is_disabled,
                cc.is_not_trusted
            FROM sys.check_constraints AS cc
            INNER JOIN sys.tables AS t ON t.object_id = cc.parent_object_id
            INNER JOIN sys.schemas AS s ON s.schema_id = t.schema_id
            ORDER BY s.name, t.name, cc.name
            """
        )
        result: dict[tuple[str, str], list[CheckConstraintMetadata]] = {}
        for row in rows:
            key = (str(row["schema_name"]), str(row["table_name"]))
            if key not in allowed:
                continue
            result.setdefault(key, []).append(
                CheckConstraintMetadata(
                    schema=key[0],
                    table=key[1],
                    name=str(row["constraint_name"]),
                    definition=str(row["definition"]),
                    is_disabled=bool(row.get("is_disabled")),
                    is_not_trusted=bool(row.get("is_not_trusted")),
                )
            )
        return result

    def _collect_foreign_keys(
        self, allowed: set[tuple[str, str]]
    ) -> list[ForeignKeyMetadata]:
        rows = self.executor.fetch_all(
            """
            -- EDQSG:FOREIGN_KEYS
            SELECT
                fk.name AS fk_name,
                ps.name AS parent_schema,
                pt.name AS parent_table,
                pc.name AS parent_column,
                rs.name AS referenced_schema,
                rt.name AS referenced_table,
                rc.name AS referenced_column,
                fkc.constraint_column_id,
                fk.is_disabled,
                fk.is_not_trusted,
                fk.delete_referential_action_desc AS delete_action,
                fk.update_referential_action_desc AS update_action
            FROM sys.foreign_keys AS fk
            INNER JOIN sys.foreign_key_columns AS fkc
              ON fkc.constraint_object_id = fk.object_id
            INNER JOIN sys.tables AS pt ON pt.object_id = fk.parent_object_id
            INNER JOIN sys.schemas AS ps ON ps.schema_id = pt.schema_id
            INNER JOIN sys.columns AS pc
              ON pc.object_id = pt.object_id
             AND pc.column_id = fkc.parent_column_id
            INNER JOIN sys.tables AS rt ON rt.object_id = fk.referenced_object_id
            INNER JOIN sys.schemas AS rs ON rs.schema_id = rt.schema_id
            INNER JOIN sys.columns AS rc
              ON rc.object_id = rt.object_id
             AND rc.column_id = fkc.referenced_column_id
            ORDER BY fk.name, fkc.constraint_column_id
            """
        )
        grouped: dict[tuple[str, str, str, str, str], list[dict[str, Any]]] = {}
        for row in rows:
            parent = (str(row["parent_schema"]), str(row["parent_table"]))
            referenced = (str(row["referenced_schema"]), str(row["referenced_table"]))
            if parent not in allowed or referenced not in allowed:
                continue
            key = (
                str(row["fk_name"]),
                parent[0],
                parent[1],
                referenced[0],
                referenced[1],
            )
            grouped.setdefault(key, []).append(row)
        result: list[ForeignKeyMetadata] = []
        for (name, ps, pt, rs, rt), values in grouped.items():
            ordered = sorted(values, key=lambda item: int(item["constraint_column_id"]))
            first = ordered[0]
            result.append(
                ForeignKeyMetadata(
                    name=name,
                    parent_schema=ps,
                    parent_table=pt,
                    parent_columns=tuple(str(item["parent_column"]) for item in ordered),
                    referenced_schema=rs,
                    referenced_table=rt,
                    referenced_columns=tuple(
                        str(item["referenced_column"]) for item in ordered
                    ),
                    is_disabled=bool(first.get("is_disabled")),
                    is_not_trusted=bool(first.get("is_not_trusted")),
                    delete_action=str(first.get("delete_action") or "NO_ACTION"),
                    update_action=str(first.get("update_action") or "NO_ACTION"),
                )
            )
        return result
