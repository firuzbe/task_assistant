import os
import logging
import tempfile

from telegram import (
    Update,
    InlineKeyboardMarkup,
    InlineKeyboardButton
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters
)

from config import (
    TELEGRAM_TOKEN,
    PASSWORD,
    MAX_ACTIVE_TASKS,
    LOG_FILE,
    ADMIN_TELEGRAM_ID
)

from deadline_parser import parse_deadline
from email_sender import send_task_email, send_cancel_email
from gigachat import parse_task_with_assignee
from asr import transcribe_audio

from database import (
    init_db,
    ensure_admin,
    create_bot_user,
    is_authorized,
    set_authorized,
    get_role,
    list_employees,
    add_employee,
    delete_employee,
    find_employee_by_lastname,
    get_employee_by_email,
    set_employee_telegram,
    get_employee_tasks,
    count_active_tasks,
    create_task,
    assign_task,
    get_active_tasks,
    cancel_task,
    get_history_tasks,
    get_task,
    get_task_emails,
    complete_task,
    get_task_creator
)

# -------------------- LOGGING --------------------
os.makedirs("logs", exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler()
    ]
)

# -------------------- GLOBAL STATE --------------------
pending_tasks = {}   # telegram_id -> {"task_text":..., "deadline":..., "recipients":[...], "employee_id":..., "telegram_id":...}
user_modes = {}      # telegram_id -> "newtask" / "broadcast" / None


# -------------------- HELPERS --------------------
def is_admin(telegram_id: int) -> bool:
    return get_role(telegram_id) == "admin"


def confirm_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Отправить", callback_data="confirm_task"),
            InlineKeyboardButton("❌ Отменить", callback_data="reject_task")
        ]
    ])


def done_keyboard(task_id: int):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Выполнено", callback_data=f"done_{task_id}")]
    ])


async def auth_required(update: Update) -> bool:
    """Проверяет авторизацию. Если не авторизован — пишет сообщение и возвращает False."""
    user_id = update.message.from_user.id
    if not is_authorized(user_id):
        await update.message.reply_text("❌ Сначала выполните /start и введите пароль.")
        return False
    return True


# -------------------- COMMANDS --------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    create_bot_user(user_id)

    if is_authorized(user_id):
        await update.message.reply_text("✅ Вы уже авторизованы.\nИспользуйте /help.")
        return

    await update.message.reply_text("🔐 Введите пароль.\nДля сотрудника пароль = email.")


async def logout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    set_authorized(user_id, False)

    pending_tasks.pop(user_id, None)
    user_modes.pop(user_id, None)

    logging.info(f"User {user_id} logged out")
    await update.message.reply_text("🚪 Вы вышли. Для входа используйте /start")


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id

    text = "📌 Справка\n\n"
    text += "/start - вход\n"
    text += "/logout - выход\n"
    text += "/help - команды\n"
    text += "/id - показать ваш telegram_id\n\n"

    text += "📋 Задачи:\n"
    text += "/mytasks - мои задачи (сотрудник)\n"
    text += "/tasks - все активные задачи\n"
    text += "/history - история\n"
    text += "/cancel ID - отменить задачу\n\n"

    text += "📌 Руководитель:\n"
    text += "/newtask - создать задачу (текст/голос)\n\n"

    if is_admin(user_id):
        text += "👑 Админ:\n"
        text += "/employees - список сотрудников\n"
        text += "/add_employee ФИО email - добавить сотрудника\n"
        text += "/del_employee email - удалить сотрудника\n"
        text += "/bind_employee email telegram_id - привязать Telegram\n"
        text += "/broadcast - отправить задачу всем (текст/голос)\n"

    await update.message.reply_text(text)


async def id_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    await update.message.reply_text(f"Ваш telegram_id: {user_id}")


