# Báo cáo kiểm thử

Ngày: 2026-08-06.

## Vòng nghiệm thu progress fingerprint

Tất cả test dùng `%TEMP%`/`tmp_path`; không đọc, ghi hoặc build lại kho 1.717 clip production.

### Baseline tái hiện

Fake ba clip và một `_run_stream` im lặng 1,5 giây phát event đầu ở 0,003 giây, sau đó không có
thêm trạng thái tới 1,503 giây rồi nhảy thẳng 100%. Bằng call graph vendored, parent audfprint
multi-core chỉ report sau khi một worker xử lý xong toàn bộ phần list của core.

### Automated result hiện tại

| Lệnh/phạm vi | Passed | Failed | Skipped/deselected | Thời lượng |
|---|---:|---:|---:|---:|
| Progress/controller/process/engine tests | 16 | 0 | 0 | 2,85 giây |
| Audfprint + FFmpeg multi-core integration thật | 1 | 0 | 0 | 7,38 giây |
| Full fast suite (lượt cuối, không có audfprint validation cạnh tranh CPU) | 299 | 0 | 1 skip, 4 slow deselect | 7,49 giây |
| Full fast suite có coverage | 299 | 0 | 1 skip, 4 slow deselect | 14,75 giây pytest |
| Ruff cho toàn bộ file thay đổi của vòng này | — | 0 finding | — | Pass |

Coverage trong lệnh cuối: `fingerprint_progress.py` 91%, `process_runner.py` 87%, `engine.py`
83%; tổng ba module được đo là 85%. Wrapper chạy ở subprocess nên coverage process cha không thu
được; đường thật của wrapper được kiểm bởi integration test.

Các test mới xác minh event đầu/discovery/start/phase/success/skip/failure/completed/cancelled,
Unicode và khoảng trắng, invariant bộ đếm/percent, ETA và total 0, event đến khi worker chưa xong,
không tạo job trùng, queue bounded, output subprocess đến trước exit, process im lặng có heartbeat,
non-zero/timeout/cancel dọn đúng root + child, skip record hợp lệ, retry zero-hash, atomic DB khi
cancel/failure và logger không giữ handle trên Windows.

### Manual Streamlit smoke

Lệnh validation chạy Streamlit bằng `.venv` hiện có nhưng inject `TIMCLIP_DATA_DIR` và
`TIMCLIP_OUTPUT_DIR` vào một root `%TEMP%` riêng. Dataset có 6 file: một đã fingerprint, bốn WAV
hợp lệ (ngắn/dài/tên có khoảng trắng/tên tiếng Việt) và một file hỏng. Không dùng SQLite hay `.pklz`
production.

- 250 ms sau click: UI hiện `Đang chuẩn bị danh sách clip` và tên đang xác định.
- 1,25 giây: job còn sống; UI hiện `1/6 — 16,7%`, skip 1, phase audfprint, PID root, số worker,
  Queue `0/256`.
- 3,75 giây: UI hiện `6/6`, 4 đã tính, 1 skip, 1 lỗi, phase saving; event log trên màn hình có tên
  file khoảng trắng, file hỏng, tiếng Việt và số FFmpeg đang sống.
- Khoảng 5 giây: summary `4 tạo mới / 1 đã tồn tại / 1 lỗi`; app tiếp tục phản hồi và DB load lại
  báo 6 record (record lỗi zero-hash sẽ được retry lần sau).
- `fingerprint.log` có 29 event gắn `job_id` của lượt smoke cùng process start/end, child PID và
  exit code. Python đọc file UTF-8 xác nhận nguyên vẹn `tiếng Việt.wav`.

### Performance/queue

Benchmark 5 vòng, 2.000 clip/4.002 event, logger bị disable để chỉ đo event/controller:

- Không callback queue: median 0,078395 giây.
- Có bounded queue/controller: median 0,122816 giây.
- Chênh lệch: 0,044421 giây (56,66% trong microbenchmark CPU-only), xấp xỉ 11 microsecond/event.
- Queue/recent: `256/256` và `50/50`; peak `tracemalloc` 657,0 KiB.
- UI rerun mỗi 0,75 giây, tức tối đa khoảng 1,33 lần/giây; không render từng dòng FFmpeg.

Phần trăm tương đối của microbenchmark cao vì baseline không có audio/FFmpeg và chỉ chạy 0,078 giây;
độ tăng tuyệt đối là số phù hợp để so với workload fingerprint nhiều giây/phút.

### Chưa kiểm thử trong vòng này

- Không chạy toàn bộ 1.717 clip thật.
- Không tạo `.venv-validation` mới; dùng `.venv` hiện có vì dependency native đã được xác minh, còn
  mọi data/output vẫn cô lập trong `%TEMP%`.
- Chưa soak cancel đúng lúc audfprint đang store một database nhiều GiB hoặc antivirus giữ file.
- Không có test ETA trực quan trên batch dài; công thức/moving window đã unit-test.

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
- Cancellation toàn process tree đã test cho fingerprint bằng root + child giả im lặng; chưa soak-test database nhiều GiB và các flow scan/channel khác.

