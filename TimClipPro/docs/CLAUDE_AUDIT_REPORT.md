# CLAUDE_AUDIT_REPORT — Vòng review độc lập trên workspace của Codex

Ngày: 2026-08-06 · Branch: `master` · Môi trường kiểm chứng: `.venv-claude`

> Tài liệu này chỉ ghi những gì đã **chạy và quan sát được**. Mọi con số đều kèm lệnh
> tái lập. Không sao chép số liệu từ tài liệu cũ.

---

## 1. WORKSPACE BASELINE

| Mục | Giá trị |
| --- | --- |
| Branch | `master` (không phải `main`) |
| Trạng thái | dirty, chưa commit |
| File tracked đã sửa | 16 (`app.py`, `engine.py`, `bang_ngang.py`, `cli.py`, `dossier.py`, 5 test, 6 doc) |
| File untracked mới | 12 (5 module + 6 test + 2 doc; xem bảng dưới) |
| Quy mô | +1672 / −375 dòng trên phần tracked |
| `git diff --check` | sạch (exit 0) |
| File nhạy cảm | `google_key.json` — **đã ignore, không tracked** (đã xác minh bằng `git ls-files`) |
| Dữ liệu production | `data/kho_cory_72c177.pklz` (288 MB), `data/lichsu.db`, `D:\ClipGocCory` — **không bị đụng tới trong vòng này** |

Module mới do Codex tạo (untracked):
`fingerprint_progress.py`, `clip_metadata.py`, `process_runner.py`,
`audfprint_progress_runner.py`, `kiem_metadata_kho.py`.

**Không phát hiện implementation dang dở.** Cả hai luồng Codex đang làm đều có module,
call site và test đầy đủ. Vấn đề còn lại là **thiếu bằng chứng chạy thật** và **một số
lỗ hổng ở tầng dữ liệu**, không phải code viết dở.

### Sai lệch môi trường so với yêu cầu

Yêu cầu dựng `.venv-claude` bằng Python 3.12. Máy **không có 3.12**
(`py -0p` chỉ liệt kê 3.14). `.venv` đang chạy app thật là **Python 3.14.6**.
Đã dựng `.venv-claude` bằng đúng 3.14.6 — kiểm chứng trên chính runtime production
thay vì trên một phiên bản không tồn tại trên máy này.

---

## 2. CALL GRAPH THỰC TẾ (sau thay đổi)

### 2.1. Tạo kho vân tay

```
app.py chay_van_tay()
  └─ FingerprintJobController.start()          [fingerprint_progress.py]
       └─ worker thread "fingerprint-<id>"
            └─ Engine.build_database()          [engine.py:1294]
                 ├─ FingerprintProgressTracker(callback=controller.publish)
                 ├─ KhoaTienTrinh(data/tool.lock, "dựng kho vân tay")
                 └─ _build_database_da_khoa()   [engine.py:1360]
                      ├─ liet_ke_media() → tracker.set_files()      → phase=validating
                      ├─ db_clips() → tracker.skipped() cho clip đã có
                      ├─ copy db cũ → data/fingerprint_jobs/<job_id>/database.pklz
                      ├─ _run_stream(_audfprint_build_cmd(...))     [engine.py:536]
                      │    └─ run_observed_process()                [process_runner.py:78]
                      │         ├─ Popen(stdout=PIPE, stderr=STDOUT)
                      │         ├─ thread "stdout-<pid>" → queue(256)   ← KHÔNG block main loop
                      │         ├─ vòng lặp: get(timeout=.2) → on_line / on_heartbeat / cancel
                      │         └─ audfprint_progress_runner.py
                      │              ├─ patch audfprint.make_ht_from_list  (nhánh ncores>1)
                      │              ├─ patch Analyzer.ingest              (nhánh ncores=1)
                      │              └─ in "TIMCLIP_FINGERPRINT_EVENT {json}"
                      ├─ os.replace(db_tam → db_file)   ← commit nguyên tử, cuối cùng
                      └─ _cap_nhat_snapshot_sau_build()
  └─ main thread: controller.drain() / .snapshot() / .recent() → vẽ UI
```

