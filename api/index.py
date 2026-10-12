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
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
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
        claims = jwt.decode(creds.credentials, SECRET, algorithms=["HS256"])
    except jwt.PyJWTError:
        raise HTTPException(401, "Invalid or expired token")
    # Resolve the account on every request. Deleting/disabling an account
    # invalidates existing JWTs immediately instead of waiting eight hours.
    with db() as conn:
        row = conn.execute(
            "SELECT id,name,email,role,is_active FROM public.crm_users WHERE id=%s",
            (claims.get("sub"),),
        ).fetchone()
    if not row or not row[4]:
        raise HTTPException(401, "Account was deleted or disabled. Please sign in again.")
    return {"sub": str(row[0]), "name": row[1], "email": row[2], "role": row[3]}


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


@app.get("/api/team-members")
def list_team_members(user=Depends(current)):
    if user.get("role") not in TEAM_MANAGERS:
        raise HTTPException(403, "Only Founder, CEO or Admin can manage team members.")
    with db() as conn:
        rows = conn.execute(
            "SELECT id,name,email,role,is_active FROM public.crm_users "
            "WHERE is_active=true ORDER BY id"
        ).fetchall()
    return [
        {"id": row[0], "name": row[1], "email": row[2], "role": row[3], "is_active": row[4]}
        for row in rows
    ]


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
        existing = conn.execute(
            "SELECT id,is_active FROM public.crm_users WHERE lower(email)=lower(%s)",
            (email,),
        ).fetchone()
        if existing and existing[1]:
            raise HTTPException(409, "An account with this email already exists.")
        if existing:
            # Recover legacy disabled accounts created before permanent deletion
            # was implemented. New deletions remove the row entirely.
            row = conn.execute(
                "UPDATE public.crm_users SET name=%s,email=%s,password_hash=%s,role=%s,"
                "is_active=true WHERE id=%s RETURNING id,name,email,role,is_active",
                (name, email, hashpw(body.password), role, existing[0]),
            ).fetchone()
        else:
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
def delete_team_member(member_id: int, user=Depends(current)):
    if user.get("role") not in TEAM_MANAGERS:
        raise HTTPException(403, "Only Founder, CEO or Admin can manage team members.")
    if str(member_id) == str(user.get("sub")):
        raise HTTPException(400, "You cannot delete the account you are currently using.")
    with db() as conn:
        existing = conn.execute(
            "SELECT role FROM public.crm_users WHERE id=%s AND is_active=true",
            (member_id,),
        ).fetchone()
        if not existing:
            raise HTTPException(404, "Team account not found.")
        if user.get("role") != "Founder" and existing[0] == "Founder":
            raise HTTPException(403, "Only Founder can delete the Founder account.")
        # The dashboard snapshot references the last editor. Clear that reference
        # first so the foreign key does not prevent a permanent account deletion.
        conn.execute(
            "UPDATE public.crm_dashboard_state SET updated_by=NULL WHERE updated_by=%s",
            (member_id,),
        )
        conn.execute("DELETE FROM public.crm_users WHERE id=%s", (member_id,))
    return {"ok": True, "id": member_id, "deleted": True}


def _as_list(value):
    return value if isinstance(value, list) else []


def _norm(value):
    if value is None:
        return ""
    if isinstance(value, (dict, list, tuple, set)):
        return ""
    return str(value).strip().lower()


def _matches(value, targets):
    targets = {_norm(target) for target in targets if _norm(target)}
    if isinstance(value, (list, tuple, set)):
        return any(_matches(item, targets) for item in value)
    if isinstance(value, dict):
        return any(_matches(value.get(key), targets) for key in ("id", "name", "email", "value"))
    return _norm(value) in targets if _norm(value) else False


def _identity_targets(user):
    return [user.get("name"), user.get("email"), user.get("sub")]


def _record_has_identity(record, user):
    if not isinstance(record, dict):
        return False
    fields = (
        "assignedTo", "assigned_to", "assignee", "assigneeName", "assignee_name",
        "owner", "ownerName", "owner_name", "createdBy", "created_by",
        "uploadedBy", "uploaded_by", "from", "sender", "author", "organizer",
        "user", "recipient", "to", "pm", "projectManager", "project_manager",
    )
    if any(_matches(record.get(field), _identity_targets(user)) for field in fields):
        return True
    for field in ("participants", "attendees", "assignees", "team", "members"):
        if _matches(record.get(field), _identity_targets(user)):
            return True
    return False


def _id_of(record, *fields):
    if not isinstance(record, dict):
        return None
    for field in fields:
        value = record.get(field)
        if value is not None and value != "":
            return str(value)
    return None


