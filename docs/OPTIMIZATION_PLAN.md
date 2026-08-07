# Kế hoạch sửa lỗi và tối ưu TimClip Pro

Ưu tiên dùng `Impact × Likelihood × Ease of verification ÷ Regression risk`. Mọi thay đổi
trong nhóm 1–2 phải giữ nguyên thuật toán `_merge`, ngưỡng nhận diện và schema báo cáo công khai.

## Vòng progress fingerprint — 2026-08-06

Ưu tiên theo `Impact × Likelihood × Ease of verification ÷ Regression risk`:

| Ưu tiên | Hạng mục | Trạng thái | Bằng chứng |
|---|---|---|---|
| P0 | Event thật từng clip/phase thay callback phần trăm nguyên khối | Hoàn tất | Unit + audfprint multi-core integration + browser smoke |
| P0 | Không ghi trực tiếp DB thật; workspace + atomic replace | Hoàn tất | Cancel/failure sentinel regression; DB thật tạm load được |
| P0 | Reader/poll subprocess không deadlock khi im lặng; cancel đúng cây PID | Hoàn tất | 5 subprocess tests trên Windows |
| P1 | Controller một worker + queue bounded + session snapshot | Hoàn tất | Queue 256, recent 50, duplicate/cancel integration tests |
| P1 | UI placeholder, bộ đếm, elapsed/rate/ETA/PID/heartbeat | Hoàn tất | Browser smoke quan sát ở 250 ms, 1,25 s, 3,75 s và cuối job |
| P1 | Terminal + rotating file logger UTF-8, flush và traceback | Hoàn tất cho fingerprint | Log smoke có PID/phase/file/exit code; Windows handle test |
| P2 | Check fingerprint đã có chỉ khi `so_hash > 0` | Hoàn tất | Existing được skip; zero-hash được retry |
| P3 | Resume staged fingerprint sau cancel | Chưa làm | Cần thay đổi contract/storage audfprint, regression risk cao |
| P3 | Nhận biết file cùng path đã đổi nội dung | Chưa làm | `.pklz` không có mtime/size/content hash; cần quyết định migration |

Chi phí event đo tổng hợp trên 2.000 clip (4.002 event): median tăng 0,044421 giây, khoảng
11 microsecond/event. Queue đạt trần 256, recent đạt trần 50, peak `tracemalloc` 657,0 KiB.
Đây là overhead CPU của controller trong benchmark không sleep; UI thực chỉ rerun mỗi 0,75 giây.

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
3. Mở rộng `process_runner.py` đã dùng cho fingerprint sang FFmpeg/yt-dlp của các flow scan/channel
   sau khi có soak test riêng; không thay máy móc call site hiện có.
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
- Cancellation: số đếm sync; fingerprint đã dọn đúng subprocess tree, scan/channel còn ở phase riêng.
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
