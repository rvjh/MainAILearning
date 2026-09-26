import os
from datetime import timedelta
import httpx
from .db import *

POLICY={'eligibility_days':45,'thresholds_minor':[750000,2500000],'excluded':['personalized','gift_card','consumed_digital'],'self_approval':False}
FAULTS={'none','lost_response','crash_after_refund','transient_once','permanent','unknown_status'}

def new_task(c,w,role,stage,supersedes=None):
    seconds=int(w['proposal'].get('approval_seconds',os.getenv('APPROVAL_SECONDS','180')))
    task=one(c,'''INSERT INTO approval_tasks(tenant_id,id,workflow_id,stage,required_role,proposal_version,status,due_at,supersedes_id)
        VALUES(%s,%s,%s,%s,%s,%s,'PENDING',clock_timestamp()+(%s * interval '1 second'),%s) RETURNING *''',
        (w['tenant_id'],uid(),w['id'],stage,role,w['proposal_version'],seconds,supersedes))
    c.execute('''INSERT INTO workflow_timers(tenant_id,id,workflow_id,task_id,kind,due_at,status)
        VALUES(%s,%s,%s,%s,'approval_deadline',%s,'PENDING')''',(w['tenant_id'],uid(),w['id'],task['id'],task['due_at']))
    return task

def create_request(who,body):
    if who['role'] not in ('requester','finance_manager'):
        raise DomainError(403,'This persona cannot submit requests')
    if body['fault'] not in FAULTS: raise DomainError(422,'Unknown scenario')
    if os.getenv('ENABLE_LAB_FAULTS')!='1' and (body['fault']!='none' or body.get('approval_seconds')):
        raise DomainError(403,'Lab controls disabled')
    rh=digest({**body,'requester_id':str(who['id'])})
    with tx() as c:
        # Serializes same-tenant key creation even when no workflow row exists yet.
        c.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))',(str(who['tenant_id'])+body['idempotency_key'],))
        existing=one(c,'SELECT * FROM workflow_instances WHERE tenant_id=%s AND idempotency_key=%s',(who['tenant_id'],body['idempotency_key']))
        if existing:
            if existing['request_hash']!=rh: raise DomainError(409,'Idempotency key reused with changed request')
            return existing
        team_case = None
        if os.getenv('REQUIRE_TEAM_CASE')=='1' or body.get('team_case_id'):
            team_case = one(c,'SELECT * FROM agent_cases WHERE tenant_id=%s AND id=%s FOR UPDATE',
                            (who['tenant_id'],body.get('team_case_id')))
            if not team_case or team_case['requester_id']!=who['id']:
                raise DomainError(403,'A prepared team case owned by the requester is required')
            if team_case['status']!='READY':
                raise DomainError(409,'Team case is not ready for human approval')
            if str(team_case['order_id'])!=body['order_id'] or team_case['amount_minor']!=body['amount_minor']:
                raise DomainError(409,'Request differs from the team proposal')
        c.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))',('order:'+str(who['tenant_id'])+body['order_id'],))
        order=one(c,'SELECT * FROM orders WHERE tenant_id=%s AND id=%s',(who['tenant_id'],body['order_id']))
        if not order: raise DomainError(404,'Order not found in tenant')
        if order['customer_id']!=who['id']: raise DomainError(403,'Order not assigned to this requester')
        if one(c,'SELECT id FROM workflow_instances WHERE tenant_id=%s AND order_id=%s',(who['tenant_id'],order['id'])):
            raise DomainError(409,'This order already has a refund workflow')
        if body['amount_minor']>order['amount_minor']: raise DomainError(422,'Refund exceeds order value')
        proposal={'summary':'Customer requests refund; evidence verified against ACME policy v2.',
                  'evidence':['acme_refund_policy_v2','order:'+str(order['id'])],
                  'fault':body['fault'],'approval_seconds':body.get('approval_seconds') or int(os.getenv('APPROVAL_SECONDS','180'))}
        if team_case:
            proposal['team_case_id']=str(team_case['id'])
            proposal['team_snapshot']=team_case['snapshot']
            proposal['team_snapshot_hash']=digest(team_case['snapshot'])
            proposal['summary']='Specialist evidence collected; human authorization still required.'
        w=one(c,'''INSERT INTO workflow_instances(tenant_id,id,order_id,requester_id,idempotency_key,request_hash,state,
            amount_minor,currency,proposal,policy_version,policy_snapshot)
            VALUES(%s,%s,%s,%s,%s,%s,'RECEIVED',%s,'INR',%s,'acme-v2+lab-v1',%s) RETURNING *''',
            (who['tenant_id'],uid(),order['id'],who['id'],body['idempotency_key'],rh,body['amount_minor'],Jsonb(proposal),Jsonb(POLICY)))
        audit(c,w,'request_created',who,details={'amount_minor':w['amount_minor']})
        if team_case:
            c.execute("UPDATE agent_cases SET status='SUBMITTED',workflow_id=%s WHERE tenant_id=%s AND id=%s",
                      (w['id'],who['tenant_id'],team_case['id']))
        age=one(c,'SELECT clock_timestamp() AS now')['now']-order['delivered_at']
        if age>timedelta(days=45) or age.total_seconds()<0 or order['category'] in POLICY['excluded']:
            transition(c,w,'REJECTED'); audit(c,w,'policy_rejected',reason='Order outside eligibility or excluded category')
        else: emit(c,w,'workflow.submitted')
        return w

