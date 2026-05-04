# TG-Lion Monitor Bot

Telegram-бот на aiogram 3 для мониторинга TG-Lion API: страны, цена, количество, баланс и алерты по пользовательским фильтрам.

## Возможности

- настройка `apiKey` и `YourID` прямо в боте;
- проверка подключения через `get_balance`;
- мониторинг всех стран или выбранного списка;
- лимит цены в USD;
- интервалы 5 сек, 10 сек, 30 сек, 1 мин, 5 мин и ручной ввод;
- антиспам одинаковых алертов по стране: 5 минут;
- статистика проверок и алертов;
- SQLite-хранение.
- встроенная админ-панель с whitelist, баном, статистикой, логами и broadcast.
- автоскуп через `getNumber` с лимитами, стоп-балансом и автополучением кода через `getCode`.

## Установка

```bash
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

Заполните `.env`:

```env
BOT_TOKEN=123456789:your_bot_token
ADMINS=123456789
DATABASE_PATH=bot.db
TG_LION_BASE_URL=https://TG-Lion.net
HTTP_TIMEOUT=15
ALERT_COOLDOWN_SECONDS=300
MAX_USERS=100
```

## Запуск

```bash
python main.py
```

После запуска откройте бота в Telegram и отправьте `/start`.

## Админ-панель

Админы задаются в `.env` через `ADMINS`, несколько ID можно указать через запятую:

```env
ADMINS=111111111,222222222
```

Команды:

```text
/admin
/broadcast
/adduser ID
/deluser ID
```

## Автоскуп

Раздел `🤖 Автоскуп` позволяет настроить:

- цену от/до;
- стоп-баланс, например остановить покупки при балансе `<= 5$`;
- общий лимит покупок;
- дневной лимит покупок;
- автополучение кода;
- интервал проверки кода.

Автоскуп работает поверх мониторинга: страна должна пройти выбранные страны, цену и количество. После покупки бот отправляет номер в чат и затем присылает код, когда API отдаст его через `getCode`.

По умолчанию включен whitelist-режим: бот доступен только пользователям, добавленным админом, и самим админам. Пользователь не из whitelist на `/start` получит сообщение “нет доступа”.

## Структура

```text
main.py
config.py
database.py
api_client.py
keyboards.py
states.py
handlers/
  start.py
  api_settings.py
  monitoring.py
  countries.py
  price.py
  interval.py
  balance.py
  stats.py
services/
  monitor.py
requirements.txt
.env.example
README.md
```

## Примечания по безопасности

- `BOT_TOKEN` хранится только в `.env`.
- Полный `apiKey` не выводится в интерфейсе.
- Логи HTTP-запросов маскируют `apiKey`.
- Все админ-действия проверяют `ADMINS` и пишутся в журнал.
