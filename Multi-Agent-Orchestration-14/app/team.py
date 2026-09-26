"""Team case CLI. Edit collect_parallel and supervise in team_starter.py."""
import argparse
import json
import os
import time
import psycopg
from . import team_starter
from .db import *
from .llm import invoke_specialist, langsmith_enabled, openai_key, openai_model

ROLES = ('policy', 'order', 'risk')
SCENARIOS = ('healthy', 'risk_timeout', 'conflict', 'missing_risk', 'malformed')
BACKENDS = ('fixture', 'openai')

def exercises():
    return team_starter

def requester():
    return actor('acme-requester-token')

def new_case(scenario='healthy'):
    if scenario not in SCENARIOS:
        raise ValueError('Unknown scenario')
    who = requester()
    with tx() as c:
        order = one(c, """INSERT INTO orders(tenant_id,id,customer_id,delivered_at,amount_minor,currency,category)
            VALUES(%s,%s,%s,clock_timestamp()-interval '5 days',5000000,'INR','standard') RETURNING *""",
            (who['tenant_id'], uid(), who['id']))
        facts = {'policy': {'age_days': 5, 'limit_days': 45, 'category': 'standard'},
                 'order': {'paid_minor': 5000000, 'already_refunded_minor': 5000000 if scenario == 'conflict' else 0,
                           'requested_minor': 1800000},
                 'risk': {'anomaly': False}}
        return one(c, """INSERT INTO agent_cases(tenant_id,id,requester_id,order_id,amount_minor,scenario,status,facts)
            VALUES(%s,%s,%s,%s,1800000,%s,'COLLECTING',%s) RETURNING *""",
            (who['tenant_id'], uid(), who['id'], order['id'], scenario, Jsonb(facts)))

def get_case(cid):
    who = requester()
    with tx() as c:
        case = one(c, 'SELECT * FROM agent_cases WHERE tenant_id=%s AND id=%s', (who['tenant_id'], cid))
        if not case:
            raise DomainError(404, 'Case not found')
        return case

def evidence(case, role):
    # Per-specialist allowlist: no shared mutable scratchpad or service credentials.
    return {'reference': str(case['id']) + ':' + role + ':v1', 'facts': case['facts'][role]}

def fixture(case, role, round_no):
    time.sleep(0.08)
    if role == 'risk' and (case['scenario'] == 'missing_risk' or
                           (case['scenario'] == 'risk_timeout' and round_no == 1)):
        raise TimeoutError('Injected risk lookup deadline')
    if case['scenario'] == 'malformed' and role == 'policy':
        return {'verdict': 'APPROVE'}
    blocked = role == 'order' and case['facts']['order']['already_refunded_minor'] > 0
    return {'verdict': 'BLOCK' if blocked else 'CLEAR',
            'evidence_ref': evidence(case, role)['reference'],
            'finding': 'Order already fully refunded' if blocked else 'Scoped evidence satisfies this check'}

def live_openai(case, role, model, timeout):
    return invoke_specialist(case, role, model, timeout)

def validate_result(raw, case, role):
    if not isinstance(raw, dict) or set(raw) != {'verdict', 'evidence_ref', 'finding'}:
        raise ValueError('Specialist output must match the exact result contract')
    if raw['verdict'] not in ('CLEAR', 'BLOCK', 'REVIEW'):
        raise ValueError('Unsupported verdict')
    if raw['evidence_ref'] != evidence(case, role)['reference']:
        raise ValueError('Wrong case, specialist or proposal evidence reference')
    if not isinstance(raw['finding'], str) or not 1 <= len(raw['finding']) <= 1000:
        raise ValueError('Finding must contain 1 to 1000 characters')
    facts = case['facts'][role]
    safe = (0 <= facts['age_days'] <= facts['limit_days'] and facts['category'] == 'standard') if role == 'policy' else (
        facts['requested_minor'] <= facts['paid_minor'] - facts['already_refunded_minor'] if role == 'order'
        else not facts['anomaly'])
    if raw['verdict'] == 'CLEAR' and not safe:
        raise ValueError('CLEAR contradicts deterministic source-data check')
    return raw

