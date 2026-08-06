# Runbook vận hành TimClip Pro

## Preflight mỗi lần vận hành quan trọng

```powershell
Set-Location "D:\Tool_Tim_Video_v2\TimClipPro"
git status --short
& ".\.venv\Scripts\python.exe" --version
& ".\.venv\Scripts\python.exe" -m pip check
& ".\bin\ffmpeg.exe" -version
```

Kiểm health khi GUI đã chạy:

```powershell
Invoke-WebRequest -UseBasicParsing "http://127.0.0.1:8501/_stcore/health"
```

Kết quả chuẩn là HTTP 200 và nội dung `ok`.

## Khởi động và dừng

GUI:

```powershell
& ".\ChayTool.bat"
```

Giám sát có log:

```powershell
& ".\.venv\Scripts\python.exe" cli.py watch --file ".\watchlist.local.json" --log
```

Yêu cầu dừng lượt watch từ PowerShell khác:

```powershell
& ".\.venv\Scripts\python.exe" cli.py dung
```

GUI có nút “Dừng lại”. Hiện cancellation có thể chỉ được kiểm tra giữa các subprocess dài;
không kill process bằng Task Manager trừ khi đã chấp nhận output dở dang.

## Lock và chạy đồng thời

`data\tool.lock` bảo vệ dựng kho và cả lượt watch. Không xóa lock khi PID ghi trong file còn
sống. Scan tương tác trực tiếp hiện dùng các file temp chung nhưng chưa lấy cùng lock; quy tắc
vận hành là chỉ chạy một job nặng trên một repository tại một thời điểm.

Kiểm PID khóa:

```powershell
Get-Content ".\data\tool.lock"
Get-Process -Id <PID>
```

## Backup và phục hồi

Đợi mọi job dừng rồi backup:

```powershell
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$backupRoot = "D:\TimClipPro_Backup\$stamp"
New-Item -ItemType Directory -Path $backupRoot -Force | Out-Null
Copy-Item ".\data" "$backupRoot\data" -Recurse
Copy-Item ".\watchlist.local.json" "$backupRoot\watchlist.local.json" -ErrorAction SilentlyContinue
```

Thành phần quan trọng:

- `data\khos.json` + `.bak`: registry kho.
- `data\*.pklz`: vân tay, tốn nhiều giờ để tái tạo.
- `data\lichsu.db`: lịch sử.
- `downloaded.txt` và `clips_meta.json` trong thư mục clip gốc.
- `google_key.json`: backup ở secret manager riêng, không cùng source archive.

Khi JSON chính hỏng, lớp storage tự thử `.bak` và giữ bản lỗi dưới `.hong.*`. Không sửa cả
file chính lẫn backup cùng lúc.

## Quy trình dựng/cập nhật kho

```powershell
& ".\.venv\Scripts\python.exe" cli.py taodb "D:\ClipGoc"
& ".\.venv\Scripts\python.exe" cli.py themclip "D:\ClipMoi"
```

`taodb` có thể thay file vân tay đang dùng; backup `data\` trước. Không đặt file `.pklz` tải
từ nguồn lạ vào `data\`. Nếu shifts của kho và config lệch, tạo lại kho có kiểm soát thay vì
trộn fingerprint khác tham số.

## Quy trình quét

File cục bộ:

```powershell
& ".\.venv\Scripts\python.exe" cli.py file "D:\VideoDai\video.mp4"
```

YouTube:

```powershell
& ".\.venv\Scripts\python.exe" cli.py youtube "https://youtu.be/VIDEO_ID"
```

Kiểm báo cáo trong `ketqua\` và job trong tab Lịch sử. Exporter không ghi đè: nếu tên tồn
tại, file mới nhận hậu tố `_2`, `_3`, ... Cell có prefix công thức được xuất dưới dạng text.

## Cache và dung lượng

Xem trước, không xóa:

```powershell
& ".\.venv\Scripts\python.exe" cli.py dondep --xem-truoc
```

Thực hiện theo `dem_max_gb`/`dem_max_ngay`:

```powershell
& ".\.venv\Scripts\python.exe" cli.py dondep
```

File `.part`/`.ytdl` đang tải không bị dọn. Vẫn backup nếu cache là nguồn duy nhất khó tải lại.

## Google Sheets

1. Kiểm `google_key.json` tồn tại nhưng không in nội dung.
2. Chia sẻ Sheet cho service account.
3. Dùng nút “Kiểm tra kết nối” trong UI.
4. Dữ liệu được gửi với mode `RAW`, không thực thi title/link như công thức.
5. Không chạy `kiem_sheet.py` trên bảng thật nếu chưa chấp nhận một dòng test sẽ được ghi.

## Log và xử lý sự cố

- Watch log: `ketqua\giamsat_YYYY-MM-DD.log` khi dùng `--log`.
- Log giữ 30 ngày theo tên ngày; chưa có rotation theo kích thước.
- Thông báo user, URL và path có thể xuất hiện trong log; không gửi log công khai trước khi
  redact.

Khi job lỗi:

1. Ghi command, thời điểm, source type và message.
2. Chạy `pip check`, check FFmpeg và health.
3. Không chạy lại đồng thời khi process cũ còn sống.
4. Dùng một file/URL reproduction nhỏ; không dùng credential thật trong test.
5. Nếu là thay đổi matching, chạy fast suite rồi slow suite khi máy rảnh.

## QA trước release

```powershell
& ".\.venv\Scripts\python.exe" -m pytest
& ".\.venv\Scripts\python.exe" -m pytest -m slow
& ".\.venv\Scripts\ruff.exe" check .
& ".\.venv\Scripts\python.exe" -m pip_audit -r requirements.txt --progress-spinner off
& ".\.venv\Scripts\python.exe" dong_goi.py --output "$env:TEMP\TimClipPro_source_release_check.zip"
```

Source packager mặc định từ chối overwrite; chỉ dùng `--overwrite` khi target đã được xác minh.

## Docker

```powershell
docker version
docker compose build
docker compose up -d
docker compose ps
Invoke-WebRequest -UseBasicParsing "http://127.0.0.1:8501/_stcore/health"
```

`.dockerignore` phải còn rule cho `google_key.json`, `data/`, `ketqua/`, `.venv/`, `bin/`,
log và archive. Credential chỉ mount read-only khi cần.

## Hạn chế vận hành đang mở

- yt-dlp có retry hữu hạn và timeout 30 giây; Google API vẫn phụ thuộc timeout của SDK.
- Không có process-tree cancellation đã soak-test trên Windows.
- Scan tương tác chưa dùng job temp directory riêng/lock chung.
- GUI chưa có structured technical log.
- Docker build cần nghiệm thu lại trên máy có daemon.
