import argparse
import getpass
import os
from datetime import datetime, timedelta, timezone
from .bookings import connect
from .security import hash_password


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--admin-email",required=True)
    parser.add_argument("--demo",action="store_true")
    args=parser.parse_args()
    email=args.admin_email.strip().lower()
    if "@" not in email or len(email)>254:
        raise ValueError("Invalid email")
    password=hash_password(getpass.getpass("New administrator password: "))
    db=connect(os.environ.get("DATABASE_PATH","deskline.sqlite"))
    try:
        with db:
            if db.execute("SELECT 1 FROM admins WHERE email=?",(email,)).fetchone():
                raise ValueError("Administrator already exists")
            db.execute("INSERT INTO admins(email,password_hash) VALUES(?,?)",(email,password))
            if args.demo:
                if db.execute("SELECT count(*) FROM services").fetchone()[0]:
                    raise ValueError("Demo requires empty service catalog")
                service=db.execute("INSERT INTO services(title,duration_minutes,price_kopecks) VALUES(?,?,?)",("Консультация по проекту",45,250000)).lastrowid
                for day in range(1,6):
                    start=(datetime.now(timezone.utc)+timedelta(days=day)).replace(hour=10,minute=0,second=0,microsecond=0)
                    db.execute("INSERT INTO slots(service_id,starts_at) VALUES(?,?)",(service,start.isoformat()))
        print("Setup completed. No Telegram messages were sent.")
    finally:
        db.close()


if __name__=="__main__":
    main()
