"""SQL Server 只读连接适配器。

正式运行依赖 SQLAlchemy 与 pyodbc。模块采用延迟导入，因此仅使用EDQSG内核
时无需安装数据库依赖。
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from contextlib import contextmanager
from typing import Any, Protocol

from .config import SQLServerConnectionConfig


class QueryExecutor(Protocol):
    """采集器所需的最小数据库执行接口，便于使用假对象进行单元测试。"""

    def fetch_all(self, sql: str, params: Mapping[str, Any] | None = None) -> list[dict[str, Any]]:
        ...

    def fetch_one(self, sql: str, params: Mapping[str, Any] | None = None) -> dict[str, Any] | None:
        ...

    def scalar(self, sql: str, params: Mapping[str, Any] | None = None) -> Any:
        ...


_DANGEROUS_SQL = re.compile(
    r"\b(insert|update|delete|merge|alter|drop|truncate|create|grant|revoke|deny|execute|exec)\b",
    flags=re.IGNORECASE,
)


def quote_identifier(value: str) -> str:
    """使用SQL Server方括号安全引用单个标识符。"""

    if not isinstance(value, str) or not value:
        raise ValueError("SQL标识符不能为空。")
    return "[" + value.replace("]", "]]" ) + "]"


def split_qualified_name(value: str, default_schema: str = "dbo") -> tuple[str, str]:
    """将 ``schema.table`` 解析为二元组；未提供schema时使用默认值。"""

    parts = [part.strip() for part in value.split(".") if part.strip()]
    if len(parts) == 1:
        return default_schema, parts[0]
    if len(parts) == 2:
        return parts[0], parts[1]
    raise ValueError(f"对象名格式不正确：{value!r}，应为table或schema.table。")


def qualified_name(schema: str, table: str) -> str:
    return f"{quote_identifier(schema)}.{quote_identifier(table)}"


def validate_sql_condition(fragment: str, name: str = "SQL条件") -> str:
    """校验由可信配置提供的只读条件片段。

    该校验不是通用SQL沙箱，只用于防止明显的多语句、注释和DML/DDL输入。
    运行账户仍必须使用只读最小权限。
    """

    value = fragment.strip()
    if not value:
        raise ValueError(f"{name}不能为空。")
    if ";" in value or "--" in value or "/*" in value or "*/" in value:
        raise ValueError(f"{name}不能包含分号或SQL注释。")
    if _DANGEROUS_SQL.search(value):
        raise ValueError(f"{name}包含禁止的DML/DDL关键字。")
    return value


class SQLServerAdapter:
    """基于SQLAlchemy 2.x和pyodbc的SQL Server只读适配器。"""

    def __init__(
        self, config: SQLServerConnectionConfig, *, read_uncommitted: bool = False
    ):
        config.validate()
        self.config = config
        self.read_uncommitted = bool(read_uncommitted)
        self._engine = None

    def _create_engine(self):
        try:
            from sqlalchemy import create_engine, event
            from sqlalchemy.engine import URL
        except ImportError as exc:  # pragma: no cover - 运行环境决定
            raise RuntimeError(
                "SQL Server连接需安装数据库依赖：pip install edqsg[sqlserver]"
            ) from exc

        query: dict[str, str] = {
            "driver": self.config.driver,
            "Encrypt": "yes" if self.config.encrypt else "no",
            "TrustServerCertificate": (
                "yes" if self.config.trust_server_certificate else "no"
            ),
            "APP": self.config.application_name,
        }
        username = None
        password = None
        if self.config.authentication == "windows":
            query["trusted_connection"] = "yes"
        else:
            username = self.config.username
            password = self.config.resolved_password()

        url = URL.create(
            "mssql+pyodbc",
            username=username,
            password=password,
            host=self.config.server,
            port=self.config.port,
            database=self.config.database,
            query=query,
        )
        engine = create_engine(
            url,
            pool_pre_ping=True,
            future=True,
            connect_args={"timeout": self.config.login_timeout},
        )

        @event.listens_for(engine, "before_cursor_execute")
        def _set_timeout(conn, cursor, statement, parameters, context, executemany):
            del conn, statement, parameters, context, executemany
            try:
                cursor.timeout = self.config.query_timeout
            except (AttributeError, TypeError):
                # 少数DBAPI实现不暴露游标超时属性，连接仍可正常使用。
                pass

        return engine

    @property
    def engine(self):
        if self._engine is None:
            self._engine = self._create_engine()
        return self._engine

    @contextmanager
    def connection(self):
        with self.engine.connect() as connection:
            if self.read_uncommitted:
                connection = connection.execution_options(
                    isolation_level="READ UNCOMMITTED"
                )
            yield connection

    @staticmethod
    def _text(sql: str):
        try:
            from sqlalchemy import text
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("未安装SQLAlchemy。") from exc
        return text(sql)

    def fetch_all(
        self, sql: str, params: Mapping[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        with self.connection() as connection:
            result = connection.execute(self._text(sql), dict(params or {}))
            return [dict(row._mapping) for row in result]

    def fetch_one(
        self, sql: str, params: Mapping[str, Any] | None = None
    ) -> dict[str, Any] | None:
        with self.connection() as connection:
            row = connection.execute(self._text(sql), dict(params or {})).first()
            return None if row is None else dict(row._mapping)

    def scalar(self, sql: str, params: Mapping[str, Any] | None = None) -> Any:
        with self.connection() as connection:
            return connection.execute(self._text(sql), dict(params or {})).scalar()

    def test_connection(self) -> dict[str, Any]:
        row = self.fetch_one(
            """
            -- EDQSG:CONNECTION_TEST
            SELECT
                DB_NAME() AS database_name,
                CAST(SERVERPROPERTY('ServerName') AS nvarchar(256)) AS server_name,
                CAST(SERVERPROPERTY('ProductVersion') AS nvarchar(128)) AS product_version,
                CAST(SERVERPROPERTY('Edition') AS nvarchar(256)) AS edition
            """
        )
        return row or {}

    def dispose(self) -> None:
        if self._engine is not None:
            self._engine.dispose()
            self._engine = None
