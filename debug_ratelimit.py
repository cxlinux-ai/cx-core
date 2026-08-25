import time
from unittest.mock import patch
from cx.system_alert_manager import RateLimiter

limiter = RateLimiter(max_requests=2, window_seconds=1)
limiter.is_allowed('test_user')
limiter.is_allowed('test_user')
limiter.is_allowed('test_user')

print('Before patch:', limiter.requests['test_user'])
with patch('time.time') as mock_time:
    mock_time.return_value = time.time() + 2
    print('Mock return:', mock_time.return_value, type(mock_time.return_value))
    print('Mocked time.time():', time.time(), type(time.time()))
    try:
        result = limiter.is_allowed('test_user')
        print('Result:', result)
    except Exception as e:
        print('Error:', e)
        import traceback
        traceback.print_exc()
