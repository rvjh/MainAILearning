"""Independent local provider. SQLite is its ledger, never the workflow checkpoint."""
import hashlib
import json
import os
import sqlite3
import time
import uuid
from pathlib import Path
from fastapi import FastAPI, Depends, Header, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

app=FastAPI(title='ACME simulated refund provider')
PATH=os.getenv('ERP_DB','/tmp/week7-refunds.db')
Path(PATH).parent.mkdir(parents=True,exist_ok=True)
with sqlite3.connect(PATH) as c:
    c.executescript('''CREATE TABLE IF NOT EXISTS refund_ledger(
        tenant_id TEXT NOT NULL, operation_key TEXT NOT NULL, request_hash TEXT NOT NULL,
        receipt_id TEXT NOT NULL UNIQUE, order_id TEXT NOT NULL, amount_minor INTEGER NOT NULL CHECK(amount_minor>0),
        currency TEXT NOT NULL CHECK(currency='INR'), status TEXT NOT NULL,
        fault TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY(tenant_id,operation_key));''')

def authorized(authorization: str=Header(default='')):
    if authorization!='Bearer '+os.getenv('ERP_TOKEN','lab-erp-secret'): raise HTTPException(401,'Provider authentication required')

class Refund(BaseModel):
    tenant_id: uuid.UUID
    operation_key: str=Field(min_length=1,max_length=200)
    order_id: uuid.UUID
    amount_minor: int=Field(gt=0)
    currency: str='INR'
    fault: str='none'
    attempt: int=1

@app.get('/health')
def health(): return {'status':'ok','ledger':'independent SQLite volume'}

@app.post('/refunds',dependencies=[Depends(authorized)])
def refund(body:Refund):
    fault=body.fault if os.getenv('ENABLE_LAB_FAULTS')=='1' else 'none'
    if fault=='permanent': return JSONResponse({'error':'account closed','effect':'not_started'},status_code=422)
    if fault=='transient_once' and body.attempt==1:
        return JSONResponse({'error':'provider busy','effect':'not_started'},status_code=503)
    payload={k:str(v) for k,v in body.model_dump().items() if k not in ('fault','attempt')}
    rh=hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest()
    with sqlite3.connect(PATH,timeout=10) as c:
        c.row_factory=sqlite3.Row
        c.execute('BEGIN IMMEDIATE')
        existing=c.execute('SELECT * FROM refund_ledger WHERE tenant_id=? AND operation_key=?',(str(body.tenant_id),body.operation_key)).fetchone()
        if existing:
            if existing['request_hash']!=rh: raise HTTPException(409,'Key reused for a different refund')
            return dict(existing)
        receipt=str(uuid.uuid4())
        c.execute('''INSERT INTO refund_ledger(tenant_id,operation_key,request_hash,receipt_id,order_id,amount_minor,currency,status,fault)
            VALUES(?,?,?,?,?,?,?,'SETTLED',?)''',(str(body.tenant_id),body.operation_key,rh,receipt,str(body.order_id),body.amount_minor,body.currency,fault))
    # Commit has happened. Slow response deliberately exceeds the caller's timeout.
    if fault in ('lost_response','unknown_status'): time.sleep(5)
    return {'receipt_id':receipt,'status':'SETTLED','operation_key':body.operation_key}

@app.get('/refunds/status',dependencies=[Depends(authorized)])
def status(tenant_id:uuid.UUID,operation_key:str):
    with sqlite3.connect(PATH) as c:
        c.row_factory=sqlite3.Row
        r=c.execute('SELECT * FROM refund_ledger WHERE tenant_id=? AND operation_key=?',(str(tenant_id),operation_key)).fetchone()
    if not r: raise HTTPException(404,'Authoritative absence')
    if r['fault']=='unknown_status': raise HTTPException(503,'Status service unavailable for this injected scenario')
    return dict(r)

@app.get('/ledger',dependencies=[Depends(authorized)])
def ledger():
    with sqlite3.connect(PATH) as c:
        c.row_factory=sqlite3.Row
        return [dict(r) for r in c.execute('SELECT * FROM refund_ledger ORDER BY created_at DESC')]

class Restore(BaseModel):
    tenant_id: uuid.UUID
    operation_key: str

@app.post('/lab/restore',dependencies=[Depends(authorized)])
def restore(body:Restore):
    if os.getenv('ENABLE_LAB_FAULTS')!='1': raise HTTPException(404,'Lab controls disabled')
    with sqlite3.connect(PATH) as c:
        changed=c.execute("UPDATE refund_ledger SET fault='none' WHERE tenant_id=? AND operation_key=?",(str(body.tenant_id),body.operation_key)).rowcount
    return {'restored':bool(changed)}
