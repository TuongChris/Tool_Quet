# PROJECT MASTER AUDIT — TimClipPro

> **Vòng audit READ-ONLY, ngày 2026-09-07.** Không một file mã nguồn nào bị sửa.
> Tài liệu này mô tả hệ thống **đang là**, không phải hệ thống nên là.
>
> Nguồn chân lý là **source code**. Ở mọi chỗ tài liệu cũ mâu thuẫn với source,
> source thắng và điều đó được ghi rõ.

**Tài liệu liên quan** (cùng vòng audit, đọc kèm):

| File | Nội dung |
|---|---|
| [SYSTEM_MAP.md](SYSTEM_MAP.md) | Sơ đồ luồng quét / vân tay / metadata / Sheets / thread |
| [MODULE_MAP.md](MODULE_MAP.md) | Bảng 38 module, ai gọi ai, thứ tự đọc cho người mới |
| [DATA_FLOW.md](DATA_FLOW.md) | Biến đổi từng chặng, ma trận nguồn chân lý, **hệ quy chiếu thời gian** |
| [FUTURE_DEVELOPMENT_READINESS.md](FUTURE_DEVELOPMENT_READINESS.md) | Đa khách hàng, Works Registry, điểm mở rộng an toàn |
| [CLAUDE_HANDOFF_2026-09.md](CLAUDE_HANDOFF_2026-09.md) | Bàn giao cho phiên làm việc kế tiếp |

---

## 1. Executive Summary

**Sức khoẻ hiện tại: tốt hơn đáng kể so với số lượng finding gợi ý.**

Đây là một codebase có kỷ luật kỹ thuật thật, và điều đó cần nói trước:

* `engine.py` hoàn toàn không import Streamlit, và điều này được **ép bằng cấu trúc**
  chứ không bằng quy ước — `tests/test_scan_thread_boundary.py:48-70` tokenize source
  để docstring không tạo false positive, và có cả meta-test chứng minh guard thật sự bắn.
* Ghi JSON là atomic: tmp + fsync + `os.replace`, có `.bak` phục hồi và cách ly `.hong.*`
  (`luu_tru.py:85-92`).
* Khoá liên tiến trình là **khoá OS thật** (`khoa.py:16-39`), không phải mẹo kiểm tra
  sự tồn tại của file lock, không có heuristic PID cũ.
* Mọi lệnh `subprocess` đều là argv list; **không có `shell=True` ở bất kỳ đâu**,
  kể cả trong `audfprint-master/` được vendor.
* Mọi lần ghi Google Sheets đều dùng `value_input_option=RAW` — chặn formula injection
  ở cơ chế chứ không bằng cách escape chuỗi.
* Đường dẫn kho được kiểm tra containment, có regression test riêng
  (`engine.py:743-765` + `tests/test_security_regressions.py:15-24`).
* Mỗi lượt quét có workspace `uuid4` riêng (`engine.py:2219-2234`) — đã sửa một bug
  xoá nhầm khi chạy song song.
* `audfprint-master/` **không bị sửa**; thay đổi hành vi được áp bằng runtime patch
  (`audfprint_progress_runner.py:307-318`) nên vẫn đối chiếu được với upstream.

Văn hoá viết lại **lý do** trong comment ở đây là bất thường theo nghĩa tốt: gần như mọi
bất biến được kiểm tra ngẫu nhiên đều kèm comment nêu đúng sự cố đã sinh ra nó, và các
comment đó **chính xác**.

**Không tìm thấy lỗi P0 nào.** Không có hỏng dữ liệu, không có lỗ hổng bảo mật khai thác được.

**Rủi ro lớn nhất không phải là một bug — mà là một chiều dữ liệu bị thiếu.**

Danh tính và phạm vi không được mang xuyên suốt pipeline:

* `Match` chỉ mang **basename**, không mang work id (`engine.py:882-885`).
* Bảng `jobs` **không có cột kho** (`engine.py:873-877`).
* Cả hai schema báo cáo đều không có cột kho (`bang_ngang.py:14-48`, `engine.py:3318-3324`).
* Phạm vi đã quét không bao giờ tới được artefact xuất ra (AUD-201).
* Tầng metadata có **hai kho lưu mà không có thoả thuận ai là chủ** (AUD-061/AUD-081).

Sáu defect nghiêm trọng nhất trong báo cáo này **không phải sáu bug độc lập** — chúng là
cùng một chiều bị thiếu, lộ ra ở sáu chỗ khác nhau. Và tất cả đều **hỏng im lặng**, trên
một công cụ mà sản phẩm đầu ra là bằng chứng pháp lý.

**Rào cản thứ hai: cổng kiểm tra hồi quy không hoạt động.** Chi tiết ở §16 — tóm tắt là
`kiemtra.bat` không thể báo lỗi, `.venv` không có pytest, và không có CI.

**Kết luận (§28): READY FOR LIMITED FEATURE DEVELOPMENT.** Ba critic độc lập đều đi tới
đúng kết luận này bằng ba đường lập luận khác nhau.

---

## 2. Repository State

### 2.1 Vị trí thật

Brief yêu cầu audit `D:\Tool_Tim_Video_v2\TimClipPro`. **Đường dẫn đó không tồn tại trên
máy này** — không có thư mục `Tool_Tim_Video_v2` nào trên ổ D:, và không có `engine.py`
nào ở độ sâu ≤ 4 trên D:.

Repository thật được audit:

```
C:\Users\Admin\OneDrive\Desktop\ToolQuet\Tool_Quet\TimClipPro
```

Đây chắc chắn là cùng dự án: cùng bộ 38 module, cùng remote `Tool_Quet`.

### 2.2 Trạng thái Git

```
remote   : git@github.com:TuongChris/Tool_Quet.git
HEAD     : 7f85c8d22e33d61c09961cc30afcb9bf35539f00
           "fix(chan-doan): chỉ đúng nguyên nhân 0 kết quả, vá 4 lỗi lộ ra khi audit"
           2026-08-21 10:59:37 +0700
branch   : (HEAD detached at v2.6)      <-- KHÔNG ở trên nhánh nào
tags     : v2.2 v2.3 v2.4 v2.5 v2.6
tree     : sạch trước và sau toàn bộ vòng audit
```

> ⚠️ **HEAD đang detached tại tag `v2.6`, không ở trên `main`.**
> Bất kỳ commit nào tạo ra ở trạng thái này sẽ không thuộc nhánh nào và rất dễ mất khi
> `git checkout` lần sau. Đây nhiều khả năng là hệ quả của bộ tự cập nhật
> (`cap_nhat.py`, commit `451e382` "tự cập nhật từ GitHub theo tag").
> **Trước khi commit bất cứ thứ gì: `git switch -c <nhánh>` hoặc `git switch main`.**

### 2.3 Chia rẽ môi trường — rủi ro thật

| | `.venv` (cái **chạy**) | `py -3` (cái **test**) |
|---|---|---|
| Python | 3.12.10 | 3.14.3 |
| pytest | **không có** | 9.1.1 |
| ruff | **không có** | **không có** |
| streamlit | 1.62.0 | 1.60.0 |
| pyarrow | 25.0.1 | 24.0.0 |
| yt-dlp | 2026.8.19 | 2026.7.23.234303.**dev0** |
| numpy | 2.5.2 | 2.5.1 |
| google-auth | 2.56.3 | 2.56.2 |

`ruff.toml` đặt `target-version = "py312"`; `README.md:9` và `Dockerfile:2` cũng nói 3.12.
Nhưng bộ test **chỉ chạy được trên 3.14**. Nghĩa là: **code chạy bằng một môi trường,
được chứng nhận bằng một môi trường khác**, với `yt-dlp` — thư viện dễ vỡ nhất trong cả
stack — lệch hẳn một bản dev. (AUD-X26, AUD-245)

### 2.4 Bối cảnh lúc audit

Một job **dựng kho vân tay đang chạy** trong suốt vòng audit:

```
data/tool.lock -> PID: 41936 | 2026-09-07 08:40:57 | Tác vụ: dựng kho vân tay
```

Vì vậy mọi agent bị ràng buộc read-only tuyệt đối với `data/`, và bộ test `slow`
**không được chạy** (nó gọi audfprint/FFmpeg thật, sẽ tranh CPU với job đang chạy).

