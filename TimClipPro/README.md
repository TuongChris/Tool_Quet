# TimClip Pro

TimClip Pro tìm clip gốc xuất hiện trong video dài bằng audio fingerprinting. Ứng dụng có
giao diện Streamlit chạy local, CLI cho automation, chế độ giám sát YouTube, lịch sử SQLite,
CSV/Markdown và tích hợp Google Sheets tùy chọn.

## Khởi động nhanh trên Windows

Runtime chuẩn: Python 3.12 64-bit. Máy audit cũng đã chạy fast suite thành công trên
Python 3.14.6, nhưng Python 3.12 là phiên bản dùng trong Docker và tài liệu cài đặt.

```powershell
Set-Location "D:\Tool_Tim_Video_v2\TimClipPro"
py -3.12 -m venv .venv
& ".\.venv\Scripts\python.exe" -m pip install --upgrade pip
& ".\.venv\Scripts\python.exe" -m pip install -r requirements.txt
& ".\.venv\Scripts\python.exe" -m streamlit run app.py --server.address=127.0.0.1 --server.port=8501 --browser.gatherUsageStats=false
```

Nếu máy chưa có FFmpeg trong `bin\`, chạy `cai_dat.bat`; script sẽ dùng/tạo `.venv` và
tải FFmpeg. Sau khi UI mở, truy cập <http://127.0.0.1:8501>.

## Các entry point

- GUI: `app.py` qua `ChayTool.bat` hoặc `python -m streamlit run app.py`.
- CLI: `cli.py` với các lệnh `kenh`, `taodb`, `themclip`, `youtube`, `file`, `watch`,
  `vameta`, `dondep`, `dung`.
- Giám sát định kỳ: `GiamSat.bat` hoặc `python cli.py watch`.
- Source package an toàn: `dong_goi.py` (không phải executable build).
- Container: `Dockerfile` + `docker-compose.yml`.

Ví dụ CLI:

```powershell
Set-Location "D:\Tool_Tim_Video_v2\TimClipPro"
& ".\.venv\Scripts\python.exe" cli.py taodb "D:\ClipGoc"
& ".\.venv\Scripts\python.exe" cli.py file "D:\VideoDai"
& ".\.venv\Scripts\python.exe" cli.py youtube "https://youtu.be/VIDEO_ID"
& ".\.venv\Scripts\python.exe" cli.py watch --file ".\watchlist.example.json"
```

## Test và kiểm tra chất lượng

```powershell
Set-Location "D:\Tool_Tim_Video_v2\TimClipPro"
& ".\.venv\Scripts\python.exe" -m pip install -r requirements-dev.txt
& ".\.venv\Scripts\python.exe" -m pytest
& ".\.venv\Scripts\python.exe" -m pytest -m slow
& ".\.venv\Scripts\ruff.exe" check .
& ".\.venv\Scripts\python.exe" -m pip_audit -r requirements.txt --progress-spinner off
```

Fast suite sau audit: 283 passed, 1 skipped, 3 slow deselected; coverage đo trên các module
lõi được chọn là 80%. Slow suite đã được thử nhưng timeout trong lúc có job audfprint thật
đang dùng CPU, vì vậy phải chạy lại khi máy rảnh trước release liên quan matching.

## Dữ liệu và bí mật

- Dữ liệu bền vững: `data/`.
- Báo cáo/log watch: `ketqua/`.
- Credential Sheets tùy chọn: `google_key.json` ở root, tuyệt đối không commit/bake vào image.
- Watch list mẫu: `watchlist.example.json`; không đưa URL vận hành nhạy cảm vào source package.
- Docker context đã loại credential, data, log, `.venv`, binary Windows và archive qua
  `.dockerignore`.

Không xóa hoặc ghi đè `data/*.pklz`, `data/lichsu.db`, `downloaded.txt` hay
`clips_meta.json` nếu chưa có backup. Đừng mở/chạy file `.pklz` nhận từ nguồn không tin cậy;
đây là format pickle của audfprint.

## Tài liệu

- [Cài đặt Windows](docs/INSTALL_WINDOWS.md)
- [Runbook vận hành](docs/RUNBOOK.md)
- [Tổng quan kiến trúc](docs/SYSTEM_OVERVIEW.md)
- [Báo cáo audit](docs/AUDIT_REPORT.md)
- [Kế hoạch tối ưu](docs/OPTIMIZATION_PLAN.md)
- [Kết quả test](docs/TEST_REPORT.md)
- [Changelog audit/tối ưu](docs/CHANGELOG_OPTIMIZATION.md)
- [Hướng dẫn sử dụng chi tiết](HUONG_DAN.md)

## Giới hạn

- Chỉ nhận dạng được khi audio gốc còn đủ dấu vân tay; video bị thay/mute toàn bộ tiếng cần
  một nhánh nhận dạng hình ảnh khác.
- Tải nội dung YouTube có thể chịu giới hạn mạng, quyền truy cập và điều khoản nền tảng.
- Google Sheets chỉ hoạt động khi người dùng chủ động cung cấp service account và chia sẻ Sheet.
- Chưa có PyInstaller/.exe; `dong_goi.py` chỉ tạo source zip.
- Docker build chưa được chạy trong audit vì Docker daemon không hoạt động.
