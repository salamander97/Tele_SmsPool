import asyncio
import logging
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters, CallbackQueryHandler

from config import Config, setup_logging, validate_config

# Setup logging
logger = setup_logging()


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command"""
    user = update.effective_user
    logger.info(f"User {user.id} ({user.username}) started the bot")

    from database import db
    from smspool_api import smspool_api

    # Kiểm tra xem user đã có API key chưa
    existing_user = db.get_user(user.id)

    if existing_user:
        # User đã đăng nhập rồi, cập nhật balance và hiển thị menu chính
        try:
            # Cập nhật balance mới nhất
            balance_result = await smspool_api.get_balance(existing_user['api_key'])
            if balance_result['success']:
                db.update_user_balance(existing_user['user_id'], balance_result['balance'])
                current_balance = balance_result['balance']
            else:
                current_balance = existing_user.get('balance', 0)
        except:
            current_balance = existing_user.get('balance', 0)

        await update.message.reply_text(
            f"👋 Chào mừng {user.first_name} quay trở lại!\n\n"
            f"✅ Bạn đã đăng nhập với API key SMSPool\n"
            f"💰 Số dư: ${current_balance}\n\n"
            f"🤖 Bot đang tự động theo dõi số JP Pokemon cho bạn.\n"
            f"📱 Khi có số khả dụng, bạn sẽ nhận được thông báo!\n\n"
            f"📱 Thông báo sẽ tự động gửi sau mỗi 5 phút nếu có số khả dụng!\n\n"
            f"Chọn một tùy chọn bên dưới:",
            reply_markup=get_main_menu()
        )
    else:
        # User chưa đăng nhập, yêu cầu API key
        await update.message.reply_text(
            f"👋 Xin chào {user.first_name}!\n\n{Config.WELCOME_MESSAGE}",
            parse_mode='HTML'
        )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help command"""
    await update.message.reply_text(
        Config.HELP_MESSAGE,
        parse_mode='HTML'
    )


async def balance_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /balance command"""
    user = update.effective_user
    from database import db
    from smspool_api import smspool_api

    user_data = db.get_user(user.id)
    if not user_data:
        await update.message.reply_text(
            "❌ Bạn chưa đăng nhập! Vui lòng gửi API key SMSPool."
        )
        return

    balance_result = await smspool_api.get_balance(user_data['api_key'])
    if balance_result['success']:
        db.update_user_balance(user_data['user_id'], balance_result['balance'])
        await update.message.reply_text(
            f"💰 Số dư: ${balance_result['balance']}\n"
            f"🕐 Cập nhật: {datetime.now().strftime('%H:%M:%S')}"
        )
    else:
        await update.message.reply_text(
            f"❌ {balance_result['message']}"
        )


async def test_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /test command"""
    user = update.effective_user
    from database import db
    from smspool_api import smspool_api

    user_data = db.get_user(user.id)
    if not user_data:
        await update.message.reply_text("❌ Bạn chưa đăng nhập! Vui lòng gửi API key SMSPool.")
        return

    await update.message.reply_text("🔍 Testing API endpoints...")

    # Test balance
    balance_result = await smspool_api.get_balance(user_data['api_key'])
    balance_msg = f"💰 Balance: {balance_result}"

    # Test stock
    stock_result = await smspool_api.check_service_availability(user_data['api_key'])
    stock_msg = f"📱 Stock: {stock_result}"

    # Test price
    try:
        price_result = await smspool_api._get_service_price(user_data['api_key'])
        price_msg = f"💲 Price: ${price_result}"
    except:
        price_msg = "💲 Price: Error"

    test_results = f"""🧪 API Test Results:

{balance_msg}

{stock_msg}

{price_msg}

🕐 Time: {update.message.date}
👤 User: {user.id}"""

    await update.message.reply_text(test_results)


