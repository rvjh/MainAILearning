import hashlib
import json
import os
import uuid
from contextlib import contextmanager
import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

def load_dotenv(path=None):
    path = path or os.path.join(os.path.dirname(__file__), '..', '.env')
    if not os.path.isfile(path):
        return
    for raw in open(path, encoding='utf-8'):
        line = raw.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, value = line.split('=', 1)
        key, value = key.strip(), value.strip().strip('"').strip("'")
        if key and not os.environ.get(key, '').strip():
            os.environ[key] = value

def apply_langsmith_env():
    api_key = os.getenv('LANGSMITH_API_KEY', '').strip()
    if not api_key:
        return
    flag = os.getenv('LANGSMITH_TRACING', '').strip().lower()
    if flag in {'0', 'false', 'no', 'off'}:
        os.environ['LANGCHAIN_TRACING_V2'] = 'false'
        return
    os.environ['LANGSMITH_TRACING'] = 'true'
    os.environ['LANGCHAIN_TRACING_V2'] = 'true'
    os.environ['LANGCHAIN_API_KEY'] = api_key
    os.environ['LANGSMITH_API_KEY'] = api_key
    project = (os.getenv('LANGSMITH_PROJECT') or 'july-cohort-observability').strip()
    os.environ['LANGCHAIN_PROJECT'] = project
    os.environ['LANGSMITH_PROJECT'] = project

load_dotenv()
apply_langsmith_env()

DSN = os.getenv('DATABASE_URL', 'postgresql://lab_app:classroom@localhost:5547/enterprise')

def uid():
    return str(uuid.uuid4())

def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str, separators=(',', ':')).encode()).hexdigest()

def token_hash(token):
    return hashlib.sha256(token.encode()).hexdigest()

@contextmanager
def tx():
    with psycopg.connect(DSN, row_factory=dict_row) as c:
        c.execute("SET LOCAL lock_timeout = '5s'")
        c.execute("SET LOCAL statement_timeout = '10s'")
        yield c

def one(c, sql, args=()):
    return c.execute(sql, args).fetchone()

def all_rows(c, sql, args=()):
    return c.execute(sql, args).fetchall()

def log(event, **fields):
    print(json.dumps({'event': event, **fields}, default=str), flush=True)

class DomainError(Exception):
    def __init__(self, status, message):
        self.status, self.message = status, message

def actor(token):
    with tx() as c:
        a = one(c, 'SELECT * FROM principals WHERE token_hash=%s AND active', (token_hash(token),))
    if not a:
        raise DomainError(401, 'Unknown or inactive classroom identity')
    return a

def lock_workflow(c, tenant, wid):
    w = one(c, 'SELECT * FROM workflow_instances WHERE tenant_id=%s AND id=%s FOR UPDATE', (tenant, wid))
    if not w:
        raise DomainError(404, 'Workflow not found in your tenant')
    return w

def audit(c, w, event, who=None, reason=None, details=None, request_id=None, cause=None):
    # Caller holds workflow lock, serializing sequence allocation.
    seq = one(c, 'SELECT COALESCE(max(sequence_no),0)+1 AS n FROM audit_events WHERE tenant_id=%s AND workflow_id=%s', (w['tenant_id'], w['id']))['n']
    c.execute('''INSERT INTO audit_events(tenant_id,id,workflow_id,sequence_no,event_type,
        actor_id,actor_kind,actor_role_snapshot,reason,policy_version,proposal_version,request_id,correlation_id,causation_id,details)
        VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)''',
        (w['tenant_id'], uid(), w['id'], seq, event, who['id'] if who else None,
         'human' if who else 'system', who['role'] if who else None, reason, w['policy_version'],
         w['proposal_version'], request_id, w['id'], cause, Jsonb(details or {})))

def transition(c, w, state):
    w.update(one(c, '''UPDATE workflow_instances SET state=%s,version=version+1,
        updated_at=clock_timestamp() WHERE tenant_id=%s AND id=%s RETURNING *''', (state, w['tenant_id'], w['id'])))

def emit(c, w, kind, **payload):
    eid = uid()
    c.execute('''INSERT INTO outbox_events(id,tenant_id,workflow_id,aggregate_version,event_type,payload)
        VALUES(%s,%s,%s,%s,%s,%s)''', (eid,w['tenant_id'],w['id'],w['version'],kind,Jsonb(payload)))
    return eid
