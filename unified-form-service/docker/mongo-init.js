// mongo-init.js
// Runs automatically on first container start.
// Creates all required databases and collections with indexes.

const databases = [
  {
    name: "form_builder_db",
    collections: [
      { name: "users",         indexes: [{ key: { email: 1 }, unique: true }] },
      { name: "organizations", indexes: [{ key: { name: 1 } }] },
      { name: "projects",      indexes: [{ key: { organization_id: 1 } }] },
      { name: "forms",         indexes: [{ key: { organization_id: 1 } }, { key: { project_id: 1 } }] },
      { name: "responses",     indexes: [{ key: { form_id: 1 } }, { key: { status: 1 } }] },
      { name: "themes",        indexes: [] },
      { name: "notifications", indexes: [{ key: { user_id: 1 } }] },
    ]
  },
  {
    name: "form_response",
    collections: [
      { name: "form_snapshots", indexes: [{ key: { form_id: 1 }, unique: false }] },
      { name: "responses",      indexes: [{ key: { form_id: 1 } }, { key: { status: 1 } }, { key: { submitted_at: -1 } }] },
    ]
  },
  {
    name: "form_analyser",
    collections: [
      { name: "analysis_definitions", indexes: [{ key: { organization_id: 1 } }] },
      { name: "analysis_results",     indexes: [{ key: { definition_id: 1 } }, { key: { run_at: -1 } }] },
      { name: "api_keys",             indexes: [{ key: { key_hash: 1 }, unique: true }] },
      { name: "webhooks",             indexes: [{ key: { organization_id: 1 } }] },
      { name: "forms",                indexes: [{ key: { survey_id: 1 }, unique: true }] },
      { name: "responses",            indexes: [{ key: { form_id: 1 } }, { key: { submitted_at: -1 } }] },
      { name: "survey_definitions",   indexes: [{ key: { survey_id: 1 }, unique: true }] },
    ]
  }
];

databases.forEach(dbConfig => {
  const db = db.getSiblingDB(dbConfig.name);
  print(`\n✓ Setting up database: ${dbConfig.name}`);

  dbConfig.collections.forEach(col => {
    // Create collection if it doesn't exist
    if (!db.getCollectionNames().includes(col.name)) {
      db.createCollection(col.name);
      print(`  + Created collection: ${col.name}`);
    }

    // Create indexes
    col.indexes.forEach(idx => {
      db[col.name].createIndex(idx.key, idx.unique ? { unique: true } : {});
    });
  });
});

print("\n✅ MongoDB initialisation complete.\n");
