# MODULE MAP — Bản đồ sở hữu module

Tài liệu tham chiếu cho người mới. Mục tiêu: trả lời được "file này làm gì, ai gọi nó, nó
đụng vào dữ liệu nào, sửa nó thì vỡ ở đâu" mà không phải đọc hết 15.174 dòng.

**Phạm vi.** 38 file `.py` ở thư mục gốc dự án, cộng hai nhóm `tests/` và `apps_script/`.
Không bao gồm `audfprint-master/` (thư viện MIT vendor, không được sửa — CLAUDE.md:29) và
`.venv/`.

**Nguồn sự thật.** Mọi khẳng định trong tài liệu này đều kèm `file:line` đọc trực tiếp từ
source. Khi tài liệu trong `docs/` mâu thuẫn với code, code thắng và mâu thuẫn được nói rõ.
Tài liệu này **mô tả hiện trạng**; phần khuyến nghị luôn được viết ở thì điều kiện và
**không có thay đổi code nào được thực hiện**.

**Đồ thị import đã kiểm chứng.** Cột "Depends on" liệt kê import nội bộ dự án ở mức module,
lấy từ một lượt grep toàn cây. Import muộn (trong hàm) được đánh dấu `(muộn)` kèm dòng.

## Thang đánh giá Risk

Nhãn Risk là **phán đoán kỹ thuật**, không phải phát hiện lỗi. Rubric:

| Nhãn | Điều kiện (chỉ cần một) |
|---|---|
| **HIGH** | Có finding CONFIRMED cấp P1/P2 làm ra **kết quả sai** hoặc **mất dữ liệu**; HOẶC fan-in ≥ 4 module (sửa là lan rộng); HOẶC giữ state mutable dùng chung giữa nhiều thread/process. |
| **MEDIUM** | Chỉ có finding CONFIRMED cấp P2/P3, hoặc blast radius bị chặn (script chạy tay, đường không mặc định). |
| **LOW** | Hàm thuần, không I/O, không có finding trên P3, và không ai phụ thuộc ngoài 1–2 chỗ. |

Mã `AUD-xxx` trỏ về digest audit. Trong tài liệu này **chỉ trích dẫn finding có verdict
CONFIRMED**, trừ khi ghi rõ `(LIKELY)`. Không finding nào bị bác bỏ (REFUTED /
NOT_REPRODUCED) được nêu ra như một vấn đề.

---

## 1. Bảng module

Sắp theo LOC giảm dần. Tổng: **15.174 dòng** trên 38 file.