def _safe_profile(profile, user):
    profile = profile if isinstance(profile, dict) else {}
    allowed = ("id", "authId", "name", "email", "role", "dept", "phone", "skills", "joined", "clientId")
    result = {key: profile[key] for key in allowed if key in profile}
    result.setdefault("id", str(user.get("sub", "")))
    result.setdefault("authId", int(user["sub"]) if str(user.get("sub", "")).isdigit() else None)
    result.setdefault("name", user.get("name", ""))
    result.setdefault("email", user.get("email", ""))
    result.setdefault("role", user.get("role", "Staff"))
    return result


def _profile_for_state(state, user):
    email = _norm(user.get("email"))
    sub = str(user.get("sub", ""))
    for profile in _as_list(state.get("users")):
        if not isinstance(profile, dict):
            continue
        if _norm(profile.get("email")) == email or str(profile.get("authId", profile.get("id", ""))) == sub:
            return profile
    return {}


def _client_id_for_user(state, user, profile):
    client_id = profile.get("clientId") if isinstance(profile, dict) else None
    if client_id not in (None, ""):
        return str(client_id)
    email = _norm(user.get("email"))
    for client in _as_list(state.get("clients")):
        if isinstance(client, dict) and _norm(client.get("email")) == email:
            return str(client.get("id"))
    return None


def _safe_settings(state):
    settings = state.get("settings") if isinstance(state.get("settings"), dict) else {}
    return {
        "company": settings.get("company", "NCHURE"),
        "tagline": settings.get("tagline", "Business Growth Infrastructure"),
        "currency": settings.get("currency", "₹"),
    }


def _task_assigned_to_user(task, user):
    if not isinstance(task, dict):
        return False
    return (
        _matches(task.get("assignedTo"), [user.get("name"), user.get("email")])
        or _matches(task.get("assignedToId"), [user.get("sub")])
        or _matches(task.get("assignee"), _identity_targets(user))
    )


def _project_ids_for_user(state, user):
    projects = [
        row for row in _as_list(state.get("projects"))
        if isinstance(row, dict) and _record_has_identity(row, user)
    ]
    tasks = [row for row in _as_list(state.get("tasks")) if _task_assigned_to_user(row, user)]
    project_ids = {
        str(_id_of(row, "id")) for row in projects if _id_of(row, "id") is not None
    }
    project_ids.update(
        str(_id_of(row, "projectId", "project_id"))
        for row in tasks if _id_of(row, "projectId", "project_id") is not None
    )
    return project_ids


def _worker_state(state, user):
    profile = _safe_profile(_profile_for_state(state, user), user)
    project_ids = _project_ids_for_user(state, user)
    tasks = [row for row in _as_list(state.get("tasks")) if _task_assigned_to_user(row, user)]
    projects = [
        row for row in _as_list(state.get("projects"))
        if isinstance(row, dict) and (
            _record_has_identity(row, user) or str(_id_of(row, "id")) in project_ids
        )
    ]
    client_ids = {
        str(_id_of(row, "clientId", "client_id")) for row in projects
        if _id_of(row, "clientId", "client_id") is not None
    }
    clients = [
        row for row in _as_list(state.get("clients"))
        if isinstance(row, dict) and str(_id_of(row, "id")) in client_ids
    ]
    # Support staff need the support queue; other employees only see tickets
    # assigned to them or attached to one of their projects.
    if user.get("role") == "Support Executive":
        tickets = [row for row in _as_list(state.get("tickets")) if isinstance(row, dict)]
        ticket_client_ids = {
            str(_id_of(row, "clientId", "client_id")) for row in tickets
            if _id_of(row, "clientId", "client_id") is not None
        }
        client_ids.update(ticket_client_ids)
        clients = [
            row for row in _as_list(state.get("clients"))
            if isinstance(row, dict) and str(_id_of(row, "id")) in client_ids
        ]
    else:
        tickets = [
            row for row in _as_list(state.get("tickets")) if isinstance(row, dict) and (
                _record_has_identity(row, user)
                or str(_id_of(row, "projectId", "project_id")) in project_ids
            )
        ]
    meetings = [
        row for row in _as_list(state.get("meetings")) if isinstance(row, dict) and (
            _record_has_identity(row, user)
            or str(_id_of(row, "projectId", "project_id")) in project_ids
            or str(_id_of(row, "clientId", "client_id")) in client_ids
        )
    ]
    messages = [
        row for row in _as_list(state.get("messages")) if isinstance(row, dict) and (
            _record_has_identity(row, user)
            or str(_id_of(row, "clientId", "client_id")) in client_ids
        )
    ]
    documents = [
        row for row in _as_list(state.get("documents")) if isinstance(row, dict) and (
            _matches(row.get("uploadedBy"), [user.get("name"), user.get("email")])
            or _matches(row.get("assignedTo"), _identity_targets(user))
            or str(_id_of(row, "projectId", "project_id")) in project_ids
            or str(_id_of(row, "clientId", "client_id")) in client_ids
        )
    ]
    milestones = [
        row for row in _as_list(state.get("milestones")) if isinstance(row, dict) and
        str(_id_of(row, "projectId", "project_id")) in project_ids
    ]
    activity = [
        row for row in _as_list(state.get("audit")) if isinstance(row, dict) and
        _matches(row.get("user"), [user.get("name"), user.get("email")])
    ]
    ai_chats = [
        row for row in _as_list(state.get("aiChats")) if isinstance(row, dict) and
        _record_has_identity(row, user)
    ]
    notifications = [
        row for row in _as_list(state.get("notifications")) if isinstance(row, dict) and
        _record_has_identity(row, user)
    ]
    return {
        "settings": _safe_settings(state),
        "users": [profile],
        "clients": clients,
        "projects": projects,
        "milestones": milestones,
        "tasks": tasks,
        "tickets": tickets,
        "documents": documents,
        "meetings": meetings,
        "messages": messages,
        "audit": activity,
        "aiChats": ai_chats,
        "notifications": notifications,
    }


