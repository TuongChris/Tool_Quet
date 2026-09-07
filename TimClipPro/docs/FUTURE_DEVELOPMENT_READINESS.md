# FUTURE DEVELOPMENT READINESS — Đánh giá trước khi làm tính năng tiếp theo

> **KHÔNG CÓ GÌ TRONG TÀI LIỆU NÀY ĐÃ ĐƯỢC TRIỂN KHAI.**
> Đây là một bản **đánh giá** (assessment), không phải nhật ký thay đổi. Không một dòng
> code nào được sửa, không một `WORK_ID` nào được cấp phát, không một cột nào được thêm
> vào cơ sở dữ liệu. Mọi câu "nên làm", "cần thêm", "fix direction" đều là **đề xuất chưa
> thực hiện**.
>
> Mục đích: trả lời câu hỏi *"cái gì phải đúng TRƯỚC khi bắt đầu hai tính năng tiếp theo
> (Works Registry và vận hành nhiều khách hàng)?"* — bằng bằng chứng `file:line`, không
> bằng cảm tính.

**Cách đọc tài liệu này.** Mọi khẳng định đều kèm `file:line` đã được mở và đọc trong vòng
audit này. Ở những chỗ tài liệu `docs/` cũ mâu thuẫn với source, **source thắng** và mâu
thuẫn được nêu rõ. Ba mức độ tin cậy được tách bạch và **không bao giờ trộn lẫn**:

| Nhãn | Nghĩa |
|---|---|
| **CONFIRMED** | Đã đọc trực tiếp trong source, hoặc đã tái hiện được. |
| **LIKELY** | Cơ chế đã đọc trong source, nhưng điều kiện kích hoạt chưa tái hiện được. |
| **HYPOTHESIS** | Suy luận hợp lý, **chưa** kiểm chứng. Không được xem là sự thật. |

**Phạm vi không kiểm chứng được ở vòng này (gap).** Thư mục `data/` nằm ngoài phạm vi
(một job dựng vân tay đang chạy), nên **giá trị cấu hình sống chưa đọc được**:
`data/cau_hinh.json` (`top_n`, `luoi_resample`, `ncores`, `keep_downloads`),
`data/khos.json` (số kho thật), `data/lichsu.db` (số dòng thật). Ở đâu một kết luận phụ
thuộc vào các giá trị đó, tài liệu này nói rõ.

---

## Mục lục