**Ranh giới:** worker thread **không** gọi API Streamlit; nó chỉ `publish()` vào
`queue.Queue(maxsize=256)`. Main thread Streamlit đọc snapshot. Đã kiểm chứng bằng
`test_worker_khong_goi_streamlit_va_queue_khong_phinh_vo_han`.

### 2.2. Quét video vi phạm → báo cáo

```
Engine.scan_youtube()/scan_file()
  → yt-dlp → audio → audfprint match → _merge() → _chon_loc() → ScanResult
       ├─ so_dat_nguong = số đoạn ĐẠT NGƯỠNG (trước chọn lọc)
       └─ matches       = số đoạn ĐƯỢC CHỌN để xuất (top_n)
  → Engine.clip_metadata_resolver()             [engine.py:784]  ← MỘT resolver duy nhất
       ├─ nguồn 0: data/metadata/kho_<slug>.json     (snapshot theo kho)
       ├─ nguồn 10: <kho_thu_muc>/clips_meta.json     (live)
       ├─ nguồn 20+: <thư mục của clip trong DB>/clips_meta.json (legacy)
       └─ nguồn 100: data/clips_meta.json  ← CHỈ khi kho là "" hoặc "Kho mặc định"
  → resolver.resolve(match.clip): exact → exact_basename → canonical → video_id
                                   → filename_fallback → basename_fallback
  → dùng chung bởi: to_rows (dọc) · bang_ngang.dung_dong_ngang (34 cột)
                    dossier.dung_ho_so (Markdown) · to_rows_ngang → Sheets · UI
```

---

## 3. LỖI A — Tiến trình tạo vân tay đứng im

### 3.1. Root cause (đã chứng minh bằng thực nghiệm, không suy đoán)

| Thành phần | Chi tiết |
| --- | --- |
| File | `engine.py` (bản HEAD `e8c0db5`) |
| Hàm | `_build_database_da_khoa.on_line()` và `_run_stream()` |
| Cơ chế | Tiến độ chỉ đến từ việc bắt chuỗi `"ingesting #"` trên stdout của audfprint |

Production chạy `ncores = so_nhan_nen_dung()` = **8** trên máy này
(`engine.py:1277-1279`). Với `ncores > 1`, audfprint đi nhánh
`do_cmd_multiproc → multiproc_add` (`audfprint.py:272`) → `make_ht_from_list`
(`audfprint.py:130`) gọi **thẳng** `analyzer.wavfile2hashes()`. Dòng `"ingesting #"`
chỉ được in ở `audfprint.py:178` (nhánh **một nhân**) và `audfprint_analyze.py:572`
(hàm không dùng).

**Đo trực tiếp trên audfprint vendored, 3 file WAV tổng hợp:**

| `--ncores` | return code | tổng dòng stdout | số dòng chứa `ingesting #` |
| ---: | ---: | ---: | ---: |
| 1 | 1 | 23 | **3** |
| 2 | 0 | 6 | **0** |
| 8 | 0 | 12 | **0** |

→ Ở cấu hình production (8 nhân), audfprint in **0 dòng per-file**; toàn bộ 6–12 dòng
output chỉ xuất hiện **sau khi mọi tiến trình con kết thúc**. Callback `on_line` không
bao giờ chạy trong lúc job đang chạy ⇒ `st.progress` giữ nguyên 0.0 và thông báo giữ
nguyên `"Bắt đầu tạo vân tay cho 1717 clip gốc..."` cho tới hết batch. Đây **chính xác**
là triệu chứng người dùng báo.

**Yếu tố cộng hưởng:** `_run_stream` cũ dùng `for dong in p.stdout:` — vòng lặp block
trên `readline()`. Không có dòng nào ⇒ vòng lặp không quay ⇒ `self.cancel_event` cũng
không bao giờ được kiểm tra ⇒ nút Dừng cũng vô hiệu. Đây là lý do người dùng "không
biết chương trình đang chạy, bị block, bị treo hay chỉ cập nhật sau khi hoàn thành".

> Ghi chú phụ: nhánh `ncores=1` còn có `ZeroDivisionError` trong audfprint vendored khi
> tổng thời lượng bằng 0. Không nằm trong phạm vi vòng này (thư viện bên thứ ba, và
> production không dùng nhánh này), nhưng đã ghi lại.

