from fastapi.testclient import TestClient
from app.api import create_app
from app.bookings import connect, book
from app.security import hash_password


def test_management_auth_schedule_booking_status_and_revocation(tmp_path):
    path=tmp_path/"api.sqlite"
    db=connect(path)
    with db:
        db.execute("INSERT INTO admins(email,password_hash) VALUES(?,?)",("admin@example.test",hash_password("long-test-password")))
    db.close()
    with TestClient(create_app(path)) as client:
        headers={"Origin":"http://localhost:8001"}
        assert client.get("/api/overview").status_code==401
        assert client.post("/api/login",json={"email":"admin@example.test","password":"long-test-password"},headers=headers).status_code==200
        service=client.post("/api/services",json={"title":"Consultation","duration_minutes":30,"price_kopecks":150000},headers=headers)
        assert service.status_code==201
        payload={"service_id":service.json()["id"],"starts_at":"2099-01-01T10:00:00Z"}
        slot=client.post("/api/slots",json=payload,headers=headers)
        assert slot.status_code==201
        assert client.post("/api/slots",json=payload,headers=headers).status_code==409
        assert client.post("/api/slots",json={**payload,"starts_at":"2099-01-02T10:00:00"},headers=headers).status_code==400
        db=connect(path)
        booking=book(db,101,slot.json()["id"],"Customer",1)
        db.close()
        assert len(client.get("/api/overview").json()["bookings"])==1
        assert client.patch(f"/api/bookings/{booking['id']}",json={"status":"completed"},headers=headers).status_code==200
        assert client.patch(f"/api/bookings/{booking['id']}",json={"status":"cancelled"},headers=headers).status_code==409
        assert client.post("/api/services",json={},headers={"Origin":"https://evil.example"}).status_code==403
        assert client.post("/api/logout",json={},headers=headers).status_code==200
        assert client.get("/api/overview").status_code==401
