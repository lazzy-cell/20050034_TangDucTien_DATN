# Smart Rental Management System

> **Đồ án tốt nghiệp:** Xây dựng hệ thống quản lý nhà trọ thông minh sử dụng IoT, Computer Vision và Cloud.

## Giới thiệu

Đây là hệ thống quản lý nhà trọ thông minh, hỗ trợ chủ trọ quản lý phòng, người thuê, theo dõi điện năng và điều khiển thiết bị từ xa.

Hệ thống sử dụng **ESP32** để thu thập dữ liệu điện, **Raspberry Pi** để xử lý dữ liệu và nhận diện người trong phòng, kết hợp với **Firebase** để lưu trữ và đồng bộ dữ liệu.

## Kiến trúc hệ thống

Hệ thống gồm các thành phần chính:

* **IoT (ESP32):** Thu thập dữ liệu điện và điều khiển nguồn điện.
* **Edge (Raspberry Pi):** Xử lý dữ liệu, MQTT và nhận diện người bằng Computer Vision.
* **Backend (Flask):** Xử lý API và kết nối các thành phần hệ thống.
* **Cloud (Firebase):** Xác thực, lưu trữ và đồng bộ dữ liệu.
* **Web / Mobile:** Theo dõi và quản lý hệ thống.

## Công nghệ và công cụ phát triển

| Thành phần       | Công nghệ             |
| ---------------- | --------------------- |
| IoT              | ESP32                 |
| Đo điện          | PZEM-004T             |
| Giao tiếp        | MQTT, JSON            |
| Edge Computing   | Raspberry Pi          |
| Computer Vision  | OpenCV, MobileNet-SSD |
| Backend          | Python, Flask         |
| Cloud / Database | Firebase              |
| Mobile           | React Native, Expo    |
| Web              | JavaScript            |

## Tác giả

**Tăng Đức Tiền** — Sinh viên trường đại học Bình Dương — Đồ án tốt nghiệp ngành Kỹ thuật phần mềm, khoa CNTT.
