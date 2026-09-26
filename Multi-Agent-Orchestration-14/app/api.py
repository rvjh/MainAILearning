import os
import uuid
from pathlib import Path
from fastapi import FastAPI, Depends, Header, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, Field
from .db import *
from . import core

app=FastAPI(title='July: Multi-Agent Enterprise Orchestration',version='2.0')

@app.exception_handler(DomainError)
def domain_error(request:Request,exc:DomainError):
    with tx() as c:
        c.execute('INSERT INTO security_events(id,actor_subject,action,outcome,request_id) VALUES(%s,%s,%s,%s,%s)',
                  (uid(),None,request.url.path,exc.message,uid()))
    return JSONResponse({'detail':exc.message},status_code=exc.status)

def identity(authorization:str=Header(default='')):
    return actor(authorization.removeprefix('Bearer '))

def operator(who=Depends(identity)):
    if who['role']!='operator': raise DomainError(403,'Operator role required')
    return who

class Submit(BaseModel):
    team_case_id: uuid.UUID|None=None
    order_id: uuid.UUID
    amount_minor:int=Field(gt=0,le=100000000)
    idempotency_key:str=Field(min_length=1,max_length=128)
    fault:str='none'
    approval_seconds:int|None=Field(default=None,ge=2,le=3600)

class Decision(BaseModel):
    decision:str
    reason:str=Field(min_length=1,max_length=1000)
    proposal_version:int=Field(ge=1)
    task_version:int=Field(ge=0)
    command_key:str=Field(min_length=1,max_length=128)
    request_id:uuid.UUID=Field(default_factory=uuid.uuid4)

class Operation(BaseModel):
    action:str
    reason:str=Field(min_length=1,max_length=1000)

class Fixture(BaseModel):
    amount_minor:int=Field(default=5000000,gt=0)
    age_days:int=Field(default=5,ge=0,le=100)
    category:str='standard'

@app.get('/',response_class=HTMLResponse)
def ui(): return Path(__file__).with_name('dashboard.html').read_text()

@app.get('/health')
def health():
    with tx() as c: one(c,'SELECT 1 AS ok')
    return {'status':'ok'}

@app.get('/me')
def me(who=Depends(identity)):
    return {k:who[k] for k in ('tenant_id','id','subject','role')}

@app.post('/workflows',status_code=202)
def submit(body:Submit,response:Response,who=Depends(identity)):
    w=core.create_request(who,body.model_dump(mode='json'))
    response.headers['Location']='/workflows/'+str(w['id'])
    return w

@app.get('/workflows')
def workflows(who=Depends(identity)):
    with tx() as c:
        if who['role']=='requester':
            return all_rows(c,'SELECT * FROM workflow_instances WHERE tenant_id=%s AND requester_id=%s ORDER BY created_at DESC LIMIT 100',(who['tenant_id'],who['id']))
        return all_rows(c,'SELECT * FROM workflow_instances WHERE tenant_id=%s ORDER BY created_at DESC LIMIT 100',(who['tenant_id'],))

@app.get('/workflows/{wid}')
def detail(wid:uuid.UUID,who=Depends(identity)):
    with tx() as c:
        w=one(c,'SELECT * FROM workflow_instances WHERE tenant_id=%s AND id=%s',(who['tenant_id'],wid))
        if not w: raise DomainError(404,'Workflow not found in tenant')
        if who['role']=='requester' and who['id']!=w['requester_id']: raise DomainError(403,'Not your workflow')
        result={'workflow':w}
        for name in ('approval_tasks','execution_attempts','audit_events','outbox_events'):
            order='sequence_no' if name=='audit_events' else 'stage' if name=='approval_tasks' else 'attempt_no' if name=='execution_attempts' else 'created_at'
            result[name]=all_rows(c,f'SELECT * FROM {name} WHERE tenant_id=%s AND workflow_id=%s ORDER BY {order}',(who['tenant_id'],wid))
        result['approval_decisions']=all_rows(c,'''SELECT d.* FROM approval_decisions d JOIN approval_tasks t
            ON d.tenant_id=t.tenant_id AND d.task_id=t.id WHERE t.tenant_id=%s AND t.workflow_id=%s''',(who['tenant_id'],wid))
        return result