1. [Multi-client readiness scorecard](#1-multi-client-readiness-scorecard)
2. [Global & singleton audit](#2-global--singleton-audit)
3. [Extension points](#3-extension-points)
4. [Cross-contamination risks](#4-cross-contamination-risks)
5. [Works Registry readiness](#5-works-registry-readiness)
6. [Stable identity analysis cho WORK_ID](#6-stable-identity-analysis-cho-work_id)
7. [Dangerous change areas](#7-dangerous-change-areas)
8. [Prerequisites](#8-prerequisites)

---

## 0. Một sự thật cấu trúc, nêu trước

`grep -rniE "tenant|workspace_id|client_id|khach_hang|copyright|owner|ban_quyen|rights_holder"`
trên toàn bộ `*.py` của dự án (trừ `.venv/`, `audfprint-master/`) trả về **đúng hai kết
quả dương tính giả**: chuỗi `ownEr` bên trong `"UnknownError"` tại `engine.py:1545` và
`engine.py:1554`, cộng phần license text của thư viện vendored trong
`audfprint-master/audio_read.py`. (CONFIRMED)

Nghĩa là: **khái niệm "khách hàng" không tồn tại ở bất kỳ tầng nào** — không trong code,
không trong schema, không trong báo cáo, không trong UI. Thứ gần nhất đóng vai trò đó là
**kho vân tay** (`kho`), một entry trong `data/khos.json` gồm `{ten, thu_muc, db}`
(`engine.py:824-825`). Toàn bộ phần còn lại của tài liệu này lấy giả định *"một kho = một
khách hàng"* làm mô hình phân vùng duy nhất mà codebase hiện đã hiểu được.

---

## 1. Multi-client readiness scorecard

Thang đánh giá: **READY** = dùng được ngay cho nhiều khách hàng, không cần sửa.
**NEEDS REFACTOR** = phân vùng được, nhưng phải sửa call site hoặc schema.
**BLOCKED** = không thể phân vùng nếu không đổi schema/thiết kế, và việc đổi đó không
đảo ngược được nếu làm sai.

| # | Khu vực | Verdict | Đã đúng sẵn | Cái chặn |
|---|---|---|---|---|
| 1 | **Google credentials** | NEEDS REFACTOR | `SheetsExporter.__init__(self, key_path=None, sheet="", worksheet="KetQuaQuet")` đã nhận `key_path` làm tham số (`sheets.py:94-99`). Chỉ `client_email` được nạp vào Python (`sheets.py:130-134`); private key giao cho gspread theo đường dẫn (`sheets.py:150`). | **Không một call site production nào truyền `key_path`.** Đã kiểm bằng grep toàn tree: `watch.py:398`, `danh_sach_video.py:626`, `kiem_sheet.py:60`, `app.py:224`, `app.py:636`, `app.py:1333` — tất cả chỉ truyền `sheet=`. Nên mọi khách hàng đều rơi về `<dir(sheets.py)>/google_key.json` (`sheets.py:96-97`), không có env override. Một service account phải có quyền Editor trên **mọi** spreadsheet khách hàng; thu hồi là all-or-nothing. (CONFIRMED) |
| 2 | **Spreadsheet / worksheet** | NEEDS REFACTOR | `sheet_link` đã đi theo từng job end-to-end: `ScanLaunchConfig.sheet_link` (`scan_jobs.py:65-83`) → `SheetDelivery.sheet_link` → `sender(sheet_link, header, rows)` (`app.py:84-85`). `danh_sach_video.ten_trang_tinh` (`danh_sach_video.py:517`) đã sinh tên tab **theo từng kho** — tiền lệ đang chạy tốt. | `sheet_link` là **một scalar duy nhất** (`cau_hinh.py:17`), **không hề ràng buộc với kho đang chọn**. Worksheet kết quả quét là hằng `"KetQuaQuet"` cho **cả hai** schema báo cáo (`sheets.py:95`). (CONFIRMED) |
| 3 | **Kho vân tay (lưu trữ)** | READY | Phân vùng thật sự: `khos.json` là danh sách `{ten, thu_muc, db}`; file là `kho_<slug(ten)>.pklz` với hậu tố md5 chống trùng (`engine.py:729-732`, `engine.py:824-825`); `_duong_dan_db_kho` chặn traversal, chỉ nhận basename `.pklz` nằm trong `data_dir` (`engine.py:743-765`). | — |
| 3b | **Kho vân tay (ràng buộc runtime)** | NEEDS REFACTOR | — | Đúng **một** kho được bind tại một thời điểm, qua `khos.json["dang_dung"]` → `_ap_dung_kho` (`engine.py:784`, `engine.py:789-799`). `use_kho` **ghi xuống đĩa** con trỏ đó (`engine.py:832-838`). Một `Engine` không phục vụ được hai kho đồng thời. (CONFIRMED) |
| 4 | **Clip metadata store** | NEEDS REFACTOR | Nguồn đã scope theo kho active: snapshot `data/metadata/kho_<slug>.json` priority 0 và `<kho_thu_muc>/clips_meta.json` priority 10 (`engine.py:1121-1124`); resolver cache theo full file signature (`engine.py:1141-1161`). | Nguồn `legacy_data` đọc `data/clips_meta.json` **dùng chung** ở priority 100 khi tên kho là `""` hoặc `"Kho mặc định"` (`engine.py:1137-1138`). Nghiêm trọng hơn: snapshot ở priority 0 **che** mọi chỉnh sửa ghi vào `clips_meta.json` (AUD-061/AUD-081 — cùng một defect, nộp hai lần). Đổi tên kho làm mồ côi snapshot (xem W1). (CONFIRMED) |
| 5 | **Lịch sử quét (`data/lichsu.db`)** | **BLOCKED** | Một transaction cho mỗi video, nên độ bền per-video vẫn đúng (`engine.py:3273-3288`). | Bảng `jobs` là `id, created_at, source_type, source_name, source_ref, duration_s, status, n_matches, note, source_id` — **không có cột kho, không có cột khách hàng** (`engine.py:874-878`). `ids_da_quet()` là `SELECT DISTINCT source_id FROM jobs WHERE source_id IS NOT NULL AND source_id != '' AND status = 'ok'`, **không có predicate phân vùng** (`engine.py:3295-3304`). Dòng cũ không mang attribution nên **không back-fill được**, và tập dedupe này là load-bearing cho `watch` (xem §4 hạng 1). (CONFIRMED) |
| 6 | **Config** | NEEDS REFACTOR | `doc_cau_hinh(data_dir)` / `ghi_cau_hinh(data_dir, du_lieu)` đã tham số hoá theo thư mục (`cau_hinh.py:29`, `cau_hinh.py:39`), `CauHinhMang.tu_file_cau_hinh(data_dir)` cũng vậy (`ytdlp_chung.py:286`). | Một file `data/cau_hinh.json` phẳng chứa **mọi** trường `Config` (`cau_hinh.py:70-72`, không có allowlist) cộng năm khoá UI (`cau_hinh.py:16-22`). Ngưỡng khớp, đường dẫn cookie và `sheet_link` đều toàn cục. `ap_vao_config` so kiểu cứng `type(gia_tri) is not type(gia_tri_hien_tai)` (`cau_hinh.py:63`), nên một section lồng theo khách hàng bị **bỏ qua âm thầm** (xem W4). (CONFIRMED) |
| 7 | **Runtime / thư mục tạm** | READY | `scan_workspace` cấp cho mỗi lượt quét một `data/scan_jobs/<uuid4().hex>` và `rmtree` trong `finally` (`engine.py:2229-2233`); build vân tay có `data/fingerprint_jobs/<job_id>` (`engine.py:1818-1819`). | Chỉ là lưu ý, không phải blocker: `data/downloads` khoá theo `video_id` đơn thuần dưới một ngân sách chung (`engine.py:2070`, `engine.py:2093`); nhánh `data/chunks` cũ đã chết vẫn còn (`engine.py:637`, `engine.py:3139` — AUD-006). |
| 8 | **Exports (`ketqua/`)** | NEEDS REFACTOR | `out_dir` là tham số constructor (`engine.py:638`), và GUI override được bằng env (`app.py:44`). | Một thư mục, tên file không mang danh tính khách hàng: `ketqua_<ts>.csv`, `ketqua_ngang_<ts>.csv`, `hoso_<video vi phạm>_<ts>.md`. `cli.py:182` dựng `Engine()` trần nên **CLI không redirect được** (AUD-004/AUD-185). (CONFIRMED) |
| 9 | **Watchlist** | READY | Đã sẵn sàng cho nhiều khách hàng: `--file` chọn file (`cli.py:51`), `WatchList.kho` đặt tên kho (`watch.py:26-29`). `chia_watchlist.py` tách một list ra nhiều máy. | Không phải blocker mà là tác dụng phụ: `watch` gọi `engine.use_kho(wl.kho)` (`watch.py:370-372`), mà `use_kho` **ghi xuống đĩa** (`engine.py:836-837`) — xem §4 hạng 4. |
| 10 | **Logs** | NEEDS REFACTOR | `mo_nhat_ky(thu_muc, …)` (`nhat_ky.py:122`) và `tao_fingerprint_logger(log_dir)` (`fingerprint_progress.py:48`) đều nhận thư mục và đi theo `out_dir`. | Tee thay **`sys.stdout` / `sys.stderr` cấp process** (`nhat_ky.py:79-81`, `nhat_ky.py:150-153`), nên chỉ một khách hàng sở hữu được log của process. `scan.job`, `scan.sheet`, `publication_date` **không có handler nào** (AUD-143/AUD-166), nên sự kiện của chúng không tới log của bất kỳ khách hàng nào. (CONFIRMED) |
| 11 | **`data/tool.lock`** | NEEDS REFACTOR | Đường dẫn dẫn xuất từ `data_dir` (`engine.py:1437`, `1496`, `1691`; `watch.py:288`) nên **một `data_dir` riêng cho mỗi khách hàng là tự động phân vùng được khoá**. Là khoá OS thật, kernel tự nhả khi process chết. | Với một `data_dir` chung nó là bộ tuần tự hoá toàn cục, và **non-blocking**: build vân tay nhiều giờ của khách A khiến sweep theo lịch của khách B **thất bại ngay** với `DangChayRoi` → `watch.py:300-301` → `cli.py` exit 1. Nó cũng **không reentrant**, nên không thể bọc đơn giản quanh đường quét — mà đường quét hiện **không** lấy khoá nào, mâu thuẫn với `CLAUDE.md:78-80` (AUD-125/AUD-261). (CONFIRMED) |

**Tổng kết: 1 BLOCKED, 8 NEEDS REFACTOR, 2 READY.**

**Câu hỏi quyết định chưa có lời đáp (gap).** Mô hình dự kiến là *một cài đặt phục vụ
nhiều khách hàng* hay *một cài đặt cho mỗi khách hàng*? Mọi verdict ở trên đổi theo câu
trả lời: mô hình **một-cài-đặt-mỗi-khách-hàng** phần lớn là READY qua con đường ở §3
Tier 3, chỉ còn lại các mục 1, 6 (cookie/identity) và 11 (tranh chấp lock đã tự hết).
Đây là ẩn số **load-bearing nhất** của toàn bộ tài liệu này.

---

## 2. Global & singleton audit

### 2.1 Module-level mutable state — danh sách đầy đủ

Quét bằng `grep -nE '^_?[A-Za-z_]+ *[:=].*(\{\}|\[\]|RLock\(|Lock\(|os\.environ)'` trên
toàn bộ `*.py` không phải test/vendored. (CONFIRMED)

| # | Ký hiệu | file:line | Chứa gì | Hệ quả multi-client |
|---|---|---|---|---|
| G1 | `_CACHE: dict[tuple, _KetNoi] = {}` | `sheets.py:44` | Handle worksheet gspread đang sống, khoá `(normcase(abspath(key_path)), key mtime_ns, sheet_id, worksheet)` (`sheets.py:139-145`) | Khoá **có** `sheet_id`, nên A và B trên hai sheet khác nhau **không** lẫn nhau. Nhưng **không có eviction**: `xoa_cache_ket_noi()` (`sheets.py:47-50`) không có call site production nào. Mỗi khách hàng để lại một phiên xác thực sống suốt đời process. |
| G2 | `_KHOA = threading.RLock()` | `sheets.py:43` | Bảo vệ G1 | Giữ **xuyên qua network call**: `_mo_worksheet()` chạy bên trong `with _KHOA` (`sheets.py:157-173`). Lần mở đầu chậm của khách A chặn cả tra cache của khách B. |
| G3 | `_KHOA_THEO_DUONG_DAN: dict[str, threading.RLock] = {}` | `luu_tru.py:59` | Khoá ghi theo abspath cho JSON store | Theo path nên file của mỗi khách tự phân vùng. Không bao giờ được dọn. **Chỉ trong process** — không có bảo vệ liên tiến trình (AUD-161). |
| G4 | `_KHOA_DANH_SACH = threading.Lock()` | `luu_tru.py:60` | Bảo vệ G3 | Không vấn đề. |
| G5 | `_CACHE_COOKIE: dict = {}` | `ytdlp_chung.py:189` | Kết quả kiểm định file cookie, khoá `(path, mtime, size)` | Khoá theo path, nhưng chỉ có **một** đường dẫn cookie duy nhất (xem G8) nên thực tế chứa một entry. |
| G6 | `MUI_GIO_MAC_DINH = os.environ.get("TIMCLIP_MUI_GIO", "Asia/Ho_Chi_Minh")` và `_MAC_DINH = PublicationDateResolver()` | `publication_date.py:56`, `publication_date.py:238` | Múi giờ hiển thị toàn process, bind lúc **import** | Một múi giờ cho mọi khách hàng; `resolve_publication_date` dùng `_MAC_DINH` nên không override được per-call trong production. |
| G7 | `Config.ytdlp_cookiefile` / `Config.ytdlp_cookies_browser` | `engine.py:150-151` | Một danh tính YouTube | Mọi lượt tải của mọi khách hàng chạy dưới một tài khoản Google. |
| G8 | `_STDOUT_GOC` / `_STDERR_GOC` / `_FILE_LOG` | `nhat_ky.py:79-81`, gán tại `nhat_ky.py:150-153` | Thay thế `sys.stdout` / `sys.stderr` cấp process | Khách hàng nào chạy `watch --log` sau cùng thì sở hữu stdout/stderr của process. |
| G9 | `_DA_CAI_THEO_DOI_GIAI_MA = False` | `audfprint_progress_runner.py:96` | Cờ idempotent cài monkey-patch | Chỉ sống trong process con audfprint. Không ảnh hưởng. |
| G10 | `_TRUONG_HONG: dict[str, tuple[str, str]]` | `danh_sach_video.py:83` | Bảng tra thông điệp lỗi (đọc-only sau khi định nghĩa) | Không ảnh hưởng. |

**Không có `st.cache_data` / `st.cache_resource` ở bất kỳ đâu** — `grep -rn "st\.cache"
*.py` trả về **0 kết quả**. Toàn bộ state Streamlit là per-browser-session trong
`st.session_state` (`app.py:41-92`). Đây là tin tốt thật sự: **không có chia sẻ cấp
Streamlit nào phải gỡ.** (CONFIRMED)

### 2.2 Instance Engine / Config cấp module

**Không có.** Mọi `Engine` đều dựng tường minh: (CONFIRMED)

| Nơi dựng | file:line | Phạm vi |
|---|---|---|
| Streamlit | `app.py:42-45` — `Engine(data_dir=os.environ.get("TIMCLIP_DATA_DIR") or None, out_dir=os.environ.get("TIMCLIP_OUTPUT_DIR") or None)` | Một Engine mỗi browser session, giữ ở `st.session_state.eng` (`app.py:57`) |
| CLI | `cli.py:182` — `eng = Engine()` | Một Engine mỗi process; **bỏ qua cả hai env var** |
| Script guard | `kiem_ngang.py:62` — `e = Engine()` ở top level | Chạy ngay khi import (AUD-209) |
| Audit CLI | `kiem_metadata_kho.py:62-76` — cố ý `object.__new__(Engine)` để tránh side effect của `__init__` | Read-only |

`Config` là dataclass thuần dựng theo mỗi Engine (`engine.py:618`), và bị **sửa trực tiếp
lúc đang chạy** bởi sidebar ở mỗi lần Streamlit vẽ lại (`app.py:503-565`) —
xem AUD-122 và §4 hạng 4.

### 2.3 Cached resources (tất cả đều per-Engine)

| Trường | file:line | Khoá invalidate |
|---|---|---|
| `_cache_khoa` / `_cache_clips` (danh sách clip trong kho) | khai báo `engine.py:651-652`, ghi `engine.py:1054` | `(path, mtime_ns, size)`; xoá bởi `_ap_dung_kho` (`engine.py:798`) |
| `_metadata_cache_key` / `_metadata_resolver_cache` | khai báo `engine.py:653-654`, dùng `engine.py:1163-1173` | Signature trên DB + mọi metadata source + `.bak` của chúng (`engine.py:1141-1161`) |
| `canh_bao_metadata` | `engine.py:655`, ghi `engine.py:1221` | Xoá bởi `_invalidate_metadata_cache` (`engine.py:801-805`) |
| `nho_client` (`NhoClientTotNhat`) | `engine.py:627` | TTL 30 phút; có thêm một bản sao per-`ChannelSync` (`channel.py:174`) |
| `chan_doan_quet` | `engine.py:628`, reset mỗi lượt quét tại `engine.py:3059` | Per scan |
| `cancel_event` | `engine.py:650` | **Dùng chung cho cả build lẫn scan** (AUD-051) |

Tất cả đều per-Engine → **một Engine cho mỗi khách hàng là tự động phân vùng xong.**

### 2.4 Đường dẫn cứng, một-và-chỉ-một

| # | Đường dẫn | file:line | Tham số hoá được không? |
|---|---|---|---|
| P1 | `<root>/data` | `engine.py:632` — `self.data_dir = os.path.abspath(data_dir or os.path.join(self.root, "data"))` | **Được**, qua ctor arg `data_dir=`. Lưu ý: **không** đọc `TIMCLIP_DATA_DIR`, khác với helper `thu_muc_data_mac_dinh` ở `engine.py:608` (AUD-004/AUD-185) |
| P2 | `<root>/ketqua` | `engine.py:638` | **Được**, ctor arg `out_dir=` |
| P3 | `<data_dir>/db.pklz` (legacy default) | `engine.py:633`, lặp lại tại `engine.py:794-795` | Dẫn xuất |
| P4 | `<data_dir>/downloads` | `engine.py:636` | Dẫn xuất |
| P5 | `<data_dir>/chunks` (legacy, chết) | `engine.py:637`; `rmtree` tại `engine.py:3139` | Dẫn xuất (AUD-006) |
| P6 | `<data_dir>/lichsu.db` | `engine.py:639` | Dẫn xuất |
| P7 | `<data_dir>/khos.json` — **registry kho duy nhất** | `engine.py:648` | Dẫn xuất |
| P8 | `<data_dir>/metadata/kho_<slug>.json` | `engine.py:1080-1094` | Dẫn xuất; slug từ **tên kho** |
| P9 | `<data_dir>/tool.lock` | `engine.py:1437`, `1496`, `1691`; `watch.py:288` | Dẫn xuất |
| P10 | `<data_dir>/scan_jobs/<uuid4>` | `engine.py:2229` | Per-job (đúng) |
| P11 | `<data_dir>/fingerprint_jobs/<job_id>` | `engine.py:1818-1819` | Per-job (đúng) |
| P12 | `<data_dir>/chan_doan/*.json`, giữ **200 file mới nhất, toàn cục** | `engine.py:2671`, `engine.py:2696-2699` | Dẫn xuất; trần 200 **không** theo từng kho |
| P13 | `<root>/bin` prepend vào `PATH` của **process** | `engine.py:631`, `engine.py:645-646` | Không bao giờ khôi phục (AUD-247) |
| P14 | **`<dir(sheets.py)>/google_key.json`** | `sheets.py:27`, `sheets.py:96-97` | Ctor arg `key_path=` **có tồn tại** nhưng **không call site production nào truyền** (đã kiểm bằng grep) |
| P15 | Một spreadsheet, một worksheet `"KetQuaQuet"` | `sheets.py:95` (default); `sheet_link` khai báo tại `cau_hinh.py:17` | Arg `worksheet=` có; chỉ `danh_sach_video.py:626` dùng |
| P16 | `watchlist.json` trong CWD | `cli.py:51` — `a.file or "watchlist.json"` | **Được**, `--file` |
| P17 | `<script dir>/data/DUNG`, bỏ qua `data_dir` | `cli.py:41-46` so với `cli.py:55` (`os.path.join(eng.data_dir, "DUNG")`) | **Không** — bẫy tiềm ẩn, xem W5 |
| P18 | `ketqua/giamsat_<date>.log` | `nhat_ky.py:131-133`, mở từ `cli.py:233` | Đi theo `out_dir` |
| P19 | `ketqua/fingerprint.log` | `fingerprint_progress.py:69` | Đi theo `out_dir` |
| P20 | Streamlit port 8501, mọi interface | `ChayTool.bat:46` | Một UI process mỗi máy như đang ship (AUD-222) |

---

## 3. Extension points

Xếp theo đòn bẩy. Mọi chữ ký đều trích nguyên văn từ source.

### 3.1 Tier 1 — tham số ĐÃ CÓ SẴN, chỉ là không ai truyền

| Ký hiệu | file:line | Chữ ký hiện tại | Ghi chú |
|---|---|---|---|
| `Engine.__init__` | `engine.py:615-616` | `def __init__(self, root=None, config=None, data_dir=None, out_dir=None)` | **Điểm mở rộng có đòn bẩy cao nhất, cách biệt rất xa.** Một Engine mỗi khách hàng với `data_dir=<clients>/<id>/data`, `out_dir=<clients>/<id>/ketqua` phân vùng ngay lập tức P1–P12 và P18–P19: registry, DB lịch sử, config, `tool.lock`, downloads, workspace, chẩn đoán, exports và cả hai log. `app.py:42-45` đã làm đúng như vậy từ env var. |
| `SheetsExporter.__init__` | `sheets.py:94-99` | `def __init__(self, key_path=None, sheet="", worksheet="KetQuaQuet")` | Cả ba trục đã là tham số. Sáu call site production chỉ truyền `sheet=`. Credential riêng và tab riêng cho mỗi khách hàng là **thay đổi call site, không phải thay đổi thiết kế**. |
| `danh_sach_video.day_len_sheet` | `danh_sach_video.py:598-603` | `def day_len_sheet(ket_qua, sheet_link, *, tao_exporter=None)` | `tao_exporter: Callable[[str, str], Any]` là điểm inject tường minh (default tại `danh_sach_video.py:626`). |
| `SheetDeliveryWorker.__init__` | `sheet_delivery.py:121-131` | `def __init__(self, sender: Callable[[str, list, list], int], max_attempts=4, base_delay=2.0, queue_maxsize=256, sleep_fn=time.sleep)` | `sender(sheet_link, header, rows)` **đã mang đích đến theo từng job**, nên một worker đã fan-out được tới N spreadsheet khách hàng. |
| `bang_ngang.dung_dong_ngang` / `dossier.dung_ho_so` | `bang_ngang.py:69-74`, `dossier.py:41-46` | `(kq, clips_meta=None, *, resolver: ClipMetadataResolver \| None = None)` | Resolver inject được, nên metadata riêng theo khách hàng **không cần đụng tới exporter**. |
| `cau_hinh.doc_cau_hinh` / `ghi_cau_hinh` | `cau_hinh.py:29`, `cau_hinh.py:39` | `(data_dir: str)` / `(data_dir: str, du_lieu: dict)` | Đã phân vùng theo thư mục. |
| `ytdlp_chung.CauHinhMang.tu_file_cau_hinh` | `ytdlp_chung.py:286` | `(cls, data_dir: str)` | Đã phân vùng theo thư mục. |
| `nhat_ky.mo_nhat_ky`, `fingerprint_progress.tao_fingerprint_logger`, `don_dep.don_kho_dem`, `don_dep.don_job_quet` | `nhat_ky.py:122`, `fingerprint_progress.py:48`, `don_dep.py:60`, `don_dep.py:162` | tất cả đều nhận một thư mục | Đã phân vùng theo thư mục. |

### 3.2 Tier 2 — phải thêm tham số/trường mới, nhưng hình dạng đã rõ

| Ký hiệu | file:line | Chữ ký hiện tại | Cần thêm gì |
|---|---|---|---|
| `ScanLaunchConfig` | `scan_jobs.py:65-83` | frozen dataclass: `auto_sheet: bool`, `sheet_link: str`, `dang_ngang: bool` | `client_id` / `kho`. Dataclass này **sinh ra chính xác để** mang state của main thread qua ranh giới worker thread — đúng chỗ để đặt client id. |
| `khoa_giao_hang` | `sheet_delivery.py:69-89` | `(sheet_id, worksheet, dang_bao_cao, scan_job_id, source_id, rows)` | Đã hash `sheet_id`; thêm client id để hai khách hàng không bao giờ đụng nhau ở idempotency key. Lưu ý `app.py:125` hiện truyền `""` cho `worksheet`. |
| `Engine.save_job` | `engine.py:3273` | `(self, kq: ScanResult, source_type: str) -> int` | Ghi kho/khách hàng vào một cột `jobs` mới. |
| `Engine.ids_da_quet` | `engine.py:3295` | `(self, chi_thanh_cong: bool = True) -> set` | **Bắt buộc** phải có filter theo kho/khách hàng — xem §4 hạng 1. |
| `Engine.list_jobs` | `engine.py:3290` | `(self, limit: int = 200) -> list` | Tương tự, cộng thêm tab Lịch sử tại `app.py:1471`. |
| `Engine._metadata_source_candidates` | `engine.py:1109` | `(self, clips: list[dict]) -> list[tuple[str, str, int]]` | Nơi **duy nhất** quyết định thứ tự ưu tiên nguồn; override theo khách hàng thuộc về đây. |
| `Engine.scan_iter` | `engine.py:3224-3230` | `(self, nguon, source_type="youtube", progress=None, on_video=None)` | **Không cần sửa** nếu Engine đã là per-client; cần thêm tham số nếu giữ một Engine chung. |
| `watch.chay_giam_sat` | `watch.py:270-278` | `(engine, wl, progress=None, lister=None, sheet_link="", dang_ngang=True, dung_lai=None)` | `sheet_link` đã theo từng lượt chạy; mảnh còn thiếu là `wl.kho` làm mutate shared state (§4 hạng 4). |
| `ChannelSync.__init__` | `channel.py:139-142` | `(self, dest, network_timeout_s=None, player_clients=None, cau_hinh_mang=None)` | Đã per-warehouse qua `dest`, và `cau_hinh_mang` đã mang cookie — nên **danh tính YouTube riêng cho mỗi khách hàng chỉ cần một `CauHinhMang` riêng**. |
| `Engine.build_database` / `khoi_phuc_metadata_offline` / `va_metadata_thieu` | `engine.py:1669`, `engine.py:1428`, `engine.py:1461` | đều thao tác ngầm trên `self.kho_dang_dung` | Nhận kho tường minh. |

### 3.3 Tier 3 — con đường khả thi gần nhất

**Một OS process cho mỗi khách hàng, chỉ khác nhau ở `TIMCLIP_DATA_DIR` /
`TIMCLIP_OUTPUT_DIR`.** Dùng đúng seam Tier 1 số 1, **không cần đổi schema**. Ba thứ phải
sửa trước:

1. `cli.py:182` dựng `Engine()` trần — **CLI bỏ qua cả hai env var** (AUD-185), nên một
   `watch` per-client sẽ âm thầm ghi vào `<repo>/data` dùng chung. (CONFIRMED)
2. `cli.py:41-46` `_file_dung_mac_dinh()` hardcode `<script dir>/data/DUNG` trong khi
   watcher đọc `os.path.join(eng.data_dir, "DUNG")` (`cli.py:55`) — `cli.py dung` sẽ dừng
   nhầm khách hàng. (CONFIRMED)
3. `sheets.py:96-97` resolve `google_key.json` từ thư mục **module**, không phải
   `data_dir`, nên các process riêng biệt vẫn dùng chung một service account. (CONFIRMED)

`ChayTool.bat:46` cũng hardcode `--server.port=8501`, nên launcher như đang ship chỉ hỗ
trợ đúng một UI process mỗi máy.

### 3.4 Cảnh báo: chỗ nào một thay đổi ngây thơ phá vỡ dữ liệu trên đĩa

Mỗi mục dưới đây đã kiểm chứng trong source.

**W1 — Đổi tên kho để thêm tiền tố khách hàng là mất dữ liệu âm thầm ở BA nơi cùng lúc.**
(CONFIRMED)
Ba artefact độc lập dẫn xuất từ **tên** kho qua `_slug` (`engine.py:729-732`):

- File vân tay `kho_<slug>.pklz` (`engine.py:824-825`) — đổi tên ⇒ `_duong_dan_db_kho`
  trỏ tới path không còn tồn tại ⇒ `list_khos` báo `co_van_tay: False`
  (`engine.py:812-813`) và lượt quét chạy trên hư không.
- Snapshot metadata `data/metadata/kho_<slug>.json` (`engine.py:1080-1086`) — đổi tên ⇒
  snapshot mồ côi ⇒ mọi clip mất tiêu đề YouTube và URL trong hồ sơ khiếu nại, rơi về
  tên file.
- Tab Google Sheets `DanhSachVideo_<name>` (`danh_sach_video.py:517-561`) — đổi tên ⇒
  xuất hiện tab mới, tab cũ để lại lỗi thời.

`update_kho` (`engine.py:840-846`) **chỉ** đổi `thu_muc`; **không có thao tác rename nào
trong toàn bộ codebase**. Vậy nên tiền tố khách hàng phải được đưa vào bằng một entry
registry **mới**, tuyệt đối không bằng cách sửa `ten`.

**W2 — Tách `data/lichsu.db` theo khách hàng làm mọi video đã quét trông như chưa quét.**
(CONFIRMED)
`ids_da_quet` trả về một `set` phẳng các `source_id` (`engine.py:3295-3304`), mà
`watch.loc_can_quet` (`watch.py:190-201`, gọi tại `watch.py:378-379`) dùng để bỏ qua công
việc. Di chuyển hay phân vùng DB ⇒ sweep kế tiếp tải lại và quét lại toàn bộ backlog.
Dòng cũ không mang attribution (`engine.py:874-878`) nên **không gán được cho khách hàng
sau khi đã ghi**.

**W3 — Tái cấu trúc `khos.json` ném exception ngay trong `Engine.__init__`.** (CONFIRMED)
`_init_kho` index `d["danh_sach"]` không guard (`engine.py:779`) và `_ap_dung_kho` index
`kho["ten"]` / `kho["db"]` không guard (`engine.py:791-796`); chỉ `LoiDuLieu` được bắt
(`engine.py:771`, `engine.py:785`). Lồng kho dưới khách hàng ⇒ GUI chết lúc import
(`app.py:42`) và mọi lệnh CLI dựng Engine cũng chết (AUD-047/AUD-163). **Thêm khoá phụ
vào từng entry thì AN TOÀN** — chúng sống sót qua `{**k, ...}` tại `engine.py:813` và được
`_ghi_khos` ghi lại nguyên vẹn (`engine.py:740-741`).

**W4 — Một section lồng theo khách hàng trong `cau_hinh.json` bị bỏ qua âm thầm, rồi bị
ghi đè.** (CONFIRMED)
`ap_vao_config` loại mọi khoá có kiểu khác kiểu hiện tại của trường `Config`
(`cau_hinh.py:63`) và chỉ báo qua `bi_bo_qua` — thứ trở thành cảnh báo khởi động mà
`cli.py` **không bao giờ in** (chỉ `app.py:467` render `canh_bao_khoi_dong`). Tệ hơn:
`lay_tu_config` serialize lại **mọi** trường dataclass ở lần lưu kế tiếp
(`cau_hinh.py:70-72`), nên section lồng biến mất ngay lần bấm "Lưu cấu hình" đầu tiên
(`app.py:656`).

**W5 — Làm `Engine.__init__` tôn trọng `TIMCLIP_DATA_DIR` sẽ phá `cli.py dung`.**
(CONFIRMED)
`_file_dung_mac_dinh()` (`cli.py:41-46`) và `os.path.join(eng.data_dir, "DUNG")`
(`cli.py:55`) trùng nhau **chỉ vì** `Engine.__init__` hiện đang bỏ qua biến môi trường
(`engine.py:632`). Sửa một cái mà không sửa cái kia ⇒ tín hiệu dừng rơi vào file không ai
theo dõi.

**W6 — `out_dir` riêng mà không có `data_dir` riêng để lại state tách nửa vời.**
(CONFIRMED)
Log và export đi theo `out_dir`; `tool.lock`, `lichsu.db`, downloads, workspace, config,
registry và metadata đều đi theo `data_dir` (`engine.py:632` so với `engine.py:638`).

**W7 — Nhân bản snapshot metadata theo khách hàng là nhân bản một P1 đã biết.**
(CONFIRMED)
Snapshot ở priority 0 che các chỉnh sửa ghi vào `clips_meta.json`
(`engine.py:1121-1124`; AUD-061/AUD-081). Mọi rollout per-client **nhân defect đó lên
theo số khách hàng** nếu không sửa trước.

**W8 — Chuyển `google_key.json` ra khỏi repo root vô hiệu hoá guard đóng gói.**
(CONFIRMED)
`sheets.py:96-97` là resolver duy nhất, `thieu_gi()` hardcode thông điệp "trong thư mục
dự án" (`sheets.py:117-124`), và `dong_goi.CAM` loại file theo **basename** — nên vừa đổi
chỗ vừa đổi tên sẽ để nó lọt vào zip audit (xem thêm AUD-221 cho lỗ hổng `.txt` kề bên).

---

## 4. Cross-contamination risks

Xếp hạng theo **khả năng xảy ra**, không theo mức độ thiệt hại.

| Hạng | Điểm trộn lẫn | Cơ chế (file:line) | Khả năng | Bán kính thiệt hại |
|---|---|---|---|---|
| **1** | **Dedupe lịch sử triệt tiêu một video cho MỌI khách hàng khác** | `jobs` không có cột kho (`engine.py:874-878`); `ids_da_quet` không phân vùng (`engine.py:3295-3304`); `watch.loc_can_quet` loại mọi candidate có id trong set đó (`watch.py:190-201`, gọi tại `watch.py:378-379`); `ScanResult.status` mặc định `"ok"` kể cả khi 0 match (`engine.py:371`) | **Rất cao** — tự động, mỗi lượt chạy theo lịch | **Âm tính giả im lặng và vĩnh viễn** trên một công cụ phát hiện vi phạm bản quyền. Video đã quét cho khách A **không bao giờ** được so với kho của khách B. Sweep báo chúng dưới `da_quet_truoc` (`watch.py:381`) như đã quét hợp lệ ⇒ operator thấy một lượt chạy sạch. Chỉ thoát được bằng cách xoá tay dòng trong `lichsu.db`. (CONFIRMED — AUD-X19) |
| **2** | **Dòng bằng chứng rơi vào Google Sheet của khách hàng SAI** | `sheet_link` là một scalar (`cau_hinh.py:17`), đọc tại `app.py:107` và `app.py:229`, đóng băng theo batch vào `ScanLaunchConfig` (`scan_jobs.py:65-83`). **Không có gì ràng buộc nó với kho đang chọn.** Chọn kho B ở sidebar (`app.py:485-489`) đổi corpus đối chiếu chứ không đổi đích đến. | **Rất cao** — một ô text, zero coupling, không cảnh báo | Bằng chứng vi phạm của khách B ghi vào workbook của khách A. Chỉ đảo ngược được bằng xoá dòng thủ công. (CONFIRMED) |
| **3** | **Apps Script tô "đã quét" xuyên khách hàng từ một tập khoá không lọc** | `DANG_KY_BANG_LIEN_KET` đăng ký hai bảng link khách hàng với cùng một nguồn so sánh: `{sheetName: 'Link SML', ...}` và `{sheetName: 'Link Cory', ...}`, cả hai `ketQuaHeader: KET_QUA_JSON_FIELDS.INFRINGING_URL` (`apps_script/File01_CauHinh_TienIch.gs:181-191`). `xayDungTapKhoaTuKetQuaQuet_` đọc **toàn bộ** cột "Link video vi phạm" không lọc gì (`apps_script/File04_DanhDauLinkDaQuet.gs:150-158`). Lọc là **bất khả thi về nguyên tắc** vì `bang_ngang.HEADER_NGANG` không có cột kho/khách hàng nào trong 34 tên (`bang_ngang.py:14-49`, đã đọc đủ 34). | **Cao** (nếu dùng Apps Script) | Cặp song sinh tầng Sheets của hạng 1, và nó **tới mắt người** chứ không chỉ nằm trong DB: người phân loại thủ công thấy ô xanh và bỏ qua. Tuy nhiên chỉ là định dạng ô, tự tính lại mỗi lần chạy nên tự lành. (CONFIRMED — AUD-X20) |
| **4** | **Con trỏ kho active là toàn cục, ghi xuống đĩa, và sửa được giữa chừng** | `use_kho` ghi `khos.json["dang_dung"]` (`engine.py:832-838`); selectbox sidebar **không có guard `disabled=`** (`app.py:485-489`, đã đọc — AUD-122); `watch` cũng gọi nó (`watch.py:370-372`) | **Trung bình-cao** | Bằng chứng gán nhầm cho catalogue gốc của khách hàng khác. Theo AUD-122, một build còn có thể ghi đè nhầm `.pklz`. Ngoài ra một sweep ban đêm đổi vĩnh viễn kho mà GUI mở lên sáng hôm sau (AUD-X21, AUD-X15). (CONFIRMED) |
| **5** | **`ketqua/` chứa báo cáo của mọi khách hàng dưới tên file không phân biệt** | `ketqua_<ts>.csv` (`engine.py:3371-3372`), `ketqua_ngang_<ts>.csv` (`engine.py:3404-3407`), `hoso_<video vi phạm>_<ts>.md` (`engine.py:3448-3452`); `giamsat_<date>.log` (`nhat_ky.py:131-133`) | **Trung bình-cao** — mỗi lần export | Operator nén "kết quả" gửi đi là gửi hồ sơ của khách A cho khách B; log chứa URL và đường dẫn cục bộ của mọi khách hàng. (CONFIRMED) |
| **6** | **Một danh tính YouTube cho mọi khách hàng** | `Config.ytdlp_cookiefile` / `ytdlp_cookies_browser` (`engine.py:150-151`); một `CauHinhMang` mỗi Engine (`ytdlp_chung.py:255-268`); `_CACHE_COOKIE` cấp module (`ytdlp_chung.py:189`) | **Trung bình** | Mọi lưu lượng quét quy về một tài khoản Google; bot-block do khối lượng của khách A gây ra làm khách B ngừng hoạt động. (CONFIRMED) |
| **7** | **Một Google service account trên mọi spreadsheet khách hàng** | `sheets.py:96-97`; không call site nào override `key_path` (đã grep) | **Trung bình** (chắc chắn nếu dùng Sheets) | Danh tính đó có Editor trên **mọi** workbook khách hàng — đọc và ghi được tất cả, thu hồi là all-or-nothing. (CONFIRMED) |
| **8** | **Tab Lịch sử phơi bày lượt quét của mọi khách hàng cho ai mở UI** | `eng.list_jobs()` không lọc (`app.py:1471`), render `app.py:1475-1481`, tải CSV per-job `app.py:1495-1497` | **Trung bình** (chắc chắn nếu khách hàng nhìn thấy UI) | Lộ toàn bộ danh sách mục tiêu của các khách hàng khác. Cộng hưởng với việc UI không có xác thực và bind mọi interface (`ChayTool.bat:46`, AUD-222). (CONFIRMED) |
| **9** | **Cache download dùng chung với một ngân sách toàn cục** | `glob(dl_dir + "/" + video_id + ".*")` (`engine.py:2070`, `engine.py:2093`); `don_kho_dem(eng.dl_dir, max_gb=…)` (`cli.py:197-202`, `watch.py:328-331`) | **Trung bình** | Không phải trộn nội dung — cùng video thì cùng byte — mà là ràng buộc chi phí/eviction: sync của khách A đẩy audio cache của khách B ra. (CONFIRMED) |
| **10** | **Retention chẩn đoán là trần 200 file toàn cục** | `engine.py:2696-2699` — `sorted(glob(...))[:-200]` bị xoá, xuyên mọi kho | **Trung bình** | Bản ghi zero-result của khách A đẩy của khách B ra. Chỉ ảnh hưởng chẩn đoán. (CONFIRMED) |
| **11** | **`data/clips_meta.json` dùng chung cho kho tên mặc định** | `engine.py:1136-1138` thêm nó ở priority 100 khi `kho_dang_dung in {"", "Kho mặc định"}` | **Thấp** — cần một khách hàng giữ tên mặc định | Metadata trộn giữa những ai dùng kho mặc định. (CONFIRMED) |
| **12** | **`tool.lock` gây đói tài nguyên chứ không trộn dữ liệu** | `engine.py:1437`, `1496`, `1691`; `watch.py:288`; non-blocking (`khoa.py:20`, `khoa.py:33`) → `DangChayRoi` → `watch.py:300-301` → `cli.py` exit 1 | **Cao về tính sẵn sàng, không về trộn lẫn** | Build nhiều giờ cho khách A làm sweep theo lịch của mọi khách hàng khác thất bại thẳng. **Cuối bảng về TRỘN LẪN, đầu bảng về SẴN SÀNG.** (CONFIRMED) |

**Một rủi ro hạng-2 nữa, ghi riêng vì nó là một nút bấm được ghi nhãn như tính năng:**
"📤 Đẩy TẤT CẢ N kho lên Google Sheets" lặp qua mọi kho vào cùng
`st.session_state.sheet_link` (`app.py:1398-1410`) — toàn bộ catalogue của mọi khách hàng
vào một spreadsheet, hiển thị cho bất kỳ ai có link. (CONFIRMED)

---

## 5. Works Registry readiness

**Định nghĩa dùng ở đây.** "Work" = **một clip gốc trong một kho vân tay** — thứ mà đơn
khiếu nại được lập *thay mặt cho*. Không nhầm với **video vi phạm**, vốn có danh tính
riêng (`ScanResult.source_id`, `engine.py:367`) và được phục vụ tốt hơn nhiều.

### 5.1 Bảng theo từng trường

| Trường registry | Hệ thống có chưa? | Nằm ở đâu (file:line) | Canonical hay derived | Caveat về chất lượng | Gap |
|---|---|---|---|---|---|
| **WORK_ID** | **Không.** Không tồn tại định danh phạm vi-work ở bất kỳ store nào. Khoá de-facto là **tên file clip** | Sinh tại `engine.py:2492` `ten_clip = os.path.basename(g["clip"])` → `Match.clip` (`engine.py:2511-2512`); phía kho `engine.py:1049`; phía metadata `channel.py:592`; lưu tại `matches.clip` (`engine.py:884`, INSERT `engine.py:3284-3287`) | **Derived** (từ một tên file mà chính tool soạn ra) | Tên file nhúng **hai thuộc tính có thể đổi**: ngày đăng và tiêu đề đã sanitize/cắt — `channel.py:465-469` `f"{ngay} - {lam_sach_ten(v.title)} [{v.id}].{AUDIO_EXT}"`. YouTube video ID chỉ tồn tại như **fallback mức 4** (`clip_metadata.py:831` `resolve`, nhánh ID) | **Không có danh tính ổn định, opaque, do máy cấp phát ở bất kỳ đâu.** Không có gì để làm khoá cho một dòng registry |
| **TITLE** | **Có, nhưng không tin được như "the title"** — trường không bao giờ rỗng, và tên file bị thay vào âm thầm | `clips_meta.json["title"]` ghi tại `channel.py:593`; đọc `clip_metadata.py:317`; phơi ra thành `ResolvedClipMetadata.title` (`clip_metadata.py:179`); tiêu thụ `engine.py:3361`, `bang_ngang.py:106`, `dossier.py:56` | **Canonical khi có**; **derived** trên mọi đường suy biến | `_resolved_from_entry` trả `title=title or basename_compatible(clip_name)` (`clip_metadata.py:817`); `_ambiguous_result` đặt `title=name` (`clip_metadata.py:752`); `basename_fallback` đặt `title=name` (`clip_metadata.py:947`). **Không một exporter nào phát ra `resolution_method`/`status`/`warnings`** — `public_dict` chỉ có 5 khoá (`clip_metadata.py:192-199`) | Không có cờ provenance trên giá trị xuất ra. `danh_sach_video.DongVideo.chinh_xac` (`danh_sach_video.py:132`) chứng minh codebase **có mô hình hoá** phân biệt này — rồi vứt nó đi trước khi tới hồ sơ khiếu nại |
| **COPYRIGHT_OWNER** | **Không. Không tồn tại ở bất kỳ đâu.** | Grep toàn tree chỉ ra hai dương tính giả `"UnknownError"` (`engine.py:1545`, `engine.py:1554`) | — | Thứ gần nhất là cấp **kênh**, không phải cấp work: `ScanResult.channel_name/channel_id/channel_url` (`engine.py:374-376`) mô tả kênh **vi phạm**, không phải chủ sở hữu quyền. Tên kho (`khos.json["ten"]`, `engine.py:824`) là free text do operator đặt | **Toàn bộ.** Không trường, không store, không UI, không schema slot |
| **OWNERSHIP_STATUS** | **Không. Không tồn tại ở bất kỳ đâu.** | Cùng grep — không có | — | Ngầm định và không mô hình hoá: "operator đã dựng một kho từ kênh này" là tín hiệu sở hữu duy nhất, và nó là một đường dẫn thư mục (`khos.json["thu_muc"]`, `engine.py:824`) | **Toàn bộ.** Cũng không có gì để gắn trạng thái VÀO, vì chưa có dòng work |
| **PUBLICATION_DATE** | **Một phần.** Mô hình hoá đàng hoàng, nhưng hay rỗng và dễ bị che | Resolve: `publication_date.py:172` `PublicationDateResolver.resolve`; precedence `publication_date.py:65-66` `TRUONG_EPOCH = ("release_timestamp","timestamp")`, `TRUONG_NGAY = ("release_date","upload_date")`. Ghi `channel.py:596-598`. Đọc `clip_metadata.py:347` rồi legacy fallback `clip_metadata.py:354`. Xuất `bang_ngang.py:107` | **Canonical** (`publication_date`) với **derived** fallback (`upload_date`), rồi thêm một derived fallback từ tên file (`clip_metadata.py:642` → `clip_metadata.py:782`) | (a) Lưu dạng `YYYYMMDD` — **không có giờ**, nên registry không tái tạo được múi giờ (`publication_date.py:88-90`). (b) `00000000` là sentinel "không rõ", bị từ chối đúng (`clip_metadata.py:123-124`) và `channel._ten_file` ghi nó có chủ đích (`channel.py:466-468`). (c) Confidence/provenance **được tính mà không bao giờ tới resolver**: `source_from_mapping` không đọc khoá `publication_date_source`/`_confidence` nào, và `MetadataEntry` không có slot (`clip_metadata.py:139-151`). (d) Snapshot (priority 0) che các chỉnh sửa của `kiem_ngay_dang.py:216-218` vào `clips_meta.json` (priority 10) — AUD-061/AUD-081 | Chỉ có ở **một trong ba** exporter (`bang_ngang` có; `Engine.HEADER` tại `engine.py:3317-3322` và `dossier.py` không có cột ngày). Không provenance nào đi cùng giá trị |
| **DURATION** | **Một phần**, và tên trường **âm thầm đổi nghĩa** | `clips_meta.json["duration"]` = `lengthSeconds` YouTube (đã làm tròn) ghi tại `channel.py:602`; `clips_meta.json["duration_media"]` = đo bằng ffprobe ghi tại `channel.py:603` và bởi `kiem_thoi_luong.py:117`. Đọc `clip_metadata.py:366` / `:370`, với **`duration_media` GHI ĐÈ `duration`** tại `clip_metadata.py:374-375` | **Hai phép đo canonical khác nhau bị gộp vào một trường derived** | (a) Registry đọc `ResolvedClipMetadata.duration` (`clip_metadata.py:182`) **không phân biệt được** source-rounded với media-measured. (b) Snapshot mã hoá lại người thắng **dưới khoá `duration`** (`engine.py:1289-1292` → `public_dict`, `clip_metadata.py:153-160`), nên phân biệt bị **huỷ** khi round-trip qua snapshot — xem EF-1 dưới đây. (c) Không bao giờ suy từ tên file (`clip_metadata.py:635`, `:643` đều trả `"duration": None`) — nên work không có metadata entry thì **hoàn toàn không có duration**. (d) Có type guard: `bool` bị loại, phải hữu hạn và > 0 (`clip_metadata.py:133-136`) | Không có marker đơn vị/ngữ nghĩa trên giá trị xuất ra; không có duration cho các work filename-fallback |
| **ORIGINAL_URL** | **Một phần.** Có và **được chuẩn hoá** khi danh tính resolve được; rỗng trên mọi đường suy biến | `clips_meta.json["url"]` ghi tại `channel.py:604` `f"https://youtu.be/{v.id}"`; kiểm định + viết lại `clip_metadata.py:385`; dựng lại từ tên file `clip_metadata.py:641`; xuất `engine.py:3361`, `bang_ngang.py:105`, `dossier.py:57` | **Canonical**, cố ý viết lại để bỏ userinfo/query/fragment (`clip_metadata.py:383-384`) | (a) **Rỗng, không có marker**, trên `ambiguous` (`clip_metadata.py:753`) và `basename_fallback` (`clip_metadata.py:948`) — AUD-062/AUD-063. (b) `_youtube_ids_from_url` chỉ chấp nhận `youtu.be/<id>` và `youtube.com?v=<id>` (`clip_metadata.py:71-90`); `/shorts/`, `/embed/`, `/live/` bị từ chối và URL bị xoá trắng (AUD-069). (c) URL **dẫn xuất từ ID**, nên nó có đúng bằng mức ID có | Không phải danh tính bền — nó là một cách render `video_id`. Rỗng đúng lúc đơn khiếu nại cần nó nhất |
| **VERSION** | **Không.** Không có version/revision/as-of cấp work | Grep `schema_version\|updated_at\|phien_ban\|version` chỉ ra các hit **cấp file**: `schema_version: 1` trên payload snapshot (`engine.py:1367`, và bản sao `engine.py:1601`), `updated_at` (`engine.py:1371`, `engine.py:1607`), mirror lên `MetadataSource.updated_at` (`clip_metadata.py:172`, đọc `clip_metadata.py:510`); còn lại là đồng hồ UI (`app.py:741`) và `FingerprintProgress.updated_at` (`fingerprint_progress.py:105`) | — | `updated_at` là **một** timestamp cho **cả file** snapshot, không phải per clip. `ClipMetadataResolver.updated_at` (`clip_metadata.py:698-700`) chỉ lấy stamp của source non-empty đầu tiên | **Toàn bộ.** Không cách nào diễn đạt "metadata của work này được sửa ngày X", "đây là take 2 của cùng bản gốc", hay "dòng này thay thế dòng kia" |

### 5.2 Store nào mang trường nào

| Store | WORK_ID | TITLE | COPYRIGHT_OWNER | OWNERSHIP_STATUS | PUBLICATION_DATE | DURATION | ORIGINAL_URL | VERSION |
|---|---|---|---|---|---|---|---|---|
| `.pklz` (`ht.names[i]`, đọc `engine.py:1044-1050`) | chỉ path | trong tên file | — | — | trong tên file | — | — | — |
| `<kho>/clips_meta.json` (`channel.py:592-605`) | key = basename | `title` | — | — | `publication_date` + `upload_date` (+ `publication_date_source`) | `duration` + `duration_media` | `url` | — |
| `data/metadata/kho_<slug>.json` (`engine.py:1366-1385`) | key = basename | `title` | — | — | **chỉ `upload_date`** | **chỉ `duration`** (giá trị media bị gộp vào) | `url` | `schema_version` + `updated_at` **cấp file** |
| `data/lichsu.db` `matches` (`engine.py:882-885`) | `clip` (basename) | — | — | — | — | — | — | — |
| `<kho>/downloaded.txt` (`channel.py:359-361`) | YouTube ID, append-only | — | — | — | — | — | — | — |
| CSV dọc `Engine.HEADER` (`engine.py:3317-3322`) | `Clip gốc tìm thấy` | `Tên video gốc (YouTube)` | — | — | — | — | `Link video gốc` | — |
| Bảng ngang 34 cột (`bang_ngang.py:14-49`) | — | `Tên video gốc N` | — | — | `Ngày đăng video gốc N` | `Thời lượng video gốc N` | `Link video gốc N` | — |
| Hồ sơ Markdown (`dossier.py:54-66`) | `ten_clip_goc` | `tieu_de_goc` | — | — | — | — | `link_goc` | — |
| Tab danh sách kho (`danh_sach_video.py:46`) | — | `Tên video` (+ cờ `chinh_xac`, bị bỏ trước khi lên Sheets) | — | — | — | — | — | — |

**Đọc bảng này như sau:** ba trên tám trường (`COPYRIGHT_OWNER`, `OWNERSHIP_STATUS`,
`VERSION`) **không có biểu diễn ở bất kỳ tầng nào**. `WORK_ID` chỉ tồn tại như một tên
file. Bốn trường còn lại có tồn tại nhưng **mất mát trên đường ra**: tầng snapshot — vốn
là nguồn đọc ưu tiên cao nhất (`engine.py:1121-1122`) — lại là schema **hẹp nhất** trong
cả chuỗi (`clip_metadata.py:153-160`, năm khoá), và nó chính là thứ mà một importer
registry sẽ đọc một cách tự nhiên nhất.

### 5.3 Ghi chú cần mang vào thiết kế

1. **`complete` là cờ ĐẦY ĐỦ, không phải cờ ĐÚNG.** `complete = not missing` trên đúng
   năm `_FIELDS` (`clip_metadata.py:31`, tính tại `clip_metadata.py:802`). Một clip mà
   title, ngày và duration đều cũ-nhưng-có-mặt vẫn báo `status="complete"` (AUD-061).
   (CONFIRMED)
2. **Ba công cụ "sửa chữa" và store ưu tiên cao nhất là rời rạc nhau.**
   `ChannelSync.va_metadata`, `kiem_ngay_dang.py:229`, `kiem_thoi_luong.py:135` đều ghi
   `clips_meta.json` (priority 10, `engine.py:1124`); `Engine.va_metadata_thieu`
   (`engine.py:1621`) và offline repair (`engine.py:1400`) chỉ ghi snapshot (priority 0,
   `engine.py:1122`). Merge giữ giá trị non-empty của priority-0
   (`clip_metadata.py:549-558`, fill-empty-only tại `clip_metadata.py:591-592`). **Bất kỳ
   registry nào sync từ `clips_meta.json` sẽ bất đồng với báo cáo.** (CONFIRMED)
3. **Provenance được tính rồi vứt đi ba lần liên tiếp.**
   `PublicationDateResult.to_dict()` sinh `publication_date_source`, `_confidence`,
   `_warnings` (`publication_date.py:97-103`); `channel.py:598` chỉ lưu `_source`;
   `source_from_mapping` không đọc cái nào; `_snapshot_entry` (`engine.py:1289-1292`) bỏ
   nốt cả `_source`. `channel.provenance_ngay_dang` (`channel.py:110-112`) — hàm duy nhất
   trả về đủ dict — **không có caller nào**. (CONFIRMED)
4. **`resolve_many` giữ nguyên thứ tự VÀ duplicate có chủ đích**
   (`clip_metadata.py:961`, docstring "Giữ nguyên thứ tự và duplicate để không lệch đoạn
   ↔ video gốc") — một registry join **không được** de-duplicate danh sách match, nếu
   không đoạn *i* thôi tương ứng với work *i*. (CONFIRMED)
5. **Một kho có thể chứa work chưa bao giờ ở trên YouTube.** `liet_ke_media`
   (`engine.py:574-581`) nhận 18 phần mở rộng gồm `.wav`, `.mp3`, `.flac`
   (`engine.py:101-102`), và UI nhận một đường dẫn thư mục tuỳ ý (`app.py:1119`). Work
   như vậy không có ID, URL, ngày và duration — `basename_fallback` / `unresolved`
   (`clip_metadata.py:944-959`). (CONFIRMED)

### 5.4 Ghi chú về quy mô

`docs/CLIP_METADATA_ARCHITECTURE.md:373-384` ghi lại một lần audit kho thật: **1717 clip,
86 metadata entry, 1631 filename-fallback, 0 complete, 1717 partial.** **Chưa chạy lại**
ở vòng này (`data/` ngoài phạm vi) và tài liệu đã cũ — nên đây là **HYPOTHESIS** về hiện
trạng. Nhưng nó **nhất quán với code**: `duration` không bao giờ suy từ tên file
(`clip_metadata.py:635`, `clip_metadata.py:643`), nên mọi clip filename-fallback **theo
cấu trúc** là `partial`. Hãy xem "phần lớn work trong một kho lắp tay không có DURATION và
không có PUBLICATION_DATE" là **trạng thái ổn định dự kiến**, không phải ngoại lệ.

### 5.5 Cách trung thực tối thiểu để đưa vào ba trường còn thiếu

Cám dỗ với `COPYRIGHT_OWNER` / `OWNERSHIP_STATUS` / `VERSION` là tổng hợp chúng từ thứ có
sẵn gần đó. Đó là kết cục **tệ nhất** cho một công cụ bản quyền: một chủ sở hữu bịa ra
trong hồ sơ khiếu nại còn tệ hơn một ô trống.

**COPYRIGHT_OWNER**
- Đưa vào dạng **do operator khẳng định, nullable tường minh, không bao giờ suy diễn.**
  Mặc định `NULL`, render bằng quy ước `"—"` đã có (`dossier.py:88-89` `hien_thi`), không
  phải bằng phỏng đoán.
- Cách tự động điền duy nhất bảo vệ được là một **gợi ý được ghi nhãn rõ**, lấy từ một
  default cấp kho do operator đặt một lần — vì kho vốn đã là một tập hợp per-channel
  (`khos.json["ten"]`/`["thu_muc"]`, `engine.py:824-825`). Suy từ
  `ScanResult.channel_name` (`engine.py:374`) là **KHÔNG** được: đó là kênh **vi phạm**.
- **Đừng** đưa vào bảng 34 cột cho tới khi nó được người thật điền. Header là hợp đồng
  đóng băng với spreadsheet của người dùng và với hai bản sao Apps Script
  (`bang_ngang.py:14-49`), nên thêm một cột phần lớn để trống chỉ mua về một cuộc migration
  mà không có bằng chứng nào.

**OWNERSHIP_STATUS**
- Một **enum đóng với default `unknown` tường minh**, và `unknown` phải là giá trị trên
  **mọi** work có sẵn — tuyệt đối không back-fill thành `owned` chỉ vì "nó nằm trong kho
  của mình".
- Tiền lệ nên sao chép là `ResolvedClipMetadata.status` (`clip_metadata.py:184`): bốn giá
  trị đóng, `unresolved` làm đáy trung thực, và một tuple `warnings` song song
  (`clip_metadata.py:190`) mang lý do. Dùng hình dạng đó thay vì một boolean.
- Phải ghi kèm **ai khẳng định và khi nào** — nếu không nó không phân biệt được với một
  giá trị mặc định và không bảo vệ được trước bên thứ ba.

**VERSION**
- Version trung thực tối thiểu là **một số nguyên đơn điệu theo từng work, cộng
  `updated_at` và một lý do**, chỉ tăng khi có thay đổi *được khẳng định* (một lần sửa
  của người, hoặc một lượt chạy công cụ sửa chữa), **không bao giờ** khi đọc lại hay
  fingerprint lại.
- Có tiền lệ đang chạy ở cấp file để sao chép: snapshot đã mang `schema_version` +
  `updated_at` + một danh sách provenance `sources` (`engine.py:1367-1376`).
- **Điều kiện tiên quyết, không phải tuỳ chọn:** `MetadataEntry`
  (`clip_metadata.py:139-151`) và `public_dict` (`clip_metadata.py:153-160`) **đều phải
  mở rộng**, vì round-trip qua snapshot hiện **vứt bỏ mọi khoá nó không gọi tên** — đúng
  cơ chế làm mất `publication_date_source` hôm nay (§5.3 mục 3). Một trường VERSION chỉ
  thêm vào `clips_meta.json` sẽ **bị xoá bởi lần dựng vân tay kế tiếp**
  (`engine.py:1803` và `engine.py:1976` đều gọi refresh snapshot).

**Điều kiện xuyên suốt cho cả ba.** Không trường nào có nghĩa nếu không có một `WORK_ID`
ổn định để gắn vào, và không trường nào sống sót nếu không mở rộng schema snapshot. Thứ
tự trung thực là: (1) cấp phát và lưu `WORK_ID` + lịch sử basename, (2) mở rộng
`MetadataEntry`/`public_dict` để khoá phụ sống sót qua round-trip snapshot, (3) **chỉ sau
đó** mới thêm ba trường do người khẳng định, mặc định null/unknown.

---

## 6. Stable identity analysis cho WORK_ID

### 6.1 Bốn ứng viên, chấm điểm

| Ứng viên | Luôn có? | Ổn định qua tải lại? | Ổn định qua đổi tên/copy? | Ổn định qua fingerprint lại? | Kết luận |
|---|---|---|---|---|---|
| **YouTube video ID** (`ResolvedClipMetadata.video_id`, `clip_metadata.py:178`) | **Không** — rỗng với work không phải YouTube, với `ambiguous`, và với `basename_fallback` | **Có** — đó là định danh thượng nguồn | **Có**, *nếu* còn trích được; hôm nay trích từ file đã đổi tên **đang hỏng** (AUD-063) | Có — hoàn toàn không lưu trong `.pklz`, nên dựng lại không đổi được nó | **Neo tốt nhất hiện có, nhưng không phổ quát** |
| **URL chuẩn** (`https://youtu.be/<id>`, `clip_metadata.py:385`) | Không — thuần tuý là cách render ID | Có | Có | Có | **Trùng lặp với ID; tuyệt đối không dùng làm khoá** |
| **Tên file (basename)** (`Match.clip`, `engine.py:2492`) | **Có, luôn luôn** — đây là khoá join mà mọi thứ đã dùng | **Không** — `_ten_file` (`channel.py:465-469`) soạn lại tên từ `upload_date` + tiêu đề đã sanitize, cả hai đều đổi được | **Không** — một bản copy, hậu tố `(copy)`, hay mất tiền tố `YYYYMMDD - ` đều phá fallback mức 6 (AUD-063) | Có — basename sống sót qua rebuild và qua deploy sang máy khác (xem §6.3) | **Phổ quát nhưng không ổn định** |
| **ID nội bộ của audfprint** (index `ht.names`, `audfprint-master/hash_table.py:325-340`) | Có | n/a | n/a | **Không** — xem §6.5 | **Không bao giờ dùng được làm WORK_ID** |

### 6.2 Tính sẵn có — "video ID có luôn tồn tại không?"

**Không.** Bốn nhóm đã kiểm chứng thiếu ID: (CONFIRMED)

1. **Work chưa bao giờ ở trên YouTube.** Mọi file media thả vào thư mục kho đều được
   fingerprint (`engine.py:574-581`, `engine.py:101-102`). `_filename_fallback_parts` trả
   `"video_id": ""` khi pattern chặt không khớp (`clip_metadata.py:629-636`).
2. **Work có token 11 ký tự trong ngoặc vuông ở tiêu đề.** `_BRACKET_ID_PATTERN`
   (`clip_metadata.py:26`) quét cả chuỗi, tìm ra hai "ID", và `resolve` thoát ở bước 0 với
   `input_clip_identity_conflict` → `video_id=""` (`clip_metadata.py:751`). Các thủ phạm
   thật đã được ghi lại ngay trong tree (`danh_sach_video.py:281-291` nêu tên
   `[Compilation]`, `[Official_MV]`, `[4K-REMASTER]`). AUD-062.
3. **Work bị đổi tên/copy.** Mức 6 tự trích lại ID bằng `_FILENAME_PATTERN` chặt
   (`clip_metadata.py:27-30`) thay vì tái sử dụng ID mà bước 0 đã có →
   `basename_fallback`, `video_id=""` (`clip_metadata.py:946-948`). AUD-063.
4. **Entry có `id`, key và `url` bất đồng.** `video_id` và `url` bị cố ý xoá trắng và
   entry không bao giờ được index theo ID (`clip_metadata.py:389-391`).

Nhóm 2–4 cũng chính là các nhóm **không sửa được**: offline repair bỏ qua `unresolved`
(`engine.py:1355-1357`) và `ambiguous` (`engine.py:1352-1354`); network patch đòi
`item.video_id` khác rỗng (`engine.py:1524`).

### 6.3 Ổn định qua tải lại / đổi tên / fingerprint lại

- **Tải lại.** `ChannelSync.sync` không tải lại ID đã có trong `downloaded.txt` hay trên
  đĩa, nên thực tế tên file ổn định. Nhưng nếu file bị xoá rồi sync lại **sau khi**
  uploader đổi tiêu đề, hoặc sau khi `kiem_ngay_dang.py --apply` sửa ngày, thì `_ten_file`
  (`channel.py:465-469`) sinh ra một **basename khác** cho **cùng một work**. Entry `.pklz`
  cũ và khoá metadata mới khi đó không còn join được. (CONFIRMED)
- **Đổi tên / copy.** Phá danh tính hoàn toàn — xem §6.2 mục 3. (CONFIRMED)
- **Fingerprint lại.** Basename **không bị ảnh hưởng**: `db_clips` lấy
  `os.path.basename(ten)` (`engine.py:1049`) và khoá metadata là basename
  (`channel.py:592`). Đây cũng chính là thứ làm deployment chạy được — `.pklz` lưu
  **đường dẫn tuyệt đối của máy nguồn**, vô nghĩa trên máy phụ, trong khi basename vẫn
  join được với `clips_meta.json` đã đóng gói kèm (`dong_goi_may_chay.py:97-99`).
  (CONFIRMED)
- **Di chuyển kho.** Chỉ `clip["duong_dan"]` hỏng; nguồn metadata dẫn xuất
  `legacy_db_folder` (`engine.py:1126-1133`) âm thầm rơi ra, còn hai nguồn chính (snapshot
  + `kho_thu_muc/clips_meta.json`) không ảnh hưởng. (CONFIRMED)

**Kết luận:** basename ổn định trước đúng thao tác mà một registry phải sống sót
(fingerprint lại, redeploy) và **không** ổn định trước đúng thao tác mà con người thực
hiện (đổi tên, copy, tải lại sau khi tiêu đề đổi). Video ID thì ngược lại. **Không cái
nào một mình là đủ.**

### 6.4 Nhu cầu chuẩn hoá URL

Hệ thống đã chuẩn hoá đúng, và registry nên giữ nguyên quy tắc đó:

- URL lưu trữ luôn được viết lại thành `https://youtu.be/<id>` **chính là để bỏ
  userinfo/query/fragment có thể mang token** (`clip_metadata.py:383-385`, và cùng dạng ở
  nguồn ghi `channel.py:604`). (CONFIRMED)
- **Ngữ pháp đầu vào được chấp nhận HẸP HƠN không gian URL thật của YouTube.**
  `_youtube_ids_from_url` (`clip_metadata.py:71-90`) chỉ nhận `youtu.be/<id>` (path) và
  `{youtube.com, m.youtube.com, youtube-nocookie.com}?v=<id>` (query). `www.` bị strip.
  **Không nhận:** `/shorts/<id>`, `/embed/<id>`, `/live/<id>`, `/v/<id>`, và mọi scheme
  không phải http(s). URL không khớp bị xoá trắng kèm `invalid_url`
  (`clip_metadata.py:336-342`). AUD-069. (CONFIRMED)
- **Hệ quả thực tế cho một registry import:** bất kỳ nguồn work bên ngoài nào (một
  spreadsheet, một export từ chủ sở hữu quyền) **rất có khả năng** chứa link `/shorts/` và
  `/embed/`. Những dòng đó sẽ **âm thầm mất cả `url` LẪN `video_id`** khi ingest, trừ khi
  ngữ pháp được nới ra trước. (LIKELY — cơ chế đã đọc trong source, tỷ lệ thực tế trong dữ
  liệu khách hàng chưa đo)
- **Đừng chuẩn hoá về URL.** URL dẫn xuất từ ID (`clip_metadata.py:385`,
  `clip_metadata.py:641`), nên lưu URL làm khoá là lưu ID cộng thêm một quyết định định
  dạng. **Lưu ID.**

### 6.5 Ổn định thứ tự — WORK_ID có tránh được đánh số lại không?

**Không một chuỗi nào trong hệ thống hôm nay an toàn để suy ra WORK_ID.** Đã kiểm chứng:
(CONFIRMED)

1. **ID clip nội bộ của audfprint** — `name_to_id` append theo thứ tự chèn
   (`audfprint-master/hash_table.py:338`) **và tái sử dụng slot của clip đã xoá**
   (`hash_table.py:334` `id_ = self.names.index(None)`, sau khi `remove` đặt
   `self.names[id_] = None` tại `hash_table.py:361`). Nghĩa là một id có thể **được gán
   lại cho một work khác**. Tệ hơn, thứ tự build còn không tất định giữa các lần chạy:
   wrapper chia danh sách file round-robin theo core
   (`audfprint_progress_runner.py:193` `filelists[ix % ncores].append(filename)`) và merge
   theo từng core (`audfprint_progress_runner.py:257` `hash_tab.merge(hash_tabx)`, append
   tại `hash_table.py:298`), nên **đổi `--ncores` là đổi thứ tự `ht.names`** ngay cả với
   một thư mục y hệt. Việc `liet_ke_media` có sort (`engine.py:581`) **không** cứu được.
2. **STT của `danh_sach_video`** — enumerate thuần lúc liệt kê
   (`danh_sach_video.py:470` `DongVideo(stt=i, …)`), tính lại mỗi lần chạy và theo từng
   kho. Chèn một clip là đánh số lại mọi thứ phía sau.
3. **ID autoincrement của `lichsu.db`** — `jobs.id` và `matches.id`
   (`engine.py:875`, `engine.py:883`) đơn điệu **theo từng máy**, và `lichsu.db` bị cố ý
   loại khỏi gói triển khai (`dong_goi_may_chay.py:82-119` chỉ đóng gói `.pklz` +
   `clips_meta.json` + snapshot). Hai máy sẽ cấp phát id đụng nhau. Chúng cũng định danh
   **lượt quét**, không phải work.
4. **`downloaded.txt`** — thứ gần nhất với một work log append-only
   (`channel.py:359-361` append `youtube <id>`), nhưng `sua_archive` ghi lại nó **sắp xếp
   theo id** (`channel.py:650` `for vid in sorted(tren_dia)`), phá huỷ thứ tự chèn, và nó
   được dựng lại từ đĩa bằng một regex ID **thứ ba**, lỏng hơn (`channel.py:634`
   `\[([A-Za-z0-9_-]{6,})\]\.[^.]+$`).

**Do đó:** một WORK_ID phải được **cấp phát và lưu trữ**, không phải **tính ra**. Thứ tự
duy nhất hệ thống cung cấp được là thứ tự operator tình cờ tải về, và thứ tự đó **đã bị
một công cụ recovery hiện có phá huỷ**.

### 6.6 Mô hình danh tính đề xuất (đánh giá, không phải triển khai)

Một cột danh tính đơn lẻ không thể hoạt động ở đây. Hình dạng mà bằng chứng ủng hộ:

- **WORK_ID là opaque, cấp phát một lần, không bao giờ tái suy diễn.** Không phải ID,
  không phải URL, không phải basename, không phải số thứ tự dòng. Việc cấp phát phải
  append-only để không dòng hiện có nào bị đánh số lại.
- **Hai khoá resolve lưu kèm, cả hai đều nullable:** `youtube_video_id` (neo bền và
  portable — có cho nhóm channel-sync) và `fingerprint_basename` (khoá join phổ quát
  nhưng mong manh mà mọi đường code hiện có đã nói: `engine.py:2492`, `engine.py:1049`,
  `channel.py:592`, `engine.py:884`).
- **Một *lịch sử* basename, không phải một giá trị** — vì chính tool có thể đổi tên một
  work (`channel.py:465-469` soạn lại tên từ các thuộc tính thay đổi được). Một ánh xạ
  một-nhiều `work_id → basename` mới là thứ sống sót qua một lần tải lại sau khi tiêu đề
  đổi.
- **Scope registry theo (kho, work), hoặc chấp nhận dedupe là một bài toán mới.** Không
  gì trong hệ thống có góc nhìn xuyên kho: `_metadata_source_candidates` scope cứng theo
  kho active (`engine.py:1121-1138`), `db_clips` chỉ đọc `self.db_file`
  (`engine.py:1007-1021`), và hành động "đẩy tất cả các kho" lặp và ghi **một tab rời cho
  mỗi kho** (`app.py:1398-1410` → `liet_ke_theo_ten_kho`, `danh_sach_video.py:487`; tên
  tab `danh_sach_video.py:517`). Xem EF-3.
- **Đừng resolve danh tính lúc render.** Hôm nay mọi deliverable resolve trực tiếp
  (`engine.py:3359`, `bang_ngang.py:102`, `dossier.py:53`), nên một đơn khiếu nại mở lại
  sau này mô tả metadata **của hôm nay**, không phải metadata đã khẳng định lúc lập đơn
  (AUD-064). Registry chỉ giúp được nếu `matches` **đóng băng** `work_id` tại thời điểm
  `save_job` (`engine.py:3284-3287`).

---

## 7. Dangerous change areas

Xếp theo mức độ nguy hiểm khi sửa. "Nguy hiểm" ở đây = xác suất một thay đổi trông hợp lý
gây ra **kết quả sai âm thầm** hoặc **mất dữ liệu**, chứ không phải độ khó.

### 7.1 HIGH — đừng đụng nếu chưa có quyết định thiết kế và test canh

| Khu vực | file:line | Vì sao nguy hiểm |
|---|---|---|
| **Thứ tự ưu tiên nguồn metadata** | `engine.py:1121-1124` + `clip_metadata.py:549-558` | Đổi priority là đổi **nguồn sự thật** của tiêu đề/ngày/duration trong hồ sơ khiếu nại. Và nó **đã bị test khoá lại**: `tests/test_clip_metadata.py:229-267` khẳng định snapshot thắng live. Sửa AUD-061/AUD-081 theo hướng đảo priority sẽ làm suite đỏ và đồng thời vô hiệu hoá `va_metadata_thieu` — vốn **chỉ** ghi snapshot (`engine.py:1621`). Đây là **xung đột yêu cầu**, không phải bug đơn thuần. (CONFIRMED) |
| **`_merge()`** | `engine.py:2395-2521` | `CLAUDE.md:118-119` cấm sửa nếu không được yêu cầu. Nó quyết định `Match.clip` (khoá join của cả hệ thống, `engine.py:2492`), `clip_bat_dau_s`/`start_s` (mốc trong hồ sơ, `engine.py:2507-2513`) và `clip_offset_s` (`engine.py:2516`). Ba tài liệu kiến trúc đều xác nhận đã cố ý không đụng vào. |
| **`channel._ten_file`** | `channel.py:465-469` | Sinh ra **khoá join** cho toàn hệ thống. Đổi công thức tên = re-key toàn bộ dữ liệu trên đĩa cùng lúc: `.pklz` `ht.names`, khoá `clips_meta.json`, `matches.clip` trong `lichsu.db`. Không có migration nào tồn tại. (CONFIRMED) |
| **`_slug` và mọi thứ dẫn xuất từ tên kho** | `engine.py:729-732`, `engine.py:824-825`, `engine.py:1080-1086`, `danh_sach_video.py:517-561` | Xem W1. Đổi tên kho làm mồ côi **ba** artefact độc lập, và **không có thao tác rename** trong codebase. |
| **Schema `jobs` / `matches`** | `engine.py:874-878`, `engine.py:882-885` | Migration là **một** `ALTER TABLE ... ADD COLUMN` bọc trong `contextlib.suppress(sqlite3.OperationalError)` (`engine.py:879-881`) — idempotent nhưng **không back-fill**. Dòng cũ giữ giá trị mặc định và biến mất khỏi mọi query có filter. Xem W2. (CONFIRMED) |
| **Hợp đồng 34 cột** | `bang_ngang.py:14-49`, `kiem_header.py:11-32`, `apps_script/File01_CauHinh_TienIch.gs:75-110`, `apps_script/TOAN_BO_AppsScript.gs` | Bốn bản sao phải khớp byte-for-byte, cộng thêm **hai vòng lặp hardcode `<= 5`** trong `apps_script/File03_XuatHangDaChon.gs:248` và `:267` dựng lại từng tên slot bằng nối chuỗi (AUD-X22). `kiem_header.py` chỉ so tên cột, **không đọc file `.gs` nào** — nên nó sẽ báo hợp đồng còn nguyên trong khi File03 vẫn phát ra đúng 5 slot. (CONFIRMED) |
| **`cancel_event` và đường huỷ** | `engine.py:650`, `engine.py:1680`, `engine.py:3055-3056`, `engine.py:3149`, `dung_lai.py:33-40` | Một cờ dùng chung cho mọi loại job, bị **sáu** entry point clear khi vào. Đường CLI/watch sống sót nhờ cờ sticky `YeuCauDung._da_dat` (`dung_lai.py:35-36`), được `tests/test_dung_lai.py:92-134` khoá. Sửa cho GUI mà không giữ nguyên hành vi watch là regress một thứ đang đúng. (CONFIRMED) |
| **`data/tool.lock` và ai lấy nó** | `khoa.py:19-20`, `khoa.py:33`, `engine.py:1437/1496/1691`, `watch.py:288` | Khoá **không reentrant** và **non-blocking**. Bọc `scan_media` vào đó (để tuân thủ `CLAUDE.md:78-80`) sẽ **deadlock** đường watch, vốn đã giữ khoá quanh `watch.py:459`. Cần tách `_da_khoa` variant trước. (CONFIRMED) |

### 7.2 MEDIUM — sửa được, nhưng phải đọc invariant trước

| Khu vực | file:line | Lưu ý |
|---|---|---|
| `Engine.__init__` / độ phân giải đường dẫn | `engine.py:615-658` | Tham số hoá tốt, nhưng W5 (`cli.py dung`) và W6 (out_dir/data_dir lệch) rình sẵn. `root=` được dùng cho test isolation ở nhiều chỗ, nên precedence phải là `data_dir` > `root` > env > default. |
| `SheetsExporter` | `sheets.py:91-260` | Ba trục đã là tham số. Nhưng `_KHOA` giữ **xuyên qua network call** (`sheets.py:157-173`) và **không có timeout nào** (`grep -n timeout sheets.py` trả về rỗng) — thêm per-client connection mà không thêm timeout là nhân bản một điểm treo. (CONFIRMED — AUD-X13) |
| `cau_hinh.ap_vao_config` | `cau_hinh.py:44-67` | So kiểu cứng tại `:63`. Thêm trường `Config` kiểu Optional/None sẽ làm **mọi** giá trị đã lưu của trường đó không nạp được (`engine.py:148-149` ghi rõ cái bẫy này). |
| `luu_tru.ghi_json_an_toan` | `luu_tru.py:59-92` | Tên temp file cố định `<path>.tmp` (`luu_tru.py:79`) dùng chung giữa mọi process; khoá chỉ trong process (AUD-161). |
| `don_dep.don_job_quet` | `don_dep.py:162-243` | Heuristic "tuổi = file mới nhất bên trong" (`don_dep.py:132-159`) đúng cho scan job nhưng **không chuyển được** sang fingerprint job, nơi audfprint chỉ ghi db_tam ở cuối (AUD-164). |
| `ScanLaunchConfig` / ranh giới thread | `scan_jobs.py:65-88`, `app.py:105-109` | Frozen dataclass đúng chỗ để thêm `client_id`. Nhưng `tests/test_scan_thread_boundary.py:48-57` khoá cấu trúc: `scan_jobs.py`, `sheet_delivery.py`, `scan_ui.py` **không được import streamlit**. |

### 7.3 LOW — an toàn để mở rộng ngay hôm nay

| Khu vực | file:line | Vì sao an toàn |
|---|---|---|
| `chap_nhan_khop.py` | toàn module | Hàm thuần, không I/O, không phụ thuộc UI. Được test dày (`tests/test_selection.py`, `test_match_selection.py`). |
| `toc_do_khop.py` | toàn module | Thuần, không I/O (`os.path.basename` duy nhất). |
| `publication_date.py` | toàn module | Thuần, chỉ logging. Bốn structural test khoá quy tắc (`tests/test_publication_date_exporters.py:90`, `:118`, `:132`, `:143`). |
| `chan_doan_quet.py` | toàn module | Thuần data record, không I/O. |
| `scan_ui.build_scan_status_dataframe` | `scan_ui.py:67-95` | Hàm thuần, schema dtype khai báo tường minh, có test (`tests/test_scan_ui_schema.py`). |
| `clip_metadata.py` — **chỉ tầng resolve** | `clip_metadata.py:831-959` | Stdlib-only, không network, không ghi file (`clip_metadata.py:4-5`, `:10-22`). Sửa **logic resolve** an toàn; sửa **priority** thì không (§7.1). |
| `dossier.py` render | `dossier.py:86-127` | Hàm thuần, không ràng buộc schema — có thể sửa một mình, khác hẳn bảng 34 cột. |
| `danh_sach_video.py` | toàn module | Read-only theo thiết kế (`danh_sach_video.py:9-14`), cố ý không dùng `luu_tru.doc_json_an_toan` để không bao giờ rename file hỏng. |

---

## 8. Prerequisites

Những việc nên **xong trước** khi bắt đầu Works Registry hoặc vận hành nhiều khách hàng.
Xếp theo thứ tự thực hiện, vì các mục sau phụ thuộc mục trước.

### P0 — Khôi phục cổng kiểm thử (không có nó thì mọi việc sau đều không kiểm chứng được)

| # | Việc | Bằng chứng |
|---|---|---|
| P0.1 | Cài `pytest` vào `.venv` mà launcher chọn, để suite chạy được ở **chính interpreter đang ship** | `kiemtra.bat:8` pin `PY` về `.venv`, nhưng `.venv` không có pytest (AUD-245). Suite thực tế chạy trên CPython 3.14 (bytecode `tests/__pycache__/*.cpython-314-*.pyc`) trong khi `.venv` là 3.12 (AUD-X26). (CONFIRMED) |
| P0.2 | Thêm guard báo lỗi cho bước test và bước AppTest | `kiemtra.bat:18` và `:22` **không có** `\|\| echo [X]`, khác với `:14`. Bước test không thể báo thất bại. (CONFIRMED — AUD-245) |
| P0.3 | Cô lập bước 3/3 bằng `TIMCLIP_DATA_DIR` / `TIMCLIP_OUTPUT_DIR` | `kiemtra.bat:22` chạy AppTest trên `app.py` không set env nào, nên `app.py:41-45` dựng Engine trên `data/` production và chạy DDL trên `lichsu.db` thật (AUD-241). (CONFIRMED) |
| P0.4 | Ghi lại một baseline thật sau khi P0.1–P0.3 xong | Bốn con số mâu thuẫn đang tồn tại: `CLAUDE.md:96` "hơn 240", `README.md:53` "hơn 800", `CLAUDE.md:588` "952 passed", `docs/TEST_REPORT.md:10` "643". Không con số nào chạy lại được ở vòng này. (CONFIRMED) |

### P1 — Quyết định thiết kế phải chốt (không phải task code)

| # | Câu hỏi | Vì sao chặn |
|---|---|---|
| P1.1 | **`data/metadata/kho_<slug>.json` hay `<kho>/clips_meta.json` là nguồn sự thật?** | Đây là P1 cao nhất (AUD-061/AUD-081) và nó là **xung đột yêu cầu**, không phải bug: `tests/test_clip_metadata.py:229-267` khoá snapshot-thắng, `docs/CLIP_METADATA_ARCHITECTURE.md:143-145` tài liệu hoá nó, trong khi **ba** công cụ sửa chữa lại ghi vào file thua. Cho tới khi chốt, mọi tính năng metadata xây trên một split brain. (CONFIRMED) |
| P1.2 | **Một cài đặt phục vụ nhiều khách hàng, hay một cài đặt cho mỗi khách hàng?** | Quyết định toàn bộ scorecard §1 và chọn giữa Tier 3 (rẻ, không đổi schema) và Tier 2 (đắt, đổi schema `jobs`). Không đảo ngược được sau khi đã cấp phát WORK_ID. |
| P1.3 | **Registry key theo (kho, work) hay theo work đơn thuần?** | §6.6 và EF-3: không có đường code nào enumerate xuyên kho được, nên nếu chọn work-đơn-thuần thì phải có quy tắc dedupe (gần như chắc chắn theo `youtube_video_id`) **trước khi** cấp phát ID đầu tiên. |
| P1.4 | **"Stop" có bắt buộc dừng cả batch không?** | AUD-001/AUD-121 chưa sửa, và fix đúng **không được** regress `watch.py`, nơi guard sticky `YeuCauDung` được `tests/test_dung_lai.py:92-134` khoá. Đây là quyết định hợp đồng hành vi. (CONFIRMED) |
| P1.5 | **Đường quét có được miễn `data/tool.lock` không?** | `CLAUDE.md:78-80` phát biểu invariant tuyệt đối; đường quét vi phạm nó (`engine.py:3043`, `engine.py:3145` không lấy khoá nào). AUD-125 và AUD-261 đều kết luận "hoặc sửa code, hoặc sửa doc" và **chưa ai chọn** — nên một invariant thành văn của dự án đang sai một cách có ý thức. (CONFIRMED) |

### P2 — Fix code phải xong trước khi bắt đầu Works Registry

| # | Việc | Bằng chứng | Vì sao là prerequisite |
|---|---|---|---|
| P2.1 | Mở rộng `MetadataEntry` (`clip_metadata.py:139-151`) và `public_dict` (`clip_metadata.py:153-160`) để khoá phụ sống sót qua round-trip snapshot | Snapshot payload = `public_dict()` + `resolution_method` (`engine.py:1289-1292`); 5 khoá, vứt mọi thứ khác | Không có nó, **mọi** trường registry mới thêm vào `clips_meta.json` sẽ bị xoá bởi lần dựng vân tay kế tiếp (`engine.py:1803`, `engine.py:1976`). Đây là cơ chế đang làm mất `publication_date_source` và `duration_media` hôm nay (EF-1, §5.3 mục 3) |
| P2.2 | Sửa AUD-062 (token 11 ký tự trong ngoặc làm work vĩnh viễn không resolve được) và AUD-063 (file đổi tên mất ID dù ID nằm ngay trong tên) | `clip_metadata.py:25`, `clip_metadata.py:841-850`; `clip_metadata.py:918-919` | Đây chính là các nhóm work **không có ID và không sửa được** ở §6.2. Cấp phát WORK_ID trước khi sửa là đóng băng vĩnh viễn một tập work không định danh được |
| P2.3 | Thêm cột kho/khách hàng vào `jobs` và filter cho `ids_da_quet` | `engine.py:874-878`, `engine.py:3295-3304` | Đây là mục **BLOCKED** duy nhất ở §1 và là rủi ro trộn lẫn hạng 1 ở §4. Migration phải quyết định dòng legacy tính là "đã quét cho mọi kho" hay "cho không kho nào" (W2) — quyết định này cũng không đảo ngược được |
| P2.4 | Thêm `gc.set_timeout(...)` sau `gspread.service_account(...)` | `sheets.py:150`; `grep -n timeout sheets.py` → rỗng | Trước khi nhân bản kết nối Sheets theo khách hàng. Không có nó, một kết nối treo giữ `_KHOA` (`sheets.py:157-173`) và, trên đường `watch`, giữ luôn `data/tool.lock` (`watch.py:287-290`) vô thời hạn (AUD-X13) |
| P2.5 | Cho `use_kho` một tham số `luu: bool = True` và để `watch` gọi `luu=False` | `engine.py:832-838`, `watch.py:370-372` | Ngăn một sweep theo lịch đổi vĩnh viễn kho mà GUI và các lệnh CLI khác dùng (AUD-X15). Không test nào khoá hành vi hiện tại của đường watch — `grep -rn "dang_dung" tests/*.py` chỉ ra `tests/test_app.py` và `tests/test_app_fingerprint_progress.py:108` |
| P2.6 | Làm `wl.kho` không dùng được thành **fatal** cho sweep | `watch.py:369-374` — `except` rồi chạy tiếp, không `return`, không `raise` | Một typo trong `watchlist.json` khiến sweep ban đêm so kênh của khách B với vân tay của khách A (AUD-X21). **Lưu ý:** hành vi hiện tại **được test khoá** — `tests/test_watch.py:469` `test_kho_khong_ton_tai_van_tiep_tuc_quet` — nên đây là **thay đổi thiết kế**, phải sửa test cùng lúc. (CONFIRMED) |

### P3 — Test cần viết trước (pin behaviour trước khi refactor)

Hiện **chưa có** test nào khoá các invariant dưới đây; đó là lý do chúng nằm ở đây.
(CONFIRMED — đã grep `tests/`)

| # | Test cần có | Khoá cái gì |
|---|---|---|
| P3.1 | Ghi snapshot, rồi sửa `clips_meta.json`, rồi assert dòng `bang_ngang` **đổi theo** | Chốt chặn cho P1.1. `tests/test_clip_metadata.py:229-267` hiện khoá **chiều ngược lại** ở tầng resolver; chưa có test nào ở tầng engine cho kịch bản snapshot-cũ-che-live-mới |
| P3.2 | Hai kho, cùng một `video_id`, assert kho thứ hai **vẫn quét** | Chốt chặn cho P2.3 / §4 hạng 1. `tests/test_engine_core.py:118-141` chỉ pin filter theo status và id rỗng, nên một tham số có default sẽ giữ nó xanh |
| P3.3 | Batch nhiều video, bấm Stop giữa chừng, assert các video còn lại **không** chạy | Chốt chặn cho P1.4. `grep -rn "cancel" tests/test_scan_streaming.py` → không có kết quả |
| P3.4 | Snapshot round-trip giữ nguyên một khoá phụ (ví dụ `duration_media`) | Chốt chặn cho P2.1 |
| P3.5 | Assert `ChayTool.bat` chứa `--server.address=` | Chốt chặn cho AUD-222; hiện không test nào đọc bind address (`tests/test_cap_nhat.py:217` chỉ đọc thứ tự errorlevel) |
| P3.6 | Assert biên `SO_DOAN` trong Apps Script khớp `bang_ngang.SO_DOAN` | Chốt chặn cho AUD-X22; `kiem_header.py` hiện **không đọc file `.gs` nào** |

### P4 — Nên dọn cùng lúc (rẻ, giảm nhiễu cho mọi việc trên)

- Sửa `cli.py:126` `--ncores` default `1` → `None` và chỉ gán khi được truyền
  (`cli.py:183`) — CLI hiện âm thầm ghi đè cấu hình đã lưu (AUD-162/AUD-183). (CONFIRMED)
- Thêm `"cookie"` vào `TU_KHOA_NHAY_CAM` (`dong_goi.py:28-31`) — một dòng, đóng **cả hai**
  packager vì cùng dùng `la_file_nhay_cam` (AUD-181/AUD-221). (CONFIRMED)
- Thêm `--server.address=127.0.0.1` vào `ChayTool.bat:46`, khớp với `README.md:17` và
  `docs/INSTALL_WINDOWS.md:112` (AUD-222). (CONFIRMED)
- Cho `delete_kho` xoá luôn `self._metadata_snapshot_path()` và `.bak` của nó — guard
  `commonpath` tại `engine.py:1088-1093` đã làm việc đó an toàn (AUD-X03). (CONFIRMED)
- Sửa `docs/RUNBOOK.md:100`: snippet backup copy `watchlist.local.json` trong khi tool đọc
  `watchlist.json` (`cli.py:51`, `ChayMayPhu.bat:13`), và `-ErrorAction SilentlyContinue`
  làm nó trượt im lặng. Watchlist là input vận hành **duy nhất không tái tạo được**.
  (CONFIRMED)

---

## Phụ lục A — Ba phát hiện xuất hiện từ chính góc nhìn này

Ba mục dưới đây không thuộc bất kỳ domain đơn lẻ nào; chúng lộ ra khi nhìn xuyên các tầng.

**EF-1 (P2, CONFIRMED) — Round-trip qua snapshot đổi tên `duration_media` thành
`duration`, huỷ phân biệt source-vs-measured.**
`clips_meta.json` cố ý mang hai phép đo dưới hai khoá và code ghi rõ lý do
(`channel.py:599-603`; lập luận tương tự tại `clip_metadata.py:361-365`).
`source_from_mapping` đọc cả hai và để giá trị media thắng, **gán vào cùng một biến**
(`clip_metadata.py:370-375`). Snapshot rồi serialize giá trị đó **dưới tên `duration`**
(`engine.py:1289-1292` → `public_dict`, `clip_metadata.py:153-160`). Ở lần đọc kế tiếp
entry snapshot có `duration` và **không có** `duration_media` (`clip_metadata.py:366`,
`:370`), nên không ai — không resolver, không importer, không con người — phân biệt được
đó là lengthSeconds làm tròn hay số đo thật. Vì snapshot ở priority 0
(`engine.py:1122`) và được ghi lại tự động sau **mọi** lần dựng vân tay
(`engine.py:1803`, `engine.py:1976`), việc gộp này là **trạng thái ổn định**, không phải
ca biên. *Hệ quả cho registry:* cột `DURATION` import từ `data/metadata/kho_*.json` sẽ
**không đồng nhất một cách âm thầm**. Khác với AUD-081 (nói về snapshot *che chỉnh sửa*);
đây là snapshot *đổi tên trường*.

**EF-2 (P2, CONFIRMED) — Không một deliverable nào phân biệt được tiêu đề YouTube thật với
tên file đã sanitize, dù codebase có mô hình hoá phân biệt đó.**
Ba đường suy biến đều thay tên file vào chỗ tiêu đề, không marker: `clip_metadata.py:817`
(`title or basename_compatible(clip_name)`), `clip_metadata.py:752` (`title=name`),
`clip_metadata.py:947` (`title=name`). Ba exporter chỉ đọc `title`: `engine.py:3361`,
`bang_ngang.py:106`, `dossier.py:56` — không cái nào phát ra `resolution_method`
(`clip_metadata.py:183`), `status` (`:184`) hay `warnings` (`:190`). Trong khi đó
`DongVideo.chinh_xac` (`danh_sach_video.py:132`) là một boolean chuyên dụng có docstring
nêu chính xác sự khác biệt (`danh_sach_video.py:122-125`) — và cờ đó **không bao giờ rời
khỏi tab danh sách kho**. Phạm vi rộng hơn AUD-062/AUD-063 (vốn nói về nhóm `ambiguous` /
`unresolved` mất **URL**): EF-2 phủ nhóm `partial` / `filename_fallback` lớn hơn nhiều,
nơi URL và ID vẫn đúng nhưng **TITLE** là một tên file bị cắt và thay ký tự, được trình
bày như tên của tác phẩm gốc trong một hồ sơ khiếu nại.

**EF-3 (P3, CONFIRMED) — Không có danh tính work xuyên kho, và không đường code nào
enumerate work xuyên kho được.**
`_metadata_source_candidates` chỉ thêm `self._metadata_snapshot_path()` và
`self.kho_thu_muc/clips_meta.json` (`engine.py:1121-1124`), với docstring "Nguồn chỉ thuộc
kho active" (`engine.py:1110`) và một từ chối tường minh không đọc `data/clips_meta.json`
ngoài kho mặc định "vì sẽ trộn metadata giữa nhiều kho" (`engine.py:1135-1138`).
`db_clips` chỉ đọc `self.db_file` (`engine.py:1007-1021`). Hành động "tất cả các kho" duy
nhất lặp và ghi **một tab rời cho mỗi kho**, mỗi tab có `stt` bắt đầu lại từ 1
(`app.py:1398-1410` → `danh_sach_video.py:487`; tên tab `danh_sach_video.py:517`). Đây
**không phải bug** — scope này cố ý và đúng cho việc quét — nhưng nó là tiền đề cấu trúc
mà registry **phải quyết định trước khi** cấp phát bất kỳ ID nào, vì lựa chọn đó không
đảo ngược được nếu không đánh số lại (§6.5).

---

## Phụ lục B — Gap: những gì tài liệu này KHÔNG xác định được

| # | Chưa biết | Cách giải quyết |
|---|---|---|
| B1 | Mô hình dự kiến là *một cài đặt nhiều khách hàng* hay *một cài đặt mỗi khách hàng* (P1.2) | Hỏi operator. **Ẩn số load-bearing nhất trong tài liệu này.** |
| B2 | Nội dung sống của `data/khos.json` và `data/cau_hinh.json` — có bao nhiêu kho, có kho nào tên `"Kho mặc định"`, `sheet_link` và cookie đã set chưa | Ngoài phạm vi vòng này. `python kiem_metadata_kho.py --json` là read-only (`kiem_metadata_kho.py:290`) và trả lời được nửa metadata |
| B3 | Có kho nào **hiện đang** có snapshot lệch với `clips_meta.json` không — tức bán kính thật của AUD-061/AUD-081 và của W1 | Cùng lệnh trên; đọc `audit.conflicts` |
| B4 | Có snapshot mồ côi nào của một kho không còn trong `khos.json` không (tức AUD-X03 đã nổ chưa) | So `ls data/metadata/kho_*.json` với `_slug(ten)` của từng entry trong `khos.json` |
| B5 | Service account trong `google_key.json` đã được chia sẻ với spreadsheet của bên thứ ba nào chưa | Google Cloud IAM + danh sách share của từng spreadsheet; không xác định được từ source |
| B6 | Streamlit UI có/sẽ tiếp cận được bởi khách hàng không — §4 hạng 8 chỉ là vấn đề rò rỉ **dưới điều kiện đó** | Hỏi operator; xem thêm AUD-222 (`ChayTool.bat:46` bind mọi interface) |
| B7 | Hậu tố md5 6 hex của `_slug` (`engine.py:731-732`) đã đụng độ bao giờ chưa. Xác suất ~1/16.7 triệu mỗi cặp tên — không đáng kể dưới vài nghìn kho, nhưng nó là thứ **duy nhất** tách hai kho có 30 ký tự đầu sau sanitize giống nhau | Một lệnh kiểm trên `khos.json` lúc triển khai. Không đáng đổi code |
| B8 | Múi giờ bind lúc import (`publication_date.py:56`, `:238`) có thành vấn đề không — tức có khách hàng nào ngoài `Asia/Ho_Chi_Minh` | Hỏi. Nó override được per-process qua `TIMCLIP_MUI_GIO`, nên con đường Tier 3 đã xử lý |
| B9 | Tỷ lệ thực tế URL `/shorts/` và `/embed/` trong dữ liệu nguồn của khách hàng (§6.4, đánh giá LIKELY) | Chỉ đo được trên dữ liệu thật |

---

*Tài liệu này mô tả **hiện trạng** và đề xuất **khả năng**. Không có thay đổi nào đã được
thực hiện.*
