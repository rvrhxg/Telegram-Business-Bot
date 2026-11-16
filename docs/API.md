# REST API

Swagger: /docs. Cookie session, HttpOnly/SameSite, Secure в production. Все изменяющие запросы требуют Origin=APP_ORIGIN и JSON; тело до 32KiB. Администратор создаётся локально через app.setup, публичной регистрации нет.

| Метод | Путь | Назначение |
|---|---|---|
| POST | /api/login | email, password |
| GET | /api/me | Текущий администратор |
| POST | /api/logout | Отозвать сессию |
| GET | /api/overview | Услуги, последние 200 слотов/записей |
| POST | /api/services | title, duration_minutes (5–480), price_kopecks |
| POST | /api/slots | service_id, starts_at с часовым поясом, в будущем |
| PATCH | /api/bookings/:id | status: cancelled/completed |
| GET | /api/health | HTTP liveness |

Закрытая запись не может сменить терминальный статус. Повтор того же статуса допустим. API управления не создаёт запись от имени Telegram-пользователя: идентичность клиента берётся только из обработанного ботом Update. Ошибки возвращаются в detail с кодами 400/401/403/404/409/413/415/422/429.