def decide(who,task_id,body):
    from .exercises import record_decision
    with tx() as c:
        c.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))',('decision:'+str(who['tenant_id'])+str(who['id'])+body['command_key'],))
        task=one(c,'SELECT * FROM approval_tasks WHERE tenant_id=%s AND id=%s',(who['tenant_id'],task_id))
        if not task: raise DomainError(404,'Task not found in tenant')
        w=lock_workflow(c,who['tenant_id'],task['workflow_id'])
        task=one(c,'SELECT * FROM approval_tasks WHERE tenant_id=%s AND id=%s FOR UPDATE',(who['tenant_id'],task_id))
        return record_decision(c,w,task,who,{**body,'task_id':str(task_id)})

def schedule_tick():
    from .exercises import expire_or_escalate
    with tx() as c:
        due=all_rows(c,"SELECT * FROM workflow_timers WHERE status='PENDING' AND due_at<=clock_timestamp() ORDER BY due_at LIMIT 50")
    for timer in due:
        with tx() as c:
            w=lock_workflow(c,timer['tenant_id'],timer['workflow_id'])
            task=one(c,'SELECT * FROM approval_tasks WHERE tenant_id=%s AND id=%s FOR UPDATE',(timer['tenant_id'],timer['task_id']))
            expire_or_escalate(c,w,task)

def consume(event):
    from .exercises import handle_event_and_recover
    if event.get('schema_version')!=1: raise DomainError(422,'Unsupported event schema')
    with tx() as c:
        w=lock_workflow(c,event['tenant_id'],event['workflow_id'])
        return handle_event_and_recover(c,w,event)

def operation_key(w):
    return f"refund:{w['tenant_id']}:{w['id']}:v{w['proposal_version']}"

def new_attempt(c,w,delay=0):
    n=one(c,'SELECT COALESCE(max(attempt_no),0)+1 AS n FROM execution_attempts WHERE tenant_id=%s AND workflow_id=%s',(w['tenant_id'],w['id']))['n']
    return one(c,'''INSERT INTO execution_attempts(tenant_id,id,workflow_id,operation_key,attempt_no,status,available_at)
        VALUES(%s,%s,%s,%s,%s,'PENDING',clock_timestamp()+(%s * interval '1 second')) RETURNING *''',
        (w['tenant_id'],uid(),w['id'],operation_key(w),n,delay))

