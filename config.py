import os
import logging
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


class Config:
    # Telegram Bot
    TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')

    # SMSPool API
    SMSPOOL_BASE_URL = os.getenv('SMSPOOL_API_BASE', 'https://api.smspool.net')

    # Bot Settings
    MONITORING_INTERVAL = int(os.getenv('MONITORING_INTERVAL', 30))
    SMS_TIMEOUT = int(os.getenv('SMS_TIMEOUT', 600))
    MAX_RETRIES = int(os.getenv('MAX_RETRIES', 3))

    # Database
    DATABASE_PATH = os.getenv('DATABASE_PATH', 'users.db')

    # Logging
    LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
    LOG_FILE = os.getenv('LOG_FILE', 'logs/bot.log')
    DEBUG = os.getenv('DEBUG', 'False').lower() == 'true'

    # SMSPool Service Configuration
    TARGET_COUNTRY = "jp"  # Japan
    TARGET_SERVICE = "pokemon"  # Pokemon GO

    # Messages
    WELCOME_MESSAGE = """
🤖 Chào mừng đến với SMS Pool Bot!

Bot này giúp bạn thuê số điện thoại Nhật Bản để nhận SMS.

Để bắt đầu, vui lòng gửi API key của bạn từ SMSPool.net
    """

    HELP_MESSAGE = """
📋 Hướng dẫn sử dụng:

1️⃣ Gửi API key SMSPool để đăng nhập
2️⃣ Bot sẽ tự động theo dõi số JP Pokemon có sẵn
3️⃣ Khi có số, bạn sẽ nhận thông báo
4️⃣ Chọn "Thuê số" để thuê số điện thoại
5️⃣ Chờ SMS đến trong vòng 10 phút
6️⃣ Nếu không có SMS, bot tự động hoàn tiền

Commands:
/start - Bắt đầu
/help - Hướng dẫn  
/balance - Kiểm tra số dư
/orders - Xem đơn hàng đang active
    """


# Setup logging
def setup_logging():
    # Tạo thư mục logs nếu chưa có
    os.makedirs('logs', exist_ok=True)

    log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'

    # Configure root logger
    logging.basicConfig(
        level=getattr(logging, Config.LOG_LEVEL),
        format=log_format,
        handlers=[
            logging.FileHandler(Config.LOG_FILE, encoding='utf-8'),
            logging.StreamHandler()
        ]
    )

    # Disable some noisy loggers
    logging.getLogger('httpx').setLevel(logging.WARNING)
    logging.getLogger('telegram').setLevel(logging.WARNING)

    return logging.getLogger(__name__)


# Validate configuration
def validate_config():
    errors = []

    if not Config.TELEGRAM_BOT_TOKEN:
        errors.append("TELEGRAM_BOT_TOKEN không được để trống")

    if not Config.SMSPOOL_BASE_URL:
        errors.append("SMSPOOL_API_BASE không được để trống")

    if errors:
        for error in errors:
            print(f"❌ Lỗi cấu hình: {error}")
        return False

    return True