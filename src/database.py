"""Database sandbox, index management, and EXPLAIN QUERY PLAN introspection."""

import sqlite3
from typing import Dict, List, Any
import pandas as pd


class DatabaseSandbox:
    """Isolated SQLite sandbox providing query execution, indexing, and query plan analysis."""

    def __init__(self, db_path: str = ":memory:"):
        self.db_path = db_path
        self.connection = sqlite3.connect(self.db_path, check_same_thread=False)
        self._seed_sample_tables()

    def _seed_sample_tables(self):
        cursor = self.connection.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS customers (
                customer_id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                tier TEXT CHECK(tier IN ('Standard', 'Premium', 'Enterprise')),
                region TEXT,
                annual_spend REAL
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                order_id INTEGER PRIMARY KEY,
                customer_id INTEGER,
                category TEXT,
                amount REAL,
                status TEXT CHECK(status IN ('Completed', 'Pending', 'Cancelled')),
                order_date TEXT,
                FOREIGN KEY (customer_id) REFERENCES customers(customer_id)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS equipment_telemetry (
                telemetry_id INTEGER PRIMARY KEY,
                machine_id TEXT NOT NULL,
                sensor_type TEXT,
                reading_value REAL,
                operational_status TEXT,
                timestamp TEXT
            )
        """)

        # Create performance indexes for query plan optimization
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_orders_customer ON orders(customer_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_telemetry_status ON equipment_telemetry(operational_status);")

        cursor.executemany("""
            INSERT INTO customers (customer_id, name, tier, region, annual_spend) VALUES (?, ?, ?, ?, ?)
        """, [
            (101, "Acme Robotics", "Enterprise", "North America", 154000.0),
            (102, "BioTech Labs", "Premium", "Europe", 82000.0),
            (103, "SolarGrid Energy", "Enterprise", "North America", 210000.0),
            (104, "AeroDynamics Corp", "Standard", "Asia-Pacific", 34000.0),
            (105, "Quantum AI Systems", "Enterprise", "Europe", 195000.0),
        ])

        cursor.executemany("""
            INSERT INTO orders (order_id, customer_id, category, amount, status, order_date) VALUES (?, ?, ?, ?, ?, ?)
        """, [
            (1, 101, "Industrial Sensors", 12500.0, "Completed", "2026-01-15"),
            (2, 101, "Maintenance Kit", 4200.0, "Completed", "2026-02-10"),
            (3, 102, "Diagnostic Software", 8500.0, "Completed", "2026-02-14"),
            (4, 103, "Turbine Actuators", 45000.0, "Completed", "2026-03-01"),
            (5, 104, "Replacement Belts", 1800.0, "Cancelled", "2026-03-05"),
            (6, 105, "Edge Compute Nodes", 38000.0, "Completed", "2026-03-12"),
            (7, 103, "Thermal Probes", 6200.0, "Pending", "2026-03-18"),
        ])

        cursor.executemany("""
            INSERT INTO equipment_telemetry (telemetry_id, machine_id, sensor_type, reading_value, operational_status, timestamp) VALUES (?, ?, ?, ?, ?, ?)
        """, [
            (1, "M-01", "Vibration_RMS", 4.2, "Normal", "2026-03-20 08:00:00"),
            (2, "M-01", "Bearing_Temp", 68.5, "Normal", "2026-03-20 08:00:00"),
            (3, "M-02", "Vibration_RMS", 12.8, "Critical", "2026-03-20 08:05:00"),
            (4, "M-02", "Bearing_Temp", 92.4, "Critical", "2026-03-20 08:05:00"),
            (5, "M-03", "Vibration_RMS", 5.1, "Normal", "2026-03-20 08:10:00"),
        ])

        self.connection.commit()

    def get_schema(self) -> Dict[str, List[str]]:
        cursor = self.connection.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
        tables = [row[0] for row in cursor.fetchall()]

        schema: Dict[str, List[str]] = {}
        for table in tables:
            cursor.execute(f"PRAGMA table_info({table});")
            schema[table] = [row[1] for row in cursor.fetchall()]

        return schema

    def explain_query_plan(self, sql_query: str) -> Dict[str, Any]:
        """Run EXPLAIN QUERY PLAN to inspect index usage and scan strategy."""
        cursor = self.connection.cursor()
        cursor.execute(f"EXPLAIN QUERY PLAN {sql_query}")
        rows = cursor.fetchall()
        details = [str(r[-1]) for r in rows]
        uses_index = any("USING INDEX" in d.upper() or "USING INTEGER PRIMARY KEY" in d.upper() for d in details)
        return {
            "plan_steps": details,
            "uses_index": uses_index,
            "scan_strategy": "INDEX_SEARCH" if uses_index else "FULL_TABLE_SCAN",
        }

    def execute(self, sql_query: str) -> pd.DataFrame:
        """Executes a read-only SQL query and returns DataFrame."""
        return pd.read_sql_query(sql_query, self.connection)

    def execute_mutation(self, sql_query: str) -> int:
        """Executes an approved mutation statement (UPDATE/INSERT) and returns affected rows."""
        cursor = self.connection.cursor()
        cursor.execute(sql_query)
        self.connection.commit()
        return cursor.rowcount
