# Tổng quan hệ thống TimClip Pro

## Mục đích

TimClip Pro tìm các clip gốc xuất hiện trong video dài bằng vân tay âm thanh. Ứng dụng tải
audio YouTube hoặc đọc media cục bộ, cắt thành các khúc WAV, gọi audfprint để đối chiếu,
gộp bằng chứng ở biên khúc, lưu lịch sử SQLite và xuất CSV/Markdown/Google Sheets.

## Công nghệ và kiểu ứng dụng

- Runtime: Python. Runtime mục tiêu rõ nhất trong repository là Python 3.12 (`Dockerfile`);
  tài liệu cũ ghi 3.10–3.13. Baseline tại máy audit dùng Python 3.14.6.
- UI: Streamlit chạy local, entry point `app.py`.
- CLI/automation: `cli.py`; chế độ giám sát được điều phối bởi `watch.py`.
- Xử lý media: FFmpeg/FFprobe; bản Windows project-local nằm trong `bin/`.
- Tải và đọc metadata YouTube: yt-dlp.
- Nhận dạng: bản vendored MIT của `audfprint` trong `audfprint-master/`.
- Dữ liệu: JSON nguyên tử, SQLite, pickle nén gzip theo format của audfprint.
- Tích hợp tùy chọn: Google Sheets qua gspread/service account.
- Kiểm thử: pytest và Streamlit AppTest.
- Container: Dockerfile + Docker Compose; chưa có quy trình PyInstaller/.exe.

## Sơ đồ module

```text
ChayTool.bat -> app.py (Streamlit) ---------+
cli.py --------------------+                |
watch.py ------------------|----------------+
                            v
                     engine.py
               +------------+-------------+
               |            |             |
          channel.py    audfprint      FFmpeg/yt-dlp
               |      (subprocess)       |
               +------------+-------------+
                            |
          +-----------------+------------------+
          |                 |                  |
      luu_tru.py        SQLite             báo cáo
   JSON + backup      lichsu.db      bang_ngang/dossier
                                             |
                                         sheets.py
```

Các module vận hành bổ trợ:

- `khoa.py`: khóa file liên tiến trình.
- `dung_lai.py`: gom Ctrl+C, SIGTERM, cờ Engine và file `data/DUNG`.
- `don_dep.py`: dọn cache tải theo tuổi/dung lượng.
- `nhat_ky.py`: tee stdout/stderr của CLI watch sang log theo ngày.
- `cau_hinh.py`: allowlist và lưu cấu hình không bí mật.
- `dong_goi.py`: đóng gói mã nguồn để gửi audit, không phải build executable.

## Entry point và cách chạy hiện tại

- GUI: `python -m streamlit run app.py` hoặc `ChayTool.bat`.
- CLI: `python cli.py <lenh>`.
- Giám sát: `python cli.py watch ...` hoặc `GiamSat.bat`.
- Container: `docker compose up --build` sau khi sửa bind mount trong compose.
- Test nhanh: `python -m pytest`; test audio thật: `python -m pytest -m slow`.

Launcher ban đầu ưu tiên `py -3`/`python` toàn hệ thống dù repository có `.venv`.
`cai_dat.bat` ban đầu cũng cài dependency vào interpreter toàn hệ thống thay vì tạo môi
trường cô lập.

## Luồng chạy chính

### Tạo kho vân tay

1. `Engine.build_database()` lấy `data/tool.lock`.
2. `liet_ke_media()` duyệt clip nguồn và ghi `data/_ds_clip.txt` UTF-8.
3. `_run_stream()` gọi `audfprint.py new/add` bằng chính Python hiện tại.
4. Database `.pklz` được đăng ký trong `data/khos.json`.
5. Metadata tiêu đề/link/thời lượng nằm trong `clips_meta.json` ở kho clip.

### Quét media cục bộ

1. `scan_media()` kiểm tra môi trường và file đầu vào.
2. `_cut_chunks()` dùng FFmpeg cắt WAV mono 11025 Hz vào `data/chunks/`.
3. `_match_chunks()` gọi audfprint, parse `data/_raw_match.txt` bằng `RE_MATCH`.
4. `_merge()` gộp interval theo align/dedup và tích phân mật độ hash tốt nhất.
5. `_gan_chi_so()` và `_chon_loc()` áp ngưỡng/chọn top N mà không đổi trong audit này.
6. `save_job()` lưu job/match vào SQLite; exporter sinh báo cáo.

### Quét YouTube và giám sát