## Rủi ro còn lại

Không thay đổi `_merge`, ngưỡng chọn lọc hay shifts mặc định. Vì slow suite chưa hoàn tất,
mọi release thay thuật toán matching vẫn phải bị chặn cho tới khi `pytest -m slow` xanh trên
máy rảnh. Xem `AUDIT_REPORT.md` cho lock scan tương tác, phần cancellation/logging còn lại ngoài
fingerprint flow.


---

## Vòng kiểm chứng độc lập của Claude — 2026-08-06

Môi trường: `.venv-claude` (Python **3.14.6** — máy không có 3.12, `py -0p` chỉ liệt kê 3.14).

| Lệnh | Passed | Failed | Skipped | Deselected |
|---|---:|---:|---:|---:|
| `pytest -p no:cacheprovider --no-header` | **339** | 0 | 1 | 4 |
| `pytest -m slow` | xem `CLAUDE_VALIDATION_REPORT.md` | | | |
| `ruff check .` | `All checks passed!` | | | |
| `compileall` (13 module chính) | exit 0 | | | |
| `pip check` | `No broken requirements found.` | | | |
| `git diff --check` | sạch | | | |

**Baseline trước vòng này: 330 passed, 1 skipped, 1 FAILED.**
`test_app.py::test_giao_dien_khong_loi_render` gọi `AppTest.from_file("app.py")`;
Streamlit 1.61 giải đường dẫn tương đối theo file gọi (`tests/`) chứ không theo CWD.
Đã sửa bằng đường dẫn tuyệt đối dựng từ `__file__`.

### Test mới bổ sung trong vòng này

| File | Số test | Bảo vệ điều gì |
|---|---:|---|
| `tests/test_fingerprint_progress_streaming.py` | 5 | Event per-clip vẫn tới khi audfprint **không in `ingesting #`** (đúng nhánh `ncores>1`); heartbeat khi subprocess im lặng; UI thấy tiến độ khi worker còn chạy; không tạo job trùng; queue bounded |
| `tests/test_app_fingerprint_progress.py` | 2 | Khung hình tiến độ **giữa chừng** của `app.py` có tên clip/công đoạn/`2/3`/elapsed; ba đoạn ⇒ ba video gốc, tổng `so_dat_nguong=12` giữ nguyên, không bịa ngày đăng |
| `tests/test_va_meta.py` (bổ sung) | 3 | Clip trên đĩa chưa có entry vẫn vá được; không tạo rác cho file không có VIDEO_ID; không ghi đè metadata chính thức bằng dữ liệu suy từ tên file |

### Số liệu cũ trong tài liệu này

Các số ở những mục phía trên là của vòng Codex và **chưa được chạy lại** trong vòng này.
Số liệu đã kiểm chứng nằm ở [CLAUDE_VALIDATION_REPORT.md](CLAUDE_VALIDATION_REPORT.md).


---

## Vòng ngày đăng — 2026-08-07

| Bộ | Kết quả |
|---|---|
| `tests/test_publication_date.py` (mới) | 30 passed |
| `tests/test_publication_date_exporters.py` (mới) | 7 passed |
| `tests/test_kiem_ngay_dang.py` (mới) | 7 passed |
| Fast suite toàn bộ | **400 passed, 1 skipped, 5 deselected** |
| `ruff check .` | All checks passed |
| `compileall`, `pip check` | sạch |

Bao phủ: upload thường · premiere/scheduled (`release_timestamp` thắng
`upload_date`) · `release_date` khi không có epoch · ranh giới 16:59:59 và 17:00:00
UTC · cùng ngày thì không cảnh báo thừa · metadata legacy · fallback tên file và
quy tắc metadata chính thức thắng tên file · ngày không hợp lệ · thiếu ngày ·
epoch mili giây bị từ chối rõ ràng · epoch âm/bool/chuỗi · **độc lập múi giờ máy**
(chạy lại trong tiến trình con với TZ = UTC / LA / Tokyo / Kiritimati) · múi giờ
không tồn tại lùi về UTC.

Guard cấu trúc: không module nào ngoài `publication_date.py` được tự định dạng
`%d/%m/%Y`, tự quy đổi epoch, hay dùng `timedelta(days=...)` cho ngày đăng.
Ngoại lệ liệt kê tường minh: `app.py` (đồng hồ tiến trình), `nhat_ky.py` (hạn giữ log).

Regression hai video thật, fixture chứa đúng raw field dẫn tới quyết định:
`Asv1kjFuX-4` → 01/08/2026, `T_mKh8IUpWw` → 21/06/2025.


---

## Vòng Scan Pipeline V2 — 2026-08-07