| Module | LOC | Responsibility | Main public APIs | Depends on | State owned | Side effects | Concurrency | Risk |
|---|---|---|---|---|---|---|---|---|
| **engine.py** | 3453 | Trục chính của cả hệ: `Config`, quản lý kho vân tay, gọi audfprint/ffmpeg, tải YouTube, cắt khúc, merge, chọn Top-N, ghi SQLite, xuất CSV/hồ sơ | `Engine.scan_iter` :3224, `scan_youtube` :3145, `scan_media` :3043, `build_database` :1669, `save_job` :3273, `db_clips` :1007, `clip_metadata_resolver` :1163, `to_rows` :3344 / `to_rows_ngang` :3385, `export_csv` :3369 / `export_csv_ngang` :3396 / `export_ho_so` :3420, `ids_da_quet` :3295, `HEADER` :3317, `hhmmss` :407, `o_bang_tinh_an_toan` :538, `liet_ke_media` :574 | channel, cau_hinh, ytdlp_chung, dossier, chan_doan_quet, chap_nhan_khop, toc_do_khop, clip_metadata, fingerprint_progress, khoa, luu_tru, process_runner, publication_date; `bang_ngang` (muộn :3387, :3398) | `config` :618, `cancel_event` :650, `_cache_khoa`/`_cache_clips` :651-652, `_metadata_resolver_cache` :653-654, `chan_doan_quet` :628, `canh_bao_*` :619-624, `db_file`/`kho_dang_dung` :794-797 | Tạo `data/`, `data/downloads/`, `ketqua/` :641-642; **prepend `bin/` vào `os.environ["PATH"]` cả process** :645-646; insert `audfprint-master` vào `sys.path` :1032-1033; spawn ffmpeg/ffprobe/audfprint; ghi lichsu.db, khos.json, snapshot metadata, CSV, .md | **Không thread-safe.** Một Engine dùng chung giữa main thread Streamlit và worker (app.py:113-118 gọi `to_rows_ngang` trong worker). Cache không có lock. `KhoaTienTrinh` chỉ ở :1436, :1495, :1690 — **đường quét không giữ khoá** | **HIGH** — AUD-121, AUD-122, AUD-061, AUD-064 |
| **app.py** | 1508 | Toàn bộ UI Streamlit: sidebar, 6 tab (:944), hai màn hình tiến độ, khởi/kết job. **Module duy nhất `import streamlit`** (:18) | `chay_quet` :95, `chay_nen` :146, `chay_van_tay` :168, `df_ket_qua` :330, `bang_ket_qua` :358, `tao_sheets_exporter` :222, `day_len_sheets` :232, `bao_cao_khong_co_ket_qua` :256 | bang_ngang, danh_sach_video, cau_hinh, clip_metadata, ytdlp_chung, engine, fingerprint_progress, scan_jobs, scan_ui, sheet_delivery, channel, sheets; `engine.liet_ke_media` (muộn :1458) | `st.session_state`: `eng` :41-45, `job` dict :53-55, `fingerprint_controller` :59-60, `scan_sheet_worker` :80-86, `scan_controller` :87-90 | Sinh tới 4 họ daemon thread; ghi `cau_hinh.json` (:656); đẩy Google Sheets; **ghi đè `eng.config.*` mỗi lần rerun** :503-565, :580-606 | Main thread only, **trừ 4 closure giao cho worker**: `sau_moi_video` :113, `chay_nen.target` :152-161, sender lambda :84-85. Không closure nào gọi API Streamlit (khoá bởi tests/test_scan_thread_boundary.py:48-57). Vòng lặp `time.sleep(0.75); st.rerun()` :835-836 | **HIGH** — AUD-121, AUD-122, AUD-127, AUD-205 |
| **clip_metadata.py** | 1058 | Mô hình metadata thuần: load/validate/index/merge từ nhiều nguồn, chuỗi phân giải 7 mức từ tên clip → danh tính YouTube. **Không mạng, không credential, không ghi file** (:4-5) | `ClipMetadataResolver.resolve` :831, `resolve_many` :961, `coverage` :968, `audit` :981, `load_metadata_strict` :434, `source_from_mapping` :276, `configure_metadata_logging` :34, `filename_fallback_parts`, `extract_youtube_id` :105, `valid_upload_date` :111 | *(không có — chỉ stdlib, :10-22)* | Ba index `_exact`/`_basename`/`_canonical`/`_video_id` + `conflicts`, dựng một lần trong `__init__` :660-701 | Chỉ logging | Bất biến sau khi dựng; Engine cache resolver theo chữ ký file :1141-1162 | **HIGH** — AUD-061, AUD-062, AUD-063; fan-in 7 |
| **channel.py** | 687 | Đồng bộ kênh gốc: liệt kê kênh, tải bestaudio, transcode opus, đặt tên file chuẩn. **Là writer duy nhất của `clips_meta.json`** | `ChannelSync.sync` :557, `list_channel` :381, `va_metadata` :216, `lay_info_video` :366, `load_meta`/`save_meta` :178-182, `seed_meta_tu_dia` :184, `kiem_tra_thieu` :669, `sua_archive` :639, `lam_sach_ten` :91, `ngay_dang_tu_info` :98, `do_dai_media` :69 | clip_metadata, luu_tru, publication_date, ytdlp_chung | `<kho>/clips_meta.json`, `<kho>/downloaded.txt`, `<kho>/_tam/`; `NhoClientTotNhat` riêng mỗi instance :174 | Mạng yt-dlp (:377, :419, :490); spawn ffmpeg :543 và ffprobe :81; `rmtree` `_tam` :614 | Tuần tự trong `sync`; `cancel_check` chỉ giữa các video :584. **`va_metadata` không có tham số cancel nào** | **HIGH** — AUD-067, AUD-101 (LIKELY), AUD-X06 |
| **danh_sach_video.py** | 647 | Kiểm kê kho offline (tên video thật, không suy từ tên file) rồi **ghi đè** một tab Sheets riêng cho từng kho | `liet_ke_kho` :327, `liet_ke_theo_ten_kho` :487, `ten_trang_tinh` :517, `hang_bang_tinh` :562, `day_len_sheet` :598, `KetQuaKho` :137, `DongVideo` :117 | channel (`AUDIO_EXT`), clip_metadata, sheets | *(không giữ state)* | **Ghi đè toàn bộ tab `DanhSachVideo_<kho>` qua `ghi_de`** — resize + update, không undo | Main thread; cố ý **không** dùng `SheetDeliveryWorker` (:616-619) vì khoá idempotency băm nội dung sẽ bỏ qua lần chạy lại không đổi | **HIGH** — AUD-207; ghi phá huỷ |
| **fingerprint_progress.py** | 593 | Hợp đồng tiến độ dựng kho: `FingerprintProgress` (dataclass đông cứng), tracker giữ bất biến bộ đếm, controller một worker + queue có chặn. Cố ý không biết gì về Streamlit | `FingerprintJobController.start` :482, `cancel` :542, `snapshot` :553, `drain` :567, `FingerprintProgressTracker` :146, `tao_fingerprint_logger` :48, `ten_file_an_toan` :41 | *(chỉ stdlib)* | `_state`, `_files`/`_active`/`_finished`, `events` Queue(256) :458, `_recent` deque(50) | Ghi `ketqua/fingerprint.log` (RotatingFileHandler 5MB×3) | `threading.RLock`; đúng một daemon thread mỗi job :534-539. Queue ops ở :473-480 **nằm ngoài lock** | **MEDIUM** — AUD-053 (LIKELY) |
| **ytdlp_chung.py** | 520 | **Chỗ duy nhất dựng dict tuỳ chọn yt-dlp.** Kiểm tra file cookie, xếp thứ tự player client, phát hiện cookie chết, dịch lỗi sang tiếng Việt | `CauHinhMang` :256 (`tuy_chon` :339, `tu_config` :270, `tu_file_cau_hinh` :286, `bo_cookie` :329), `kiem_tra_file_cookie` :192, `chay_kem_duong_lui_cookie` :393, `thu_tung_client` :463, `giai_thich_loi` :84, `NhoClientTotNhat` :425 | *(không; `yt_dlp` import muộn)* | `_CACHE_COOKIE` module-global :189; `NhoClientTotNhat._client`/`_luc` | Đọc file cookie (chỉ để validate format, :218) | `CauHinhMang` là frozen dataclass, cố ý chia sẻ được giữa thread (:257-259). `NhoClientTotNhat` mutable, không lock (lành: chỉ là gợi ý thứ tự) | **HIGH** — AUD-104, AUD-105, AUD-X12; cổng duy nhất của 6 điểm dựng `YoutubeDL` |
| **watch.py** | 517 | Model watchlist + **một lượt quét giám sát** (không có vòng lặp/scheduler nào trong file — nhịp do Task Scheduler quyết định) | `chay_giam_sat` :270, `doc_watchlist` :123, `ghi_watchlist` :164, `id_da_quet` :174, `loc_can_quet` :190, `lay_ung_vien` :205, `WatchList` :26, `BaoCao` :41 | bang_ngang, channel, don_dep, khoa, luu_tru, sheets | Chỉ trong process: bộ đếm `BaoCao`, `da_day_sheets: set[int]` :390 | Giữ `data/tool.lock` cả lượt :287-290; ghi Sheets :426 và :509; ghi CSV; dọn cache trong `finally` :326-356 | Đơn luồng dưới khoá liên process. **Loại trừ lẫn nhau với build/metadata repair, nhưng KHÔNG với quét từ GUI** | **HIGH** — AUD-144, AUD-182 (LIKELY), AUD-187, AUD-X14, AUD-X21 |
| **sheets.py** | 407 | Writer Google Sheets duy nhất: auth service-account, cache kết nối module-level, `append` (cộng thêm) và `ghi_de` (ghi đè phá huỷ). Mọi ghi đều `value_input_option="RAW"` | `SheetsExporter` :91, `append` :197, `ghi_de` :253, `kiem_tra` :179, `san_sang` :114, `email_service_account` :126, `xoa_cache_ket_noi` :47 | *(không)* | `_CACHE` module-global :44, khoá `(key path, key mtime_ns, sheet_id, worksheet)` :139-145 | Ghi mạng lên Sheets; có thể tạo worksheet mới :155; `ghi_de` thu nhỏ grid → **xoá vĩnh viễn dòng ngoài phạm vi** :271-273 | `_KHOA = threading.RLock()` :43 bảo vệ cache — **nhưng lock được giữ xuyên qua network I/O** trong `_ket_noi` :163-172, và object `Worksheet` trả về thì không được serialise | **HIGH** — AUD-141, AUD-147, AUD-X07 (LIKELY), AUD-X13 |
| **scan_jobs.py** | 390 | Controller batch quét cho UI: một worker thread, `BatchSnapshot` bất biến cho main thread, suy phase từ chuỗi tiến độ của engine | `ScanJobController.start` :169, `cancel` :207, `snapshot` :344, `results` :374, `ghi_nhan_giao_hang` :329, `ScanLaunchConfig` :66, `VideoState` :91, `doan_phase` :52 | *(không)*; `sheets._lay_sheet_id` (muộn :85) | `_videos`, `_results`, `_recent` deque(60), `_events` Queue(512) :158 — tất cả dưới `RLock` :152 | Sinh daemon thread `scan-<8hex>` :198-204; `engine.cancel_event.clear()` :193 | RLock + snapshot đông cứng. **Vòng lặp tiêu thụ `scan_iter` không bao giờ đọc lại `self._cancelled`** :263-266 | **HIGH** — AUD-001/AUD-121, AUD-124 |
| **audfprint_progress_runner.py** | 340 | Adapter runtime bọc audfprint vendor: cài 3 monkey-patch, phát sự kiện JSON mỗi clip, thay `multiproc_add` bằng fan-in qua file tạm (không deadlock trên pipe) | `main`, `cai_dat_instrumentation` :307-318, `instrumented_make_ht_from_list`, `instrumented_multiproc_add` :170-264, `PREFIX` | *(không project; nạp `audfprint-master` lúc chạy)* | `CHO_WORKER_S = 1800`, thư mục `mkdtemp(prefix="timclip_ht_")` :195 | **Sửa thuộc tính module audfprint lúc chạy** (không sửa source vendor); ghi `hash_table_<i>.pklz` vào temp | Chạy **với tư cách** process audfprint; sinh `ncores` worker `multiprocessing.Process`; mỗi worker một ffmpeg. Một sự kiện = một `os.write` để 8 con không đan xen (:39-40) | **HIGH** — AUD-044; là lớp duy nhất giữ audfprint không bị sửa |
| **kiem_metadata_kho.py** | 338 | CLI audit ánh xạ metadata kho, chỉ đọc. `--repair-offline --apply` là đường ghi duy nhất | `main`, `_engine_chi_doc` :62-76, `_report` :165 | clip_metadata, engine | *(không; dựng Engine bằng `object.__new__` :62-76 để tránh side effect của `__init__`)* | Mở `lichsu.db` với URI `?mode=ro&immutable=1` :82; chỉ ghi snapshot khi `--apply` | Đơn process | **LOW** — công dân mẫu mực; nhưng phải mirror thuộc tính mới của `Engine.__init__` nếu không sẽ `AttributeError` |
| **kiem_ngay_dang.py** | 323 | CLI audit/sửa `publication_date` trong `clips_meta.json`. Chỉ đọc trừ khi `--apply` | `audit` :69, `repair` :135, `main` :244, `TRUONG_DO_TIN_CAY_CAO` :43 | channel, clip_metadata, publication_date | *(không ngoài file đích)* | Ghi `<kho>/clips_meta.json` + backup `.truoc_ngay_dang_<ts>` :226-229; gọi mạng khi `--repair-network` | Đơn luồng; **không giữ `tool.lock`**; có circuit breaker 25 lỗi liên tiếp :192-195 | **HIGH** — AUD-102, AUD-082; ghi vào store bị snapshot che (AUD-081) |
| **cli.py** | 318 | Front-end argparse lên Engine — bề mặt tương thích cho automation. 10 lệnh: `kenh taodb themclip youtube file watch vameta vametak dondep dung` :104-116 | `main` :101, `in_tien_do`, `_chay_lenh_watch`, `_file_dung_mac_dinh` :41-46 | don_dep, nhat_ky, watch, channel, clip_metadata, dung_lai, engine, ytdlp_chung | Không của riêng nó; giữ quy ước đường dẫn cờ dừng `<script dir>/data/DUNG` | Dựng `Engine()` **không tham số** :182 (bỏ qua `TIMCLIP_DATA_DIR`); ghi `data/DUNG`, CSV, log giám sát; **ghi đè `eng.config.ncores` vô điều kiện** :183 | Main thread; không giữ khoá trực tiếp. `SystemExit(1)` khi `bc.loi` khác rỗng :97-98 | **HIGH** — AUD-162/AUD-183, AUD-185, AUD-187 |
| **publication_date.py** | 294 | **Nguồn sự thật duy nhất cho "ngày đăng"**: chuỗi ưu tiên, quy đổi múi giờ, dataclass provenance, và formatter DD/MM/YYYY duy nhất | `PublicationDateResolver.resolve` :172, `resolve_publication_date` :241, `format_publication_date` :251, `ngay_tu_epoch` :141, `epoch_hop_le` :125, `ghi_log_chan_doan` :267, `TRUONG_EPOCH` :65 | *(không)* | `MUI_GIO_MAC_DINH` :56 và `_MAC_DINH` resolver :238 — **cả hai bind lúc import** | Chỉ logging | Thuần, main thread, không state mutable dùng chung | **MEDIUM** — AUD-086 (LIKELY); bất biến được khoá bởi 4 test cấu trúc |
| **dong_goi_may_chay.py** | 289 | Đóng gói zip chạy được cho máy phụ: source + `.pklz` chọn lọc + `clips_meta.json` + snapshot + config đã lọc + ffmpeg. Cố ý loại audio nguồn và `lichsu.db` | `gom_thanh_phan` :65, `noi_dung_sinh_them` :166, `tao_goi` :199, `KHOA_RIENG_CUA_MAY` :152-157 | dong_goi, luu_tru | Định nghĩa `KHOA_RIENG_CUA_MAY` — các key config **không được đi giữa máy** | Ghi zip; xoá zip nếu hậu kiểm phát hiện tên nhạy cảm :225-229 | Đơn luồng | **MEDIUM** — AUD-046, AUD-181/AUD-221; đọc `khos.json["db"]` **không qua guard** `_duong_dan_db_kho` |
| **chan_doan_quet.py** | 287 | Bản ghi phễu phát hiện: đếm sống sót mỗi tầng, gọi tên tầng làm mất hết kết quả, ghi ứng viên bị loại mạnh nhất, nhận diện "toàn nhạc hiệu" | `ChanDoanQuet` , `chot_giai_doan` :134, `mat_o_dau` :153, `tom_tat` :191, `dong_log` :203, `thanh_dict`, `ghi_nhan_bi_loai` :263, `_deu_la_nhac_hieu` :246 | *(không)* | Dataclass thuần; instance sống nằm trên `Engine.chan_doan_quet` (:660-676) | Không I/O | Dữ liệu thuần; instance cấp Engine là per-scan, **không reentrant** | **MEDIUM** — AUD-009/AUD-031, AUD-026 |
| **process_runner.py** | 280 | Giám sát subprocess không chặn: thread đọc stdout, queue 256 dòng, tail 30 dòng, soi cây process bằng psutil mỗi 0.2 s, heartbeat, huỷ theo cây PID | `run_observed_process` :82, `terminate_process_tree` :61, `ProcessResult` :38, `ProcessSnapshot` :29 | *(không)* | Không bền; queue/deque cục bộ mỗi lần gọi | Spawn và kill **cây** process | 1 daemon reader thread mỗi lần gọi. Kill **chỉ theo PID gốc và hậu duệ của nó** — không bao giờ khớp theo tên process | **MEDIUM** — AUD-048 (`timeout_seconds` có nhưng không ai truyền), AUD-052 |
| **cap_nhat.py** | 267 | Tự cập nhật từ GitHub theo **tag**. Không bao giờ raise, không bao giờ dùng verb git phá huỷ | `cap_nhat` :168, `_git` :64, `thu_muc_repo` :97, `cay_lam_viec_sach` :107, `ban_moi_nhat` :127, `la_ban_moi_hon` :141, `ma_thoat` :249 | *(không)* | Vị trí git HEAD. Trạng thái ổn định trên máy user là **detached HEAD tại tag** | `git fetch --tags` (mạng) và `git checkout --quiet <tag>` :215; đặt `GIT_TERMINAL_PROMPT=0`, `GIT_SSH_COMMAND='ssh -o BatchMode=yes'` :78-80 | Subprocess git, timeout 45 s (local) / 90 s (mạng); **không có khoá** — hai launcher khởi động cùng lúc đều có thể checkout | **HIGH** — AUD-184; chạy **trước mọi thứ khác** ở mỗi lần mở app |
| **sheet_delivery.py** | 256 | Giao hàng Sheets ngoài luồng: một thread riêng, backoff luỹ thừa, phân loại lỗi vĩnh viễn/tạm thời, khoá idempotency SHA-256 | `SheetDeliveryWorker` :115, `enqueue` :144, `start` :162, `stop` :172, `snapshot` :180, `tom_tat` :184, `khoa_giao_hang` :69, `phan_loai_loi` :57, `SheetDelivery` :93 | *(không — `sender` được inject; đó là thứ giữ nó sạch Streamlit)* | `_trang_thai` dict :137 — **chỉ trong RAM, không bao giờ prune** | Không I/O riêng; mọi I/O nằm trong `sender` được inject | Một daemon thread `sheet-delivery` :167-170 + `RLock`. `enqueue` dùng **blocking `Queue.put`** :155 — lời gọi chặn duy nhất giữa thread trong cả codebase | **MEDIUM** — AUD-123 (LIKELY)/AUD-148, AUD-126 |
| **toc_do_khop.py** | 253 | Ước lượng tỉ lệ tốc độ phát từ độ trôi tuyến tính của `align` theo thời gian video (Theil-Sen + refit bình phương tối thiểu trên inlier); dựng chuỗi filter ffmpeg và mã hoá hệ số vào tên file | `uoc_luong_toc_do` :159, `bo_loc_ffmpeg` :226, `ma_he_so` :242, `giai_ma_he_so` :247, `UocLuongTocDo` :68, `HO_TEMPO`/`HO_RESAMPLE` | *(không — chỉ `os.path.basename`)* | Không | **Không** — module thuần | Thuần | **LOW** |
| **don_dep.py** | 243 | GC theo tuổi/ngân sách cho cache tải và cho thư mục job quét mồ côi | `chon_can_xoa` :25, `don_kho_dem` :60, `don_job_quet` :162, `MucDem` :19 | *(không)* | Không — stateless, clock inject được qua `bay_gio` | **Xoá file** trong `data/downloads` và **rmtree** `data/scan_jobs/<uuid>`; mọi lỗi gom vào `ket_qua['loi']`, không raise | Không lock, không kiểm tra file đang dùng. Người gọi (`cli.py:214`, `watch.py:347`) không chồng lấn với quét **trong cùng process** | **MEDIUM** — AUD-164, AUD-167; không biết gì về `data/fingerprint_jobs` |
| **nhat_ky.py** | 184 | Tee `stdout`/`stderr` vào `ketqua/giamsat_<date>.log`, che cảnh báo cookie của yt-dlp, xoá log quá 30 ngày | `mo_nhat_ky` :122, `dong_nhat_ky` :157, `che_bi_mat` :27, `_GhiSongSong` :43 | *(không)* | Global module `_STDOUT_GOC`/`_STDERR_GOC`/`_FILE_LOG` | **Thay `sys.stdout`/`sys.stderr` cấp process** :152-153; xoá log cũ :84-119 | Không thread-safe; chỉ `cli.py watch --log` (:233) gọi, và đường đó đã bị `tool.lock` serialise | **MEDIUM** — AUD-166; lớp phòng thủ thứ hai chống rò cookie |
| **kiem_thoi_luong.py** | 184 | CLI đo thời lượng thật bằng ffprobe rồi điền `duration_media` vào `clips_meta.json` | `kiem_mot_kho` :65, `do_dai_media` :41, `hhmmss` :54, `main` :142, `TRUONG = "duration_media"` :38 | luu_tru; `engine` (muộn :155 — "nhập muộn để --help không phải nạp cả engine") | Không | Spawn ffprobe mỗi clip; chỉ ghi khi `--sua --that-su` :134-136 | Tuần tự, main thread; **không giữ `tool.lock`** | **MEDIUM** — AUD-067, AUD-087; ghi vào store bị snapshot che (AUD-081) |
| **dong_goi.py** | 162 | Zip source để gửi audit. Lọc theo **whitelist đuôi file** + denylist tên nhạy cảm | `nen_lay` :68, `la_file_nhay_cam` :60, `la_thu_muc_bo_qua` :44, `liet_ke_source` :91, `tao_goi` :106, `CAM`/`TU_KHOA_NHAY_CAM` :26-31, `DUOI_OK` :55 | *(không)* | Là nguồn sự thật duy nhất cho "file nào được rời máy này" — `dong_goi_may_chay` dùng lại | Ghi zip; xoá zip dở nếu có exception :125-131 | Đơn luồng | **MEDIUM** — AUD-181/AUD-221; docstring :5-7 hứa whitelist theo **file**, hiện thực là whitelist theo **đuôi** |
| **luu_tru.py** | 161 | Ghi JSON nguyên tử (`.bak` → `.tmp` → `fsync` → `os.replace`) + đọc có phục hồi (`.bak`, cách ly `.hong.<ts>`); `ten_file_hop_le` là sanitiser tên file duy nhất xử lý được DOS device name của Windows | `ghi_json_an_toan` :71, `doc_json_an_toan` :118, `ten_file_hop_le` :40, `LoiDuLieu` :15 | *(không)* | `_KHOA_THEO_DUONG_DAN` :63 — registry `RLock` theo abspath | Ghi `<path>`, `<path>.tmp`, `<path>.bak`, `<path>.hong.<ts>` | **RLock theo path, chỉ trong process.** Không có bảo vệ liên process; tên file tạm cố định `<path>.tmp` :79 dùng chung cho mọi writer | **HIGH** — AUD-161 (LIKELY), AUD-163, AUD-170; **fan-in 8 — rộng nhất cây** |
| **chap_nhan_khop.py** | 140 | Vị từ chấp nhận hai bậc. Bậc A = `hashes ≥ min_hash_floor` **và** `mật độ ≥ mat_do_bac_a` (:88-96); Bậc B = `ty_le ≥ 60` **và** `matched_s ≥ 20` **và** `mật độ ≥ 3` (:103) | `loc_chap_nhan` :129, `danh_gia_chap_nhan` :81, `mat_do_hash` :73, `KetQuaChapNhan` :63, `BAC_TUYET_DOI`/`BAC_PHU_CAO` | *(không)* | Không | **Không** — module thuần, không I/O, không phụ thuộc UI | Thuần | **LOW** — nhưng docstring :23 còn thiếu rào mật độ Bậc A (AUD-267) |
| **thiet_lap_may_phu.py** | 135 | Thiết lập một lần trên máy phụ sau khi giải nén: trỏ lại `thu_muc` của từng kho về `kho_meta/<Tên>`, rồi in checklist sẵn sàng | `sua_duong_dan_kho` :30, `kiem_tra` :59, `main` :103, `THU_MUC_META` | luu_tru | Ánh xạ đường dẫn kho trên máy đích | Ghi `data/khos.json` (nguyên tử, giữ `.bak`); exit 1 khi thiếu điều kiện cứng | Đơn luồng | **MEDIUM** — AUD-046, AUD-186; là module **duy nhất** có shape-guard cho registry (:34) |
| **dossier.py** | 127 | Model + renderer hồ sơ khiếu nại bản quyền Markdown | `dung_ho_so` :41, `render_markdown` :86, `HoSo` :29, `MucViPham` :14 | clip_metadata, **engine** (`import engine` :10 — vòng tròn, xem §3.1) | Không | **Không** — hàm thuần; `Engine.export_ho_so` mới ghi `ketqua/hoso_*.md` | Thuần, main thread | **HIGH** — AUD-201, AUD-202, AUD-210; là artefact gửi cho chủ sở hữu quyền |
| **khoa.py** | 124 | Khoá độc quyền liên process trên `data/tool.lock` bằng khoá OS thật (`msvcrt.locking` / `fcntl.flock`), ghi PID/thời điểm/tác vụ vào file cho thông báo | `KhoaTienTrinh` :42, `DangChayRoi` :12, `thong_tin_chu_khoa` :51 | *(không)* | Handle file đang mở + chuỗi mô tả chủ khoá | Tạo thư mục cha; ghi byte 1..N; **byte 0 là khoá, file không bao giờ bị xoá** | **Chính là primitive concurrency.** Non-blocking → raise ngay `DangChayRoi`. **Không reentrant trong cùng process** | **MEDIUM** — thiết kế đúng (kernel tự nhả khi process chết); rủi ro nằm ở chỗ **đường quét không dùng nó** (AUD-125/AUD-261) |
| **bang_ngang.py** | 121 | Dựng **đúng một dòng 34 ô** cho mỗi `ScanResult`; sở hữu `HEADER_NGANG` — hợp đồng đông cứng với bảng tính của người dùng | `HEADER_NGANG` :14-49, `SO_DOAN = 5` :12, `dung_dong_ngang` :69, `dinh_dang_doan` :61, `dinh_dang_ngay` :52 | clip_metadata, engine, publication_date | Không | **Không** — hàm thuần (:75). Nhưng gọi `datetime.now()` mỗi dòng :81 → không tất định | Thuần; chạy **trên worker thread quét** qua `app.sau_moi_video` :114-134 | **HIGH** — AUD-201, AUD-208; 34 cột phải khớp byte-for-byte với `kiem_header.py` và 2 bản Apps Script |
| **chia_watchlist.py** | 109 | Chia round-robin một watchlist thành N watchlist theo máy, để N máy có `lichsu.db` độc lập không quét trùng | `chia_muc` :37, `chia_watchlist` :47, `main` :61 | luu_tru | Không | Ghi `watchlist.<tiền-tố>N.json` bằng `json.dump` trần vào **thư mục làm việc hiện tại** :97-99 — **writer JSON duy nhất trong cây bỏ qua `luu_tru`**; chỉ khi có `--that-su` | Đơn luồng | **MEDIUM** — không nguyên tử, không `.bak`, khác mọi writer khác |
| **scan_ui.py** | 95 | Builder thuần cho DataFrame trạng thái quét theo video, khai báo schema chuỗi tường minh để PyArrow không phải đoán. Cố ý sạch Streamlit | `build_scan_status_dataframe` :67, `CHUA_CO = "—"`, `COT`, `TEN_TRANG_THAI_QUET`, `TEN_TRANG_THAI_SHEET` | *(không; pandas)* | Không — hàm thuần | Không | Bất khả tri về thread; gọi từ main thread `app.py:811-814` | **LOW** — mọi cột `astype("string")` kể cả frame rỗng (:95), khoá bởi tests/test_scan_ui_schema.py |
| **kiem_sheet.py** | 93 | Script chẩn đoán: dựng `ScanResult` giả, so header sheet thật với `HEADER_NGANG` từng ô, rồi **ghi một dòng test thật** mà người dùng phải tự xoá | *(script, không có API import được)* | bang_ngang, engine, sheets | Không | **Ghi mạng thật vào sheet của người dùng** :91 | Script, đơn luồng | **MEDIUM** — đường code duy nhất chạm mạng thật gọi được từ thư mục gốc |
| **kiem_ngang.py** | 77 | Script guard: kiểm độ rộng dòng == độ rộng header, rồi chạy `export_csv_ngang` **thật** và kiểm 34 ô | *(script)* | bang_ngang, engine | Không | **Dựng `Engine()` ở cấp module (:62)** → chạy DDL trên `lichsu.db` thật và ghi một CSV vào `ketqua/` không bao giờ dọn | Script | **MEDIUM** — AUD-209; guard tự ghi vào chính workspace nó bảo vệ |
| **cau_hinh.py** | 72 | Lưu/khôi phục cấu hình người dùng; áp JSON đã lưu lên một instance `Config` **tại chỗ** | `doc_cau_hinh` :29, `ghi_cau_hinh` :39, `ap_vao_config` :44, `lay_tu_config` :70, `GIA_TRI_GIAO_DIEN_MAC_DINH` :16-22 | luu_tru | Không (hàm thuần trên đường dẫn `data_dir`) | Ghi `data/cau_hinh.json` | Chỉ main thread trong thực tế | **HIGH** — `lay_tu_config` :70-71 serialise **mọi** field dataclass **không có allowlist**: đó là lý do `ytdlp_cookiefile` chỉ được chứa **đường dẫn** (engine.py:150) |
| **kiem_header.py** | 66 | Guard offline: `HEADER_NGANG` phải khớp từng ký tự với 34 tiêu đề lấy từ file Excel của người dùng | `CHUAN_33` :11-32, `COT_34`, `CHUAN` | bang_ngang (trong `try` :40) | Không | Chỉ stdout; exit 1 khi lệch | Script | **LOW** — guard đúng chuẩn: thuần, không ghi gì |
| **dung_lai.py** | 56 | Gộp tín hiệu OS + `engine.cancel_event` + file dừng thành **một vị từ `can_dung()` dính (sticky)** | `YeuCauDung` :11, `bat_tin_hieu` :20, `can_dung` :33, `dat` :42, `don_file_dung` :49 | *(không)* | `_da_dat` (bool sticky), `_so_tin_hieu` | Cài handler SIGINT/SIGTERM :28-31; tín hiệu thứ hai raise `KeyboardInterrupt`; xoá `data/DUNG` | Handler chạy main thread; `can_dung()` được poll bởi thread gọi. **`_da_dat` và file dừng là sticky — đó là lý do huỷ ở CLI/watch sống sót qua `cancel_event.clear()` của engine, còn GUI thì không** | **LOW** — `app.py` **không** import module này |
| **tests/** *(nhóm)* | 61 file / 14.034 dòng / 781 hàm `def test_` | Bộ test tự động. `pytest.ini:3` mặc định `-m "not slow"`; đúng **5** test `slow` (tests/test_integration.py:6,30,47 và tests/test_audfprint_progress_integration.py:12,52) là những test duy nhất chạy audfprint thật + `bin/ffmpeg.exe` thật | `tests/conftest.py`: fixture `bo_clip` :32, `engine` :53, helper `M()` :65 | engine và ~20 module khác | `tmp_path` per-test; `tmp_path_factory` cho WAV tổng hợp | Ghi tmp; các AppTest sinh daemon thread thật | Chỉ một fixture `autouse` trong cả bộ, phạm vi file (tests/test_nhat_ky.py:13). **Cách ly là quy ước, không được cưỡng chế** | **HIGH** — AUD-242, AUD-245; guard cấu trúc tốt nhất cây nằm ở tests/test_scan_thread_boundary.py:48-70 |
| **apps_script/** *(nhóm)* | 8 file `.gs` / 3.792 dòng + README.md | Phía Google Sheets: bản sao hợp đồng 34 cột, bản đồ cột theo TÊN với fallback theo vị trí, tô màu link đã quét, xuất hàng đã chọn, tự động hoá trigger | `File01`: `KETQUAQUET_COT_MAC_DINH` :75-110, `layCauTrucKetQuaQuet_` :319-330, `SO_COT_TOI_THIEU_DE_COI_LA_TIEU_DE = 3` :116. `File04`: `danhDauTrungLapTrongKetQuaQuet_`. `TOAN_BO_AppsScript.gs` = bản gộp 85 KB | *(SpreadsheetApp)* | Watermark `PropertiesService` cho `File05` | `File04` chỉ `setBackgrounds`/`setFontColors` — **không bao giờ ghi giá trị ô**, nên không xung đột ghi với exporter Python | Apps Script, một ngữ cảnh thực thi | **MEDIUM** — AUD-147, AUD-X20, AUD-X22, AUD-X24; hợp đồng 34 cột tồn tại ở **4 nơi** không có kiểm tra tự động Python↔JS |

---

## 2. Nhóm module theo tầng

Mỗi module thuộc **đúng một** tầng. Số trong ngoặc là LOC.

### 2.1 Entry points — 3 module, 1.921 dòng

`app.py` (1508) · `cli.py` (318) · `scan_ui.py` (95)

Hai cửa vào duy nhất của sản phẩm. `app.py` là module **duy nhất** `import streamlit`
(:18) và điều đó được cưỡng chế bằng test cấu trúc (tests/test_scan_thread_boundary.py:48-57).
`scan_ui.py` ở đây vì nó chỉ phục vụ màn hình tiến độ của `app.py`, nhưng cố ý được viết
sạch Streamlit để test được không cần AppTest.

Điều một người mới hay nhầm: `cli.py` **không** là wrapper mỏng của `app.py`. Hai đường có
ngữ nghĩa khác nhau ở ba chỗ — huỷ (CLI dùng `dung_lai`, GUI không), khoá (`watch` giữ
`tool.lock`, GUI không), và cấu hình (`cli.py:183` ghi đè `ncores` vô điều kiện).

### 2.2 Orchestration & job control — 5 module, 4.550 dòng

`engine.py` (3453) · `watch.py` (517) · `scan_jobs.py` (390) · `khoa.py` (124) · `dung_lai.py` (56)

`engine.py` là hub: nó import 13 module nội bộ và bị 8 module import lại. Ba lớp điều khiển
job bao quanh nó, mỗi lớp cho một ngữ cảnh: `scan_jobs.py` (batch trong UI, thread),
`watch.py` (một lượt giám sát, process, giữ khoá), `dung_lai.py` (vị từ dừng sticky cho CLI).
`khoa.py` là primitive loại trừ liên process duy nhất.

Ranh giới đáng nhớ: `Engine.save_job` chạy **trước** callback `on_video`
(engine.py:3142/:3221 rồi :3252-3258) — nên một lỗi giao hàng Sheets không bao giờ làm mất
kết quả quét.

### 2.3 Matching — 3 module, 680 dòng

`chan_doan_quet.py` (287) · `toc_do_khop.py` (253) · `chap_nhan_khop.py` (140)

Cả ba đều **thuần, không I/O, không phụ thuộc UI** — đây là phần dễ đọc và dễ sửa nhất của
hệ. Nửa còn lại của tầng matching nằm trong `engine.py` (`_match_chunks` :2283, `_merge`
:2395, `_gan_chi_so` :2535, `_chon_loc` :2545, `_quet_tho` :2735, `_quet_da_toc_do` :2944)
và **không** tách ra module riêng.

Thứ tự thực: audfprint → parse (`_match_chunks`) → lọc & gộp (`_merge`) → gán `ty_le`/`vùng`
(`_gan_chi_so`) → chấp nhận (`chap_nhan_khop.loc_chap_nhan`) → chọn Top-N (`_chon_loc`) →
chốt phễu (`chan_doan_quet.chot_giai_doan`).

### 2.4 Fingerprint — 3 module, 1.213 dòng

`fingerprint_progress.py` (593) · `audfprint_progress_runner.py` (340) · `process_runner.py` (280)

`audfprint_progress_runner.py` là lớp duy nhất giữ cho `audfprint-master/` không bị sửa: nó
cài 3 monkey-patch lúc chạy (:307-318) thay vì vá source vendor. `process_runner.py` giám sát
subprocess cho **cả** đường build lẫn đường match. `fingerprint_progress.py` là **mẫu tham
chiếu** cho job control — `scan_jobs.py` khai trong docstring (:2-6) rằng nó tái dùng pattern
này, nhưng chỉ tái dùng ranh giới thread/snapshot, không tái dùng phần drain queue, validate
phase, hay phát hiện worker chết.

### 2.5 Metadata — 2 module, 1.352 dòng

`clip_metadata.py` (1058) · `publication_date.py` (294)

Cả hai đều thuần và chỉ dùng stdlib. `clip_metadata.py` sở hữu chuỗi phân giải 7 mức từ
**tên file clip** sang danh tính YouTube; `publication_date.py` sở hữu chuỗi ưu tiên ngày
đăng và formatter DD/MM/YYYY duy nhất.

Cần biết ngay: **writer của `clips_meta.json` không nằm ở tầng này.** Nó là `channel.py`
(tầng Integration), cộng hai CLI sửa chữa `kiem_ngay_dang.py` và `kiem_thoi_luong.py` (tầng
Diagnostics). Còn snapshot `data/metadata/kho_<slug>.json` do `engine.py` ghi (:1400, :1621)
và được đăng ký ở **priority 0**, tức cao hơn `clips_meta.json` ở priority 10
(engine.py:1121-1124).

### 2.6 Persistence — 4 module, 660 dòng

`luu_tru.py` (161) · `don_dep.py` (243) · `nhat_ky.py` (184) · `cau_hinh.py` (72)

`luu_tru.py` có **fan-in 8** — cao nhất cây (cau_hinh, channel, chia_watchlist,
dong_goi_may_chay, engine, kiem_thoi_luong, thiet_lap_may_phu, watch). Mọi JSON store trong
dự án đi qua nó, trừ hai ngoại lệ có chủ đích: `chia_watchlist.py:97-99` (`json.dump` trần)
và `ytdlp_chung.CauHinhMang.tu_file_cau_hinh` :299-306 (`io.open` + `json.load` trần).

Nửa SQLite của tầng này nằm trong `engine.py` (`_init_sqlite` :872-893, `save_job` :3273,
`ids_da_quet` :3295) và không có module riêng.

### 2.7 Export — 5 module, 1.558 dòng

`danh_sach_video.py` (647) · `sheets.py` (407) · `sheet_delivery.py` (256) ·
`dossier.py` (127) · `bang_ngang.py` (121)

Bốn định dạng báo cáo, ba độ rộng cố định: 16 cột (`Engine.HEADER` engine.py:3317-3322),
34 cột (`bang_ngang.HEADER_NGANG` :14-49), 2 cột (`danh_sach_video.HEADER` :46), và Markdown
hồ sơ (`dossier.render_markdown` :86).

Hai ngữ nghĩa ghi Sheets khác hẳn nhau: `SheetsExporter.append` :197 (cộng thêm, không tự
retry) và `SheetsExporter.ghi_de` :253 (resize + update, **phá huỷ**, idempotent về kết quả
nhưng không nguyên tử về tiến trình). `danh_sach_video.py` là consumer duy nhất của `ghi_de`.

### 2.8 Integration — 2 module, 1.207 dòng

`channel.py` (687) · `ytdlp_chung.py` (520)

`ytdlp_chung.py` là **cổng duy nhất** ra yt-dlp: cả 6 điểm dựng `YoutubeDL` trong cây
(engine.py:1480, :2014, :2127; channel.py:377, :419, :490) đều lấy dict tuỳ chọn từ
`CauHinhMang.tuy_chon` :339. `channel.py` là gateway đồng bộ kho gốc và, như đã nói ở §2.5,
là writer chính của `clips_meta.json`.

Không có lệnh gọi yt-dlp qua CLI ở đâu cả; `subprocess` chỉ dùng cho ffmpeg, ffprobe,
audfprint và git.

### 2.9 Operations — 5 module, 962 dòng

`cap_nhat.py` (267) · `dong_goi_may_chay.py` (289) · `dong_goi.py` (162) ·
`thiet_lap_may_phu.py` (135) · `chia_watchlist.py` (109)

Vòng đời triển khai: đóng gói (`dong_goi.py` cho audit, `dong_goi_may_chay.py` cho máy phụ),
thiết lập máy đích (`thiet_lap_may_phu.py`), chia tải giám sát (`chia_watchlist.py`), và tự
cập nhật (`cap_nhat.py`).

`cap_nhat.py` thao tác trên **thư mục cha** (`Tool_Quet/`), không phải `TimClipPro/` —
`thu_muc_repo` :97-104 chạy `git rev-parse --show-toplevel` chính vì lý do đó. Nó chạy trước
mọi thứ khác ở mỗi lần khởi động GUI/máy phụ.

### 2.10 Diagnostics & helpers — 6 module, 1.081 dòng

`kiem_metadata_kho.py` (338) · `kiem_ngay_dang.py` (323) · `kiem_thoi_luong.py` (184) ·
`kiem_sheet.py` (93) · `kiem_ngang.py` (77) · `kiem_header.py` (66)

Sáu script chạy tay. **Không cái nào được pytest thu thập** (`pytest.ini:2` đặt
`testpaths = tests`), nên chúng không có test và không chạy trong CI.

Ba mức tác dụng phụ rất khác nhau, cần phân biệt trước khi chạy:

| Script | Tác dụng phụ |
|---|---|
| `kiem_header.py` | Thuần — chỉ so chuỗi và in |
| `kiem_metadata_kho.py` | Chỉ đọc theo mặc định; mở `lichsu.db` bằng URI `?mode=ro&immutable=1` :82 |
| `kiem_ngang.py` | Dựng `Engine()` **ở cấp module** :62 → DDL trên `lichsu.db` thật + ghi CSV vào `ketqua/` |
| `kiem_thoi_luong.py` | Ghi `clips_meta.json` khi `--sua --that-su` |
| `kiem_ngay_dang.py` | Ghi `clips_meta.json` + gọi mạng khi `--repair-network --apply` |
| `kiem_sheet.py` | **Ghi một dòng thật lên Google Sheet của người dùng** :91 |

---

## 3. Call-graph highlights

Xếp hạng theo tiêu chí đã nêu: nhãn HIGH ∩ mật độ finding CONFIRMED ∩ fan-in. Á quân sát
nút — `luu_tru.py` (fan-in 8, rộng nhất cây) và `bang_ngang.py` (chủ hợp đồng 34 cột đông
cứng) — nên đọc kèm dù không nằm trong 8.

### 3.1 `engine.py` — HIGH

**Ai gọi nó** (import mức module, đã kiểm chứng): `app.py:25` · `cli.py:25` ·
`bang_ngang.py:8` · `dossier.py:10` · `kiem_metadata_kho.py:19` · `kiem_ngang.py:10` ·
`kiem_sheet.py:23` · `kiem_thoi_luong.py:155` (muộn). `watch.py` **không** import engine —
nó nhận object qua tham số.

**Nó gọi gì**: 13 module nội bộ (channel, cau_hinh, ytdlp_chung, dossier, chan_doan_quet,
chap_nhan_khop, toc_do_khop, clip_metadata, fingerprint_progress, khoa, luu_tru,
process_runner, publication_date).

**Hai vòng import cần biết trước khi refactor:**

1. `engine.py:48 import dossier` ↔ `dossier.py:10 import engine`. **Vòng thật.** Nó chạy
   được vì `dossier` dùng dạng `import engine` (bind module object) và chỉ chạm thuộc tính
   lúc gọi hàm: `engine.ScanResult` :42, `engine.Engine.link_moc` :60, `engine.hhmmss`
   :78, :100. Đổi sang `from engine import ...` ở `dossier.py` sẽ làm vỡ import ngay.
2. `bang_ngang.py:8 from engine import Engine, hhmmss` (mức module) ↔ `engine.py:3387,
   :3398 import bang_ngang` (**muộn, trong hàm**). Vòng được cắt bằng import muộn. Nâng hai
   import đó lên đầu file `engine.py` sẽ làm vỡ import.

**Chuỗi gọi chính (một URL YouTube → báo cáo):**

```
cli.py:277 / app.py:138 → scan_jobs.py:263
  Engine.scan_iter                    engine.py:3224
    Engine.scan_youtube               engine.py:3145
      Engine.youtube_info             engine.py:2009   → ytdlp_chung.tuy_chon :339 (mạng)
      Engine._gioi_han_tai            engine.py:2790
      Engine.download_audio           engine.py:2054   → ytdlp_chung.thu_tung_client :463 (mạng)
      Engine.scan_media               engine.py:3043
        Engine.scan_workspace         engine.py:2219   (data/scan_jobs/<uuid4>)
        Engine._cut_chunks            engine.py:2236   → ffmpeg
        Engine._quet_tho              engine.py:2735
          Engine._match_chunks        engine.py:2283
            Engine._run_stream        engine.py:914
              process_runner.run_observed_process  process_runner.py:82  → audfprint
        Engine._quet_da_toc_do        engine.py:2944   → toc_do_khop.uoc_luong_toc_do :159
        Engine._merge                 engine.py:2395   → Engine.db_clips :1007 (đọc .pklz)
        Engine._gan_chi_so            engine.py:2535
        Engine._chon_loc              engine.py:2545   → chap_nhan_khop.loc_chap_nhan :129
        Engine._chot_chan_doan        engine.py:2636   → chan_doan_quet.chot_giai_doan :134
      Engine.save_job                 engine.py:3273   (SQLite — CHẠY TRƯỚC on_video)
    on_video callback                 engine.py:3252-3258 (exception bị nuốt có chủ đích)
```

**Chuỗi xuất báo cáo** (không có lời gọi mạng nào — `clip_metadata.py` không import thư
viện mạng nào, :10-22):

```
Engine.to_rows        engine.py:3344 → clip_metadata_resolver :1163 → resolve :831
Engine.to_rows_ngang  engine.py:3385 → bang_ngang.dung_dong_ngang  bang_ngang.py:69
Engine.export_ho_so   engine.py:3420 → dossier.dung_ho_so          dossier.py:41
```

Cả ba đều dựng resolver **đúng một lần mỗi lần gọi**, không phải mỗi match.

### 3.2 `app.py` — HIGH

**Ai gọi nó**: không module Python nào. Chỉ `ChayTool.bat:46` (`streamlit run app.py`) và
13 test qua `AppTest.from_file` (tests/test_app.py:28 và ba file `test_app_*` khác).

**Nó gọi gì**: 12 module nội bộ. Bốn closure của nó chạy trên worker thread:

```
app.chay_quet                    app.py:95
  ScanLaunchConfig(...)          app.py:105-109 → scan_jobs.py:66   (snapshot main-thread)
  SheetDeliveryWorker.start      app.py:111     → sheet_delivery.py:162
  ScanJobController.start        app.py:138     → scan_jobs.py:169
    └─ [worker thread] sau_moi_video           app.py:113
         Engine.to_rows_ngang    engine.py:3385
         khoa_giao_hang          sheet_delivery.py:69
         worker.enqueue          sheet_delivery.py:144   (blocking put :155)
         scan_controller.ghi_nhan_giao_hang    scan_jobs.py:329
```

Chi tiết dễ bỏ sót: sidebar (`app.py:461-681`) nằm **phía trên** màn hình tiến độ
(`app.py:688`), nên nó được render lại ~1,3 lần/giây suốt cả job, trong khi các tab
(`app.py:944`) thì không bao giờ tới vì `st.rerun()` ở :836 raise trước. Đó là lý do
`eng.use_kho` ở :488 và các widget tinh chỉnh ở :503-565 vẫn sống giữa lúc quét (AUD-122).

### 3.3 `clip_metadata.py` — HIGH

**Ai gọi nó** (fan-in 7): `engine.py:63` · `app.py:23` · `cli.py:23` · `channel.py:27` ·
`danh_sach_video.py:35` · `bang_ngang.py:7` · `dossier.py:9` · `kiem_metadata_kho.py:14` ·
`kiem_ngay_dang.py:33`.

**Nó gọi gì**: không gì cả. Chỉ stdlib (:10-22). Đây là lá của đồ thị phụ thuộc.

**Ba consumer đường báo cáo đều gọi cùng một cách — một tham số:**

```
engine.py:3359      mt   = resolver.resolve(m.clip)
bang_ngang.py:102   meta = resolver.resolve(matches[i].clip)
dossier.py:53       thong_tin = resolver.resolve(m.clip)
```

`Match.clip` là **basename trần** (`os.path.basename` tại engine.py:2492 → `Match(clip=...)`
:2512), cùng khoá với `db_clips` (engine.py:1049) và với key `clips_meta.json`
(channel.py:592). Đường audit thì gọi hai tham số (`resolve(name, path)`, engine.py:1351).

**Nguồn metadata và thứ tự ưu tiên** (engine.py:1109-1138 `_metadata_source_candidates`):

| Priority | Nguồn | Ghi ở đâu |
|---|---|---|
| 0 | `data/metadata/kho_<slug>.json` (snapshot) | engine.py:1400, :1621 |
| 1 | snapshot `.bak` | engine.py:1188-1192 |
| 10 | `<kho>/clips_meta.json` (live) | channel.py:182, kiem_ngay_dang.py:229, kiem_thoi_luong.py:135 |
| 20+ | `clips_meta.json` cạnh thư mục clip trong DB | — |
| 100 | `data/clips_meta.json` (chỉ khi kho tên `""` hoặc `"Kho mặc định"`) | — |

Quy tắc gộp ở `clip_metadata.py:549-558`: sắp theo `(_entry_quality, priority, source_file,
key)`, giữ giá trị non-empty của bản thắng, các nguồn sau chỉ được điền ô **trống**
(:586-590). Đây là cơ chế đứng sau AUD-061/AUD-081.

### 3.4 `channel.py` — HIGH

**Ai gọi nó** (fan-in 5): `app.py:30` (5 điểm dựng `ChannelSync`: :1007, :1014, :1031,
:1051, :1070) · `cli.py:22` (:169, :244) · `watch.py:10` (qua `_lister_theo_cau_hinh` :264)
· `kiem_ngay_dang.py:32` (:65) · `danh_sach_video.py:34` (chỉ hằng `AUDIO_EXT`) ·
`engine.py:45` (chỉ 2 hàm: `ngay_dang_tu_info` :1491, `lam_sach_ten` :3436 — **không** dùng
`ChannelSync`).

**Nó gọi gì**: `clip_metadata`, `luu_tru`, `publication_date`, `ytdlp_chung`; yt-dlp và
ffmpeg/ffprobe qua subprocess.

```
ChannelSync.sync              channel.py:557
  list_channel                channel.py:381  → yt-dlp (extract_flat, 1 request/kênh)
  _tai_va_nen                 channel.py:~523
    _tai_thu_tung_client      channel.py:~509 → ytdlp_chung.thu_tung_client :463
                                              → ytdlp_chung.chay_kem_duong_lui_cookie :393
    ffmpeg (transcode opus)   channel.py:543
  do_dai_media                channel.py:69   → ffprobe :81
  save_meta                   channel.py:181  → luu_tru.ghi_json_an_toan :71
```

Bất đối xứng đáng chú ý cho người sửa: `sync` nhận `cancel_check` (:557, kiểm ở :584) còn
`va_metadata` (:216) thì **không có tham số cancel nào** và không có lệnh kiểm tra nào
trong vòng lặp — `grep -n "cancel" channel.py` chỉ trả về :559 và :584.

### 3.5 `watch.py` — HIGH

**Ai gọi nó**: chỉ `cli.py:21` (nhánh `watch`). `app.py` **không bao giờ import watch** —
không có UI giám sát nào.

**Nó gọi gì**: `bang_ngang`, `channel`, `don_dep`, `khoa`, `luu_tru`, `sheets`. Nó nhận
`Engine` qua tham số, không import.

```
cli.py:86 chay_giam_sat            watch.py:270
  KhoaTienTrinh(data/tool.lock)    watch.py:287-290   ← giữ suốt cả lượt
  engine.use_kho(wl.kho)           watch.py:371       → engine.py:832 (GHI khos.json)
  lay_ung_vien                     watch.py:205       → channel.list_channel (cửa sổ 50 video, :208)
  id_da_quet                       watch.py:174       → Engine.ids_da_quet engine.py:3295
  loc_can_quet                     watch.py:190       (hàm thuần)
  ├─ engine.scan_youtube           watch.py:459
  ├─ day_tung_phan                 watch.py:417       → SheetsExporter.append sheets.py:197
  └─ dung_neu_duoc_yeu_cau         watch.py:437-448   → YeuCauDung.can_dung dung_lai.py:33
  quét bù cuối lượt                watch.py:497-512   (retry duy nhất tồn tại)
  export_csv_ngang                 watch.py:487-495
  finally: don_kho_dem/don_job_quet watch.py:326-356
```

`chay_giam_sat` là **một lượt**, không có vòng lặp/sleep/scheduler nào trong file — nhịp
lặp do Windows Task Scheduler gọi `ChayMayPhu.bat` / `GiamSat.bat` quyết định.

### 3.6 `sheets.py` — HIGH

**Ai gọi nó** (fan-in 4): `app.py:31` (:224, :636, :1333) · `watch.py:14` (:398) ·
`danh_sach_video.py:41` (:626) · `kiem_sheet.py:24` (:60) · `scan_jobs.py:85` (muộn, chỉ
`_lay_sheet_id`).

**Nó gọi gì**: không module nội bộ nào. `gspread` + `google-auth` (import muộn).

```
[main thread]  app.day_len_sheets  app.py:232 → tao_sheets_exporter :222 → append :197
[worker]       sender lambda       app.py:84-85 → tao_sheets_exporter :222 → append :197
[watch proc]   day_tung_phan       watch.py:417 → append :197
[main thread]  day_len_sheet       danh_sach_video.py:598 → ghi_de :253 (PHÁ HUỶ)
```

Hai đường đầu **chia sẻ cùng một entry `_CACHE`** vì khoá cache (`sheets.py:139-145`) gồm
key path, mtime, sheet_id và worksheet — mà cả hai đều dùng `worksheet` mặc định
`"KetQuaQuet"` (:95). Đó là cơ sở của AUD-X07 (LIKELY).

`append` cố ý **không tự retry** (:245-250): một lần ghi có thể đã tới Google rồi, thử lại
sẽ tạo dòng trùng. Việc retry thuộc về `SheetDeliveryWorker` — nhưng `watch.py` không dùng
worker đó.

### 3.7 `ytdlp_chung.py` — HIGH

**Ai gọi nó** (fan-in 4): `engine.py:47` · `app.py:24` · `cli.py:26` · `channel.py:30`.

**Nó gọi gì**: không gì (yt-dlp import muộn ở `client_khong_ho_tro_cookie` :122).

**Bất biến quan trọng nhất của module** — cả 6 điểm dựng `YoutubeDL` trong cây đều đi qua
`CauHinhMang.tuy_chon` :339:

| Điểm dựng | Mục đích |
|---|---|
| engine.py:1480 | fetcher mạng của `va_metadata_thieu` |
| engine.py:2014 | `youtube_info` — metadata video vi phạm |
| engine.py:2127 | `download_audio` |
| channel.py:377 | `lay_info_video` |
| channel.py:419 | `list_channel` |
| channel.py:490 | `_tai_thu_tung_client` |

Hai lớp fallback lồng nhau, thứ tự **cố ý**: cookie bọc ngoài, player-client bên trong
(engine.py:2163-2166, channel.py:515-518) — vì cookie chết làm hỏng mọi client, nên phải
vét hết vòng client trước.

```
chay_kem_duong_lui_cookie   ytdlp_chung.py:393   ← lớp ngoài (bỏ cookie, thử lại 1 lần)
  thu_tung_client           ytdlp_chung.py:463   ← lớp trong (lặp qua player client)
    tuy_chon                ytdlp_chung.py:339   ← dựng dict, đặt socket_timeout :349
      kiem_tra_file_cookie  ytdlp_chung.py:192   ← validate TRƯỚC khi yt-dlp mở file
```

### 3.8 `scan_jobs.py` — HIGH

**Ai gọi nó**: chỉ `app.py:27`.

**Nó gọi gì**: không module nội bộ ở mức file; `sheets._lay_sheet_id` muộn ở :85. Nó nhận
`engine` theo kiểu duck-typing (chỉ cần `scan_iter`, `cancel`, `cancel_event`).

```
app.py:138  ScanJobController.start      scan_jobs.py:169
              engine.cancel_event.clear() scan_jobs.py:193
              Thread(target=self._chay)   scan_jobs.py:198-204   ← daemon "scan-<8hex>"
                _chay                     scan_jobs.py:233
                  engine.scan_iter        engine.py:3224
                    tien_do closure       scan_jobs.py:~240 → doan_phase :52
                    sau_moi_video closure scan_jobs.py:258
                      _hoan_tat_video     scan_jobs.py:303
                      on_result           → app.py:113
app.py:784  snapshot                      scan_jobs.py:344  ← main thread poll
app.py:824  cancel                        scan_jobs.py:207  → engine.cancel()
```

Cần biết khi sửa: `doan_phase` :52 **suy phase từ chuỗi tiếng Việt** mà engine phát ra, và
`_tach_chi_so` :287-294 parse tiền tố `"[i/n] "` mà `scan_iter` chèn ở engine.py:3246. Đổi
định dạng chuỗi tiến độ của engine sẽ làm UI im lặng ngừng theo dõi video nào đang chạy —
mà không có test nào bắt.

---

## 4. Đọc file nào trước

Thứ tự cho người chưa từng thấy repo này. Mỗi bước một lý do; tổng ~2.500 dòng cho 8 bước
đầu, đủ để hiểu toàn bộ hình dạng hệ thống trước khi mở `engine.py`.

**Giai đoạn 1 — Hợp đồng và luật chơi (đọc trước khi mở bất kỳ file `.py` nào)**

| # | File | Lý do |
|---|---|---|
| 1 | `CLAUDE.md` | Chứa 25 phát biểu RULE/INVARIANT/CẤM và 15 post-mortem đánh số — là tài liệu **duy nhất** phủ ~6 commit gần nhất. Đọc mục 1–5 và mục 15. |
| 2 | `.github/copilot-instructions.md` | 30 dòng, mọi khẳng định đã kiểm chứng đúng với source. Năm cái "bẫy" ở đây là năm cách nhanh nhất để làm vỡ hệ thống. |
| 3 | `docs/SYSTEM_OVERVIEW.md` | Định hướng kiến trúc — **nhưng viết từ điểm nhìn audit 2026-08-06**, trộn phát biểu "ban đầu" với hiện trạng; đọc để lấy hình dạng, không lấy chi tiết. |

**Giai đoạn 2 — Các module thuần, dễ đọc, nơi logic lõi thật sự sống**

| # | File | LOC | Lý do |
|---|---|---|---|
| 4 | `chap_nhan_khop.py` | 140 | Toàn bộ luật "bằng chứng này có đủ mạnh không" gói trong một hàm thuần (:81-126). Đọc xong là hiểu tiêu chuẩn của sản phẩm. |
| 5 | `chan_doan_quet.py` | 287 | Phễu phát hiện. Nó liệt kê **mọi tầng có thể làm mất kết quả** (:134-151) — tức là mục lục ngược của pipeline. |
| 6 | `publication_date.py` | 294 | Ví dụ mẫu mực về cách dự án xử lý một trường dữ liệu: nguồn sự thật duy nhất, chuỗi ưu tiên tường minh, provenance, một formatter. |
| 7 | `bang_ngang.py` | 121 | Sản phẩm cuối cùng người dùng nhìn thấy — 34 cột. Ngắn, thuần, và cho biết chính xác báo cáo cần những gì. |

**Giai đoạn 3 — Hạ tầng dữ liệu (đọc trước `engine.py`, vì `engine.py` giả định chúng)**

| # | File | LOC | Lý do |
|---|---|---|---|
| 8 | `luu_tru.py` | 161 | Fan-in 8. Mọi JSON store đi qua đây. Hiểu `.bak`/`.tmp`/`.hong` trước là hiểu được toàn bộ hành vi phục hồi. |
| 9 | `khoa.py` | 124 | Primitive loại trừ liên process duy nhất. Ngắn, và giải thích tại sao khoá không cần dọn sau khi crash. |
| 10 | `clip_metadata.py` (chỉ :1-200 và :831-960) | ~330 | Chuỗi phân giải 7 mức từ tên file sang danh tính YouTube. Đây là **khoá join của cả hệ** — đọc `resolve` :831 rồi mới đọc phần index. |

**Giai đoạn 4 — Điều phối**

| # | File | LOC | Lý do |
|---|---|---|---|
| 11 | `process_runner.py` | 280 | Cách dự án chạy và huỷ subprocess. Đọc trước `engine.py` để không phải dừng lại giữa chừng ở `_run_stream`. |
| 12 | `scan_jobs.py` | 390 | Ranh giới thread của UI, và mẫu snapshot bất biến mà cả hai controller dùng. |
| 13 | `fingerprint_progress.py` | 593 | Bản tham chiếu của mẫu job-control (drain queue, validate phase, worker liveness) mà `scan_jobs.py` chỉ tái dùng một nửa. |

**Giai đoạn 5 — `engine.py`, theo lát cắt**

Đừng đọc tuần tự 3.453 dòng. Đọc theo bốn lát, mỗi lát là một câu hỏi:

| # | Lát | Dòng | Câu hỏi nó trả lời |
|---|---|---|---|
| 14 | `Config` + `Match` + `ScanResult` | :105-397 | Hệ thống có những tham số nào, và một kết quả quét gồm những trường gì. |
| 15 | Vòng đời quét | :3043-3264 (`scan_media`, `scan_youtube`, `scan_iter`) | Một video đi từ URL tới `ScanResult` như thế nào. |
| 16 | Lõi matching | :2283-2628 (`_match_chunks`, `_merge`, `_gan_chi_so`, `_chon_loc`) | Từ output audfprint tới danh sách Top-N. |
| 17 | Tầng metadata + xuất báo cáo | :1109-1223 và :3317-3453 | Nguồn metadata nào thắng, và ba định dạng báo cáo dựng ra sao. |

**Giai đoạn 6 — Cửa vào và mạng**

| # | File | LOC | Lý do |
|---|---|---|---|
| 18 | `cli.py` | 318 | Cửa vào nhỏ hơn và trung thực hơn `app.py`; 10 lệnh ở :104-116 là bản đồ tính năng đầy đủ. |
| 19 | `ytdlp_chung.py` | 520 | Toàn bộ chính sách mạng: cookie, pacing, fallback, dịch lỗi. Một chỗ duy nhất. |
| 20 | `channel.py` | 687 | Writer của kho gốc và của `clips_meta.json`. Đọc `_ten_file` :465-469 kỹ — tên file đó là khoá join của cả hệ. |
| 21 | `app.py` | 1508 | Để cuối. Đọc theo thứ tự: bootstrap :41-92 → `chay_quet` :95-144 → màn hình tiến độ :688-836 → tabs :944+. |

**Giai đoạn 7 — Tuỳ mục tiêu**

| Nếu bạn sẽ làm việc với… | Đọc |
|---|---|
| Kho vân tay / audfprint | `audfprint_progress_runner.py`, rồi `engine.py:1646-1963` |
| Google Sheets | `sheets.py`, `sheet_delivery.py`, `apps_script/README.md` (chứa post-mortem sự cố mất hàng tiêu đề), `apps_script/File01_CauHinh_TienIch.gs` |
| Giám sát không người trực | `watch.py`, `dung_lai.py`, `ChayMayPhu.bat`, `GiamSat.bat` |
| Triển khai / đóng gói | `dong_goi.py` → `dong_goi_may_chay.py` → `thiet_lap_may_phu.py` → `cap_nhat.py` |
| Kiểm thử | `pytest.ini`, `tests/conftest.py`, rồi `tests/test_scan_thread_boundary.py` (guard cấu trúc tốt nhất trong cây) |

### 4.1 Bốn thứ cần biết trước khi sửa bất cứ gì

Không phải finding — là đặc tính cấu trúc mà một người mới rất dễ vi phạm trong ngày đầu.

1. **Khoá join của cả hệ là basename tên file clip**, không phải video ID.
   `Match.clip` (engine.py:2492), `db_clips()["ten"]` (engine.py:1049) và key
   `clips_meta.json` (channel.py:592) đều là `os.path.basename` của cùng một chuỗi. Đổi cách
   sinh tên file ở `channel.py:465-469` là re-key toàn bộ hệ thống.

2. **Có hai vòng import và cả hai đang được cắt bằng thủ thuật** — xem §3.1. Nâng một import
   muộn lên đầu file, hoặc đổi `import engine` thành `from engine import ...` trong
   `dossier.py`, sẽ làm vỡ import ngay lập tức.

3. **`cau_hinh.lay_tu_config` :70-71 serialise MỌI field của `Config` và không có
   allowlist.** Vì vậy không được thêm field chứa giá trị bí mật vào `Config` — đó là lý do
   `ytdlp_cookiefile` chỉ chứa **đường dẫn** (engine.py:150), không phải nội dung.

4. **Hợp đồng 34 cột tồn tại ở bốn nơi và không có kiểm tra tự động nào nối Python với
   Apps Script**: `bang_ngang.HEADER_NGANG` :14-49, `kiem_header.CHUAN_33` :11-32,
   `apps_script/File01_CauHinh_TienIch.gs:75-110`, và bản sao trong
   `apps_script/TOAN_BO_AppsScript.gs`. `kiem_header.py` chỉ so bản Python với một danh sách
   literal hard-code — nó **không đọc file `.gs` nào**.

### 4.2 Ba câu hỏi thiết kế đang mở

Nêu ở đây vì chúng chặn việc mở rộng ở các tầng tương ứng, và người mới sẽ gặp chúng trong
tuần đầu. Đây là **quyết định sản phẩm chưa có chủ**, không phải bug cần vá ngay.

1. **Store nào là nguồn sự thật cho metadata clip gốc?** Snapshot ở priority 0
   (engine.py:1122) hay `clips_meta.json` ở priority 10 (engine.py:1124)? Ba công cụ sửa
   chữa ghi vào store priority 10; một công cụ (`va_metadata_thieu`) ghi vào store priority
   0. Thứ tự hiện tại được test khoá lại (tests/test_clip_metadata.py:229-266), nên đổi
   precedence là đổi cả test đó. Xem AUD-061/AUD-081.

2. **"Dừng lại" phải có nghĩa gì với một batch?** Đường CLI/watch dừng được nhờ vị từ sticky
   `YeuCauDung` (dung_lai.py:35-40, khoá bởi tests/test_dung_lai.py:92-134); đường GUI thì
   không, vì `scan_iter` không kiểm tra giữa các video (engine.py:3244-3251) và mỗi
   `scan_youtube` xoá cờ ngay đầu (engine.py:3149). Sửa mà không hiểu bất đối xứng này sẽ
   làm hồi quy đường `watch`. Xem AUD-001/AUD-121.

3. **Đường quét có được miễn `data/tool.lock` không?** `CLAUDE.md:78-80` phát biểu bất biến
   này là tuyệt đối; `scan_media` (engine.py:3043) đọc `.pklz` và ghi `lichsu.db` mà không
   giữ khoá nào — bốn điểm giữ khoá duy nhất là engine.py:1436, :1495, :1690 và watch.py:287.
   `KhoaTienTrinh` không reentrant (khoa.py:20, :33), nên bọc `scan_media` bằng khoá sẽ
   deadlock `watch.py:459`. Hoặc sửa code, hoặc sửa doc — hiện tại một bất biến đã viết ra
   đang sai. Xem AUD-125/AUD-261.
