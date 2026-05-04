# 🤖 Telegram Monitor Bot

Бот для мониторинга изменений профилей Telegram-аккаунтов.

## 📦 Стек технологий

| Компонент | Библиотека |
|-----------|------------|
| Bot framework | [Aiogram 3](https://docs.aiogram.dev/) |
| Userbot / API | [Telethon](https://docs.telethon.dev/) |
| База данных | SQLite (aiosqlite) |
| Конфигурация | python-dotenv |

> **Почему Telethon?**  
> Bot API Telegram не позволяет получать информацию о профилях произвольных пользователей
> (username, bio, фото). Для этого нужен **userbot** — обычный аккаунт Telegram,
> авторизованный через MTProto API.

---

## ⚙️ Установка и запуск

### 1. Клонируйте / распакуйте проект

```bash
cd tg_monitor_bot
```

### 2. Создайте виртуальное окружение

```bash
python -m venv venv
source venv/bin/activate      # Linux / macOS
venv\Scripts\activate.bat     # Windows
```

### 3. Установите зависимости

```bash
pip install -r requirements.txt
```

### 4. Настройте переменные окружения

```bash
cp .env.example .env
nano .env     # или любой редактор
```

Заполните все поля:

| Переменная | Где взять |
|------------|-----------|
| `BOT_TOKEN` | [@BotFather](https://t.me/BotFather) |
| `ADMIN_ID` | [@userinfobot](https://t.me/userinfobot) |
| `API_ID` / `API_HASH` | [my.telegram.org](https://my.telegram.org) → API development tools |
| `PHONE` | Номер телефона аккаунта-наблюдателя |

### 5. Первый запуск (авторизация userbot)

При первом запуске Telethon запросит код из SMS / Telegram.

```bash
python bot.py
```

После успешной авторизации файл сессии (`monitor_session.session`) сохраняется.
При последующих запусках авторизация не требуется.

---

## 🗂 Структура проекта

```
tg_monitor_bot/
├── bot.py                  # Точка входа
├── config.py               # Загрузка конфигурации из .env
├── requirements.txt
├── .env.example
│
├── db/
│   ├── __init__.py
│   └── database.py         # Async SQLite — все методы работы с БД
│
├── handlers/
│   ├── __init__.py
│   ├── common.py           # /start, /admin, навигация
│   ├── user.py             # Добавление, просмотр, управление мониторингами
│   └── admin.py            # Панель администратора
│
├── services/
│   ├── __init__.py
│   ├── access.py           # Middleware проверки доступа
│   └── monitor.py          # Telethon клиент + фоновый цикл мониторинга
│
├── states/
│   ├── __init__.py
│   └── forms.py            # FSM-состояния (Aiogram)
│
└── utils/
    ├── __init__.py
    └── keyboards.py        # Все inline-клавиатуры
```

---

## 🔐 Система доступа

```
Новый пользователь → /start → запись в БД (is_allowed=0)
Админ → Выдать доступ → is_allowed=1
Пользователь → может пользоваться ботом
```

- Бот полностью приватный — без доступа ни одна команда не работает
- Администратор определяется через `ADMIN_ID` в `.env`
- Adminka: `/admin` или из /start

---

## 📊 Что отслеживается

| Поле | Описание |
|------|----------|
| Username | @username аккаунта |
| Имя | Имя + Фамилия |
| Bio | Описание профиля |
| Фото профиля | Хэш photo_id (фиксирует факт смены) |

---

## 📩 Пример уведомления

```
📌 Изменение профиля обнаружено

👤 Аккаунт: @example_user
🔄 Изменения:
  • Username: @old_name → @new_name
  • Имя: Ivan Petrov → Ivan Ivanov
  • Bio: — → Привет, это мой новый bio!

⏰ Время: 2025-03-15 14:32
```

---

## 🛡 Важные замечания

1. **Аккаунт-наблюдатель** — лучше использовать отдельный аккаунт, не основной.
2. **Публичные аккаунты** — бот может мониторить только аккаунты с username.
3. **FloodWait** — при большом числе мониторингов Telegram может замедлить запросы. Бот автоматически выдерживает паузу.
4. **Сессия** — файл `monitor_session.session` содержит авторизованную сессию. Храните его в безопасном месте.

---

## 🚀 Деплой на сервер

```bash
# Systemd service
sudo nano /etc/systemd/system/tgmonitor.service
```

```ini
[Unit]
Description=Telegram Monitor Bot
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/opt/tg_monitor_bot
ExecStart=/opt/tg_monitor_bot/venv/bin/python bot.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable tgmonitor
sudo systemctl start tgmonitor
sudo journalctl -u tgmonitor -f
```
