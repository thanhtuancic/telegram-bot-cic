from telegram import Update
import os
# from dotenv import load_dotenv # Không cần dùng load_dotenv khi deploy lên Render vì biến môi trường được set trực tiếp
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, Application, MessageHandler, filters
from telegram.ext import WebhookHandler # Import thêm WebhookHandler
from telegram.ext.filters import MessageFilter # Import thêm MessageFilter nếu cần
import requests
from bs4 import BeautifulSoup
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo # Đảm bảo thư viện này có sẵn nếu bạn muốn dùng timezone phức tạp hơn
import logging # Thêm logging để dễ debug

# Cấu hình logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)


# CHAT_ID ban đầu là None. Nó sẽ được cập nhật khi người dùng gửi lệnh /news
CHAT_ID = None

# Lấy token từ biến môi trường
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    print("⚠️ Lỗi: Chưa có TELEGRAM_BOT_TOKEN trong biến môi trường!")
    TOKEN = "YOUR_DUMMY_TOKEN_FOR_LOCAL_DEBUG" # Cần đảm bảo TOKEN thật khi deploy

# ============================
# 1) Hàm lấy tin từ Coin68
# ============================
def get_news_coin68():
    news_list = ["📰 *Tin tức từ Coin68:*"]
    url = 'https://coin68.com/'
    try:
        r = requests.get(url, timeout=10)
        r.encoding = r.apparent_encoding
        soup = BeautifulSoup(r.text, 'html.parser')
        
        articles = soup.find_all('div', {'class': 'MuiBox-root css-fv3lde'})

        for idx, article in enumerate(articles[:5], start=1):
            link_tag = article.find('a', href=True)
            title_tag = article.find('span', {'class': 'MuiTypography-root MuiTypography-metaSemi css-1dk5p1t'})

            if link_tag and title_tag:
                title = title_tag.text.strip()
                link = link_tag['href']
                if not link.startswith("http"):
                    link = url.rstrip('/') + link
                news_list.append(f"[{idx}. {title}]({link})")

    except Exception as e:
        logger.error(f"❌ Lỗi khi lấy tin từ Coin68: {e}")

    return "\n".join(news_list) if len(news_list) > 1 else "Không tìm thấy tin tức từ Coin68!"

# ===============================
# 2) Hàm lấy tin từ Allinstation
# ===============================
def get_news_allinstation():
    news_list = ["📰 *Tin tức từ Allinstation:*"]
    url = 'https://allinstation.com/tin-tuc/'
    try:
        r = requests.get(url, timeout=10)
        r.encoding = r.apparent_encoding
        soup = BeautifulSoup(r.text, 'html.parser')

        articles = soup.find_all('div', {'class': 'col post-item'})

        for idx, article in enumerate(articles[:5], start=6):
            title_tag = article.find('h3', {'class': 'post-title is-large'})
            link_tag = article.find('a', href=True)

            if title_tag and link_tag:
                title = title_tag.text.strip()
                link = link_tag['href']
                news_list.append(f"[{idx}. {title}]({link})")

    except Exception as e:
        logger.error(f"❌ Lỗi khi lấy tin từ Allinstation: {e}")

    return "\n".join(news_list) if len(news_list) > 1 else "Không tìm thấy tin tức từ Allinstation!"

# 3) Gộp tin từ cả 2 trang
def get_all_news():
    coin68_news = get_news_coin68()
    allin_news = get_news_allinstation()
    return coin68_news + "\n\n" + allin_news

# 4) Gửi tin tự động chỉ trong khoảng 09:00 - 22:00
async def auto_send_news(context: ContextTypes.DEFAULT_TYPE) -> None:
    global CHAT_ID
    if not CHAT_ID:
        logger.warning("⚠️ Chưa có CHAT_ID, bot chưa được sử dụng trong nhóm hoặc chat cá nhân!")
        return

    # Lấy giờ UTC
    now_utc = datetime.now(timezone.utc)
    # Cộng 7 giờ để ra giờ VN (Nếu múi giờ của bạn là UTC+7, VD: Hồ Chí Minh, Hà Nội)
    now_vn = now_utc + timedelta(hours=7) 

    # Chỉ gửi tin trong khoảng 9:00 - 22:00 giờ VN
    if time(9, 0) <= now_vn.time() <= time(22, 0):
        news_message = get_all_news()
        try:
            await context.bot.send_message(
                chat_id=CHAT_ID, 
                text=news_message, 
                parse_mode="Markdown",
                disable_web_page_preview=True # Tắt preview link để tránh làm tin nhắn quá dài
            )
            logger.info(f"✅ Đã gửi tin tự động lúc {now_vn.strftime('%H:%M')} tới CHAT_ID: {CHAT_ID}")
        except Exception as e:
            logger.error(f"❌ Lỗi gửi tin tự động tới CHAT_ID {CHAT_ID}: {e}")
    else:
        logger.info(f"⏳ {now_vn.strftime('%H:%M')} - Ngoài giờ gửi tin (09:00 - 22:00 VN), bỏ qua...")

