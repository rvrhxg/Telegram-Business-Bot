import os
import subprocess
import sys
import tempfile
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from playwright.sync_api import sync_playwright
from app.bookings import book, connect
from app.security import hash_password

with tempfile.TemporaryDirectory(prefix="deskline-browser-") as temporary:
    path=str(Path(temporary)/"browser.sqlite")
    db=connect(path)
    password="isolated-browser-password"
    with db:
        db.execute("INSERT INTO admins(email,password_hash) VALUES(?,?)",("admin@example.test",hash_password(password)))
        db.execute("INSERT INTO services VALUES(1,'Консультация по проекту',45,250000)")
        for i in range(1,5):
            db.execute("INSERT INTO slots(id,service_id,starts_at) VALUES(?,1,?)",(i,(datetime.now(timezone.utc)+timedelta(days=i)).replace(hour=10,minute=0,second=0,microsecond=0).isoformat()))
    book(db,101,1,"Алексей Морозов",1)
    book(db,102,2,"Мария Соколова",2)
    db.close()
    process=subprocess.Popen([sys.executable,"-m","uvicorn","app.api:create_app","--factory","--host","127.0.0.1","--port","8001"],env={**os.environ,"DATABASE_PATH":path,"APP_ORIGIN":"http://127.0.0.1:8001"})
    try:
        for _ in range(60):
            try:
                urllib.request.urlopen("http://127.0.0.1:8001/api/health",timeout=1)
                break
            except OSError:
                time.sleep(.25)
        else:
            raise RuntimeError("Dashboard did not start")
        Path("screenshots").mkdir(exist_ok=True)
        with sync_playwright() as p:
            browser=p.chromium.launch()
            page=browser.new_page(viewport={"width":1440,"height":1000})
            errors=[]
            page.on("pageerror",lambda error:errors.append(str(error)))
            page.goto("http://127.0.0.1:8001")
            page.get_by_label("Email",exact=True).fill("admin@example.test")
            page.get_by_label("Пароль",exact=True).fill(password)
            page.get_by_role("button",name="Войти →",exact=True).click()
            page.locator("#dashboard").wait_for(state="visible")
            page.screenshot(path="screenshots/dashboard-desktop.png",full_page=True)
            page.get_by_role("button",name="+ Услуга",exact=True).click()
            dialog=page.locator("#editor")
            dialog.get_by_label("Название",exact=True).fill("Разбор бизнес-процессов")
            dialog.get_by_label("Длительность, минут",exact=True).fill("60")
            dialog.get_by_label("Цена, ₽",exact=True).fill("3500")
            dialog.get_by_role("button",name="Сохранить",exact=True).click()
            dialog.wait_for(state="hidden")
            page.locator("#services").get_by_text("Разбор бизнес-процессов",exact=True).wait_for()
            page.get_by_role('button',name='+ Сотрудник',exact=True).click()
            dialog.get_by_label('Имя сотрудника',exact=True).fill('Елена Крылова')
            dialog.get_by_role('button',name='Сохранить',exact=True).click()
            dialog.wait_for(state='hidden')
            page.get_by_role('button',name='+ Время записи',exact=True).click()
            dialog.get_by_label('Сотрудник',exact=True).select_option(label='Елена Крылова')
            dialog.get_by_label('Дата и время (ваш часовой пояс)',exact=True).fill('2099-01-01T10:00')
            dialog.get_by_role('button',name='Сохранить',exact=True).click()
            dialog.wait_for(state='hidden')
            page.locator('#employee-filter').select_option(label='Елена Крылова')
            page.locator('#slots').get_by_text('Елена Крылова',exact=False).wait_for()
            assert page.locator('#bookings .row').count()==0
            page.locator('#employee-filter').select_option('')
            page.locator("#bookings .row").filter(has_text="Алексей Морозов").get_by_role("button",name="Завершить",exact=True).click()
            page.locator("#bookings .row").filter(has_text="Алексей Морозов").get_by_text("Завершено",exact=True).wait_for()
            page.set_viewport_size({"width":390,"height":844})
            page.screenshot(path="screenshots/dashboard-mobile.png",full_page=True)
            assert not errors,errors
            browser.close()
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