# -------------------- ADMIN COMMANDS --------------------
async def employees_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id

    if not is_admin(user_id):
        await update.message.reply_text("❌ Нет прав (нужен admin).")
        return

    emps = list_employees()
    if not emps:
        await update.message.reply_text("⚠️ Список сотрудников пуст.")
        return

    text = "👥 Сотрудники:\n\n"
    for e in emps:
        text += f"- {e['full_name']} ({e['email']}) tg_id={e['telegram_id']}\n"

    await update.message.reply_text(text)


async def add_employee_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id

    if not is_admin(user_id):
        await update.message.reply_text("❌ Нет прав (нужен admin).")
        return

    if len(context.args) < 2:
        await update.message.reply_text("Использование:\n/add_employee Иванов Иван Иванович ivanov@company.ru")
        return

    full_name = " ".join(context.args[:-1])
    email = context.args[-1].strip().lower()

    try:
        add_employee(full_name, email)
        logging.info(f"Admin {user_id} added employee {email}")
        await update.message.reply_text("✅ Сотрудник добавлен.")
    except Exception as e:
        logging.exception("Add employee error")
        await update.message.reply_text(f"Ошибка: {e}")


async def del_employee_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id

    if not is_admin(user_id):
        await update.message.reply_text("❌ Нет прав (нужен admin).")
        return

    if not context.args:
        await update.message.reply_text("Использование:\n/del_employee ivanov@company.ru")
        return

    email = context.args[0].strip().lower()
    delete_employee(email)

    logging.info(f"Admin {user_id} deleted employee {email}")
    await update.message.reply_text("🗑 Сотрудник удалён.")


async def bind_employee_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id

    if not is_admin(user_id):
        await update.message.reply_text("❌ Только админ.")
        return

    if len(context.args) < 2:
        await update.message.reply_text("Использование:\n/bind_employee ivanov@company.ru 123456789")
        return

    email = context.args[0].strip().lower()
    telegram_id = int(context.args[1])

    emp = get_employee_by_email(email)
    if not emp:
        await update.message.reply_text("⚠️ Сотрудник не найден.")
        return

    set_employee_telegram(emp["id"], telegram_id)

    logging.info(f"Employee {email} binded to telegram_id={telegram_id}")
    await update.message.reply_text(f"✅ Привязано: {emp['full_name']} -> {telegram_id}")


# -------------------- BROADCAST LOGIC --------------------
async def process_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    user_id = update.message.from_user.id

    text = (text or "").strip()

    # защита от пустого текста
    if not text or text == "/broadcast":
        await update.message.reply_text("⚠️ Текст задачи пустой. Отправьте текст или голос.")
        return

    if not is_admin(user_id):
        await update.message.reply_text("❌ Только админ может делать рассылку.")
        return

    if count_active_tasks() >= MAX_ACTIVE_TASKS:
        await update.message.reply_text("⚠️ Лимит активных задач достигнут.")
        return

    employees = list_employees()
    if not employees:
        await update.message.reply_text("⚠️ Нет сотрудников.")
        return

    deadline = parse_deadline(text)

    recipients_email = [e["email"] for e in employees]
    employee_ids = [e["id"] for e in employees]

    task_id = create_task(text, deadline, user_id)
    assign_task(task_id, employee_ids)

    # EMAIL всем
    try:
        send_task_email(recipients_email, text, deadline)
    except Exception:
        logging.exception("Broadcast email error")

    # TELEGRAM всем
    for e in employees:
        if not e["telegram_id"]:
            continue
        try:
            await context.bot.send_message(
                chat_id=e["telegram_id"],
                text=f"📢 Новая общая задача #{task_id}\n\n{text}\n\n📅 deadline: {deadline}",
                reply_markup=done_keyboard(task_id)
            )
        except Exception:
            logging.exception(f"Telegram broadcast failed to {e['telegram_id']}")

    user_modes[user_id] = None
    await update.message.reply_text(f"📢 Общая задача #{task_id} отправлена всем.")


