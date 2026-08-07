# Changelog audit và tối ưu

Ngày: 2026-08-06.

## Vòng observability tạo vân tay — 2026-08-06

| File | Nội dung và lý do | Rủi ro | Test xác minh | Trước → Sau |
|---|---|---|---|---|
| `fingerprint_progress.py` | Event immutable, tracker invariant/ETA, terminal + rotating file logger, một worker/controller và queue bounded | Medium | Progress/controller unit + Unicode/queue/cancel | Callback phần trăm nghèo, shared dict → event thật, snapshot, queue 256/recent 50 |
| `process_runner.py` | Reader/poll loop, heartbeat, child PID, tail bounded, timeout/cancel đúng process tree | Medium | Output-live/silent/nonzero/timeout/cancel tests | Block trên stdout và terminate parent → poll được khi im lặng, dọn root + descendants |
| `audfprint_progress_runner.py` | Instrument trước/sau từng `wavfile2hashes` mà không sửa vendor/thuật toán/DB format | Medium | Multi-core integration thật | Parent chỉ report sau cả core-list → JSON event per-file ngay khi worker chạy |
| `engine.py` | Nối event, skip positive hash/retry zero-hash, workspace per job, atomic DB replace, summary success/skip/fail/cancel | Medium | Engine regressions + real audfprint smoke | Một subprocess ghi thẳng DB, progress cuối batch → per-file + DB cũ sống qua cancel/failure |
| `app.py` | Controller trong session, placeholder cố định, phase/clip/count/elapsed/rate/ETA/PID/heartbeat/recent log, duplicate guard | Low–medium | App tests + browser smoke 6 fixture | UI gần như im lặng → cập nhật sau 250 ms và trong lúc job còn chạy |
| `cli.py` | Summary tạo mới/skip/lỗi/cancel theo result mới | Low | Full fast suite | Chỉ tổng clip/thời gian → outcome rõ |
| `tests/test_fingerprint_progress.py` | Contract, invariant, ETA, Unicode, queue, duplicate, cancel | Low | 6 tests pass | Không có → regression coverage |
| `tests/test_process_runner.py` | Output tức thời, silent heartbeat, nonzero, timeout/cancel tree | Low | 5 tests pass | Không có → chứng minh không chờ process kết thúc/deadlock |
| `tests/test_fingerprint_engine_progress.py` | Parse event, skip/retry, atomic DB, Windows logger handle | Low | 4 tests pass | Không có → regression storage/process boundary |
| `tests/test_audfprint_progress_integration.py` | FFmpeg + audfprint multi-core thật trên WAV tạm | Low | 1 slow test pass | Không có → event phải đến trước commit được chứng minh |
| `tests/test_app.py`, `tests/test_shifts.py`, `tests/test_tang_toc.py` | Cập nhật fake/signature theo API additive và DB temp | Low | Full fast suite | Fake cũ không phản ánh staging → test tương thích |

Hành vi ảnh hưởng người dùng: màn hình tạo vân tay có trạng thái chi tiết và nút dừng chính xác hơn;
CLI có thêm outcome; mode add cần dung lượng tạm xấp xỉ kích thước DB hiện có để đảm bảo atomic.
API cũ `build_database(..., progress=...)` vẫn được giữ; event/job ID là tham số tùy chọn mới.

Không thay đổi: audfprint vendored, Analyzer/HashTable, `_merge`, threshold, top-N, shifts, schema
SQLite, fingerprint format, dữ liệu/credential production.

Vấn đề còn lại: chưa nghiệm thu 1.717 clip thật; chưa resume phần staged sau cancel; chưa nhận biết
file cùng path đổi nội dung; progress structured chưa mở rộng sang toàn bộ scan/channel.

## Thay đổi source/runtime

