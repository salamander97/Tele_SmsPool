import sqlite3
import json
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any
from config import Config

logger = logging.getLogger(__name__)


class Database:
    def __init__(self, db_path: str = None):
        self.db_path = db_path or Config.DATABASE_PATH
        self.init_database()

    def init_database(self):
        """Initialize database tables"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                # Users table
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS users (
                        user_id INTEGER PRIMARY KEY,
                        username TEXT,
                        first_name TEXT,
                        api_key TEXT NOT NULL,
                        balance REAL DEFAULT 0.0,
                        is_active BOOLEAN DEFAULT 1,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')

                # Orders table
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS orders (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER NOT NULL,
                        order_id TEXT UNIQUE NOT NULL,
                        phone_number TEXT NOT NULL,
                        country_code TEXT DEFAULT 'jp',
                        service_id INTEGER DEFAULT 1552,
                        service_name TEXT DEFAULT 'Pokemon Center',
                        status TEXT DEFAULT 'active',
                        price REAL,
                        sms_content TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        expires_at TIMESTAMP,
                        completed_at TIMESTAMP,
                        FOREIGN KEY (user_id) REFERENCES users (user_id)
                    )
                ''')

                # Monitoring status table
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS monitoring_status (
                        user_id INTEGER PRIMARY KEY,
                        is_monitoring BOOLEAN DEFAULT 1,
                        last_check TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        notification_sent BOOLEAN DEFAULT 0,
                        FOREIGN KEY (user_id) REFERENCES users (user_id)
                    )
                ''')

                conn.commit()
                logger.info("✅ Database initialized successfully")

        except Exception as e:
            logger.error(f"❌ Database initialization failed: {e}")
            raise

    def save_user(self, user_id: int, username: str, first_name: str, api_key: str, balance: float = 0.0) -> bool:
        """Save or update user information"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                cursor.execute('''
                    INSERT OR REPLACE INTO users 
                    (user_id, username, first_name, api_key, balance, updated_at)
                    VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ''', (user_id, username, first_name, api_key, balance))

                # Initialize monitoring status
                cursor.execute('''
                    INSERT OR REPLACE INTO monitoring_status 
                    (user_id, is_monitoring, last_check)
                    VALUES (?, 1, CURRENT_TIMESTAMP)
                ''', (user_id,))

                conn.commit()
                logger.info(f"✅ User {user_id} saved successfully")
                return True

        except Exception as e:
            logger.error(f"❌ Failed to save user {user_id}: {e}")
            return False

    def get_user(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Get user information"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()

                cursor.execute('''
                    SELECT * FROM users WHERE user_id = ? AND is_active = 1
                ''', (user_id,))

                row = cursor.fetchone()
                return dict(row) if row else None

        except Exception as e:
            logger.error(f"❌ Failed to get user {user_id}: {e}")
            return None

    def get_all_active_users(self) -> List[Dict[str, Any]]:
        """Get all active users for monitoring"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()

                cursor.execute('''
                    SELECT u.*, m.is_monitoring, m.last_check 
                    FROM users u
                    LEFT JOIN monitoring_status m ON u.user_id = m.user_id
                    WHERE u.is_active = 1 AND (m.is_monitoring = 1 OR m.is_monitoring IS NULL)
                ''')

                return [dict(row) for row in cursor.fetchall()]

        except Exception as e:
            logger.error(f"❌ Failed to get active users: {e}")
            return []

    def save_order(self, user_id: int, order_id: str, phone_number: str,
                   price: float, expires_at: datetime) -> bool:
        """Save new order"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                cursor.execute('''
                    INSERT INTO orders 
                    (user_id, order_id, phone_number, price, expires_at)
                    VALUES (?, ?, ?, ?, ?)
                ''', (user_id, order_id, phone_number, price, expires_at))

                conn.commit()
                logger.info(f"✅ Order {order_id} saved for user {user_id}")
                return True

        except Exception as e:
            logger.error(f"❌ Failed to save order {order_id}: {e}")
            return False

    def update_order_sms(self, order_id: str, sms_content: str) -> bool:
        """Update order with received SMS"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                cursor.execute('''
                    UPDATE orders 
                    SET sms_content = ?, status = 'completed', completed_at = CURRENT_TIMESTAMP
                    WHERE order_id = ?
                ''', (sms_content, order_id))

                conn.commit()
                logger.info(f"✅ Order {order_id} updated with SMS")
                return True

        except Exception as e:
            logger.error(f"❌ Failed to update order {order_id}: {e}")
            return False

    def get_active_orders(self, user_id: int) -> List[Dict[str, Any]]:
        """Get active orders for user"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()

                cursor.execute('''
                    SELECT * FROM orders 
                    WHERE user_id = ? AND status = 'active'
                    ORDER BY created_at DESC
                ''', (user_id,))

                return [dict(row) for row in cursor.fetchall()]

        except Exception as e:
            logger.error(f"❌ Failed to get orders for user {user_id}: {e}")
            return []

    def get_all_active_orders(self) -> List[Dict[str, Any]]:
        """Get all active orders for monitoring"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()

                cursor.execute('''
                    SELECT * FROM orders 
                    WHERE status = 'active' AND expires_at > CURRENT_TIMESTAMP
                    ORDER BY created_at ASC
                ''')

                return [dict(row) for row in cursor.fetchall()]

        except Exception as e:
            logger.error(f"❌ Failed to get all active orders: {e}")
            return []

    def update_order_status(self, order_id: str, status: str) -> bool:
        """Update order status (cancelled, refunded, etc.)"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                cursor.execute('''
                    UPDATE orders 
                    SET status = ?, completed_at = CURRENT_TIMESTAMP
                    WHERE order_id = ?
                ''', (status, order_id))

                conn.commit()
                logger.info(f"✅ Order {order_id} status updated to {status}")
                return True

        except Exception as e:
            logger.error(f"❌ Failed to update order {order_id} status: {e}")
            return False

    def update_user_balance(self, user_id: int, balance: float) -> bool:
        """Update user balance"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                cursor.execute('''
                    UPDATE users 
                    SET balance = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE user_id = ?
                ''', (balance, user_id))

                conn.commit()
                return True

        except Exception as e:
            logger.error(f"❌ Failed to update balance for user {user_id}: {e}")
            return False

    def update_monitoring_status(self, user_id: int, last_check: datetime, notification_sent: bool = False) -> bool:
        """Update monitoring status"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                cursor.execute('''
                    UPDATE monitoring_status 
                    SET last_check = ?, notification_sent = ?
                    WHERE user_id = ?
                ''', (last_check, notification_sent, user_id))

                conn.commit()
                return True

        except Exception as e:
            logger.error(f"❌ Failed to update monitoring status for user {user_id}: {e}")
            return False


# Global database instance
db = Database()