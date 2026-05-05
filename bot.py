from datetime import datetime, time
from zoneinfo import ZoneInfo
import re
from html import escape

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)
from telegram.constants import ParseMode, ChatMemberStatus

from config import BOT_TOKEN
from db import (
    init_db,
    set_chat_id,
    set_dashboard_message_id,
    get_settings,
    get_dashboard_message_id,
    get_chat_id,
    get_current_date,
    reset_daily_counts,
    has_milestone_been_hit,
    mark_milestone_hit,
    add_sale_message,
    deactivate_sale_by_message,
    deactivate_sale_by_code,
    get_active_sale_by_message,
    get_active_sale_by_code,
    rebuild_counts_from_sales,
    get_today_total,
    get_leaderboard,
    get_all_operator_counts,
    ignore_user,
    unignore_user,
    is_user_ignored,
    get_ignored_users,
)


GERMAN_TZ = ZoneInfo("Europe/Berlin")

GOAL = 70
STEP = 10
MILESTONES = tuple(range(STEP, GOAL + STEP, STEP))

# Progress report every 2 hours during German daytime.
PROGRESS_REPORT_HOURS = 2
PROGRESS_REPORT_START_HOUR = 10
PROGRESS_REPORT_END_HOUR = 20

# Replace this with a valid Telegram animation file_id if needed.
GOAL_ANIMATION = "CgACAgIAAxkBAAFGeM1p0hIn2BPy-9ukL7GBA-y-VWxqJgACt48AAqARkUph1fssf_3FEjsE"

STRICT_ID_RE = re.compile(r"^\s*id[\s:#\-]*([0-9]{4,})?\b", re.IGNORECASE)
NUMBER_ONLY_RE = re.compile(r"^\s*#?\s*([0-9]{5,12})\s*$")
POSSIBLE_SALE_RE = re.compile(
    r"\b(?:bestellung|auftrag|verkauf|sale|order|заказ|продажа)\b.*?\b([0-9]{5,12})\b"
    r"|\b([0-9]{5,12})\b.*?\b(?:bestellung|auftrag|verkauf|sale|order|заказ|продажа)\b",
    re.IGNORECASE,
)


def get_today_string() -> str:
    return datetime.now(GERMAN_TZ).strftime("%Y-%m-%d")


def get_now_time_string() -> str:
    return datetime.now(GERMAN_TZ).strftime("%H:%M")


def ensure_today_is_current() -> None:
    today = get_today_string()
    saved_date = get_current_date()
    if saved_date != today:
        reset_daily_counts(today)


def extract_strict_sale_code(text: str) -> str | None:
    match = STRICT_ID_RE.search(text or "")
    if not match:
        return None

    # If the operator wrote only "id" without a number, still treat the message as a sale,
    # but sale_code stays None.
    return match.group(1)


def is_strict_sale_message(text: str) -> bool:
    return bool(STRICT_ID_RE.search(text or ""))


def extract_possible_sale_code(text: str) -> str | None:
    if not text:
        return None

    number_only = NUMBER_ONLY_RE.search(text)
    if number_only:
        return number_only.group(1)

    possible = POSSIBLE_SALE_RE.search(text)
    if possible:
        return possible.group(1) or possible.group(2)

    return None


def get_status_text(today_count: int) -> str:
    if today_count > GOAL:
        return "Ziel übertroffen"
    if today_count >= GOAL:
        return "Ziel erreicht"
    if today_count >= int(GOAL * 0.8):
        return "Fast geschafft"
    if today_count >= int(GOAL * 0.6):
        return "Starker Lauf"
    if today_count >= int(GOAL * 0.3):
        return "Kommt in Fahrt"
    if today_count > 0:
        return "Guter Start"
    return "Warten auf den ersten Verkauf"


def get_next_milestone(today_count: int) -> str:
    for milestone in MILESTONES:
        if today_count < milestone:
            return str(milestone)
    return "Ziel erreicht"


def get_level_for_count(count: int) -> str:
    if count >= 6:
        return "🔥 Hohes Leistungsniveau"
    if count >= 4:
        return "🎯 Zielniveau"
    if count >= 2:
        return "⚠️ Mindestniveau"
    if count == 1:
        return "❌ Unter Mindestniveau"
    return "⏳ Noch kein Verkauf heute"