| File | Nội dung và lý do | Rủi ro | Test xác minh | Trước → Sau |
|---|---|---|---|---|
| `engine.py` | Inject `data_dir/out_dir`; validate resource/timeout config; chặn path database thoát data; yt-dlp timeout; export CSV exclusive + formula-safe | Medium | security/core/config/network/full suite | Test khởi tạo data thật, registry có thể traversal, network có thể chờ default, CSV overwrite → storage tạm, path bị từ chối, timeout 30s, suffix `_2` |
| `channel.py` | Đếm số tải thành công thực, trả `da_huy`, đặt yt-dlp socket timeout | Low | cancel/network regression/full suite | Cancel có thể báo toàn bộ đã tải và request dùng default → báo đúng số, timeout 30s |
| `sheets.py` | Gửi cell bằng `RAW` | Low–medium | fake worksheet/full suite | `USER_ENTERED` có thể chạy công thức → dữ liệu thuần |
| `app.py` | Data/output override qua env cho test/deploy; CSV download formula-safe; trạng thái cancel; help overlap đúng policy; xác nhận xóa | Low–medium | AppTest/full suite | Test/UI phụ thuộc data thật, xóa một bước → cô lập và xác nhận hai bước |
| `cli.py` | In `ĐÃ DỪNG` cho channel sync bị cancel | Low | full suite | Cancel vẫn ghi `XONG` → trạng thái rõ |
| `dong_goi.py` | Refactor thành hàm/CLI testable; deny secret case-insensitive; giữ audfprint/build file; loại runtime config; từ chối overwrite | Low | packaging tests + zip smoke | Archive cố định bị overwrite và có thể lọt nested secret → output explicit, kiểm tra hai lớp |

## Build, dependency và vận hành

| File | Nội dung và lý do | Rủi ro | Test xác minh |
|---|---|---|---|
| `.dockerignore` | Loại credential, 138.91 GiB data, venv, log, Windows binary, archive | Low | rule regression + source/context review |
| `Dockerfile` | Copy `constraints.txt` trước bước cài requirements | Low | Docker contract test + Compose config |
| `constraints.txt` | Minimum fixed cho cryptography/GitPython theo pip-audit | Medium | pip-audit resolver sạch + pip check |
| `requirements.txt` | Áp security constraint | Low–medium | pip-audit + fast suite |
| `requirements-dev.txt` | Khai báo pytest, coverage, pip-audit, Ruff riêng dev | Low | cài/run thật trong `.venv` |
| `ruff.toml` | Lint tập trung lỗi cú pháp/import/tên, không bulk restyle source cũ | Low | `ruff check .` pass |
| `cai_dat.bat` | Tạo `.venv`, ưu tiên Python 3.12 | Medium | static review; clean VM còn pending |
| `ChayTool.bat`, `GiamSat.bat`, `kiemtra.bat` | Ưu tiên `.venv`, fallback tương thích | Low | static review + UI/CLI smoke |
| `docker-compose.yml` | Gợi ý mount credential read-only, không bake | Low | review; Docker daemon pending |
| `.gitignore` | Ignore log/Ruff/coverage artifact mới | Low | `git status` |
| `watchlist.example.json` | Mẫu không chứa URL vận hành thật | Low | parser/package test |

## Test

| File | Thay đổi |
|---|---|
| `tests/conftest.py` | Fixture Engine truyền storage tạm trước mọi side effect |
| `tests/test_app.py` | AppTest dùng env data/output tạm |
| `tests/test_security_regressions.py` | Test path traversal, overwrite, formula, Sheets RAW, cancel, config, timeout/retry |
| `tests/test_packaging.py` | Test source package/Docker ignore/Docker constraint copy |
| `tests/test_core.py`, `tests/test_nhat_ky.py` | Bỏ import thừa để lint sạch |

Kết quả: fast suite tăng từ 248 pass lên 283 pass; không có test fail. Coverage module được đo
80%. Slow suite chưa kết luận vì timeout/cạnh tranh CPU với job thật.

## Tài liệu

Đã thêm/cập nhật:

- `README.md`.
- `docs/SYSTEM_OVERVIEW.md`.
- `docs/AUDIT_REPORT.md`.
- `docs/OPTIMIZATION_PLAN.md`.
- `docs/TEST_REPORT.md`.
- `docs/INSTALL_WINDOWS.md`.
- `docs/RUNBOOK.md`.
- `docs/CHANGELOG_OPTIMIZATION.md`.
- `HUONG_DAN.md` (quyền riêng tư, runtime, venv, 5 tab, overlap, cookie).

## Thay đổi có thể ảnh hưởng người dùng

1. Export CSV không còn ghi đè target; path trả về có thể có hậu tố `_2`, `_3`.
2. Cell CSV nguy hiểm có thêm apostrophe để spreadsheet coi là text; Sheets dùng RAW.
3. Config thủ công ngoài bounds bị từ chối/reset về default theo cơ chế startup hiện có.
4. Registry kho chỉ chấp nhận basename `.pklz` trực tiếp trong `data`; path tuyệt đối/legacy
   ngoài data không còn được phép.