### 2.5 Bí mật

Không in giá trị bí mật ở bất kỳ đâu trong vòng audit. Chỉ ghi nhận sự tồn tại:

| File | Trạng thái |
|---|---|
| `google_key.json` | tồn tại ở gốc dự án; **gitignored** (`.gitignore:2`); **không** được git theo dõi |
| `cookies.txt` | gitignored (`.gitignore:10`); **không** được git theo dõi |
| `data/cau_hinh.json` | gitignored (`.gitignore:3`) |

Xác minh: `git ls-files --error-unmatch google_key.json` → *did not match any file(s) known to git*.

---

## 3. Architecture Diagram

```
                     NGƯỜI DÙNG
   ┌──────────────┬──────────────────┬────────────────────┐
   │              │                  │                    │
ChayTool.bat   GiamSat.bat      cli.py (thủ công)   ChayMayPhu.bat
   │              │                  │                    │
   ▼              ▼                  ▼                    ▼
app.py        watch.py            cli.py            app.py (máy phụ)
(Streamlit)   (vòng lặp giám sát)  (một lượt)
   │              │                  │
   │  ScanJobController              │
   │  (scan_jobs.py — thread nền)    │
   └──────────────┴──────────────────┘
                  │
                  ▼
        ┌───────────────────────┐
        │      Engine           │  engine.py — 3453 dòng
        │  KHÔNG import st.*    │  (ép bằng test cấu trúc)
        └───────────┬───────────┘
                    │
     ┌──────────────┼───────────────────┬──────────────────┐
     ▼              ▼                   ▼                  ▼
 ytdlp_chung    bin/ffmpeg          audfprint       clip_metadata
 + channel      bin/ffprobe        (vendored)        (phân giải 7 mức)
     │              │                   │                  │
   YouTube       cắt khúc         kho .pklz          clips_meta.json
                                                   + data/metadata/*.json
     └──────────────┴───────────────────┴──────────────────┘
                    │
                    ▼
              ┌───────────┐
              │ScanResult │
              └─────┬─────┘
                    │
      ┌─────────────┼──────────────────┬─────────────────┐
      ▼             ▼                  ▼                 ▼
 data/lichsu.db  ketqua/*.csv    bảng ngang 34 cột   hồ sơ .md
 (jobs+matches)  (dọc 16 cột)          │            (dossier.py)
                                       ▼
                              sheets.py / sheet_delivery.py
                                       │
                                       ▼
                              Google Sheets "KetQuaQuet"
                                       │
                                       ▼
                              apps_script/*.gs (7 file)
```

Sơ đồ chi tiết từng luồng: [SYSTEM_MAP.md](SYSTEM_MAP.md).

---

## 4. Module Map (rút gọn)

38 module Python ở gốc dự án, **15.174 dòng**. Bảng đầy đủ ở [MODULE_MAP.md](MODULE_MAP.md).

| Module | LOC | Vai trò | Rủi ro |
|---|---:|---|---|
| `engine.py` | 3453 | Lõi: quét, khớp, gộp, dựng kho, lưu lịch sử, xuất báo cáo | **HIGH** |
| `app.py` | 1508 | Toàn bộ giao diện Streamlit | **HIGH** |
| `clip_metadata.py` | 1058 | Phân giải metadata clip gốc, 7 mức fallback | **HIGH** |
| `channel.py` | 687 | Đồng bộ kênh YouTube, tải clip, vá metadata | MEDIUM |
| `danh_sach_video.py` | 647 | Tab liệt kê video kho, ghi đè trang tính riêng | MEDIUM |
| `fingerprint_progress.py` | 593 | Job controller cho dựng kho (kiến trúc tham chiếu) | MEDIUM |
| `ytdlp_chung.py` | 520 | Lớp gom mọi tuỳ chọn yt-dlp, cookie, giãn nhịp | **HIGH** |
| `watch.py` | 517 | Chế độ giám sát tự động | MEDIUM |
| `sheets.py` | 407 | Xuất Google Sheets | MEDIUM |
| `scan_jobs.py` | 390 | ScanJobController — thread nền cho quét | **HIGH** |
| `audfprint_progress_runner.py` | 340 | Bọc audfprint, phát event tiến độ | MEDIUM |
| `cli.py` | 318 | Giao diện dòng lệnh | LOW |
| `publication_date.py` | 294 | Chuẩn hoá ngày đăng | LOW |
| `chan_doan_quet.py` | 287 | Phễu chẩn đoán 0 kết quả | LOW |
| `process_runner.py` | 280 | Chạy tiến trình con, dọn cây tiến trình | MEDIUM |
| `cap_nhat.py` | 267 | Tự cập nhật từ GitHub theo tag | MEDIUM |
| `sheet_delivery.py` | 256 | Giao Sheets tăng dần, có thử lại | MEDIUM |
| `toc_do_khop.py` | 253 | Ước lượng tỷ lệ tốc độ (Theil-Sen) | MEDIUM |
| `luu_tru.py` | 161 | Ghi JSON atomic + phục hồi | MEDIUM |
| `chap_nhan_khop.py` | 140 | Ngưỡng chấp nhận hai bậc | **HIGH** |
| `dossier.py` | 127 | Dựng hồ sơ khiếu nại bản quyền | MEDIUM |
| `khoa.py` | 124 | Khoá OS liên tiến trình | MEDIUM |
| `bang_ngang.py` | 121 | Bảng ngang 34 cột | MEDIUM |

*(15 module còn lại — `don_dep`, `nhat_ky`, `kiem_*`, `dong_goi*`, `cau_hinh`,
`scan_ui`, `dung_lai`, `chia_watchlist`, `thiet_lap_may_phu` — ở [MODULE_MAP.md](MODULE_MAP.md).)*

---

## 5. Scan Pipeline — từ URL tới kết quả

Tên hàm **thật**, đã đối chiếu source:

```
scan_many (engine.py:3261)              — API lô, gom list
   └─ scan_iter (engine.py:3224)        — generator, yield từng ScanResult
        └─ scan_youtube (engine.py:3145)
             ├─ lấy metadata qua ytdlp_chung
             ├─ tải audio (ưu tiên client audio-only)
             └─ scan_media (engine.py:3043)
                  ├─ ffprobe đo thời lượng media thật
                  ├─ cắt khúc theo config.chunk_s (có overlap)
                  ├─ _quet_tho — đường Top-1 nhanh (SYSTEM_MAP §2.4)
                  ├─ _match_chunks (engine.py:2283) — gọi audfprint từng khúc
                  ├─ _merge (engine.py:2395) — gộp mảnh thành Match
                  ├─ chap_nhan_khop — ngưỡng hai bậc
                  └─ chọn Top-N
   └─ save_job (engine.py:3273) — ghi lichsu.db NGAY sau từng video
```

**Ba nơi chứa `ScanResult`** và ba đường xuất:

| Đích | Hàm | Số cột |
|---|---|---:|
| CSV dọc | `to_rows` (engine.py:3344) | **16** |
| Bảng ngang / Sheets | `to_rows_ngang` (engine.py:3385) → `bang_ngang.py` | **34** |
| Hồ sơ khiếu nại | `export_ho_so` (engine.py:3420) → `dossier.py` | — |

Cả ba số cột đã được xác minh bằng cách import module thật trong vòng audit này:
`len(bang_ngang.HEADER_NGANG) == 34`, `len(engine.Engine.HEADER) == 16`, và
`kiem_header.py` báo *"Toàn bộ 34 tiêu đề khớp chính xác từng ký tự."*

**Nếu app chết ở video 8/10:** kết quả 1–7 **còn**. `save_job` được gọi sau *từng* video,
không phải cuối lô. Mất tối đa một kết quả.

---

## 6. Fingerprint Pipeline

```
Nút "Dựng kho" (app.py) hoặc cli.py
   └─ build_database (engine.py:1669)
        └─ _build_database_da_khoa   [GIỮ data/tool.lock — engine.py:1690]
             ├─ dựng workspace data/fingerprint_jobs/<id>/
             ├─ (mode "add") pre-copy kho cũ
             ├─ audfprint_progress_runner — tiến trình con, phát event qua FILE TẠM
             │    (bản vá: audfprint gốc đẩy HashTable ~419MB/worker qua Pipe → treo cứng)
             └─ commit: os.replace, có fallback PermissionError (engine.py:1939-1961)
        └─ _cap_nhat_snapshot_sau_build (engine.py:1803, 1976)   <-- xem §8, đây là gốc AUD-061
```

