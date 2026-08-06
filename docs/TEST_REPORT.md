# Báo cáo kiểm thử

Ngày: 2026-08-06.

## Môi trường

- OS: Windows, PowerShell.
- Runtime có trên máy: Python 3.14.6 64-bit trong `.venv`.
- pip: 26.1.2.
- pytest: 9.1.1.
- Streamlit: 1.60.0.
- yt-dlp: 2026.07.04.
- FFmpeg/FFprobe: 8.1.2 essentials build.
- Docker CLI: 29.6.1; Docker daemon không chạy.

Python 3.12 là target tài liệu/Docker nhưng không được cài trên máy audit; vì vậy chưa có
test matrix đa phiên bản.

## Baseline trước sửa

| Lệnh | Kết quả |
|---|---|
| `.\.venv\Scripts\python.exe -m pytest --disable-warnings` | 248 passed, 1 skipped, 3 deselected; 6.63s |
| import `engine, channel, sheets, cli, watch` | OK; tiến trình đo khoảng 147 ms |
| `.\.venv\Scripts\python.exe -m pip check` | Không có requirement hỏng |
| Health `/_stcore/health` | HTTP 200 `ok` |
| `pytest -m slow` | Timeout 244s, không có kết quả pytest hoàn chỉnh |
| Docker version/build | CLI có; daemon không kết nối nên chưa build |

Slow timeout để lại cây pytest con; audit đã xác minh đúng PID/command và chỉ dừng cây test
do audit tạo. Phiên Streamlit/audfprint thật đọc `data/` được bảo toàn và không bị dừng.

## Regression test đã thêm

- Chặn absolute/path traversal của database kho và không xóa file ngoài `data/`.
- CSV không ghi đè và escape formula prefix.
- Google Sheets gửi dữ liệu bằng `RAW`.
- Đồng bộ bị cancel không báo video chưa tải là thành công.
- Config từ chối resource bounds nguy hiểm.
- yt-dlp luôn có socket timeout và retry hữu hạn; timeout config bị giới hạn 5–300 giây.
- Engine fixture/AppTest dùng data/output tạm ngay từ constructor.
- Source packager loại file nhạy cảm không phân biệt hoa/thường, giữ build/vendor asset,
  từ chối overwrite.
- `.dockerignore` có các nhóm chốt credential/runtime bắt buộc.

## Kết quả sau sửa

| Lệnh | Passed | Failed | Skipped/deselected | Kết quả |
|---|---:|---:|---:|---|
| Targeted security/core/config/app | 55 | 0 | 0 | 6.64s |
| Targeted packaging/security/app | 30 | 0 | 0 | 2.04s |
| Full fast suite (vòng trước) | 277 | 0 | 1 skipped, 3 slow deselected | 7.47s |
| Full fast suite + coverage cuối | 283 | 0 | 1 skipped, 3 slow deselected | 7.48s |
| Ruff `E4,E7,E9,F` qua `ruff.toml` | — | 0 finding | — | Pass |
| `pip check` | — | 0 conflict | — | Pass |
| `pip-audit -r requirements.txt` | — | 0 known vulnerability | — | Pass sau constraint |
| Source package smoke | 92 entries | 0 sensitive entry | — | 225 KB, có Dockerfile + audfprint |
| UI health | — | — | — | HTTP 200 `ok` |

Một test khóa được skip có chủ đích vì Windows không cho xóa file đang có handle mở. Ba test
integration mang marker `slow` bị deselect bởi `pytest.ini` trong fast suite.

## Coverage

Coverage đo cho `engine`, `channel`, `watch`, `luu_tru`, `cau_hinh`, `sheets`, `dong_goi`:

| Module | Coverage |
|---|---:|
| `cau_hinh.py` | 97% |
| `watch.py` | 94% |
| `luu_tru.py` | 92% |
| `engine.py` | 80% |
| `channel.py` | 71% |
| `dong_goi.py` | 67% |
| `sheets.py` | 49% |
| Tổng 1.628 statement | 80% |

Adapter Sheets thấp vì không dùng service account/API thật; các nhánh download/FFmpeg thật
của channel/engine cũng được để cho integration/manual test.

## Dependency audit

Baseline trên `requirements-lock.txt` untracked báo ba advisory:

- `cryptography 49.0.0` → minimum fixed 50.0.0.
- `GitPython 3.1.55` → minimum fixed 3.1.57 (hai advisory).

`constraints.txt` khóa đúng hai minimum này. Audit resolver trên `requirements.txt` sau sửa
báo “No known vulnerabilities found”. File lock untracked của người dùng không bị sửa.

## Build/package

- Source zip: pass trong pytest `%TEMP%`, không overwrite `TimClipPro_source.zip` hiện có;
  allowlist cuối có 96 file/658.355 byte thô và 0 basename nhạy cảm.
- Docker: chưa build vì Docker Desktop/Linux daemon không chạy; `.dockerignore` đã loại context
  138.91 GiB ban đầu gồm data/venv/credential khỏi build.
- PyInstaller/.exe: không áp dụng vì repository chưa có quy trình đó.

## Chưa thể test

- Slow audio suite hoàn chỉnh khi máy rảnh.
- YouTube download/metadata thật, rate limit, age restriction và network outage (policy yt-dlp đã được fake-test).
- Google Sheets read/write thật vì không sử dụng credential.
- Disk full, antivirus lock kéo dài, Windows long-path policy khác.
- Docker build/run trên daemon hoạt động.
- Python 3.12 clean-machine install và các runtime khác.
- Cancellation toàn process tree khi audfprint/FFmpeg im lặng.

## Rủi ro còn lại

Không thay đổi `_merge`, ngưỡng chọn lọc hay shifts mặc định. Vì slow suite chưa hoàn tất,
mọi release thay thuật toán matching vẫn phải bị chặn cho tới khi `pytest -m slow` xanh trên
máy rảnh. Xem `AUDIT_REPORT.md` cho lock scan tương tác, process-tree cancellation và logging.
