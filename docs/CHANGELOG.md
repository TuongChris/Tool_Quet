# Changelog

## 2026-07-29 — Phase 2b: overlap có trần và merge theo mật độ hash

- Thêm trần overlap cấu hình được, mặc định 180 giây; loại bỏ anomaly khiến clip
  50 phút tốn gần 6 lần audio trong khi clip 60 phút chỉ tốn gần 2 lần.
- Gộp mảnh bằng hợp interval và tích phân mật độ hash tốt nhất theo từng đoạn con.
  Clip bị chia ở ranh giới khúc giữ đủ bằng chứng mà vùng overlap không bị đếm đôi.
- Kẹp hash theo tổng vân tay clip và phát cảnh báo khi chạm cận trên hoặc thiếu
  metadata tổng hash.
- Không gọi ffmpeg tại đúng EOF và báo tiến độ trước lúc audfprint nạp kho.
- Gỡ file ZIP nguồn khỏi Git, giữ nguyên bản sao trên máy người dùng.
- Kiểm thử: `248 passed, 1 skipped, 3 deselected`; nhóm slow:
  `3 passed, 249 deselected`.