def build_dashboard_text() -> str:
    today_count = get_today_total()
    leaderboard = get_leaderboard(limit=10)

    lines = [
        "🔥 <b>SALES-DASHBOARD</b>",
        "",
        f"Heute: <b>{today_count}</b> / {GOAL}",
        f"Status: <b>{get_status_text(today_count)}</b>",
        f"Next milestone: <b>{get_next_milestone(today_count)}</b>",
        "",
        "🏆 <b>Bestenliste</b>",
    ]

    if leaderboard:
        for idx, row in enumerate(leaderboard, start=1):
            lines.append(f"{idx}. {escape(row['display_name'])} — <b>{row['count']}</b>")
    else:
        lines.append("Noch keine Verkäufe heute")

    return "\n".join(lines)


def build_progress_report_text() -> str:
    rows = get_all_operator_counts()

    lines = [
        f"📊 <b>Zwischenstand — {get_now_time_string()}</b>",
        "",
        "🏆 <b>Operator-Fortschritt</b>",
        "",
    ]

    if rows:
        for idx, row in enumerate(rows, start=1):
            count = row["count"]
            sales_word = "Verkauf" if count == 1 else "Verkäufe"
            lines.extend([
                f"{idx}. {escape(row['display_name'])} — <b>{count}</b> {sales_word}",
                f"   {get_level_for_count(count)}",
                "",
            ])
    else:
        lines.extend([
            "Noch keine Verkäufe heute.",
            "",
        ])

    lines.extend([
        "📌 <b>Tagesorientierung:</b>",
        "⚠️ Mindestniveau: 2–3 Verkäufe",
        "🎯 Zielniveau: 4–5 Verkäufe",
        "🔥 Hohes Leistungsniveau: 5–6+ Verkäufe",
        "",
        "🚀 Weiter so — jeder Abschluss zählt.",
    ])

    return "\n".join(lines)


async def is_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    if update.effective_chat is None or update.effective_user is None:
        return False

    member = await context.bot.get_chat_member(
        chat_id=update.effective_chat.id,
        user_id=update.effective_user.id,
    )

    return member.status in (
        ChatMemberStatus.ADMINISTRATOR,
        ChatMemberStatus.OWNER,
    )


async def require_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    if await is_admin(update, context):
        return True

    if update.message:
        await update.message.reply_text("Nur Admins können diesen Befehl benutzen.")
    return False


async def update_dashboard(bot) -> None:
    chat_id = get_chat_id()
    dashboard_message_id = get_dashboard_message_id()

    if not chat_id or not dashboard_message_id:
        return

    await bot.edit_message_text(
        chat_id=chat_id,
        message_id=dashboard_message_id,
        text=build_dashboard_text(),
        parse_mode=ParseMode.HTML,
    )


def get_milestone_message(milestone: int) -> str:
    if milestone >= GOAL:
        return f"🎉 <b>ZIEL ERREICHT — {GOAL} / {GOAL}!</b>\nStarke Leistung."

    remaining = GOAL - milestone

    if remaining == STEP:
        return (
            f"🚀 <b>{milestone} Verkäufe erreicht!</b>\n"
            f"Letzter Push — nur noch {remaining}!"
        )

    if milestone >= int(GOAL * 0.8):
        return (
            f"🔥 <b>{milestone} Verkäufe erreicht!</b>\n"
            f"Fast geschafft — noch {remaining}!"
        )

    if milestone >= int(GOAL * 0.5):
        return f"💪 <b>{milestone} Verkäufe erreicht!</b>\nWeiter so — noch {remaining}!"

    return (
        f"🔥 <b>{milestone} Verkäufe erreicht!</b>\n"
        f"Noch {remaining} bis zum Ziel."
    )


