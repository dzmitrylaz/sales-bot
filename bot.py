from datetime import datetime, time

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)
from telegram.constants import ParseMode

from config import BOT_TOKEN
from db import (
    init_db,
    set_chat_id,
    set_dashboard_message_id,
    get_settings,
    get_leaderboard,
    increment_today_count,
    increment_user_count,
    get_today_count,
    get_dashboard_message_id,
    get_chat_id,
    get_current_date,
    reset_daily_counts,
    set_current_date,
    has_milestone_been_hit,
    mark_milestone_hit,
)


GOAL = 40
MILESTONES = (10, 20, 30, 40)

# Replace this later with a Telegram file_id
GOAL_ANIMATION = "AAMCAgADGQEAAUZpHWnQ-zwlr2vHezt03iEbchlhZBNjAAJekwAClJGJSuDp5mGoxcPSAQAHbQADOwQ"


def get_status_text(today_count: int) -> str:
    if today_count > 40:
        return "Ziel übertroffen"
    if today_count >= 40:
        return "Ziel erreicht"
    if today_count >= 30:
        return "Fast geschafft"
    if today_count >= 20
        return "Starker Lauf"
    if today_count >= 10:
        return "Kommt in Fahrt"
    if today_count > 0:
        return "Guter Start"
    return "Warten auf den ersten Verkauf"


def get_next_milestone(today_count: int) -> str:
    for milestone in (10, 20, 30, 40):
        if today_count < milestone:
            return str(milestone)
    return "Ziel erreicht"


def build_dashboard_text(today_count: int) -> str:
    leaderboard = get_leaderboard(limit=10)

    lines = [
        "🔥 <b>SALES-DASHBOARD</b>",
        "",
        f"Heute: {today_count} / 40",
        f"Status: <b>{get_status_text(today_count)}</b>",
        f"Next milestone: <b>{get_next_milestone(today_count)}</b>",
        "",
        "🏆 <b>Bestenliste</b>",
    ]

    if leaderboard:
        for idx, row in enumerate(leaderboard, start=1):
            lines.append(
                f"{idx}. {row['display_name']} — <b>{row['count']}</b>")
    else:
        lines.append("Noch keine Verkäufe heute")

    return "\n".join(lines)


def get_today_string() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def ensure_today_is_current() -> None:
    today = get_today_string()
    saved_date = get_current_date()

    if saved_date != today:
        reset_daily_counts(today)


async def update_dashboard(bot) -> None:
    chat_id = get_chat_id()
    dashboard_message_id = get_dashboard_message_id()
    today_count = get_today_count()

    if not chat_id or not dashboard_message_id:
        return

    await bot.edit_message_text(
        chat_id=chat_id,
        message_id=dashboard_message_id,
        text=build_dashboard_text(today_count),
        parse_mode=ParseMode.HTML,
    )


def get_milestone_message(milestone: int) -> str:
    if milestone == 10:
        return "✅ <b>10 Verkäufe erreicht!</b>\nGuter Start — es geht los."
    if milestone == 20:
        return "🔥 <b>20 Verkäufe erreicht!</b>\nHalbzeit."
    if milestone == 30:
        return "🚀 <b>30 Verkäufe erreicht!</b>\nJetzt der letzte Push."
    if milestone == 40:
        return "🎉 <b>ZIEL ERREICHT — 40 / 40!</b>\nStarke Leistung."
    return f"<b>{milestone} erreicht!</b>"


async def maybe_send_milestone_message(bot, chat_id: int, today_count: int) -> None:
    for milestone in MILESTONES:
        if today_count >= milestone and not has_milestone_been_hit(milestone):
            mark_milestone_hit(milestone)

            await bot.send_message(
                chat_id=chat_id,
                text=get_milestone_message(milestone),
                parse_mode=ParseMode.HTML,
            )

            if milestone == 40:
                await bot.send_animation(
                    chat_id=chat_id,
                    animation=GOAL_ANIMATION,
                    caption="🏆 Ziel erreicht!"
                )


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


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None:
        return

    await update.message.reply_text(
        "Bot is running. Use /setup in the test group to create the dashboard."
    )


async def setup(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_chat is None or update.message is None:
        return

    chat = update.effective_chat

    if chat.type not in ("group", "supergroup"):
        await update.message.reply_text("Please use /setup inside your test group.")
        return

    chat_id = chat.id
    set_chat_id(chat_id)
    reset_daily_counts(get_today_string())

    dashboard_text = build_dashboard_text(today_count=0)

    dashboard_message = await update.message.reply_text(
        dashboard_text,
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

    settings = get_settings()
    if settings is None:
        await update.message.reply_text("No settings found.")
        return

    text = (
        f"chat_id: {settings['chat_id']}\n"
        f"dashboard_message_id: {settings['dashboard_message_id']}\n"
        f"current_date: {settings['current_date']}\n"
        f"today_count: {settings['today_count']}"
    )
    await update.message.reply_text(text)


async def reset_now(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None:
        return

    reset_daily_counts(get_today_string())
    await update_dashboard(context.bot)
    await update.message.reply_text("Dashboard reset manually.")


async def count_sales(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_chat is None or update.message is None or update.effective_user is None:
        return

    saved_chat_id = get_chat_id()
    if saved_chat_id is None:
        return

    if update.effective_chat.id != saved_chat_id:
        return

    text = update.message.text
    if not text:
        return

    if not text.strip().lower().startswith("id"):
        return

    ensure_today_is_current()

    user = update.effective_user
    username = user.username
    display_name = user.full_name

    today_count = increment_today_count()
    increment_user_count(
        user_id=user.id,
        username=username,
        display_name=display_name,
    )

    try:
        await update_dashboard(context.bot)
        await maybe_send_milestone_message(
            bot=context.bot,
            chat_id=update.effective_chat.id,
            today_count=today_count,
        )
    except Exception as e:
        print(f"Failed to update dashboard or milestone: {e}")


def main():
    init_db()

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("setup", setup))
    app.add_handler(CommandHandler("debug_settings", debug_settings))
    app.add_handler(CommandHandler("reset_now", reset_now))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, count_sales))

    # Daily midnight reset
    app.job_queue.run_daily(
        midnight_reset_job,
        time=time(hour=0, minute=0, second=0),
        name="midnight_reset",
    )

    print("Bot is running...")
    app.run_polling()


if __name__ == "__main__":
    main()