def call_specialist(case, role, round_no, backend, model, timeout):
    with tx() as c:
        task = one(c, 'SELECT * FROM agent_tasks WHERE tenant_id=%s AND case_id=%s AND specialist=%s AND round_no=%s',
                   (case['tenant_id'], case['id'], role, round_no))
        if not task:
            task = one(c, """INSERT INTO agent_tasks(tenant_id,id,case_id,specialist,round_no,status,due_at)
                VALUES(%s,%s,%s,%s,%s,'RUNNING',clock_timestamp()+(%s * interval '1 second'))
                RETURNING *""", (case['tenant_id'], uid(), case['id'], role, round_no, timeout))
        previous = one(c, 'SELECT result FROM agent_results WHERE tenant_id=%s AND task_id=%s',
                       (case['tenant_id'], task['id']))
        if previous:
            return previous['result']
        remaining = one(c, 'SELECT EXTRACT(EPOCH FROM (%s-clock_timestamp())) AS seconds', (task['due_at'],))['seconds']
    # No open DB transaction while calling a specialist.
    try:
        if remaining <= 0:
            raise TimeoutError('Persisted specialist deadline passed')
        raw = fixture(case, role, round_no) if backend == 'fixture' else live_openai(case, role, model, float(remaining))
        result = validate_result(raw, case, role)
        status = 'SUCCEEDED'
    except Exception as exc:
        # Do not persist a remote response body, secret, or private model reasoning.
        result = {'verdict': 'ERROR', 'evidence_ref': evidence(case, role)['reference'],
                  'finding': type(exc).__name__}
        status = 'FAILED'
    with tx() as c:
        overdue = one(c, 'SELECT clock_timestamp()>due_at AS overdue FROM agent_tasks WHERE tenant_id=%s AND id=%s',
                      (case['tenant_id'], task['id']))['overdue']
        if overdue:
            result = {'verdict': 'ERROR', 'evidence_ref': evidence(case, role)['reference'], 'finding': 'DeadlineExceeded'}
            status = 'FAILED'
        c.execute("""INSERT INTO agent_results(tenant_id,task_id,result,backend,model_version,prompt_version)
            VALUES(%s,%s,%s,%s,%s,%s)""",
            (case['tenant_id'], task['id'], Jsonb(result), backend, model or 'fixture-v1',
             os.getenv('OBS_PROMPT_VERSION', 'specialists-v1')))
        c.execute('UPDATE agent_tasks SET status=%s WHERE tenant_id=%s AND id=%s',
                  (status, case['tenant_id'], task['id']))
    return result

def collect_round(state):
    case = get_case(state['case_id'])
    round_no = state.get('round_no') or 1
    roles = ROLES if round_no == 1 else ('risk',)
    results = dict(state.get('results') or {})
    results.update(exercises().collect_parallel(
        lambda role: call_specialist(case, role, round_no, state['backend'], state.get('model'), state['timeout']),
        roles))
    return {'results': results, 'round_no': round_no}

def decide_round(state):
    case = get_case(state['case_id'])
    round_no = state['round_no']
    results = state['results']
    decision = exercises().supervise(results, round_no)
    if decision.get('action') not in ('FOLLOW_UP', 'READY', 'BLOCKED'):
        raise ValueError('Unknown coordinator action')
    if decision['action'] == 'FOLLOW_UP' and (round_no != 1 or decision.get('target') != 'risk'):
        raise ValueError('Only one risk follow-up is permitted')
    if decision['action'] == 'READY' and any(results.get(r, {}).get('verdict') != 'CLEAR' for r in ROLES):
        raise ValueError('Readiness requires all mandatory evidence CLEAR')
    with tx() as c:
        prior = one(c, 'SELECT * FROM coordination_decisions WHERE tenant_id=%s AND case_id=%s AND round_no=%s',
                    (case['tenant_id'], state['case_id'], round_no))
        if prior:
            decision = {k: prior[k] for k in ('action', 'target', 'reason')}
        else:
            c.execute("""INSERT INTO coordination_decisions(tenant_id,id,case_id,round_no,action,target,reason,input_snapshot)
                VALUES(%s,%s,%s,%s,%s,%s,%s,%s)""",
                (case['tenant_id'], uid(), state['case_id'], round_no, decision['action'],
                 decision.get('target'), decision['reason'], Jsonb(results)))
        if decision['action'] != 'FOLLOW_UP':
            snapshot = {'case_id': state['case_id'], 'proposal_version': 1, 'amount_minor': case['amount_minor'],
                        'results': results, 'coordinator_version': 'bounded-v1'} if decision['action'] == 'READY' else None
            c.execute('UPDATE agent_cases SET status=%s,snapshot=%s WHERE tenant_id=%s AND id=%s',
                      (decision['action'], Jsonb(snapshot) if snapshot else None, case['tenant_id'], state['case_id']))
    log('coordination_decision', case_id=state['case_id'], round=round_no, **decision)
    return {'decision': decision, 'round_no': 2 if decision['action'] == 'FOLLOW_UP' else round_no}