### 3.2. Giải pháp (Codex triển khai — đã review và xác nhận đúng)

- `audfprint_progress_runner.py` bọc **cả hai** nhánh: `make_ht_from_list` (ncores>1) và
  `Analyzer.ingest` (ncores=1). Không sửa một dòng nào trong `audfprint-master/`.
- `process_runner.run_observed_process()`: thread đọc stdout riêng + `queue`, vòng lặp
  chính `get(timeout=0.2)` nên vẫn quay khi subprocess im lặng ⇒ heartbeat, kiểm tra
  cancel và dọn cây PID (`terminate_process_tree`, chỉ theo PID gốc — không kill theo tên).
- `FingerprintProgress` (frozen dataclass) mang đủ: `phase`, `current/total`, `file_name`,
  `success/skipped/failed`, `elapsed`, `eta`, `rate`, `active_subprocess_pid`, `queue_size`.
- `FingerprintJobController`: một worker, queue bounded 256, `start()` ném `RuntimeError`
  nếu job đang chạy ⇒ double-click không tạo job trùng.
- `app.py`: placeholder cố định (`st.empty()`), không tạo component mới mỗi vòng.

### 3.3. Bằng chứng sau sửa

`tests/test_fingerprint_progress_streaming.py` (mới, 5 test) chạy **subprocess thật** qua
đúng `_run_stream`/`run_observed_process`, với audfprint giả **không in một dòng
`ingesting #` nào** — tái hiện chính xác nhánh `ncores>1`:

- event per-clip vẫn tới đủ 3/3 clip;
- event clip đầu tiên tới trong **nửa đầu** thời gian job (không dồn về cuối);
- heartbeat vẫn phát khi subprocess im lặng 1.2 giây;
- `percent` không lùi, `current ≤ total`, event cuối là `completed`;
- `FingerprintJobController.snapshot()` thấy `total=3` và tên clip **trong lúc**
  `controller.running is True`;
- gọi `start()` lần hai khi đang chạy → `RuntimeError`;
- `events.qsize() ≤ maxsize` suốt job.

`tests/test_app_fingerprint_progress.py` (mới) chạy chính `app.py` qua `AppTest` và chụp
khung hình **giữa chừng**: màn hình có tiêu đề "Đang tạo vân tay clip gốc", tên clip hiện
tại, công đoạn, `2/3`, `Đã chạy 00:00:01`, `Worker: Đang hoạt động`, `Cập nhật gần nhất`.

Log terminal thật quan sát được trong khi test chạy:

```
INFO fingerprint.job.<...> job_id=<...> event=job phase=discovering
INFO fingerprint.job.<...> job_id=<...> event=job total=3 phase=validating
INFO fingerprint.job.<...> event=process_start process=audfprint-build pid=34244
INFO fingerprint.job.<...> event=clip start index=1 total=3 file='...opus' pid=29504
INFO fingerprint.job.<...> event=process_child_start process=python.exe pid=29504 parent_pid=34244
INFO fingerprint.job.<...> event=heartbeat phase=fingerprinting pid=34244
INFO fingerprint.job.<...> event=clip success index=1 total=3 file='...opus' elapsed=0.300s
INFO fingerprint.job.<...> event=process_end process=audfprint-build pid=34244 exit_code=0 elapsed=2.771s
INFO fingerprint.job.<...> event=job completed processed=3 total=3
```

Có timestamp, level, job_id, current/total, tên file đã làm sạch (chỉ basename qua
`ten_file_an_toan()`), phase, elapsed và exit code. Không lộ đường dẫn đầy đủ,
credential hay URL có token.

---

## 4. LỖI B — Danh sách video gốc trống

### 4.1. Root cause tầng code (đã chứng minh)

Bản HEAD `bang_ngang.py` tra metadata bằng **đúng một cách**:

```python
meta = clips_meta.get(matches[i].clip, {})     # exact key, không fallback
```

`dossier.py` và `engine.to_rows()` cũng dùng cùng kiểu tra cứu. Miss ⇒ `{}` ⇒ cả bốn ô
"Link / Tên / Ngày đăng / Thời lượng video gốc N" đều rỗng, **không có cảnh báo nào**.

