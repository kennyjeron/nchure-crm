import os
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, EmailStr
from psycopg_pool import ConnectionPool

app = FastAPI(title="NCHURE CRM API", version="1.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[x.strip() for x in os.getenv("CORS_ORIGINS", "").split(",") if x.strip()],
    allow_credentials=False,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

DATABASE_URL = os.getenv("DATABASE_URL") or os.getenv("SUPABASE_DB_URL")
SECRET = os.getenv("JWT_SECRET")
pool = ConnectionPool(DATABASE_URL, open=False, kwargs={"autocommit": False}) if DATABASE_URL else None
security = HTTPBearer(auto_error=False)

MAP = {
    "clients": ["company", "contact", "email", "phone", "status"],
    "leads": ["name", "company", "contact", "status", "priority"],
    "projects": ["name", "client_id", "status", "budget"],
    "tasks": ["title", "status", "priority", "due_date"],
    "invoices": ["number", "client_id", "status", "total"],
    "payments": ["invoice_id", "amount", "method"],
    "expenses": ["title", "amount", "category"],
}
TABLES = {name: "crm_" + name for name in MAP}


def db():
    if not pool:
        raise HTTPException(503, "Database is not configured. Set DATABASE_URL in the hosting environment.")
    return pool.connection()


def hashpw(password: str) -> str:
    salt = secrets.token_bytes(16)
    derived = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 310_000)
    return "pbkdf2_sha256$310000$" + salt.hex() + "$" + derived.hex()


def verify(stored: str, password: str) -> bool:
    try:
        algorithm, rounds, salt_hex, digest_hex = stored.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        derived = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt_hex), int(rounds))
        return hmac.compare_digest(derived.hex(), digest_hex)
    except (ValueError, TypeError):
        return False


def token(user):
    if not SECRET or len(SECRET) < 32:
        raise HTTPException(503, "JWT_SECRET must be configured as a random secret of at least 32 characters.")
    return jwt.encode(
        {"sub": str(user["id"]), "email": user["email"], "role": user["role"],
         "exp": datetime.now(timezone.utc) + timedelta(hours=8)},
        SECRET, algorithm="HS256"
    )


def current(creds: HTTPAuthorizationCredentials = Depends(security)):
    if not creds:
        raise HTTPException(401, "Authentication required")
    if not SECRET or len(SECRET) < 32:
        raise HTTPException(503, "Authentication is not configured.")
    try:
        return jwt.decode(creds.credentials, SECRET, algorithms=["HS256"])
    except jwt.PyJWTError:
        raise HTTPException(401, "Invalid or expired token")


class Login(BaseModel):
    email: EmailStr
    password: str


@app.on_event("startup")
def startup():
    if pool:
        pool.open()
        # Optional first account bootstrap. No hard-coded/default credentials are shipped.
        email = os.getenv("INITIAL_ADMIN_EMAIL", "").strip().lower()
        password = os.getenv("INITIAL_ADMIN_PASSWORD", "")
        name = os.getenv("INITIAL_ADMIN_NAME", "NCHURE Founder").strip() or "NCHURE Founder"
        if email and password:
            if len(password) < 14:
                raise RuntimeError("INITIAL_ADMIN_PASSWORD must be at least 14 characters.")
            with pool.connection() as conn:
                existing = conn.execute("SELECT id FROM public.crm_users WHERE lower(email)=lower(%s)", (email,)).fetchone()
                if not existing:
                    conn.execute(
                        "INSERT INTO public.crm_users(name,email,password_hash,role) VALUES (%s,%s,%s,'Founder')",
                        (name, email, hashpw(password)),
                    )


@app.get("/health")
def health():
    database_ok = False
    if pool:
        try:
            with pool.connection() as conn:
                conn.execute("SELECT 1")
            database_ok = True
        except Exception:
            database_ok = False
    return {"ok": True, "service": "nchure-crm-api", "database_configured": bool(DATABASE_URL), "database_connected": database_ok}


@app.post("/api/auth/login")
def login(x: Login):
    if not SECRET or len(SECRET) < 32:
        raise HTTPException(503, "JWT_SECRET is not configured.")
    with db() as conn:
        user = conn.execute(
            "SELECT id,name,email,password_hash,role,is_active FROM public.crm_users WHERE lower(email)=lower(%s)",
            (x.email,),
        ).fetchone()
    if not user or not user[5] or not verify(user[3], x.password):
        raise HTTPException(401, "Invalid email or password")
    access_token = token({"id": user[0], "email": user[2], "role": user[4]})
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": {"id": user[0], "name": user[1], "email": user[2], "role": user[4]},
    }


@app.get("/api/auth/me")
def me(user=Depends(current)):
    with db() as conn:
        row = conn.execute(
            "SELECT id,name,email,role,is_active FROM public.crm_users WHERE id=%s",
            (user["sub"],),
        ).fetchone()
    if not row or not row[4]:
        raise HTTPException(401, "User not found or disabled")
    return {"id": row[0], "name": row[1], "email": row[2], "role": row[3]}


@app.get("/api/state")
def state(user=Depends(current)):
    return {name: list_rows(name) for name in MAP}


def list_rows(resource):
    with db() as conn:
        cursor = conn.execute(f"SELECT * FROM public.{TABLES[resource]} ORDER BY id DESC LIMIT 1000")
        return [dict(zip([d.name for d in cursor.description], row)) for row in cursor.fetchall()]


def register_routes(resource):
    table = TABLES[resource]
    allowed = MAP[resource]

    @app.get("/api/" + resource)
    def list_endpoint(user=Depends(current), _resource=resource):
        return list_rows(_resource)

    @app.post("/api/" + resource)
    def create_endpoint(body: dict[str, Any], user=Depends(current), _table=table, _allowed=allowed):
        fields = [field for field in _allowed if field in body]
        if not fields:
            raise HTTPException(400, "No writable fields")
        values = [body[field] for field in fields]
        marks = ",".join(["%s"] * len(fields))
        with db() as conn:
            cursor = conn.execute(
                f"INSERT INTO public.{_table} ({','.join(fields)}) VALUES ({marks}) RETURNING *",
                values,
            )
            row = cursor.fetchone()
            return dict(zip([d.name for d in cursor.description], row))

    @app.delete("/api/" + resource + "/{record_id}")
    def delete_endpoint(record_id: int, user=Depends(current), _table=table):
        with db() as conn:
            cursor = conn.execute(f"DELETE FROM public.{_table} WHERE id=%s", (record_id,))
            if cursor.rowcount == 0:
                raise HTTPException(404, "Record not found")
        return {"ok": True}


for resource_name in MAP:
    register_routes(resource_name)