# 5) Lệnh /news để lấy tin
async def news(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    global CHAT_ID
    # Cập nhật CHAT_ID khi có lệnh /news được gửi đến
    CHAT_ID = update.message.chat_id
    logger.info(f"✅ Đã cập nhật CHAT_ID: {CHAT_ID}")

    news_message = get_all_news()
    try:
        await update.message.reply_text(news_message, parse_mode="Markdown", disable_web_page_preview=True)
        logger.info(f"✅ Đã trả lời lệnh /news tới CHAT_ID: {CHAT_ID}")
    except Exception as e:
        logger.error(f"❌ Lỗi khi trả lời lệnh /news tới CHAT_ID {CHAT_ID}: {e}")

# 6) Cấu hình JobQueue: Gửi tin tự động từ 09:00 - 22:00, cách 3 giờ/lần
async def setup_jobs(application: Application):
    job_queue = application.job_queue
    job_queue.run_repeating(auto_send_news, interval=10800, first=10)
    logger.info("✅ Đã thiết lập JobQueue để gửi tin tự động mỗi 3 giờ.")

# =========================================================================
# 7) PHẦN QUAN TRỌNG CẦN SỬA ĐỂ CHẠY TRÊN RENDER HOẶC CỤC BỘ
# =========================================================================

# Thêm một handler cho các yêu cầu GET/HEAD từ các dịch vụ như UptimeRobot
# telegram.ext không có trực tiếp Handler cho GET/HEAD requests,
# bạn cần tạo một HTTP server tùy chỉnh hoặc sử dụng thư viện như aiohttp (đã có trong [webhooks] extra)
# Tuy nhiên, cách đơn giản nhất là dựa vào cách ptb xử lý WebhookHandler
# để đảm bảo nó vẫn đáp ứng được HTTP 200 OK cho các request không phải POST.
# Nếu bạn không nhận được lỗi "No open ports detected" nữa,
# có thể lỗi 405 đến từ việc PTB chỉ cho phép POST method trên đường dẫn đó.
# Chúng ta sẽ dùng một phương pháp đơn giản hơn là tạo một HTTP server cơ bản bên ngoài.

# Cần một micro-framework như Flask hoặc FastAPI nếu bạn muốn tự xử lý GET/HEAD requests
# Tuy nhiên, python-telegram-bot[webhooks] đã bao gồm aiohttp.
# Ta sẽ dùng phương pháp tích hợp với Flask để tạo một HTTP endpoint riêng cho health check.

# CẬP NHẬT CÁCH CHẠY MAIN ĐỂ THÊM HTTP SERVER RIÊNG BIỆT CHO HEALTH CHECK

from flask import Flask, request, jsonify # Thêm import Flask

# Tạo một Flask app riêng để xử lý các request HTTP không phải từ Telegram
app_flask = Flask(__name__)

# Endpoint cho UptimeRobot hoặc Health Check
@app_flask.route("/news", methods=['GET', 'HEAD'])
def health_check():
    # logger.info(f"Received health check request: {request.method} {request.url}")
    return "OK", 200 # Trả về 200 OK cho các yêu cầu GET/HEAD

# Endpoint cho Telegram Webhook (POST requests)
# Flask sẽ chuyển tiếp các request POST về hàm xử lý của telegram-bot
@app_flask.route("/news", methods=['POST'])
async def telegram_webhook():
    # logger.info(f"Received Telegram webhook request: {request.method} {request.url}")
    update = Update.de_json(request.get_json(force=True), telegram_application.bot)
    await telegram_application.process_update(update)
    return "OK", 200

telegram_application = None # Biến toàn cục để lưu trữ telegram Application

def main() -> None:
    global telegram_application # Khai báo sử dụng biến toàn cục
    # Khi chạy cục bộ, bạn có thể bỏ comment dòng dưới này:
    # load_dotenv() 

    telegram_application = ApplicationBuilder().token(TOKEN).post_init(setup_jobs).build()

    telegram_application.add_handler(CommandHandler("news", news))
    telegram_application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, news)) # Thêm handler cho tin nhắn text thông thường

    WEBHOOK_HOST = os.getenv("RENDER_EXTERNAL_HOSTNAME")
    PORT = int(os.environ.get("PORT", "8443"))

    if WEBHOOK_HOST:
        logger.info(f"🚀 Triển khai bot với Webhook. Lắng nghe trên port: {PORT}")
        logger.info(f"   Webhook URL đầy đủ: https://{WEBHOOK_HOST}/news")

        # Chạy cả Flask app và telegram_application trong cùng một tiến trình
        # Sử dụng waitress làm WSGI server (phù hợp với môi trường production)
        # hoặc gunicorn. Cần thêm waitress vào requirements.txt
        # Bắt buộc phải thêm waitress vào requirements.txt:
        # python-telegram-bot[job_queue,webhooks]==20.0
        # requests
        # beautifulsoup4
        # python-dotenv
        # Flask
        # waitress # THÊM DÒNG NÀY

        from waitress import serve # Import waitress

        # Khởi tạo Flask app với WSGI handler của PTB
        # ptb_webhook_handler = telegram_application.updater.dispatcher.get_handler() # Đây là cách cũ
        # Với PTB 20+, run_webhook đã tự lo phần này rồi.
        # Chúng ta cần tích hợp Flask và PTB.
        # Cách đơn giản nhất là Flask sẽ lắng nghe POST requests và gọi process_update của PTB.

        # Đây là cấu hình cho Flask để lắng nghe, và PTB sẽ xử lý Telegram updates
        serve(app_flask, host="0.0.0.0", port=PORT)

    else:
        logger.info("💻 Chạy bot ở chế độ Polling (chế độ phát triển cục bộ).")
        telegram_application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()

