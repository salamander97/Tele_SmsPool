import aiohttp
import asyncio
import logging
from typing import Optional, Dict, Any, List
from config import Config

logger = logging.getLogger(__name__)


class SMSPoolAPI:
    def __init__(self):
        self.base_url = Config.SMSPOOL_BASE_URL
        self.session = None
        # Japan Pokemon Center configuration
        self.target_country = "157"  # Japan ID
        self.target_service = "1552"  # Pokemon Center ID

    async def _get_session(self):
        """Get or create aiohttp session"""
        if self.session is None or self.session.closed:
            timeout = aiohttp.ClientTimeout(total=30)
            self.session = aiohttp.ClientSession(
                timeout=timeout,
                headers={'User-Agent': 'TelegramBot/1.0'}
            )
        return self.session

    async def _make_request(self, method: str, endpoint: str, api_key: str,
                            params: Dict = None, data: Dict = None) -> Optional[Dict[str, Any]]:
        """Make HTTP request to SMSPool API"""
        try:
            session = await self._get_session()
            url = f"{self.base_url}{endpoint}"

            # Add API key to params
            if params is None:
                params = {}
            params['key'] = api_key

            logger.debug(f"Making {method} request to {url} with params: {params}")

            async with session.request(method, url, params=params, json=data) as response:
                if response.status == 200:
                    result = await response.json()
                    logger.debug(f"API Response: {result}")
                    return result
                else:
                    error_text = await response.text()
                    logger.error(f"API Error {response.status}: {error_text}")
                    return None

        except asyncio.TimeoutError:
            logger.error("API request timeout")
            return None
        except Exception as e:
            logger.error(f"API request failed: {e}")
            return None

    async def verify_api_key(self, api_key: str) -> Dict[str, Any]:
        """Verify API key and get account info"""
        try:
            # Check balance to verify API key
            result = await self._make_request('GET', '/request/balance', api_key)

            if result and result.get('success') == 1:
                balance = float(result.get('balance', 0))

                return {
                    'valid': True,
                    'balance': balance,
                    'message': 'API key hợp lệ'
                }
            else:
                error_msg = result.get('message', 'API key không hợp lệ') if result else 'Không thể kết nối API'
                return {
                    'valid': False,
                    'balance': 0,
                    'message': error_msg
                }

        except Exception as e:
            logger.error(f"API key verification failed: {e}")
            return {
                'valid': False,
                'balance': 0,
                'message': f'Lỗi xác thực: {str(e)}'
            }

    async def check_service_availability(self, api_key: str) -> Dict[str, Any]:
        """Check if Japan Pokemon service is available"""
        try:
            # Get service list for Japan
            result = await self._make_request('GET', '/request/service', api_key, {
                'country': self.target_country
            })

            if result and result.get('success') == 1:
                services = result.get('data', [])

                # Find Pokemon Center service
                pokemon_service = None
                for service in services:
                    if str(service.get('ID')) == self.target_service:
                        pokemon_service = service
                        break

                if pokemon_service:
                    available_count = int(pokemon_service.get('stock', 0))
                    price = float(pokemon_service.get('price', 0))

                    return {
                        'available': available_count > 0,
                        'count': available_count,
                        'price': price,
                        'service_name': pokemon_service.get('name', 'Pokemon Center'),
                        'message': f'Có {available_count} số JP Pokemon, giá ${price}'
                    }
                else:
                    return {
                        'available': False,
                        'count': 0,
                        'price': 0,
                        'service_name': 'Pokemon Center',
                        'message': 'Dịch vụ Pokemon Center không khả dụng'
                    }
            else:
                error_msg = result.get('message', 'Không thể kiểm tra dịch vụ') if result else 'API Error'
                return {
                    'available': False,
                    'count': 0,
                    'price': 0,
                    'service_name': 'Pokemon Center',
                    'message': error_msg
                }

        except Exception as e:
            logger.error(f"Service availability check failed: {e}")
            return {
                'available': False,
                'count': 0,
                'price': 0,
                'service_name': 'Pokemon Center',
                'message': f'Lỗi kiểm tra dịch vụ: {str(e)}'
            }

    async def rent_number(self, api_key: str) -> Dict[str, Any]:
        """Rent a Japan Pokemon number"""
        try:
            result = await self._make_request('POST', '/purchase/sms', api_key, data={
                'country': self.target_country,
                'service': self.target_service
            })

            if result and result.get('success') == 1:
                order_data = result.get('order_id')
                phone_number = result.get('number')
                price = float(result.get('price', 0))

                return {
                    'success': True,
                    'order_id': order_data,
                    'phone_number': phone_number,
                    'price': price,
                    'message': f'Đã thuê số {phone_number} thành công!'
                }
            else:
                error_msg = result.get('message', 'Không thể thuê số') if result else 'API Error'
                return {
                    'success': False,
                    'order_id': None,
                    'phone_number': None,
                    'price': 0,
                    'message': error_msg
                }

        except Exception as e:
            logger.error(f"Number rental failed: {e}")
            return {
                'success': False,
                'order_id': None,
                'phone_number': None,
                'price': 0,
                'message': f'Lỗi thuê số: {str(e)}'
            }

    async def check_sms(self, api_key: str, order_id: str) -> Dict[str, Any]:
        """Check for received SMS"""
        try:
            result = await self._make_request('GET', '/sms/check', api_key, {
                'orderid': order_id
            })

            if result and result.get('success') == 1:
                sms_content = result.get('sms')
                full_sms = result.get('full_sms')

                if sms_content:
                    return {
                        'received': True,
                        'sms_content': sms_content,
                        'full_sms': full_sms,
                        'message': 'Đã nhận được SMS!'
                    }
                else:
                    return {
                        'received': False,
                        'sms_content': None,
                        'full_sms': None,
                        'message': 'Chưa có SMS'
                    }
            else:
                error_msg = result.get('message', 'Không thể kiểm tra SMS') if result else 'API Error'
                return {
                    'received': False,
                    'sms_content': None,
                    'full_sms': None,
                    'message': error_msg
                }

        except Exception as e:
            logger.error(f"SMS check failed: {e}")
            return {
                'received': False,
                'sms_content': None,
                'full_sms': None,
                'message': f'Lỗi kiểm tra SMS: {str(e)}'
            }

    async def cancel_order(self, api_key: str, order_id: str) -> Dict[str, Any]:
        """Cancel order and request refund"""
        try:
            result = await self._make_request('POST', '/sms/cancel', api_key, data={
                'orderid': order_id
            })

            if result and result.get('success') == 1:
                return {
                    'success': True,
                    'message': 'Đã hủy đơn hàng và hoàn tiền thành công!'
                }
            else:
                error_msg = result.get('message', 'Không thể hủy đơn hàng') if result else 'API Error'
                return {
                    'success': False,
                    'message': error_msg
                }

        except Exception as e:
            logger.error(f"Order cancellation failed: {e}")
            return {
                'success': False,
                'message': f'Lỗi hủy đơn hàng: {str(e)}'
            }

    async def get_balance(self, api_key: str) -> Dict[str, Any]:
        """Get current account balance"""
        try:
            result = await self._make_request('GET', '/request/balance', api_key)

            if result and result.get('success') == 1:
                balance = float(result.get('balance', 0))
                return {
                    'success': True,
                    'balance': balance,
                    'message': f'Số dư hiện tại: ${balance}'
                }
            else:
                error_msg = result.get('message', 'Không thể lấy số dư') if result else 'API Error'
                return {
                    'success': False,
                    'balance': 0,
                    'message': error_msg
                }

        except Exception as e:
            logger.error(f"Balance check failed: {e}")
            return {
                'success': False,
                'balance': 0,
                'message': f'Lỗi kiểm tra số dư: {str(e)}'
            }

    async def close(self):
        """Close aiohttp session"""
        if self.session and not self.session.closed:
            await self.session.close()


# Global API instance
smspool_api = SMSPoolAPI()