Kho được **nạp một lần cho mỗi lệnh audfprint**, không phải mỗi khúc — chi tiết
[SYSTEM_MAP.md §3.3](SYSTEM_MAP.md).

`audfprint-master/` **không bị sửa** — thay đổi hành vi áp bằng runtime patch. Điều này
giữ khả năng đối chiếu với upstream và là một quyết định kiến trúc tốt.

---

## 7. Matching Pipeline — bảy tầng

Định nghĩa chính xác, không gộp tầng mà code thật sự tách
(chi tiết đầy đủ ở [DATA_FLOW.md §2](DATA_FLOW.md)):

| Tầng | Là gì | Ở đâu |
|---|---|---|
| T0 | ứng viên nội bộ của audfprint | không bao giờ ra khỏi subprocess |
| T1 | dòng `Matched` thô (stdout) | `_match_chunks` |
| T2 | **parsed** — dict đã parse | `_match_chunks` |
| T3 | **chunk** — đã lọc ngưỡng mảnh | `_match_chunks` |
| T4 | **merged** — `Match` đã gộp | `_merge` (engine.py:2395) |
| T5 | **accepted** — qua ngưỡng hai bậc | `chap_nhan_khop.py:81-126` |
| T6 | **selected** — Top-N | engine.py |
| T7 | dòng báo cáo | `to_rows` / `to_rows_ngang` |

**`top_n` thật sự đếm gì:** đếm **ứng viên đã gộp (T4/T6)**, *không phải* số tác phẩm gốc
duy nhất. Hai đoạn khớp cùng một clip gốc chiếm hai suất.

> ⚠️ `top_n` cho phép người dùng đặt tới 50, nhưng định dạng báo cáo mặc định
> **giới hạn cứng ở `SO_DOAN = 5` slot** và hồ sơ in con số đã bị cắt đó như thể là tổng
> (AUD-208, AUD-202). Đây là câu hỏi sản phẩm chưa ai quyết: **một khiếu nại nên chứa
> bao nhiêu đoạn?**

**Ngưỡng chấp nhận chỉ dùng `matched_s` và `hashes`** — không bao giờ dùng thời lượng
source/media (`chap_nhan_khop.py:81-126`). Đây là một bất biến tốt: nó cô lập quyết định
chấp nhận khỏi toàn bộ họ bug về duration.

---

## 8. Metadata Architecture

Chuỗi phân giải 7 mức, nguồn và độ ưu tiên đầy đủ ở
[SYSTEM_MAP.md §4](SYSTEM_MAP.md) và [DATA_FLOW.md §3.4](DATA_FLOW.md).

**Vấn đề trung tâm — hai kho lưu, không thoả thuận ai là chủ:**

```
data/metadata/kho_<slug>.json   priority  0   <-- DẪN XUẤT, nhưng THẮNG
<kho>/clips_meta.json           priority 10   <-- NGUỒN GỐC, nhưng THUA
                                  (engine.py:1120-1124)
```

`_merge_entries` (`clip_metadata.py:549-557`) lấy `ordered[0]`; các nguồn sau **chỉ được
điền vào ô RỖNG** (`clip_metadata.py:586-590`). Guard `_entry_quality`
(`clip_metadata.py:541-547`) chỉ hạ bậc entry `filename_fallback`/`basename_fallback` —
mà `_snapshot_entry` đóng dấu `"exact"` cho mọi clip phân giải đúng (`engine.py:1289-1292`).

Hệ quả: **cả ba công cụ sửa metadata đều ghi vào file thua.**

| Công cụ | Ghi vào | Tới được báo cáo? |
|---|---|---|
| `ChannelSync.va_metadata(lay_title=True)` (nút app.py:1066) | `clips_meta.json` | **KHÔNG** |
| `kiem_ngay_dang.py --repair-network --apply` (:229) | `clips_meta.json` | **KHÔNG** |
| `kiem_thoi_luong.py --sua --that-su` (:135) | `clips_meta.json` | **KHÔNG** |

Và nó **không tự lành**: `_khoi_phuc_metadata_offline_da_khoa` dựng resolver từ chính
danh sách nguồn có snapshot cũ (`engine.py:1301`), phân giải qua nó (`:1351`) rồi ghi
ngược trở lại (`:1358-1363`). Cả `preserve_existing=False` (`:1446`) cũng không thoát,
vì snapshot cũ trên đĩa vẫn được nạp làm nguồn. **Lối thoát duy nhất là xoá tay
`data/metadata/kho_*.json`.**

Xung đột **có được phát hiện** — `conflict:<field>:<key>` đi từ `clip_metadata.py:601,612`
→ `ResolvedClipMetadata.warnings` → `resolver.conflicts` → `Engine.canh_bao_metadata`
(`engine.py:1211-1221`). Nhưng **chỉ `kiem_metadata_kho.py:229` đọc nó**; `app.py` hiển
thị sáu chỉ số audit mà không có `conflicts` (`app.py:1174-1180`), và exporter bỏ hẳn
`warnings`. Tín hiệu được tính ra rồi chết ở một CLI.

> **Quan trọng trước khi sửa:** `tests/test_clip_metadata.py:229-266` **khẳng định đúng
> hành vi này là hợp đồng** (`result.title == "Tiêu đề snapshot"` đối lại một title live
> khác). Đây **không phải bug ngẫu nhiên** — nó là một quyết định thiết kế được pin bằng
> test. Sửa nó sẽ làm test đỏ, và đó là việc phải làm có chủ ý.
>
> Trong khi đó `dong_goi_may_chay.py:112` mô tả snapshot là *nguồn phụ chỉ dùng khi
> clips_meta thiếu* — tức là **tài liệu và code đang nói ngược nhau**. Đó chính là mâu
> thuẫn nằm ở tim của AUD-061/AUD-081.

**Danh tính clip** (AUD-062, AUD-063): regex trích ID áp lên **toàn bộ tên file** thay vì
neo vào vị trí `[ID]<ext>` mà `channel._ten_file` thật sự sinh ra (`channel.py:466-469`).
Nên bất kỳ token 11 ký tự trong ngoặc vuông nằm trong *tiêu đề* cũng bị tính là ID thứ hai
→ resolver fail closed → `url = ""` trong mọi báo cáo, và **không công cụ sửa nào cứu được**
(`engine.py:1352-1354`, `:1524` đều bỏ qua clip `ambiguous`).

Codebase **đã biết** chuyện này xảy ra trên dữ liệu thật: `danh_sach_video.py:281-291`
gọi đích danh `[Compilation]`, `[Official_MV]`, `[4K-REMASTER]` và thêm workaround —
nhưng chỉ cho tab của chính nó.

---

## 9. Publication Date

Chuỗi ưu tiên và mọi exporter: [DATA_FLOW.md §8](DATA_FLOW.md).

Điểm cần biết ở tầng master:

* `publication_date.py` (294 dòng) chuẩn hoá; `kiem_ngay_dang.py` sửa qua mạng.
* `docs/PUBLICATION_DATE_AUDIT.md` ước tính **~88% kho Cory lệch một ngày**, và
  `kiem_ngay_dang --repair-network` là cách sửa duy nhất.
* **Cách sửa đó hiện đang vô hiệu** vì §8 — nó ghi vào `clips_meta.json`, file thua.
* `kiem_ngay_dang --repair-network` còn gửi **một request không xác thực cho mỗi clip**:
  cookie đã cấu hình không tới được `lay_info_video` (AUD-102, `kiem_ngay_dang.py:131-132`).

---

## 10. Duration — canonical vs processing

Bốn khái niệm phải tách bạch (bảng đầy đủ [DATA_FLOW.md §6-7](DATA_FLOW.md)):

