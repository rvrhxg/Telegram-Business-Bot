# Приёмка Deskline v1

Подтверждено CI 43863564736: три теста ядра/aiogram Dispatcher/REST API, Docker build, runtime с сохранением услуги и входом после перезапуска, непривилегированный UID, Chromium-сценарий панели. Desktop/mobile снимки просмотрены визуально.

**Реальное Telegram-подключение не проверено.** BOT_TOKEN отсутствует; тестовый транспорт перехватывает SendMessage без обращения к сети. Пользовательский live smoke после локального задания токена: запустить polling, отправить /start, /services, /slots, /book ID, /mine, /cancel ID и подтвердить ответы. Токен не передавать в чат. Пока этот шаг не выполнен, нельзя утверждать, что реальная доставка или polling проверены.

Приложение принято как самостоятельный проект портфолио с проверенным ядром, обработчиками и панелью; без заявления о production-готовности. Ограничения расписания и масштабирования перечислены в README/ARCHITECTURE.

[CI 43907341139](https://github.com/rvrhxg/Telegram-Business-Bot/actions/runs/43907341139) на 34296e0: Python 3.12, 3.13, 3.14, Docker/runtime и Chromium успешны; 9 тестов с проверками пересечения интервалов. После этого добавлен отдельный тест конкурентной записи: локально полный набор 10 passed на Python 3.14, CI повторяется. Реальная Telegram-доставка не проверена.

[Финальный CI 43909764342](https://github.com/rvrhxg/Telegram-Business-Bot/actions/runs/43909764342) на 6b4d66d: 10 тестов с конкурентной гонкой успешны на Python 3.12, 3.13 и 3.14; Docker/runtime и Chromium успешны.


## Расписания сотрудников

[CI 43919717118](https://github.com/rvrhxg/Telegram-Business-Bot/actions/runs/43919717118) на 611de43: 12 тестов успешны на Python 3.12, 3.13, 3.14; Ruff E9/F, strict mypy интервалов, Docker build/runtime/persistence и Chromium успешны. Браузер создал сотрудника и его слот, выбрал фильтр сотрудника и завершил существующую запись. Скриншоты1440/390px получены из этого CI и просмотрены визуально. Тест переноса первоначальной базы сохранил ID и внешние ключи. Реальная Telegram-доставка по-прежнему не проверена.


## Readiness, безопасные HTTP-логи и backup/restore

[CI 43930043895](https://github.com/rvrhxg/Telegram-Business-Bot/actions/runs/43930043895) на c1ec3e7: все job успешны на Python3.12/3.13/3.14. Проверены200/503 readiness, реальная недоступность БД/структуры, request_id и отсутствие URL/query/cookie/тела/секрета в JSON-событиях, общий500 без внутреннего текста, SQLite WAL-snapshot/restore, запрет перезаписи и повреждённый источник. Контейнер Deskline дополнительно восстановил реальную тестовую БД в новый файл и проверил услугу/внешние ключи. Docker build/runtime/readiness/persistence и Chromium успешны. Локально: 16 passed; PostgreSQL локально не установлен. Strict mypy охватывает новые эксплуатационные модули и ранее указанный типизированный модуль, RuffE9/F — app/tests/scripts. Шифрование/ротация/offsite/PITR и аварийные RPO/RTO не проверены; это остаётся MVP. [Инструкции](OPERATIONS.md).


## Recorded demonstration

CI 43939546954 passed. The published WebM is 41.17 seconds at 1280x888, without audio, with explicitly documented 3x playback slowdown. File SHA256 matches metadata; six-frame contact sheet was visually reviewed. This is a Chromium recording with fictional data. It does not establish production readiness or real Telegram delivery.
