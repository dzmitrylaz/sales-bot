from telegram.ext import ApplicationBuilder
from config import BOT_TOKEN
from db import init_db

def main():
    init_db()
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    print("Bot app created successfully and database initialized")

if __name__ == "__main__":
    main()