5. Xóa kho/lịch sử trên UI cần tick xác nhận.
6. Launcher ưu tiên `.venv`; môi trường global cũ chỉ là fallback.
7. Source packager không ghi đè nếu thiếu `--overwrite` và không đưa `watchlist.json` runtime vào zip.
8. Request/tải yt-dlp có timeout socket 30 giây; `network_timeout_s` hợp lệ trong 5–300 giây.

## Không thay đổi

- Thuật toán `_merge`, overlap policy, thresholds, top-N, shifts mặc định.
- Schema CSV/Sheets 15/34 cột.
- Schema SQLite và dữ liệu thật.
- API YouTube/Google credential hoặc nội dung người dùng.
- `requirements-lock.txt` untracked ban đầu.
- `session.log` tracked ban đầu (không xóa/untrack trong audit).

## Vấn đề còn tồn tại

- Cancellation process tree của scan/channel và soak test database fingerprint rất lớn; fingerprint flow cơ bản đã triển khai/test.
- Lock và temp workspace riêng cho scan tương tác.
- Timeout/backoff riêng cho Google API và hành vi mạng thật.
- Structured logging/redaction/size rotation cho scan/channel; fingerprint flow đã có logger riêng.
- Pin/checksum supply-chain cho artifact tải.
- Docker build, Python 3.12 clean install, slow suite và API thật chưa nghiệm thu do môi trường.


---

## 2026-08-06 — Vòng review độc lập của Claude

### Sửa lỗi

- **`tests/test_app.py`** — `AppTest.from_file("app.py")` giải đường dẫn tương đối theo
  `tests/` trên Streamlit 1.61 ⇒ suite đỏ. Đổi sang đường dẫn tuyệt đối dựng từ `__file__`.
- **`channel.py` — `ChannelSync.va_metadata()`** chỉ lặp qua các key đã có trong
  `clips_meta.json`. Kho Cory có 1717 file trên đĩa nhưng chỉ 86 entry ⇒ **1631 clip
  không thể vá metadata bằng bất kỳ thao tác nào**. Thêm `seed_meta_tu_dia()`: tạo entry
  từ tên file `<ngày> - <tiêu đề> [<VIDEO_ID>].opus` (chỉ `id`/`title`/`url`;
  `upload_date`/`duration` để trống cho fetcher điền bằng dữ liệu thật). Không ghi đè
  metadata chính thức đã có.
- **`channel.py`** — `save_meta()` được gọi sau **mỗi** mục ⇒ O(n²) I/O trên 1631 mục.
  Đổi sang ghi theo lô 25 mục + ghi ở `finally` để crash giữa chừng không mất dữ liệu.

### Thay đổi hỗ trợ kiểm thử

- **`engine._run_stream()`** nhận thêm tham số `heartbeat_seconds` (mặc định 10.0, không
  đổi hành vi) để test heartbeat không phải chờ 10 giây thật.
- **`clip_metadata.filename_fallback_parts()`** — API công khai, để `channel.py` và
  resolver dùng chung **một** cách bóc tách tên file thay vì hai định nghĩa lệch nhau.

### Thay đổi contract

- `ChannelSync.va_metadata()` trả thêm khoá `da_them_tu_dia`. `cli.py vameta` in thêm số
  này. Đã cập nhật call site và test.

### Đã xác nhận đúng, giữ nguyên

`fingerprint_progress.py`, `process_runner.py`, `audfprint_progress_runner.py`,
`clip_metadata.py`, `kiem_metadata_kho.py`, màn hình tiến độ trong `app.py`,
resolver dùng chung ở `bang_ngang.py`/`dossier.py`/`engine.to_rows()`, lệnh `vametak`.

### Sửa deadlock nhánh đa nhân của audfprint

- **`audfprint_progress_runner.py` — `instrumented_multiproc_add()`**: thay
  `audfprint.multiproc_add`. Bản vendored đẩy nguyên một `HashTable` **419 MB mỗi worker**
  (~3,3 GB với `--ncores 8`) qua `multiprocessing.Pipe`, giữ mọi đầu ghi ở tiến trình cha
  và không có timeout ⇒ treo cứng **40 % số lần** (đo 8/20 lượt trên chính audfprint gốc).
  Bản mới: worker ghi bảng ra file tạm gzip, pipe chỉ mang dict trạng thái; cha đóng đầu
  ghi ngay sau `start()` nên worker chết thành `EOFError`; `recv()` có `poll(1800 s)` làm
  lưới an toàn; file tạm xoá ngay sau merge.
  → **0/20 lượt treo**, trung bình **6,4 s** so với 8,2 s của bản gốc.
  → Bảng hash, `counts` và danh sách file **giống hệt từng ô** so với audfprint gốc.
