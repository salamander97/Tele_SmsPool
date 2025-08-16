import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, Any
from telegram import Bot
from telegram.error import TelegramError

from config import Config
from database import db
from smspool_api import smspool_api

logger = logging.getLogger(__name__)


class MonitoringService:
    def __init__(self, bot: Bot):
        self.bot = bot
        self.is_running = False
        self.monitoring_task = None
        self.sms_checking_task = None

    async def start_monitoring(self):
        """Start background monitoring services"""
        if self.is_running:
            logger.warning("Monitoring already running")
            return

        self.is_running = True
        logger.info("🔄 Starting monitoring services...")

        # Start service availability monitoring
        self.monitoring_task = asyncio.create_task(self._monitor_service_availability())

        # Start SMS checking for active orders
        self.sms_checking_task = asyncio.create_task(self._monitor_active_orders())

        logger.info("✅ Monitoring services started")

    async def stop_monitoring(self):
        """Stop background monitoring services"""
        self.is_running = False

        if self.monitoring_task:
            self.monitoring_task.cancel()
            try:
                await self.monitoring_task
            except asyncio.CancelledError:
                pass

        if self.sms_checking_task:
            self.sms_checking_task.cancel()
            try:
                await self.sms_checking_task
            except asyncio.CancelledError:
                pass

        logger.info("🛑 Monitoring services stopped")

    async def _monitor_service_availability(self):
        """Monitor Pokemon service availability for all users"""
        logger.info("🔍 Service availability monitoring started")

        while self.is_running:
            try:
                # Get all active users
                active_users = db.get_all_active_users()
                logger.debug(f"Checking service for {len(active_users)} users")

                for user in active_users:
                    try:
                        await self._check_service_for_user(user)
                        # Small delay between users to avoid rate limiting
                        await asyncio.sleep(1)

                    except Exception as e:
                        logger.error(f"Error checking service for user {user['user_id']}: {e}")

                # Wait for next check
                await asyncio.sleep(Config.MONITORING_INTERVAL)

            except asyncio.CancelledError:
                logger.info("Service monitoring cancelled")
                break
            except Exception as e:
                logger.error(f"Service monitoring error: {e}")
                await asyncio.sleep(Config.MONITORING_INTERVAL)

    async def _check_service_for_user(self, user: Dict[str, Any]):
        """Check service availability for a specific user"""
        try:
            user_id = user['user_id']
            api_key = user['api_key']

            # Check if user has active orders (skip notification if they do)
            active_orders = db.get_active_orders(user_id)
            if active_orders:
                logger.debug(f"User {user_id} has active orders, skipping notification")
                return

            # Check service availability
            availability = await smspool_api.check_service_availability(api_key)

            if availability['available'] and availability['count'] > 0:
                # Send notification to user
                await self._send_availability_notification(user_id, availability)

                # Update monitoring status
                db.update_monitoring_status(user_id, datetime.now(), notification_sent=True)

                logger.info(f"📢 Sent availability notification to user {user_id}")
            else:
                # Update last check time
                db.update_monitoring_status(user_id, datetime.now(), notification_sent=False)

        except Exception as e:
            logger.error(f"Error checking service for user {user['user_id']}: {e}")

    async def _send_availability_notification(self, user_id: int, availability: Dict[str, Any]):
        """Send service availability notification to user"""
        try:
            from telegram import InlineKeyboardButton, InlineKeyboardMarkup

            keyboard = [
                [InlineKeyboardButton(f"🎮 Thuê số ngay (${availability['price']})", callback_data='rent_number')],
                [InlineKeyboardButton("📋 Xem menu", callback_data='main_menu')]
            ]

            message = (
                f"🚨 THÔNG BÁO: Có số JP Pokemon!\n\n"
                f"📱 Số lượng có sẵn: {availability['count']}\n"
                f"💰 Giá: ${availability['price']}\n"
                f"⏰ Thời gian: {datetime.now().strftime('%H:%M:%S')}\n\n"
                f"🔥 Hãy nhanh tay thuê số trước khi hết!"
            )

            await self.bot.send_message(
                chat_id=user_id,
                text=message,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )

        except TelegramError as e:
            if "blocked" in str(e).lower():
                logger.warning(f"User {user_id} blocked the bot")
                # Optionally deactivate user
            else:
                logger.error(f"Failed to send notification to user {user_id}: {e}")
        except Exception as e:
            logger.error(f"Error sending notification to user {user_id}: {e}")

    async def _monitor_active_orders(self):
        """Monitor active orders for SMS and handle timeouts"""
        logger.info("📱 SMS monitoring started")

        while self.is_running:
            try:
                # Get all active orders
                active_orders = db.get_all_active_orders()
                logger.debug(f"Monitoring {len(active_orders)} active orders")

                for order in active_orders:
                    try:
                        await self._check_order_sms(order)
                        # Small delay between orders
                        await asyncio.sleep(1)

                    except Exception as e:
                        logger.error(f"Error checking order {order['order_id']}: {e}")

                # Check every 30 seconds for SMS
                await asyncio.sleep(30)

            except asyncio.CancelledError:
                logger.info("SMS monitoring cancelled")
                break
            except Exception as e:
                logger.error(f"SMS monitoring error: {e}")
                await asyncio.sleep(30)

    async def _check_order_sms(self, order: Dict[str, Any]):
        """Check SMS for a specific order"""
        try:
            order_id = order['order_id']
            user_id = order['user_id']
            expires_at = datetime.fromisoformat(order['expires_at'])

            # Check if order expired
            if datetime.now() > expires_at:
                await self._handle_expired_order(order)
                return

            # Get user API key
            user = db.get_user(user_id)
            if not user:
                logger.error(f"User {user_id} not found for order {order_id}")
                return

            # Check for SMS
            sms_result = await smspool_api.check_sms(user['api_key'], order_id)

            if sms_result['received']:
                # SMS received!
                await self._handle_sms_received(order, sms_result)
            else:
                logger.debug(f"No SMS yet for order {order_id}")

        except Exception as e:
            logger.error(f"Error checking SMS for order {order['order_id']}: {e}")

    async def _handle_sms_received(self, order: Dict[str, Any], sms_result: Dict[str, Any]):
        """Handle received SMS"""
        try:
            order_id = order['order_id']
            user_id = order['user_id']
            phone_number = order['phone_number']

            # Update order in database
            db.update_order_sms(order_id, sms_result['sms_content'])

            # Send SMS to user
            message = (
                f"✅ ĐÃ NHẬN ĐƯỢC SMS!\n\n"
                f"📱 Số điện thoại: {phone_number}\n"
                f"🆔 Order ID: {order_id}\n"
                f"📩 Nội dung SMS: {sms_result['sms_content']}\n\n"
                f"🎉 Giao dịch hoàn tất thành công!"
            )

            await self.bot.send_message(chat_id=user_id, text=message)

            logger.info(f"✅ SMS received for order {order_id}, user {user_id} notified")

        except Exception as e:
            logger.error(f"Error handling received SMS for order {order['order_id']}: {e}")

    async def _handle_expired_order(self, order: Dict[str, Any]):
        """Handle expired order - request refund"""
        try:
            order_id = order['order_id']
            user_id = order['user_id']
            phone_number = order['phone_number']
            price = order['price']

            # Get user API key
            user = db.get_user(user_id)
            if not user:
                logger.error(f"User {user_id} not found for expired order {order_id}")
                return

            # Request refund
            refund_result = await smspool_api.cancel_order(user['api_key'], order_id)

            if refund_result['success']:
                # Update order status
                db.update_order_status(order_id, 'refunded')

                # Get updated balance
                balance_result = await smspool_api.get_balance(user['api_key'])
                if balance_result['success']:
                    db.update_user_balance(user_id, balance_result['balance'])

                # Notify user
                message = (
                    f"⏰ ĐƠN HÀNG HẾT HẠN - ĐÃ HOÀN TIỀN\n\n"
                    f"📱 Số điện thoại: {phone_number}\n"
                    f"🆔 Order ID: {order_id}\n"
                    f"💰 Số tiền hoàn: ${price}\n"
                    f"💵 Số dư hiện tại: ${balance_result.get('balance', 'N/A')}\n\n"
                    f"😔 Không nhận được SMS trong 10 phút.\n"
                    f"🔄 Bạn có thể thử thuê số khác."
                )

                await self.bot.send_message(chat_id=user_id, text=message)

                logger.info(f"💰 Order {order_id} refunded for user {user_id}")
            else:
                # Refund failed
                db.update_order_status(order_id, 'expired')

                message = (
                    f"⚠️ ĐƠN HÀNG HẾT HẠN\n\n"
                    f"📱 Số điện thoại: {phone_number}\n"
                    f"🆔 Order ID: {order_id}\n\n"
                    f"❌ Không thể hoàn tiền tự động.\n"
                    f"📞 Vui lòng liên hệ support SMSPool."
                )

                await self.bot.send_message(chat_id=user_id, text=message)

                logger.error(f"❌ Failed to refund expired order {order_id}")

        except Exception as e:
            logger.error(f"Error handling expired order {order['order_id']}: {e}")


# Global monitoring service instance
monitoring_service = None


def get_monitoring_service(bot: Bot = None) -> MonitoringService:
    """Get or create monitoring service instance"""
    global monitoring_service
    if monitoring_service is None and bot:
        monitoring_service = MonitoringService(bot)
    return monitoring_service