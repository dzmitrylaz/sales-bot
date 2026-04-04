from telegram.ext import ApplicationBuilder
from config import BOT_TOKEN

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    print("Bot app created successfully")

if __name__ == "__main__":
    main()