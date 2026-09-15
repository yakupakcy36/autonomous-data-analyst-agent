"""SQL generation and multi-pattern self-healing engine with schema-guided correction."""

import difflib
import re
from typing import Dict, List, Optional


class SQLGeneratorAndHealer:
    """
    Generates schema-aware SQL from natural language intents and automatically heals:
    1. Misspelled column names ('no such column')
    2. Misspelled table names ('no such table')
    3. Ambiguous join columns ('ambiguous column name')
    4. Common SQL keyword syntax typos ('near "...": syntax error')
    """

    KEYWORD_FIXES = {
        "FORM": "FROM",
        "SELEC": "SELECT",
        "WHER": "WHERE",
        "GORUP": "GROUP",
        "ORDR": "ORDER",
    }

    def __init__(self, schema: Dict[str, List[str]]):
        self.schema = schema
        self._all_columns = {col: table for table, cols in schema.items() for col in cols}

    def generate_initial_query(self, user_question: str) -> str:
        q = user_question.lower()

        if "critical" in q or "machine" in q or "vibration" in q or "telemetry" in q:
            if "critical" in q:
                return "SELECT machine_id, sensor_type, reading_value, timestamp FROM equipment_telemetry WHERE operational_status = 'Critical' ORDER BY reading_value DESC;"
            return "SELECT machine_id, sensor_type, AVG(reading_value) as avg_reading FROM equipment_telemetry GROUP BY machine_id, sensor_type;"

        if "order" in q or "revenue" in q or "sales" in q or "spend" in q:
            if "total" in q or "sum" in q or "revenue" in q:
                return "SELECT category, SUM(amount) as total_revenue, COUNT(*) as order_count FROM orders WHERE status = 'Completed' GROUP BY category ORDER BY total_revenue DESC;"
            if "top" in q or "highest" in q:
                return "SELECT c.name, c.tier, SUM(o.amount) as total_spent FROM customers c JOIN orders o ON c.customer_id = o.customer_id WHERE o.status = 'Completed' GROUP BY c.name, c.tier ORDER BY total_spent DESC LIMIT 5;"
            return "SELECT order_id, customer_id, category, amount, status FROM orders WHERE status = 'Completed' ORDER BY amount DESC LIMIT 10;"

        if "customer" in q or "tier" in q or "enterprise" in q:
            if "enterprise" in q:
                return "SELECT customer_id, name, region, annual_spend FROM customers WHERE tier = 'Enterprise' ORDER BY annual_spend DESC;"
            return "SELECT tier, COUNT(*) as customer_count, AVG(annual_spend) as avg_annual_spend FROM customers GROUP BY tier ORDER BY avg_annual_spend DESC;"

        return "SELECT customer_id, name, tier, region, annual_spend FROM customers ORDER BY annual_spend DESC LIMIT 5;"

    def heal_query(self, faulty_sql: str, error_message: str) -> Optional[str]:
        """Diagnoses SQLite OperationalError messages and synthesizes a repaired SQL query."""
        # Case 1: no such column: <col_name>
        col_match = re.search(r"no such column:\s*([a-zA-Z0-9_.]+)", error_message, flags=re.IGNORECASE)
        if col_match:
            faulty_col = col_match.group(1).split(".")[-1]
            all_cols = list(self._all_columns.keys())
            closest = difflib.get_close_matches(faulty_col, all_cols, n=1, cutoff=0.5)
            if closest:
                healed_col = closest[0]
                return re.sub(rf"\b{faulty_col}\b", healed_col, faulty_sql, flags=re.IGNORECASE)

        # Case 2: no such table: <table_name>
        tbl_match = re.search(r"no such table:\s*([a-zA-Z0-9_]+)", error_message, flags=re.IGNORECASE)
        if tbl_match:
            faulty_tbl = tbl_match.group(1)
            all_tables = list(self.schema.keys())
            closest = difflib.get_close_matches(faulty_tbl, all_tables, n=1, cutoff=0.5)
            if closest:
                healed_tbl = closest[0]
                return re.sub(rf"\b{faulty_tbl}\b", healed_tbl, faulty_sql, flags=re.IGNORECASE)

        # Case 3: ambiguous column name: <col_name>
        amb_match = re.search(r"ambiguous column name:\s*([a-zA-Z0-9_]+)", error_message, flags=re.IGNORECASE)
        if amb_match:
            amb_col = amb_match.group(1)
            owner_table = self._all_columns.get(amb_col)
            if owner_table:
                return re.sub(rf"(?<!\.)\b{amb_col}\b", f"{owner_table}.{amb_col}", faulty_sql, count=1)

        # Case 4: syntax error near "<token>"
        syn_match = re.search(r'near\s+"([a-zA-Z0-9_]+)":\s*syntax error', error_message, flags=re.IGNORECASE)
        if syn_match:
            bad_tok = syn_match.group(1).upper()
            if bad_tok in self.KEYWORD_FIXES:
                fixed_kw = self.KEYWORD_FIXES[bad_tok]
                return re.sub(rf"\b{bad_tok}\b", fixed_kw, faulty_sql, flags=re.IGNORECASE)

        return None
