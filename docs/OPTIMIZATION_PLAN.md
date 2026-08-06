# Kế hoạch sửa lỗi và tối ưu TimClip Pro

Ưu tiên dùng `Impact × Likelihood × Ease of verification ÷ Regression risk`. Mọi thay đổi
trong nhóm 1–2 phải giữ nguyên thuật toán `_merge`, ngưỡng nhận diện và schema báo cáo công khai.

## 1. Sửa lỗi bắt buộc

| Ưu tiên | Hạng mục | Điểm tương đối | Cách xác minh |
|---|---|---:|---|
| P0 | Thêm `.dockerignore`, chặn credential/data/venv/log/bin/archive | 100 | Đo context + inspect rule + Docker build khi daemon có |
| P0 | Chặn path traversal của file kho `.pklz` | 90 | Test absolute/`..`/xóa ngoài data |
| P0 | Cô lập test khỏi `data/` và `ketqua/` thật | 88 | Spy path + full fast suite |
| P1 | Constraint hai dependency có advisory và audit lại | 75 | pip-audit + pip check + pytest |
| P1 | Sheets ghi RAW, CSV escape formula | 72 | Fake worksheet + CSV regression test |
| P1 | Không ghi đè báo cáo CSV | 68 | Sentinel + suffix test |
| P1 | Sửa số lượng sync khi cancel | 65 | Cancel trước/giữa/lỗi test |

## 2. Tối ưu ít rủi ro

1. Mở rộng `Config.validate()` cho resource bounds mà không đổi default.
2. Compile/giữ regex hiện có; không có bằng chứng regex compile là bottleneck.
3. Giữ cache `db_clips()` theo `(path, mtime_ns, size)` vì đã giải quyết reread file lớn.
4. Đồng bộ help overlap theo policy trần và thêm xác nhận xóa trong UI.
5. Venv hóa launcher; tách dependency dev khỏi runtime.
6. Refactor source packager thành hàm có thể test, loại basename nhạy cảm case-insensitive.
7. Đặt timeout socket yt-dlp 30 giây, giữ retry hữu hạn hiện có và validate config 5–300 giây.

## 3. Refactor có kiểm soát

Chưa thực hiện trong lượt sửa ít rủi ro nếu chưa có soak test:

1. Tạo một job/workspace tạm riêng cho mỗi scan thay vì `data/chunks` dùng chung.
2. Đưa khóa vào mọi entry point scan bằng wrapper `_scan_*_da_khoa`, tránh nested lock ở watch.
3. Tách `ProcessRunner` có cancellation, timeout terminate/kill và dọn process tree.
4. Tách `HistoryStore`, `FingerprintStore` và reporter khỏi `Engine` nhưng giữ facade cũ.
5. Gỡ import vòng báo cáo bằng protocol/type-only import.

## 4. Nâng cấp dependency

1. Chỉ nâng `cryptography` lên tối thiểu 50.0.0 và GitPython lên tối thiểu 3.1.57 vì
   advisory cụ thể; không nâng hàng loạt.
2. Bảo toàn `requirements-lock.txt` đang untracked; không tự ghi đè.
3. Dài hạn dùng lock có hash được tạo từ Python 3.12 trong CI/máy build sạch.
4. Pin commit/checksum audfprint và FFmpeg download ở phase supply-chain riêng; không theo
   `master.zip`/`latest` vô điều kiện.

## 5. Cải thiện UI/UX

1. Xác nhận trước xóa kho vân tay và lịch sử.
2. Hiển thị “đã hủy” khác “đồng bộ xong”; không báo số tải mới sai.
3. Sửa mô tả overlap có trần 180 giây.
4. Dài hạn thêm nút mở thư mục output và trang log kỹ thuật đã redact.
5. Dài hạn nối file `data/DUNG` vào cancellation giữa video với subprocess đang chạy.

## 6. Bổ sung test

- Config: bounds, compatibility khi thiếu field mới.
- Path: registry kho không thoát data; Unicode/space giữ hoạt động.
- URL: giữ test parser hiện có; không siết URL GUI làm thay đổi yt-dlp contract.
- Filename: ký tự Windows và package secret filename case-insensitive.
- Network: fake timeout/retry yt-dlp đã có; Google API/live outage để phase integration.
- Cancellation: số đếm sync; subprocess tree ở phase riêng.
- Output: formula escape, RAW Sheets, không overwrite.
- Compatibility: schema JSON cũ và constructor Engine mặc định.
- Build: `.dockerignore`, source archive không chứa file cấm.

## 7. Đề xuất dài hạn chưa thực hiện

1. CI Windows + Python 3.12 chạy fast suite, AppTest, secret scan và dependency audit.
2. Job directory riêng dưới `data/temp/<job-id>` và cleanup recovery sau crash.
3. SQLite WAL/busy timeout sau khi lock boundary được thống nhất.
4. Structured logging có timestamp/level/module/job ID, redaction và size rotation.
5. Installer xác minh SHA-256 cho FFmpeg/audfprint artifact.
6. Docker Compose mount credential read-only thay vì bake vào image.
7. Benchmark end-to-end trên một corpus đại diện sau khi job hiện tại kết thúc; không dùng
   số đo giả hoặc thay ngưỡng dựa trên synthetic-only benchmark.