- **`audfprint_progress_runner.py` — `_emit()`**: ghi bằng đúng một `os.write()` thay vì
  `print()`. Tám tiến trình con ghi chung một pipe stdout; `print()` tách nhiều lần ghi
  làm lồng dòng và mất progress event (quan sát 7/8 thay vì 8/8).
- **`audfprint_progress_runner.py` — `cai_dat_instrumentation()`**: tách phần gắn bản vá
  ra khỏi `main()` để test được cả ba điểm vá.
- **`process_runner.py`**: rút stdout theo lô và soi cây process theo nhịp 0,2 giây thay vì
  sau mỗi dòng. Thông lượng **138 → 15.094 dòng/giây**.

Test mới: `tests/test_audfprint_multiproc.py` (4 test) và
`tests/test_audfprint_progress_integration.py::test_nhanh_da_nhan_that_khong_treo_va_khong_mat_event`
(slow, 3 lượt build thật với `ncores=8`).

### Lấy đúng ngày đăng khi đồng bộ kênh

- **`channel._tai_va_nen()`**: đổi `ydl.download()` → `ydl.extract_info(download=True)`.
  Lượt tải vốn đã trích xuất đầy đủ trang video nhưng giá trị trả về bị vứt đi; giờ dùng
  nó để lấy `upload_date`/`duration`/`title` thật — **không thêm request mạng nào**.
  Trả về `(đường_dẫn, VideoInfo đã bổ sung)`.
- **`channel.ngay_dang_tu_info()`** / **`bo_sung_video_info()`**: rút ngày từ
  `upload_date`, hoặc `release_timestamp`/`timestamp` khi có; không bao giờ ghi đè dữ
  liệu tốt bằng rỗng.
- **`channel.list_channel()`**: thêm `lay_ngay_dang=False` (mặc định giữ nguyên tốc độ —
  một request cho cả kênh) và `chi_tiet=` để test offline. Bật cờ thì chỉ hỏi lại những
  video còn thiếu ngày, có báo tiến độ, một video lỗi không làm hỏng cả danh sách.
- **`channel._ten_file()`**: lọc qua `valid_upload_date()` — `00000000` chỉ khi thật sự
  không có ngày, không bịa ngày hôm nay.
- **`ChannelSync.lay_info_video()`**: một điểm trích xuất đầy đủ dùng chung.
  `channel.va_metadata` và `engine.va_metadata_thieu` cùng dùng `ngay_dang_tu_info()`.
- **`clip_metadata.valid_upload_date()`**: API công khai để hai module dùng chung một
  định nghĩa "ngày đăng hợp lệ".
- **`app.py`**: thêm ô chọn "Lấy cả ngày đăng chính xác" cho bảng xem trước (mặc định
  tắt) và caption cho biết bao nhiêu video chưa có ngày trong danh sách nhanh.

Test mới: `tests/test_ngay_dang.py` (12 test, không gọi mạng).

### Phase `decoding` trở thành tín hiệu tất định

- **`audfprint_progress_runner.cai_dat_theo_doi_giai_ma()`**: bọc
  `audio_read.audio_read()` — đúng nơi `audfprint_analyze.wavfile2peaks` gọi FFmpeg —
  để phát event `clip_phase` với `phase=decoding` / `fingerprinting`.
  Trước đây phase `decoding` chỉ được suy ra khi *bắt gặp* tiến trình ffmpeg lúc lấy mẫu
  cây process; clip ngắn thì ffmpeg chỉ sống vài chục mili giây nên giao diện lúc hiện lúc
  không và `pytest -m slow` flaky. Phải cài trong **mỗi tiến trình con** vì Windows dùng
  spawn nên bản vá ở cha không đi theo sang con.
- **`engine._build_database_da_khoa`**: xử lý event `clip_phase`, lọc qua
  `PHASES_FINGERPRINT = {decoding, fingerprinting, probing}` để một dòng stdout hỏng
  không đẩy job sang trạng thái kết thúc giả.

Test mới trong `tests/test_fingerprint_engine_progress.py`: phase `decoding` đến từ event
thật (có tên clip + PID), và `clip_phase` mang pha kết thúc/không hợp lệ thì bị bỏ qua.
`pytest -m slow` chạy **3 lượt liên tiếp, 5 passed mỗi lượt** — hết flaky.

### Ngày đăng video: chốt theo múi giờ người dùng