async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle text messages (API key input)"""
    user = update.effective_user
    message_text = update.message.text.strip()

    logger.info(f"Received message from {user.id}: {message_text[:20]}...")

    from database import db
    from smspool_api import smspool_api

    existing_user = db.get_user(user.id)
    if existing_user:
        await update.message.reply_text(
            "✅ Bạn đã đăng nhập rồi!\n"
            "Sử dụng /help để xem các lệnh có sẵn.",
            reply_markup=get_main_menu()
        )
        return

    # Kiểm tra xem có phải API key không (ít nhất 20 ký tự và chỉ chứa chữ số, chữ cái)
    if len(message_text) >= 20 and message_text.replace('_', '').replace('-', '').replace('.', '').isalnum():
        loading_msg = await update.message.reply_text("🔄 Đang xác thực API key...")
        try:
            verification_result = await smspool_api.verify_api_key(message_text)
            await loading_msg.delete()

            # Log chi tiết để debug
            logger.info(f"API verification result: {verification_result}")

            if verification_result['valid']:
                success = db.save_user(
                    user_id=user.id,
                    username=user.username or '',
                    first_name=user.first_name or '',
                    api_key=message_text,
                    balance=verification_result['balance']
                )
                if success:
                    await update.message.reply_text(
                        f"✅ API key hợp lệ!\n\n"
                        f"👤 Tài khoản: @{user.username or user.first_name}\n"
                        f"💰 Số dư: ${verification_result['balance']}\n\n"
                        f"🤖 Bot sẽ tự động theo dõi số JP Pokemon cho bạn.\n"
                        f"📱 Khi có số khả dụng, bạn sẽ nhận được thông báo!",
                        reply_markup=get_main_menu()
                    )
                    logger.info(f"✅ User {user.id} authenticated successfully")
                else:
                    await update.message.reply_text(
                        "❌ Lỗi lưu thông tin. Vui lòng thử lại sau."
                    )
            else:
                await update.message.reply_text(
                    f"❌ {verification_result['message']}\n\n"
                    f"Vui lòng kiểm tra lại API key và thử lại."
                )
        except Exception as e:
            await loading_msg.delete()
            logger.error(f"API key verification error: {e}")
            await update.message.reply_text(
                "❌ Lỗi kết nối đến SMSPool API.\n"
                "Vui lòng thử lại sau ít phút."
            )
    else:
        await update.message.reply_text(
            "❓ Tin nhắn không hợp lệ.\n\n"
            "🔑 Vui lòng gửi API key SMSPool của bạn.\n"
            "📖 Sử dụng /help để xem hướng dẫn chi tiết."
        )


def get_main_menu():
    """Create main menu inline keyboard"""
    keyboard = [
        [InlineKeyboardButton("💰 Kiểm tra số dư", callback_data='check_balance')],
        [InlineKeyboardButton("🔍 Check số JP Pokemon", callback_data='check_availability')],
        [InlineKeyboardButton("📱 Thuê số JP Pokemon", callback_data='rent_number')],
        [InlineKeyboardButton("📋 Đơn hàng active", callback_data='active_orders')],
        [InlineKeyboardButton("❓ Hướng dẫn", callback_data='help')]
    ]
    return InlineKeyboardMarkup(keyboard)


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle button callbacks"""
    query = update.callback_query
    user = update.effective_user

    await query.answer()

    from database import db
    from smspool_api import smspool_api

    user_data = db.get_user(user.id)
    if not user_data:
        await query.edit_message_text(
            "❌ Bạn chưa đăng nhập!\n"
            "Vui lòng gửi API key SMSPool để bắt đầu."
        )
        return

    if query.data == 'check_balance':
        await handle_check_balance(query, user_data)
    elif query.data == 'check_availability':
        await handle_check_availability(query, user_data)
    elif query.data == 'rent_number':
        await handle_rent_number(query, user_data)
    elif query.data == 'confirm_rent':
        await handle_confirm_rent(query, user_data)
    elif query.data == 'active_orders':
        await handle_active_orders(query, user_data)
    elif query.data == 'help':
        await query.edit_message_text(
            Config.HELP_MESSAGE,
            reply_markup=get_main_menu()
        )
    elif query.data == 'main_menu':
        await query.edit_message_text(
            "🏠 Menu chính:",
            reply_markup=get_main_menu()
        )


