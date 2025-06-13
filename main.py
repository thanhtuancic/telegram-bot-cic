from telegram import Update
import os
# from dotenv import load_dotenv # Không cần dùng load_dotenv khi deploy lên Render vì biến môi trường được set trực tiếp
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, Application, MessageHandler, filters
import requests
from bs4 import BeautifulSoup
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo # Đảm bảo thư viện này có sẵn nếu bạn muốn dùng timezone phức tạp hơn

# CHAT_ID ban đầu là None. Nó sẽ được cập nhật khi người dùng gửi lệnh /news
CHAT_ID = None

# Lấy token từ biến môi trường
# Khi chạy cục bộ, biến này sẽ được load từ .env nếu bạn giữ load_dotenv()
# Khi deploy trên Render, biến này được Render cung cấp trực tiếp
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    # In ra lỗi nếu không tìm thấy token, hữu ích cho debug
    print("⚠️ Lỗi: Chưa có TELEGRAM_BOT_TOKEN trong biến môi trường!")
    # Tùy chọn: bạn có thể raise một exception nếu muốn dừng chương trình hẳn
    # raise ValueError("TELEGRAM_BOT_TOKEN environment variable not set.")
    # Để bot không crash khi debug, có thể gán tạm một giá trị rỗng
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
        print(f"❌ Lỗi khi lấy tin từ Coin68: {e}")

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
        print(f"❌ Lỗi khi lấy tin từ Allinstation: {e}")

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
        print("⚠️ Chưa có CHAT_ID, bot chưa được sử dụng trong nhóm hoặc chat cá nhân!")
        return

    # Lấy giờ UTC
    now_utc = datetime.now(timezone.utc)
    # Cộng 7 giờ để ra giờ VN (Nếu múi giờ của bạn là UTC+7, VD: Hồ Chí Minh, Hà Nội)
    # Cách tốt hơn là sử dụng thư viện zoneinfo để xử lý múi giờ chính xác
    # vietnam_tz = ZoneInfo("Asia/Ho_Chi_Minh")
    # now_vn = now_utc.astimezone(vietnam_tz)
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
            print(f"✅ Đã gửi tin tự động lúc {now_vn.strftime('%H:%M')} tới CHAT_ID: {CHAT_ID}")
        except Exception as e:
            print(f"❌ Lỗi gửi tin tự động tới CHAT_ID {CHAT_ID}: {e}")
    else:
        print(f"⏳ {now_vn.strftime('%H:%M')} - Ngoài giờ gửi tin (09:00 - 22:00 VN), bỏ qua...")

# 5) Lệnh /news để lấy tin
async def news(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    global CHAT_ID
    # Cập nhật CHAT_ID khi có lệnh /news được gửi đến
    CHAT_ID = update.message.chat_id
    print(f"✅ Đã cập nhật CHAT_ID: {CHAT_ID}")

    news_message = get_all_news()
    try:
        await update.message.reply_text(news_message, parse_mode="Markdown", disable_web_page_preview=True)
        print(f"✅ Đã trả lời lệnh /news tới CHAT_ID: {CHAT_ID}")
    except Exception as e:
        print(f"❌ Lỗi khi trả lời lệnh /news tới CHAT_ID {CHAT_ID}: {e}")

# 6) Cấu hình JobQueue: Gửi tin tự động từ 09:00 - 22:00, cách 3 giờ/lần
async def setup_jobs(application: Application):
    job_queue = application.job_queue
    # run_repeating(callback, interval, first)
    # interval=10800 giây = 3 giờ
    # first=10 (giây): Bắt đầu lần đầu tiên sau 10 giây khi bot khởi động
    job_queue.run_repeating(auto_send_news, interval=10800, first=10)
    print("✅ Đã thiết lập JobQueue để gửi tin tự động mỗi 3 giờ.")

# =========================================================================
# 7) PHẦN QUAN TRỌNG CẦN SỬA ĐỂ CHẠY TRÊN RENDER HOẶC CỤC BỘ
# =========================================================================
def main() -> None:
    # ⚠️ Quan trọng: Khi deploy lên Render, không dùng load_dotenv() vì biến môi trường được set trực tiếp
    # Nếu chạy cục bộ để debug, bạn có thể bỏ comment dòng dưới này:
    # load_dotenv() 

    application = ApplicationBuilder().token(TOKEN).post_init(setup_jobs).build()

    application.add_handler(CommandHandler("news", news))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, news)) # Thêm handler cho tin nhắn text thông thường

    # Lấy thông tin từ biến môi trường của Render
    # RENDER_EXTERNAL_HOSTNAME là tên miền mà Render gán cho dịch vụ của bạn
    # PORT là cổng mà Render yêu cầu ứng dụng của bạn lắng nghe
    WEBHOOK_HOST = os.getenv("RENDER_EXTERNAL_HOSTNAME")
    PORT = int(os.environ.get("PORT", "8443")) # Mặc định 8443 nếu không tìm thấy PORT

    if WEBHOOK_HOST:
        # Nếu có biến môi trường RENDER_EXTERNAL_HOSTNAME, chúng ta đang chạy trên Render
        # Cấu hình webhook
        WEBHOOK_URL_PATH = "/news" # Đường dẫn webhook bạn muốn
        FULL_WEBHOOK_URL = f"https://{WEBHOOK_HOST}{WEBHOOK_URL_PATH}"

        print(f"🚀 Triển khai bot với Webhook. Lắng nghe trên port: {PORT}")
        print(f"   Webhook URL đầy đủ: {FULL_WEBHOOK_URL}")

        application.run_webhook(
            listen="0.0.0.0",       # Lắng nghe trên tất cả các địa chỉ IP
            port=PORT,              # Lắng nghe trên cổng được Render cấp
            url_path=WEBHOOK_URL_PATH, # Đường dẫn mà bot sẽ xử lý các update
            webhook_url=FULL_WEBHOOK_URL # URL mà Telegram sẽ gửi các update đến
        )
    else:
        # Nếu không có biến môi trường RENDER_EXTERNAL_HOSTNAME, chúng ta đang chạy cục bộ
        print("💻 Chạy bot ở chế độ Polling (chế độ phát triển cục bộ).")
        application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()

