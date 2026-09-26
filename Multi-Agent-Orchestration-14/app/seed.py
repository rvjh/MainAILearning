"""Idempotent seeds. Run with migration/admin credentials, never grant identity writes to API."""
import os
import uuid
import psycopg
from .db import token_hash

def stable(name): return str(uuid.uuid5(uuid.NAMESPACE_DNS,'week7.acme.'+name))

def main():
    dsn=os.getenv('ADMIN_DATABASE_URL','postgresql://lab_admin:classroom-admin@db:5432/enterprise')
    with psycopg.connect(dsn) as c:
        for tenant in ('acme','globex'):
            tid=stable(tenant)
            c.execute('INSERT INTO tenants VALUES(%s,%s) ON CONFLICT DO NOTHING',(tid,tenant.upper()))
            for role in ('requester','support_lead','finance_manager','finance_director','operator'):
                subject=tenant+'-'+role
                c.execute('''INSERT INTO principals(tenant_id,id,subject,role,token_hash) VALUES(%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING''',
                          (tid,stable(subject),subject,role,token_hash(subject+'-token')))
    print('Seeded ACME and GLOBEX classroom identities. No existing workflow data changed.')

if __name__=='__main__': main()
