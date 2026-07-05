import asyncio
import logging
import sqlite3
from datetime import datetime, timezone, timedelta
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.errors import SessionPasswordNeededError
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackQueryHandler, ContextTypes

# ────────────── تنظیمات ──────────────
BOT_TOKEN = "8650191433:AAExAiW3jio4iLN9BSTwe_XLs2V2vF3dloI"
API_ID = 22835488
API_HASH = "c1963cfed1d21e4d5ef22f43316161e1"

# کانال‌های اجباری
REQUIRED_CHANNELS = ["@radon_store"]

PHONE, CODE, PASSWORD = range(3)

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# ────────────── دیتابیس ──────────────
def init_db():
    conn = sqlite3.connect("sessions.db")
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            telegram_id INTEGER PRIMARY KEY,
            phone TEXT,
            session_string TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

def save_session(telegram_id, phone, session_string):
    conn = sqlite3.connect("sessions.db")
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO users (telegram_id, phone, session_string) VALUES (?, ?, ?)",
              (telegram_id, phone, session_string))
    conn.commit()
    conn.close()

def get_session(telegram_id):
    conn = sqlite3.connect("sessions.db")
    c = conn.cursor()
    c.execute("SELECT session_string FROM users WHERE telegram_id = ?", (telegram_id,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else None

def delete_session_db(telegram_id):
    conn = sqlite3.connect("sessions.db")
    c = conn.cursor()
    c.execute("DELETE FROM users WHERE telegram_id = ?", (telegram_id,))
    conn.commit()
    conn.close()

# ────────────── داده‌های موقت ──────────────
temp_data = {}
telethon_clients = {}
running_bots = {}

# ────────────── چک عضویت ──────────────
async def check_membership(context: ContextTypes.DEFAULT_TYPE, user_id):
    for channel in REQUIRED_CHANNELS:
        try:
            member = await context.bot.get_chat_member(chat_id=channel, user_id=user_id)
            if member.status in ['left', 'kicked']:
                return False
        except Exception as e:
            logger.error(f"Error checking membership: {e}")
            return False
    return True

def membership_keyboard():
    keyboard = [
        [InlineKeyboardButton("📢 عضو کانال شو", url="https://t.me/radon_store")],
        [InlineKeyboardButton("✅ عضو شدم", callback_data="check_membership")]
    ]
    return InlineKeyboardMarkup(keyboard)

# ────────────── دکمه‌های اصلی ──────────────
def main_keyboard():
    keyboard = [
        [InlineKeyboardButton("🆓 سلف رایگان", callback_data="free_self")],
        [InlineKeyboardButton("💰 سلف پولی", callback_data="paid_self")]
    ]
    return InlineKeyboardMarkup(keyboard)

# ────────────── شروع ──────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    is_member = await check_membership(context, user_id)

    if not is_member:
        await update.message.reply_text(
            "⚠️ **برای استفاده از ربات، اول باید تو کانال ما عضو بشی!**\n\n"
            "📢 @radon_store\n\n"
            "بعد از عضویت، دکمه «✅ عضو شدم» رو بزن.",
            parse_mode="Markdown",
            reply_markup=membership_keyboard()
        )
        return

    await update.message.reply_text(
        "🤖 **به ربات سلف خوش اومدی!**\n\n"
        "یکی از گزینه‌های زیر رو انتخاب کن:",
        parse_mode="Markdown",
        reply_markup=main_keyboard()
    )

# ────────────── مدیریت همه دکمه‌ها ──────────────
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data
    telegram_id = update.effective_user.id

    if data == "check_membership":
        is_member = await check_membership(context, telegram_id)
        if not is_member:
            await query.edit_message_text(
                "❌ **هنوز عضو نیستی!**\n\n"
                "اول تو کانال عضو شو:",
                parse_mode="Markdown",
                reply_markup=membership_keyboard()
            )
            return

        await query.edit_message_text(
            "✅ **عضویت تأیید شد!**\n\n"
            "🤖 به ربات سلف خوش اومدی!",
            parse_mode="Markdown",
            reply_markup=main_keyboard()
        )
        return

    is_member = await check_membership(context, telegram_id)
    if not is_member:
        await query.edit_message_text(
            "⚠️ **اول باید تو کانال عضو بشی!**",
            parse_mode="Markdown",
            reply_markup=membership_keyboard()
        )
        return

    if data == "paid_self":
        await query.edit_message_text(
            "💰 **سلف پولی**\n\n"
            "❌ این دکمه در حال حاضر در دسترس نیست.\n"
            "به زودی فعال میشه...\n\n"
            "🔙 برای برگشت /start رو بزن.",
            parse_mode="Markdown"
        )
        return

    elif data == "free_self":
        session = get_session(telegram_id)
        if session:
            keyboard = [
                [InlineKeyboardButton("🚀 اجرای سلف", callback_data="run_free")],
                [InlineKeyboardButton("🆕 ساخت سشن جدید", callback_data="new_free")],
                [InlineKeyboardButton("🔙 برگشت", callback_data="back_main")]
            ]
            await query.edit_message_text(
                "✅ شما قبلاً سشن دارین.\nمی‌خواین چیکار کنین؟",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        else:
            await query.edit_message_text(
                "📱 لطفاً شماره تلفنت رو با کد کشور تایپ کن و بفرست:\n\n"
                "مثال: `+989123456789`",
                parse_mode="Markdown"
            )
            context.user_data["waiting_for"] = "phone"
        return

    elif data == "run_free":
        await run_free_selfbot(update, context)
        return

    elif data == "new_free":
        await query.edit_message_text(
            "📱 لطفاً شماره تلفنت رو با کد کشور تایپ کن و بفرست:\n\n"
            "مثال: `+989123456789`",
            parse_mode="Markdown"
        )
        context.user_data["waiting_for"] = "phone"
        return

    elif data == "back_main":
        await query.edit_message_text(
            "🤖 **به ربات سلف خوش اومدی!**\n\n"
            "یکی از گزینه‌های زیر رو انتخاب کن:",
            parse_mode="Markdown",
            reply_markup=main_keyboard()
        )
        return

    elif data == "stop_selfbot":
        if telegram_id in running_bots:
            try:
                running_bots[telegram_id]["task"].cancel()
            except:
                pass
            try:
                await running_bots[telegram_id]["client"].disconnect()
            except:
                pass
            del running_bots[telegram_id]
        await query.edit_message_text(
            "🛑 سلف‌بات متوقف شد.",
            reply_markup=main_keyboard()
        )
        return

# ────────────── دریافت پیام‌های متنی ──────────────
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = update.effective_user.id
    text = update.message.text.strip()

    is_member = await check_membership(context, telegram_id)
    if not is_member:
        await update.message.reply_text(
            "⚠️ **اول باید تو کانال عضو بشی!**",
            parse_mode="Markdown",
            reply_markup=membership_keyboard()
        )
        return

    waiting_for = context.user_data.get("waiting_for")

    if not waiting_for:
        await update.message.reply_text("❌ لطفاً اول /start بزن.")
        return

    if waiting_for == "phone":
        if not text.startswith("+"):
            await update.message.reply_text("❌ لطفاً شماره رو با + شروع کن. مثال: `+989123456789`", parse_mode="Markdown")
            return

        temp_data[telegram_id] = {"phone": text}

        try:
            client = TelegramClient(
                StringSession(),
                api_id=API_ID,
                api_hash=API_HASH,
                device_model="Min Self | Free",
                system_version="14.0",
                app_version="10.14.0",
                lang_code="fa"
            )

            telethon_clients[telegram_id] = client
            await client.connect()

            sent = await client.send_code_request(text)
            temp_data[telegram_id]["phone_code_hash"] = sent.phone_code_hash
            temp_data[telegram_id]["client"] = client

            await update.message.reply_text(
                f"📨 کد تأیید به **{text}** ارسال شد.\n\n"
                "لطفاً کد ۵ رقمی رو تایپ کن و بفرست:",
                parse_mode="Markdown"
            )
            context.user_data["waiting_for"] = "code"

        except Exception as e:
            error_text = str(e)
            if "Flood" in error_text or "flood" in error_text:
                await update.message.reply_text(
                    "⏳ **تلگرام محدودیت گذاشته!**\n\n"
                    "چند دقیقه صبر کن و دوباره تلاش کن.\n"
                    f"جزئیات: {error_text}",
                    parse_mode="Markdown"
                )
            else:
                await update.message.reply_text(f"❌ خطا: {error_text}\n\nدوباره /start بزن.")

            if telegram_id in telethon_clients:
                try:
                    await telethon_clients[telegram_id].disconnect()
                except:
                    pass
                telethon_clients.pop(telegram_id, None)
            temp_data.pop(telegram_id, None)
            context.user_data.clear()

    elif waiting_for == "code":
        if telegram_id not in temp_data or telegram_id not in telethon_clients:
            await update.message.reply_text("❌ لطفاً /start بزن و دوباره از اول شروع کن.")
            context.user_data.clear()
            return

        phone = temp_data[telegram_id]["phone"]
        phone_code_hash = temp_data[telegram_id]["phone_code_hash"]
        client = telethon_clients[telegram_id]

        try:
            await client.sign_in(phone, text, phone_code_hash=phone_code_hash)
            me = await client.get_me()

            string_session = client.session.save()
            save_session(telegram_id, phone, string_session)

            await client.disconnect()

            temp_data.pop(telegram_id, None)
            telethon_clients.pop(telegram_id, None)

            context.user_data.clear()

            keyboard = [
                [InlineKeyboardButton("🚀 اجرای سلف", callback_data="run_free")],
                [InlineKeyboardButton("🔙 برگشت", callback_data="back_main")]
            ]

            await update.message.reply_text(
                f"✅ **ورود موفق!** 🎉\n"
                f"👤 {me.first_name}\n"
                f"📱 {phone}\n\n"
                "حالا می‌تونی سلف رو اجرا کنی:",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )

        except SessionPasswordNeededError:
            await update.message.reply_text(
                "🔐 **حسابت تأیید دو مرحله‌ای داره!**\n\n"
                "رمز عبور (Cloud Password) رو بفرست:",
                parse_mode="Markdown"
            )
            context.user_data["waiting_for"] = "password"
            return

        except Exception as e:
            error = str(e)

            if "PHONE_CODE_INVALID" in error or "code is invalid" in error.lower() or "CodeInvalid" in error:
                await update.message.reply_text(
                    "❌ **کد اشتباهه!**\n\n"
                    "💡 نکات:\n"
                    "• کد رو دقیق وارد کن\n"
                    "• صبر کن کد جدید بیاد و دوباره شروع کن\n"
                    "• /start بزن و از اول با شماره شروع کن",
                    parse_mode="Markdown"
                )
                try:
                    if telegram_id in telethon_clients:
                        await telethon_clients[telegram_id].disconnect()
                except:
                    pass
                telethon_clients.pop(telegram_id, None)
                temp_data.pop(telegram_id, None)
                context.user_data.clear()

            elif "PHONE_CODE_EXPIRED" in error or "expired" in error.lower():
                await update.message.reply_text("❌ کد منقضی شد. /start بزن دوباره.")
                if telegram_id in telethon_clients:
                    try:
                        await telethon_clients[telegram_id].disconnect()
                    except:
                        pass
                    telethon_clients.pop(telegram_id, None)
                temp_data.pop(telegram_id, None)
                context.user_data.clear()
            else:
                await update.message.reply_text(f"❌ خطا: {error}\n\n/start")
                if telegram_id in telethon_clients:
                    try:
                        await telethon_clients[telegram_id].disconnect()
                    except:
                        pass
                    telethon_clients.pop(telegram_id, None)
                temp_data.pop(telegram_id, None)
                context.user_data.clear()

    elif waiting_for == "password":
        if telegram_id not in telethon_clients:
            await update.message.reply_text("❌ لطفاً /start بزن و از اول شروع کن.")
            context.user_data.clear()
            return

        client = telethon_clients[telegram_id]
        phone = temp_data.get(telegram_id, {}).get("phone", "")

        try:
            await client.sign_in(password=text)
            me = await client.get_me()

            string_session = client.session.save()
            save_session(telegram_id, phone, string_session)

            await client.disconnect()

            temp_data.pop(telegram_id, None)
            telethon_clients.pop(telegram_id, None)

            context.user_data.clear()

            keyboard = [
                [InlineKeyboardButton("🚀 اجرای سلف", callback_data="run_free")],
                [InlineKeyboardButton("🔙 برگشت", callback_data="back_main")]
            ]

            await update.message.reply_text(
                f"✅ **ورود موفق!** 🎉\n"
                f"👤 {me.first_name}\n\n"
                "حالا می‌تونی سلف رو اجرا کنی:",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )

        except Exception as e:
            error = str(e)
            if "PASSWORD_HASH_INVALID" in error or "password" in error.lower():
                await update.message.reply_text("❌ رمز اشتباهه. دوباره بفرست:")
            else:
                await update.message.reply_text(f"❌ خطا: {error}")
                context.user_data.clear()
                if telegram_id in telethon_clients:
                    try:
                        await telethon_clients[telegram_id].disconnect()
                    except:
                        pass
                    telethon_clients.pop(telegram_id, None)

# ────────────── ساعت ایران ──────────────
IRAN_TZ = timezone(timedelta(hours=3, minutes=30))

def get_iran_time():
    now = datetime.now(IRAN_TZ)
    return now.strftime("%H:%M")

# ────────────── اجرای سلف رایگان ──────────────
async def run_free_selfbot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = update.effective_user.id
    query = update.callback_query

    if telegram_id in running_bots:
        await query.edit_message_text("⚠️ سلف شما در حال اجراست!")
        return

    session_string = get_session(telegram_id)
    if not session_string:
        await query.edit_message_text("❌ سشنی نداری! اول /start بزن.")
        return

    try:
        client = TelegramClient(
            StringSession(session_string),
            api_id=API_ID,
            api_hash=API_HASH,
            device_model="Samsung Galaxy S24",
            system_version="14.0",
            app_version="10.14.0",
            lang_code="fa"
        )

        await client.start()
        me = await client.get_me()
        original_first_name = me.first_name
        original_last_name = me.last_name or ""

        bold_mode = True
        auto_reply = False
        auto_text = "⏳ الان در دسترس نیستم"
        clock_running = True
        clock_interval = 30  # ثانیه

        # ─────────── تابع بروزرسانی ساعت ───────────
        async def update_clock():
            nonlocal clock_running, clock_interval
            while clock_running:
                try:
                    time_str = get_iran_time()
                    display_name = f"⏰ {time_str}"
                    await client(functions.account.UpdateProfileRequest(
                        first_name=display_name,
                        last_name=""
                    ))
                except Exception as e:
                    logger.error(f"Clock update error: {e}")
                    # اگه خطای flood خورد، اینتروال رو بیشتر کن
                    if "FLOOD" in str(e).upper():
                        clock_interval = 60
                await asyncio.sleep(clock_interval)

        # ─────────── راهنما ───────────
        @client.on(events.NewMessage(outgoing=True, pattern=r"^راهنما$"))
        async def help_handler(event):
            nonlocal bold_mode, auto_reply, auto_text, clock_running, clock_interval
            await event.edit(
                "📚 **راهنما**\n\n"
                "`بولد روشن` - فعال کردن بولد\n"
                "`بولد خاموش` - غیرفعال کردن بولد\n"
                "`منشی روشن` - فعال کردن منشی\n"
                "`منشی خاموش` - غیرفعال کردن منشی\n"
                "`متن منشی <متن>` - تنظیم متن منشی\n"
                "`ساعت روشن` - فعال کردن ساعت روی اسم\n"
                "`ساعت خاموش` - غیرفعال کردن ساعت\n"
                f"\nوضعیت: بولد={'✅' if bold_mode else '❌'} | منشی={'✅' if auto_reply else '❌'} | ساعت={'✅' if clock_running else '❌'}"
            )

        @client.on(events.NewMessage(outgoing=True, pattern=r"^بولد روشن$"))
        async def bold_on(event):
            nonlocal bold_mode
            bold_mode = True
            await event.edit("✅ بولد فعال شد")

        @client.on(events.NewMessage(outgoing=True, pattern=r"^بولد خاموش$"))
        async def bold_off(event):
            nonlocal bold_mode
            bold_mode = False
            await event.edit("❌ بولد خاموش شد")

        @client.on(events.NewMessage(outgoing=True, pattern=r"^منشی روشن$"))
        async def auto_on(event):
            nonlocal auto_reply
            auto_reply = True
            await event.edit("✅ منشی فعال شد")

        @client.on(events.NewMessage(outgoing=True, pattern=r"^منشی خاموش$"))
        async def auto_off(event):
            nonlocal auto_reply
            auto_reply = False
            await event.edit("❌ منشی خاموش شد")

        @client.on(events.NewMessage(outgoing=True, pattern=r"^متن منشی "))
        async def set_auto_text(event):
            nonlocal auto_text
            auto_text = event.raw_text.replace("متن منشی ", "")
            await event.edit("✍️ متن منشی تنظیم شد")

        @client.on(events.NewMessage(outgoing=True, pattern=r"^ساعت روشن$"))
        async def clock_on(event):
            nonlocal clock_running
            if not clock_running:
                clock_running = True
                asyncio.create_task(update_clock())
            await event.edit("✅ ساعت فعال شد. اسمت هر ۳۰ ثانیه آپدیت میشه ⏰")

        @client.on(events.NewMessage(outgoing=True, pattern=r"^ساعت خاموش$"))
        async def clock_off(event):
            nonlocal clock_running
            clock_running = False
            try:
                await client(functions.account.UpdateProfileRequest(
                    first_name=original_first_name,
                    last_name=original_last_name
                ))
            except:
                pass
            await event.edit("❌ ساعت خاموش شد. اسم قبلی برگشت.")

        @client.on(events.NewMessage(outgoing=True))
        async def bold_handler(event):
            nonlocal bold_mode
            if bold_mode and event.raw_text and not event.raw_text.startswith(("بولد", "منشی", "متن منشی", "راهنما", "ساعت")):
                await event.edit(f"**{event.raw_text}**")

        @client.on(events.NewMessage(incoming=True, func=lambda e: e.is_private))
        async def auto_reply_handler(event):
            nonlocal auto_reply, auto_text
            if auto_reply and event.raw_text:
                await event.reply(auto_text)

        # ─────────── شروع تسک ساعت ───────────
        clock_task = asyncio.create_task(update_clock())

        running_bots[telegram_id] = {
            "client": client,
            "task": clock_task
        }

        await query.edit_message_text(
            f"✅ **سلف بات Telethon اجرا شد** 🚀\n\n"
            f"👤 {me.first_name}\n\n"
            "برو پی‌وی خودت و بنویس «راهنما»\n"
            "برای ساعت بنویس `ساعت روشن`",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🛑 توقف", callback_data="stop_selfbot")]
            ])
        )

    except Exception as e:
        running_bots.pop(telegram_id, None)
        await query.edit_message_text(f"❌ خطا: {str(e)}")

# ────────────── خطا ──────────────
async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.warning(f"Update {update} caused error {context.error}")

# ────────────── MAIN ──────────────
def main():
    init_db()

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_error_handler(error_handler)

    print("🤖 ربات در حال اجراست...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()