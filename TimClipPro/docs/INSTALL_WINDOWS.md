# Cài đặt TimClip Pro trên Windows

## 1. Yêu cầu hệ thống

- Windows 10/11 64-bit.
- Python 3.12 64-bit từ python.org; chọn “Add python.exe to PATH”.
- Ít nhất vài GB trống cho dependency và audio; video dài có thể cần nhiều hơn đáng kể.
- Kết nối mạng cho lần cài đầu, yt-dlp và Google Sheets (nếu dùng).
- FFmpeg/FFprobe: ưu tiên hai file project-local trong `bin\`.

Python 3.12 là runtime hỗ trợ chính. Fast suite đã chạy trên Python 3.14.6 nhưng slow suite
chưa hoàn tất trên runtime đó; không mặc định coi mọi dependency đều hỗ trợ các bản Python
mới hơn trong tương lai.

## 2. Mở PowerShell và vào dự án

Mở Start Menu, gõ `PowerShell`, chọn Windows PowerShell. Không cần “Run as administrator”.

```powershell
Set-Location "D:\Tool_Tim_Video_v2\TimClipPro"
```

Kiểm tra runtime:

```powershell
py -3.12 --version
```

Kết quả phải bắt đầu bằng `Python 3.12`. Nếu lệnh không có, cài Python 3.12 64-bit rồi mở
PowerShell mới.

## 3. Tạo virtual environment project-local

```powershell
Set-Location "D:\Tool_Tim_Video_v2\TimClipPro"
py -3.12 -m venv .venv
& ".\.venv\Scripts\python.exe" --version
```

Không bắt buộc chạy `Activate.ps1`; gọi thẳng interpreter trong `.venv` tránh lỗi execution
policy và tránh vô tình dùng Python toàn hệ thống.

## 4. Cài dependency

Runtime:

```powershell
& ".\.venv\Scripts\python.exe" -m pip install --upgrade pip
& ".\.venv\Scripts\python.exe" -m pip install -r requirements.txt
& ".\.venv\Scripts\python.exe" -m pip check
```

Nếu phát triển/test:

```powershell
& ".\.venv\Scripts\python.exe" -m pip install -r requirements-dev.txt
```

`constraints.txt` giữ đúng minimum đã vá cho các dependency bắc cầu có advisory; không dùng
`pip install -U` cho toàn bộ môi trường nếu chưa test regression.

## 5. Cài dependency ngoài Python

Repository hiện có `audfprint-master\` và thường có `bin\ffmpeg.exe`, `bin\ffprobe.exe`.
Kiểm tra:

```powershell
Test-Path ".\audfprint-master\audfprint.py"
Test-Path ".\bin\ffmpeg.exe"
& ".\bin\ffmpeg.exe" -version
& ".\bin\ffprobe.exe" -version
```

Nếu FFmpeg/audfprint thiếu, dùng installer tương thích cũ:

```powershell
& ".\cai_dat.bat"
```

Installer tải artifact qua HTTPS nhưng chưa xác minh checksum. Trong môi trường kiểm soát
nghiêm ngặt, quản trị viên nên cung cấp binary đã xác minh vào `bin\` thay vì tải tự động.

## 6. Cấu hình

### Kho và preference

UI lưu preference không bí mật trong `data\cau_hinh.json`. Registry kho nằm ở
`data\khos.json`. Không chỉnh tay trường `db`; ứng dụng chỉ chấp nhận basename `.pklz` nằm
trực tiếp trong `data\`.

### Watch list

Tạo bản local từ mẫu rồi chỉnh URL/tên kho:

```powershell
Copy-Item ".\watchlist.example.json" ".\watchlist.local.json"
notepad ".\watchlist.local.json"
```

Chạy với `--file .\watchlist.local.json`. Không đưa danh sách vận hành riêng tư vào source zip.

### Google Sheets tùy chọn

Đặt service-account JSON dưới đúng tên `google_key.json` ở root. Không paste private key vào
`.env`, source, log hoặc ticket. Chia sẻ Sheet cho `client_email` với quyền Editor, rồi dán
link Sheet trong UI. Nếu không dùng Sheets, không cần file này.

## 7. Chạy development

```powershell
Set-Location "D:\Tool_Tim_Video_v2\TimClipPro"
& ".\.venv\Scripts\python.exe" -m streamlit run app.py --server.address=127.0.0.1 --server.port=8501 --browser.gatherUsageStats=false
```

Mở <http://127.0.0.1:8501>. Đóng PowerShell sẽ dừng server; tác vụ dài đang chạy cũng dừng.

Launcher double-click:

```powershell
& ".\ChayTool.bat"
```

## 8. Chạy CLI

```powershell
& ".\.venv\Scripts\python.exe" cli.py -h
& ".\.venv\Scripts\python.exe" cli.py taodb "D:\ClipGoc"
& ".\.venv\Scripts\python.exe" cli.py file "D:\VideoDai"
& ".\.venv\Scripts\python.exe" cli.py watch --file ".\watchlist.local.json" --log
```

Luôn quote đường dẫn có khoảng trắng hoặc tiếng Việt. Source dùng UTF-8 và subprocess
audfprint được ép `PYTHONUTF8=1`; tuy vậy long path vẫn phụ thuộc chính sách Windows và độ dài
tên kho. Đặt dự án/kho ở đường dẫn tương đối ngắn nếu gặp WinError 206.

## 9. Chạy test

```powershell
& ".\.venv\Scripts\python.exe" -m pytest
& ".\.venv\Scripts\python.exe" -m pytest -m slow
& ".\.venv\Scripts\ruff.exe" check .
```

Chỉ chạy slow suite khi không có job audfprint thật; test này dùng CPU và có thể mất nhiều phút.

## 10. Docker tùy chọn

Sửa hai bind mount Windows trong `docker-compose.yml`, bảo đảm Docker Desktop đang chạy:

```powershell
docker compose build
docker compose up -d
docker compose ps
```

Không bake `google_key.json` vào image. Nếu cần Sheets, bỏ comment bind mount read-only đã có
trong compose. Truy cập <http://127.0.0.1:8501>.

## 11. Lỗi thường gặp

| Triệu chứng | Lệnh/chẩn đoán |
|---|---|
| Không tìm thấy Python 3.12 | `py -0p` rồi cài Python 3.12 64-bit |
| Import lỗi | `& ".\.venv\Scripts\python.exe" -m pip check` |
| Thiếu FFmpeg | `Test-Path ".\bin\ffmpeg.exe"`; chạy `cai_dat.bat` |
| UI không mở | Kiểm port: `Test-NetConnection 127.0.0.1 -Port 8501` |
| Port 8501 bận | Chạy với `--server.port=8502` |
| Báo đang có job | Đọc `data\tool.lock`; không xóa lock khi process chủ vẫn chạy |
| JSON hỏng | Ứng dụng thử `.bak`, giữ bản hỏng dưới `.hong.<timestamp>` |
| YouTube 403 | Cập nhật riêng yt-dlp sau khi backup/test; không commit cookie/token |
| Docker không kết nối daemon | Mở Docker Desktop, chờ engine Linux sẵn sàng |

## 12. Log và output

- CSV/Markdown/log watch: `ketqua\`.
- CLI watch chỉ ghi log khi có `--log`.
- GUI hiện chưa có structured traceback log; giữ thông báo lỗi và reproduction khi báo lỗi.
- `session.log` lịch sử đang tracked từ source cũ; không đưa log mới vào commit/source zip.

## 13. Cập nhật an toàn

Trước cập nhật:

```powershell
git status
$backupRoot = "D:\TimClipPro_Backup"
New-Item -ItemType Directory -Path $backupRoot -Force | Out-Null
Copy-Item ".\data" "$backupRoot\data_$(Get-Date -Format yyyyMMdd_HHmmss)" -Recurse
```

Sau khi pull/copy source mới:

```powershell
& ".\.venv\Scripts\python.exe" -m pip install -r requirements.txt
& ".\.venv\Scripts\python.exe" -m pip check
& ".\.venv\Scripts\python.exe" -m pytest
```

Không xóa `.pklz`, SQLite, metadata hoặc archive tải để “cài sạch” nếu chưa có backup.