def _client_state(state, user):
    profile = _profile_for_state(state, user)
    client_id = _client_id_for_user(state, user, profile)
    safe_profile = _safe_profile(profile, user)
    if client_id is not None:
        safe_profile["clientId"] = client_id
    clients = [
        row for row in _as_list(state.get("clients")) if isinstance(row, dict)
        and client_id is not None and str(_id_of(row, "id")) == client_id
    ]
    project_rows = [
        row for row in _as_list(state.get("projects")) if isinstance(row, dict)
        and client_id is not None and str(_id_of(row, "clientId", "client_id")) == client_id
    ]
    project_ids = {str(_id_of(row, "id")) for row in project_rows if _id_of(row, "id") is not None}
    milestones = [
        row for row in _as_list(state.get("milestones")) if isinstance(row, dict)
        and str(_id_of(row, "projectId", "project_id")) in project_ids
    ]
    tasks = [
        row for row in _as_list(state.get("tasks")) if isinstance(row, dict)
        and (
            str(_id_of(row, "clientId", "client_id")) == str(client_id)
            or str(_id_of(row, "projectId", "project_id")) in project_ids
        )
    ]
    quotations = [
        row for row in _as_list(state.get("quotations")) if isinstance(row, dict)
        and str(_id_of(row, "clientId", "client_id")) == str(client_id)
    ]
    invoices = [
        row for row in _as_list(state.get("invoices")) if isinstance(row, dict)
        and str(_id_of(row, "clientId", "client_id")) == str(client_id)
    ]
    invoice_ids = {str(_id_of(row, "id")) for row in invoices if _id_of(row, "id") is not None}
    payments = [
        row for row in _as_list(state.get("payments")) if isinstance(row, dict) and (
            str(_id_of(row, "clientId", "client_id")) == str(client_id)
            or str(_id_of(row, "invoiceId", "invoice_id")) in invoice_ids
        )
    ]
    related = {}
    related["tickets"] = [
        row for row in _as_list(state.get("tickets")) if isinstance(row, dict)
        and str(_id_of(row, "clientId", "client_id")) == str(client_id)
    ]
    related["documents"] = [
        row for row in _as_list(state.get("documents")) if isinstance(row, dict)
        and (
            str(_id_of(row, "clientId", "client_id")) == str(client_id)
            or str(_id_of(row, "projectId", "project_id")) in project_ids
        )
    ]
    related["approvals"] = [
        row for row in _as_list(state.get("approvals")) if isinstance(row, dict)
        and (
            str(_id_of(row, "clientId", "client_id")) == str(client_id)
            or str(_id_of(row, "projectId", "project_id")) in project_ids
        )
    ]
    related["meetings"] = [
        row for row in _as_list(state.get("meetings")) if isinstance(row, dict)
        and (
            str(_id_of(row, "clientId", "client_id")) == str(client_id)
            or str(_id_of(row, "projectId", "project_id")) in project_ids
        )
    ]
    related["messages"] = [
        row for row in _as_list(state.get("messages")) if isinstance(row, dict)
        and str(_id_of(row, "clientId", "client_id")) == str(client_id)
    ]
    return {
        "settings": _safe_settings(state),
        "users": [safe_profile],
        "clients": clients,
        "projects": project_rows,
        "milestones": milestones,
        "tasks": tasks,
        "quotations": quotations,
        "invoices": invoices,
        "payments": payments,
        "tickets": related["tickets"],
        "documents": related["documents"],
        "approvals": related["approvals"],
        "meetings": related["meetings"],
        "messages": related["messages"],
        "notifications": [],
        "audit": [],
        "aiChats": [],
    }


