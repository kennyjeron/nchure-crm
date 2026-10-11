import os
import hashlib
import hmac
import json
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from fastapi import FastAPI, HTTPException, Depends
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, EmailStr
from psycopg_pool import ConnectionPool, PoolTimeout, TooManyRequests
from psycopg.types.json import Jsonb

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
pool = ConnectionPool(DATABASE_URL, open=False, kwargs={"autocommit": False}, timeout=5, min_size=0, max_size=2, max_waiting=4) if DATABASE_URL else None
security = HTTPBearer(auto_error=False)


@app.exception_handler(PoolTimeout)
@app.exception_handler(TooManyRequests)
async def handle_database_pool_timeout(request, exc):
    # Return an actionable API error instead of Vercel's generic function crash.
    return JSONResponse(
        status_code=503,
        content={"detail": "Database is not reachable or the connection pool is busy. Check DATABASE_URL in Vercel and use the Supabase Transaction Pooler URI."},
    )

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


class ChangePassword(BaseModel):
    current_password: str
    new_password: str


class TeamMemberCreate(BaseModel):
    name: str
    email: EmailStr
    password: str
    role: str


class TeamMemberUpdate(BaseModel):
    name: str
    email: EmailStr
    role: str
    password: str | None = None


TEAM_ROLES = {
    "Founder", "CEO", "CTO", "COO", "Admin", "Team Leader",
    "Sales Manager", "Sales Executive", "Project Manager", "Developer",
    "Designer", "Content Team", "Accountant", "Support Executive", "Staff",
}
ELEVATED_TEAM_ROLES = {"Founder", "CEO", "CTO", "COO", "Admin", "Team Leader"}
TEAM_MANAGERS = {"Founder", "CEO", "Admin"}


@app.on_event("startup")
def startup():
    # Do not block FastAPI startup on a database round-trip. On serverless hosts,
    # a database outage or wrong DATABASE_URL must not turn every route into a 500.
    # Existing founder users are managed in the database; bootstrap is not run on
    # every cold start to avoid lockups and duplicate account races.
    if pool:
        pool.open()


@app.get("/health")
def health():
    database_ok = False
    database_error = None
    if pool:
        try:
            with pool.connection() as conn:
                conn.execute("SELECT 1")
            database_ok = True
        except Exception as exc:
            # Expose only the exception class, never DSN, host credentials, or secrets.
            database_error = type(exc).__name__
    return {
        "ok": True,
        "service": "nchure-crm-api",
        "database_configured": bool(DATABASE_URL),
        "database_connected": database_ok,
        "database_error": database_error,
    }


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


@app.post("/api/auth/change-password")
def change_password(body: ChangePassword, user=Depends(current)):
    if len(body.new_password) < 14:
        raise HTTPException(400, "New password must be at least 14 characters.")
    with db() as conn:
        row = conn.execute(
            "SELECT password_hash FROM public.crm_users WHERE id=%s AND is_active=true",
            (user["sub"],),
        ).fetchone()
        if not row or not verify(row[0], body.current_password):
            raise HTTPException(400, "Current password is incorrect.")
        conn.execute(
            "UPDATE public.crm_users SET password_hash=%s WHERE id=%s",
            (hashpw(body.new_password), user["sub"]),
        )
    return {"ok": True}


@app.post("/api/team-members")
def create_team_member(body: TeamMemberCreate, user=Depends(current)):
    if user.get("role") not in TEAM_MANAGERS:
        raise HTTPException(403, "Only Founder, CEO or Admin can manage team members.")
    name = body.name.strip()
    email = str(body.email).strip().lower()
    role = body.role.strip()
    if not name:
        raise HTTPException(400, "Name is required.")
    if role not in TEAM_ROLES:
        raise HTTPException(400, "Select a valid team role.")
    if user.get("role") != "Founder" and role == "Founder":
        raise HTTPException(403, "Only Founder can assign the Founder role.")
    if len(body.password) < 14:
        raise HTTPException(400, "Password must be at least 14 characters.")
    with db() as conn:
        duplicate = conn.execute(
            "SELECT id FROM public.crm_users WHERE lower(email)=lower(%s)",
            (email,),
        ).fetchone()
        if duplicate:
            raise HTTPException(409, "An account with this email already exists.")
        row = conn.execute(
            "INSERT INTO public.crm_users(name,email,password_hash,role,is_active) "
            "VALUES (%s,%s,%s,%s,true) RETURNING id,name,email,role,is_active",
            (name, email, hashpw(body.password), role),
        ).fetchone()
    return {"id": row[0], "name": row[1], "email": row[2], "role": row[3], "is_active": row[4]}