| Bộ | Kết quả |
|---|---|
| `tests/test_scan_streaming.py` (mới) | 12 passed |
| `tests/test_sheet_delivery.py` (mới) | 14 passed |
| `tests/test_sheets_session.py` (mới) | 15 passed |
| `tests/test_app_scan_progress.py` (mới) | 1 passed |
| **Fast suite toàn bộ** | **449 passed, 1 skipped, 5 deselected** |
| `ruff` · `compileall` · `pip check` · `git diff --check` | sạch |

Bao phủ đáng chú ý:

- Hai luồng quét chạy chồng nhau (`threading.Barrier`) không xoá chunk của nhau.
- Kết quả video 1 xuất hiện khi batch chưa xong (`controller.results()` khác rỗng
  trong lúc `completed < total`).
- Sheets chậm 0,3 s/lần: `enqueue()` của 5 video vẫn dưới 0,2 s ⇒ scan không bị chặn.
- Sheets sập hoàn toàn: 5/5 `failed`, không mất trạng thái, scan vẫn chạy hết.
- Lỗi vĩnh viễn (`PERMISSION_DENIED`) chỉ thử **một** lần; lỗi tạm thời thử lại có backoff.
- 10 lần append chỉ xác thực + mở bảng **một** lần; `get_all_values()` **0** lượt.
- `sheets.append()` không tự thử lại ⇒ không sinh dòng trùng.
- 12 thread append đồng thời vẫn dùng chung một kết nối.


---

## Vòng sửa thread boundary + Arrow schema — 2026-08-07

| Bộ | Kết quả |
|---|---|
| `tests/test_scan_ui_schema.py` (mới) | 9 passed |
| `tests/test_scan_thread_boundary.py` (mới) | 10 passed |
| `tests/test_app_scan_no_warnings.py` (mới) | 1 passed |
| **Fast suite toàn bộ** | **470 passed, 1 skipped, 5 deselected** |
| `ruff` · `compileall` · `pip check` | sạch |
| Streamlit thật (cổng 8503, data dir tạm) | health `200 ok`, trang `200`, terminal không có ArrowInvalid/Serialization/ScriptRunContext |

Đáng chú ý:

- `pa.Table.from_pandas()` chạy thẳng trên bảng trạng thái với đủ tổ hợp trạng thái
  (chưa quét · 0 đoạn · N đoạn · lỗi · đang chạy), cả khung rỗng và batch 50 dòng.
- Callback chạy thật trong thread nền với `st.session_state` bị thay bằng đối tượng
  cấm truy cập — test đỏ ngay nếu worker chạm vào.
- Callback ném exception: 3/3 video vẫn `completed`, kết quả vẫn còn.
- Guard cấu trúc bỏ bình luận/chuỗi bằng `tokenize` nên không bắt nhầm chính phần
  docstring giải thích, và có test khẳng định guard bắt được vi phạm thật.


---

## Vòng chọn kết quả đại diện — 2026-08-07

| Bộ | Kết quả |
|---|---|
| `tests/test_match_selection.py` (mới) | 26 passed |
| **Fast suite toàn bộ** | **496 passed, 1 skipped, 5 deselected** |
| `ruff` · `compileall` · `pip check` | sạch |

Bao phủ: match mạnh ở cuối thắng match yếu ở đầu · ngang bằng thì chọn đoạn sớm hơn ·
compilation 8 tiếng · đoạn 20 giây không thắng đoạn 15 phút · bậc "bằng chứng mạnh"
không bị dung sai phá · không biết thời lượng video · `start_s` âm · một ứng viên duy
nhất · danh sách rỗng · dung sai = 0 · **kết quả không đổi qua 50 lần xáo trộn đầu
vào** · phá hoà theo tên clip · `top_n=1` trả đúng một kết quả · `top_n>1` vẫn giữ
phân bổ đều theo vùng · dưới ngưỡng vẫn bị loại · không bịa kết quả khi không ai đạt
ngưỡng · `Config` từ chối dung sai vô lý.

Đối chứng trên 200 job thật trong `lichsu.db`: 188 giữ nguyên (94%), 12 đổi (6%) —
xa ngưỡng cảnh báo 80–90%, đúng vùng near-tie.


---

## Vòng đổi khoá chất lượng sang ty_le — 2026-08-07

| Bộ | Kết quả |
|---|---|
| `tests/test_match_selection.py` | 34 passed (26 cũ + 8 mới) |
| **Fast suite toàn bộ** | **504 passed, 1 skipped, 5 deselected** |
| `ruff` · `compileall` · `pip check` | sạch |

Test mới tái hiện đúng hai ca thật: job 316 (sàn phải chặn) và job 315 (sàn phải cho
qua), cộng test chứng minh bỏ sàn thì `ty_le` thắng luôn — tức chính cái sàn tạo ra
khác biệt chứ không phải thứ khác.

Đối chứng 283 job thật: `ty_le` thuần đổi 58 % Top-1 với 30 ca đánh đổi nặng;
`ty_le` + sàn 0,70 đổi 46 % với **0** ca đánh đổi nặng (28 ca bị chặn).
