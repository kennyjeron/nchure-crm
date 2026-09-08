import os
from datetime import datetime, timedelta, timezone
from typing import Any
import jwt
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, EmailStr
from psycopg_pool import ConnectionPool

app=FastAPI(title='NCHURE CRM API',version='1.0.0')
app.add_middleware(CORSMiddleware,allow_origins=['*'],allow_credentials=True,allow_methods=['*'],allow_headers=['*'])
DATABASE_URL=os.getenv('DATABASE_URL') or os.getenv('SUPABASE_DB_URL')
SECRET=os.getenv('JWT_SECRET','change-this-in-production')
pool=ConnectionPool(DATABASE_URL,open=False) if DATABASE_URL else None
security=HTTPBearer(auto_error=False)

SCHEMA='''create table if not exists users(id bigserial primary key,name text not null,email text unique not null,password_hash text not null,role text not null default 'Admin',created_at timestamptz default now());
create table if not exists clients(id bigserial primary key,company text,contact text,email text,phone text,status text default 'Active',created_at timestamptz default now());
create table if not exists leads(id bigserial primary key,name text,company text,contact text,status text default 'New',priority text default 'Medium',created_at timestamptz default now());
create table if not exists projects(id bigserial primary key,name text,client_id bigint,status text default 'Planning',budget numeric default 0,created_at timestamptz default now());
create table if not exists tasks(id bigserial primary key,title text,status text default 'Pending',priority text default 'Medium',due_date text,created_at timestamptz default now());
create table if not exists invoices(id bigserial primary key,number text,client_id bigint,status text default 'Draft',total numeric default 0,created_at timestamptz default now());
create table if not exists payments(id bigserial primary key,invoice_id bigint,amount numeric default 0,method text,created_at timestamptz default now());
create table if not exists expenses(id bigserial primary key,title text,amount numeric default 0,category text,created_at timestamptz default now());'''

def db():
 if not pool: raise HTTPException(500,'DATABASE_URL is not configured')
 return pool.connection()
@app.on_event('startup')
def startup():
 if pool:
  pool.open()
  with pool.connection() as c:c.execute(SCHEMA)

def token(user): return jwt.encode({'sub':str(user['id']),'email':user['email'],'role':user['role'],'exp':datetime.now(timezone.utc)+timedelta(hours=12)},SECRET,algorithm='HS256')
def current(creds:HTTPAuthorizationCredentials=Depends(security)):
 if not creds: raise HTTPException(401,'Authentication required')
 try:return jwt.decode(creds.credentials,SECRET,algorithms=['HS256'])
 except jwt.PyJWTError:raise HTTPException(401,'Invalid or expired token')

class Login(BaseModel): email:EmailStr; password:str
class AnyBody(BaseModel): data:dict[str,Any]={}

def verify(stored,pw):
 import hashlib,hmac
 if stored.startswith('sha256$'): return hmac.compare_digest(stored.split('$',1)[1],hashlib.sha256(pw.encode()).hexdigest())
 return hmac.compare_digest(stored,pw)

def hashpw(pw):
 import hashlib;return 'sha256$'+hashlib.sha256(pw.encode()).hexdigest()

@app.get('/health')
def health():return {'ok':True,'service':'nchure-crm-api','database':bool(DATABASE_URL)}
@app.post('/api/auth/login')
def login(x:Login):
 with db() as c:
  u=c.execute('select id,name,email,password_hash,role from users where lower(email)=lower(%s)',(x.email,)).fetchone()
  if not u or not verify(u[3],x.password): raise HTTPException(401,'Invalid email or password')
  return {'access_token':token({'id':u[0],'email':u[2],'role':u[4]}),'token_type':'bearer','user':{'id':u[0],'name':u[1],'email':u[2],'role':u[4]}}
@app.get('/api/auth/me')
def me(u=Depends(current)):
 with db() as c:
  x=c.execute('select id,name,email,role from users where id=%s',(u['sub'],)).fetchone()
  if not x: raise HTTPException(401,'User not found')
  return {'id':x[0],'name':x[1],'email':x[2],'role':x[3]}

MAP={'clients':['company','contact','email','phone','status'],'leads':['name','company','contact','status','priority'],'projects':['name','client_id','status','budget'],'tasks':['title','status','priority','due_date'],'invoices':['number','client_id','status','total'],'payments':['invoice_id','amount','method'],'expenses':['title','amount','category']}
@app.get('/api/state')
def state(u=Depends(current)):
 return {k:list_rows(k) for k in MAP}
def list_rows(r):
 with db() as c:return [dict(zip([d.name for d in c.description],row)) for row in c.execute('select * from '+r+' order by id desc').fetchall()]

def routes(r):
 @app.get('/api/'+r)
 def ls(u=Depends(current)):return list_rows(r)
 @app.post('/api/'+r)
 def create(body:dict,u=Depends(current)):
  fs=[f for f in MAP[r] if f in body]
  if not fs: raise HTTPException(400,'No writable fields')
  vals=[body[f] for f in fs]; marks=','.join(['%s']*len(fs))
  with db() as c:
   row=c.execute(f"insert into {r} ({','.join(fs)}) values ({marks}) returning *",vals).fetchone();return dict(zip([d.name for d in c.description],row))
 @app.delete('/api/'+r+'/{id}')
 def delete(id:int,u=Depends(current)):
  with db() as c:c.execute('delete from '+r+' where id=%s',(id,))
  return {'ok':True}
for _r in MAP: routes(_r)

@app.post('/api/seed')
def seed(u=Depends(current)):
 if u.get('role') not in ('Founder','Admin'): raise HTTPException(403,'Admin access required')
 accounts=[('Jero','jero@nchure.com','Founder','jero123'),('Amar','amar@nchure.com','Founder','amar123'),('Ashin','ashin@nchure.com','Admin','ashin123')]
 with db() as c:
  for n,e,r,p in accounts:c.execute('insert into users(name,email,password_hash,role) values(%s,%s,%s,%s) on conflict(email) do update set name=excluded.name,password_hash=excluded.password_hash,role=excluded.role',(n,e,hashpw(p),r))
 return {'ok':True,'accounts':[x[1] for x in accounts]}