| # | Khái niệm | Nguồn |
|---|---|---|
| (a) | thời lượng **tác phẩm gốc** (canonical) | yt-dlp / metadata |
| (b) | thời lượng **media đang xử lý** | ffprobe trên file đã tải |
| (c) | **mốc thời gian khớp** | audfprint |
| (d) | thời gian **chạy thực tế** | đồng hồ |

> ⚠️ **Mâu thuẫn chưa giải quyết (AUD-083):** `ScanResult.duration_s` mang
> `lengthSeconds` của yt-dlp trên đường tải một phần (`engine.py:3194` — đã xác minh),
> trong khi `docs/DURATION_ARCHITECTURE.md:46-47,53-55` nói ngược lại.
> Chưa quyết định thêm trường `duration_source` hay sửa tài liệu.

`Match.vung` (Đầu/Giữa/Cuối) được tính theo độ dài file **tải dở** và **không bao giờ
được tính lại** sau khi `duration_s` được đính chính (AUD-084, `engine.py:2535-2543`).

---

## 11. YouTube Integration

`ytdlp_chung.py` (520 dòng, commit `354da23`) **thật sự** là lớp gom tập trung — điều này
đã được kiểm chứng chứ không chỉ tin theo commit message. Bảng call-site đầy đủ ở
[SYSTEM_MAP.md](SYSTEM_MAP.md) và [DATA_FLOW.md](DATA_FLOW.md).

Điểm đáng lưu ý:

* `Engine.nho_client = ytdlp_chung.NhoClientTotNhat()` — nhớ client vừa tải được để
  **không trả giá 403 cho từng video**, tự quên sau 30 phút (`engine.py` docstring).
  Đây là xử lý 403 chủ động, không phải retry mù.
* Mọi request YouTube **đều có socket timeout**.
* `channel.py:457` bỏ qua video bị xoá/riêng tư bằng `try/except/continue` **có chủ ý và
  có comment**: mục đó giữ ngày rỗng *chứ không bị bịa*. Đây là hành vi đúng cho một công
  cụ bằng chứng.
* Ngược lại `list_channel` **im lặng bỏ** các entry yt-dlp không extract được, rồi `sync()`
  và `kiem_tra_thieu()` báo kho là đầy đủ (AUD-101, LIKELY).

**Câu hỏi kiến trúc quan trọng — quét một video có vô tình gọi mạng cho hàng trăm clip gốc
không?** Trên đường xuất báo cáo bình thường: **không**. Metadata được phân giải **cục bộ**
qua `ClipMetadataResolver`. Gọi mạng chỉ xảy ra khi người dùng chủ động chạy công cụ vá.

---

## 12. Google Sheets

Ba đường ghi (chi tiết [SYSTEM_MAP.md §5](SYSTEM_MAP.md)):

1. **GUI** — bất đồng bộ, có thử lại (`sheet_delivery.py`)
2. **watch** — đồng bộ, một lượt quét dọn cuối
3. **danh_sach_video** — ghi đè trang tính riêng

**Điểm mạnh:** mọi lần ghi dùng `value_input_option=RAW` → formula injection bị chặn ở
cơ chế. Hợp đồng 34 cột **byte-identical** giữa `bang_ngang.py:14-48`, `kiem_header.py:11-32`
và `apps_script/File01:75-110`.

**Điểm yếu:**

| Vấn đề | ID |
|---|---|
| Hai schema (34 cột ngang, 16 cột dọc) nhắm **cùng một worksheet**; dòng 16 cột bị nối dưới header 34 cột, mismatch được log nhưng **vẫn ghi và vẫn báo thành công** | AUD-141, AUD-206 |
| **Không request Sheets nào có timeout** (`sheets.py:150`); ở watch mode một call treo sẽ chặn vô hạn cả lượt quét | AUD-X13 |
| Apps Script nói với người dùng rằng chèn/di chuyển cột trong `KetQuaQuet` là vô hại; exporter Python ghi **strict theo vị trí** | AUD-147 |
| Cùng một kết quả ghi tự động vs thủ công cho ra **text ô khác nhau** (thừa dấu nháy) | AUD-205 |
| Main thread và thread giao Sheets dùng chung một `Worksheet` + `requests.Session`, không serialise | AUD-X07 (LIKELY) |

**Ngữ nghĩa thất bại:** lỗi Sheets **không** làm hỏng `ScanResult` — đúng như thiết kế.
Nhưng `cli.py watch` **thoát 1 sau một lỗi Sheets thoáng qua mà lượt quét dọn cuối đã khắc
phục xong** (AUD-144) — trạng thái giao hàng đang đầu độc exit code của việc quét.

---

## 13. Streamlit & Concurrency

Bản đồ thread đầy đủ: [SYSTEM_MAP.md §6](SYSTEM_MAP.md).

**Bất biến được ép bằng cấu trúc:** `engine.py` không import Streamlit, không `print`,
không `input` — `tests/test_scan_thread_boundary.py` tokenize source (docstring không tạo
false positive) và có meta-test chứng minh guard bắn. Đây là điểm sáng nhất của codebase.

**Hai defect P1 ở tầng này:**

* **AUD-121 — nút «⏹️ Dừng lại» không dừng được một lô.** Cancel được mô hình hoá bằng
  một `threading.Event` mà **mọi entry point quét đều RESET khi khởi tạo**
  (`engine.py:3149`, `:3055-3056`), và vòng lặp lô không có predicate "lô đã bị huỷ" riêng.
  `dung_lai.YeuCauDung` **chính là** predicate dính đó (`dung_lai.py:33-40`) và `watch.py:437-448`
  dùng nó giữa các video — đó là lý do cancel ở CLI/watch **hoạt động**. `app.py` không
  bao giờ import `dung_lai`. Tệ hơn: `scan_jobs.py:277-279` phát *"Đã dừng theo yêu cầu."*
  bất cứ khi nào `_cancelled` được đặt, nên **một lô chạy hết vẫn tự báo là đã dừng**.
  Mâu thuẫn trực tiếp với `CLAUDE.md:70`.

* **AUD-122 — sidebar vẫn sống trong lúc job chạy và sửa chính Engine mà worker đang đọc.**
  `Engine` nằm trong `st.session_state`, dùng chung giữa main thread và worker; chỉ cấu hình
  Sheets từng được snapshot (`ScanLaunchConfig`, `scan_jobs.py:65-87`). Bộ chọn kho
  (`app.py:485-489`) và các widget «⚙️ Tham số» (`app.py:503-565`) **không có `disabled` guard**.
  Hậu quả xấu nhất: **một hồ sơ bản quyền trộn bằng chứng từ hai kho vân tay khác nhau,
  không có dấu hiệu gì trong đầu ra.** Thiếu sót này lộ rõ vì bất đối xứng — hai nút ngay
  bên dưới cùng sidebar **có** guard (`app.py:653`, `:667`).

* **AUD-X06 — nút Dừng của «Lấy lại tên video thật» hoàn toàn trơ:**
  `ChannelSync.va_metadata` không có đường cancel nào (`channel.py:216-345`).

---

## 14. Persistence

`data/lichsu.db` — SQLite, hai bảng `jobs` và `matches`. Ma trận sở hữu dữ liệu đầy đủ:
[DATA_FLOW.md §4](DATA_FLOW.md).

**Điểm mạnh:**

* Ghi JSON atomic: tmp + fsync + `os.replace`, `.bak` phục hồi, cách ly `.hong.*`
  (`luu_tru.py:85-92`) — có test (`tests/test_luu_tru.py:104-111`).
* `save_job` chạy **sau từng video** → crash mất tối đa một kết quả.
* Commit kho vân tay dùng `os.replace` có fallback `PermissionError` (`engine.py:1939-1961`).

**Điểm yếu:**

| Vấn đề | ID |
|---|---|
| `jobs` **không có cột kho** → dedup lịch sử là **toàn cục**, không theo kho | AUD-X14/X19 |
| `matches` chỉ lưu **basename**; job cũ mở lại sẽ phân giải lại theo metadata **hôm nay** | AUD-064 |
| `data/khos.json` ghi **không có khoá liên tiến trình**, mọi writer dùng chung một tên `.tmp` cố định | AUD-161 (LIKELY) |
| `khos.json` parse được nhưng sai hình dạng → `Engine.__init__` chết bằng `KeyError`/`TypeError` thô | AUD-163 |
| `data/fingerprint_jobs/` **không bao giờ được thu gom**; rò rỉ toàn bộ workspace nếu cancel rơi vào lúc pre-copy mode "add" | AUD-043, AUD-164 |
| `don_kho_dem` có thể **xoá một download mà tiến trình khác đang quét dở** | AUD-167 |

