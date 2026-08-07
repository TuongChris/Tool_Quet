# CLAUDE_VALIDATION_REPORT — Kết quả kiểm chứng đã chạy

Ngày: 2026-08-06 · Môi trường: `.venv-claude` (Python 3.14.6, `pip check` sạch)

Phân tích nguyên nhân nằm ở [CLAUDE_AUDIT_REPORT.md](CLAUDE_AUDIT_REPORT.md).
Tài liệu này chỉ liệt kê **lệnh đã chạy và kết quả quan sát được**.

---

## 1. Dựng môi trường

```powershell
& "C:\Users\Administrator\AppData\Local\Python\pythoncore-3.14-64\python.exe" -m venv .venv-claude
& ".\.venv-claude\Scripts\python.exe" -m pip install -r requirements-dev.txt
& ".\.venv-claude\Scripts\python.exe" -m pip check
```

| Kiểm tra | Kết quả |
| --- | --- |
| Python | 3.14.6 (máy **không có** 3.12: `py -0p` chỉ có 3.14) |
| `pip check` | `No broken requirements found.` |
| `.venv-claude` được ignore | ✅ đã thêm vào `.gitignore` |

---

## 2. Kiểm thử tự động

```powershell
& ".\.venv-claude\Scripts\python.exe" -m pytest -p no:cacheprovider --no-header
```

| Bộ | Kết quả |
| --- | --- |
| Fast suite (toàn bộ) | **344 passed, 1 skipped, 5 deselected** (xem mục 10) |
| `tests/test_fingerprint_progress_streaming.py` (mới) | 5 passed |
| `tests/test_app_fingerprint_progress.py` (mới) | 2 passed |
| `tests/test_va_meta.py` | 11 passed |
| `tests/test_clip_metadata.py` + `test_metadata_integration.py` | passed |
| `tests/test_audfprint_multiproc.py` (mới) | 4 passed |
| `tests/test_audfprint_progress_integration.py` (`-m slow`, audfprint thật) | 2 passed |
| `ruff check .` | `All checks passed!` |
| `compileall` (13 module chính) | exit 0 |
| `git diff --check` | sạch (exit 0) |

**Baseline trước khi Claude sửa:** 330 passed, 1 skipped, **1 failed**
(`test_app.py::test_giao_dien_khong_loi_render` — `AppTest.from_file("app.py")` giải
đường dẫn tương đối theo `tests/`, không theo CWD, trên Streamlit 1.61).

---

## 3. Bằng chứng cho Lỗi A — tiến trình tạo vân tay

### 3.1. Thực nghiệm xác định nguyên nhân

audfprint vendored, 3 file WAV tổng hợp trong thư mục tạm:

| `--ncores` | rc | tổng dòng stdout | dòng chứa `ingesting #` |
| ---: | ---: | ---: | ---: |
| 1 | 1 | 23 | **3** |
| 2 | 0 | 6 | **0** |
| 8 (mặc định production) | 0 | 12 | **0** |

`so_nhan_nen_dung()` trên máy này = **8**. Cơ chế đếm tiến độ cũ dựa 100% vào
`"ingesting #"` ⇒ **không nhận được một dòng nào** trong suốt job 1717 clip.

### 3.2. Sau sửa — test streaming với subprocess thật

`tests/test_fingerprint_progress_streaming.py` dùng audfprint giả **không in
`ingesting #`** (khẳng định bằng `assert "ingesting #" not in AUDFPRINT_GIA`), chạy qua
đúng `_run_stream` → `run_observed_process` → `Popen`:

| Test | Xác minh |
| --- | --- |
| `..._van_toi_khi_audfprint_khong_in_ingesting` | 3/3 clip có event; event clip đầu tới trong nửa đầu thời gian job; `percent` không lùi; `current ≤ total`; event cuối `completed` |
| `test_heartbeat_van_cap_nhat_khi_audfprint_im_lang` | có heartbeat khi subprocess im 1.2 s; heartbeat **không** tự tăng phần trăm |
| `test_controller_cho_phep_ui_ve_tien_do_khi_worker_con_chay` | `snapshot()` thấy `total=3` và tên clip **khi `controller.running is True`** |
| `test_khong_tao_hai_job_van_tay_trung_nhau` | `start()` lần hai → `RuntimeError` |
| `test_worker_khong_goi_streamlit_va_queue_khong_phinh_vo_han` | `qsize() ≤ maxsize` suốt job; event phát từ thread `fingerprint-*` |