async def handle_confirm_rent(query, user_data):
    """Handle confirmed number rental"""
    from smspool_api import smspool_api
    from database import db
    from datetime import timedelta

    await query.edit_message_text("🔄 Đang thuê số điện thoại...")

    rent_result = await smspool_api.rent_number(user_data['api_key'])
    if rent_result['success']:
        # Sử dụng expires_in từ API hoặc default 10 phút
        expires_seconds = rent_result.get('expires_in', 600)
        expires_at = datetime.now() + timedelta(seconds=expires_seconds)

        success = db.save_order(
            user_id=user_data['user_id'],
            order_id=rent_result['order_id'],
            phone_number=rent_result['phone_number'],
            price=rent_result['price'],
            expires_at=expires_at
        )
        if success:
            await query.edit_message_text(
                f"✅ Đã thuê số thành công!\n\n"
                f"📱 Số điện thoại: {rent_result['phone_number']}\n"
                f"🆔 Order ID: {rent_result['order_id']}\n"
                f"💰 Giá: ${rent_result['price']}\n"
                f"⏰ Hết hạn lúc: {expires_at.strftime('%H:%M:%S')}\n"
                f"⏱️ Thời gian còn lại: {expires_seconds // 60} phút\n\n"
                f"🔄 Bot sẽ tự động kiểm tra SMS và thông báo cho bạn.\n"
                f"⚠️ Nếu sau {expires_seconds // 60} phút không có SMS, bot sẽ tự động hoàn tiền.",
                reply_markup=get_main_menu()
            )
            logger.info(f"✅ Order {rent_result['order_id']} created for user {user_data['user_id']}")
        else:
            await query.edit_message_text(
                f"❌ Lỗi lưu đơn hàng. Vui lòng liên hệ admin.",
                reply_markup=get_main_menu()
            )
    else:
        await query.edit_message_text(
            f"❌ {rent_result['message']}",
            reply_markup=get_main_menu()
        )