**Về khoá:** `CLAUDE.md:76-80` tuyên bố *bất biến tuyệt đối* rằng mọi thứ chạm kho hoặc
lịch sử phải giữ `data/tool.lock`. **Đường quét không giữ khoá nào** — bốn nơi duy nhất giữ
khoá là `engine.py:1436`, `:1495`, `:1690` và `watch.py:287`. `KhoaTienTrinh` **không
reentrant** (`khoa.py:20,33`), nên bọc `scan_media` bằng khoá sẽ **deadlock** `watch.py:459`.
→ **Hoặc sửa code, hoặc sửa doc. Hiện tại một bất biến đã viết ra đang sai.** (AUD-125, AUD-261)

---

## 15. Security

**Không tìm thấy lỗ hổng khai thác được.** Nền tảng tốt:

| Kiểm tra | Kết quả |
|---|---|
| `shell=True` | **không có ở đâu**, kể cả `audfprint-master/` |
| Subprocess | 100% argv list |
| Path traversal | có guard containment + regression test (`engine.py:743-765`, `tests/test_security_regressions.py:15-24`) |
| Formula injection (Sheets/CSV) | chặn ở cơ chế bằng `value_input_option=RAW` |
| Credential trong git | `google_key.json`, `cookies.txt` đều gitignored **và** không được theo dõi |
| Credential trong zip đóng gói | có test khẳng định loại trừ (`tests/test_dong_goi_may_chay.py:47-79`) |
| Cookie rò rỉ vào log/report | có test riêng (`tests/test_cookie_khong_ro_ri.py`) |
| ruff (cấu hình dự án) | **All checks passed** |

**Ba vấn đề thật, đều là sửa một dòng:**

1. **AUD-222 — `ChayTool.bat:46` bind giao diện Streamlit *không xác thực* ra mọi network
   interface**, trong khi `README.md` và `INSTALL_WINDOWS.md` đều ghi `127.0.0.1`.
   Bất kỳ ai trong cùng LAN đều mở được UI, đọc được cấu hình, kho, lịch sử.
2. **AUD-221 / AUD-181 — `cookies.txt` lọt qua whitelist đóng gói** (`dong_goi.py:55-56`)
   và được ship trong **cả** zip audit lẫn zip triển khai máy phụ; `.dockerignore` cũng
   không coi nó là nhạy cảm. Cookie YouTube = phiên đăng nhập của người dùng.
3. **Kênh tự cập nhật** (`cap_nhat.py`) — cần xác nhận nguồn được xác thực. Xem
   [FUTURE_DEVELOPMENT_READINESS.md](FUTURE_DEVELOPMENT_READINESS.md).

**Lượt lint rộng để tham khảo** (không phải cấu hình dự án):
`ruff --select B,S,C4,A,RUF,PERF` → 175 mục. Mọi tín hiệu bảo mật đáng nhìn đã được kiểm
tra **thủ công** và đều là **false positive**:

* `engine.py:3302` S608 "SQL injection" — f-string chỉ nội suy điều kiện dựng từ hằng
  trong hàm theo cờ bool, **không có dữ liệu người dùng**. An toàn.
* `engine.py:1042`, `audfprint_progress_runner.py:245` S301 pickle — nạp kho `.pklz` do
  chính máy sinh ra, không phải nguồn không tin cậy.
* `engine.py:732`, `danh_sach_video.py:556` S324 md5 — dùng để đặt tên/slug, không dùng
  cho mục đích bảo mật.
* Các S110 còn lại — guard `import` ở đầu module hoặc fallback `.bak`.

---

## 16. Tests

60 file test. Bản đồ coverage đầy đủ: [CLAUDE_HANDOFF_2026-09.md](CLAUDE_HANDOFF_2026-09.md).

### 16.1 Baseline đo được

<!-- BASELINE_START -->

Chạy ngày **2026-09-07**, HEAD `7f85c8d`, working tree sạch trước và sau.

| Kiểm tra | Lệnh | Kết quả |
|---|---|---|
| **Fast suite** | `py -3 -m pytest` | **952 passed, 1 skipped, 5 deselected** — 0 failures, 0 errors, 50.53s |
| **Slow suite** | `py -3 -m pytest -m slow` | **KHÔNG CHẠY** — xem lý do bên dưới |
| **Ruff** | `ruff check .` (ruff.toml: E4,E7,E9,F) | **All checks passed!** |
| **Cú pháp** | `ast.parse` 99 file, **cả hai** interpreter | **0 lỗi** cú pháp, 0 lỗi encoding |
| **pip check** | `.venv/Scripts/python.exe -m pip check` | No broken requirements found |
| **git diff --check** | | sạch |
| **git status --short** | | rỗng (trước **và** sau khi chạy test) |

Từ junit XML: `tests=953 failures=0 errors=0 skipped=1 time=49.179s`.

Skip duy nhất là **hợp lệ và có điều kiện theo nền tảng**:
`tests/test_khoa.py::test_file_khoa_bi_xoa_khi_dang_giu_khong_lam_crash`
→ *"Windows không cho xóa file đang có handle mở"* — kịch bản chỉ có trên POSIX.

5 test bị deselect là các test đánh dấu `slow` trong
`tests/test_audfprint_progress_integration.py` và `tests/test_integration.py`.

**Vì sao slow suite không chạy:** nó gọi audfprint và `bin/ffmpeg.exe` **thật**, trong khi
một job dựng kho vân tay đang chạy (PID 41936). Chạy nó sẽ tranh CPU với công việc thật
của người dùng. **Cần chạy lại khi máy rảnh** — đây là 5 test duy nhất chạm audfprint thật,
nên toàn bộ đường vân tay hiện **chưa được xác nhận bằng thực thi** trong vòng audit này.

**Ruff không được cài** trong `.venv` cũng không trong `py -3`. Chạy bằng binary
ruff 0.16.2 có sẵn trong cache của uv — **không cài thêm gì vào môi trường dự án**.

<!-- BASELINE_END -->

### 16.2 Cô lập test — đã xác minh

Bộ test nhanh **an toàn để chạy** ngay cả khi job vân tay đang chạy. Đã kiểm chứng:

* `Engine.__init__` (`engine.py:615-660`) dẫn **mọi** đường ghi từ `self.data_dir` /
  `self.out_dir`; `self.root` chỉ dùng cho `bin_dir` (đọc) và làm mặc định.
* Fixture `engine` trong `conftest.py:56-62` ghi đè cả `data_dir` và `out_dir` bằng `tmp_path`.
* Hai test dựng `Engine(root=<dự án thật>)` (`test_audfprint_progress_integration.py:30,59`)
  **đều** truyền `data_dir`/`out_dir` tmp, và **đều** mang mark `slow`.
* `test_khoa.py` chỉ chạm `tmp_path` hoặc `engine.data_dir` (đã tmp) — không chạm
  `data/tool.lock` thật.
* Xác nhận thực nghiệm: `git status` rỗng và mtime của `data/` không đổi sau khi chạy.

### 16.3 Cổng kiểm tra hồi quy — không hoạt động

> ⚠️ Đây là rào cản chính giữ verdict ở LIMITED thay vì STRUCTURED.

| Vấn đề | Bằng chứng |
|---|---|
| pytest **không có** trong `.venv` mà `kiemtra.bat` trỏ tới | `kiemtra.bat:8`, AUD-245 |
| Bước test **không thể báo lỗi** — thiếu `\|\| echo [X]` mà dòng anh em `:14` có. `pytest` vắng mặt chỉ in lỗi ra stderr rồi chạy tiếp, **không có dấu `[X]` nào** | `kiemtra.bat:18` |
| Bước 3/3 dựng `Engine` chạy vào **`data/` production** (không .bat nào đặt `TIMCLIP_DATA_DIR`) | `kiemtra.bat:22` |
| **Không có CI** | `.github/` chỉ chứa `copilot-instructions.md` |
| IDE trỏ interpreter khác | `.vscode/settings.json:17` |
| Cô lập test là **quy ước**, không có autouse guard | AUD-242 |