`upload_date` của yt-dlp là ngày theo lịch **UTC**. Người dùng ở `Asia/Ho_Chi_Minh`
(UTC+7) thấy ngày khác khi video phát hành từ **17:00 UTC** trở đi — đúng 1 ngày,
không bao giờ 2. Đó là lý do chỉ một số video sai.

- **`publication_date.py`** (mới): `PublicationDateResolver` + `PublicationDateResult`
  (date, source_field, raw_value, confidence, warnings) + `format_publication_date()`.
  Ưu tiên `release_timestamp` → `timestamp` → `release_date` → `upload_date` →
  tên file. Trường có thời điểm chính xác luôn thắng trường chỉ có ngày, vì chỉ nó
  mới quy đổi được múi giờ.
- **`engine.youtube_info()`**: chốt ngày chính tắc ngay tại tầng nạp metadata, trả
  thêm `upload_date_raw`, `publication_date_source`, `publication_date_confidence`.
- **`channel.ngay_dang_tu_info()`**: trước đây ưu tiên `upload_date` nên nhánh đọc
  `timestamp` không bao giờ chạy; nay uỷ quyền cho resolver.
- **`channel.sync()`**: ghi thêm `publication_date` + `publication_date_source` vào
  `clips_meta.json`, giữ `upload_date` cho bản đọc cũ.
- **`clip_metadata.source_from_mapping()`**: đọc `publication_date` trước, lùi về
  `upload_date` cho kho cũ (đường bình thường, không phát cảnh báo).
- **`bang_ngang.dinh_dang_ngay()`**: uỷ quyền cho `format_publication_date()` — một
  hàm định dạng duy nhất cho CSV ngang, Sheets và UI.
- **`kiem_ngay_dang.py`** (mới): audit / repair-offline / repair-network, mặc định
  chỉ đọc, có dry-run, backup, ghi nguyên tử, `--limit`.

Kiểm chứng: hai video mẫu qua đúng đường của tool cho `01/08/2026` và `21/06/2025`,
khớp giá trị người dùng đã xác minh. Mẫu 25 clip kho Cory: 22 lệch 1 ngày, 3 đúng,
0 lỗi (dry-run, không ghi). 400 passed, 1 skipped.

### Scan Pipeline V2 — streaming result, Sheets không chặn, workspace riêng

- **`engine.Engine.scan_workspace()`** (mới): mỗi lượt quét có `data/scan_jobs/<uuid>/`
  riêng. Trước đây `_cut_chunks` `rmtree` thư mục CHUNG `data/chunks` ngay đầu hàm và
  `_match_chunks` ghi `data/_ds_khuc.txt` / `data/_raw_match.txt` cố định — hai luồng
  quét đồng thời (GUI + Watch) xoá chunk của nhau. Đây là lỗi ĐÚNG/SAI, không phải chậm.
- **`engine.Engine.scan_iter()`** (mới): generator, yield từng `ScanResult` ngay khi
  xong, kèm `on_video` callback. `scan_many()` giờ là `list(scan_iter(...))` nên mọi
  call site cũ (CLI, Watch, test) giữ nguyên hành vi.
- **`scan_jobs.py`** (mới): `ScanJobController` + `VideoState` + `BatchSnapshot`. Một
  worker thread, snapshot bất biến cho UI, ETA theo trung bình trượt, tách hẳn trạng
  thái QUÉT khỏi trạng thái GIAO SHEETS.
- **`sheet_delivery.py`** (mới): `SheetDeliveryWorker` chạy thread riêng. Scan worker
  chỉ `enqueue()` rồi đi tiếp. Retry phân loại (429/5xx/timeout thử lại;
  PERMISSION_DENIED/404 dừng ngay), backoff mũ, khoá idempotency SHA-256 chống ghi trùng.
- **`app.py`**: màn hình quét mới — batch progress, Hoàn tất/Lỗi/Đã chạy/ETA, video
  hiện tại kèm công đoạn, bảng từng video (Quét · Đoạn · Sheets), tóm tắt Sheets.

Đo được (10 video, quét 0,3 s/video, Sheets 1,5 s/lần): người dùng thấy kết quả sau
**3,00 s** thay vì **18,01 s** — sớm hơn 83 %.

### Dùng lại kết nối Google Sheets