async def maybe_send_milestone_message(bot, chat_id: int, today_count: int) -> None:
    for milestone in MILESTONES:
        if today_count >= milestone and not has_milestone_been_hit(milestone):
            mark_milestone_hit(milestone)

            await bot.send_message(
                chat_id=chat_id,
                text=get_milestone_message(milestone),
                parse_mode=ParseMode.HTML,
            )

            if milestone == GOAL:
                try:
                    await bot.send_animation(
                        chat_id=chat_id,
                        animation=GOAL_ANIMATION,
                        caption="🏆 Ziel erreicht!",
                    )
                except Exception as e:
                    print(f"Goal animation failed: {e}")


async def add_sale_from_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    source_message,
    manual: bool = False,
) -> bool:
    if update.effective_chat is None or source_message is None or source_message.from_user is None:
        return False

    saved_chat_id = get_chat_id()
    if saved_chat_id is None or update.effective_chat.id != saved_chat_id:
        return False

    ensure_today_is_current()

    user = source_message.from_user

    if is_user_ignored(user.id):
        if update.message:
            await update.message.reply_text("Dieser Benutzer ist von der Zählung ausgeschlossen.")
        return False

    text = source_message.text or source_message.caption or ""
    sale_code = extract_strict_sale_code(text) or extract_possible_sale_code(text)

    existing_by_message = get_active_sale_by_message(
        chat_id=update.effective_chat.id,
        message_id=source_message.message_id,
    )
    if existing_by_message:
        if update.message:
            await update.message.reply_text("ℹ️ Dieser Verkauf wurde bereits gezählt.")
        return False

    if sale_code:
        existing_by_code = get_active_sale_by_code(
            sale_date=get_today_string(),
            sale_code=sale_code,
        )
        if existing_by_code:
            if update.message:
                await update.message.reply_text("ℹ️ Diese Verkaufs-ID wurde bereits gezählt.")
            return False

    add_sale_message(
        chat_id=update.effective_chat.id,
        message_id=source_message.message_id,
        user_id=user.id,
        username=user.username,
        display_name=user.full_name,
        sale_date=get_today_string(),
        sale_code=sale_code,
        text=text,
        source="manual" if manual else "auto",
    )

    rebuild_counts_from_sales(get_today_string())

    today_count = get_today_total()

    try:
        await update_dashboard(context.bot)
        await maybe_send_milestone_message(
            bot=context.bot,
            chat_id=update.effective_chat.id,
            today_count=today_count,
        )
    except Exception as e:
        print(f"Failed to update dashboard or milestone: {e}")

    return True


async def midnight_reset_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    today = get_today_string()
    reset_daily_counts(today)

    chat_id = get_chat_id()
    if not chat_id:
        return

    try:
        await update_dashboard(context.bot)
    except Exception as e:
        print(f"Midnight reset failed: {e}")


async def progress_report_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = get_chat_id()
    if not chat_id:
        return

    ensure_today_is_current()

    now = datetime.now(GERMAN_TZ)
    if not (PROGRESS_REPORT_START_HOUR <= now.hour <= PROGRESS_REPORT_END_HOUR):
        return

    try:
        await context.bot.send_message(
            chat_id=chat_id,
            text=build_progress_report_text(),
            parse_mode=ParseMode.HTML,
        )
    except Exception as e:
        print(f"Progress report failed: {e}")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None:
        return

    await update.message.reply_text(
        "Bot is running. Use /setup in the group to create the dashboard."
    )