async def handle_check_availability(query, user_data):
    """Handle availability check"""
    from smspool_api import smspool_api

    await query.edit_message_text("🔄 Đang kiểm tra tình trạng số JP Pokemon...")
    availability = await smspool_api.check_service_availability(user_data['api_key'])

    if availability['available']:
        # Kiểm tra xem user có đủ tiền không
        user_balance = user_data.get('balance', 0)
        service_price = availability['price']

        if user_balance >= service_price:
            # Đủ tiền - hiển thị nút thuê
            keyboard = [
                [InlineKeyboardButton(f"🎮 Thuê số ngay (${availability['price']})", callback_data='confirm_rent')],
                [InlineKeyboardButton("🔙 Quay lại", callback_data='main_menu')]
            ]
            await query.edit_message_text(
                f"✅ {availability['message']}\n\n"
                f"📱 Dịch vụ: {availability['service_name']}\n"
                f"💰 Giá: ${availability['price']}\n"
                f"💵 Số dư của bạn: ${user_balance}\n"
                f"⏰ Thời gian chờ SMS: 10 phút\n"
                f"🔄 Auto hoàn tiền nếu không có SMS\n\n"
                f"Bạn có muốn thuê số không?",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        else:
            # Không đủ tiền - chỉ hiển thị thông tin
            needed = service_price - user_balance
            keyboard = [
                [InlineKeyboardButton("💰 Kiểm tra số dư", callback_data='check_balance')],
                [InlineKeyboardButton("🔙 Quay lại", callback_data='main_menu')]
            ]
            await query.edit_message_text(
                f"⚠️ Có {availability['count']} số JP Pokemon nhưng bạn không đủ tiền!\n\n"
                f"📱 Dịch vụ: {availability['service_name']}\n"
                f"💰 Giá: ${service_price}\n"
                f"💵 Số dư hiện tại: ${user_balance}\n"
                f"📈 Cần thêm: ${needed:.2f}\n\n"
                f"💳 Vui lòng nạp thêm tiền vào tài khoản SMSPool để thuê số.",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
    else:
        await query.edit_message_text(
            f"❌ {availability['message']}\n\n"
            f"🔄 Bot sẽ tiếp tục theo dõi và thông báo khi có số khả dụng.",
            reply_markup=get_main_menu()
        )


async def handle_check_balance(query, user_data):
    """Handle balance check"""
    from smspool_api import smspool_api
    from database import db

    await query.edit_message_text("🔄 Đang kiểm tra số dư...")
    balance_result = await smspool_api.get_balance(user_data['api_key'])
    if balance_result['success']:
        db.update_user_balance(user_data['user_id'], balance_result['balance'])
        await query.edit_message_text(
            f"💰 Thông tin tài khoản:\n\n"
            f"👤 User: @{user_data['username']}\n"
            f"💵 Số dư: ${balance_result['balance']}\n"
            f"🕐 Cập nhật: {datetime.now().strftime('%H:%M:%S')}",
            reply_markup=get_main_menu()
        )
    else:
        await query.edit_message_text(
            f"❌ {balance_result['message']}",
            reply_markup=get_main_menu()
        )


async def handle_rent_number(query, user_data):
    """Handle number rental"""
    from smspool_api import smspool_api

    await query.edit_message_text("🔄 Đang kiểm tra tình trạng dịch vụ...")
    availability = await smspool_api.check_service_availability(user_data['api_key'])
    if availability['available']:
        keyboard = [
            [InlineKeyboardButton(f"🎮 Thuê số (${availability['price']})", callback_data='confirm_rent')],
            [InlineKeyboardButton("🔙 Quay lại", callback_data='main_menu')]
        ]
        await query.edit_message_text(
            f"📱 Dịch vụ JP Pokemon có sẵn!\n\n"
            f"📊 Số lượng: {availability['count']} số\n"
            f"💰 Giá: ${availability['price']}\n"
            f"⏰ Thời gian chờ SMS: 10 phút\n"
            f"🔄 Auto hoàn tiền nếu không có SMS\n\n"
            f"Bạn có muốn thuê số không?",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    else:
        await query.edit_message_text(
            f"❌ {availability['message']}\n\n"
            f"🔄 Bot sẽ tiếp tục theo dõi và thông báo khi có số khả dụng.",
            reply_markup=get_main_menu()
        )


async def handle_active_orders(query, user_data):
    """Handle active orders display"""
    from database import db

    active_orders = db.get_active_orders(user_data['user_id'])
    if active_orders:
        orders_text = "📋 Đơn hàng đang active:\n\n"
        for order in active_orders:
            orders_text += (
                f"📱 Số: {order['phone_number']}\n"
                f"🆔 Order: {order['order_id']}\n"
                f"💰 Giá: ${order['price']}\n"
                f"⏰ Tạo lúc: {order['created_at']}\n"
                f"⌛ Hết hạn: {order['expires_at']}\n"
                f"{'─' * 30}\n"
            )
    else:
        orders_text = "📋 Bạn không có đơn hàng nào đang active."
    await query.edit_message_text(
        orders_text,
        reply_markup=get_main_menu()
    )


async def post_init(application: Application) -> None:
    """Called after bot initialization"""
    logger.info("🔄 Khởi tạo monitoring services...")
    from monitoring import get_monitoring_service
    monitoring = get_monitoring_service(application.bot)
    await monitoring.start_monitoring()
    logger.info("✅ Monitoring services started")


async def post_stop(application: Application) -> None:
    """Called before bot shutdown"""
    logger.info("🛑 Đang dừng bot...")
    from monitoring import get_monitoring_service
    monitoring = get_monitoring_service(application.bot)
    if monitoring:
        await monitoring.stop_monitoring()

    # Cleanup smspool session
    from smspool_api import smspool_api
    await smspool_api.close()

    # Force stop Telegram updater to avoid conflicts
    try:
        await application.updater.stop()
    except:
        pass

    logger.info("✅ Bot cleanup completed")


def main():
    """Main function"""
    logger.info("🚀 Starting SMS Pool Telegram Bot...")

    if not validate_config():
        logger.error("❌ Lỗi cấu hình - Bot không thể khởi động")
        return

    if not Config.TELEGRAM_BOT_TOKEN or Config.TELEGRAM_BOT_TOKEN == "your_bot_token_here":
        logger.error("❌ Vui lòng cập nhật TELEGRAM_BOT_TOKEN trong file .env")
        print("\n📝 Hướng dẫn lấy Bot Token:")
        print("1. Mở Telegram, tìm @BotFather")
        print("2. Gửi /newbot và làm theo hướng dẫn")
        print("3. Copy token và paste vào file .env")
        print("4. Chạy lại bot")
        return

    logger.info("✅ Configuration validated successfully")

    # Tạo application với callbacks và drop_pending_updates
    application = (Application.builder()
                   .token(Config.TELEGRAM_BOT_TOKEN)
                   .post_init(post_init)
                   .post_stop(post_stop)
                   .build())

    # Thêm handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("balance", balance_command))
    application.add_handler(CommandHandler("test", test_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    application.add_handler(CallbackQueryHandler(button_handler))
    logger.info("✅ Bot handlers đã được thiết lập")

    logger.info("🔄 Bắt đầu polling...")

    # Chạy bot với drop_pending_updates để tránh conflict
    try:
        application.run_polling(
            poll_interval=1.0,
            timeout=20,
            drop_pending_updates=True,  # Quan trọng: drop old updates
            stop_signals=None  # Disable default signal handlers
        )
    except KeyboardInterrupt:
        logger.info("🛑 Bot đã dừng bởi người dùng")
    except Exception as e:
        logger.error(f"❌ Lỗi bot: {e}")
    finally:
        logger.info("🔄 Bot shutdown completed")


if __name__ == '__main__':
    main()