async def broadcast_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await auth_required(update):
        return

    user_id = update.message.from_user.id

    if not is_admin(user_id):
        await update.message.reply_text("❌ Только админ может делать рассылку.")
        return

    # если текст есть сразу после команды
    if context.args:
        text = " ".join(context.args).strip()
        await process_broadcast(update, context, text)
        return

    # включаем режим ожидания текста/голоса
    user_modes[user_id] = "broadcast"
    await update.message.reply_text(
        "📢 Отправьте задачу текстом или голосом для рассылки всем сотрудникам.\n\n"
        "Пример:\n"
        "Сделать отчёт по продажам до пятницы."
    )


# -------------------- TASK COMMANDS --------------------
async def tasks_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await auth_required(update):
        return

    tasks = get_active_tasks()
    if not tasks:
        await update.message.reply_text("📌 Активных задач нет.")
        return

    text = "📌 Активные задачи:\n\n"
    for t in tasks:
        text += f"#{t['id']} | {t['task_text']}\n"
        text += f"📅 deadline: {t['deadline']}\n\n"

    await update.message.reply_text(text)


async def mytasks_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await auth_required(update):
        return

    user_id = update.message.from_user.id

    tasks = get_employee_tasks(user_id)
    if not tasks:
        await update.message.reply_text("📌 У вас нет активных задач.")
        return

    for t in tasks:
        await update.message.reply_text(
            f"📌 Задача #{t['id']}\n\n"
            f"{t['task_text']}\n\n"
            f"📅 deadline: {t['deadline']}",
            reply_markup=done_keyboard(t["id"])
        )


async def history_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await auth_required(update):
        return

    tasks = get_history_tasks()
    if not tasks:
        await update.message.reply_text("🕘 История пуста.")
        return

    text = "🕘 История задач:\n\n"
    for t in tasks:
        text += f"#{t['id']} [{t['status']}] {t['task_text']}\n"
        text += f"📅 deadline: {t['deadline']}\n\n"

    await update.message.reply_text(text)


async def cancel_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await auth_required(update):
        return

    user_id = update.message.from_user.id

    if not context.args:
        await update.message.reply_text("Пример:\n/cancel 5")
        return

    task_id = int(context.args[0])

    task = get_task(task_id)
    if not task:
        await update.message.reply_text("⚠️ Задача не найдена.")
        return

    recipients = get_task_emails(task_id)

    cancel_task(task_id)
    logging.info(f"Task {task_id} cancelled by user {user_id}")

    if recipients:
        try:
            send_cancel_email(recipients, task["task_text"], task["deadline"])
        except Exception:
            logging.exception("Cancel email sending error")

    await update.message.reply_text(f"❌ Задача #{task_id} отменена. Исполнители уведомлены.")


# -------------------- NEWTASK LOGIC --------------------
async def newtask_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await auth_required(update):
        return

    user_id = update.message.from_user.id

    if context.args:
        text = " ".join(context.args)
        await process_newtask(update, context, text)
        return

    user_modes[user_id] = "newtask"
    await update.message.reply_text(
        "🎯 Отправьте задачу текстом или голосом.\n\n"
        "Пример:\n"
        "Иванов, отчёт по продажам до понедельника."
    )


