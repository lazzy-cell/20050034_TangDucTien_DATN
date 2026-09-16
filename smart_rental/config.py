import os


class Config:

    DEBUG = True

    FIREBASE_KEY_PATH = "credentials/firebase-key.json"

    DEFAULT_ELECTRICITY_PRICE = 3500

    # Ngưỡng cảnh báo điện
    ALERT_HIGH_POWER = 3000      # Watt
    ALERT_HIGH_CURRENT = 20      # Ampere
    ALERT_LOW_VOLTAGE = 180      # Volt
    ALERT_HIGH_VOLTAGE = 250     # Volt
    ALERT_DEBOUNCE_COUNT = 3     # Số lần vi phạm liên tiếp mới tạo alert

    # Automation: tự ngắt điện khi HIGH_POWER / HIGH_CURRENT
    AUTO_CUT_POWER = True

    # Automation: tự ngắt điện khi phòng liên tục không có người.
    # Đơn vị: giây. Chỉ trạng thái "vacant" được tính; "unknown" sẽ
    AUTO_CUT_EMPTY_ROOM_SECONDS =  10
    

    # Nếu phòng VACANT nhưng vẫn tiêu thụ điện trên ngưỡng này, tạo
    # cảnh báo OCCUPANCY_POWER. Không phụ thuộc AUTO_CUT_POWER.
    VACANT_POWER_ALERT_WATTS = float(
        os.getenv("VACANT_POWER_ALERT_WATTS", "20")
    )

    # Computer Vision / room occupancy API.
    # Có thể override bằng biến môi trường OCCUPANCY_API_KEY.
    # Nếu để trống, API giám sát không yêu cầu API key.
    OCCUPANCY_API_KEY = os.getenv("OCCUPANCY_API_KEY", "").strip()