### 3.3. Log terminal thật (chụp từ stdout khi test chạy)

```
2026-08-06 22:44:45 INFO fingerprint.job.<k> job_id=<id> event=job phase=discovering
2026-08-06 22:44:45 INFO fingerprint.job.<k> job_id=<id> event=job total=3 phase=validating
2026-08-06 22:44:45 INFO fingerprint.job.<k> event=process_start process=audfprint-build pid=34244
2026-08-06 22:44:45 INFO fingerprint.job.<k> job_id=<id> event=clip start index=1 total=3 file='...opus' pid=29504
2026-08-06 22:44:45 INFO fingerprint.job.<k> event=process_child_start process=python.exe pid=29504 parent_pid=34244
2026-08-06 22:44:45 INFO fingerprint.job.<k> job_id=<id> event=heartbeat phase=fingerprinting pid=34244
2026-08-06 22:44:45 INFO fingerprint.job.<k> job_id=<id> event=clip success index=1 total=3 file='...opus' elapsed=0.300s
2026-08-06 22:44:54 INFO fingerprint.job.<k> event=process_end process=audfprint-build pid=34244 exit_code=0 elapsed=2.771s
2026-08-06 22:44:54 INFO fingerprint.job.<k> job_id=<id> event=job completed processed=3 total=3
```

Đủ timestamp · level · job_id · current/total · tên clip đã làm sạch · phase · elapsed ·
exit code. Không lộ đường dẫn đầy đủ, cookie, credential hay URL có token.

---

## 4. Smoke test Streamlit

### 4.1. Server thật, cổng riêng, dữ liệu tạm

```powershell
$env:TIMCLIP_DATA_DIR = "<tmp>\data"; $env:TIMCLIP_OUTPUT_DIR = "<tmp>\ketqua"
& ".\.venv-claude\Scripts\python.exe" -m streamlit run app.py `
  --server.address=127.0.0.1 --server.port=8502 --server.headless=true `
  --browser.gatherUsageStats=false
```

| Kiểm tra | Kết quả |
| --- | --- |
| `GET /_stcore/health` | `200 ok` |
| `GET /` | `200`, 10951 byte |
| Ngoại lệ khi khởi động | không có |
| Kho production | **không đụng tới** (dùng `TIMCLIP_DATA_DIR` tạm) |

### 4.2. Khung hình giữa chừng (AppTest, `tests/test_app_fingerprint_progress.py`)

`st.rerun` được vô hiệu hoá để chụp đúng một khung hình đang chạy — nếu không, AppTest
sẽ lặp rerun tới khi job xong và chỉ trả về khung hình cuối.

Nội dung quan sát được **khi job còn chạy**:

```
Đang tạo vân tay clip gốc
Clip hiện tại (2/3): 00000000 - Clip hai [bbbbbbbbbbb].opus
Đã tính xong 2 · Đã tồn tại 0 · Lỗi 0 · Đã xử lý 2/3
Đã chạy 00:00:01 · Tốc độ trung bình: Đang tính... · ETA: Đang tính... · Worker: Đang hoạt động
Cập nhật gần nhất: 22:44:46 · PID audfprint: 34244 · Queue: 0/256
```

---

## 5. Bằng chứng cho Lỗi B — danh sách video gốc

### 5.1. Diagnostic chỉ đọc trên kho thật

```powershell
& ".\.venv-claude\Scripts\python.exe" kiem_metadata_kho.py --video-id Zlfty7Enrkg
```

Không dùng `--repair-offline`, không `--apply`. Đã xác minh sau khi chạy: mtime của
`data/kho_cory_72c177.pklz`, `data/metadata/kho_cory_72c177.json`,
`D:\ClipGocCory\clips_meta.json` đều **không đổi**; `data/fingerprint_jobs/` rỗng.