Hệ quả: **cổng xanh do cấu trúc, không do kiểm chứng.** Và vì `py -3` (3.14) mới là chỗ
duy nhất chạy được test, mọi khẳng định "sửa cái này không làm hỏng test nào" trong vòng
audit này **là đọc source, không phải chạy test** — trừ baseline ở §16.1 do orchestrator
chạy tập trung.

---

## 17. Confirmed Findings

**141 finding thô → 133 sống sót thẩm định đối kháng → +29 finding muộn = 162 mục đã xác minh.**
7 mục bị bác bỏ hoàn toàn.

Phân bố: **P0: 0 · P1: 7 · P2: 38 · P3: 117**
Verdict: CONFIRMED 143 · LIKELY 17 · HYPOTHESIS 1 · NOT_REPRODUCED 1

> **Cảnh báo về trùng lặp — hãy đọc trước khi triage.** Mỗi domain gán severity độc lập,
> nên cùng một defect xuất hiện dưới nhiều ID với severity khác nhau. ~162 mục mô tả
> **~118 defect thật**. Bảng dưới đã **gộp trùng và lấy severity cao nhất**.

### 17.1 Defect mức P1 (6 defect thật, từ 9 mục)

| # | Defect | ID (đã gộp) | Vị trí | Vì sao nghiêm trọng |
|---|---|---|---|---|
| 1 | **Snapshot cũ che clips_meta.json** — cả ba công cụ sửa metadata đều ghi vào file thua, không tự lành | AUD-061 + AUD-081 | `engine.py:1120-1124`, `clip_metadata.py:541-557,582-601` | Hồ sơ bản quyền mang tiêu đề cũ, ngày lệch một hôm, thời lượng lệch một giây — **sau khi** người dùng đã chạy đúng công cụ để sửa. Báo cáo vẫn ghi `complete`. |
| 2 | **Token 11 ký tự trong ngoặc vuông xoá vĩnh viễn danh tính clip** | AUD-062 | `clip_metadata.py:25,744-772,845-850` | "Link video gốc" **trống** trong mọi báo cáo, và không công cụ sửa nào cứu được. Đã biết xảy ra trên dữ liệu thật. |
| 3 | **«Dừng lại» không dừng được lô** | AUD-121 + AUD-001 | `scan_jobs.py:207-212`, `engine.py:3149,3055-3056,3244-3251` | Không có cách dừng lô từ UI ngoài giết tiến trình. Còn **báo nhầm** là "đã dừng" khi lô chạy hết. |
| 4 | **Sidebar sửa Engine trong lúc worker đang đọc** | AUD-122 | `app.py:485-489,503-565` | Hồ sơ bản quyền có thể **trộn bằng chứng từ hai kho khác nhau**, không dấu hiệu. |
| 5 | **Quét một phần không bao giờ được công bố trong artefact xuất ra** | AUD-201 | `bang_ngang.py:86`, `engine.py:3350-3352`, `dossier.py:28-38` | Hồ sơ khiếu nại trình bày số liệu từ khảo sát **một phần** như thể đã quét toàn bộ. |
| 6 | **Dedup lịch sử là toàn cục, không theo kho** | AUD-X19 + AUD-X14 | `engine.py:3295-3304`, `watch.py:376-379` | Onboard khách hàng thứ hai: mọi video đã quét cho khách A **vĩnh viễn vô hình** với khách B. Sweep báo là "đã quét trước" nên vận hành thấy sạch. |

### 17.2 Nhóm P2 đáng chú ý (38 mục — danh sách đầy đủ ở phần cuối)

Bốn cụm chính:

**Bề mặt cảnh báo không tồn tại** — `ScanResult.note` được ghi ở `engine.py:3105,3219`
nhưng **cả bốn nơi đọc đều gate trên `status != "ok"`** (`app.py:907`, `cli.py:289`,
`watch.py:475`, `bang_ngang.py:86`). Nên cảnh báo cookie chết — mà comment tại
`engine.py:3216-3217` nói rõ nó tồn tại **chính để** người dùng không thấy "chạy tốt" khi
đang chạy không xác thực — **không tới được ai**. Cảnh báo "có dấu hiệu đếm trùng" gắn vào
một khiếu nại bản quyền cũng vậy. Cộng với AUD-166 (không có log handler cho `scan.*`):
**công cụ im lặng đúng vào lúc nó sai.** (AUD-X31, AUD-166, AUD-025)

**Hai schema chung một worksheet** — AUD-141, AUD-206, AUD-147, AUD-205, AUD-X20.

**Rò rỉ workspace và dọn dẹp không an toàn** — AUD-043, AUD-164, AUD-167, AUD-X05.

**Bảo mật/đóng gói một dòng** — AUD-222 (bind 0.0.0.0), AUD-221/AUD-181 (cookies.txt).

---

## 18. Hypotheses / Needs More Evidence

**Tách riêng khỏi §17 — không mục nào dưới đây được coi là sự thật đã xác lập.**

| ID | Mức | Nội dung | Cần gì để kết luận |
|---|---|---|---|
| AUD-101 | LIKELY | `list_channel` im lặng bỏ entry yt-dlp không extract được | Quan sát một kênh có video bị xoá |
| AUD-161 | LIKELY | `khos.json` ghi không khoá, dùng chung tên `.tmp` | Chạy hai tiến trình ghi đồng thời |
| AUD-182 | LIKELY | Kết quả watch không tới được Sheets không có đường giao lại | Dựng lỗi Sheets có kiểm soát |
| AUD-X07 | LIKELY | Main thread và thread giao Sheets dùng chung `Worksheet`/`Session` | Kiểm chứng thread-safety của gspread |
| AUD-X26 | CONFIRMED* | Runtime test ≠ runtime ship | *đã xác nhận; hệ quả lên yt-dlp thì chưa đo |

### 18.1 Điều audit này **không** làm được

Ghi rõ để không ai hiểu nhầm mức độ chắc chắn:

* **Không finding P1/P2 nào được tái hiện lúc chạy thật.** Tất cả đều truy vết source.
  Ba mục có chạy code (AUD-061, 062, 063) chạy trên **bản sao** trong scratchpad.
* **Slow suite chưa chạy** → toàn bộ đường vân tay chưa được xác nhận bằng thực thi.
* **`data/` thật chưa được đọc** (đúng theo ràng buộc read-only). Nên **khả năng chạm tới**
  của một họ finding vẫn chưa xác định: giá trị thật của `top_n`, `luoi_resample`,
  `luoi_tempo`, `ncores`, `keep_downloads`, `min_hash_floor` trong `data/cau_hinh.json`
  không ai được xem.
* **Chưa kiểm chứng có kho thật nào đang lệch snapshot vs clips_meta hay không** — đây là
  điều kiện biến P1 số 1 từ *tiềm ẩn* thành *đang xảy ra*. `py -3 kiem_metadata_kho.py --json`
  là **read-only** (`kiem_metadata_kho.py:290`) và sẽ trả lời câu này trong vài giây.
* **Apps Script chưa từng được chạy.** Hợp đồng 34 cột được xác minh bằng diff chuỗi, không
  bằng round-trip qua sheet thật.
* **Chưa quan sát yt-dlp dưới 403/bot-check thật** (đúng theo ràng buộc).
* **Docker image chưa từng được build** (`README.md:88`).

---

## 19. Multi-client Readiness

Đầy đủ: [FUTURE_DEVELOPMENT_READINESS.md](FUTURE_DEVELOPMENT_READINESS.md).

