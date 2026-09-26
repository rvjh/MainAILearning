-- Local demo credentials only. Runtime cannot mutate audit/decisions or perform DDL.
CREATE ROLE lab_app LOGIN PASSWORD 'classroom';
GRANT CONNECT ON DATABASE enterprise TO lab_app;
GRANT USAGE ON SCHEMA public TO lab_app;
GRANT SELECT,INSERT,UPDATE ON ALL TABLES IN SCHEMA public TO lab_app;
REVOKE UPDATE ON audit_events,approval_decisions,security_events,schema_migrations,tenants,principals,orders FROM lab_app;
REVOKE INSERT ON schema_migrations,tenants,principals FROM lab_app;
INSERT INTO schema_migrations(version) VALUES(2);