@app.put("/api/team-members/{member_id}")
def update_team_member(member_id: int, body: TeamMemberUpdate, user=Depends(current)):
    if user.get("role") not in TEAM_MANAGERS:
        raise HTTPException(403, "Only Founder, CEO or Admin can manage team members.")
    name = body.name.strip()
    email = str(body.email).strip().lower()
    role = body.role.strip()
    if not name:
        raise HTTPException(400, "Name is required.")
    if role not in TEAM_ROLES:
        raise HTTPException(400, "Select a valid team role.")
    with db() as conn:
        existing = conn.execute(
            "SELECT id,role FROM public.crm_users WHERE id=%s AND is_active=true",
            (member_id,),
        ).fetchone()
        if not existing:
            raise HTTPException(404, "Team account not found.")
        if user.get("role") != "Founder" and existing[1] == "Founder":
            raise HTTPException(403, "Only Founder can edit the Founder account.")
        if member_id == int(user.get("sub")) and role != existing[1]:
            raise HTTPException(400, "You cannot change your own role.")
        if member_id == int(user.get("sub")) and user.get("role") == "CEO" and body.password:
            raise HTTPException(403, "CEO cannot change their own password from Edit Profile.")
        duplicate = conn.execute(
            "SELECT id FROM public.crm_users WHERE lower(email)=lower(%s) AND id<>%s",
            (email, member_id),
        ).fetchone()
        if duplicate:
            raise HTTPException(409, "An account with this email already exists.")
        if body.password:
            if len(body.password) < 14:
                raise HTTPException(400, "New password must be at least 14 characters.")
            row = conn.execute(
                "UPDATE public.crm_users SET name=%s,email=%s,role=%s,password_hash=%s "
                "WHERE id=%s RETURNING id,name,email,role,is_active",
                (name, email, role, hashpw(body.password), member_id),
            ).fetchone()
        else:
            row = conn.execute(
                "UPDATE public.crm_users SET name=%s,email=%s,role=%s "
                "WHERE id=%s RETURNING id,name,email,role,is_active",
                (name, email, role, member_id),
            ).fetchone()
    return {"id": row[0], "name": row[1], "email": row[2], "role": row[3], "is_active": row[4]}


@app.delete("/api/team-members/{member_id}")
def deactivate_team_member(member_id: int, user=Depends(current)):
    if user.get("role") not in TEAM_MANAGERS:
        raise HTTPException(403, "Only Founder, CEO or Admin can manage team members.")
    if str(member_id) == str(user.get("sub")):
        raise HTTPException(400, "You cannot deactivate the account you are currently using.")
    with db() as conn:
        existing = conn.execute(
            "SELECT role FROM public.crm_users WHERE id=%s AND is_active=true",
            (member_id,),
        ).fetchone()
        if not existing:
            raise HTTPException(404, "Team account not found.")
        if user.get("role") != "Founder" and existing[0] == "Founder":
            raise HTTPException(403, "Only Founder can deactivate the Founder account.")
        conn.execute(
            "UPDATE public.crm_users SET is_active=false WHERE id=%s",
            (member_id,),
        )
    return {"ok": True, "id": member_id, "is_active": False}


@app.get("/api/app-state")
def get_app_state(user=Depends(current)):
    if user.get("role") not in {"Founder", "CEO", "Admin", "Team Leader"}:
        raise HTTPException(403, "Only authorized workspace managers may read workspace state.")
    with db() as conn:
        row = conn.execute(
            "SELECT state, updated_at FROM public.crm_dashboard_state WHERE id=1"
        ).fetchone()
    return {"state": row[0] if row else None, "updated_at": row[1].isoformat() if row else None}


@app.put("/api/app-state")
def put_app_state(body: dict[str, Any], user=Depends(current)):
    if user.get("role") not in {"Founder", "CEO", "Admin", "Team Leader"}:
        raise HTTPException(403, "Only authorized workspace managers may save workspace state.")
    try:
        encoded = json.dumps(body, separators=(",", ":"), ensure_ascii=False)
    except (TypeError, ValueError):
        raise HTTPException(400, "Invalid workspace state.")
    if len(encoded.encode("utf-8")) > 2_000_000:
        raise HTTPException(413, "Workspace state exceeds the 2 MB limit.")
    state_value = json.loads(encoded)
    if not isinstance(state_value, dict):
        raise HTTPException(400, "Workspace state must be an object.")
    # Authentication secrets never belong in the dashboard snapshot.
    if isinstance(state_value.get("users"), list):
        for member in state_value["users"]:
            if isinstance(member, dict):
                for secret_key in ("pass", "password", "password_hash", "token", "access_token"):
                    member.pop(secret_key, None)
    with db() as conn:
        conn.execute(
            """
            INSERT INTO public.crm_dashboard_state (id, state, updated_by, updated_at)
            VALUES (1, %s, %s, now())
            ON CONFLICT (id) DO UPDATE
            SET state=EXCLUDED.state, updated_by=EXCLUDED.updated_by, updated_at=now()
            """,
            (Jsonb(state_value), user["sub"]),
        )
    return {"ok": True}


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
