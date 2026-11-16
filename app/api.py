import os
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, StrictInt
from .bookings import connect, available_slots
from .security import hash_password, verify_password, new_token, token_hash


class Login(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=12, max_length=128)


class ServiceInput(BaseModel):
    title: str = Field(min_length=1, max_length=100)
    duration_minutes: StrictInt = Field(ge=5, le=480)
    price_kopecks: StrictInt = Field(ge=0, le=100000000)


class SlotInput(BaseModel):
    service_id: StrictInt = Field(gt=0)
    employee_id: StrictInt = Field(default=1, gt=0)
    starts_at: datetime


class EmployeeInput(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class StatusInput(BaseModel):
    status: str


def create_app(path=None, origin=None):
    path = path or os.environ.get("DATABASE_PATH", "deskline.sqlite")
    origin = origin or os.environ.get("APP_ORIGIN", "http://localhost:8001")
    parsed = urlsplit(origin)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.path or parsed.query or parsed.fragment or parsed.username:
        raise ValueError("APP_ORIGIN must contain only HTTP(S) origin")
    secure = os.environ.get("ENVIRONMENT") == "production"
    if secure and parsed.scheme != "https":
        raise ValueError("HTTPS required")
    db = connect(path)
    db.close()
    app = FastAPI(title="Deskline management API")
    dummy = hash_password("dummy-password-value")
    attempts = {}

    @app.middleware("http")
    async def security(request: Request, call_next):
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            if request.headers.get("origin") != origin:
                return JSONResponse({"detail": "Origin rejected"}, status_code=403)
            if request.headers.get("content-type", "").split(";")[0] != "application/json":
                return JSONResponse({"detail": "JSON required"}, status_code=415)
            chunks, size = [], 0
            async for chunk in request.stream():
                size += len(chunk)
                if size > 32768:
                    return JSONResponse({"detail": "Request too large"}, status_code=413)
                chunks.append(chunk)
            request._body = b"".join(chunks)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Cache-Control"] = "no-store"
        if request.url.path in {"/", "/app.js", "/style.css"}:
            response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self'; frame-ancestors 'none'; base-uri 'none'"
        return response

    def admin(request, db):
        token = request.cookies.get("session", "")
        row = db.execute("SELECT a.id,a.email FROM admin_sessions s JOIN admins a ON a.id=s.admin_id WHERE s.token_hash=? AND s.expires_at>?", (token_hash(token),int(time.time()))).fetchone()
        if not row:
            raise HTTPException(401,"Authentication required")
        return dict(row)

    @app.get("/api/health")
    def health():
        return {"status":"ok"}

    @app.post("/api/login")
    def login(data: Login, request: Request, response: Response):
        now = int(time.time())
        for key in list(attempts):
            if attempts[key][1] < now:
                del attempts[key]
        key = request.client.host
        count, until = attempts.get(key,(0,now+60))
        attempts[key]=(count+1,until)
        if count>=15:
            raise HTTPException(429,"Try again later")
        db = connect(path)
        try:
            row = db.execute("SELECT * FROM admins WHERE email=?",(data.email.lower().strip(),)).fetchone()
            if not verify_password(data.password,row["password_hash"] if row else dummy) or not row:
                raise HTTPException(401,"Invalid credentials")
            token=new_token()
            with db:
                db.execute("DELETE FROM admin_sessions WHERE expires_at<?",(now,))
                db.execute("INSERT INTO admin_sessions VALUES(?,?,?)",(token_hash(token),row["id"],now+86400))
            response.set_cookie("session",token,httponly=True,secure=secure,samesite="strict",max_age=86400)
            return {"email":row["email"]}
        finally:
            db.close()

    @app.get("/api/me")
    def me(request: Request):
        db=connect(path)
        try:
            return admin(request,db)
        finally:
            db.close()

    @app.post("/api/logout")
    def logout(request: Request,response: Response):
        db=connect(path)
        try:
            admin(request,db)
            with db:
                db.execute("DELETE FROM admin_sessions WHERE token_hash=?",(token_hash(request.cookies["session"]),))
            response.delete_cookie("session",httponly=True,secure=secure,samesite="strict")
            return {"ok":True}
        finally:
            db.close()

    @app.get("/api/overview")
    def overview(request: Request):
        db=connect(path)
        try:
            admin(request,db)
            return {
                'available_slot_ids': [slot['id'] for slot in available_slots(db, 200)],
                'employees': [dict(r) for r in db.execute('SELECT * FROM employees ORDER BY id')],
                'services': [dict(r) for r in db.execute('SELECT * FROM services ORDER BY id')],
                'slots': [dict(r) for r in db.execute('SELECT s.*,v.title,e.name AS employee_name FROM slots s JOIN services v ON v.id=s.service_id JOIN employees e ON e.id=s.employee_id ORDER BY s.starts_at DESC LIMIT 200')],
                'bookings': [dict(r) for r in db.execute('SELECT b.*,s.starts_at,s.employee_id,v.title,e.name AS employee_name FROM bookings b JOIN slots s ON s.id=b.slot_id JOIN services v ON v.id=s.service_id JOIN employees e ON e.id=s.employee_id ORDER BY b.id DESC LIMIT 200')],
            }
        finally:
            db.close()

    @app.post("/api/services",status_code=201)
    def service(data: ServiceInput,request: Request):
        db=connect(path)
        try:
            admin(request,db)
            with db:
                cursor=db.execute("INSERT INTO services(title,duration_minutes,price_kopecks) VALUES(?,?,?)",(data.title.strip(),data.duration_minutes,data.price_kopecks))
            return {"id":cursor.lastrowid,**data.model_dump()}
        finally:
            db.close()

    @app.post("/api/slots",status_code=201)
    def slot(data: SlotInput,request: Request):
        import sqlite3
        if data.starts_at.tzinfo is None or data.starts_at<=datetime.now(timezone.utc):
            raise HTTPException(400,"Future timezone-aware time required")
        db=connect(path)
        try:
            admin(request,db)
            try:
                with db:
                    cursor=db.execute("INSERT INTO slots(service_id,starts_at,employee_id) VALUES(?,?,?)",(data.service_id,data.starts_at.astimezone(timezone.utc).isoformat(),data.employee_id))
                return {"id":cursor.lastrowid}
            except sqlite3.IntegrityError:
                raise HTTPException(409,"Service missing or time already exists")
        finally:
            db.close()

    @app.post('/api/employees', status_code=201)
    def employee(data: EmployeeInput, request: Request):
        db = connect(path)
        try:
            admin(request, db)
            if not data.name.strip():
                raise HTTPException(400, 'Name required')
            with db:
                cursor = db.execute('INSERT INTO employees(name) VALUES(?)', (data.name.strip(),))
            return {'id': cursor.lastrowid, 'name': data.name.strip()}
        finally:
            db.close()

    @app.patch("/api/bookings/{booking_id}")
    def booking_status(booking_id: int,data: StatusInput,request: Request):
        if data.status not in {"cancelled","completed"}:
            raise HTTPException(400,"Invalid status")
        db=connect(path)
        try:
            admin(request,db)
            with db:
                db.execute("BEGIN IMMEDIATE")
                row=db.execute("SELECT * FROM bookings WHERE id=?",(booking_id,)).fetchone()
                if not row:
                    raise HTTPException(404,"Booking not found")
                if row["status"]!=data.status and row["status"]!="confirmed":
                    raise HTTPException(409,"Booking already closed")
                db.execute("UPDATE bookings SET status=? WHERE id=?",(data.status,booking_id))
            return {"id":booking_id,"status":data.status}
        finally:
            db.close()

    static=Path(__file__).resolve().parent.parent/"public"
    if static.exists():
        app.mount("/",StaticFiles(directory=static,html=True),name="dashboard")
    return app