def _owned_merge(existing, incoming, is_owner, create_allowed=False, update_fields=None):
    rows = [dict(row) for row in _as_list(existing) if isinstance(row, dict)]
    index = {str(row.get("id")): pos for pos, row in enumerate(rows) if row.get("id") is not None}
    for candidate in _as_list(incoming):
        if not isinstance(candidate, dict):
            continue
        record_id = str(candidate.get("id", ""))
        if record_id and record_id in index:
            pos = index[record_id]
            stored = rows[pos]
            if is_owner(stored):
                if update_fields is None:
                    for key, value in candidate.items():
                        if key != "id":
                            stored[key] = value
                else:
                    for key in update_fields:
                        if key in candidate:
                            stored[key] = candidate[key]
        elif create_allowed and is_owner(candidate):
            rows.append(dict(candidate))
            if record_id:
                index[record_id] = len(rows) - 1
    return rows


def _read_full_state(conn):
    row = conn.execute("SELECT state FROM public.crm_dashboard_state WHERE id=1").fetchone()
    value = row[0] if row else {}
    return value if isinstance(value, dict) else {}


def _merge_limited_state(full_state, incoming, user):
    # Non-manager updates are merged into the full snapshot only for records
    # they own. This prevents a partial worker/client snapshot from overwriting
    # another user's records or writing hidden finance/team data.
    state = dict(full_state)
    profile = _profile_for_state(full_state, user)
    if user.get("role") == "Client":
        client_id = _client_id_for_user(full_state, user, profile)
        own_message = lambda row: (
            client_id is not None
            and str(_id_of(row, "clientId", "client_id")) == str(client_id)
            and _matches(row.get("from"), [user.get("name"), user.get("email")])
            and str(row.get("role", "Client")) == "Client"
        )
        own_ticket = lambda row: (
            client_id is not None
            and str(_id_of(row, "clientId", "client_id")) == str(client_id)
        )
        own_approval = lambda row: (
            client_id is not None
            and str(_id_of(row, "clientId", "client_id")) == str(client_id)
        )
        if "messages" in incoming:
            state["messages"] = _owned_merge(
                state.get("messages"), incoming.get("messages"), own_message, True,
                ["text", "time"]
            )
        if "tickets" in incoming:
            state["tickets"] = _owned_merge(
                state.get("tickets"), incoming.get("tickets"), own_ticket, True,
                ["comments", "status", "resolvedAt"]
            )
        if "approvals" in incoming:
            state["approvals"] = _owned_merge(
                state.get("approvals"), incoming.get("approvals"), own_approval, False,
                ["status", "feedback", "version", "uploadedAt", "clientFeedback"]
            )
        return state

    project_ids = _project_ids_for_user(full_state, user)
    client_ids = {
        str(_id_of(row, "clientId", "client_id")) for row in _as_list(full_state.get("projects"))
        if isinstance(row, dict) and str(_id_of(row, "id")) in project_ids
        and _id_of(row, "clientId", "client_id") is not None
    }
    task_owner = lambda row: _task_assigned_to_user(row, user)
    if "tasks" in incoming:
        state["tasks"] = _owned_merge(
            state.get("tasks"), incoming.get("tasks"), task_owner, False,
            ["status", "actHours", "comments", "attachments", "workNotes", "updatedAt"]
        )
    own_message = lambda row: (
        _matches(row.get("from"), [user.get("name"), user.get("email")])
        and (
            _id_of(row, "clientId", "client_id") is None
            or str(_id_of(row, "clientId", "client_id")) in client_ids
        )
    )
    if "messages" in incoming:
        state["messages"] = _owned_merge(
            state.get("messages"), incoming.get("messages"), own_message, True,
            ["text", "time", "read"]
        )
    own_meeting = lambda row: (
        _record_has_identity(row, user)
        and (
            _id_of(row, "projectId", "project_id") is None
            or str(_id_of(row, "projectId", "project_id")) in project_ids
        )
    )
    if "meetings" in incoming:
        state["meetings"] = _owned_merge(
            state.get("meetings"), incoming.get("meetings"), own_meeting, True,
            ["title", "date", "time", "participants", "link", "agenda", "notes", "actions"]
        )
    own_ticket = lambda row: (
        _matches(row.get("assignedTo"), [user.get("name"), user.get("email")])
        or str(_id_of(row, "projectId", "project_id")) in project_ids
    )
    if "tickets" in incoming:
        state["tickets"] = _owned_merge(
            state.get("tickets"), incoming.get("tickets"), own_ticket, False,
            ["status", "comments", "resolvedAt", "updatedAt"]
        )
    own_document = lambda row: (
        _matches(row.get("uploadedBy"), [user.get("name"), user.get("email")])
        and (
            _id_of(row, "projectId", "project_id") is None
            or str(_id_of(row, "projectId", "project_id")) in project_ids
        )
    )
    if "documents" in incoming:
        state["documents"] = _owned_merge(
            state.get("documents"), incoming.get("documents"), own_document, True,
            ["name", "folder", "version", "uploadedAt", "size"]
        )
    own_audit = lambda row: _matches(row.get("user"), [user.get("name"), user.get("email")])
    if "audit" in incoming:
        state["audit"] = _owned_merge(state.get("audit"), incoming.get("audit"), own_audit, True, [])
    own_ai_chat = lambda row: _record_has_identity(row, user)
    if "aiChats" in incoming:
        state["aiChats"] = _owned_merge(
            state.get("aiChats"), incoming.get("aiChats"), own_ai_chat, True, None
        )
    return state


