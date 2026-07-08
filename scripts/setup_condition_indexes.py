import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app import create_openapi_app
from app.models.form import Condition
from app.models.condition_management import (
    ConditionApprovalAudit,
    ConditionAsyncJob,
    ConditionEvaluationStat,
    ConditionPreset,
    ConditionVersion,
)


def main() -> None:
    app = create_openapi_app()
    with app.app_context():
        for doc in [
            Condition,
            ConditionPreset,
            ConditionVersion,
            ConditionApprovalAudit,
            ConditionAsyncJob,
            ConditionEvaluationStat,
        ]:
            doc.ensure_indexes()
    print("Condition indexes ensured")


if __name__ == "__main__":
    main()
