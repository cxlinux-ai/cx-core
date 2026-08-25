import time
from unittest.mock import patch

with patch('time.time') as mock_time:
    print('Before assignment, mock_time():', mock_time())
    mock_time.return_value = time.time() + 2
    print('After assignment, mock_time():', mock_time())
    print('return_value:', mock_time.return_value, type(mock_time.return_value))