def claim():
    with tx() as c:
        # Claim workflow first to keep the global lock order consistent.
        w=one(c,'''SELECT w.* FROM workflow_instances w WHERE w.state IN ('READY_TO_EXECUTE','RETRY_WAIT')
            AND EXISTS(SELECT 1 FROM execution_attempts e WHERE e.tenant_id=w.tenant_id AND e.workflow_id=w.id
            AND e.status='PENDING' AND e.available_at<=clock_timestamp())
            ORDER BY w.updated_at FOR UPDATE OF w SKIP LOCKED LIMIT 1''')
        if not w: return None
        e=one(c,'''UPDATE execution_attempts SET status='RUNNING',lease_owner=%s,
            lease_until=clock_timestamp()+(%s * interval '1 second'),fence=fence+1,started_at=clock_timestamp()
            WHERE tenant_id=%s AND workflow_id=%s AND status='PENDING' RETURNING *''',
            (os.getenv('HOSTNAME','local-worker'),int(os.getenv('LEASE_SECONDS','8')),w['tenant_id'],w['id']))
        transition(c,w,'EXECUTING'); audit(c,w,'execution_claimed',details={'attempt':e['attempt_no'],'operation_key':e['operation_key']})
        return w,e

def finish(w,e,outcome,receipt=None,error=None):
    with tx() as c:
        current=lock_workflow(c,w['tenant_id'],w['id'])
        attempt=one(c,'SELECT * FROM execution_attempts WHERE tenant_id=%s AND id=%s FOR UPDATE',(w['tenant_id'],e['id']))
        if attempt['status']!='RUNNING' or attempt['fence']!=e['fence'] or current['state']!='EXECUTING':
            return False
        status={'success':'SUCCEEDED','retry':'RETRY','unknown':'UNKNOWN','failed':'FAILED'}[outcome]
        c.execute('''UPDATE execution_attempts SET status=%s,finished_at=clock_timestamp(),provider_receipt_id=%s,
            error_class=%s,lease_until=NULL WHERE tenant_id=%s AND id=%s''',(status,receipt,error,w['tenant_id'],e['id']))
        state={'success':'COMPLETED','retry':'RETRY_WAIT','unknown':'RECONCILING','failed':'MANUAL_REVIEW'}[outcome]
        if outcome=='retry':
            if e['attempt_no']>=3: state='MANUAL_REVIEW'
            else: new_attempt(c,current,delay=2**e['attempt_no'])
        transition(c,current,state)
        audit(c,current,'execution_'+outcome,details={'attempt':e['attempt_no'],'receipt':receipt,'error':error})
        emit(c,current,'workflow.'+state.lower())
        return True

def erp_headers(): return {'Authorization':'Bearer '+os.getenv('ERP_TOKEN','lab-erp-secret')}
def erp_url(): return os.getenv('ERP_URL','http://localhost:8078')

def execute_one():
    claimed=claim()
    if not claimed: return False
    w,e=claimed
    try:
        response=httpx.post(erp_url()+'/refunds',headers=erp_headers(),timeout=3,
            json={'tenant_id':str(w['tenant_id']),'operation_key':e['operation_key'],'order_id':str(w['order_id']),
                  'amount_minor':w['amount_minor'],'currency':'INR','fault':w['proposal']['fault'],'attempt':e['attempt_no']})
        if response.status_code==200:
            receipt=response.json()['receipt_id']
            if w['proposal']['fault']=='crash_after_refund' and e['attempt_no']==1:
                log('injected_crash_after_external_commit',workflow_id=w['id'],receipt=receipt)
                os._exit(77)
            finish(w,e,'success',receipt)
        elif response.status_code==503 and response.json().get('effect')=='not_started':
            finish(w,e,'retry',error='transient_confirmed_before_effect')
        elif response.status_code in (400,409,422): finish(w,e,'failed',error='permanent_provider_rejection')
        else: finish(w,e,'unknown',error='ambiguous_provider_response')
    except httpx.RequestError:
        finish(w,e,'unknown',error='response_lost')
    return True

