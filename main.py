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
from telegram.error import Conflict, TelegramError
from bs4 import BeautifulSoup
from datetime import datetime, time, timedelta, timezone
from flask import Flask

# Cấu hình logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Biến toàn cục
CHAT_ID = None

# Load token từ biến môi trường
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    logger.error("⚠️ Lỗi: Chưa có TELEGRAM_BOT_TOKEN trong biến môi trường!")
    raise ValueError("TELEGRAM_BOT_TOKEN không được thiết lập!")

# Khởi tạo Flask (chỉ để Render phát hiện cổng)
app_http = Flask(__name__)

# Route đơn giản để giữ Web Service sống
@app_http.route('/')
def health_check():
    logger.info("✅ Health check received")
    return "Bot is running", 200

# Hàm lấy tin từ Coin68
async def get_news_coin68():
    news_list = ["📰 *Tin tức từ Coin68:*"]
    url = "https://coin68.com/"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"}) as response:
                if response.status != 200:
                    logger.error(f"❌ Lỗi HTTP khi lấy tin từ Coin68: Status {response.status}")
                    return "\n".join(news_list)
                soup = BeautifulSoup(await response.text(), "html.parser")
                articles = soup.find_all("div", {"class": "MuiBox-root css-fv3lde"})
                for idx, article in enumerate(articles[:5], start=1):
                    link_tag = article.find("a", href=True)
                    title_tag = article.find("span", {"class": "MuiTypography-root MuiTypography-metaSemi css-1dk5p1t"})
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
    news_list = ["📰 *Tin tức từ Allinstation:*"]
    url = "https://allinstation.com/tin-tuc/"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"}) as response:
                if response.status != 200:
                    logger.error(f"❌ Lỗi HTTP khi lấy tin từ Allinstation: Status {response.status}")
                    return "\n".join(news_list)
                soup = BeautifulSoup(await response.text(), "html.parser")
                articles = soup.find_all("div", {"class": "col post-item"})
                if not articles:
                    logger.warning("⚠️ Không tìm thấy thẻ div class='col post-item' trên trang Allinstation")
                    return "\n".join(news_list)
                for idx, article in enumerate(articles[:5], start=6):
                    title_tag = article.find("h3", {"class": "post-title is-large"})
                    link_tag = article.find("a", href=True)
                    if title_tag and link_tag:
                        title = title_tag.text.strip()
                        link = link_tag["href"]
                        news_list.append(f"[{idx}. {title}]({link})")
                    else:
                        logger.warning(f"⚠️ Không tìm thấy tiêu đề hoặc liên kết cho bài viết {idx}")
    except Exception as e:
        logger.error(f"❌ Lỗi khi lấy tin từ Allinstation: {e}")
    return "\n".join(news_list) if len(news_list) > 1 else "Không tìm thấy tin tức từ Allinstation!"

# Gộp tin từ cả 2 trang
async def get_all_news():
    coin68_news = await get_news_coin68()
    allin_news = await get_news_allinstation()
    return f"{coin68_news}\n\n{allin_news}"

# Gửi tin tự động chỉ trong khoảng 09:00 - 22:00
async def auto_send_news(context: ContextTypes.DEFAULT_TYPE) -> None:
    global CHAT_ID
    if not CHAT_ID:
        logger.warning("⚠️ Chưa có CHAT_ID, bot chưa được sử dụng trong nhóm!")
        return

    now_utc = datetime.now(timezone.utc)
    now_vn = now_utc + timedelta(hours=7)  # UTC+7
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

# Lệnh /news để lấy tin
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

# Thiết lập JobQueue
async def setup_jobs(application: Application):
    application.job_queue.run_repeating(auto_send_news, interval=10800, first=10)
    logger.info("✅ Đã thiết lập JobQueue gửi tin mỗi 3 giờ")

# Error handler
async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error(f"❌ Lỗi: {context.error}")
    if isinstance(context.error, Conflict):
        logger.error("Xung đột getUpdates hoặc webhook, cần xóa webhook trước!")
        raise ApplicationHandlerStop
    elif isinstance(context.error, TelegramError):
        logger.error(f"Lỗi Telegram: {context.error.message}")
    raise context.error

# Cấu hình & chạy bot
def main():
    # Chạy Flask trên cổng Render cung cấp
    port = int(os.getenv("PORT", 8080))
    app_http.run(host="0.0.0.0", port=port, threaded=True)

    # Khởi động bot polling trong thread riêng
    app = ApplicationBuilder().token(TOKEN).post_init(setup_jobs).build()
    app.add_handler(CommandHandler("news", news))
    app.add_error_handler(error_handler)
    logger.info("🚀 Bot đang khởi động ở chế độ polling...")
    try:
        app.run_polling(allowed_updates=Update.ALL_TYPES)
    except Exception as e:
        logger.error(f"❌ Lỗi khi chạy bot: {e}")
        raise

if __name__ == "__main__":
    main()