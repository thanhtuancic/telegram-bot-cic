import os
import logging
import aiohttp
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
    Application,
)
from bs4 import BeautifulSoup
from datetime import datetime, time, timedelta, timezone
from flask import Flask, request
from waitress import serve
import asyncio

# Cấu hình logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Biến toàn cục
CHAT_ID = None
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN") or "YOUR_DUMMY_TOKEN_FOR_LOCAL_DEBUG"

# Hàm lấy tin tức từ Coin68 (bất đồng bộ)
async def get_news_coin68():
    news_list = ["🗞️ *Tin tức từ Coin68*:"]
    url = "https://coin68.com/"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=10) as response:
                soup = BeautifulSoup(await response.text(), "html.parser")
                articles = soup.find_all("div", {"class": "MuiBox-root css-fv3lde"})
                for idx, article in enumerate(articles[:5], start=1):
                    link_tag = article.find("a", href=True)
                    title_tag = article.find(
                        "span", {"class": "MuiTypography-root MuiTypography-metaSemi css-1dk5p1t"}
                    )
                    if link_tag and title_tag:
                        title = title_tag.text.strip()
                        link = link_tag["href"]
                        if not link.startswith("http"):
                            link = url.rstrip("/") + link
                        news_list.append(f"[{idx}. {title}]({link})")
    except Exception as e:
        logger.error(f"❌ Error fetching Coin68: {e}")
    return "\n".join(news_list) if len(news_list) > 1 else "Không tìm thấy tin tức từ Coin68!"

# Hàm lấy tin tức từ Allinstation (bất đồng bộ)
async def get_news_allinstation():
    news_list = ["🗞️ *Tin tức từ Allinstation*:"]
    url = "https://allinstation.com/tin-tuc/"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=10) as response:
                soup = BeautifulSoup(await response.text(), "html.parser")
                articles = soup.find_all("div", {"class": "col post-item"})
                for idx, article in enumerate(articles[:5], start=6):
                    title_tag = article.find("h3", {"class": "post-title is-large"})
                    link_tag = article.find("a", href=True)
                    if title_tag and link_tag:
                        title = title_tag.text.strip()
                        link = link_tag["href"]
                        news_list.append(f"[{idx}. {title}]({link})")
    except Exception as e:
        logger.error(f"❌ Error fetching Allinstation: {e}")
    return "\n".join(news_list) if len(news_list) > 1 else "Không tìm thấy tin tức từ Allinstation!"

# Gộp tin tức từ cả hai nguồn
async def get_all_news():
    coin68_news = await get_news_coin68()
    allin_news = await get_news_allinstation()
    return f"{coin68_news}\n\n{allin_news}"

# Hàm gửi tin tự động
async def auto_send_news(context: ContextTypes.DEFAULT_TYPE) -> None:
    global CHAT_ID
    if not CHAT_ID:
        logger.warning("⚠️ No CHAT_ID set, bot not used yet!")
        return
    now_vn = datetime.now(timezone.utc) + timedelta(hours=7)
    if time(9, 0) <= now_vn.time() <= time(22, 0):
        try:
            await context.bot.send_message(
                chat_id=CHAT_ID,
                text=await get_all_news(),
                parse_mode="Markdown",
                disable_web_page_preview=True,
            )
            logger.info(f"✅ Sent auto news at {now_vn.strftime('%H:%M')}")
        except Exception as e:
            logger.error(f"❌ Error sending auto news: {e}")

# Lệnh /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    global CHAT_ID
    CHAT_ID = update.message.chat_id
    await update.message.reply_text("Chào mừng bạn! Dùng /news để nhận tin tức mới.")
    logger.info(f"✅ Received /start from CHAT_ID: {CHAT_ID}")

# Lệnh /news
async def news(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    global CHAT_ID
    CHAT_ID = update.message.chat_id
    try:
        await update.message.reply_text(
            await get_all_news(),
            parse_mode="Markdown",
            disable_web_page_preview=True,
        )
        logger.info(f"✅ Replied /news to CHAT_ID: {CHAT_ID}")
    except Exception as e:
        logger.error(f"❌ Error replying /news: {e}")

# Thiết lập JobQueue
async def setup_jobs(application: Application):
    application.job_queue.run_repeating(auto_send_news, interval=10800, first=10)
    logger.info("✅ JobQueue setup for 3h interval")

# Flask app
app_flask = Flask(__name__)
telegram_application_instance = None

# Health check endpoint
@app_flask.route("/news", methods=["GET", "HEAD"])
def health_check():
    logger.info(f"Received health check request: {request.method} {request.url}")
    return "OK", 200

# Webhook endpoint
@app_flask.route("/news", methods=["POST"])
async def telegram_webhook():
    global telegram_application_instance
    if telegram_application_instance:
        try:
            update = Update.de_json(request.get_json(), telegram_application_instance.bot)
            await telegram_application_instance.process_update(update)
            return "OK", 200
        except Exception as e:
            logger.error(f"❌ Error processing webhook: {e}")
            return "Error", 500
    logger.error("Telegram Application instance not initialized.")
    return "Internal Server Error", 500

# Hàm thiết lập webhook
async def set_webhook(webhook_host):
    webhook_url = f"https://{webhook_host}/news"
    async with aiohttp.ClientSession() as session:
        async with session.get(
            f"https://api.telegram.org/bot{TOKEN}/setWebhook?url={webhook_url}"
        ) as resp:
            response = await resp.json()
            logger.info(f"Webhook setup response: {response}")
            if not response.get("ok"):
                logger.error(f"Failed to set webhook: {response}")

# Hàm khởi động bot
async def start_bot():
    global telegram_application_instance
    telegram_application_instance = (
        ApplicationBuilder().token(TOKEN).post_init(setup_jobs).build()
    )
    telegram_application_instance.add_handler(CommandHandler("start", start))
    telegram_application_instance.add_handler(CommandHandler("news", news))
    telegram_application_instance.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, news)
    )
    
    # Khởi tạo Application
    await telegram_application_instance.initialize()
    logger.info("✅ Application initialized")

    # Thiết lập webhook
    WEBHOOK_HOST = os.getenv("RENDER_EXTERNAL_HOSTNAME")
    if WEBHOOK_HOST:
        await set_webhook(WEBHOOK_HOST)
    else:
        logger.warning("⚠️ No RENDER_EXTERNAL_HOSTNAME set, skipping webhook setup")

def main():
    WEBHOOK_HOST = os.getenv("RENDER_EXTERNAL_HOSTNAME")
    PORT = int(os.getenv("PORT", "10000"))

    if WEBHOOK_HOST:
        logger.info(f"🚀 Starting bot with webhook on port {PORT}")
        # Chạy start_bot trong event loop
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(start_bot())
        # Chạy Flask server
        serve(app_flask, host="0.0.0.0", port=PORT)
    else:
        logger.info("💻 Running bot in polling mode")
        telegram_application_instance = (
            ApplicationBuilder().token(TOKEN).post_init(setup_jobs).build()
        )
        telegram_application_instance.add_handler(CommandHandler("start", start))
        telegram_application_instance.add_handler(CommandHandler("news", news))
        telegram_application_instance.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, news)
        )
        telegram_application_instance.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()