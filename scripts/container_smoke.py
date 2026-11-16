import subprocess
import time
import uuid
import httpx

suffix=uuid.uuid4().hex
name,volume="deskline-ci-"+suffix,"deskline-data-"+suffix
created=False


def docker(*args):
    return subprocess.check_output(["docker",*args],text=True).strip()


def ready():
    address=docker("port",name,"8001/tcp").splitlines()[0]
    base="http://"+address
    for _ in range(60):
        try:
            if httpx.get(base+"/api/health",timeout=1).status_code==200:
                return base
        except httpx.HTTPError:
            pass
        time.sleep(.25)
    raise RuntimeError("Container not ready")


docker("volume","create",volume)
try:
    docker("run","-d","--name",name,"-p","127.0.0.1::8001","-v",volume+":/data","deskline-test")
    created=True
    base=ready()
    password=uuid.uuid4().hex
    setup="import sys;from app.bookings import connect;from app.security import hash_password;db=connect('/data/deskline.sqlite');db.execute('INSERT INTO admins(email,password_hash) VALUES(?,?)',('ci@example.test',hash_password(sys.stdin.read())));db.commit();db.close()"
    subprocess.run(["docker","exec","-i",name,"python","-c",setup],input=password,text=True,check=True)
    with httpx.Client(base_url=base,headers={"Origin":"http://localhost:8001"}) as client:
        credentials={"email":"ci@example.test","password":password}
        assert client.post("/api/login",json=credentials).status_code==200
        assert client.post("/api/services",json={"title":"Persistent service","duration_minutes":30,"price_kopecks":150000}).status_code==201
    docker("restart",name)
    base=ready()
    with httpx.Client(base_url=base,headers={"Origin":"http://localhost:8001"}) as client:
        assert client.post("/api/login",json=credentials).status_code==200
        assert client.get("/api/overview").json()["services"][0]["title"]=="Persistent service"
    assert docker("exec",name,"id","-u")=="1000"
    print("Deskline container persistence and non-root smoke passed; no Telegram network used")
except Exception:
    if created:
        print(docker("logs",name))
    raise
finally:
    if created:
        docker("rm","-f",name)
    docker("volume","rm",volume)