`sheets.append()` trước đây mỗi lần gọi đều `service_account()` → `open_by_key()` →
`worksheet()` → `get_all_values()`. Riêng `get_all_values()` **tải toàn bộ bảng** chỉ
để hỏi «bảng có trống không», nên chi phí tăng theo số dòng đã tích luỹ. Với
incremental delivery, số lần append tăng từ 1/batch lên 1/video nên điểm này thành nút thắt.

- Cache kết nối ở **cấp module** (không phải cấp instance) vì `app.py` tạo
  `SheetsExporter` mới mỗi lần đẩy; khoá cache gồm mtime của `google_key.json` nên
  thay khoá là tự xác thực lại.
- Kiểm tra header bằng cách đọc **ô A1** thay vì tải cả bảng, và chỉ đọc **một lần**
  cho cả phiên.
- Lỗi khi ghi thì bỏ cache để lần sau kết nối lại, nhưng **không tự thử lại append** —
  lượt ghi có thể đã tới Google, thử lại tại đây sẽ tạo dòng trùng. Việc thử lại là
  của `SheetDeliveryWorker`.
- `kiem_tra()` vẫn mở kết nối mới để «Kiểm tra kết nối» thật sự chạm tới Google.

Đo được (10 video, bảng đã có 2000 dòng, 0,25 s/lượt API):

| | Lượt gọi API | Thời gian |
| --- | ---: | ---: |
| Trước | 50 | 22,54 s |
| Sau | **14** | **3,50 s** |

Test mới: `tests/test_scan_streaming.py` (12), `tests/test_sheet_delivery.py` (14),
`tests/test_sheets_session.py` (15), `tests/test_app_scan_progress.py` (1).

### Sửa ranh giới thread và schema bảng trạng thái

Hai lỗi do chính vòng Scan Pipeline V2 gây ra, lộ ra khi chạy thật.

**`missing ScriptRunContext` + `KeyError: sheet_link`.** `sheet_link` **không** thiếu
khởi tạo (`cau_hinh.py:17` + `app.py:44-47` đã tạo sẵn). Root cause là thread nền
không có `ScriptRunContext`, nên `st.session_state` đọc từ đó trả về proxy **rỗng** —
key có ở main thread vẫn báo thiếu. Hai chỗ vi phạm, đều là code vòng trước:
`chay_quet.sau_moi_video` → `lay_sheets()`, và `sender` của `SheetDeliveryWorker`.

- `scan_jobs.ScanLaunchConfig` (mới): ảnh chụp bất biến `auto_sheet`/`sheet_link`/
  `dang_ngang`, chụp trên main thread lúc bấm Bắt đầu quét. Kèm lợi ích nghiệp vụ:
  đổi link Sheet giữa batch không làm batch đang chạy bắn sang bảng khác.
- `app.tao_sheets_exporter(sheet_link)` (mới): hàm thuần. `lay_sheets()` giữ lại
  nhưng chỉ là bản tiện dụng cho main thread.
- `SheetDelivery.sheet_link` (mới) và `sender(sheet_link, header, rows)`: công việc tự
  mang đích đến nên thread giao hàng không phải hỏi lại UI.

**`ArrowInvalid` lặp mỗi lần render.** Bảng trạng thái dựng bằng
`"—" if v.matches is None else v.matches` → cột `object` trộn `int`/`str`; PyArrow ném
exception rồi Streamlit mới sửa dtype — mỗi lần vẽ lại một exception, suốt lượt quét.
Gốc rễ là **bảng UI không có schema**.

- `scan_ui.py` (mới): `build_scan_status_dataframe()` khai báo dtype tường minh cho
  cả năm cột (kể cả khung rỗng), tách khỏi `app.py` nên test được bằng
  `pa.Table.from_pandas` mà không cần chạy Streamlit.
- Cột `Đoạn` là `string`: cần phân biệt ba trạng thái — chưa quét (`—`), quét xong 0
  đoạn (`0`), quét xong N đoạn. `Int64` + `pd.NA` sẽ hiển thị "chưa quét" thành ô
  trống, khó phân biệt với 0.

Đã đối chứng: cách cũ `dtype=object` → `ArrowInvalid`; cách mới `dtype=string` →
chuyển Arrow thành công, giá trị `['3', '0', '—']`.

Test mới: `tests/test_scan_ui_schema.py` (9), `tests/test_scan_thread_boundary.py` (10),
`tests/test_app_scan_no_warnings.py` (1). Có guard cấu trúc dùng `tokenize` để chặn
`scan_jobs.py`/`sheet_delivery.py`/`scan_ui.py` chạm Streamlit — và một test tự kiểm
tra guard đó thật sự bắt được vi phạm.
