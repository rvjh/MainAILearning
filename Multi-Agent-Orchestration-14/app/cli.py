"""CLI commands used verbatim in the facilitator script. All calls go through HTTP."""
import argparse
import json
import os
import time
import uuid
import urllib.request
import urllib.error

def call(method,path,body=None,role='requester',tenant='acme',base=None):
    base=base or os.getenv('API_URL','http://localhost:8000')
    req=urllib.request.Request(base+path,data=json.dumps(body).encode() if body is not None else None,method=method,
        headers={'Authorization':f'Bearer {tenant}-{role}-token','Content-Type':'application/json'})
    try:
        with urllib.request.urlopen(req,timeout=15) as r: return json.load(r)
    except urllib.error.HTTPError as e:
        raise RuntimeError(f'HTTP {e.code}: {e.read().decode()}') from e

def wait(wid,states=('COMPLETED','REJECTED','MANUAL_REVIEW'),timeout=40):
    end=time.monotonic()+timeout; last=None
    while time.monotonic()<end:
        d=call('GET','/workflows/'+wid,role='operator')
        s=d['workflow']['state']
        if s!=last: print('STATE',s,flush=True);last=s
        if s in states:return d
        time.sleep(.4)
    raise RuntimeError('Timed out; durable workflow remains inspectable: '+wid)

def submit(fault='none',seconds=180,amount=1800000,role='requester'):
    o=call('POST','/lab/orders',{'amount_minor':max(amount,5000000)},role)
    w=call('POST','/workflows',{'order_id':o['id'],'amount_minor':amount,'idempotency_key':str(uuid.uuid4()),'fault':fault,'approval_seconds':seconds},role)
    print('WORKFLOW_ID='+w['id'],flush=True)
    return w

def approve(wid,role=None,decision='approve',reason='Verified order evidence and exact refund amount'):
    d=call('GET','/workflows/'+wid,role='operator')
    t=next(t for t in d['approval_tasks'] if t['status']=='PENDING')
    return call('POST','/tasks/'+t['id']+'/decision',{'decision':decision,'reason':reason,'proposal_version':t['proposal_version'],
                'task_version':t['version'],'command_key':str(uuid.uuid4())},role or t['required_role'])

def main():
    p=argparse.ArgumentParser(); s=p.add_subparsers(dest='cmd',required=True)
    n=s.add_parser('new');n.add_argument('--fault',default='none');n.add_argument('--seconds',type=int,default=180);n.add_argument('--amount',type=int,default=1800000)
    for name in ('show','wait','approve','reject','audit','redeliver','provider-recover'):
        x=s.add_parser(name);x.add_argument('id')
        if name in ('approve','reject'):x.add_argument('--role');x.add_argument('--reason',default='Verified order evidence and policy')
    x=s.add_parser('operate');x.add_argument('id');x.add_argument('action',choices=['reconcile','close']);x.add_argument('--reason',required=True)
    s.add_parser('metrics');s.add_parser('ledger')
    x=s.add_parser('demo');x.add_argument('scenario',choices=['healthy','lost_response','transient_once','permanent','unknown_status','crash_after_refund'])
    a=p.parse_args();result=None
    if a.cmd=='new': result=submit(a.fault,a.seconds,a.amount)
    elif a.cmd in ('show','audit'): result=call('GET',('/audit/' if a.cmd=='audit' else '/workflows/')+a.id,role='operator')
    elif a.cmd=='wait':result=wait(a.id)
    elif a.cmd in ('approve','reject'):result=approve(a.id,a.role,a.cmd,a.reason)
    elif a.cmd=='redeliver':result=call('POST','/lab/redeliver/'+a.id,{},'operator')
    elif a.cmd=='provider-recover':result=call('POST','/lab/provider-recover/'+a.id,{},'operator')
    elif a.cmd=='operate':result=call('POST','/workflows/'+a.id+'/operate',{'action':a.action,'reason':a.reason},'operator')
    elif a.cmd=='metrics':result=call('GET','/metrics',role='operator')
    elif a.cmd=='ledger':
        req=urllib.request.Request(os.getenv('ERP_URL','http://localhost:8078')+'/ledger',headers={'Authorization':'Bearer '+os.getenv('ERP_TOKEN','lab-erp-secret')})
        with urllib.request.urlopen(req) as r:result=json.load(r)
    elif a.cmd=='demo':
        w=submit('none' if a.scenario=='healthy' else a.scenario)
        wait(w['id'],('WAITING_APPROVAL',));approve(w['id'])
        if a.scenario=='crash_after_refund':
            print('Worker will exit 77. Restart worker, then use wait with the workflow ID.');return
        result=wait(w['id'])
    print(json.dumps(result,indent=2))

if __name__=='__main__':main()