def run_case(cid, backend='fixture', model=None, timeout=30):
    from .graph import TEAM_GRAPH
    if backend not in BACKENDS or not 0 < timeout <= 120:
        raise ValueError('Invalid backend or timeout')
    if backend == 'openai':
        model = openai_model(model)
        if not openai_key():
            raise ValueError('OPENAI_API_KEY is required for --backend openai')
    log('team_run', case_id=cid, backend=backend, model=model or 'fixture-v1', langsmith=langsmith_enabled())
    # Session lock spans calls but holds no transaction. A crashed CLI releases it.
    # Interrupted read-only calls may rerun on resume, so inference cost is at-least-once.
    with psycopg.connect(DSN, autocommit=True) as guard:
        got = guard.execute('SELECT pg_try_advisory_lock(hashtextextended(%s,0))', ('team:' + cid,)).fetchone()[0]
        if not got:
            raise DomainError(409, 'Another coordinator is running this case')
        case = get_case(cid)
        if case['status'] != 'COLLECTING':
            return case
        TEAM_GRAPH.invoke({
            'case_id': cid,
            'backend': backend,
            'model': model,
            'timeout': timeout,
            'round_no': 1,
            'results': {},
        })
        return get_case(cid)

def submit_case(cid, seconds=600, fault='none'):
    from .core import create_request
    case = get_case(cid)
    if not 2 <= seconds <= 3600:
        raise ValueError('Deadline must be 2 to 3600 seconds')
    return create_request(requester(), {'team_case_id': cid, 'order_id': str(case['order_id']),
        'amount_minor': case['amount_minor'], 'idempotency_key': 'team:' + cid,
        'fault': fault, 'approval_seconds': seconds})

def inspect_case(cid):
    case = get_case(cid)
    with tx() as c:
        tasks = all_rows(c, """SELECT t.*,r.result,r.backend,r.model_version,r.prompt_version
            FROM agent_tasks t LEFT JOIN agent_results r ON t.tenant_id=r.tenant_id AND t.id=r.task_id
            WHERE t.tenant_id=%s AND t.case_id=%s ORDER BY round_no,specialist""", (case['tenant_id'], cid))
        decisions = all_rows(c, 'SELECT * FROM coordination_decisions WHERE tenant_id=%s AND case_id=%s ORDER BY round_no',
                            (case['tenant_id'], cid))
    return {'case': case, 'tasks': tasks, 'coordination_decisions': decisions}

def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='command', required=True)
    q = sub.add_parser('new'); q.add_argument('scenario', choices=SCENARIOS, nargs='?', default='healthy')
    q = sub.add_parser('run'); q.add_argument('id')
    q.add_argument('--backend', choices=list(BACKENDS), default='openai' if openai_key() else 'fixture')
    q.add_argument('--model', default=None)
    q.add_argument('--timeout', type=float, default=60 if openai_key() else 30)
    q = sub.add_parser('show'); q.add_argument('id')
    q = sub.add_parser('submit'); q.add_argument('id'); q.add_argument('--seconds', type=int, default=600)
    q.add_argument('--fault', default='none')
    a = p.parse_args()
    if a.command == 'new':
        result = new_case(a.scenario); print('CASE_ID=' + str(result['id']))
    elif a.command == 'run':
        result = run_case(a.id, a.backend, a.model, a.timeout)
    elif a.command == 'show':
        result = inspect_case(a.id)
    else:
        result = submit_case(a.id, a.seconds, a.fault); print('WORKFLOW_ID=' + str(result['id']))
    print(json.dumps(result, default=str, indent=2))

if __name__ == '__main__':
    main()
