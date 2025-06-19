from telegram import Update
import os
from dotenv import load_dotenv
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, Application
import requests
from bs4 import BeautifulSoup
from datetime import datetime, time
from datetime import time, timedelta, datetime
from zoneinfo import ZoneInfo
from datetime import datetime, timezone

CHAT_ID = None
load_dotenv()

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise ValueError("⚠️ Lỗi: Chưa có TELEGRAM_BOT_TOKEN trong file .env!")

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
        print("⚠️ Chưa có CHAT_ID, bot chưa được sử dụng trong nhóm!")
        return

    # Lấy giờ UTC, +7 giờ để ra giờ VN
    now_utc = datetime.now(timezone.utc)
    now_vn = now_utc + timedelta(hours=7)  # Giả sử bạn ở UTC+7

    # Chỉ gửi tin trong khoảng 9:00 - 22:00 giờ VN
    if time(9, 0) <= now_vn.time() <= time(22, 0):
        news_message = get_all_news()
        try:
            await context.bot.send_message(
                chat_id=CHAT_ID, 
                text=news_message, 
                parse_mode="Markdown"
            )
        except Exception as e:
            print(f"❌ Lỗi gửi tin: {e}")
    else:
        print(f"⏳ {now_vn.strftime('%H:%M')} - Ngoài giờ gửi tin (09:00 - 22:00), bỏ qua...")

# 5) Lệnh /news để lấy tin
async def news(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    global CHAT_ID
    CHAT_ID = update.message.chat_id
    print(f"✅ Đã cập nhật CHAT_ID: {CHAT_ID}")

    news_message = get_all_news()
    try:
        await update.message.reply_text(news_message, parse_mode="Markdown")
    except Exception as e:
        print(f"❌ Lỗi gửi tin nhắn: {e}")

# 6) JobQueue: Gửi tin tự động từ 09:00 - 22:00, cách 3 giờ/lần
async def setup_jobs(application: Application):
    job_queue = application.job_queue
    job_queue.run_repeating(auto_send_news, interval=10800, first=10)

# 7) Cấu hình & chạy bot
app = ApplicationBuilder().token(TOKEN).post_init(setup_jobs).build()

app.add_handler(CommandHandler("news", news))
app.run_polling()