@app.get("/api/app-state")
def get_app_state(user=Depends(current)):
    with db() as conn:
        full_state = _read_full_state(conn)
    if user.get("role") in ELEVATED_TEAM_ROLES:
        return {"state": full_state, "updated_at": None}
    if user.get("role") == "Client":
        safe_state = _client_state(full_state, user)
    else:
        safe_state = _worker_state(full_state, user)
    return {"state": safe_state, "updated_at": None}


@app.put("/api/app-state")
def put_app_state(body: dict[str, Any], user=Depends(current)):
    try:
        encoded = json.dumps(body, separators=(",", ":"), ensure_ascii=False)
    except (TypeError, ValueError):
        raise HTTPException(400, "Invalid workspace state.")
    if len(encoded.encode("utf-8")) > 2_000_000:
        raise HTTPException(413, "Workspace state exceeds the 2 MB limit.")
    incoming = json.loads(encoded)
    if not isinstance(incoming, dict):
        raise HTTPException(400, "Workspace state must be an object.")
    if isinstance(incoming.get("users"), list):
        for member in incoming["users"]:
            if isinstance(member, dict):
                for secret_key in ("pass", "password", "password_hash", "token", "access_token"):
                    member.pop(secret_key, None)
    with db() as conn:
        if user.get("role") in ELEVATED_TEAM_ROLES:
            new_state = incoming
        else:
            full_state = _read_full_state(conn)
            new_state = _merge_limited_state(full_state, incoming, user)
        conn.execute(
            """
            INSERT INTO public.crm_dashboard_state (id, state, updated_by, updated_at)
            VALUES (1, %s, %s, now())
            ON CONFLICT (id) DO UPDATE
            SET state=EXCLUDED.state, updated_by=EXCLUDED.updated_by, updated_at=now()
            """,
            (Jsonb(new_state), user["sub"]),
        )
    return {"ok": True}


@app.get("/api/state")
def state(user=Depends(current)):
    if user.get("role") not in ELEVATED_TEAM_ROLES:
        raise HTTPException(403, "This API is reserved for workspace managers.")
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
        if user.get("role") not in ELEVATED_TEAM_ROLES:
            raise HTTPException(403, "This API is reserved for workspace managers.")
        return list_rows(_resource)

    @app.post("/api/" + resource)
    def create_endpoint(body: dict[str, Any], user=Depends(current), _table=table, _allowed=allowed):
        if user.get("role") not in ELEVATED_TEAM_ROLES:
            raise HTTPException(403, "This API is reserved for workspace managers.")
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
        if user.get("role") not in ELEVATED_TEAM_ROLES:
            raise HTTPException(403, "This API is reserved for workspace managers.")
        with db() as conn:
            cursor = conn.execute(f"DELETE FROM public.{_table} WHERE id=%s", (record_id,))
            if cursor.rowcount == 0:
                raise HTTPException(404, "Record not found")
        return {"ok": True}


for resource_name in MAP:
    register_routes(resource_name)