async def setup(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_chat is None or update.message is None:
        return

    chat = update.effective_chat

    if chat.type not in ("group", "supergroup"):
        await update.message.reply_text("Please use /setup inside your group.")
        return

    if not await require_admin(update, context):
        return

    chat_id = chat.id
    set_chat_id(chat_id)
    reset_daily_counts(get_today_string())

    dashboard_message = await update.message.reply_text(
        build_dashboard_text(),
        parse_mode=ParseMode.HTML,
    )

    set_dashboard_message_id(dashboard_message.message_id)

    try:
        await context.bot.pin_chat_message(
            chat_id=chat_id,
            message_id=dashboard_message.message_id,
            disable_notification=True,
        )
        await update.message.reply_text("Dashboard created and pinned successfully.")
    except Exception:
        await update.message.reply_text(
            "Dashboard created successfully.\n"
            "I could not pin it automatically, so please pin it manually."
        )


async def debug_settings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None:
        return

    if not await require_admin(update, context):
        return

    settings = get_settings()
    if settings is None:
        await update.message.reply_text("No settings found.")
        return

    text = (
        f"chat_id: {settings['chat_id']}\n"
        f"dashboard_message_id: {settings['dashboard_message_id']}\n"
        f"current_date: {settings['current_date']}\n"
        f"today_count: {settings['today_count']}\n"
        f"real_total_from_sales: {get_today_total()}"
    )
    await update.message.reply_text(text)


async def reset_now(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None:
        return

    if not await require_admin(update, context):
        return

    reset_daily_counts(get_today_string())
    await update_dashboard(context.bot)
    await update.message.reply_text("Dashboard reset manually.")


async def rebuild_today(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None:
        return

    if not await require_admin(update, context):
        return

    ensure_today_is_current()
    rebuild_counts_from_sales(get_today_string())
    await update_dashboard(context.bot)
    await update.message.reply_text("✅ Dashboard wurde neu berechnet.")


async def progress_now(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None:
        return

    ensure_today_is_current()
    await update.message.reply_text(
        build_progress_report_text(),
        parse_mode=ParseMode.HTML,
    )


async def add_sale(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None:
        return

    if not await require_admin(update, context):
        return

    if not update.message.reply_to_message:
        await update.message.reply_text("Bitte antworte mit /add_sale auf die Verkaufsnachricht.")
        return

    added = await add_sale_from_message(
        update=update,
        context=context,
        source_message=update.message.reply_to_message,
        manual=True,
    )

    if added:
        await update.message.reply_text("✅ Verkauf wurde manuell hinzugefügt.")


async def confirm_sale(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None:
        return

    if not update.message.reply_to_message:
        await update.message.reply_text("Bitte antworte mit /confirm_sale auf die Verkaufsnachricht.")
        return

    added = await add_sale_from_message(
        update=update,
        context=context,
        source_message=update.message.reply_to_message,
        manual=True,
    )

    if added:
        await update.message.reply_text("✅ Verkauf bestätigt und gezählt.")


async def remove_sale(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None or update.effective_chat is None:
        return

    if not await require_admin(update, context):
        return

    ensure_today_is_current()
    removed = False

    if update.message.reply_to_message:
        removed = deactivate_sale_by_message(
            chat_id=update.effective_chat.id,
            message_id=update.message.reply_to_message.message_id,
        )
    elif context.args:
        sale_code = context.args[0].strip()
        removed = deactivate_sale_by_code(
            sale_date=get_today_string(),
            sale_code=sale_code,
        )
    else:
        await update.message.reply_text(
            "Bitte antworte mit /remove_sale auf die Verkaufsnachricht oder nutze /remove_sale 123456."
        )
        return

    if removed:
        rebuild_counts_from_sales(get_today_string())
        await update_dashboard(context.bot)
        await update.message.reply_text("✅ Verkauf wurde entfernt.")
    else:
        await update.message.reply_text("Kein aktiver Verkauf gefunden.")


async def ignore_user_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None:
        return

    if not await require_admin(update, context):
        return

    if not update.message.reply_to_message or not update.message.reply_to_message.from_user:
        await update.message.reply_text("Bitte antworte mit /ignore_user auf eine Nachricht des Benutzers.")
        return

    user = update.message.reply_to_message.from_user
    ignore_user(user.id, user.username, user.full_name)

    # Remove already counted sales from today for this user.
    rebuild_counts_from_sales(get_today_string())

    await update_dashboard(context.bot)
    await update.message.reply_text(f"✅ {user.full_name} wird nicht mehr getrackt.")


async def unignore_user_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None:
        return

    if not await require_admin(update, context):
        return

    if update.message.reply_to_message and update.message.reply_to_message.from_user:
        user_id = update.message.reply_to_message.from_user.id
    elif context.args:
        try:
            user_id = int(context.args[0])
        except ValueError:
            await update.message.reply_text("Bitte User-ID korrekt angeben oder auf eine Nachricht antworten.")
            return
    else:
        await update.message.reply_text("Bitte antworte mit /unignore_user auf eine Nachricht oder nutze /unignore_user USER_ID.")
        return

    if unignore_user(user_id):
        rebuild_counts_from_sales(get_today_string())
        await update_dashboard(context.bot)
        await update.message.reply_text("✅ Benutzer wird wieder getrackt.")
    else:
        await update.message.reply_text("Benutzer war nicht in der Ignorierliste.")


async def ignored_users_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None:
        return

    if not await require_admin(update, context):
        return

    rows = get_ignored_users()
    if not rows:
        await update.message.reply_text("Keine ignorierten Benutzer.")
        return

    lines = ["🚫 Ignorierte Benutzer:"]
    for row in rows:
        lines.append(f"- {row['display_name']} — <code>{row['user_id']}</code>")

    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)


async def count_or_detect_sales(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_chat is None or update.message is None or update.effective_user is None:
        return

    saved_chat_id = get_chat_id()
    if saved_chat_id is None or update.effective_chat.id != saved_chat_id:
        return

    if is_user_ignored(update.effective_user.id):
        return

    text = update.message.text or update.message.caption or ""
    if not text:
        return

    ensure_today_is_current()

    if is_strict_sale_message(text):
        await add_sale_from_message(
            update=update,
            context=context,
            source_message=update.message,
            manual=False,
        )
        return

    possible_code = extract_possible_sale_code(text)
    if possible_code:
        await update.message.reply_text(
            "⚠️ Möglicher Verkauf erkannt.\n\n"
            "Falls das ein Verkauf ist, bitte auf diese Nachricht mit /confirm_sale antworten."
        )


async def handle_edited_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_chat is None or update.edited_message is None:
        return

    saved_chat_id = get_chat_id()
    if saved_chat_id is None or update.effective_chat.id != saved_chat_id:
        return

    ensure_today_is_current()

    edited = update.edited_message
    text = edited.text or edited.caption or ""

    existing = get_active_sale_by_message(
        chat_id=update.effective_chat.id,
        message_id=edited.message_id,
    )

    if existing and not is_strict_sale_message(text):
        deactivate_sale_by_message(
            chat_id=update.effective_chat.id,
            message_id=edited.message_id,
        )
        rebuild_counts_from_sales(get_today_string())
        await update_dashboard(context.bot)
        return

    if existing and is_strict_sale_message(text):
        # The message is still a sale. Rebuild to keep counts safe.
        rebuild_counts_from_sales(get_today_string())
        await update_dashboard(context.bot)
        return

    if not existing and is_strict_sale_message(text):
        # A normal message was edited into a sale.
        fake_update = update
        await add_sale_from_message(
            update=fake_update,
            context=context,
            source_message=edited,
            manual=False,
        )


def main():
    init_db()

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("setup", setup))
    app.add_handler(CommandHandler("debug_settings", debug_settings))
    app.add_handler(CommandHandler("reset_now", reset_now))
    app.add_handler(CommandHandler("rebuild_today", rebuild_today))
    app.add_handler(CommandHandler("progress_now", progress_now))
    app.add_handler(CommandHandler("add_sale", add_sale))
    app.add_handler(CommandHandler("confirm_sale", confirm_sale))
    app.add_handler(CommandHandler("remove_sale", remove_sale))
    app.add_handler(CommandHandler("ignore_user", ignore_user_command))
    app.add_handler(CommandHandler("unignore_user", unignore_user_command))
    app.add_handler(CommandHandler("ignored_users", ignored_users_command))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, count_or_detect_sales))
    app.add_handler(MessageHandler(filters.UpdateType.EDITED_MESSAGE, handle_edited_message))

    app.job_queue.run_daily(
        midnight_reset_job,
        time=time(hour=0, minute=0, second=0, tzinfo=GERMAN_TZ),
        name="midnight_reset",
    )

    app.job_queue.run_repeating(
        progress_report_job,
        interval=PROGRESS_REPORT_HOURS * 60 * 60,
        first=60,
        name="progress_report",
    )

    print("Bot is running...")
    app.run_polling()


if __name__ == "__main__":
    main()
