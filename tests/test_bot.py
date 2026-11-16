import asyncio
from datetime import datetime, timezone
from aiogram import Bot
from aiogram.client.session.base import BaseSession
from aiogram.methods import SendMessage
from aiogram.types import Update, Message, Chat
from app.bot import create_dispatcher
from app.bookings import connect


class CapturedSession(BaseSession):
    def __init__(self):
        super().__init__()
        self.sent = []

    async def close(self):
        pass

    async def make_request(self, bot, method, timeout=None):
        assert isinstance(method, SendMessage), f"Unexpected network method: {type(method)}"
        self.sent.append(method)
        return Message(message_id=len(self.sent), date=datetime.now(timezone.utc), chat=Chat(id=int(method.chat_id), type="private"), text=method.text)

    async def stream_content(self, *args, **kwargs):
        raise AssertionError("Network download is forbidden in this test")
        yield b""


def test_real_dispatcher_handles_booking_replay_and_owner_cancel(tmp_path):
    path = tmp_path / "bot.sqlite"
    db = connect(path)
    with db:
        db.execute("INSERT INTO services VALUES(1,'Консультация',30,150000)")
        db.execute("INSERT INTO slots VALUES(1,1,'2099-01-01T10:00:00+00:00')")
    db.close()

    async def scenario():
        transport = CapturedSession()
        bot = Bot("123456789:" + "A" * 35, session=transport)
        dispatcher = create_dispatcher(path)
        async def feed(update_id, user, command):
            update = Update.model_validate({"update_id": update_id, "message": {"message_id": update_id, "date": 1700000000, "chat": {"id": user, "type": "private"}, "from": {"id": user, "is_bot": False, "first_name": "Customer"}, "text": command, "entities": [{"type": "bot_command", "offset": 0, "length": len(command.split()[0])}]}})
            await dispatcher.feed_update(bot, update)
            return transport.sent[-1].text
        try:
            assert "Deskline" in await feed(1,101,"/start")
            assert "Консультация" in await feed(2,101,"/services")
            assert "/book 1" in await feed(3,101,"/slots")
            assert "подтверждена" in await feed(4,101,"/book 1")
            assert "подтверждена" in await feed(4,101,"/book 1")
            assert "Не удалось" in await feed(5,102,"/book 1")
            assert "не найдена" in await feed(6,102,"/cancel 1")
            assert "Подтверждено" in await feed(7,101,"/mine")
            assert "отменена" in await feed(8,101,"/cancel 1")
            assert "подтверждена" in await feed(9,102,"/book 1")
            assert all(m.chat_id in {101,102} for m in transport.sent)
        finally:
            await bot.session.close()
    asyncio.run(scenario())
