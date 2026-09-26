"""Four learner boundaries. Reference implementation; starter replaces these bodies."""
from .db import *

def pause_for_approval(c, w):
    """TODO 1: caller owns workflow lock; persist waiting state and task atomically."""
    from .core import new_task
    if w['state'] != 'RECEIVED':
        return
    amount = w['amount_minor']
    role = 'support_lead' if amount <= 750000 else 'finance_manager' if amount <= 2500000 else 'finance_director'
    transition(c, w, 'WAITING_APPROVAL')
    task = new_task(c, w, role, 1)
    audit(c, w, 'approval_requested', details={'task_id': str(task['id']), 'required_role': role})
    emit(c, w, 'approval.requested', task_id=str(task['id']))

def record_decision(c, w, task, who, body):
    """TODO 2: workflow and task already locked, validate before committing authority."""
    command_hash = digest({k: body[k] for k in ('task_id','decision','reason','proposal_version','task_version')})
    previous = one(c, '''SELECT * FROM approval_decisions WHERE tenant_id=%s AND actor_id=%s AND command_key=%s''',
                   (who['tenant_id'],who['id'],body['command_key']))
    if previous:
        if previous['command_hash'] != command_hash:
            raise DomainError(409, 'Command key reused with different intent')
        return previous
    if str(who['id']) == str(w['requester_id']):
        raise DomainError(403, 'Requester cannot approve their own request')
    if who['role'] != task['required_role']:
        raise DomainError(403, 'Current task requires ' + task['required_role'])
    if w['state'] != 'WAITING_APPROVAL' or task['status'] != 'PENDING':
        raise DomainError(409, 'Task is no longer pending')
    if body['proposal_version'] != w['proposal_version'] or body['proposal_version'] != task['proposal_version'] or body['task_version'] != task['version']:
        raise DomainError(409, 'Stale proposal or task version')
    now = one(c, 'SELECT clock_timestamp() AS now')['now']
    if now >= task['due_at']:
        raise DomainError(409, 'Deadline passed; wait for escalation')
    if body['decision'] not in ('approve','reject') or not body['reason'].strip():
        raise DomainError(422, 'Decision and reason required')
    decision = one(c, '''INSERT INTO approval_decisions(tenant_id,id,task_id,actor_id,decision,reason,
        proposal_version,request_id,command_key,command_hash) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *''',
        (w['tenant_id'],uid(),task['id'],who['id'],body['decision'],body['reason'],body['proposal_version'],
         body['request_id'],body['command_key'],command_hash))
    c.execute('''UPDATE approval_tasks SET status=%s,closed_at=clock_timestamp(),version=version+1 WHERE tenant_id=%s AND id=%s''',
              ('APPROVED' if body['decision']=='approve' else 'REJECTED',w['tenant_id'],task['id']))
    c.execute("UPDATE workflow_timers SET status='CANCELLED' WHERE tenant_id=%s AND task_id=%s AND status='PENDING'", (w['tenant_id'],task['id']))
    transition(c,w,'READY_TO_EXECUTE' if body['decision']=='approve' else 'REJECTED')
    audit(c,w,'human_'+body['decision'],who,body['reason'],{'task_id':str(task['id'])},body['request_id'])
    emit(c,w,'approval.accepted' if body['decision']=='approve' else 'workflow.rejected',task_id=str(task['id']),proposal_version=w['proposal_version'])
    return decision

def expire_or_escalate(c, w, task):
    """TODO 3: same workflow-then-task lock order as decision handler."""
    from .core import new_task
    if w['state'] != 'WAITING_APPROVAL' or task['status'] != 'PENDING':
        return False
    if one(c,'SELECT clock_timestamp() AS now')['now'] < task['due_at']:
        return False
    next_role = {'support_lead':'finance_manager','finance_manager':'finance_director'}.get(task['required_role'])
    c.execute('''UPDATE approval_tasks SET status=%s,closed_at=clock_timestamp(),version=version+1 WHERE tenant_id=%s AND id=%s''',
              ('SUPERSEDED' if next_role else 'EXPIRED',w['tenant_id'],task['id']))
    c.execute("UPDATE workflow_timers SET status='FIRED',fired_at=clock_timestamp() WHERE tenant_id=%s AND task_id=%s AND status='PENDING'",(w['tenant_id'],task['id']))
    transition(c,w,'WAITING_APPROVAL' if next_role else 'MANUAL_REVIEW')
    if next_role:
        replacement = new_task(c,w,next_role,task['stage']+1,task['id'])
        audit(c,w,'approval_escalated',details={'old_task':str(task['id']),'new_task':str(replacement['id']),'required_role':next_role})
        emit(c,w,'approval.escalated',task_id=str(replacement['id']))
    else:
        audit(c,w,'approval_expired',reason='Final authority deadline expired; operator owns review')
        emit(c,w,'workflow.manual_review')
    return True

def handle_event_and_recover(c, w, event):
    """TODO 4: commit inbox and execution intent together; no network call here."""
    from .core import new_attempt
    fingerprint = digest(event)
    inserted = one(c, '''INSERT INTO inbox_events(consumer,event_id,tenant_id,workflow_id,schema_version,payload_hash)
        VALUES('workflow',%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING RETURNING event_id''',
        (event['id'],w['tenant_id'],w['id'],event['schema_version'],fingerprint))
    if not inserted:
        previous = one(c,"SELECT * FROM inbox_events WHERE consumer='workflow' AND event_id=%s",(event['id'],))
        if previous['payload_hash'] != fingerprint:
            raise DomainError(409,'Duplicate event ID with changed payload')
        return 'duplicate'
    if event['event_type']=='workflow.submitted' and w['state']=='RECEIVED':
        pause_for_approval(c,w)
        return 'paused'
    if event['event_type']=='approval.accepted':
        task = one(c,'SELECT * FROM approval_tasks WHERE tenant_id=%s AND id=%s', (w['tenant_id'],event['payload'].get('task_id')))
        valid = (task and task['workflow_id']==w['id'] and task['status']=='APPROVED'
                 and event['payload'].get('proposal_version')==w['proposal_version']
                 and event['aggregate_version']==w['version'] and w['state']=='READY_TO_EXECUTE')
        if valid:
            exists = one(c,'SELECT id FROM execution_attempts WHERE tenant_id=%s AND workflow_id=%s', (w['tenant_id'],w['id']))
            if not exists:
                new_attempt(c,w)
                audit(c,w,'execution_scheduled',cause=event['id'])
            return 'scheduled'
        audit(c,w,'stale_event_ignored',details={'event_id':event['id']},cause=event['id'])
    return 'observed'