```
Kho:                      Cory
Database fingerprint:     data\kho_cory_72c177.pklz
Thư mục clip:             D:\ClipGocCory
Số clip trong database:   1717
Số metadata entry:        1717   (snapshot đã được khôi phục offline từ trước)
Khớp exact:               86
Khớp exact basename:      0
Khớp canonical:           0
Khớp YouTube ID:          0
Fallback từ filename:     1631
Không thể ánh xạ:         0
Ánh xạ mơ hồ:             0
Metadata orphan:          0

Nguồn metadata:
- metadata/kho_cory_72c177.json [snapshot]     entries=1717  invalid=0
- ClipGocCory/clips_meta.json   [live]         entries=86    invalid=0
- ClipGocCory/clips_meta.json.bak [live_backup] entries=85   invalid=0
```

### 5.2. Đối chiếu dữ liệu thô

| Chỉ số | Giá trị |
| --- | ---: |
| File media trên `D:\ClipGocCory` | 1717 |
| Entry trong `clips_meta.json` | 86 |
| File có key exact trong `clips_meta.json` | 86 |
| Entry có `upload_date` thật | **0** |
| File có prefix `00000000` | **1717 / 1717** |

### 5.3. Dựng lại đúng báo cáo `Zlfty7Enrkg` từ `lichsu.db` thật

Job #307 · `n_matches = 3` · `so_dat_nguong = 12` · nguồn:
`3 Hours Of Coryxkenshin HorrorShorts Party! Spooky Scary Sunday Compilation #24`

