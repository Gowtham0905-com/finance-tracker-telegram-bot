import logging
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
import psycopg2
import calendar
from datetime import date
from passlib.context import CryptContext
from dotenv import load_dotenv

# Requires: pip install passlib argon2-cffi python-dotenv

load_dotenv()  # reads variables from a .env file in the same folder (see .env.example)

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN is not set. Copy .env.example to .env and fill it in.")

DATABASE_URL = os.environ.get("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not set.")# Password hashing uses Argon2. The website's auth.py uses the same scheme

# so passwords created here can be verified there and vice versa.
pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")

# ---------- Signup flow state ----------
# Every new user goes: name -> login ID -> password, in that order.
# Existing users (already have a name/UserID) can jump straight into
# login ID -> password via /setuplogin, skipping the name step.
# `signup_step[telegram_id]` tracks which step they're on.
# `pending_signup[telegram_id]` holds the fields collected so far.
signup_step = {}             # {telegram_id: "name" | "login_id" | "password"}
pending_signup = {}          # {telegram_id: {"name": ..., "login_id": ...}}

current_date = {}            # {telegram_id: date object} - the date they're logging for

# ---------- Logging setup ----------
# Logs go to bot.log so you can check what went wrong after the fact,
# without needing the terminal open.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("bot.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ---------- Database helpers ----------

def get_connection():
    return psycopg2.connect(DATABASE_URL)

def get_user_id(telegram_id):
    conn = get_connection()

    try:
        cursor = conn.cursor()

        cursor.execute(
            '''
            SELECT "UserID"
            FROM users
            WHERE "TelegramUserID" = %s
            ''',
            (telegram_id,)
        )

        row = cursor.fetchone()

        return row[0] if row else None

    finally:
        conn.close()


def create_user(telegram_id, name, login_id, password_hash):

    conn = get_connection()

    try:
        cursor = conn.cursor()

        cursor.execute(
            '''
            INSERT INTO users
                ("TelegramUserID", "Username", "LoginID", "PasswordHash")
            VALUES
                (%s, %s, %s, %s)
            ''',
            (telegram_id, name, login_id, password_hash)
        )

        conn.commit()

    finally:
        conn.close()


def login_id_already_taken(login_id):

    conn = get_connection()

    try:
        cursor = conn.cursor()

        cursor.execute(
            '''
            SELECT "UserID"
            FROM users
            WHERE "LoginID" = %s
            ''',
            (login_id,)
        )

        return cursor.fetchone() is not None

    finally:
        conn.close()


def get_login_status(user_id):

    conn = get_connection()

    try:
        cursor = conn.cursor()

        cursor.execute(
            '''
            SELECT "LoginID"
            FROM users
            WHERE "UserID" = %s
            ''',
            (user_id,)
        )

        row = cursor.fetchone()

        return row is not None and row[0] is not None

    finally:
        conn.close()


def set_login_credentials(user_id, login_id, password_hash):

    conn = get_connection()

    try:
        cursor = conn.cursor()

        cursor.execute(
            '''
            UPDATE users
            SET "LoginID" = %s,
                "PasswordHash" = %s
            WHERE "UserID" = %s
            ''',
            (login_id, password_hash, user_id)
        )

        conn.commit()

    finally:
        conn.close()


def insert_expense(user_id, category, amount, entry_date):

    conn = get_connection()

    try:
        cursor = conn.cursor()

        cursor.execute(
            '''
            INSERT INTO expenses
                ("UserID", "Category", "Amount", "ExpenseDate")
            VALUES
                (%s, %s, %s, %s)
            ''',
            (user_id, category, amount, entry_date)
        )

        conn.commit()

    finally:
        conn.close()


def insert_income(user_id, source, amount, entry_date):

    conn = get_connection()

    try:
        cursor = conn.cursor()

        cursor.execute(
            '''
            INSERT INTO income
                ("UserID", "Source", "Amount", "IncomeDate")
            VALUES
                (%s, %s, %s, %s)
            ''',
            (user_id, source, amount, entry_date)
        )

        conn.commit()

    finally:
        conn.close()

# ---------- Error-handling wrapper ----------

def safe_handler(func):
    """
    Wraps a handler so that:
    - DB/connection errors get logged and the user gets a friendly retry message
      instead of the bot silently dying on that update.
    - Any other unexpected error is also caught, logged with full traceback,
      and doesn't crash the whole bot process.
    """
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            await func(update, context)
        except psycopg2.Error as e:
            logger.error(f"[DB ERROR] in {func.__name__}: {e}", exc_info=True)
            target = update.effective_message
            if target:
                await target.reply_text(
                    "⚠️ I couldn't reach the database just now. Please try again in a moment."
                )
        except Exception as e:
            logger.error(f"[UNEXPECTED ERROR] in {func.__name__}: {e}", exc_info=True)
            target = update.effective_message
            if target:
                await target.reply_text(
                    "⚠️ Something went wrong on my end. Please try again."
                )
    wrapper.__name__ = func.__name__
    return wrapper

