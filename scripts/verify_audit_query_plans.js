/*
Usage:
  mongosh "mongodb://localhost:27017/<db_name>" scripts/verify_audit_query_plans.js

This script prints explain plans for key session_audit_logs query patterns.
*/

function printExplain(title, cursor) {
  print("\n=== " + title + " ===");
  const result = cursor.explain("executionStats");
  printjson({
    winningPlan: result.queryPlanner.winningPlan,
    executionStats: {
      nReturned: result.executionStats.nReturned,
      totalKeysExamined: result.executionStats.totalKeysExamined,
      totalDocsExamined: result.executionStats.totalDocsExamined,
      executionTimeMillis: result.executionStats.executionTimeMillis,
    },
  });
}

const c = db.session_audit_logs;

printExplain(
  "actor_user_uuid + created_at desc",
  c.find({ actor_user_uuid: "sample-user" }).sort({ created_at: -1 }).limit(20)
);

printExplain(
  "target_user_uuid + created_at desc",
  c.find({ target_user_uuid: "sample-user" }).sort({ created_at: -1 }).limit(20)
);

printExplain(
  "action + created_at desc",
  c.find({ action: "logout" }).sort({ created_at: -1 }).limit(20)
);

printExplain(
  "created_at desc pagination",
  c.find({ created_at: { $lt: ISODate("2026-07-07T00:00:00Z") } })
    .sort({ created_at: -1 })
    .limit(100)
);
