<<<<<<< HEAD
"""
Cấu hình node detect_person.

Chỉ cần sửa ROOM_ID để xác định dữ liệu camera sẽ cập nhật cho phòng nào.
API_BASE_URL trỏ tới địa chỉ đang chạy smart_rental.

Nếu smart_rental cấu hình OCCUPANCY_API_KEY thì điền cùng giá trị vào API_KEY.
Có thể dùng biến môi trường để không phải ghi secret vào source:
    DETECT_ROOM_ID
    SMART_RENTAL_API_URL
    OCCUPANCY_API_KEY
"""
import os


ROOM_ID = "yOfcHH3uhxHdXJNs6nzj"

API_BASE_URL = os.getenv(
    "SMART_RENTAL_API_URL",
    "http://127.0.0.1:5000",
).rstrip("/")

OCCUPANCY_API_URL = f"{API_BASE_URL}/api/monitoring/occupancy"

API_KEY = os.getenv("OCCUPANCY_API_KEY", "").strip()

# Gửi lại trạng thái định kỳ để server không đánh dấu dữ liệu là stale.
HEARTBEAT_SECONDS = 60

# HTTP timeout cho mỗi lần cập nhật.
REQUEST_TIMEOUT_SECONDS = 5
=======
"""
Cấu hình node detect_person.

Chỉ cần sửa ROOM_ID để xác định dữ liệu camera sẽ cập nhật cho phòng nào.
API_BASE_URL trỏ tới địa chỉ đang chạy smart_rental.

Nếu smart_rental cấu hình OCCUPANCY_API_KEY thì điền cùng giá trị vào API_KEY.
Có thể dùng biến môi trường để không phải ghi secret vào source:
    DETECT_ROOM_ID
    SMART_RENTAL_API_URL
    OCCUPANCY_API_KEY
"""
import os


ROOM_ID = "yOfcHH3uhxHdXJNs6nzj"

API_BASE_URL = os.getenv(
    "SMART_RENTAL_API_URL",
    "http://127.0.0.1:5000",
).rstrip("/")

OCCUPANCY_API_URL = f"{API_BASE_URL}/api/monitoring/occupancy"

API_KEY = os.getenv("OCCUPANCY_API_KEY", "").strip()

# Gửi lại trạng thái định kỳ để server không đánh dấu dữ liệu là stale.
HEARTBEAT_SECONDS = 60

# HTTP timeout cho mỗi lần cập nhật.
REQUEST_TIMEOUT_SECONDS = 5
>>>>>>> e9c4bb4de6487f0343579edf12926d46b1325b5c