async def process_newtask(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    user_id = update.message.from_user.id

    text = (text or "").strip()

    if not text:
        await update.message.reply_text("⚠️ Текст задачи пустой.")
        return

    logging.info(f"Newtask request from {user_id}: {text}")

    if count_active_tasks() >= MAX_ACTIVE_TASKS:
        await update.message.reply_text("⚠️ Лимит активных задач достигнут.")
        return

    employees = list_employees()
    if not employees:
        await update.message.reply_text("⚠️ Список сотрудников пуст. Админ должен добавить сотрудников.")
        return

    employees_names = [e["full_name"] for e in employees]

    await update.message.reply_text("⏳ Анализирую задачу...")

    task_data = parse_task_with_assignee(text, employees_names)

    if "status" in task_data:
        await update.message.reply_text(f"Ошибка Gigachat: {task_data['message']}")
        return

    assignee = task_data.get("assignee")
    task_text = task_data.get("task_text")
    deadline = task_data.get("deadline")

    parsed_deadline = parse_deadline(text)
    if parsed_deadline:
        deadline = parsed_deadline

    if not assignee:
        await update.message.reply_text("⚠️ Не удалось определить исполнителя.")
        return

    if not task_text:
        await update.message.reply_text("⚠️ Не удалось определить текст задачи.")
        return

    last_name = assignee.split()[0].strip()
    emp = find_employee_by_lastname(last_name)

    if not emp:
        await update.message.reply_text(f"⚠️ Исполнитель '{assignee}' не найден в справочнике.")
        return

    recipients = [emp["email"]]

    pending_tasks[user_id] = {
        "task_text": task_text,
        "deadline": deadline,
        "recipients": recipients,
        "employee_id": emp["id"],
        "telegram_id": emp["telegram_id"]
    }

    user_modes[user_id] = None

    await update.message.reply_text(
        f"📝 Проверьте задачу:\n\n"
        f"{task_text}\n\n"
        f"👤 Исполнитель: {emp['full_name']}\n"
        f"📧 Email: {emp['email']}\n"
        f"📅 Срок: {deadline}\n\n"
        f"Подтвердить отправку?",
        reply_markup=confirm_keyboard()
    )


# -------------------- MESSAGE HANDLERS --------------------
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    text = update.message.text.strip()

    logging.info(f"Text from {user_id}: {text}")

    create_bot_user(user_id)

    # ---------------- AUTH ----------------
    if not is_authorized(user_id):

        # общий пароль руководителя/админа
        if text == PASSWORD:
            set_authorized(user_id, True)
            logging.info(f"User {user_id} authorized by global password")
            await update.message.reply_text("✅ Авторизация успешна. Используйте /help.")
            return

        # пароль сотрудника = email
        emp = get_employee_by_email(text.lower())
        if emp:
            set_employee_telegram(emp["id"], user_id)
            set_authorized(user_id, True)
            logging.info(f"Employee {emp['email']} authorized and binded telegram_id={user_id}")
            await update.message.reply_text(
                f"✅ Вы вошли как сотрудник: {emp['full_name']}\n"
                f"Используйте /mytasks"
            )
            return

        await update.message.reply_text("❌ Неверный пароль.")
        return

    # ---------------- MODES ----------------
    if user_modes.get(user_id) == "newtask":
        await process_newtask(update, context, text)
        return

    if user_modes.get(user_id) == "broadcast":
        # если пользователь вместо текста прислал команду
        if text.startswith("/"):
            await update.message.reply_text("⚠️ Отправьте текст задачи или голосовое сообщение.")
            return
        await process_broadcast(update, context, text)
        return

    await update.message.reply_text(
        "Я не понял что делать.\n"
        "Справка: /help"
    )


async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    create_bot_user(user_id)

    logging.info(f"Voice from {user_id}")

    if not is_authorized(user_id):
        await update.message.reply_text("❌ Сначала /start и пароль.")
        return

    file = await update.message.voice.get_file()

    fd, temp_path = tempfile.mkstemp(suffix=".ogg")
    os.close(fd)

    try:
        await file.download_to_drive(temp_path)
        text = transcribe_audio(temp_path)
        logging.info(f"Voice recognized from {user_id}: {text}")

        await update.message.reply_text(f"🎤 Распознано: {text}")

        if user_modes.get(user_id) == "newtask":
            await process_newtask(update, context, text)
            return

        if user_modes.get(user_id) == "broadcast":
            await process_broadcast(update, context, text)
            return

        await update.message.reply_text("Используйте /newtask или /broadcast перед голосовым сообщением.")
    finally:
        os.unlink(temp_path)


# -------------------- INLINE BUTTONS --------------------
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    await query.answer()

    data = query.data
    logging.info(f"Callback from {user_id}: {data}")

    # ---------------- DONE BUTTON ----------------
    if data.startswith("done_"):
        if not is_authorized(user_id):
            await query.edit_message_text("❌ Сначала /start и пароль.")
            return

        task_id = int(data.split("_")[1])
        task = get_task(task_id)

        if not task:
            await query.edit_message_text("⚠️ Задача не найдена.")
            return

        complete_task(task_id)
        logging.info(f"Task {task_id} completed by {user_id}")

        creator_id = get_task_creator(task_id)
        if creator_id:
            try:
                await context.bot.send_message(
                    chat_id=creator_id,
                    text=f"✅ Задача #{task_id} выполнена.\n\n{task['task_text']}"
                )
            except Exception:
                logging.exception("Creator notify error")

        await query.edit_message_text(f"✅ Задача #{task_id} отмечена как выполненная.")
        return

    # ---------------- CONFIRM TASK CREATION ----------------
    if user_id not in pending_tasks:
        await query.edit_message_text("⚠️ Нет задачи для подтверждения.")
        return

    if data == "reject_task":
        pending_tasks.pop(user_id, None)
        await query.edit_message_text("❌ Задача отменена.")
        return

    if data == "confirm_task":
        task_data = pending_tasks.pop(user_id)

        task_text = task_data["task_text"]
        deadline = task_data.get("deadline")
        recipients = task_data.get("recipients", [])
        employee_id = task_data.get("employee_id")
        tg_id = task_data.get("telegram_id")

        task_id = create_task(task_text, deadline, user_id)

        if employee_id:
            assign_task(task_id, [employee_id])

        # EMAIL
        try:
            send_task_email(recipients, task_text, deadline)
        except Exception:
            logging.exception("Email sending error")
            await query.edit_message_text("⚠️ Задача сохранена, но email не отправился.")
            return

        # TELEGRAM исполнителю
        if tg_id:
            try:
                await context.bot.send_message(
                    chat_id=tg_id,
                    text=f"📌 Новая задача #{task_id}\n\n{task_text}\n\n📅 deadline: {deadline}",
                    reply_markup=done_keyboard(task_id)
                )
            except Exception:
                logging.exception("Telegram notify assignee error")

        logging.info(f"Task {task_id} created by {user_id} -> {recipients}")
        await query.edit_message_text(f"✅ Задача #{task_id} отправлена.")


# -------------------- MAIN --------------------
def main():
    init_db()

    if ADMIN_TELEGRAM_ID and ADMIN_TELEGRAM_ID != 0:
        ensure_admin(ADMIN_TELEGRAM_ID)
        logging.info(f"Admin ensured: {ADMIN_TELEGRAM_ID}")

    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    # базовые команды
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("logout", logout))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("id", id_cmd))

    # задачи
    app.add_handler(CommandHandler("newtask", newtask_cmd))
    app.add_handler(CommandHandler("broadcast", broadcast_cmd))
    app.add_handler(CommandHandler("tasks", tasks_cmd))
    app.add_handler(CommandHandler("mytasks", mytasks_cmd))
    app.add_handler(CommandHandler("history", history_cmd))
    app.add_handler(CommandHandler("cancel", cancel_cmd))

    # админ
    app.add_handler(CommandHandler("employees", employees_cmd))
    app.add_handler(CommandHandler("add_employee", add_employee_cmd))
    app.add_handler(CommandHandler("del_employee", del_employee_cmd))
    app.add_handler(CommandHandler("bind_employee", bind_employee_cmd))

    # кнопки
    app.add_handler(CallbackQueryHandler(button_handler))

    # сообщения
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))

    logging.info("Bot started successfully")
    print("BOT STARTED")

    app.run_polling()


if __name__ == "__main__":
    main()