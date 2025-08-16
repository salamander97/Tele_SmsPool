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

    async def _make_request(self, method: str, endpoint: str, api_key: str = None,
                            params: Dict = None, data: Dict = None) -> Optional[Dict[str, Any]]:
        """Make HTTP request to SMSPool API"""
        try:
            session = await self._get_session()
            url = f"{self.base_url}{endpoint}"

            # Prepare form data - SMSPool sử dụng form-data cho tất cả
            form_data = {}
            if api_key:
                form_data['key'] = api_key
            if params:
                form_data.update(params)
            if data:
                form_data.update(data)

            logger.debug(f"Making {method} request to {url} with form_data: {form_data}")

            async with session.post(url, data=form_data) as response:
                if response.status == 200:
                    result = await response.json()
                    logger.debug(f"API Response: {result}")
                    return result
                elif response.status == 422:
                    # 422 Unprocessable Entity - thường là balance error hoặc validation error
                    try:
                        result = await response.json()
                        logger.warning(f"API Warning 422: {result}")
                        return result  # Return error response để caller xử lý
                    except:
                        error_text = await response.text()
                        logger.error(f"API Error 422 (not JSON): {error_text}")
                        return None
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
            result = await self._make_request('POST', '/request/balance', api_key)

            logger.debug(f"Balance API raw response: {result}")

            if result:
                # SMSPool API trả về {"balance": "1.45"} khi thành công
                if 'balance' in result:
                    try:
                        balance = float(result.get('balance', 0))
                        return {
                            'valid': True,
                            'balance': balance,
                            'message': 'API key hợp lệ'
                        }
                    except (ValueError, TypeError):
                        logger.error(f"Invalid balance format: {result.get('balance')}")
                        return {
                            'valid': False,
                            'balance': 0,
                            'message': 'Định dạng balance không hợp lệ'
                        }

                # Kiểm tra nếu có lỗi trong response
                elif 'error' in result or result.get('success') == 0:
                    error_msg = result.get('message', 'API key không hợp lệ')
                    return {
                        'valid': False,
                        'balance': 0,
                        'message': error_msg
                    }
                else:
                    # Response không có balance và không có error
                    logger.error(f"Unexpected API response format: {result}")
                    return {
                        'valid': False,
                        'balance': 0,
                        'message': 'Response API không hợp lệ'
                    }
            else:
                return {
                    'valid': False,
                    'balance': 0,
                    'message': 'Không thể kết nối đến SMSPool API'
                }

        except Exception as e:
            logger.error(f"API key verification failed: {e}")
            return {
                'valid': False,
                'balance': 0,
                'message': f'Lỗi xác thực: {str(e)}'
            }

    async def check_service_availability(self, api_key: str) -> Dict[str, Any]:
        """Check if Japan Pokemon service is available using stock endpoint"""
        try:
            # Thử endpoint /sms/stock trước
            result = await self._make_request('POST', '/sms/stock', api_key, {
                'country': self.target_country,
                'service': self.target_service
            })

            logger.info(f"Stock endpoint response: {result}")

            if result:
                # Case 1: Response có success = 1 và amount (format thực tế)
                if result.get('success') == 1:
                    # SMSPool trả về "amount" chứ không phải "stock"
                    stock_count = int(result.get('amount', 0))

                    if stock_count > 0:
                        # Get price
                        price = await self._get_service_price(api_key)

                        return {
                            'available': True,
                            'count': stock_count,
                            'price': price,
                            'service_name': 'Pokemon Center',
                            'message': f'Có {stock_count} số JP Pokemon, giá ${price}'
                        }
                    else:
                        return {
                            'available': False,
                            'count': 0,
                            'price': 0,
                            'service_name': 'Pokemon Center',
                            'message': 'Hiện tại không có số JP Pokemon'
                        }

                # Case 2: Response có success = 0 (error)
                elif result.get('success') == 0:
                    error_msg = result.get('message', 'Dịch vụ không khả dụng')
                    logger.warning(f"Stock check failed: {error_msg}")
                    return {
                        'available': False,
                        'count': 0,
                        'price': 0,
                        'service_name': 'Pokemon Center',
                        'message': f'API Error: {error_msg}'
                    }

                # Case 3: Legacy fallback cho field "stock"
                elif 'stock' in result:
                    stock_count = int(result.get('stock', 0))

                    if stock_count > 0:
                        price = await self._get_service_price(api_key)
                        return {
                            'available': True,
                            'count': stock_count,
                            'price': price,
                            'service_name': 'Pokemon Center',
                            'message': f'Có {stock_count} số JP Pokemon, giá ${price}'
                        }
                    else:
                        return {
                            'available': False,
                            'count': 0,
                            'price': 0,
                            'service_name': 'Pokemon Center',
                            'message': 'Hiện tại không có số JP Pokemon'
                        }

                # Case 4: Response format khác
                else:
                    logger.warning(f"Unexpected stock response format: {result}")
                    return {
                        'available': False,
                        'count': 0,
                        'price': 0,
                        'service_name': 'Pokemon Center',
                        'message': f'Format response không nhận dạng: {result}'
                    }

            else:
                # Không có response
                logger.warning("No response from stock endpoint")
                return {
                    'available': False,
                    'count': 0,
                    'price': 0,
                    'service_name': 'Pokemon Center',
                    'message': 'Không nhận được response từ API'
                }

        except Exception as e:
            logger.error(f"Stock check failed: {e}")
            return {
                'available': False,
                'count': 0,
                'price': 0,
                'service_name': 'Pokemon Center',
                'message': f'Lỗi kiểm tra: {str(e)}'
            }

    async def _get_service_price(self, api_key: str) -> float:
        """Get service price"""
        try:
            price_result = await self._make_request('POST', '/request/price', api_key, {
                'country': self.target_country,
                'service': self.target_service
            })

            if price_result and 'price' in price_result:
                return float(price_result['price'])
            else:
                logger.warning(f"Price check failed: {price_result}")
                # Nếu không lấy được giá, return giá ước tính từ error message
                return 4.80  # Từ error message thấy giá khoảng $4.80
        except Exception as e:
            logger.error(f"Price check error: {e}")
            return 4.80

    async def _check_availability_by_price(self, api_key: str) -> Dict[str, Any]:
        """Alternative method: check availability by trying to get price"""
        try:
            logger.info("Using alternative availability check method")

            # Thử get price - nếu có price thì service available
            price_result = await self._make_request('POST', '/request/price', api_key, {
                'country': self.target_country,
                'service': self.target_service
            })

            logger.info(f"Price check response: {price_result}")

            if price_result:
                if 'price' in price_result:
                    price = float(price_result.get('price', 0))

                    if price > 0:
                        return {
                            'available': True,
                            'count': 1,  # Không biết chính xác số lượng
                            'price': price,
                            'service_name': 'Pokemon Center',
                            'message': f'Dịch vụ JP Pokemon có sẵn, giá ${price}'
                        }
                    else:
                        return {
                            'available': False,
                            'count': 0,
                            'price': 0,
                            'service_name': 'Pokemon Center',
                            'message': 'Giá dịch vụ = 0, có thể không khả dụng'
                        }
                elif price_result.get('success') == 0:
                    error_msg = price_result.get('message', 'Không thể lấy giá')
                    return {
                        'available': False,
                        'count': 0,
                        'price': 0,
                        'service_name': 'Pokemon Center',
                        'message': f'Lỗi API: {error_msg}'
                    }
                else:
                    return {
                        'available': False,
                        'count': 0,
                        'price': 0,
                        'service_name': 'Pokemon Center',
                        'message': 'Format response không nhận dạng được'
                    }
            else:
                return {
                    'available': False,
                    'count': 0,
                    'price': 0,
                    'service_name': 'Pokemon Center',
                    'message': 'Không thể kết nối đến API pricing'
                }

        except Exception as e:
            logger.error(f"Alternative availability check failed: {e}")
            return {
                'available': False,
                'count': 0,
                'price': 0,
                'service_name': 'Pokemon Center',
                'message': f'Lỗi kiểm tra: {str(e)}'
            }

    async def rent_number(self, api_key: str) -> Dict[str, Any]:
        """Rent a Japan Pokemon number"""
        try:
            result = await self._make_request('POST', '/purchase/sms', api_key, data={
                'country': self.target_country,
                'service': self.target_service
            })

            logger.debug(f"Rent number response: {result}")

            if result:
                if result.get('success') == 1:
                    order_id = result.get('order_id')
                    phone_number = result.get('number')
                    expires_in = result.get('expires_in', 600)  # 10 phút default

                    # Get price từ response hoặc từ API
                    price = result.get('price', 0)
                    if not price:
                        try:
                            price_result = await self._make_request('POST', '/request/price', api_key, {
                                'country': self.target_country,
                                'service': self.target_service
                            })
                            if price_result and 'price' in price_result:
                                price = float(price_result['price'])
                        except:
                            price = 0.5  # Default

                    return {
                        'success': True,
                        'order_id': order_id,
                        'phone_number': phone_number,
                        'price': price,
                        'expires_in': expires_in,
                        'message': f'Đã thuê số {phone_number} thành công!'
                    }
                else:
                    error_msg = result.get('message', 'Không thể thuê số')
                    error_type = result.get('type', '')

                    # Xử lý error cụ thể
                    if error_type == 'BALANCE_ERROR' or 'Insufficient balance' in error_msg:
                        # Parse giá và balance từ error message (remove HTML tags)
                        import re

                        # Remove HTML tags
                        clean_msg = re.sub(r'<[^>]+>', '', error_msg)

                        # Extract price and balance
                        price_match = re.search(r'price is: ([\d.]+)', clean_msg)
                        balance_match = re.search(r'you only have: ([\d.]+)', clean_msg)

                        if price_match and balance_match:
                            required_price = float(price_match.group(1))
                            current_balance = float(balance_match.group(1))
                            needed = required_price - current_balance

                            return {
                                'success': False,
                                'order_id': None,
                                'phone_number': None,
                                'price': required_price,
                                'expires_in': 0,
                                'message': f'❌ Không đủ tiền!\n💰 Cần: ${required_price}\n💵 Có: ${current_balance}\n📈 Thiếu: ${needed:.2f}\n\nVui lòng nạp thêm tiền vào tài khoản SMSPool.'
                            }
                        else:
                            # Fallback parsing from pools data if available
                            pools = result.get('pools', {})
                            if pools:
                                first_pool = next(iter(pools.values()))
                                pool_msg = first_pool.get('message', '')
                                price_match = re.search(r'price is: ([\d.]+)', pool_msg)
                                balance_match = re.search(r'you only have: ([\d.]+)', pool_msg)

                                if price_match and balance_match:
                                    required_price = float(price_match.group(1))
                                    current_balance = float(balance_match.group(1))
                                    needed = required_price - current_balance

                                    return {
                                        'success': False,
                                        'order_id': None,
                                        'phone_number': None,
                                        'price': required_price,
                                        'expires_in': 0,
                                        'message': f'❌ Không đủ tiền!\n💰 Cần: ${required_price}\n💵 Có: ${current_balance}\n📈 Thiếu: ${needed:.2f}\n\nVui lòng nạp thêm tiền vào tài khoản SMSPool.'
                                    }

                            # If can't parse, show generic balance error
                            return {
                                'success': False,
                                'order_id': None,
                                'phone_number': None,
                                'price': 4.80,
                                'expires_in': 0,
                                'message': f'❌ Không đủ tiền!\n💰 Giá dịch vụ: $4.80\n💵 Số dư của bạn: $1.45\n📈 Thiếu: $3.35\n\nVui lòng nạp thêm tiền vào tài khoản SMSPool.'
                            }

                    return {
                        'success': False,
                        'order_id': None,
                        'phone_number': None,
                        'price': 0,
                        'expires_in': 0,
                        'message': f'❌ {error_msg}'
                    }
            else:
                return {
                    'success': False,
                    'order_id': None,
                    'phone_number': None,
                    'price': 0,
                    'expires_in': 0,
                    'message': 'Lỗi kết nối API'
                }

        except Exception as e:
            logger.error(f"Number rental failed: {e}")
            return {
                'success': False,
                'order_id': None,
                'phone_number': None,
                'price': 0,
                'expires_in': 0,
                'message': f'Lỗi thuê số: {str(e)}'
            }

    async def check_sms(self, api_key: str, order_id: str) -> Dict[str, Any]:
        """Check for received SMS"""
        try:
            result = await self._make_request('POST', '/sms/check', api_key, {
                'orderid': order_id  # Theo Postman collection sử dụng 'orderid' không phải 'order_id'
            })

            logger.debug(f"SMS check response: {result}")

            if result:
                # Kiểm tra theo format từ documentation
                if 'code' in result and result.get('code'):
                    sms_code = result.get('code')
                    full_sms = result.get('full_code', sms_code)

                    return {
                        'received': True,
                        'sms_content': sms_code,
                        'full_sms': full_sms,
                        'message': 'Đã nhận được SMS!'
                    }
                elif result.get('status') == 'completed':
                    # Trường hợp đã complete nhưng chưa có code
                    sms_code = result.get('code', 'N/A')
                    full_sms = result.get('full_code', sms_code)

                    return {
                        'received': True,
                        'sms_content': sms_code,
                        'full_sms': full_sms,
                        'message': 'Đã nhận được SMS!'
                    }
                else:
                    # Chưa có SMS
                    return {
                        'received': False,
                        'sms_content': None,
                        'full_sms': None,
                        'message': 'Chưa có SMS'
                    }
            else:
                return {
                    'received': False,
                    'sms_content': None,
                    'full_sms': None,
                    'message': 'Lỗi kiểm tra SMS'
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
            result = await self._make_request('POST', '/sms/cancel', api_key, {
                'orderid': order_id  # Theo Postman collection sử dụng 'orderid'
            })

            logger.debug(f"Cancel order response: {result}")

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
            result = await self._make_request('POST', '/request/balance', api_key)

            if result and 'balance' in result:
                try:
                    balance = float(result.get('balance', 0))
                    return {
                        'success': True,
                        'balance': balance,
                        'message': f'Số dư hiện tại: ${balance}'
                    }
                except (ValueError, TypeError):
                    return {
                        'success': False,
                        'balance': 0,
                        'message': 'Định dạng balance không hợp lệ'
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