| Khu vực | Điểm | Lý do |
|---|---|---|
| Google credentials | **NEEDS REFACTOR** | một `google_key.json` cố định ở gốc |
| Spreadsheet / worksheet | **NEEDS REFACTOR** | một sheet id trong config |
| Kho vân tay | READY | registry `khos.json` đã hỗ trợ nhiều kho |
| Metadata store | **BLOCKED** | tranh chấp chủ quyền chưa giải quyết (§8) |
| Lịch sử quét | **BLOCKED** | `jobs` không có cột kho → dedup toàn cục (P1 #6) |
| Report schema | **BLOCKED** | không schema nào mang danh tính kho |
| Config | NEEDS REFACTOR | một `cau_hinh.json` toàn cục |
| Runtime/temp dirs | NEEDS REFACTOR | `data/downloads` là namespace toàn cục cuối cùng (AUD-X05) |
| `tool.lock` | NEEDS REFACTOR | một khoá cho toàn máy |

**Ba nơi khách A và khách B có thể trộn, xếp theo khả năng xảy ra:**

1. **Dedup lịch sử toàn cục** (P1 #6) — xảy ra **chắc chắn** ngay khi có khách thứ hai,
   trên đường **không giám sát**, **vĩnh viễn**, và **im lặng**.
2. **Apps Script đánh dấu "đã quét" xuyên khách** từ một tập key không lọc
   (`File04_DanhDauLinkDaQuet.gs:13`, AUD-X20).
3. **Đổi kho giữa chừng trong một phiên** (AUD-122).

> Biện pháp vận hành tạm thời là **một thư mục data cho mỗi khách**. Nhưng
> `TIMCLIP_DATA_DIR` **tồn tại mà `Engine.__init__` bỏ qua** (AUD-004/AUD-185) —
> phải sửa cái đó trước thì workaround mới dùng được.

---

## 20. Works Registry Readiness

Bảng đầy đủ: [FUTURE_DEVELOPMENT_READINESS.md](FUTURE_DEVELOPMENT_READINESS.md).

| Trường | Có hôm nay? | Ở đâu | Ghi chú |
|---|---|---|---|
| `TITLE` | ✅ | `clips_meta.json` / snapshot | tranh chấp chủ quyền (§8) |
| `PUBLICATION_DATE` | ✅ | `publication_date.py` | ~88% một kho lệch 1 ngày; đường sửa đang vô hiệu |
| `DURATION` | ✅ | metadata + ffprobe | 4 khái niệm, chưa ghi provenance |
| `ORIGINAL_URL` | ⚠️ | dẫn từ video id | **trống** với clip `ambiguous` (P1 #2) |
| `WORK_ID` | ❌ | — | chưa tồn tại |
| `COPYRIGHT_OWNER` | ❌ | — | chưa tồn tại ở đâu |
| `OWNERSHIP_STATUS` | ❌ | — | chưa tồn tại ở đâu |
| `VERSION` | ❌ | — | chưa tồn tại ở đâu |

**Danh tính ổn định:** ứng viên hợp lý nhất là **YouTube video ID**, nhưng phải sửa P1 #2
trước — hiện tại một tiêu đề có `[Official_MV]` là đủ để **xoá vĩnh viễn** danh tính clip.
Và `matches` chỉ lưu basename (AUD-064), nên **lịch sử không đóng băng danh tính tác phẩm**:
mở lại một job cũ sẽ phân giải lại theo metadata *hôm nay*, không phải metadata lúc quét.

> Với một công cụ sinh bằng chứng pháp lý, "bằng chứng thay đổi khi bạn mở lại nó" là vấn
> đề cần quyết định có chủ ý, không phải chi tiết kỹ thuật.

---

## 21. System Invariants

**203 bất biến** được thu thập và thẩm định. Danh sách đầy đủ:
[CLAUDE_HANDOFF_2026-09.md](CLAUDE_HANDOFF_2026-09.md) và [DATA_FLOW.md](DATA_FLOW.md).

Mười hai bất biến **không được phá**:

1. `engine.py` **không** import Streamlit, không `print`, không `input` —
   ép bằng `tests/test_scan_thread_boundary.py:48-70`.
2. API Streamlit **chỉ** chạy trên main thread.
3. Hợp đồng **34 cột** bảng ngang phải byte-identical ở cả ba nơi:
   `bang_ngang.py:14-48`, `kiem_header.py:11-32`, `apps_script/File01:75-110`.
4. CSV dọc là **16 cột** (`engine.Engine.HEADER`).
5. Mọi lần ghi Sheets dùng `value_input_option=RAW`.
6. Không `shell=True` ở bất kỳ đâu; mọi subprocess là argv list.
7. Ghi JSON là atomic (tmp + fsync + `os.replace`) với `.bak` và cách ly `.hong.*`.
8. Lỗi Google Sheets **không** làm mất hiệu lực `ScanResult` — hai trạng thái tách biệt.
9. `save_job` chạy sau **từng** video, không phải cuối lô.
10. Ngưỡng chấp nhận **chỉ** dùng `matched_s` và `hashes`, **không bao giờ** dùng thời
    lượng source/media (`chap_nhan_khop.py:81-126`).
11. **Không** trường nào mang giá trị bí mật được thêm vào `Config` — `cau_hinh.lay_tu_config`
    serialise *mọi* trường không có allowlist (`cau_hinh.py:70-72`); đó là lý do
    `ytdlp_cookiefile` chỉ lưu **đường dẫn** (`engine.py:150`).
12. `audfprint-master/` **không được sửa**; thay đổi hành vi áp bằng runtime patch.

> ⚠️ **Một bất biến đã viết ra đang SAI:** `CLAUDE.md:76-80` nói mọi thứ chạm kho hoặc lịch
> sử phải giữ `data/tool.lock`. Đường quét không giữ. Xem §14.

---

## 22. Dangerous Areas

| Khu vực | Mức | Vì sao |
|---|---|---|
| `engine.py` `_merge` (`:2395`) | **HIGH** | ngữ nghĩa gộp được pin bởi `tests/test_engine_core.py`; đổi là đổi ý nghĩa bằng chứng |
| Thứ tự ưu tiên metadata (`clip_metadata.py:541-557`) | **HIGH** | được pin là *hợp đồng* bởi `tests/test_clip_metadata.py:229-266` — sửa sẽ làm test đỏ **có chủ ý** |
| Schema 34 cột | **HIGH** | ba nơi phải khớp byte; người dùng đang dựng tab Sheets theo số này |
| Schema SQLite | **HIGH** | dữ liệu production thật đang nằm trong `data/lichsu.db` |
| Vòng đời thread trong `scan_jobs.py` | **HIGH** | ranh giới thread được ép bằng test cấu trúc |
| `chap_nhan_khop.py` | **HIGH** | ngưỡng bậc A hiệu chỉnh trên 1.199 match lịch sử |
| `toc_do_khop.py` (Theil-Sen) | **MEDIUM** | **chưa agent nào kiểm chứng phần toán hồi quy** |
| `audfprint-master/` | **MEDIUM** | vendored — sửa là mất khả năng đối chiếu upstream |
| `cap_nhat.py` | **MEDIUM** | ship tới mọi máy qua `git tag && push` |

---

## 23. Safe Extension Points

Có thể mở rộng **ngay hôm nay**, đều là module thuần logic, không side effect, test tốt:

* `chap_nhan_khop.py` — thêm bậc chấp nhận
* `toc_do_khop.py` — thêm chiến lược ước lượng tốc độ *(nhưng xem §22)*
* `publication_date.py` — thêm nguồn ngày
* `clip_metadata.py` **phần phân giải** *(không phải phần ưu tiên nguồn)*
* `scan_ui.py`, `chan_doan_quet.py` — trình bày và chẩn đoán
* `bang_ngang.py`, `dossier.py` — **chỉ khi không đổi số cột**
* `cli.py` — thêm subcommand

**Chưa an toàn cho tới khi các điều kiện tiên quyết ở §24 xong:** bất cứ thứ gì chạm
phân giải metadata, danh tính tác phẩm, schema lịch sử quét, hoặc bề mặt điều khiển quét.

---

## 24. Recommended Roadmap

Cân xứng với thực tế: đây là **công cụ desktop một người dùng trên Windows**. Không đề xuất
microservice, Redis, Celery hay Kafka.

### Phase A — Khôi phục cổng kiểm tra (nửa ngày, không rủi ro)

1. `.venv\Scripts\python.exe -m pip install -r requirements-dev.txt` — để runtime **test**
   trùng runtime **ship**.
2. Thêm `|| echo [X]` vào `kiemtra.bat:18` và `:22` để bước test **có thể báo lỗi**.
3. Cô lập bước 3/3 bằng `TIMCLIP_DATA_DIR` để nó thôi chạy vào `data/` production.
4. Chạy lại cả fast **và** slow suite trên `.venv`, ghi baseline thật.
5. `git switch -c <nhánh>` để thoát detached HEAD.

*Không có bước nào ở Phase A đụng vào logic nghiệp vụ.*

### Phase B — Trả lời bốn câu hỏi thiết kế đang chặn (thảo luận, chưa code)

1. **Snapshot hay `clips_meta.json` là chủ?** (P1 #1) — quyết định rồi mới viết lại
   `tests/test_clip_metadata.py:229-266`.
2. **"Dừng" nghĩa là gì giữa lô?** (P1 #3) — phải không làm hỏng `watch.py`, vốn được pin
   bởi `tests/test_dung_lai.py:92-134`.
3. **Đường quét có được miễn `tool.lock` không?** — sửa code hay sửa `CLAUDE.md:76-80`.
4. **Một khiếu nại nên chứa bao nhiêu đoạn?** — `top_n` tới 50 vs `SO_DOAN = 5`.

### Phase C — Vá an toàn, chi phí thấp (một dòng mỗi cái)

* `ChayTool.bat:46` → bind `127.0.0.1` (AUD-222)
* `dong_goi.py:55-56` + `.dockerignore` → loại `cookies.txt` (AUD-221/181)
* `app.py:485,503-565` → thêm `disabled=job["running"]` (P1 #4)
* `sheets.py:150` → đặt timeout cho request Sheets (AUD-X13)

### Phase D — Mang chiều "danh tính + phạm vi" xuyên pipeline

Đây là phần gốc rễ. Bốn P1 và phần lớn P2 tan biến khi làm xong:

* thêm cột `kho` vào `jobs`, cho `ids_da_quet` một tham số kho có mặc định (P1 #6)
* neo trích ID vào token cuối trước phần mở rộng (P1 #2)
* đưa phạm vi đã quét vào `HoSo` và dòng xuất (P1 #5)
* dựng **bề mặt cảnh báo** cho scan thành công (AUD-X31) — mở khoá luôn AUD-025, AUD-166

### Phase E — Tính năng mới

Works Registry và đa khách hàng chỉ nên bắt đầu **sau Phase D**.

---

## 25. Next Recommended Task

> ### Chạy `py -3 kiem_metadata_kho.py --json` và đọc `audit.conflicts`.

**Chỉ một lệnh, read-only** (`kiem_metadata_kho.py:290`), vài giây.

**Vì sao đây là việc giá trị nhất, trước cả Phase A:**

Nó trả lời câu hỏi duy nhất quyết định thứ tự mọi việc còn lại — **P1 #1 đang xảy ra hay
chỉ tiềm ẩn?** Nếu `conflicts` rỗng, việc sửa ưu tiên metadata là phòng ngừa và có thể xếp
sau Phase A. Nếu nó liệt kê `conflict:title` / `conflict:upload_date` / `conflict:duration`
trên các kho thật, thì **những hồ sơ bản quyền đã xuất ra đang mang số liệu sai ngay lúc
này**, và mọi thứ khác phải xếp sau.

Vòng audit này bị cấm đọc `data/` nên không thể tự trả lời. Đó là khoảng trống duy nhất mà
một lệnh đóng lại được.

---

## 26. Files Created/Modified

**Mã nguồn: KHÔNG THAY ĐỔI.** Chỉ thêm tài liệu.

| File | Trạng thái | Lý do |
|---|---|---|
| `docs/PROJECT_MASTER_AUDIT.md` | **mới** | tài liệu này |
| `docs/SYSTEM_MAP.md` | **mới** | sơ đồ luồng |
| `docs/MODULE_MAP.md` | **mới** | bảng sở hữu module |
| `docs/DATA_FLOW.md` | **mới** | biến đổi dữ liệu, hệ quy chiếu thời gian |
| `docs/FUTURE_DEVELOPMENT_READINESS.md` | **mới** | đa khách hàng, Works Registry |
| `docs/CLAUDE_HANDOFF_2026-09.md` | **mới** | bàn giao (bản cũ `CLAUDE_HANDOFF.md` **giữ nguyên**) |

Không file `.py`, `.bat`, `.gs`, `.json`, `.toml`, `.ini` nào bị sửa.
Không file nào dưới `data/`, `bin/`, `ketqua/` bị đụng tới.

---

## 27. Git Final State

```
$ git status --short
?? TimClipPro/docs/CLAUDE_HANDOFF_2026-09.md
?? TimClipPro/docs/DATA_FLOW.md
?? TimClipPro/docs/FUTURE_DEVELOPMENT_READINESS.md
?? TimClipPro/docs/MODULE_MAP.md
?? TimClipPro/docs/PROJECT_MASTER_AUDIT.md
?? TimClipPro/docs/SYSTEM_MAP.md

$ git diff --stat      # rỗng — không file được theo dõi nào bị sửa
$ git diff --check     # rỗng
```

Toàn bộ thay đổi là **file mới, chưa được theo dõi, nằm trong `docs/`**.
Không có gì được commit. Không có gì được push.

---

## 28. Production Readiness Verdict

# READY FOR LIMITED FEATURE DEVELOPMENT

Ba critic độc lập, xuất phát từ ba góc khác nhau (bao phủ, chặt chẽ, săn defect), đều đi
tới đúng kết luận này.

**Vì sao không phải `NOT READY`:**

Các defect **có giới hạn, gọi được tên, và định vị được** — không lan toả. Không có gì
sinh dữ liệu sai trên đường mặc định ngoại trừ việc che metadata, mà chuyện đó **có giới
hạn, có phát hiện được** (`resolver.conflicts`) và **phục hồi được bằng cách xoá một file**.
Đường commit kho vân tay thực sự an toàn. Lịch sử ghi theo từng video nên crash mất tối đa
một kết quả. Hai mục nghe đáng sợ nhất — UI mở ra LAN và lỗ hổng đóng gói cookies.txt —
đều là sửa một dòng, và hiện **chưa có phơi nhiễm thực tế**. Phần lớn cây mã — các module
thuần logic và các bộ render báo cáo — được test tốt, không side effect, và **an toàn để
mở rộng ngay hôm nay**.

**Vì sao không phải `STRUCTURED`:**

Hai lý do, cả hai đều cụ thể.

*Thứ nhất*, **cổng kiểm chứng không thể báo lỗi.** Không CI, `kiemtra.bat` không có guard
thất bại, pytest vắng mặt trong venv mà chính nó trỏ tới, và hai môi trường đang cho hai
câu trả lời khác nhau về việc bộ test có xanh hay không. Không thể chạy một quy trình có
cấu trúc trên một cái cổng xanh do cấu trúc.

*Thứ hai*, **bốn trong sáu P1 là câu hỏi thiết kế chưa có lời đáp, không phải task code**:
kho nào là chủ, một khiếu nại đóng băng danh tính gì, `Engine` có được chia sẻ không, và
"dừng" nghĩa là gì giữa chừng một lô. Ship tính năng lên nền móng chưa quyết chính là cách
mà tình trạng hai kho metadata hiện tại đã hình thành ngay từ đầu.

**Đọc theo hướng thực dụng:**

* **An toàn ngay:** báo cáo, chẩn đoán, tiện dụng CLI, tài liệu, đóng gói, và các module
  thuần logic ở §23.
* **Chặn cho tới khi Phase B trả lời xong:** bất cứ thứ gì chạm mốc thời gian, link nhảy,
  ưu tiên metadata, danh tính tác phẩm, schema lịch sử, hoặc bề mặt điều khiển quét.
* **Chặn cho tới khi Phase D xong:** Works Registry và mọi thứ đa khách hàng.

Số finding cao ở đây phản ánh **độ sâu của vòng audit**, không phải codebase kém. 117 trong
162 mục là P3. Không có P0. Với một dự án 15.000 dòng do một người phát triển, mang dữ liệu
production thật và sinh ra bằng chứng pháp lý, đây là kết quả **trên trung bình**.

---

*Vòng audit read-only, 2026-09-07. 227 agent, 141 finding thô, thẩm định đối kháng loại bỏ
7 và thu hẹp phần lớn số còn lại. Không một file mã nguồn nào bị sửa.*