### 4.2. Root cause tầng dữ liệu (mới phát hiện trong vòng này)

Diagnostic chỉ đọc trên kho thật (`kiem_metadata_kho.py`):

```
Kho: Cory                    Database: data/kho_cory_72c177.pklz
Thư mục clip: D:\ClipGocCory
Số clip trong database: 1717
```

Đối chiếu trực tiếp `D:\ClipGocCory\clips_meta.json` với đĩa:

| Chỉ số | Giá trị |
| --- | ---: |
| File media trên đĩa | 1717 |
| Entry trong `clips_meta.json` | **86** |
| File có key exact trong `clips_meta.json` | **86** |
| Entry có `upload_date` thật (khác rỗng/`00000000`) | **0** |
| File có prefix tên `00000000` | **1717 / 1717** |

Nghĩa là **1631/1717 clip (95%) chưa từng có metadata**, và **không một clip nào** có
ngày đăng. Nguyên nhân:

1. `ChannelSync.list_channel()` dùng `extract_flat: "in_playlist"` (`channel.py:190`).
   yt-dlp ở chế độ flat **không trả `upload_date`** cho entry của kênh/playlist ⇒
   `VideoInfo.upload_date` luôn rỗng ⇒ `_ten_file()` đặt tên `00000000 - ...` và
   `clips_meta.json` ghi `upload_date: ""`.
2. `clips_meta.json` chỉ được ghi cho video **mới tải**. 1631 clip tải trước khi có
   tính năng metadata không bao giờ có entry.
3. `ChannelSync.va_metadata()` **chỉ lặp qua các key đã có trong `clips_meta`** ⇒ 1631
   clip không entry là **không thể vá được bằng bất kỳ thao tác nào**. Đây là chân bị
   đứt của chuỗi `clip gốc → metadata → ngày/thời lượng → exporter`.

### 4.3. Giải pháp

**Codex đã làm (review: đúng):** `ClipMetadataResolver` dùng chung cho *tất cả* exporter,
thứ tự exact → exact_basename → canonical (NFC + normcase Windows) → YouTube-ID →
filename_fallback → basename_fallback; nguồn metadata bị giới hạn theo kho active nên
không trộn kho; ambiguous không tự chọn; `MetadataCoverage` + cảnh báo UI khi
`resolved_complete == 0`.

**Claude bổ sung trong vòng này:** `ChannelSync.seed_meta_tu_dia()` — tạo entry cho clip
đã có trên đĩa nhưng chưa có trong `clips_meta.json`, lấy `id/title/url` từ chính tên file
`<ngày> - <tiêu đề> [<VIDEO_ID>].opus`, để trống `upload_date`/`duration` cho fetcher điền
bằng **dữ liệu thật**. `va_metadata()` gọi nó trước khi chạy ⇒ 1631 clip kia trở thành vá
được. Không bịa dữ liệu, không ghi đè metadata chính thức đã có
(`test_seed_khong_ghi_de_metadata_that_bang_du_lieu_ten_file`).
Ghi theo lô 25 mục thay vì ghi lại cả file sau mỗi mục (trước là O(n²) I/O trên 1631 mục).

`filename_fallback_parts()` được đưa thành API công khai của `clip_metadata` để
`channel.py` và resolver dùng **chung một cách bóc tách tên file**, không có hai định nghĩa lệch nhau.

### 4.4. Bằng chứng sau sửa — dựng lại đúng báo cáo `Zlfty7Enrkg` từ `lichsu.db` thật

Job #307, `n_matches=3`, `so_dat_nguong=12`. Kết quả trên cả 4 exporter:

| Đoạn | Link video gốc | Tên video gốc | Cách resolve |
| ---: | --- | --- | --- |
| 1 | `https://youtu.be/iiPCTnSoj9w` | Pedro Pascal Wants You. [SSS #070] | `filename_fallback` |
| 2 | `https://youtu.be/Nkr7YLIlAdU` | DO NOT CLICK THIS VIDEO. [SSS #003] | `filename_fallback` |
| 3 | `https://youtu.be/pqzrFR3anuo` | what would you do if she asked for a ride home_ [SSS #031] | `filename_fallback` |

- Bảng ngang: đủ 34 cột; ô 4 và 5 rỗng đúng (chỉ 3 đoạn được chọn); `Tổng số đoạn phát hiện = 12` **giữ nguyên**.
- Bảng dọc `to_rows`: 3 dòng, cả 3 có `Tên video gốc` + `Link video gốc`.
- Dossier Markdown: 3 mục `## Đoạn N`, mỗi mục có Tiêu đề + Link video gốc.
- Coverage: `selected=3, complete=0, partial=3, filename_fallback=3, unresolved=0, ambiguous=0`
  ⇒ UI hiện cảnh báo "3/3 video gốc được phục hồi từ filename", **không** im lặng.

`Ngày đăng` và `Thời lượng` vẫn rỗng **vì dữ liệu đó không tồn tại ở bất kỳ đâu trên máy**
(mục 4.2). Đây là giới hạn dữ liệu, không phải lỗi ánh xạ, và đã có đường khắc phục:
`vametak` / nút "Bắt đầu vá metadata thiếu" (cần mạng, do người dùng chủ động chạy).

---

## 5. Bảng phán quyết thay đổi của Codex

| Component | Thay đổi | Đúng | Rủi ro regression | Hành động của Claude |
| --- | --- | :---: | --- | --- |
| `fingerprint_progress.py` | Contract + tracker + controller | ✅ | Thấp | Giữ; bổ sung test streaming thật |
| `process_runner.py` | Đọc stdout non-blocking, heartbeat, dọn cây PID | ✅ | Thấp | Giữ |
| `audfprint_progress_runner.py` | Bọc cả nhánh 1 nhân và đa nhân | ✅ | Trung bình (phụ thuộc pickling khi spawn) | Giữ; đã kiểm chứng chạy thật `ncores=2` |
| `engine.build_database` | Tracker, workspace tạm, commit nguyên tử | ✅ | Thấp | Thêm tham số `heartbeat_seconds` để test được |
| `clip_metadata.py` | Resolver nhiều tầng + audit + snapshot | ✅ | Thấp | Giữ;公 khai `filename_fallback_parts` |
| `engine.clip_metadata_resolver` | Nguồn giới hạn theo kho, cache theo mtime | ✅ | Thấp | Giữ |
| `bang_ngang` / `dossier` / `to_rows` | Dùng chung resolver, giữ tham số cũ | ✅ | Thấp | Giữ |
| `app.py` màn hình tiến độ | Placeholder cố định, không rerun tạo job | ✅ | Thấp | Giữ; thêm smoke AppTest |
| `kiem_metadata_kho.py` | Diagnostic chỉ đọc, `--apply` mới ghi | ✅ | Thấp | Giữ; đã dùng để chẩn đoán kho thật |
| `cli.py` `vametak` | Vá snapshot cho **toàn bộ** `db_clips()` | ✅ | Thấp | Giữ |
| `tests/test_app.py` | `AppTest.from_file("app.py")` | ❌ | **Suite đỏ** | **Đã sửa** → đường dẫn tuyệt đối |
| `channel.va_metadata` | *Không đụng tới* | ❌ thiếu | 1631 clip không vá được | **Đã sửa** → seed từ đĩa |

---

## 6. Các vùng rủi ro khác (audit có trọng tâm)

- **Credential:** `google_key.json` ignored, không tracked. Log fingerprint chỉ ghi
  basename qua `ten_file_an_toan()` + strip ký tự điều khiển. Không có `shell=True`.
- **Path traversal:** `_metadata_snapshot_path()` kiểm `os.path.commonpath` để snapshot
  không thoát khỏi `data/`.
- **Formula injection:** `o_bang_tinh_an_toan()` được áp cho cả CSV dọc và CSV ngang.
- **Nguyên tử dữ liệu:** fingerprint ghi vào `data/fingerprint_jobs/<job_id>/database.pklz`
  rồi `os.replace()`; hủy giữa chừng ⇒ kho trước job còn nguyên
  (`test_cancel_giu_nguyen_database_cu...`). Có nhánh dự phòng khi Windows khoá file.
- **Concurrency:** mọi thao tác nặng qua một khoá `data/tool.lock`. Dọn tiến trình chỉ
  theo cây PID gốc, **không** kill theo tên.
- **Dependency:** `requirements.txt` = runtime (có `-c constraints.txt`);
  `requirements-dev.txt` = `-r requirements.txt` + công cụ test;
  `constraints.txt` = sàn phiên bản vá bảo mật; `requirements-lock.txt` = snapshot tham
  khảo, **không** được cài trong vòng này. `pip check`: sạch.

---

## 7. Việc còn lại (không nằm trong phạm vi đã sửa)

1. ~~`ChannelSync.list_channel()` vẫn dùng `extract_flat`~~ — **ĐÃ SỬA**, xem mục
   "NGÀY ĐĂNG" bên dưới. Clip tải từ nay có tên `YYYYMMDD - ...` và `clips_meta.json`
   đủ ngày đăng/thời lượng, không tốn thêm một request mạng nào.
2. `duration` của 1631 clip có thể phục hồi **offline** bằng `ffprobe` trên chính file
   `.opus` (bằng chứng thật, không bịa). Chưa triển khai.
3. `audfprint` vendored `ZeroDivisionError` ở nhánh `ncores=1` khi tổng thời lượng = 0.


---

## PHÁT HIỆN MỚI — deadlock trong audfprint vendored (ĐÃ SỬA, đã xác minh 20 lượt)

> Phát hiện khi chạy `pytest -m slow` trong vòng này. **Không phải do thay đổi của Codex
> và cũng không phải do thay đổi của Claude** — đã tái hiện trên audfprint **gốc, không
> qua wrapper**. Đây là rủi ro production thật cho job 1717 clip.

### Triệu chứng

`pytest -m slow` treo vĩnh viễn ở `tests/test_integration.py` (3/3 lần thử). Tiến trình
còn sống, chiếm ~900 MB, nhưng CPU đứng yên hơn 25 phút.

### Stack thật (py-spy dump)

Tiến trình cha audfprint:

```
_recv_bytes (multiprocessing\connection.py:336)
recv        (multiprocessing\connection.py:260)
multiproc_add (audfprint-master\audfprint.py:228)
do_cmd_multiproc (audfprint-master\audfprint.py:272)
```

Tiến trình con:

```
_send_bytes (multiprocessing\connection.py:304)
send        (multiprocessing\connection.py:216)
make_ht_from_list  (audfprint.py:130 / audfprint_progress_runner.py:71)
```

Tiến trình pytest: `run_observed_process (process_runner.py:161)` → `_run_stream` →
`build_database` — tức là job đứng ở tầng dưới cùng, không phải ở UI.

### Quy trách nhiệm — thực nghiệm

Cùng dòng lệnh, cùng dữ liệu (4 clip WAV 30 s, `--ncores 8 --shifts 4 --maxtimebits 16`),
chạy lặp lại trong một tiến trình cha, timeout 180 s:

| Lần chạy | Có wrapper | Kết quả |
| --- | :---: | --- |
| goc_lan1 | không | rc=0 trong 7,5 s |
| goc_lan2 | không | rc=0 trong 7,2 s |
| **goc_lan3** | **không** | **TREO (timeout 180 s)** |
| wrapper_lan1 | có | TREO (timeout 180 s) |
| wrapper_lan2 | có | TREO (timeout 180 s) |
| wrapper_lan3 | có | rc=0 trong 7,4 s |

⇒ Treo xảy ra **cả khi không có wrapper**. Nguyên nhân nằm trong `audfprint-master/`.

### Cơ chế

`multiproc_add()` (`audfprint.py:199-235`):

1. Tạo `ncores` cặp `multiprocessing.Pipe(False)`, mỗi worker gửi trả một `HashTable`.
   Với `hashbits=20, depth=100`, mỗi bảng là `2**20 × 100 × uint32` ≈ **419 MB**.
2. Tiến trình cha **giữ nguyên mọi đầu ghi `tx[ix]`** sau khi `start()`. Vì đầu ghi vẫn
   mở trong cha nên worker chết **không** tạo EOF ⇒ `recv()` chờ mãi mãi.
3. Cha `recv()` theo **đúng thứ tự 0..n-1** và **không có timeout** ở bất kỳ đâu.

Bất kỳ trục trặc nào ở một worker đều biến thành treo vĩnh viễn. Hiện tượng không tất định
(3/6 lần) — phù hợp với race khi truyền pickle rất lớn qua named pipe trên Windows.

### Ảnh hưởng thực tế

- Cấu hình production là `ncores: 0` ⇒ `so_nhan_nen_dung()` = **8** ⇒ **luôn** đi nhánh này.
- `_run_stream()` cố ý **không** đặt `timeout_seconds` (build 1717 clip có thể chạy nhiều
  giờ), nên treo sẽ kéo dài vô hạn.
- Sau bản vá progress, người dùng **nhìn thấy** tình trạng này (heartbeat báo
  "worker vẫn sống, im lặng N giây") thay vì màn hình đứng im vô nghĩa như trước, và nút
  Dừng vẫn hoạt động vì `run_observed_process` dọn đúng cây PID. Nhưng job vẫn không xong.

### Bản vá đã thực hiện

Không sửa `audfprint-master/` (quy tắc dự án). Thay `multiproc_add` và `_emit` trong
`audfprint_progress_runner.py`:

| Thay đổi | Lý do |
| --- | --- |
| Worker ghi HashTable ra **file tạm gzip** thay vì gửi qua `Pipe`; pipe chỉ mang dict trạng thái vài chục byte | Loại bỏ hoàn toàn 3,3 GB đi qua named pipe — chính là phần không ổn định |
| Cha gọi `ghi.close()` **ngay sau** `process.start()` | Worker chết tạo `EOFError` thay vì treo vô hạn |
| `recv()` có `poll(CHO_WORKER_S=1800)` | Lưới an toàn cuối; đường chạy bình thường không chạm tới |
| Xoá file tạm ngay sau khi merge; `finally` dọn thư mục và terminate worker còn sống | Đỉnh dung lượng đĩa không cộng dồn 8 worker |
| `_emit()` ghi bằng **một** `os.write()` thay vì `print()` | 8 tiến trình con ghi chung một pipe; `print()` tách nhiều lần ghi làm lồng dòng và **mất event** (đã quan sát 7/8 thay vì 8/8) |

### Xác minh

**Thuật toán không đổi** — dựng kho cùng dữ liệu bằng audfprint gốc và bằng wrapper đã
sửa, so sánh từng ô:

```
so file:      goc=6     wrapper=6
tong hash:    goc=5802  wrapper=5802
hashbits/depth/maxtimebits: giong nhau
=> bang hash, counts va danh sach file GIONG HET TUNG O
```

**Tỉ lệ treo** — cùng lệnh, `--ncores 8 --shifts 4`, 4 clip WAV 30 s, timeout 45 s,
chạy lặp 20 lượt mỗi chế độ:

| Chế độ | Treo | Trung bình | Event nhận được |
| --- | ---: | ---: | --- |
| audfprint gốc | **8/20 (40 %)** | 23,0 s | 0 (gốc không phát event) |
| **wrapper đã sửa** | **0/20 (0 %)** | **6,4 s** | **8/8 mọi lượt** |

Bản vá còn **nhanh hơn** bản gốc ở lượt thành công (6,4 s so với 8,2 s) vì gzip trên
bảng gần như toàn số 0 rẻ hơn nhiều so với đẩy 419 MB/worker qua named pipe.

### Regression test

| Test | Bảo vệ điều gì |
| --- | --- |
| `tests/test_audfprint_multiproc.py::test_cai_dat_day_du_ba_diem_va` | Quên vá `multiproc_add` (hoặc hai điểm kia) là suite đỏ ngay |
| `..._worker_chet_khong_gui_gi_thi_bao_loi_chu_khong_treo` | Worker chết → `RuntimeError` rõ ràng, **không** treo |
| `..._khong_con_file_tam_sau_khi_that_bai` | Thư mục tạm được dọn kể cả khi lỗi |
| `..._tam_tien_trinh_con_ghi_chung_stdout_khong_mat_hay_ghep_dong` | 8 worker × 40 event = 320 dòng, tất cả nguyên vẹn và parse được JSON |
| `tests/test_audfprint_progress_integration.py::test_nhanh_da_nhan_that_khong_treo_va_khong_mat_event` (slow) | 3 lượt build thật `ncores=8`, đủ event cho mọi clip |

`pytest -m slow` chạy chung — trước đây treo 3/3 lần — nay chạy hết.


---

## NGÀY ĐĂNG — sửa `list_channel` và đường tải

### Nguyên nhân

`ChannelSync.list_channel()` dùng `extract_flat: "in_playlist"`: **một** request cho cả
kênh nên rất nhanh, nhưng yt-dlp ở chế độ này **không trả `upload_date`** cho entry của
kênh/playlist. Hệ quả đo được trên kho Cory: **1717/1717** file mang tiền tố `00000000`
và **0/86** entry `clips_meta.json` có ngày đăng thật.

Đổi thẳng `list_channel` sang chế độ đầy đủ là **sai hướng**: một request mỗi video,
kênh 1717 video sẽ mất hàng giờ cho **mọi** lần đồng bộ về sau (`docs/EXECUTION_PLAN_C.md`
cũng đã ghi rõ ràng buộc này).

### Bản vá — lấy ngày đăng ở đúng chỗ nó vốn đã có sẵn

`_tai_va_nen()` trước đây gọi `ydl.download([v.url])` và **vứt bỏ** giá trị trả về. Lượt
tải đó vốn đã trích xuất đầy đủ trang video. Đổi sang
`ydl.extract_info(v.url, download=True)` là có ngay `upload_date`, `duration` và tiêu đề
chính thức — **không tốn thêm một request nào**.

| Thay đổi | Tác dụng |
| --- | --- |
| `_tai_va_nen()` trả `(đường_dẫn, VideoInfo đã bổ sung)` | Tên file dùng ngày THẬT: `20240115 - Tiêu đề [ID].opus` |
| `sync()` ghi giá trị đã bổ sung vào `clips_meta.json` | `upload_date`/`duration`/`title` đầy đủ ngay từ lượt tải đầu |
| `ngay_dang_tu_info()` | Rút ngày từ `upload_date`, hoặc `release_timestamp`/`timestamp` (premiere/livestream có sẵn ở chế độ flat) — miễn phí |
| `bo_sung_video_info()` | Chỉ ghi đè khi giá trị mới thực sự có; không thay dữ liệu tốt bằng rỗng |
| `list_channel(..., lay_ngay_dang=True)` | Tuỳ chọn bổ sung ngày cho danh sách xem trước — **mặc định tắt**, chỉ hỏi lại những video còn thiếu |
| `_ten_file()` lọc qua `valid_upload_date()` | `00000000` chỉ khi thật sự không có ngày; **không bịa ngày hôm nay** |
| `ChannelSync.lay_info_video()` | Một điểm trích xuất đầy đủ, dùng chung cho `va_metadata` và `list_channel` |
| `engine.va_metadata_thieu` + `channel.va_metadata` dùng chung `ngay_dang_tu_info()` | Ba đường lấy metadata không còn hiểu khác nhau |

### Ràng buộc đã giữ

- Đường đồng bộ mặc định vẫn là **một** request cho cả kênh; không làm chậm thêm.
- Video bị xoá/riêng tư khi bật `lay_ngay_dang` chỉ để trống ngày, không làm hỏng cả
  danh sách và **không bịa dữ liệu**.
- Không đổi tên file đã tồn tại trong kho (sẽ làm lệch khoá `clips_meta.json` và
  `downloaded.txt`). Kho cũ vẫn cần `vameta`/`vametak` để bổ sung ngày.

### Test — `tests/test_ngay_dang.py` (12 test, không gọi mạng)

Ưu tiên `upload_date` hợp lệ · loại `00000000`/rác/tháng 13 · dùng
`release_timestamp`/`timestamp` khi flat không có ngày · timestamp vô nghĩa không thành
ngày · không ghi đè dữ liệu tốt bằng rỗng · mặc định `list_channel` **không** gọi request
phụ · `lay_ngay_dang=True` chỉ hỏi đúng video còn thiếu và báo tiến độ · một video lỗi
không làm hỏng danh sách · `sync()` ghi ngày thật vào tên file lẫn `clips_meta.json` ·
video thật sự không có ngày vẫn dùng `00000000` chứ không bịa.