| # | Link video gốc | Tên video gốc | Ngày đăng | Thời lượng | Cách resolve |
| ---: | --- | --- | --- | --- | --- |
| 1 | `https://youtu.be/iiPCTnSoj9w` | Pedro Pascal Wants You. [SSS #070] | *(trống)* | *(trống)* | `filename_fallback` |
| 2 | `https://youtu.be/Nkr7YLIlAdU` | DO NOT CLICK THIS VIDEO. [SSS #003] | *(trống)* | *(trống)* | `filename_fallback` |
| 3 | `https://youtu.be/pqzrFR3anuo` | what would you do if she asked for a ride home_ [SSS #031] | *(trống)* | *(trống)* | `filename_fallback` |

- Bảng ngang: 34/34 cột; ô video gốc 4 và 5 rỗng **đúng** (chỉ 3 đoạn được chọn).
- `Tổng số đoạn phát hiện = 12` **giữ nguyên**, không bị sửa cho khớp số đoạn xuất.
- Bảng dọc (`to_rows`): 3 dòng, cả 3 có tên + link video gốc.
- Dossier Markdown: 3 mục `## Đoạn N`, mỗi mục đủ Tiêu đề + Link video gốc.
- `metadata_coverage`: `selected=3, complete=0, partial=3, filename_fallbacks=3,
  unresolved=0, ambiguous=0` ⇒ UI hiện cảnh báo, **không** im lặng.

> `Ngày đăng` / `Thời lượng` trống vì dữ liệu đó **không tồn tại ở bất kỳ đâu trên máy**
> (mục 5.2), không phải vì ánh xạ sai. Không điền dữ liệu giả.

### 5.4. Test regression metadata (offline)

`tests/test_app_fingerprint_progress.py::test_bao_cao_hien_video_goc_cho_tung_doan_va_khong_nham_tong`
dựng kho 3 clip trong đó **chỉ 1 clip có metadata chính thức**:

- ba đoạn ⇒ ba video gốc, ô 4/5 rỗng, tổng 12 giữ nguyên;
- thứ tự đoạn ↔ video gốc bám đúng thứ tự match (không dedup làm lệch vị trí);
- clip có metadata chính thức hiển thị `02/01/2024` + `00:10:10`;
- hai clip còn lại có link/tên từ tên file nhưng **ngày đăng và thời lượng để trống**;
- `dossier`, `to_rows`, `bang_ngang` đều dùng **cùng một** resolver.

`tests/test_va_meta.py` bổ sung 3 test cho `seed_meta_tu_dia()`:
clip trên đĩa chưa có entry vẫn vá được · không tạo rác cho file không có VIDEO_ID ·
không ghi đè metadata chính thức bằng dữ liệu suy từ tên file.

---

## 6. An toàn dữ liệu — đã xác minh

| Ràng buộc | Trạng thái |
| --- | --- |
| Không `git reset --hard` / `git clean` / `git checkout -- .` | ✅ không chạy |
| Không xoá/tạo lại kho 1717 clip | ✅ `kho_cory_72c177.pklz` giữ nguyên mtime 6:04:49 PM |
| Không sửa `clips_meta.json` production | ✅ mtime giữ nguyên 8/5 2:26:34 PM |
| Không đọc/in nội dung credential | ✅ chỉ kiểm tra `google_key.json` **không** được tracked |
| Không đổi thuật toán fingerprint/matching/`_merge`/threshold | ✅ không sửa `audfprint-master/`, không sửa `_merge`/`_chon_loc`/`Config` |
| Không kill process theo tên | ✅ `terminate_process_tree()` chỉ theo cây PID gốc |
| Không gọi Google Sheets / YouTube thật trong test | ✅ mọi test dùng fetcher giả hoặc dữ liệu tạm |
| Không commit tự động | ✅ không chạy `git commit` |


---

## 7. Bộ slow chạy chung — deadlock vendored ĐÃ SỬA

| Phạm vi | Trước bản vá | Sau bản vá |
| --- | --- | --- |
| `pytest tests/test_audfprint_progress_integration.py -m slow` | 1 passed | 2 passed |
| `pytest tests/test_integration.py -m slow` | 3 passed | 3 passed |
| **`pytest -m slow` (chạy chung)** | **TREO — 3/3 lần thử** | **5 passed trong 59,50 s** |

### Chẩn đoán

`py-spy dump` khi treo: cha audfprint kẹt ở `multiproc_add` → `rx[core].recv()`;
worker kẹt ở `pipe.send(ht)`. Tái hiện **trên audfprint gốc, không qua wrapper**.

### Quy trách nhiệm và xác minh — 20 lượt mỗi chế độ

Cùng lệnh, `--ncores 8 --shifts 4 --maxtimebits 16`, 4 clip WAV 30 s, timeout 45 s:

| Chế độ | Treo | Trung bình | Event nhận được |
| --- | ---: | ---: | --- |
| audfprint gốc (vendored) | **8/20 = 40 %** | 23,0 s | 0 (gốc không phát event) |
| **wrapper đã sửa** | **0/20 = 0 %** | **6,4 s** | **8/8 mọi lượt** |

### Thuật toán không đổi — so sánh từng ô

Dựng kho cùng dữ liệu bằng audfprint gốc và bằng wrapper đã sửa:

```
so file:                    goc=6     wrapper=6
tong hash:                  goc=5802  wrapper=5802
hashbits/depth/maxtimebits: giong nhau
=> bang hash, counts va danh sach file GIONG HET TUNG O
```

Chi tiết cơ chế và bản vá: [CLAUDE_AUDIT_REPORT.md](CLAUDE_AUDIT_REPORT.md) mục
"PHÁT HIỆN MỚI".

## 8. Sửa thêm — thông lượng đọc stdout của `run_observed_process`

Phát hiện trong lúc chẩn đoán deadlock (độc lập với deadlock đó).

| | Trước | Sau |
| --- | ---: | ---: |
| Rút 4.001 dòng stdout | 29,1 s | **0,3 s** |
| Thông lượng | 138 dòng/giây | **15.094 dòng/giây** |
| Số dòng nhận được | 4.001/4.001 | 4.001/4.001 |

Nguyên nhân: vòng lặp chính lấy **một** dòng mỗi vòng rồi gọi
`psutil.Process().children(recursive=True)` — psutil phải quét toàn bộ tiến trình của máy
sau **mỗi dòng**.

Sửa: rút theo lô (tối đa 512 dòng/vòng) và soi cây process theo **nhịp thời gian cố định
0,2 giây** — giữ nguyên tần suất cũ lúc subprocess im lặng nên vẫn bắt được tiến trình
FFmpeg tồn tại rất ngắn (phase `decoding`).

Regression test: `tests/test_process_runner.py::test_rut_stdout_du_nhanh_de_khong_lam_day_pipe_cua_os`.

## 9. Sửa thêm — mất event do 8 worker ghi chung một pipe

Quan sát trong probe: `event=7` thay vì 8. `print()` có thể tách thành nhiều lần ghi nên
hai dòng lồng vào nhau, engine mất progress event và ghi rác vào `loi_file`.

Sửa: `_emit()` ghi bằng **đúng một** `os.write()`. Sau đó 20/20 lượt probe đều nhận đủ 8/8
event. Regression test:
`tests/test_audfprint_multiproc.py::test_tam_tien_trinh_con_ghi_chung_stdout_khong_mat_hay_ghep_dong`
(8 worker × 40 event = 320 dòng, tất cả nguyên vẹn).

## 10. Kết quả cuối cùng

| Lệnh | Kết quả |
| --- | --- |
| `pytest` (fast, toàn bộ) | **344 passed, 1 skipped, 5 deselected** (112,75 s) |
| **`pytest -m slow`** | **5 passed, 345 deselected** (59,50 s) |
| `ruff check .` | `All checks passed!` |
| `compileall` | exit 0 |
| `pip check` | `No broken requirements found.` |
| `git diff --check` | sạch |


---

## 11. Vòng sửa ngày đăng + phase decoding (2026-08-07)

| Lệnh | Kết quả |
| --- | --- |
| `pytest` (fast, toàn bộ) | **358 passed, 1 skipped, 5 deselected** (23,42 s) |
| `pytest -m slow` × **3 lượt liên tiếp** | **5 passed** mỗi lượt (hết flaky) |
| `tests/test_ngay_dang.py` (mới) | 12 passed |
| `ruff check .` | `All checks passed!` |
| `compileall` (13 module chính) | exit 0 |
| `pip check` | `No broken requirements found.` |
| `git diff --check` | sạch |

### Ngày đăng

Nguyên nhân và bản vá: [CLAUDE_AUDIT_REPORT.md](CLAUDE_AUDIT_REPORT.md) mục "NGÀY ĐĂNG".
Điểm mấu chốt: `_tai_va_nen()` đổi `ydl.download()` → `ydl.extract_info(download=True)`,
lấy `upload_date`/`duration`/`title` thật **không tốn thêm request nào** vì lượt tải vốn
đã trích xuất đầy đủ trang video. Đường đồng bộ mặc định vẫn là **một** request cho cả
kênh.

Kết quả kiểm chứng offline (`tests/test_ngay_dang.py`):

- `sync()` ghi file `20240115 - Tên chính thức trên YouTube [aaaaaaaaaaa].opus` và
  `clips_meta.json` có `upload_date=20240115`, `duration=612.0`.
- Video thật sự không có ngày vẫn dùng `00000000` và `upload_date=""` — **không bịa**
  ngày hôm nay.
- `list_channel()` mặc định **không** phát sinh request phụ (test khẳng định bằng fetcher
  ném `AssertionError` nếu bị gọi).
- `lay_ngay_dang=True` chỉ hỏi lại video còn thiếu (2/3 trong fixture), có báo tiến độ.
- Một video bị xoá/riêng tư chỉ để trống ngày, không làm hỏng cả danh sách.

### Phase decoding

`clip_phase` phát từ `audio_read.audio_read()` — đúng nơi gọi FFmpeg — thay cho việc
suy đoán bằng cách bắt gặp tiến trình ffmpeg khi lấy mẫu. Đây là nguyên nhân
`pytest -m slow` từng đỏ ngẫu nhiên ở
`test_audfprint_da_nhan_phat_event_truoc_khi_database_duoc_commit`
(`assert any(event.phase == "decoding" ...)`).

### Dữ liệu production

`data/kho_cory_72c177.pklz` và `D:\ClipGocCory\clips_meta.json` **không đổi mtime**
suốt vòng này. Mọi test dùng `tmp_path`/`TIMCLIP_DATA_DIR` tạm.