@app.get('/tasks')
def tasks(who=Depends(identity)):
    with tx() as c:
        return all_rows(c,"SELECT * FROM approval_tasks WHERE tenant_id=%s AND required_role=%s AND status='PENDING' ORDER BY due_at",(who['tenant_id'],who['role']))

@app.post('/tasks/{tid}/decision')
def decision(tid:uuid.UUID,body:Decision,who=Depends(identity)):
    return core.decide(who,tid,body.model_dump(mode='json'))

@app.post('/workflows/{wid}/operate')
def operate(wid:uuid.UUID,body:Operation,who=Depends(operator)):
    if not body.reason.strip(): raise DomainError(422,'Reason required')
    if body.action=='reconcile': return core.reconcile(who['tenant_id'],wid,who,body.reason)
    if body.action=='close': return core.operator_close(who,wid,body.reason)
    raise DomainError(422,'Supported actions: reconcile, close')

@app.get('/audit/{wid}')
def audit_export(wid:uuid.UUID,who=Depends(identity)):
    return detail(wid,who)

@app.get('/metrics')
def metrics(who=Depends(operator)):
    with tx() as c:
        states=all_rows(c,'SELECT state,count(*) AS count FROM workflow_instances WHERE tenant_id=%s GROUP BY state',(who['tenant_id'],))
        overdue=one(c,"SELECT count(*) AS n,COALESCE(EXTRACT(EPOCH FROM clock_timestamp()-min(due_at)),0) AS age FROM approval_tasks WHERE tenant_id=%s AND status='PENDING' AND due_at<clock_timestamp()",(who['tenant_id'],))
        outbox=one(c,'SELECT count(*) AS n,COALESCE(EXTRACT(EPOCH FROM clock_timestamp()-min(created_at)),0) AS age FROM outbox_events WHERE tenant_id=%s AND published_at IS NULL',(who['tenant_id'],))
        review=one(c,"SELECT COALESCE(EXTRACT(EPOCH FROM clock_timestamp()-min(updated_at)),0) AS age FROM workflow_instances WHERE tenant_id=%s AND state IN ('MANUAL_REVIEW','RECONCILING')",(who['tenant_id'],))
    return {'states':states,'overdue_approvals':overdue,'unpublished_events':outbox,'oldest_exception_seconds':review['age']}

@app.post('/lab/orders')
def fixture(body:Fixture,who=Depends(identity)):
    if os.getenv('ENABLE_LAB_FAULTS')!='1': raise DomainError(404,'Lab endpoint disabled')
    if body.category not in ('standard','personalized','gift_card','consumed_digital'): raise DomainError(422,'Invalid category')
    with tx() as c:
        return one(c,'''INSERT INTO orders(tenant_id,id,customer_id,delivered_at,amount_minor,currency,category)
            VALUES(%s,%s,%s,clock_timestamp()-(%s * interval '1 day'),%s,'INR',%s) RETURNING *''',
            (who['tenant_id'],uid(),who['id'],body.age_days,body.amount_minor,body.category))

@app.post('/lab/redeliver/{wid}')
def redeliver(wid:uuid.UUID,who=Depends(operator)):
    if os.getenv('ENABLE_LAB_FAULTS')!='1': raise DomainError(404,'Lab endpoint disabled')
    with tx() as c:
        w=lock_workflow(c,who['tenant_id'],wid)
        rows=all_rows(c,"UPDATE outbox_events SET published_at=NULL WHERE tenant_id=%s AND workflow_id=%s AND event_type='approval.accepted' RETURNING id",(who['tenant_id'],wid))
        audit(c,w,'lab_redelivery_requested',who,'Classroom duplicate delivery drill')
        return {'redelivered':[r['id'] for r in rows]}

@app.post('/lab/provider-recover/{wid}')
def restore_provider(wid:uuid.UUID,who=Depends(operator)):
    if os.getenv('ENABLE_LAB_FAULTS')!='1': raise DomainError(404,'Lab endpoint disabled')
    import httpx
    with tx() as c: w=lock_workflow(c,who['tenant_id'],wid)
    r=httpx.post(core.erp_url()+'/lab/restore',headers=core.erp_headers(),timeout=3,
                 json={'tenant_id':str(who['tenant_id']),'operation_key':core.operation_key(w)})
    r.raise_for_status()
    with tx() as c:
        current=lock_workflow(c,who['tenant_id'],wid)
        audit(c,current,'lab_provider_restored',who,'Cleared injected status-service fault')
    return r.json()
