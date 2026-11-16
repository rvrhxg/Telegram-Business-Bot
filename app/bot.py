import asyncio
import os
from aiogram import Bot, Dispatcher, Router
from aiogram.filters import Command
from aiogram.types import Message, Update
from .bookings import BookingConflict, book, cancel, connect, available_slots


def create_dispatcher(path):
    router = Router()

    async def query(sql, params=()):
        def work():
            db = connect(path)
            try:
                return [dict(row) for row in db.execute(sql, params)]
            finally:
                db.close()
        return await asyncio.to_thread(work)

    @router.message(Command("start", "help"))
    async def start(message: Message):
        await message.answer("Deskline — запись на услуги.\n/services — услуги\n/slots — свободное время\n/book ID — записаться\n/mine — мои записи\n/cancel ID — отменить запись")

    @router.message(Command("services"))
    async def services(message: Message):
        rows = await query("SELECT * FROM services ORDER BY id LIMIT 50")
        await message.answer("\n".join(f"{r['id']}. {r['title']} · {r['duration_minutes']} мин · {r['price_kopecks']/100:.2f} ₽" for r in rows) or "Услуги пока не добавлены.")

    @router.message(Command("slots"))
    async def slots(message: Message):
        def work():
            db = connect(path)
            try:
                return available_slots(db)
            finally:
                db.close()
        rows = await asyncio.to_thread(work)
        await message.answer("\n".join(f"{r['id']}. {r['title']} · {r['employee_name']} · {r['starts_at']}\nЗапись: /book {r['id']}" for r in rows) or "Свободного времени пока нет.")

    @router.message(Command("book"))
    async def booking(message: Message, event_update: Update):
        parts = (message.text or "").split()
        if len(parts) != 2 or not parts[1].isdigit() or not message.from_user:
            await message.answer("Укажите ID времени: /book 1")
            return
        def work():
            db = connect(path)
            try:
                return book(db, message.from_user.id, int(parts[1]), message.from_user.full_name[:100], event_update.update_id)
            finally:
                db.close()
        try:
            result = await asyncio.to_thread(work)
            await message.answer(f"Запись №{result['id']} подтверждена. Отмена: /cancel {result['id']}")
        except (BookingConflict, ValueError):
            await message.answer("Не удалось записаться: время занято или недоступно. Выберите /slots.")

    @router.message(Command("mine"))
    async def mine(message: Message):
        if not message.from_user:
            return
        rows = await query("SELECT b.*,s.starts_at,v.title,e.name AS employee_name FROM bookings b JOIN slots s ON s.id=b.slot_id JOIN services v ON v.id=s.service_id JOIN employees e ON e.id=s.employee_id WHERE b.telegram_user_id=? ORDER BY b.id DESC LIMIT 30", (message.from_user.id,))
        names = {"confirmed": "Подтверждено", "cancelled": "Отменено", "completed": "Завершено"}
        await message.answer("\n".join(f"№{r['id']} · {r['title']} · {r['employee_name']} · {r['starts_at']} · {names[r['status']]}" for r in rows) or "У вас пока нет записей.")

    @router.message(Command("cancel"))
    async def cancellation(message: Message):
        parts = (message.text or "").split()
        if len(parts) != 2 or not parts[1].isdigit() or not message.from_user:
            await message.answer("Укажите номер записи: /cancel 1")
            return
        def work():
            db = connect(path)
            try:
                cancel(db, message.from_user.id, int(parts[1]))
            finally:
                db.close()
        try:
            await asyncio.to_thread(work)
            await message.answer("Запись отменена.")
        except BookingConflict:
            await message.answer("Запись не найдена или уже завершена.")

    dispatcher = Dispatcher()
    dispatcher.include_router(router)
    return dispatcher


async def main():
    token = os.environ.get("BOT_TOKEN")
    if not token:
        raise RuntimeError("Set BOT_TOKEN in local environment; never commit it")
    path = os.environ.get("DATABASE_PATH", "deskline.sqlite")
    db = connect(path)
    db.close()
    bot = Bot(token)
    try:
        await create_dispatcher(path).start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
