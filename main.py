import os
import logging
import aiohttp
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    Application,
    ApplicationHandlerStop,
)
from telegram.error import Conflict
from bs4 import BeautifulSoup
from datetime import datetime, time, timedelta, timezone

# Cấu hình logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Biến toàn cục
CHAT_ID = None
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    logger.error("⚠️ Lỗi: Chưa có TELEGRAM_BOT_TOKEN trong biến môi trường!")
    raise ValueError("TELEGRAM_BOT_TOKEN không được thiết lập!")

# Hàm lấy tin từ Coin68
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
        logger.error(f"❌ Lỗi khi lấy tin từ Coin68: {e}")
    return "\n".join(news_list) if len(news_list) > 1 else "Không tìm thấy tin tức từ Coin68!"

# Hàm lấy tin từ Allinstation
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
        logger.error(f"❌ Lỗi khi lấy tin từ Allinstation: {e}")
    return "\n".join(news_list) if len(news_list) > 1 else "Không tìm thấy tin tức từ Allinstation!"

# Gộp tin
async def get_all_news():
    coin68_news = await get_news_coin68()
    allin_news = await get_news_allinstation()
    return f"{coin68_news}\n\n{allin_news}"

# Gửi tin tự động
async def auto_send_news(context: ContextTypes.DEFAULT_TYPE) -> None:
    global CHAT_ID
    if not CHAT_ID:
        logger.warning("⚠️ Chưa có CHAT_ID, bot chưa được sử dụng trong nhóm!")
        return
    now_vn = datetime.now(timezone.utc) + timedelta(hours=7)
    if time(9, 0) <= now_vn.time() <= time(22, 0):
        news_message = await get_all_news()
        try:
            await context.bot.send_message(
                chat_id=CHAT_ID,
                text=news_message,
                parse_mode="Markdown",
                disable_web_page_preview=True,
            )
            logger.info(f"✅ Đã gửi tin tự động lúc {now_vn.strftime('%H:%M')} đến CHAT_ID: {CHAT_ID}")
        except Exception as e:
            logger.error(f"❌ Lỗi gửi tin tự động: {e}")
    else:
        logger.info(f"⏳ {now_vn.strftime('%H:%M')} - Ngoài giờ gửi tin (09:00-22:00), bỏ qua...")

# Lệnh /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    global CHAT_ID
    CHAT_ID = update.message.chat_id
    await update.message.reply_text("Chào mừng bạn! Dùng /news để nhận tin tức mới nhất về coin.")
    logger.info(f"✅ Đã nhận lệnh /start từ CHAT_ID: {CHAT_ID}")

# Lệnh /news
async def news(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    global CHAT_ID
    CHAT_ID = update.message.chat_id
    logger.info(f"✅ Đã cập nhật CHAT_ID: {CHAT_ID}")
    news_message = await get_all_news()
    try:
        await update.message.reply_text(
            news_message,
            parse_mode="Markdown",
            disable_web_page_preview=True,
        )
        logger.info(f"✅ Đã trả lời lệnh /news đến CHAT_ID: {CHAT_ID}")
    except Exception as e:
        logger.error(f"❌ Lỗi gửi tin nhắn: {e}")

# Error handler
async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error(f"❌ Lỗi: {context.error}")
    if isinstance(context.error, Conflict):
        logger.error("Xung đột getUpdates, chỉ một instance bot được phép chạy!")
        raise ApplicationHandlerStop

# Thiết lập JobQueue
async def setup_jobs(application: Application):
    application.job_queue.run_repeating(auto_send_news, interval=10800, first=10)
    logger.info("✅ Đã thiết lập JobQueue gửi tin mỗi 3 giờ")

# Chạy bot
def main():
    app = ApplicationBuilder().token(TOKEN).post_init(setup_jobs).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("news", news))
    app.add_error_handler(error_handler)
    logger.info("🚀 Bot đang khởi động ở chế độ polling...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()