# ---------- Date picker (Today / Past date buttons + calendar) ----------

def today_or_past_keyboard():
    keyboard = [[
        InlineKeyboardButton("Today", callback_data="date_today"),
        InlineKeyboardButton("Past date", callback_data="date_past")
    ]]
    return InlineKeyboardMarkup(keyboard)

def build_calendar(year, month):
    markup = []

    month_name = calendar.month_name[month]
    markup.append([
        InlineKeyboardButton("<", callback_data=f"cal_nav_{year}_{month}_prev"),
        InlineKeyboardButton(f"{month_name} {year}", callback_data="cal_ignore"),
        InlineKeyboardButton(">", callback_data=f"cal_nav_{year}_{month}_next"),
    ])

    markup.append([InlineKeyboardButton(day, callback_data="cal_ignore")
                   for day in ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"]])

    month_days = calendar.monthcalendar(year, month)
    for week in month_days:
        row = []
        for day in week:
            if day == 0:
                row.append(InlineKeyboardButton(" ", callback_data="cal_ignore"))
            else:
                row.append(InlineKeyboardButton(str(day), callback_data=f"cal_day_{year}_{month}_{day}"))
        markup.append(row)

    return InlineKeyboardMarkup(markup)

def shift_month(year, month, direction):
    if direction == "next":
        if month == 12:
            return year + 1, 1
        return year, month + 1
    else:
        if month == 1:
            return year - 1, 12
        return year, month - 1

# ---------- Command handlers ----------

@safe_handler
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = update.effective_user.id
    user_id = get_user_id(telegram_id)

    if user_id is not None:
        await update.message.reply_text("Welcome back!")
        await update.message.reply_text(
            "Are you logging for Today or a Past date?",
            reply_markup=today_or_past_keyboard()
        )
    else:
        signup_step[telegram_id] = "name"
        pending_signup[telegram_id] = {}
        await update.message.reply_text(
            "Hello! I'm your expense tracker bot.\n"
            "I'll also set you up with a login for the web dashboard, so I need a few details first."
        )
        await update.message.reply_text("Please enter your name.")

@safe_handler
async def change_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Are you logging for Today or a Past date?",
        reply_markup=today_or_past_keyboard()
    )

@safe_handler
async def setup_login(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    For users who already exist (have a name/UserID from before the
    login-ID feature existed) and just need to add a website login,
    without repeating the whole /start signup.
    """
    telegram_id = update.effective_user.id
    user_id = get_user_id(telegram_id)

    if user_id is None:
        await update.message.reply_text("Please send /start first so I know who you are.")
        return

    if get_login_status(user_id):
        await update.message.reply_text(
            "You already have a website login set up. "
            "If you need to change your password, that'll need a /resetpassword command (coming soon)."
        )
        return

    pending_signup[telegram_id] = {}
    signup_step[telegram_id] = "login_id"
    await update.message.reply_text("Let's set up your website login. Please enter a login ID.")

# ---------- Button tap handler ----------

@safe_handler
async def button_tap(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    telegram_id = query.from_user.id
    data = query.data
    await query.answer()

    if data == "cal_ignore":
        return

    if data == "date_today":
        current_date[telegram_id] = date.today()
        await query.edit_message_text(
            f"Logging for {current_date[telegram_id].strftime('%d-%m-%Y')}.\n"
            "Send expenses like: food 250\n"
            "Send income with a + like: +salary 20000"
        )
        return

    if data == "date_past":
        today = date.today()
        await query.edit_message_text(
            "Pick a date:",
            reply_markup=build_calendar(today.year, today.month)
        )
        return

    if data.startswith("cal_nav_"):
        _, _, year, month, direction = data.split("_")
        year, month = shift_month(int(year), int(month), direction)
        await query.edit_message_reply_markup(reply_markup=build_calendar(year, month))
        return

    if data.startswith("cal_day_"):
        _, _, year, month, day = data.split("_")
        chosen = date(int(year), int(month), int(day))
        current_date[telegram_id] = chosen
        await query.edit_message_text(
            f"Logging for {chosen.strftime('%d-%m-%Y')}.\n"
            "Send expenses like: food 250\n"
            "Send income with a + like: +salary 20000"
        )
        return

# ---------- Regular text message handler ----------

@safe_handler
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = update.effective_user.id
    text = update.message.text.strip()

    # Step 1: signup flow (new user) - name, then login ID, then password
    step = signup_step.get(telegram_id)

    if step == "name":
        name = text.strip()
        if not name:
            await update.message.reply_text("Name can't be empty. Please enter your name.")
            return
        pending_signup[telegram_id]["name"] = name
        signup_step[telegram_id] = "login_id"
        await update.message.reply_text(f"Nice to meet you, {name}!")
        await update.message.reply_text("Please enter a login ID for your website login.")
        return

    if step == "login_id":
        login_id = text.strip()
        if not login_id:
            await update.message.reply_text("Login ID can't be empty. Please enter a login ID.")
            return
        if login_id_already_taken(login_id):
            await update.message.reply_text(
                "The entered login ID is already taken, so please try with another login."
            )
            return
        pending_signup[telegram_id]["login_id"] = login_id
        signup_step[telegram_id] = "password"
        await update.message.reply_text(
            "Great, that login ID is available.\n"
            "Now set a password for your dashboard login — at least 8 characters. "
            "Letters, numbers, and special characters are all fine, in any combination.\n"
            "I'll delete this message right after so it doesn't stay in your chat history."
        )
        return

    if step == "password":
        password = text
        # Best-effort cleanup: remove the plaintext password from the chat.
        # Telegram private chats aren't end-to-end encrypted, so this is a
        # privacy nicety, not a real security guarantee - it only works if
        # the bot has permission to delete the message.
        try:
            await update.message.delete()
        except Exception:
            logger.warning(f"Could not delete password message for {telegram_id}")

        if len(password) < 8:
            await update.message.reply_text(
                "Password needs to be at least 8 characters. Please send a new one."
            )
            return

        info = pending_signup.pop(telegram_id)
        signup_step.pop(telegram_id, None)

        password_hash = pwd_context.hash(password)

        if "name" in info:
            # Full signup flow via /start (new user)
            create_user(telegram_id, info["name"], info["login_id"], password_hash)
        else:
            # Existing user adding a login via /setuplogin
            user_id = get_user_id(telegram_id)
            set_login_credentials(user_id, info["login_id"], password_hash)

        await update.message.reply_text(
            "You're all set! You can log in to the web dashboard anytime with that login ID and password."
        )
        if "name" in info:
            await update.message.reply_text(
                "Are you logging for Today or a Past date?",
                reply_markup=today_or_past_keyboard()
            )
        return

    if telegram_id in pending_signup or step is not None:
        # Safety net: shouldn't normally reach here given the checks above.
        await update.message.reply_text("Please send /start to begin setup.")
        return

    # Step 2: must be a known user
    user_id = get_user_id(telegram_id)
    if user_id is None:
        await update.message.reply_text("Please send /start first so I can get your name.")
        return

    # Step 3: must have picked a date already
    if telegram_id not in current_date:
        await update.message.reply_text(
            "Are you logging for Today or a Past date?",
            reply_markup=today_or_past_keyboard()
        )
        return

    # Step 4: parse "category amount" or "+source amount"
    parts = text.split()
    if len(parts) < 2:
        await update.message.reply_text("Please send it like: food 250  or  +salary 20000")
        return

    label = parts[0]
    amount_text = parts[1]

    try:
        amount = float(amount_text)
    except ValueError:
        await update.message.reply_text("Amount must be a number. Try: food 250")
        return

    entry_date = current_date[telegram_id]

    if label.startswith("+"):
        source = label[1:]
        insert_income(user_id, source, amount, entry_date)
        await update.message.reply_text(f"Income logged: {source} ₹{amount} on {entry_date.strftime('%d-%m-%Y')}")
    else:
        category = label
        insert_expense(user_id, category, amount, entry_date)
        await update.message.reply_text(f"Expense logged: {category} ₹{amount} on {entry_date.strftime('%d-%m-%Y')}")

# ---------- Global fallback error handler ----------
# Catches anything that slips past the per-handler wrappers
# (e.g. errors raised by python-telegram-bot itself, not your code).

async def global_error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"[GLOBAL ERROR] Update {update} caused error: {context.error}", exc_info=context.error)

# ---------- App setup ----------

app = ApplicationBuilder().token(TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("date", change_date))
app.add_handler(CommandHandler("setuplogin", setup_login))
app.add_handler(CallbackQueryHandler(button_tap))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
app.add_error_handler(global_error_handler)

logger.info("Bot is running...")

async def run_bot():
    """Starts the bot's polling loop without blocking the event loop,
    so it can run alongside the FastAPI web server in the same process."""
    await app.initialize()
    await app.start()
    await app.updater.start_polling()
