"""Central deployment-configurable limits for project automation."""

import os


def limit(name, default):
    try:
        return max(1, int(os.environ.get(f"PROJECT_AUTOMATIONS_{name}", default)))
    except (TypeError, ValueError):
        return default


MAX_ENABLED = limit("MAX_ENABLED", 20)
MAX_CONDITIONS = min(3, limit("MAX_CONDITIONS", 3))
MAX_ACTIONS = min(2, limit("MAX_ACTIONS", 2))
RETRIES = limit("RETRIES", 2)
BATCH_SIZE = limit("BATCH_SIZE", 100)
RETENTION_DAYS = limit("RETENTION_DAYS", 30)