def recover_expired():
    with tx() as c:
        candidates=all_rows(c,"SELECT * FROM execution_attempts WHERE status='RUNNING' AND lease_until<clock_timestamp() LIMIT 50")
    for e in candidates:
        with tx() as c:
            w=lock_workflow(c,e['tenant_id'],e['workflow_id'])
            changed=one(c,"""UPDATE execution_attempts SET status='UNKNOWN',fence=fence+1,error_class='lease_expired',
                finished_at=clock_timestamp() WHERE tenant_id=%s AND id=%s AND status='RUNNING'
                AND lease_until<clock_timestamp() RETURNING id""",(e['tenant_id'],e['id']))
            if changed:
                transition(c,w,'RECONCILING'); audit(c,w,'lease_expired',details={'attempt':e['attempt_no']})

def reconcile(tenant,wid,who=None,reason=None):
    with tx() as c:
        w=lock_workflow(c,tenant,wid)
        if w['state'] not in ('RECONCILING','MANUAL_REVIEW'): return w
        if not one(c,'SELECT id FROM execution_attempts WHERE tenant_id=%s AND workflow_id=%s',(tenant,wid)):
            raise DomainError(409,'No external execution exists to reconcile')
    # External lookup runs outside DB transaction. State/version rechecked afterward.
    try:
        r=httpx.get(erp_url()+'/refunds/status',params={'tenant_id':str(tenant),'operation_key':operation_key(w)},headers=erp_headers(),timeout=3)
    except httpx.RequestError:
        return w
    with tx() as c:
        current=lock_workflow(c,tenant,wid)
        if current['version']!=w['version']: return current
        if r.status_code==200:
            receipt=r.json()['receipt_id']
            c.execute("UPDATE execution_attempts SET status='SUCCEEDED',provider_receipt_id=%s WHERE tenant_id=%s AND workflow_id=%s AND status='UNKNOWN'",(receipt,tenant,wid))
            transition(c,current,'COMPLETED'); audit(c,current,'receipt_reconciled',who,reason,{'receipt':receipt})
            emit(c,current,'workflow.completed')
        elif r.status_code==404:
            # Provider contract: authoritative absence plus same-key idempotent POST.
            latest=one(c,'SELECT * FROM execution_attempts WHERE tenant_id=%s AND workflow_id=%s ORDER BY attempt_no DESC LIMIT 1',(tenant,wid))
            if latest['attempt_no']<3 and latest['status']=='UNKNOWN':
                transition(c,current,'RETRY_WAIT'); new_attempt(c,current,2)
                audit(c,current,'absence_confirmed_retry_scheduled',who,reason)
            elif current['state']!='MANUAL_REVIEW':
                transition(c,current,'MANUAL_REVIEW'); audit(c,current,'retry_budget_exhausted')
        else:
            if current['state']!='MANUAL_REVIEW':
                transition(c,current,'MANUAL_REVIEW'); audit(c,current,'reconciliation_unavailable',reason='Provider cannot establish outcome')
        return current

def recovery_tick():
    recover_expired()
    with tx() as c:
        rows=all_rows(c,"SELECT tenant_id,id FROM workflow_instances WHERE state='RECONCILING' LIMIT 20")
    for w in rows: reconcile(w['tenant_id'],w['id'])

def operator_close(who,wid,reason):
    with tx() as c:
        w=lock_workflow(c,who['tenant_id'],wid)
        if w['state']!='MANUAL_REVIEW': raise DomainError(409,'Only manual-review cases can close')
        attempts=one(c,"SELECT count(*) AS n FROM execution_attempts WHERE tenant_id=%s AND workflow_id=%s AND status!='FAILED'",(who['tenant_id'],wid))['n']
        if attempts: raise DomainError(409,'External execution exists; reconcile before closure')
        transition(c,w,'CLOSED'); audit(c,w,'operator_closed',who,reason)
        return w