1. `youtube_info()` lấy ID, tiêu đề, kênh, ngày đăng.
2. `download_audio()` tải/tiếp tục tải audio vào `data/downloads/`.
3. Audio đi qua luồng `scan_media()` ở trên.
4. `watch.chay_giam_sat()` lấy khóa, khử trùng ID đã quét, chạy tuần tự, ghi từng phần
   lên Sheets (nếu bật), xuất CSV và dọn cache trong `finally`.

## Luồng dữ liệu và nơi lưu

| Dữ liệu | Vị trí | Ghi chú |
|---|---|---|
| Cấu hình UI/Engine | `data/cau_hinh.json` + `.bak` | Bị Git ignore |
| Đăng ký kho | `data/khos.json` + `.bak` | Chứa tên file `.pklz` và đường dẫn kho |
| Vân tay | `data/*.pklz` | Pickle gzip theo format audfprint |
| Lịch sử | `data/lichsu.db` | SQLite `jobs` + `matches` |
| Audio tải | `data/downloads/` | Cache có ngân sách tuổi/dung lượng |
| Khúc tạm | `data/chunks/` | Xóa sau mỗi scan |
| Báo cáo | `ketqua/` | CSV, Markdown, log watch |
| Credential Sheets | `google_key.json` | Có thật trên máy, bị Git ignore |
| Watch list | `watchlist.json` | Hiện đang được Git theo dõi |

JSON cấu hình/metadata dùng ghi `.tmp` + `fsync` + `os.replace`, có backup `.bak` và
giữ file hỏng dưới hậu tố `.hong.<timestamp>`.

## Thành phần ngoài và dependency quan trọng

- `numpy`, `scipy`, `joblib`, `psutil`, `docopt`: nền audfprint.
- `yt-dlp`: networking/tải YouTube.
- `streamlit`, `pandas`: UI và bảng/CSV tải từ UI.
- `gspread`, `google-auth`: Google Sheets tùy chọn.
- `ffmpeg`, `ffprobe`: executable ngoài Python.
- Docker base `python:3.12-slim`; FFmpeg được cài bằng apt trong image.

`requirements.txt` ban đầu không khóa phiên bản và trộn production với tất cả tích hợp tùy
chọn. `requirements-lock.txt` tồn tại nhưng đang untracked từ trước audit và được bảo toàn.

## Concurrency, hủy và resource

- Streamlit chạy một `threading.Thread(daemon=True)` cho job dài, trao đổi trạng thái qua
  dict trong `st.session_state`.
- audfprint tự dùng multiprocessing theo `ncores`; Engine tự chọn tối đa 8 core.
- `threading.Event` dùng cho nút hủy.
- `KhoaTienTrinh` khóa file cấp OS cho dựng kho và cả lượt watch.
- JSON có `RLock` theo đường dẫn nhưng chỉ bảo vệ giữa thread trong cùng process.
- SQLite mở connection theo thao tác và đóng bằng context manager.

## Khu vực rủi ro cao

1. Docker build context ban đầu không có `.dockerignore`, trong khi workspace có credential,
   138.91 GiB dữ liệu/cache và `.venv`.
2. Tên file database đọc từ `khos.json` được join trực tiếp; kết hợp `pickle.loads()` và xóa
   kho tạo bề mặt path traversal/deserialization nếu file registry bị sửa độc hại.
3. `engine.py` lớn và gom networking, subprocess, storage, matching và reporting; thay đổi
   dễ có regression nên thuật toán `_merge`/ngưỡng không được refactor trong lượt này.
4. Các subprocess FFmpeg dùng `subprocess.run()` không hủy được giữa một khúc; audfprint có
   worker con nên việc terminate parent chưa đảm bảo dọn toàn cây.
5. Test fixture ban đầu gọi `Engine(root=<repository>)` trước khi chuyển đường dẫn sang tmp,
   khiến test có thể chạm SQLite/config thật.
6. CSV/Sheets nhận title/link từ bên ngoài; Sheets ban đầu dùng `USER_ENTERED`.

## Điều chưa thể xác minh

- Docker image build/run: Docker CLI có nhưng daemon không chạy tại thời điểm audit.
- Hành vi với YouTube/Google Sheets thật: không dùng credential, không phát request ghi thật.
- Slow audio suite: baseline chạm timeout 244 giây; tiến trình audit đã được dừng mà không
  chạm phiên audfprint thật đang chạy của người dùng.
- Windows 10/11 sạch không có Python/FFmpeg: chưa có VM sạch để nghiệm thu installer.
- Antivirus false positive và startup của executable: dự án chưa có build executable.
- Khả năng tương thích runtime khác: máy audit chỉ có Python 3.14.6.

