PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;
CREATE TABLE IF NOT EXISTS projects (
 id TEXT PRIMARY KEY, name TEXT NOT NULL, version INTEGER NOT NULL CHECK(version>0),
 data_json TEXT NOT NULL CHECK(json_valid(data_json)), created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS revisions (
 project_id TEXT NOT NULL REFERENCES projects(id), version INTEGER NOT NULL,
 data_json TEXT NOT NULL CHECK(json_valid(data_json)), reason TEXT NOT NULL, created_at TEXT NOT NULL,
 PRIMARY KEY(project_id,version)
);
CREATE TABLE IF NOT EXISTS documents (
 id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id), project_version INTEGER NOT NULL,
 kind TEXT NOT NULL CHECK(kind IN ('visit1','visit2','visit3','plan','result')),
 content_json TEXT NOT NULL CHECK(json_valid(content_json)), source_json TEXT NOT NULL CHECK(json_valid(source_json)), created_at TEXT NOT NULL,
 FOREIGN KEY(project_id,project_version) REFERENCES revisions(project_id,version)
);
CREATE INDEX IF NOT EXISTS documents_project ON documents(project_id,kind,created_at);
CREATE TABLE IF NOT EXISTS templates (
 id TEXT PRIMARY KEY, name TEXT NOT NULL, sha256 TEXT NOT NULL, file_name TEXT NOT NULL,
 mapping_json TEXT NOT NULL CHECK(json_valid(mapping_json)), created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS audit_log (
 id INTEGER PRIMARY KEY AUTOINCREMENT, project_id TEXT REFERENCES projects(id), action TEXT NOT NULL,
 detail_json TEXT NOT NULL CHECK(json_valid(detail_json)), created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS transcriptions (
 id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id), project_version INTEGER NOT NULL,
 visit_round TEXT NOT NULL CHECK(visit_round IN ('1','2','3')), transcript TEXT NOT NULL,
 memo TEXT NOT NULL DEFAULT '',
 summary TEXT NOT NULL, categories_json TEXT NOT NULL CHECK(json_valid(categories_json)),
 registered_json TEXT NOT NULL CHECK(json_valid(registered_json)), created_at TEXT NOT NULL, updated_at TEXT NOT NULL DEFAULT '',
 FOREIGN KEY(project_id,project_version) REFERENCES revisions(project_id,version)
);
CREATE INDEX IF NOT EXISTS transcriptions_project ON transcriptions(project_id,created_at);
CREATE VIEW IF NOT EXISTS project_kpis AS
 SELECT p.id AS project_id, json_extract(k.value,'$.id') AS kpi_id,
 json_extract(k.value,'$.name.value') AS name, json_extract(k.value,'$.baseline.value') AS baseline,
 json_extract(k.value,'$.target.value') AS target, json_extract(k.value,'$.actual.value') AS actual
 FROM projects p, json_each(p.data_json,'$.kpis') k;
CREATE VIEW IF NOT EXISTS project_assets AS
 SELECT p.id AS project_id, a.value AS asset_json FROM projects p, json_each(p.data_json,'$.assets') a;
