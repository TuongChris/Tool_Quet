# CLAUDE_HANDOFF — 2026-09-07

> Tài liệu bàn giao sau vòng audit read-only 2026-09-07. Viết cho một kỹ sư **chưa từng
> thấy repo này**. Mọi khẳng định đều kèm `file:dòng`. Đây là tài liệu MÔ TẢ hiện trạng và
> ĐỀ XUẤT hướng đi — **không có thay đổi mã nguồn nào được thực hiện trong vòng này**.
>
> Tài liệu này **thay thế** `docs/CLAUDE_HANDOFF.md` (2026-08-07 → 2026-08-08) làm điểm
> khởi đầu. File cũ vẫn giữ nguyên vì nó chứa các giả thuyết bị bác bỏ và số đo lịch sử
> có giá trị; xem §10 để biết những khẳng định nào của nó nay đã lỗi thời.

---

## 0. Cập nhật 2026-10-02 — vòng hardening sau audit độc lập `4b7e5bd`

> Đọc mục này trước. Phần còn lại của file mô tả hiện trạng 2026-09-07; những gì mục này nói
> khác đi là bản mới hơn.

- **Baseline:** `4b7e5bd` (nhánh `sua-watchdog-van-tay`), trùng revision audit. Baseline test
  trên interpreter của app: 955 passed + 1 skipped; slow 5 passed.
- **Nơi làm:** worktree `…\ToolQuet\Tool_Quet_hardening`, nhánh `hardening-sau-audit`.
  **Chưa commit, chưa push.** Thư mục chạy thật `Tool_Quet\TimClipPro` không bị sửa.
- **Đã xong:** G1–G10, cả 16 mục TCP-01…TCP-16 `FIXED_AND_VERIFIED` trên Windows native. Chi tiết:
  `docs/HARDENING_FIX_MATRIX.md` (từng mục, test, rủi ro), `docs/HARDENING_PLAN.md` (quyết định),
  `docs/HARDENING_VALIDATION_REPORT.md` (bằng chứng), `docs/DATA_MIGRATION_AND_RECOVERY.md`.
- **Module mới:** `process_runner.NhomTienTrinh`/`chay_lenh_media` (Job Object, timeout/huỷ FFmpeg),
  `luu_tru.cap_nhat_json`/`khoa_json` (giao dịch JSON liên tiến trình), `lich_su.py` (lược đồ
  `lichsu.db` có phiên bản), sổ phạm vi quét trong `engine.py`, `ChannelSync.kiem_tep_tren_dia`.
- **Bất biến mới (đừng phá):** job chạy trên bản Engine ghim kho/cấu hình; kho tạm phải qua
  `_kiem_kho_tam` mới được thay kho; mọi đọc-sửa-ghi JSON đi qua `cap_nhat_json`; một lượt quét
  chỉ "trọn" khi hợp vùng đã khớp phủ hết video; mốc khi bù tốc độ là `O + k·(t_khúc − t_clip)`;
  lịch sử chỉ chặn quét lại trong cùng `kho_id`; `clips_meta.json` là nguồn chuẩn metadata;
  mã video trong tên file chỉ ở hậu tố `[ID].đuôi`; đồng bộ kênh nén vào staging rồi mới công bố.
- **Vòng phản biện 2 (đọc trước khi sửa phạm vi quét):** khúc audfprint lỗi đọc CHỈ nhận qua dòng
  stdout `Error reading` (+ khúc 0 hash mà WAV không đọc được). `NOMATCH … 0.0 sec` KHÔNG phải lỗi
  — khúc im lặng cũng ghi vậy (audfprint lấy "độ dài" từ mốc hash cuối); vòng 1 từng hiểu sai và
  biến video tắt tiếng thành lỗi vĩnh viễn. Test giả của audfprint phải mô phỏng đúng
  `audfprint_analyze.py`/`audfprint_match.py` và có đối chứng THẬT (`-m slow`). Các bất biến thêm:
  sổ bù tốc độ theo (lượt, mốc); độ dài tham chiếu của đồng bộ kênh chỉ từ nguồn bên ngoài (không
  `duration_media`); thiếu đuôi khi tải → tải lại MỘT lần để phân biệt tải đứt/âm thanh ngắn thật;
  sổ kho từng hỏng (`khos.json.hong.*`) → không tự dựng «Kho mặc định»; «Bổ sung» so với
  `moc_build`, gỡ clip đã vào `_hong/`, giữ clip vắng không rõ lý do. Bảng đầy đủ: ma trận, mục
  *Vòng phản biện 2*.
- **Vòng phản biện 3:** với ncores > 1 các worker audfprint ghi CHUNG stdout nên dòng xen nhau —
  mọi bộ đọc stdout của audfprint phải neo vào cụm từ (`RE_LOI_DOC_KHUC`, `finditer`), không lấy
  "khúc đầu tiên của dòng". Khúc 0 hash mà có tiếng rõ (độ lệch chuẩn > −50 dBFS — đo quanh trung
  bình, lệch DC hằng số là im lặng) = chưa phân tích. Độ dài
  luồng tiếng chỉ tin khi file có đúng một luồng tiếng (`channel.doc_moc_het_tieng`). Sổ kho hỏng
  hoặc mất-còn-`.bak` → `SoKhoHong` chặn mọi quét/build. «Bổ sung» chỉ gỡ clip đã cách ly khi bản
  thay thế cùng mã đã có vân tay. Lần tải lại kiểm chứng của đồng bộ kênh vào thư mục mới. Bảng:
  ma trận, mục *Vòng phản biện 3*.
- **Lệnh kiểm (đã chạy thật):** `kiemtra.bat` với `KIEMTRA_PY` trỏ interpreter có pytest → mã
  thoát 0; `python -m pytest -q` (nhanh) và `python -m pytest -m slow` (cần `bin\` trong PATH).
  CLI báo bận bằng mã thoát 2.
- **Đang chờ người dùng duyệt:** đưa code vào thư mục chạy thật (lần mở đầu tự nâng cấp
  `lichsu.db`, có sao lưu); quy trình ở `DATA_MIGRATION_AND_RECOVERY.md` mục 8.
- **Việc tiếp theo:** nghiệm thu vận hành có kiểm soát trên máy thật (một Watch nhỏ, một lần đồng
  bộ kênh, một build `add`), rồi mới thiết kế "nguồn chung cả lô"/multi-client.

## Mục lục

1. [Repository state](#1-repository-state)
2. [Environment reality](#2-environment-reality)
3. [Architecture in one page](#3-architecture-in-one-page)
4. [Invariants — không được phá](#4-invariants--không-được-phá)
5. [Dangerous areas](#5-dangerous-areas)
6. [Test architecture](#6-test-architecture)
7. [Operational safety notes](#7-operational-safety-notes)
8. [Findings](#8-findings--danh-sách-đã-thẩm-định)
9. [Next recommended task](#9-next-recommended-task)
10. [Những gì trong CLAUDE_HANDOFF.md cũ nay đã lỗi thời](#10-những-gì-trong-claude_handoffmd-cũ-nay-đã-lỗi-thời)
11. [Câu hỏi còn treo](#11-câu-hỏi-còn-treo-cần-người-quyết-định)

---

## 1. Repository state

| Hạng mục | Giá trị | Bằng chứng (đọc trực tiếp vòng này) |
|---|---|---|
| Đường dẫn làm việc | `C:/Users/Admin/OneDrive/Desktop/ToolQuet/Tool_Quet/TimClipPro` | — |
| **Gốc git là THƯ MỤC CHA** | `C:/Users/Admin/OneDrive/Desktop/ToolQuet/Tool_Quet` | `.git/` nằm ở `Tool_Quet/`, không ở `TimClipPro/` |
| Remote | `git@github.com:TuongChris/Tool_Quet.git` (SSH) | `.git/config:9` |
| **HEAD** | `7f85c8d22e33d61c09961cc30afcb9bf35539f00` — **DETACHED** | `.git/HEAD` chứa SHA trần, không phải `ref: refs/heads/...` |
| Tag tại HEAD | `v2.6` (annotated tag, object `961b3466…`) | `.git/refs/tags/v2.6`; `git describe --tags --exact-match` → `v2.6` (baseline round) |
| Nhánh `main` | `f4ae37a` — **sau HEAD 2 tag** (`f4ae37a` cũng chính là `v2.4`) | `.git/refs/heads/main`, `.git/packed-refs:10` |
| `origin/main` | `f4ae37a` — trùng `main` cục bộ | `.git/refs/remotes/origin/main`, `.git/packed-refs:2` |
| Working tree | **sạch** trước và sau khi chạy test | `scratchpad/audit/baseline.md:46-48` (`git status --short`, `git diff --stat`, `git diff --check` đều rỗng) |

### Detached HEAD nghĩa là gì với người sắp commit

**Đây là trạng thái ĐÚNG THIẾT KẾ, không phải checkout hỏng.** `cap_nhat.py:215` chạy
`git checkout --quiet <tag>` để cập nhật theo tag phát hành, và tag là ref không phải
branch — nên máy người dùng *phải* ở detached HEAD. Reflog của chính repo này ghi lại
`checkout: moving from main to v2.6`.

Hệ quả cụ thể nếu bạn commit ngay bây giờ:

1. **Commit sẽ không thuộc nhánh nào.** Nó chỉ được giữ bởi reflog. `git checkout main`
   sau đó sẽ in "you are leaving N commits behind" và commit của bạn trở nên khó tìm.
2. **`main` cục bộ đang ở `v2.4`, tụt 2 tag so với `v2.6` bạn đang đứng.** Đừng
   `git checkout main` rồi commit lên đó — bạn sẽ commit lên một cây nguồn cũ hơn cây
   bạn vừa đọc.
3. **Quy trình đúng:** `git switch -c <tên-nhánh-mới>` từ HEAD hiện tại (giữ nguyên
   `v2.6` làm base), làm việc, rồi merge/PR về `main`. Hoặc `git fetch && git switch main
   && git merge --ff-only origin/main` trước, nếu remote đã đi tiếp.
4. **Máy này vừa là máy dev vừa là máy chạy.** Guard chống-lùi của updater
   (`cap_nhat.py:141-152`) chỉ chặn khi HEAD **đi trước** tag mới nhất; khi HEAD ở ngang
   hoặc sau tag thì nó vẫn checkout và sẽ tách HEAD khỏi nhánh bạn đang làm việc — xem
   **AUD-184**. Nếu bạn đang làm dở trên một nhánh, **đừng để `ChayTool.bat` chạy**
   (nó gọi `cap_nhat.py` ở `ChayTool.bat:33` trước khi mở UI); dùng
   `ChayTool.bat --da-cap-nhat` để bỏ qua bước cập nhật (`ChayTool.bat:30` là guard, đã
   có sẵn, chỉ chưa được ghi tài liệu ở đâu cả).

---

## 2. Environment reality

**Có HAI môi trường Python trên máy này, và chúng khác nhau ở những thư viện dễ vỡ nhất.**

| | `.venv` | `py -3` |
|---|---|---|
| Python | **3.12.10** (`.venv/pyvenv.cfg:3`) | **3.14.3** |
| `include-system-site-packages` | `false` (`.venv/pyvenv.cfg:2`) — không có fallback | — |
| **pytest** | **KHÔNG CÓ** (kiểm trực tiếp: `.venv/Lib/site-packages/pytest/` không tồn tại) | **9.1.1** |
| **ruff** | **KHÔNG CÓ** (`.venv/Lib/site-packages/ruff/` không tồn tại) | **KHÔNG CÓ** |
| streamlit | 1.62.0 | 1.60.0 |
| pyarrow | 25.0.1 | 24.0.0 |
| **yt-dlp** | **2026.8.19** (bản phát hành) | **2026.7.23.234303.dev0** (bản **dev**) |
| numpy | 2.5.2 | 2.5.1 |
| google-auth | 2.56.3 | 2.56.2 |

Nguồn bảng: `scratchpad/audit/baseline.md:51-60`. Hai dòng in đậm về pytest/ruff và dòng
Python 3.12.10 đã được kiểm lại trực tiếp trong vòng viết tài liệu này.

### Dùng cái nào cho việc gì

| Việc | Interpreter | Lý do |
|---|---|---|
| **Chạy ứng dụng** (`ChayTool.bat`, `GiamSat.bat`, `ChayMayPhu.bat`) | **`.venv` (3.12.10)** | `ChayTool.bat:11` gán `PY=.venv\Scripts\python.exe` nếu file tồn tại; nó tồn tại, nên nhánh `py -3.12`/`py -3` ở dòng 12-13 (có guard `if not defined PY`) **không bao giờ chạy** |
| **Chạy test** | **`py -3` (3.14.3)** — bắt buộc, vì `.venv` không có pytest | `py -3 -m pytest` |
| **Chạy ruff** | Không có sẵn ở đâu cả | Baseline dùng binary `ruff 0.16.2` trong cache uv (`baseline.md:23-26`) |
| **`kiemtra.bat`** | **KHÔNG DÙNG ĐƯỢC** | `kiemtra.bat:8` ghim `PY` vào `.venv`, mà `.venv` không có pytest → bước 2/3 in `No module named pytest` và **đi tiếp**, vì `kiemtra.bat:18` không có `\|\| echo [X]` như dòng 14 |

### Vì sao sự chia rẽ này TỰ NÓ là một rủi ro

Bằng chứng bytecode: file đã biên dịch trên đĩa là
`tests/__pycache__/conftest.cpython-314-pytest-9.1.1.pyc` — tức **bộ test đã chạy trên
CPython 3.14 với pytest 9.1.1**, không phải trên `.venv`. `ruff.toml:1` lại đặt
`target-version = "py312"`.

Nghĩa là: **mã CHẠY bằng một môi trường, được TEST bằng một môi trường khác.** Điều đó
làm baseline "952 passed" không chứng minh gì về runtime thật, và nó nguy hiểm nhất ở
đúng ba thư viện:

- **yt-dlp lệch hẳn một bản dev** (`2026.8.19` vs `…dev0`). yt-dlp là cổng duy nhất cho cả
  6 chỗ dựng `YoutubeDL` (`engine.py:1480, 2014, 2127`; `channel.py:377, 419, 490`), và
  bản dev khác bản phát hành đúng ở phần extractor/player-client — chính là nơi
  AUD-101…AUD-105 nằm.
- **pyarrow 24 vs 25.** Lỗi dtype của PyArrow từng làm sập cả trang kết quả (CLAUDE.md
  mục 7); `tests/test_bang_ket_qua_arrow.py:56-60` cố tình giữ một test khẳng định đường
  chưa-sửa VẪN ném `ArrowInvalid` — hành vi đó phụ thuộc phiên bản pyarrow.
- **streamlit 1.60 vs 1.62.** 13 test render `app.py` thật qua `AppTest`.

Xem **AUD-X26** và **AUD-245**.

---

## 3. Architecture in one page

### Sơ đồ lớp

```
  ChayTool.bat        GiamSat.bat / ChayMayPhu.bat        cai_dat.bat / CapNhat.bat
  (Streamlit UI)      (Task Scheduler, headless)          (cài đặt / tự cập nhật)
        │                        │                                  │
        ▼                        ▼                                  ▼
     app.py  ──────────────►  cli.py  ──────►  watch.py          cap_nhat.py
   (78 KB, 6 tab)          (10 lệnh)        (một lượt quét)     (git tag)
        │                        │                │
        └──────────┬─────────────┴────────────────┘
                   ▼
              engine.py   ◄── LÕI. Không import streamlit, không print, không input.
              (~3.400 dòng)    Mọi tiến độ qua callback progress(pct, msg).
                   │
   ┌───────────────┼────────────────┬─────────────┬──────────────┐
   ▼               ▼                ▼             ▼              ▼
channel.py    ytdlp_chung.py   clip_metadata  chap_nhan_khop  audfprint-master/
(đồng bộ kênh) (MỌI option      (định danh    toc_do_khop     (MIT, ĐỪNG SỬA —
               yt-dlp đi qua     clip gốc)    chan_doan_quet   bọc qua
               đây)                                           audfprint_progress_runner.py)
   │                                              │
   ▼                                              ▼
sheets.py / sheet_delivery.py               bang_ngang.py / dossier.py
(Google Sheets)                             (34 cột / hồ sơ khiếu nại Markdown)
```

Hạ tầng dùng chung: `luu_tru.py` (ghi JSON nguyên tử + `.bak` + cách ly file hỏng),
`khoa.py` (khoá liên tiến trình cấp OS), `cau_hinh.py` (persist Config),
`process_runner.py` (giám sát subprocess), `fingerprint_progress.py` /
`scan_jobs.py` / `scan_ui.py` (job control + snapshot bất biến cho UI),
`don_dep.py` (GC), `nhat_ky.py` (log), `dung_lai.py` (tín hiệu dừng cho CLI),
`publication_date.py` (nguồn chân lý duy nhất cho ngày đăng).

### Đường đi của một lượt quét YouTube

`app.py:1438` → `chay_quet` (`app.py:95`) → `ScanJobController.start` (`scan_jobs.py:169`,
tạo thread daemon `scan-<hex>` ở `scan_jobs.py:198`) → `Engine.scan_iter`
(`engine.py:3224`) → mỗi video:

1. `Engine.scan_youtube` (`engine.py:3145`) → `youtube_info` (`engine.py:2014`, **1 request
   metadata**) → `_gioi_han_tai` (`engine.py:2790`) → `download_audio` (`engine.py:2127`)
2. `Engine.scan_media` (`engine.py:3043`) trong workspace riêng
   `data/scan_jobs/<uuid4>/` (`engine.py:2229`, xoá ở `finally` dòng 2233-2234)
3. `_cut_chunks` (`engine.py:2236`) → ffmpeg → WAV mono 11025 Hz
4. `_quet_tho` (`engine.py:2735`) → `_match_chunks` (`engine.py:2283`) → subprocess
   `audfprint match` qua `_run_stream` (`engine.py:914`, ép `PYTHONUTF8=1`)
5. `_merge` (`engine.py:2395`) → `_gan_chi_so` (`engine.py:2535`) →
   `chap_nhan_khop.loc_chap_nhan` → `_chon_loc` (`engine.py:2545`)
6. `save_job` (`engine.py:3142` / `3221`) — **ghi SQLite NGAY, trước callback**
7. `on_video` (`engine.py:3254`, exception bị nuốt + log ở 3255-3258) → `app.py:113`
   `sau_moi_video` → `to_rows_ngang` → `SheetDeliveryWorker.enqueue`

**Báo cáo:** `Engine.to_rows` 16 cột (`engine.py:3317-3322`),
`bang_ngang.dung_dong_ngang` 34 cột (`bang_ngang.py:14-49`, `SO_DOAN = 5`),
`dossier.dung_ho_so` Markdown. Cả ba **resolve metadata offline**, không gọi mạng.

### Ba tầng lưu trữ metadata clip gốc — điểm hợp lưu quan trọng nhất

| Nguồn | Priority | Ai ghi |
|---|---|---|
| `data/metadata/kho_<slug>.json` (snapshot) | **0 — THẮNG** (`engine.py:1122`) | `Engine.khoi_phuc_metadata_offline` (`engine.py:1400`), `Engine.va_metadata_thieu` (`engine.py:1621`), tự động sau mỗi lần dựng kho (`engine.py:1803`, `1976`) |
| `<kho>/clips_meta.json` (live) | 10 (`engine.py:1124`) | `ChannelSync.sync`/`va_metadata` (`channel.py:592-605`), `kiem_ngay_dang.py:229`, `kiem_thoi_luong.py:135` |
| `<thư mục DB>/clips_meta.json` | 20+ (`engine.py:1133`) | — (legacy) |
| `data/clips_meta.json` | 100, **chỉ khi** kho tên `""` hoặc `"Kho mặc định"` (`engine.py:1137`) | — (legacy) |

Quy tắc gộp: `_merge_entries` (`clip_metadata.py:549-558`) sắp theo
`(_entry_quality, priority, source_file, key)` rồi lấy `ordered[0]`; nguồn sau **chỉ được
điền vào ô TRỐNG** (`clip_metadata.py:591-592`), giá trị khác nhau thì ghi
`conflict:<field>:<key>` (`clip_metadata.py:601`). `_entry_quality`
(`clip_metadata.py:541-546`) chỉ hạ điểm entry gắn `filename_fallback`/`basename_fallback`.

**Đây là gốc của P1 lớn nhất trong tài liệu này** — xem §5.1.

---

## 4. Invariants — không được phá

Danh sách đã thẩm định. Mỗi mục có `file:dòng` và, khi có, test khoá lại.

### 4.1 Kiến trúc

| # | Bất biến | Bằng chứng |
|---|---|---|
| I-1 | `engine.py` không `import streamlit`, không `print()`, không `input()`; tiến độ chỉ qua `progress(pct, msg)` | `engine.py:904-908` (`_bao`, kẹp pct về `[0,1]`); khoá bằng `tests/test_scan_thread_boundary.py:56-57` |
| I-2 | `scan_jobs.py`, `sheet_delivery.py`, `scan_ui.py` không import streamlit và không đọc `st.session_state` | `tests/test_scan_thread_boundary.py:48-53`; guard tokenize source nên docstring bàn về Streamlit không thành false positive, và có **meta-test** chứng minh guard bắt được (`:59-70`) |
| I-3 | `audfprint-master/` là thư viện bên thứ ba, **không sửa**; đổi hành vi thì monkey-patch lúc chạy | `audfprint_progress_runner.py:307-318` cài đúng ba điểm vá |
| I-4 | **Mọi** dict option `yt_dlp.YoutubeDL` đi qua `CauHinhMang.tuy_chon()` | `ytdlp_chung.py:339`; 6 chỗ dựng: `engine.py:1480, 2014, 2127`; `channel.py:377, 419, 490` |
| I-5 | Mọi subprocess Python đi qua `Engine._run_stream`, ép `PYTHONUTF8=1` / `PYTHONIOENCODING=utf-8` / `-u` | `engine.py:914-957`. Bỏ qua = tái hiện `UnicodeDecodeError` trên Windows tiếng Việt (CLAUDE.md mục 1) |

### 4.2 Dữ liệu & định danh

| # | Bất biến | Bằng chứng |
|---|---|---|
| I-6 | Không bao giờ `os.remove()` trực tiếp lên `.pklz` — dùng `Engine._xoa_an_toan` | `engine.py:1059-1078` |
| I-7 | Không bao giờ dựng `hash_table.HashTable(path)` ở tiến trình cha — dùng `db_clips()`, đọc gzip vào RAM trong `with` rồi mới unpickle | `engine.py:1038-1043`; lý do ở comment `engine.py:1010-1019` (rò handle → WinError 32) |
| I-8 | Tên `.pklz` đọc từ `khos.json` phải qua `Engine._duong_dan_db_kho`: chỉ basename, chỉ `.pklz`, `commonpath` phải nằm trong `data_dir` | `engine.py:743-765`; khoá bằng `tests/test_security_regressions.py:15-24` |
| I-9 | Dựng tên file từ dữ liệu người dùng phải dùng `luu_tru.ten_file_hop_le` (hàm ĐƯỜNG DẪN), **không** `fingerprint_progress.ten_file_an_toan` (hàm HIỂN THỊ) | `luu_tru.py:40-56` vs `fingerprint_progress.py:41-45`; dùng nhầm → NTFS Alternate Data Stream, `glob("*.json")` không thấy (CLAUDE.md mục 15d) |
| I-10 | Ghi JSON: copy `.bak` → ghi `.tmp` → `flush` → `fsync` → `os.replace` | `luu_tru.py:85-92` |
| I-11 | Không thêm trường chứa BÍ MẬT vào `Config`: `cau_hinh.lay_tu_config` serialize **mọi** field không có allowlist — nên cookie chỉ lưu ĐƯỜNG DẪN | `cau_hinh.py:70-72`; `engine.py:146-151` |
| I-12 | Mọi field `Config` phải là `str/int/float/bool/list` thuần, **không** `Optional`: `ap_vao_config` so kiểu bằng `type(x) is not type(y)` | `cau_hinh.py:63`; comment `engine.py:148-149` |
| I-13 | `Config.validate()` không được chạm hệ thống file — nó nằm trong `try` mà `except` xoá sạch toàn bộ config | `engine.py:693-700` |

### 4.3 Ngữ nghĩa thời gian & so khớp

| # | Bất biến | Bằng chứng |
|---|---|---|
| I-14 | `hhmmss` **cắt**, không làm tròn; phải khớp với `link_moc` vốn dùng `int(giay)` | `engine.py:407-431`, `engine.py:3335-3342` |
| I-15 | Thời gian VẬN HÀNH (elapsed/ETA) dùng `app._thoi_luong`, không dùng `hhmmss` | `app.py:188-192`; nêu rõ ở `engine.py:425-427` |
| I-16 | Chỉ `publication_date.format_publication_date` được sinh chuỗi `DD/MM/YYYY` | `publication_date.py:251-264`; khoá bằng `tests/test_publication_date_exporters.py:90-102` |
| I-17 | Chỉ `publication_date.py` được quy đổi epoch → ngày; epoch phải dựng với `timezone.utc` rồi mới `astimezone` | `publication_date.py:150`; khoá bằng `tests/test_publication_date_exporters.py:118-129` |
| I-18 | `clip_bat_dau_s` / `vung_khop_s` / `clip_offset_s` là ba khái niệm khác nhau, không thay thế nhau | `engine.py:335-347`; CLAUDE.md mục "Ý nghĩa các trường thời gian" |
| I-19 | `clips_meta.json["duration"]` (lengthSeconds đã làm tròn) không bao giờ bị ghi đè; giá trị đo được nằm ở key riêng `duration_media` | `kiem_thoi_luong.py:38, 115`; `channel.py:602-603` |
| I-20 | `ScanResult.pham_vi_quet_s` phải tách khỏi `duration_s`; sửa `duration_s` thì phải rà lại MỌI thứ tính từ nó | `engine.py:384-396`; bài học ở CLAUDE.md mục 13 |
| I-21 | `_cut_chunks` tính lưới mốc từ giây 0 của **cả file** rồi mới LỌC theo cửa sổ — để quét tăng dần và quét trọn cho cùng một lưới | `engine.py:2263-2269` |
| I-22 | Không bao giờ thêm lại `--sortbytime` vào lệnh `audfprint match`: `--max-matches` cắt SAU khi sắp lại, nên bật vào là giữ dòng muộn nhất thay vì mạnh nhất | `engine.py:2289-2303` |
| I-23 | `_deu_la_nhac_hieu` đòi **MỌI** ứng viên dưới ngưỡng **và** có **≥2** ứng viên. Xét theo ứng viên mạnh nhất là SAI | `chan_doan_quet.py:246-259`; khoá bằng `tests/test_chan_doan_zero_match.py:429` |
| I-24 | `_du_de_dung_som` đếm **CLIP KHÁC NHAU** khi bật `uu_tien_clip_khac_nhau`, không đếm mảnh | `engine.py:2884-2886` |
| I-25 | Quét tăng dần chỉ đổi THỨ TỰ, không đổi ĐỘ PHỦ: không thấy gì thì phải quét hết | khoá bằng `tests/test_quet_tang_dan.py:151` |
| I-26 | Bậc B của `chap_nhan_khop` chỉ THÊM ứng viên, không bao giờ bớt (bậc A `return` trước) | `chap_nhan_khop.py:90-96` trước `:103` |
| I-27 | `mat_do_bac_a` là tham số DUY NHẤT trong nhóm chấp nhận có thể LẤY ĐI kết quả — phải tách riêng khỏi `mat_do_toi_thieu`, và `validate()` phải tiếp tục chặn > 9.0 | `engine.py:197-203`, `engine.py:305-311` (hiệu chỉnh trên 1.198 match lịch sử, mật độ thấp nhất 9,99 hash/s) |

### 4.4 Báo cáo

| # | Bất biến | Bằng chứng |
|---|---|---|
| I-28 | `len(dung_dong_ngang(kq)) == len(HEADER_NGANG) == 34` với **mọi** đầu vào, kể cả `status != "ok"` | `bang_ngang.py:14-49`, `:75`; khoá bằng `tests/test_bang_ngang.py:56-59` |
| I-29 | `Engine.to_rows` trả đúng `len(Engine.HEADER) == 16` ô ở **cả ba nhánh** (ok / không match / lỗi) | `engine.py:3317-3322`, `:3350-3367` |
| I-30 | `HEADER_NGANG` phải trùng từng ký tự với `kiem_header.CHUAN_33 + [COT_34]` và với `KETQUAQUET_COT_MAC_DINH` trong `apps_script/File01_CauHinh_TienIch.gs:75-110` **và** `TOAN_BO_AppsScript.gs` | đã diff thủ công vòng audit; **không có kiểm tra tự động nào** giữa Python và Apps Script |
| I-31 | Một resolver metadata cho cả lô, không phải mỗi dòng một cái | `engine.py:3346`, `:3389`, `:3423`; khoá bằng `tests/test_bang_ngang.py:196-215` |
| I-32 | Xuất báo cáo **không bao giờ** gọi mạng | `clip_metadata.py:10-22` (chỉ stdlib); khoá bằng `tests/test_publication_date_exporters.py:143-159` |
| I-33 | Mọi ghi Google Sheets dùng `value_input_option="RAW"` — đó là thứ chặn formula injection, không phải escaping | `sheets.py:213, 233, 243, 332`; khoá bằng `tests/test_security_regressions.py:72-95` |
| I-34 | `SheetsExporter.append` **không tự retry** (một lần ghi có thể đã tới Google rồi) | `sheets.py:245-250`; khoá bằng `tests/test_sheets_session.py:230-244` |
| I-35 | `ghi_de` phải `resize` TRƯỚC `update` (values.update không nới lưới) và **từ chối** danh sách rỗng | `sheets.py:260-283`, `:297-298`; caller guard `danh_sach_video.py:621-623` |
| I-36 | Cột trong `Engine.COT_SO` phải được ép kiểu số trước `st.dataframe`, và phải lấy danh sách từ `COT_SO` chứ không viết tay | `engine.py:3331-3332`, `app.py:344-354`; **negative control** ở `tests/test_bang_ket_qua_arrow.py:56-60` khẳng định đường chưa-ép VẪN ném `ArrowInvalid` |

### 4.5 Đồng thời & tiến trình

| # | Bất biến | Bằng chứng |
|---|---|---|
| I-37 | `save_job` chạy **trước** `on_video` — lỗi giao hàng không bao giờ làm mất kết quả quét | `engine.py:3142` / `:3221` trước `:3252-3258` |
| I-38 | `data/tool.lock` khoá byte 0; mô tả chủ khoá nằm từ byte 1 trở đi, **ngoài** vùng khoá, để người chờ đọc được | `khoa.py:19-20`, `:57-59`, `:95-104` |
| I-39 | Liveness của khoá là việc của HĐH — **đừng** thêm heuristic PID/timestamp vào `khoa.py` | khoá bằng `tests/test_khoa.py:57-88` (kill tiến trình con đang giữ khoá rồi lấy lại được) |
| I-40 | Mỗi lượt quét có workspace `data/scan_jobs/<uuid4>` riêng; quay lại `data/chunks` dùng chung là tái hiện lỗi ĐÚNG/SAI (hai lượt xoá chunk của nhau) | `engine.py:2219-2233` |
| I-41 | Mỗi cột của bảng trạng thái quét là dtype `string`, kể cả khung rỗng | `scan_ui.py:95`; khoá bằng `tests/test_scan_ui_schema.py:54-61` |
| I-42 | `"—"` / `"0"` / `"N"` là ba trạng thái KHÁC NHAU ở cột «Đoạn» | `scan_ui.py:87`; khoá bằng `tests/test_scan_ui_schema.py:64-73` |
| I-43 | Chỉ có `top_n` = số ĐOẠN xuất ra, không phải số video gốc | `engine.py:2545-2628` |

### 4.6 Đóng gói & tự cập nhật

| # | Bất biến | Bằng chứng |
|---|---|---|
| I-44 | `cap_nhat.py` không được sinh động từ git phá hoại (`--force`, `stash`, `--hard`, `clean`, `reset`) | khoá bằng AST walk ở `tests/test_cap_nhat.py:130-153` |
| I-45 | `cap_nhat.cap_nhat()` **không bao giờ raise**; mọi lỗi trả `KetQua` | `cap_nhat.py:168-225` |
| I-46 | Mã thoát phải tăng dần: `KHONG_DOI=0 < DA_DOI=10 < DA_DOI_CAN_PIP=11` (vì `if errorlevel N` trong cmd nghĩa là `>= N`) | `cap_nhat.py:244-246`; khoá bằng `tests/test_cap_nhat.py:211-223` |
| I-47 | File `.bat` vừa tự cập nhật **phải** khởi động lại chính nó thay vì chạy tiếp (cmd đọc file theo byte offset) | `ChayTool.bat:27-39`; `cap_nhat.py:250-255` |
| I-48 | Dữ liệu người dùng phải nằm trong `.gitignore` trước khi phát hành, nếu không `git checkout` lúc cập nhật sẽ ghi đè | `.gitignore`; khoá bằng `tests/test_cap_nhat.py:247-253` cho `data/`, `ketqua/`, `bin/`, `google_key.json`, `cau_hinh.json`, `watchlist.json` |
| I-49 | Gói triển khai máy phụ phải xoá `ytdlp_cookiefile` + `ytdlp_cookies_browser` nhưng **giữ** `sheet_link` | `dong_goi_may_chay.py:152-163` |

### 4.7 Một bất biến ĐANG BỊ VI PHẠM

`CLAUDE.md:78-80` viết: *"Mọi thao tác nặng có thể đọc hoặc ghi kho vân tay, lịch sử hay
dữ liệu giám sát phải dùng chung khoá cấp hệ điều hành `data/tool.lock`."*

**Đường quét không lấy khoá.** Kiểm trực tiếp vòng này — chỉ có **4** chỗ lấy
`KhoaTienTrinh` trong mã sản phẩm:

| `engine.py:1436` | khôi phục metadata offline |
| `engine.py:1495` | vá metadata thiếu từ YouTube |
| `engine.py:1690` | dựng kho vân tay |
| `watch.py:287` | một lượt giám sát |

`Engine.scan_media` (`engine.py:3043`) đọc `.pklz` qua audfprint (`engine.py:1655`) và ghi
`data/lichsu.db` qua `save_job` (`engine.py:3273`) mà **không** lấy khoá nào. Xem
**AUD-125** và **AUD-261**: cả hai đều kết luận nên **sửa tài liệu**, không sửa mã, vì
`KhoaTienTrinh` không reentrant (`khoa.py:20`, `:33` đều non-blocking) nên bọc
`scan_media` vào khoá sẽ làm `watch.py:459` tự kẹt. **Đây là quyết định đang treo, chưa ai
chọn** — nghĩa là bất biến quan trọng nhất của dự án hiện đang sai một cách có ý thức.

---

## 5. Dangerous areas

### 5.1 Tầng metadata — hai kho, không ai là chân lý *(P1)*

Snapshot `data/metadata/kho_<slug>.json` đứng **priority 0** (`engine.py:1122`), trước
`clips_meta.json` **priority 10** (`engine.py:1124`). `_merge_entries`
(`clip_metadata.py:549-558`) lấy `ordered[0]` và nguồn sau chỉ được điền ô trống
(`clip_metadata.py:591-592`). `_entry_quality` (`clip_metadata.py:541-546`) chỉ hạ điểm
entry gắn `filename_fallback`/`basename_fallback`, mà `_snapshot_entry`
(`engine.py:1289-1292`) đóng dấu `"exact"` cho mọi clip resolve được — nên snapshot
**luôn thắng**.

Ba công cụ sửa lỗi (`ChannelSync.va_metadata`, `kiem_ngay_dang.py:229`,
`kiem_thoi_luong.py:135`) chỉ ghi `clips_meta.json`. Công cụ thứ tư
(`Engine.va_metadata_thieu`, `engine.py:1621`) chỉ ghi snapshot.

**Cái bẫy khi sửa:** `tests/test_clip_metadata.py:229-268` **khoá lại đúng hành vi này** —
đọc trực tiếp vòng này, nó assert `result.title == "Tiêu đề snapshot"` khi live có title
khác, `result.source_kind == "snapshot"`, và `resolver.conflicts == ["conflict:title:…"]`.
Đảo priority sẽ làm test đỏ **và** vô hiệu hoá `va_metadata_thieu`. Đây là **xung đột yêu
cầu**, không phải bug ngẫu nhiên.

Xung đột **có** được ghi nhận (`clip_metadata.py:601` → `MetadataAudit.conflicts` →
`Engine.canh_bao_metadata` `engine.py:1211-1221`) nhưng **chỉ `kiem_metadata_kho.py:229`
đọc nó**; `app.py` và mọi exporter đều bỏ qua.

**Cách thoát duy nhất hiện nay:** xoá tay `data/metadata/kho_*.json`.

### 5.2 Huỷ tác vụ — một cờ, sáu chỗ xoá *(P1)*

`Engine.cancel_event` là **một** `threading.Event` cho **mọi** loại job (`engine.py:650`),
và bị `clear()` ở **sáu** nơi (kiểm trực tiếp bằng grep vòng này):

`app.py:150`, `app.py:173`, `engine.py:1680`, `engine.py:3056`, `engine.py:3149`,
`scan_jobs.py:193`.

Vì `scan_youtube` xoá cờ ngay đầu hàm (`engine.py:3149`) và `scan_iter` **không kiểm cờ
giữa các video** (`engine.py:3244-3251`), bấm «⏹️ Dừng lại» chỉ huỷ được video đang chạy;
các video còn lại vẫn tải và quét đủ. Nút lại bị `disabled=anh.cancelled` (`app.py:823`)
nên không bấm lại được.

Đường CLI **không** dính lỗi này vì `dung_lai.YeuCauDung` có cờ dính `_da_dat` riêng
(`dung_lai.py:35-40`) sống sót qua `clear()`, và `watch.py:437-448` kiểm nó giữa các video.
`app.py` **không** import `dung_lai`.

Một biến thể nữa: nút Dừng của «Lấy lại tên video thật» hoàn toàn vô tác dụng —
`ChannelSync.va_metadata` (`channel.py:216-345`) không có tham số cancel nào
(**AUD-X06**).

### 5.3 Engine dùng chung giữa main thread và worker *(P1)*

Sidebar Streamlit render **trên** màn hình tiến độ (`app.py:461-681` trước `app.py:688`),
và vòng lặp làm mới là `time.sleep(0.75); st.rerun()` (`app.py:835-836`). Nên trong suốt
một job, sidebar chạy lại ~1,3 lần/giây với widget **không** có `disabled=`:

- `app.py:485-489` — đổi kho: `eng.use_kho(chon)` → `_ap_dung_kho` đổi `self.db_file`
  (`engine.py:794-799`), mà worker đọc lại `self.db_file` ở **mỗi** lần gọi audfprint
  (`engine.py:1655`, từ `engine.py:2334`).
- `app.py:503-565` — mọi tham số tuning.

Hai nút ngay dưới **có** guard `disabled=job["running"]` (`app.py:650`, `:667`), nên thiếu
sót ở selectbox là bất đối xứng rõ ràng, không phải thiết kế.

### 5.4 Định danh clip gốc là TÊN FILE

Khoá join của cả hệ thống là basename: `engine.py:2492` (`Match.clip`),
`engine.py:1049` (`db_clips`), `channel.py:592` (`clips_meta.json`). Mà
`channel._ten_file` (`channel.py:465-469`) dựng tên từ **ngày đăng + tiêu đề đã lọc ký
tự**, hai thứ đều đổi được. Video ID chỉ là **mức 4** của chuỗi resolve
(`clip_metadata.py:898-911`).

Hai lỗ hổng đã xác nhận:

- Một token 11 ký tự trong ngoặc vuông ở giữa tiêu đề (`[Compilation]`, `[Official_MV]`,
  `[4K-REMASTER]` — chính codebase liệt kê ở `danh_sach_video.py:281-291`) khiến
  `_BRACKET_ID_PATTERN` (`clip_metadata.py:25`) tìm ra 2 ID và `resolve` thoát ở bước 0
  (`clip_metadata.py:845-850`) → URL video gốc **rỗng** trong hồ sơ khiếu nại, và
  **không công cụ sửa nào cứu được** (`engine.py:1352-1354`, `:1524`). — **AUD-062**
- File bị đổi tên/copy mất ID dù ID vẫn nằm trong tên, vì mức 6 dò lại bằng pattern chặt
  (`clip_metadata.py:918-919`) thay vì dùng ID mà bước 0 đã có. — **AUD-063**

### 5.5 `data/lichsu.db` không có cột kho *(P1)*

Schema `jobs` — đọc trực tiếp `engine.py:874-878`:

```
id, created_at, source_type, source_name, source_ref,
duration_s, status, n_matches, note, source_id
```

Không có cột kho/khách hàng. `ids_da_quet` (`engine.py:3295-3304`) truy vấn
`SELECT DISTINCT source_id FROM jobs WHERE source_id != '' AND status = 'ok'` — **không có
điều kiện kho**. `watch.py:378-379` dùng tập đó để bỏ qua video.

Hệ quả: một video đã quét cho kho A **vĩnh viễn** không được quét cho kho B. Máy này
có nhiều kho, `WatchList.kho` (`watch.py:27-30`) chọn kho theo từng watchlist, và
`ChayMayPhu.bat:6-9` hướng dẫn chạy nhiều watchlist. — **AUD-X19**

Schema `matches` (`engine.py:882-885`) cũng chỉ lưu basename, không lưu `ty_le`, `vung`,
`clip_bat_dau_s`, `vung_khop_s` — nên 4/16 cột báo cáo không tái tạo được từ lịch sử
(**AUD-064**), và kênh vi phạm + ngày đăng cũng không được persist (**AUD-X01**).

### 5.6 Không có kênh cảnh báo cho lượt quét THÀNH CÔNG

`ScanResult.note` được ghi ở `engine.py:3105` và `engine.py:3219` (cảnh báo cookie chết,
cảnh báo đếm trùng hash), nhưng **cả bốn** consumer đều gate theo lỗi:
`app.py:907` + `:932`, `cli.py:289-290`, `watch.py:475` + `:481`, `bang_ngang.py:86`.

Nên khi quét **thành công**, tool không nói được rằng nó đang chạy suy giảm —
đúng cái mà comment `engine.py:3216-3217` viết ra để chặn. Đây là gốc chung của
AUD-201, AUD-025, AUD-143/AUD-166 và **AUD-X31**.

### 5.7 Cổng kiểm thử không báo được lỗi

`kiemtra.bat` (đọc trực tiếp vòng này):

- dòng 8 ghim `PY` vào `.venv`, mà `.venv` **không có pytest**;
- dòng 18 (`%PY% -m pytest -q`) và dòng 22 (AppTest) **không có** `|| echo [X]`, khác dòng
  14 vốn có;
- dòng 22 chạy `AppTest.from_file('app.py')` mà không đặt `TIMCLIP_DATA_DIR`, nên
  `app.py:41-45` dựng `Engine()` trên **`data/` sản xuất** và chạy DDL trên
  `data/lichsu.db` thật.

Không có CI (`.github/` chỉ có `copilot-instructions.md`). — **AUD-241**, **AUD-245**

### 5.8 Các vùng khác đáng dè chừng

| Vùng | Vì sao nguy hiểm | Bằng chứng |
|---|---|---|
| `_merge` (`engine.py:2395-2521`) | Đã hiệu chỉnh bằng thực nghiệm; CLAUDE.md:118 cấm đổi khi không được yêu cầu. Nó cũng **xoá trắng** `canh_bao_gop` mỗi lần gọi | `engine.py:2405` |
| Bộ đếm chẩn đoán | `_match_chunks` **cộng dồn** (`engine.py:2377-2384`), `_merge` **gán đè** (`engine.py:2415-2419`); chỉ vì lần `_merge` CUỐI chạy trên tập thô đầy đủ (`engine.py:3103`) mà số liệu mới đúng | — |
| `dong_goi.nen_lay` | Tài liệu nói whitelist theo FILE, thực tế là whitelist theo ĐUÔI + denylist từ khoá → `cookies.txt` lọt (**AUD-181/221**) | `dong_goi.py:26-31`, `:55-56` |
| `ChayTool.bat:46` | Thiếu `--server.address` → Streamlit bind mọi interface, UI **không có xác thực** (**AUD-222**) | đọc trực tiếp vòng này |
| `sheets.py` | **Không có timeout ở đâu cả**; gspread mặc định `timeout=None`. Trên đường `watch` một kết nối treo sẽ giữ `data/tool.lock` vô thời hạn (**AUD-X13**) | `sheets.py` không có chuỗi `timeout` |
| `cli.py:126` + `:183` | Ép `--ncores 1` cho mọi lệnh CLI, ghi đè cấu hình đã lưu (**AUD-162/183**) | — |

---

## 6. Test architecture

### Cấu hình

`pytest.ini` (đọc trực tiếp):

```ini
[pytest]
testpaths = tests
addopts = -q --tb=short -m "not slow"
markers =
    slow: test cham (co xu ly audio that) - chay bang: pytest -m slow
```

- `testpaths = tests` là **load-bearing**: nó giữ các script `kiem_*.py` ở thư mục gốc ra
  khỏi collection. `kiem_ngang.py:62` dựng `Engine()` ở **cấp module** — nếu bị collect,
  nó chạy DDL trên `data/lichsu.db` sản xuất (**AUD-209**).
- `-m "not slow"` được **prepend**, và `-m` của pytest là store option, nên
  `pytest -m slow` giải ra `-m "not slow" -m slow` → giá trị cuối thắng → chạy đúng 5 test
  slow.

### Chạy nhanh vs chạy chậm

| | Lệnh | Nội dung |
|---|---|---|
| **Nhanh (mặc định)** | `py -3 -m pytest` | 952 passed, 1 skipped, 5 deselected, ~50 s (`baseline.md:11`) |
| **Chậm** | `py -3 -m pytest -m slow` | 5 test: `tests/test_integration.py:6, 30, 47` và `tests/test_audfprint_progress_integration.py:12, 52` |

**Skip duy nhất:** `tests/test_khoa.py::test_file_khoa_bi_xoa_khi_dang_giu_khong_lam_crash`
— "Windows không cho xóa file đang có handle mở", skip có điều kiện theo nền tảng, hợp lệ.

### Cái gì được cách ly, cái gì không

`tests/conftest.py` (69 dòng, đọc toàn bộ vòng này) chỉ có:

- `sys.path.insert` (dòng 10) — **không** truyền sang subprocess;
- fixture `bo_clip` (dòng 32) — audio tổng hợp, session scope;
- fixture `engine` (dòng 53-62) — `Engine(root=<repo thật>, data_dir=tmp_path/data,
  out_dir=tmp_path/ketqua)`. **`root` là repo thật một cách CỐ Ý** để tìm thấy `bin/` và
  `audfprint-master/`; an toàn vì `Engine` không ghi gì tương đối theo `root`
  (mọi ghi đều từ `data_dir`/`out_dir`: `engine.py:632, 638, 639, 641-642, 648`);
- helper `M()` (dòng 65-69).

**Không có fixture `autouse` nào trong toàn bộ conftest.** Cách ly là **quy ước**, không
phải cơ chế: không có killswitch mạng cấp session, không ép `TIMCLIP_DATA_DIR`, không
assert nào ngăn một test resolve đường dẫn vào `data/` thật (**AUD-242**).

Điểm nguy hiểm nhất: `cli.py:182` là `eng = Engine()` trần. Chín chỗ
`monkeypatch.setattr(cli, "Engine", ...)` là tất cả những gì đứng giữa bộ test và
`data/lichsu.db` thật.

Hai chỗ **thật sự** đọc đường dẫn sản xuất trong bộ nhanh (chỉ đọc, vô hại):
`tests/test_cli_watch.py:162` đọc `data/cau_hinh.json` thật qua `cli.py:171`; 13 lần
render `AppTest` đọc `google_key.json` thật qua `app.py:637` → `sheets.py:132` (chỉ lấy
`client_email`) — **AUD-243**.

### Tuyệt đối KHÔNG chạy khi có job fingerprint đang chạy

1. **`py -3 -m pytest -m slow`** — 5 test này chạy `bin/ffmpeg.exe` thật và audfprint thật,
   một test ở `Config(ncores=8)` ba vòng (`tests/test_audfprint_progress_integration.py:32`).
   Chúng tranh CPU trực tiếp với job dựng kho.
2. **`kiemtra.bat`** — bước 3/3 (`kiemtra.bat:22`) dựng `Engine()` trên `data/` sản xuất.
3. **`tests/test_audfprint_multiproc.py`** — dù nằm trong bộ nhanh, dòng 86 và 97 assert
   trên `glob("timclip_ht_*")` của **thư mục temp toàn máy**. Một job fingerprint đa nhân
   đi vào `multiproc_add` giữa hai snapshot sẽ làm nó đỏ vì lý do không liên quan
   (**AUD-244**). Cửa sổ hẹp (1-3 giây, một lần mỗi lần dựng kho) nhưng có thật.

Bộ nhanh nói chung **an toàn** khi job đang chạy: đã truy vết cả 60 file test — không file
nào ghi vào `data/`, `ketqua/`, `bin/`; không file nào mở `lichsu.db`/`khos.json`/`.pklz`
thật; không file nào lấy `data/tool.lock`; không file nào gọi mạng.

### Mẫu tốt nên sao chép

- `tests/test_scan_thread_boundary.py:48-70` — guard cấu trúc dùng `tokenize` để docstring
  bàn về Streamlit không thành false positive, **kèm meta-test chứng minh guard bắt được**.
- `tests/test_bang_ket_qua_arrow.py:56-60` — negative control cố ý đỏ nếu ai đó "sửa" nó.
- `Engine.__new__(Engine)` cho test logic thuần (`tests/test_selection.py`,
  `test_match_selection.py`, `test_merge_hash_split.py`, `test_overlap_policy.py`,
  `test_toc_do_khop.py`) — `__init__` không chạy, không ghi một byte nào.

### Độ phủ

| Mức | Vùng |
|---|---|
| **CAO** | scan pipeline, matching, acceptance, selection, fingerprint progress, metadata, publication date, duration, sheets, sheet delivery, threading, arrow, security, packaging, watch, cleanup, storage, diagnostics |
| **TRUNG BÌNH** | `app.py` (78 KB; chỉ render + 3 kịch bản tương tác; hai assert ở `tests/test_bang_ket_qua_arrow.py:109-110` là grep chuỗi trên source). `df_ket_qua`/`bang_ket_qua` **không được thực thi bởi test nào** vì cả ba file AppTest liên quan quét đều đặt `"results": []` (**AUD-127**). CLI: 6/10 verb không có test (**AUD-246**) |
| **THẤP** | `thiet_lap_may_phu.py`, `kiem_metadata_kho.py`, `kiem_ngang.py`, `kiem_sheet.py`, `kiem_header.py` — 0 test mỗi file |

---

## 7. Operational safety notes

> `data/` nằm ngoài phạm vi vòng audit này (một job fingerprint đang chạy). Các con số về
> **nội dung** `data/` dưới đây đến từ vòng đọc-chỉ trước đó và được ghi rõ nguồn; mọi
> khẳng định về **mã** đều đã kiểm lại vòng này.

### 7.1 `data/` là dữ liệu sản xuất

| Đường dẫn | Nội dung | Mất thì sao |
|---|---|---|
| `data/*.pklz` | Kho vân tay | **Phải fingerprint lại hàng chục giờ.** Vòng trước ghi nhận 128 MB + 24 MB |
| `data/lichsu.db` | Lịch sử quét (`jobs` + `matches`) | Mất bộ nhớ "đã quét" của `watch` → quét lại toàn bộ backlog |
| `data/khos.json` | Đăng ký kho, con trỏ `dang_dung` | Ứng dụng khởi động với danh sách kho rỗng (hoặc crash — **AUD-047/163**) |
| `data/cau_hinh.json` | Toàn bộ `Config` + 5 key UI | Về mặc định |
| `data/metadata/kho_*.json` | Snapshot metadata, **priority 0** | Báo cáo rơi về `clips_meta.json` — thực ra đây là cách thoát khỏi §5.1 |
| `data/downloads/` | Cache audio | Chỉ tốn băng thông. Vòng trước ghi nhận 4,9 GB / 50 file |
| `data/tool.lock` | Khoá liên tiến trình | Kernel tự nhả khi tiến trình chết — **không cần dọn tay** |

`ketqua/` chứa CSV / hồ sơ `.md` / log. **Không có mã nào đọc lại `ketqua/`.**

### 7.2 `data/tool.lock` — single-instance, nhưng chỉ 3/4 thao tác nặng

Đã kiểm bằng grep vòng này: đúng **4** chỗ lấy khoá — `engine.py:1436`, `engine.py:1495`,
`engine.py:1690`, `watch.py:287`. **Đường quét (GUI và CLI) không lấy khoá** (§4.7).

Khoá là **non-blocking**: `msvcrt.locking(LK_NBLCK)` (`khoa.py:20`) /
`fcntl.LOCK_EX|LOCK_NB` (`khoa.py:33`) → ném `DangChayRoi` ngay (`khoa.py:89-92`). Nên khi
một job dựng kho đang chạy, lượt `watch` theo lịch **thất bại ngay** chứ không xếp hàng —
`watch.py:300-301` trả `BaoCao` có lỗi, `cli.py:97-98` thoát 1.

Khoá **không reentrant**: lấy hai lần trong cùng tiến trình cũng bị từ chối
(`tests/test_khoa.py:27-31`). Đây là lý do không thể chỉ đơn giản bọc `scan_media` vào
khoá.

### 7.3 Credentials

| File | Trạng thái kiểm được vòng này | Gitignore |
|---|---|---|
| `google_key.json` (thư mục gốc dự án) | **TỒN TẠI** | `.gitignore:2` |
| `cookies.txt` (thư mục gốc dự án) | **KHÔNG tồn tại** | `.gitignore:10`, `*.cookies.txt` ở `:11` |
| `data/cau_hinh.json` | (trong `data/`, ngoài phạm vi) | `.gitignore:4` |
| `watchlist.json` | **KHÔNG tồn tại** — chỉ có `watchlist.example.json` | `.gitignore:9` |

**Không giá trị bí mật nào được đọc hay in trong vòng audit này.**

Ba điều cần biết về credentials:

1. **Đường dẫn `google_key.json` hardcode tương đối theo `sheets.py`**
   (`sheets.py:96-97`), **không** có override qua biến môi trường. Tham số `key_path=`
   tồn tại (`sheets.py:94`) nhưng **không caller sản xuất nào truyền**.
2. Chỉ `client_email` được nạp vào Python (`sheets.py:130-134`) để hiện gợi ý chia sẻ
   Sheet. Private key được giao cho gspread **bằng đường dẫn** (`sheets.py:150`) — không
   bao giờ vào biến Python.
3. **`cookies.txt` chưa từng tồn tại nên chưa có rò rỉ**, nhưng
   `dong_goi.nen_lay("cookies.txt")` trả `True` (`dong_goi.py:55-56` cho `.txt` vào
   `DUOI_OK`, và `dong_goi.py:28-31` không có từ khoá cookie). Nếu ai đó đặt file cookie
   vào thư mục dự án — đúng chỗ `.gitignore:10` dự liệu — nó sẽ vào **cả hai** gói zip và
   vào image Docker (`.dockerignore` không có pattern cookie). — **AUD-181/221**

### 7.4 Quy tắc vận hành

- **Một job nặng mỗi lần trên một máy** (`docs/RUNBOOK.md:81-83`). GUI đã tự chặn trong
  cùng session (`app.py:97`, `:170`) nhưng **không** chặn giữa hai tab trình duyệt hay
  giữa GUI và CLI.
- **`watchlist.json` là dữ liệu vận hành không tái tạo được** và hiện **không tồn tại** trên
  máy này. Nếu nó hỏng và không có `.bak` dùng được, `luu_tru.py:149-160` sẽ **đổi tên** nó
  thành `.hong.<ts>`; từ lượt sau `cli.py watch` in template và **thoát 0** (**AUD-187**).
  Đoạn backup trong `docs/RUNBOOK.md:100` chép `watchlist.local.json` — **không phải** file
  mà tool đọc (`cli.py:51` mặc định `watchlist.json`).
- **`ChayTool.bat` gọi `cap_nhat.py` mỗi lần khởi động** (`ChayTool.bat:33`), tối đa 90 s
  chờ mạng (`cap_nhat.py:46`). Dùng `ChayTool.bat --da-cap-nhat` để bỏ qua
  (`ChayTool.bat:30`).
- **`GiamSat.bat` KHÔNG gọi `cap_nhat.py`** — máy chính chạy giám sát theo lịch không bao
  giờ tự cập nhật. `GiamSat.bat:11` cũng hardcode một URL Google Sheet (**AUD-227**).

---

## 8. Findings — danh sách đã thẩm định

162 mục sống sót qua vòng phản biện đối kháng. Sắp theo severity, và **tách theo verdict**.

**Ba lưu ý bắt buộc đọc trước:**

1. **Trùng lặp.** Ít nhất 15 cặp là **cùng một defect** được hai domain khác nhau nộp, đôi
   khi ở hai severity khác nhau. Đã đánh dấu `≡` trong bảng. Số defect PHÂN BIỆT ≈ 147,
   và **P1 phân biệt là 6, không phải 7**.
2. **Verdict.** Mục có verdict `LIKELY` là *cơ chế đã xác nhận trong mã, hậu quả chưa tái
   hiện*. `HYPOTHESIS` là *chưa xác minh*. Đừng đối xử với chúng như CONFIRMED.
3. **`AUD-045` có verdict `NOT_REPRODUCED`** nên **không được liệt kê như một defect** ở
   đây. Nội dung của nó (shim tương thích ở `engine.py:1933-1937` đánh dấu clip thành công
   khi không thấy structured event) là **defence-in-depth**, không phải lỗi đang xảy ra;
   ba lớp bảo vệ khác đứng trước nó (`audfprint_progress_runner.py:305-311`,
   `:83-84`, `engine.py:1939-1940`). Bảy mục khác đã bị **bác bỏ** hoàn toàn và không xuất
   hiện ở đây: AUD-032, AUD-065, AUD-068, AUD-168, AUD-203, AUD-251, AUD-269.

### 8.1 P1 — CONFIRMED (7 mục / 6 defect phân biệt)

| ID | Vấn đề | Bằng chứng | Bước tiếp theo |
|---|---|---|---|
| **AUD-061** ≡ AUD-081 | Snapshek metadata (priority 0) che mọi hiệu chỉnh ghi vào `clips_meta.json`; báo cáo vẫn `complete`, và chạy lại công cụ sửa ghi ngược giá trị cũ | `engine.py:1122`, `:1124`; `clip_metadata.py:549-558`, `:591-601`, `:541-546` | **Quyết định trước, code sau**: kho nào là chân lý? Nếu chọn live → phải sửa `tests/test_clip_metadata.py:229-268` và `va_metadata_thieu`. Nếu chọn snapshot → cho ba CLI sửa lỗi cũng ghi/vô hiệu hoá snapshot. Việc rẻ làm ngay: hiện `audit.conflicts` lên tab metadata của `app.py` (hiện chỉ `kiem_metadata_kho.py:229` đọc) |
| **AUD-081** ≡ AUD-061 | (cùng defect, nộp từ domain ngày đăng/thời lượng) | `engine.py:1120-1124`; `clip_metadata.py:550-556` | gộp với AUD-061 |
| **AUD-062** | Token 11 ký tự trong ngoặc vuông giữa tiêu đề → clip vĩnh viễn `ambiguous`, URL gốc **rỗng** trong CSV / 34 cột / hồ sơ; không công cụ nào sửa được | `clip_metadata.py:25`, `:844-850`, `:744-772`; exporter `engine.py:3361`, `bang_ngang.py:104-113`, `dossier.py:117` | Neo việc trích ID vào token trong ngoặc **cuối cùng trước phần mở rộng** (đúng thứ `channel._ten_file` sinh ra, `channel.py:465-469`). **Phải sửa cả hai** chỗ gọi `_ids_from_value` — `clip_metadata.py:377` (lúc nạp) và `:843` (lúc resolve) |
| **AUD-121** ≡ AUD-001 | «⏹️ Dừng lại» không dừng được cả lô: video kế tiếp `clear()` cờ huỷ | `scan_jobs.py:207-212`, `:263-267`; `engine.py:3149`, `:3055-3056`, `:3244-3251`; `app.py:823` | Sửa rẻ nhất, không đụng engine: `break` khỏi generator trong `ScanJobController._chay` khi `self._cancelled`. Đồng thời bỏ `disabled=anh.cancelled` ở `app.py:823`, và chỉ in "Đã dừng theo yêu cầu" khi lô **thật sự** dừng sớm. **Không** được làm hỏng `watch.py:437-448` (`tests/test_dung_lai.py:92-134` khoá) |
| **AUD-122** ≡ AUD-005 | Selectbox chọn kho + widget tuning sống trong lúc job chạy, sửa thẳng Engine mà worker đang đọc → báo cáo trộn bằng chứng từ hai kho, và trong lúc **dựng kho** có thể ghi đè `.pklz` sai | `app.py:485-489`, `:503-565`; `engine.py:794-799`, `:1655`, `:2334`, `:1943-1957` | Thêm `disabled=job["running"] or scan_controller.running` cho `app.py:485` và cả khối `app.py:501-569` — đúng guard mà `app.py:650`/`:667` đã có. Hoặc mở rộng `ScanLaunchConfig` để snapshot cả tuning + `db_file` |
| **AUD-201** | Quét một phần **không bao giờ** được nói ra trong CSV / dòng 34 cột / hồ sơ khiếu nại — chỉ hiện trên màn hình Streamlit | `engine.py:3124-3128` (chỉ ghi `kq.note`); `bang_ngang.py:86` (note chỉ ở nhánh lỗi); `dossier.py:28-38` (không có trường phạm vi); `app.py:393-407` (nơi duy nhất nói) | Thêm `pham_vi_quet_s`/`quet_mot_phan` vào `HoSo` và in một bullet "Phạm vi đã quét" — `dossier.py` không bị ràng buộc schema. Với dòng 34 cột thì phải quyết định vì header đang **đóng băng** (§4.4 I-30) |
| **AUD-X19** | `ids_da_quet` bỏ qua video theo **toàn cục**, không theo kho: video quét cho khách A vĩnh viễn vô hình với khách B | `engine.py:3295-3304`, `:873-877`; `watch.py:378-379`, `:190-201` | Thêm cột `kho` vào `jobs` (`engine.py:874-878`), điền từ `self.kho_dang_dung` ở `save_job` (`engine.py:3276-3282`), cho `ids_da_quet` một tham số kho mặc định là kho active. Dòng cũ `NULL/''` phải được coi là **chưa phân định** để không quét lại cả backlog. `tests/test_engine_core.py:118-141` chỉ khoá status + id rỗng nên tham số có default vẫn xanh |

### 8.2 P2 — CONFIRMED (34 mục)

| ID | Vấn đề | Bằng chứng | Bước tiếp theo |
|---|---|---|---|
| AUD-001 ≡ 121 | Bản nộp thứ hai của lỗi huỷ lô | `engine.py:3149` | gộp với AUD-121 |
| AUD-003 | `pham_vi_quet_s` khai khống khi đường Top-1 nhanh cắt ngắn một đoạn | `engine.py:3086-3087`, `:2765-2777` | Cho `_quet_tho` trả về phạm vi thật sự đã so khớp; suy `da_quet_den` từ đó |
| AUD-021 | Cửa sổ vi phạm trong hồ sơ + dòng Sheets bắt đầu ở mốc **suy diễn**, link nhảy cũng vậy | `engine.py:2507-2513`; `dossier.py:58-62`; `bang_ngang.py:63-65`; `engine.py:3364` | Quyết định đã ghi ở `docs/PHASE2_FIX_PLAN.md:265` nhưng chưa làm. **Cẩn thận**: phản biện của AUD-203 lập luận ngược lại (xem §11) |
| AUD-025 | Streamlit giấu chẩn đoán zero-match của **mọi** video ngay khi **một** video có kết quả | `app.py:905`, `:913-917` vs `cli.py:290-306` | Đổi gate thành per-result. **Phải** thêm `if x.matches: continue` vào `bao_cao_khong_co_ket_qua` (`app.py:269`) trước |
| AUD-041 | Thanh tiến độ đứng im suốt pha so khớp: chỉ khớp chuỗi `"Analyzed #"` vốn chỉ có ở đường single-core | `engine.py:2315`; `audfprint-master/audfprint.py:238-240` | Khớp `"Analyzed"` (coi `#` là tuỳ chọn) + test hình dạng dòng multi-core |
| AUD-043 ≡ 164 | `data/fingerprint_jobs/` không có GC; rò cả bản copy kho khi huỷ lúc pre-copy chế độ `add` | `engine.py:1818-1837` vs `:1913`, `:1962-1963`; `don_dep.py:161-168` | Dời `try:` lên ngay sau `os.makedirs(workspace)`; thêm quét `fingerprint_jobs` vào `cli.py:214` và `watch.py:347` |
| AUD-063 | Clip đổi tên/copy mất định danh dù ID vẫn trong tên; không công cụ nào sửa được | `clip_metadata.py:26-29`, `:918-919`; `engine.py:1355-1357`, `:1524`; `channel.py:201-204` | Tái dùng `input_ids` mà bước 0 đã tính ở mức 6; đồng bộ `channel.py:202` |
| AUD-064 | Lịch sử không đóng băng định danh tác phẩm — `matches` chỉ có basename | `engine.py:3285-3287`, `:882-885` | Thêm `video_id`/`title`/`url`/`resolution_method` vào `matches`, điền lúc `save_job`. **Tiền đề cho Works Registry** |
| AUD-084 | `Match.vung` tính trên độ dài file **đã cắt ngắn**, không tính lại sau khi `duration_s` được sửa | `engine.py:2535-2543` gọi ở `:3112`, sửa ở `:3194` | Chạy lại `_gan_chi_so` sau `engine.py:3194`, hoặc truyền độ dài thật vào |
| AUD-102 | `kiem_ngay_dang --repair-network` gửi mỗi clip một request **không cookie** | `kiem_ngay_dang.py:131-132`; `channel.py:374` | Dựng `CauHinhMang.tu_file_cau_hinh(thu_muc_data_mac_dinh())` như `cli.py:171` đã làm; thêm case vào `tests/test_cau_hinh_toi_moi_duong.py` |
| AUD-141 ≡ 206 | Hai schema báo cáo cùng ghi vào worksheet `KetQuaQuet`; lệch schema chỉ được **log**, dòng vẫn ghi, UI báo thành công | `sheets.py:214-224`, `:241`; `app.py:222-229`, `:628-635` | Đặt tên worksheet theo schema, hoặc cho `append` raise ở trạng thái `"khac"` |
| AUD-144 | `cli.py watch` thoát 1 sau một lỗi Sheets **đã được sweep cứu** | `watch.py:430-435`; `cli.py:96-97` | Tách `loi_sheets` khỏi `loi`; buộc mã thoát vào lỗi quét/CSV. Lưu ý `tests/test_cli_watch.py:120-139` và `tests/test_watch.py:753-810` khoá hành vi hiện tại |
| AUD-147 | Apps Script nói chèn/di chuyển cột là vô hại; exporter Python ghi **theo vị trí** | `apps_script/File01_CauHinh_TienIch.gs:326-328`; `sheets.py:241-244`, `:365-369` | Thu hẹp lời hứa xuống "chỉ được thêm cột SAU cột AH", hoặc thêm guard chiều rộng vào `_tinh_trang_header` |
| AUD-162 ≡ 183 | Mọi lệnh CLI ép `ncores=1`, ghi đè cấu hình đã lưu | `cli.py:126`, `:183`; `engine.py:1652-1654` | `default=None` + `if a.ncores is not None:`; sửa `docs/RUNBOOK.md:355` |
| AUD-163 ≡ 047 | `khos.json` parse được nhưng sai hình dạng → `KeyError`/`TypeError` thoát khỏi `Engine.__init__` | `engine.py:779`, `:791`, `:794`; `luu_tru.py:130-131` | Kiểm hình dạng trong `_doc_khos`, ném `LoiDuLieu` để handler `engine.py:771`/`:785` bắt được |
| AUD-164 ≡ 043 | (cùng defect, severity khác) | `cli.py:214`; `watch.py:347` | gộp với AUD-043 |
| AUD-166 | Sự kiện `scan.*` bị vứt; log `clip_metadata` không vào file log của watch | `scan_jobs.py:20`; `sheets.py:29`; `cli.py:33` vs `:233`; `clip_metadata.py:38` | Gắn handler lên logger cha `scan`; cài `nhat_ky` **trước** `configure_metadata_logging` |
| AUD-167 | Khúc ffmpeg lỗi bị bỏ **âm thầm** trong khi `pham_vi_quet_s` vẫn khai đủ | `engine.py:2277-2278`, `:3087`, `:3095` | Đếm khúc bị rơi và đưa vào `kq.note`/`chan_doan`; **không** raise (bộ lọc `>1024 byte` hợp lệ cho khúc đuôi) |
| AUD-181 ≡ 221 | `cookies.txt` lọt whitelist đóng gói (`.txt` nằm trong `DUOI_OK`) và cả `.dockerignore` | `dong_goi.py:28-31`, `:52`, `:55-56`; `.dockerignore:15-36` | Thêm `"cookie"` vào `TU_KHOA_NHAY_CAM` (sửa **cả hai** packager cùng lúc); thêm pattern vào `.dockerignore`; thêm case `.txt` vào `tests/test_packaging.py:12-21` |
| AUD-183 ≡ 162 | (cùng defect) | `cli.py:126` | gộp với AUD-162 |
| AUD-205 | Cùng một kết quả đẩy tự động vs thủ công cho ra **chữ khác nhau** trong ô (dấu nháy thừa) | `app.py:123` vs `:250`, `watch.py:426`; `sheets.py:74-79` | Bỏ `o_bang_tinh_an_toan` ở `app.py:123`. Giữ nguyên ở `engine.py:3380`, `:3415`, `app.py:411` (CSV — Excel **có** parse formula) |
| AUD-206 ≡ 141 | (cùng defect) | `sheets.py:213-224` | gộp với AUD-141 |
| AUD-221 ≡ 181 | (cùng defect, phân tích rộng hơn: whitelist theo ĐUÔI, không theo FILE) | `dong_goi.py:5-7` vs `:55-56` | gộp với AUD-181 |
| AUD-222 | `ChayTool.bat` bind UI **không xác thực** lên mọi interface, trong khi README ghim 127.0.0.1 | `ChayTool.bat:46`; `README.md:17`; `docs/INSTALL_WINDOWS.md:112` | Thêm `--server.address=127.0.0.1`. Tốt hơn: commit `.streamlit/config.toml` (sửa luôn AUD-X10) |
| AUD-242 | Cách ly test là **quy ước**, không có guard `autouse` nào | `tests/conftest.py` (69 dòng, 0 autouse) | Chuyển blocker mạng có sẵn (`tests/test_metadata_integration.py:79-96`) thành fixture autouse; thêm fixture session ép `TIMCLIP_DATA_DIR` |
| AUD-245 | `.venv` không có pytest, và `kiemtra.bat` **không thể** báo lỗi | `kiemtra.bat:8`, `:14`, `:18`, `:26` | Thêm `\|\| echo   [X] LOI TEST` vào dòng 18 **và** 22. **Đừng** `pip install -r requirements-dev.txt` khi app đang chạy (dòng 1 của nó là `-r requirements.txt`, không ghim gì) — cài riêng `pytest>=9,<10` |
| AUD-X05 | `data/downloads` là namespace scratch toàn cục cuối cùng: hai lượt quét cùng video id dùng chung một `outtmpl` và một `.part` với `continuedl=True` | `engine.py:2093`, `:2095`, `:2136-2139`, `:2070-2074` | Tải vào workspace per-scan rồi `os.replace` vào cache khi xong. **Đừng** chỉ thêm uuid vào `outtmpl` — tên chung chính là thứ làm nên cache |
| AUD-X06 | Nút Dừng của «Lấy lại tên video thật» **hoàn toàn vô tác dụng** | `channel.py:216-345` (0 chỗ kiểm cancel); `app.py:1073`, `:830-832` | Cho `va_metadata` tham số `cancel_check` giống `sync` (`channel.py:559`, kiểm ở `:584`); truyền từ `app.py:1073` như `app.py:1011` đã làm |
| AUD-X13 | Mọi request YouTube có timeout; **không** request Google Sheets nào có. Trên `watch`, một kết nối treo giữ `data/tool.lock` vô thời hạn | `sheets.py:150` (không có `set_timeout`); `watch.py:426`, `:509` trong khoá `:287-290` | Gọi `gc.set_timeout(...)` sau `gspread.service_account(...)` ở `sheets.py:150`, dùng lại bound `network_timeout_s`. `sheet_delivery.py:45-50` **đã** phân loại timeout là retryable |
| AUD-X14 ≡ X19 | (cùng defect dedup theo kho, nộp từ domain khác) | `engine.py:3295-3304` | gộp với AUD-X19 |
| AUD-X20 | Apps Script tô "đã quét" cho **mọi** bảng link khách hàng từ một tập khoá không lọc | `apps_script/File04_DanhDauLinkDaQuet.gs:137-160`; `File01:181-191` | Chỉ là định dạng ô, tự phục hồi mỗi lần chạy. Cần cột kho trong `HEADER_NGANG` mới lọc được — cùng quyết định với AUD-201 |
| AUD-X21 | Tên kho không dùng được trong watchlist **không** huỷ lượt quét: mọi video bị quét bằng kho đang active | `watch.py:369-379`; `engine.py:833-835`, `:791-792` | **Là hành vi cố ý**, khoá bởi `tests/test_watch.py:469`. Muốn đổi phải nêu như thay đổi thiết kế |
| AUD-X26 | Bộ test chứng nhận một runtime **khác** runtime chạy thật | `.venv/pyvenv.cfg`; `tests/__pycache__/*.cpython-314-*.pyc`; `ruff.toml:1`; `kiemtra.bat:8` | Cài `requirements-dev.txt` vào `.venv` và chạy test ở đó; ghim dependency |
| AUD-X31 | `ScanResult.note` là kênh **chỉ ghi** khi quét thành công: cảnh báo cookie chết và cảnh báo đếm trùng hash không tới ai | `engine.py:3219`, `:3105` vs `app.py:907`+`932`, `cli.py:289-290`, `watch.py:475`+`481`, `bang_ngang.py:86` | Thêm `ScanResult.canh_bao: list` tách khỏi `note`, render vô điều kiện. **Làm việc này TRƯỚC** AUD-201 / AUD-025 / AUD-143 / AUD-166 — cả bốn đều nằm sau cùng một bề mặt còn thiếu |

### 8.3 P2 — LIKELY (4 mục — cơ chế xác nhận, hậu quả chưa tái hiện)

| ID | Vấn đề | Bằng chứng | Bước tiếp theo |
|---|---|---|---|
| AUD-101 | `list_channel` không đối chiếu số video lấy được với thực tế; một listing bị cắt ngắn hoặc thất bại hoàn toàn đều báo "kho đủ" | `channel.py:414-424`, `:571`, `:676` | Bỏ `ignoreerrors=True` cho request listing (hoặc kiểm đếm lỗi tường minh), thêm guard `if not ds` vào `kiem_tra_thieu`, tách thông điệp "URL sai" khỏi "YouTube từ chối". **Đừng** dựa vào `playlist_count` — nó trả về số đã bị cắt |
| AUD-161 | `khos.json` ghi không có khoá liên tiến trình, và mọi writer dùng chung một tên `.tmp` cố định | `luu_tru.py:59-99`, `:79`; `engine.py:817-861`, `:1969-1974` | Giữ **một** khoá xuyên suốt read-modify-write; đặt tên temp duy nhất theo tiến trình. Kịch bản thật là GUI + `cli.py` chạy song song, không phải GUI + build của chính nó |
| AUD-182 | Kết quả `watch` không tới được Sheets khi outage kéo dài **cả lượt** thì không có đường gửi lại | `watch.py:430`, `:497-512`; `engine.py:3218-3222`, `:3295-3305` | Ghi trạng thái giao hàng cạnh job; thêm nút "đẩy job này lên Sheets" vào tab Lịch sử. Có retry **trong** một lượt (`watch.py:501-512`) nên lỗi thoáng qua tự khỏi |
| AUD-X07 | Main thread và thread giao hàng dùng chung một `Worksheet` gspread + một `requests.Session`; và `_ket_noi` giữ khoá module **xuyên** lời gọi mạng | `sheets.py:43-44`, `:164-173`, `:207`, `:240-241` | Ưu tiên nửa thứ hai: dựng `_KetNoi` **ngoài** khoá + gọi `client.set_timeout(...)`. Nửa chia sẻ Worksheet là hazard tiềm ẩn — `tests/test_sheets_session.py:273-291` khoá việc dùng chung kết nối |

### 8.4 P3 — CONFIRMED (nhóm theo chủ đề)

**Engine core & scan**

| ID | Một dòng | Bằng chứng | Bước tiếp |
|---|---|---|---|
| AUD-002 | `Engine(config=...)` bị `cau_hinh.json` ghi đè, và bị vứt hẳn nếu file lỗi | `engine.py:618`, `:683-699` | Không mutate object của caller; giữ nó ở nhánh `except` |
| AUD-004 ≡ 185 | `TIMCLIP_DATA_DIR` được `thu_muc_data_mac_dinh` đọc nhưng `Engine.__init__` bỏ qua | `engine.py:632` vs `:601-609` | Thống nhất một công thức. **Sửa một mình `Engine` sẽ làm hỏng `cli.py dung`** (`cli.py:41-46` vs `:55`) |
| AUD-006 | `rmtree` `data/chunks` trong `finally` của `scan_media` là mã chết | `engine.py:3139`, `:2250-2253` | Xoá, hoặc ghi rõ nhánh no-workspace là test-only (`tests/test_tang_toc.py:138`, `:162` còn dùng) |
| AUD-007 | Thanh tiến độ đứng ở 95% suốt pha bù tốc độ và **lùi** khi tải lại toàn bộ | `engine.py:3100-3102`, `:3054`, `:3133`, `:3185` | Dành một dải riêng cho pha tempo (0.90-0.98) và một dải riêng cho lần tải thứ hai |
| AUD-008 | File tải một phần bị bỏ quên khi `keep_downloads` tắt | `engine.py:3207-3209` | Theo dõi **mọi** đường đã tải trong một list |
| AUD-009 ≡ 031 | `chan_doan.so_khuc` bị thổi phồng bởi mỗi lượt bù tốc độ, và UI dán nhãn "đã cắt" | `engine.py:2377`, `:3007-3009`; `app.py:279` | Tách `so_khuc_cat` (gán một lần) khỏi `so_khuc_so_khop` (cộng dồn); đổi nhãn UI |
| AUD-010 | Thông điệp Top-1 nói "phần đầu video" cho **mọi** đoạn | `engine.py:2763-2764`, gọi ở `:3086` | In mốc thật của khúc |
| AUD-031 ≡ 009 | (cùng defect) | `engine.py:2377`; `app.py:279` | gộp |
| AUD-042 | Kho vân tay được nạp lại **mỗi** lần gọi `_match_chunks` (~13 s/lần) | `engine.py:2333`; `audfprint-master/audfprint.py:450` | Giảm số lần gọi, hoặc một matcher thường trú. Chi phí đã được đo và ghi ở `engine.py:2745-2746` — đây là đánh đổi **có ý thức** |
| AUD-048 | `timeout_seconds` của `run_observed_process` không được `_run_stream` truyền → **không** lệnh audfprint nào có timeout | `process_runner.py:92` vs `engine.py:914-953` | Thêm tham số, truyền từ hai call site, và dịch `result.timed_out` thành lỗi riêng |
| AUD-049 | `db_clips()` giữ đồng thời stream đã giải nén và bảng đã dựng lại (~2× bộ nhớ) | `engine.py:1038-1043` | `pickle.load(f)` trong cùng `with` (streaming). Tốt hơn: chỉ đọc `names`/`hashesperid` mà không dựng bảng 419 MB |
| AUD-051 | `cancel_event` dùng chung giữa build và scan, mỗi bên xoá của bên kia | `engine.py:1681`, `:3057-3058` | Mỗi thao tác một `Event` riêng; `Engine.cancel()` thành broadcast |
| AUD-052 | Đường match poll toàn bộ process tree 5 lần/giây mà **không ai** dùng kết quả | `process_runner.py:187-193`; `engine.py:2333-2336` | Guard `if on_heartbeat or logger:` |
| AUD-053 (LIKELY) | `FingerprintJobController.publish` vẫn có thể ném `queue.Full` sau chính đoạn hồi phục của nó | `fingerprint_progress.py:468-480` | Bọc `contextlib.suppress(queue.Full)`, hoặc đưa cả put/get vào `self._lock` |

**Matching & chẩn đoán**

| ID | Một dòng | Bằng chứng | Bước tiếp |
|---|---|---|---|
| AUD-022 | Quyết định dừng-sớm và bỏ-bù-tốc-độ dựa trên ứng viên mà bộ lọc self-match sau đó xoá | `engine.py:3110-3111` vs `:3091`, `:3099`, `:2837-2846` | Áp cùng bộ lọc trong `_ung_vien_dat` / `_du_manh_de_dung_som` |
| AUD-023 ≡ 003 | (cùng defect `pham_vi_quet_s`) | `engine.py:3086-3087` | gộp với AUD-003 |
| AUD-024 | Match đã bù tốc độ vẫn vỡ trong `_merge` vì dung sai `align` là hằng còn `align` trôi tuyến tính | `engine.py:2368-2372`, `:2468`, `:2478` | Gộp theo `align` của khúc đã bù, hoặc nới dung sai theo `\|1-r\| × span` |
| AUD-026 | Cảnh báo `--max-matches` bảo người dùng chỉnh một control **không tồn tại** | `engine.py:2650-2655` | Đổi lời văn để chỉ đúng key `max_matches` trong `data/cau_hinh.json` |
| AUD-028 | `shifts_quet = 0` **không** tắt shifts — audfprint mặc định 4 ở đường match | `engine.py:2324-2326`; `audfprint-master/audfprint.py:294-297` | Sửa help text ở `app.py:519-522`; đây là vấn đề nhãn, không phải hành vi |
| AUD-029 (LIKELY) | Cột «Đánh giá» gần như là hằng số vì `min_hash_floor` = 1000 > mọi ngưỡng của `danh_gia` | `engine.py:566-572`; `chap_nhan_khop.py:90`; `engine.py:186` | Hiệu chỉnh lại band, hoặc thay bằng `ty_le`/mật độ |
| AUD-030 ≡ 204 | `clip_offset_s` báo mốc trong VIDEO thay vì offset trong CLIP khi bị kẹp về 0 | `engine.py:2507-2516`; `engine.py:3321`, `:3365` | Gán thẳng `som_nhat["t_clip"]` |
| AUD-027 (**HYPOTHESIS**) | `search_depth = 100` của audfprint là trần recall chưa ai đo | `audfprint-master/audfprint_match.py:136-146`; `engine.py:2320-2327` | **Đo trước khi sửa**: ghi `len(np.unique(allids))` mỗi khúc, đối chiếu với kho 1717 clip |

**Fingerprint & registry**

| ID | Một dòng | Bằng chứng | Bước tiếp |
|---|---|---|---|
| AUD-044 | Huỷ build đa nhân rò `%TEMP%/timclip_ht_*` (Windows `TerminateProcess` bỏ qua `finally`) | `audfprint_progress_runner.py:195`, `:260-264`; `process_runner.py:151-153` | Đặt thư mục fan-in **trong** workspace mà parent đã dọn |
| AUD-046 ≡ 223 | `dong_goi_may_chay` đọc `khos.json["db"]` **không** qua guard `_duong_dan_db_kho` | `dong_goi_may_chay.py:89-94`; `engine.py:743-765` | Nâng guard thành hàm module-level, gọi từ cả 3 chỗ join thô |
| AUD-047 ≡ 163 | (cùng defect `khos.json` sai hình dạng) | `engine.py:770-787` | gộp với AUD-163 |
| AUD-050 | Fallback `PermissionError` có thể bỏ rơi kho vừa dựng khi không có kho tên | `engine.py:1945-1961` | Assert vòng lặp khớp đúng một entry; hoặc từ chối fallback khi không có kho |
| AUD-223 ≡ 046 | (cùng defect, góc bảo mật) | `dong_goi_may_chay.py:89-94` | gộp với AUD-046 |
| AUD-224 | `.pklz` được unpickle và luồng triển khai chuyển nó giữa các máy **không** kiểm tính toàn vẹn | `engine.py:1031-1042` | Ghi một câu vào `docs/TRIEN_KHAI_MAY_PHU.md`: kho vân tay chỉ được đến từ máy của chính operator |

**Metadata & định danh**

| ID | Một dòng | Bằng chứng | Bước tiếp |
|---|---|---|---|
| AUD-066 | `va_metadata_thieu` ghi lại **toàn bộ** snapshot (+ `.bak`) sau **mỗi** entry — O(n²) I/O | `engine.py:1621`; `luu_tru.py:85-86` | Flush theo lô 25 như `channel.py:296-299`, **kèm `finally`** (thiếu là mất hết khi huỷ) |
| AUD-067 | Ba writer `clips_meta.json` không có khoá liên tiến trình | `channel.py:180-181`; `kiem_ngay_dang.py:230`; `kiem_thoi_luong.py:136` | Khoá per-kho cạnh `clips_meta.json`, giữ **suốt** read-modify-write |
| AUD-069 | URL `/shorts/` và `/embed/` bị coi là không hợp lệ → trường url bị xoá | `clip_metadata.py:69-88`, `:333-342` | Chấp nhận thêm segment đầu sau `/shorts/`, `/embed/`, `/live/`, `/v/` |
| AUD-X01 | Lịch sử chỉ lưu 4/8 cột đầu của báo cáo 34 cột — kênh vi phạm và ngày đăng bị mất | `engine.py:874-878` vs `bang_ngang.py:82-88` | Sửa cùng AUD-064 |
| AUD-X02 | Snapshot là phép chiếu **mất mát**: đổi tên `publication_date`→`upload_date`, gộp `duration_media` vào `duration`, bỏ hẳn `publication_date_source` | `clip_metadata.py:192-199`; `engine.py:1289-1292` | Mang các key theo đúng tên; là tiền đề cho AUD-061 |
| AUD-X03 | `delete_kho` bỏ rơi snapshot; tạo lại kho **cùng tên** làm sống lại metadata của kho đã xoá | `engine.py:848-861` vs `engine.py:1085` | Cho `delete_kho` xoá cả snapshot + `.bak`, hoặc khoá snapshot theo id ổn định thay vì tên |
| AUD-X17 | Không deliverable nào phân biệt được tiêu đề YouTube thật với tên file đã lọc ký tự | `clip_metadata.py:817`, `:752`, `:947` vs `engine.py:3361`, `bang_ngang.py:106`, `dossier.py:56` | Lưu provenance của TITLE trong registry; **đừng** bỏ tiêu đề fallback (hiện tên file còn tốt hơn để trống) |
| AUD-X18 | Không có định danh tác phẩm xuyên kho, và không đường mã nào liệt kê được tác phẩm qua nhiều kho | `engine.py:1121-1138`, `:1007-1019`; `app.py:1404-1410` | Quyết định trước khi cấp `WORK_ID` đầu tiên: registry khoá theo (kho, tác phẩm) hay theo tác phẩm |

**Ngày đăng & thời lượng**

| ID | Một dòng | Bằng chứng | Bước tiếp |
|---|---|---|---|
| AUD-082 | `kiem_ngay_dang --repair-offline --apply` xoá chính tín hiệu mà `--audit` dùng để nói "vẫn cần repair-network" | `kiem_ngay_dang.py:84-92`, `:206-218`, `:123-128` | Đếm theo **độ tin cậy** (`TRUONG_DO_TIN_CAY_CAO`, `:43`) thay vì theo sự **hiện diện** của key |
| AUD-083 | `ScanResult.duration_s` mang hai ngữ nghĩa tuỳ đường tải; `docs/DURATION_ARCHITECTURE.md` nói ngược lại | `engine.py:3064-3067` vs `:3194-3195` | Sửa **tài liệu** (`§3`, `§5`) — chênh lệch ≤1 giây, không đáng thêm trường + migration |
| AUD-085 | Provenance ngày đăng bị rơi ở ba tầng; tier `filename` là mã chết | `channel.py:110-112` (0 caller); `clip_metadata.py:152-160`; `publication_date.py:218-227` | Xoá tier chết hoặc nối nó vào; thêm `publication_date_source` vào `_FIELDS` |
| AUD-086 (LIKELY) | `_mui_gio` âm thầm rơi về UTC — tái hiện đúng lỗi lệch 1 ngày mà module sinh ra để chặn | `publication_date.py:115-122` | Validate tên timezone lúc parse CLI/khởi động và **fail fast**; hoặc cho `_mui_gio` báo hiệu để `resolve` hạ confidence |
| AUD-087 (LIKELY) | `hhmmss` có 2 bản sao; `duration_media` lưu ở hai độ chính xác; `Engine.duration_of` thiếu guard `isfinite` | `kiem_thoi_luong.py:54-56` vs `engine.py:407-431`; `kiem_thoi_luong.py:115` vs `channel.py:603`; `engine.py:993-1001` | Ba việc nhỏ độc lập. Guard `isfinite` là rẻ nhất và đúng nhất |
| AUD-088 | Bảng xem trước kênh in `YYYYMMDD` thô thay vì qua `format_publication_date` | `app.py:993`, `:1038` | Bọc `publication_date.format_publication_date(...)` |
| AUD-204 ≡ 030 | (cùng defect `clip_offset_s`) | `engine.py:2507-2516` | gộp với AUD-030 |

**YouTube / mạng**

| ID | Một dòng | Bằng chứng | Bước tiếp |
|---|---|---|---|
| AUD-103 | `va_metadata_thieu` retry **mọi** lớp lỗi 3 lần, khuếch đại traffic đúng lúc YouTube đang chặn | `engine.py:1534-1541` | Phân loại trước khi retry; thêm circuit breaker như `kiem_ngay_dang.py:192-195` |
| AUD-104 | `NhoClientTotNhat` làm mới TTL sau **mỗi** thành công → biến bộ đếm dò-lại thành idle timer, không bao giờ hết hạn trong một lượt sync dài | `ytdlp_chung.py:455-457`, `:445-446` | Reset timestamp khi `client != self._client` **hoặc** `not self._con_han()` — chỉ điều kiện đầu sẽ làm memory kẹt vĩnh viễn ở trạng thái hết hạn |
| AUD-105 | `CauHinhMang.tu_file_cau_hinh` không kiểm khoảng giá trị mà `Config.validate` từ chối | `ytdlp_chung.py:308-323` | Áp cùng bound; rơi về mặc định cho giá trị ngoài khoảng |
| AUD-X12 | Ladder fallback bắn tới 5 (10 nếu có cookie) lần tải liên tiếp **không nghỉ** giữa các client | `ytdlp_chung.py:495-517`, `:393-422`; `:354` | Tôn trọng `sleep_requests_s` giữa các client; thêm circuit breaker theo mẫu `kiem_ngay_dang.py:182-195` |
| AUD-228 (LIKELY) | Video ID được nội suy thẳng vào đường dẫn filesystem, không qua sanitiser nào | `channel.py:465-469`; `engine.py:2068-2069`, `:2093` | Bọc `ten_file_hop_le`. Đường `channel.py` **không** thoát được (`channel.py:537-539` chặn); chỉ `engine.py:2093` có lỗ |

**UI / threading / Sheets**

| ID | Một dòng | Bằng chứng | Bước tiếp |
|---|---|---|---|
| AUD-123 (LIKELY) ≡ 148 | `SheetDeliveryWorker.enqueue` dùng `Queue.put` **chặn** | `sheet_delivery.py:136`, `:155` | `put_nowait` + đánh dấu THAT_BAI khi đầy. Điều kiện thật để đầy là AUD-X13 (không timeout), không phải rate-limit |
| AUD-124 | Queue sự kiện + `recent()` của `ScanJobController` **không có consumer nào** | `scan_jobs.py:157-158`, `:378-380` | Quyết dứt điểm: render, hoặc xoá. Nếu render thì **phải** clear `_events` trong `start()` (hiện chỉ clear `_recent` ở `:183`) — xem AUD-X09 |
| AUD-125 ≡ 261 | Đường quét Streamlit không lấy `data/tool.lock`, trái CLAUDE.md:78-80 | `engine.py:3043`, `:3142`; `watch.py:287` | **Sửa tài liệu**, không sửa mã (khoá non-reentrant). Xem §4.7 |
| AUD-126 | Thread `SheetDeliveryWorker` không bao giờ được stop; map idempotency không bao giờ được prune | `app.py:111`, `:674`; `sheet_delivery.py:137`, `:167-176` | Gọi `stop()` trước khi thay object và trước `st.session_state.clear()`; prune theo batch |
| AUD-127 | `tests/test_bang_ket_qua_arrow.py` test một **bản sao** của quy tắc ép kiểu, không test hàm thật | `tests/test_bang_ket_qua_arrow.py:48-53`, `:102-110`; `app.py:344-354` | Tách `df_ket_qua` ra module không-Streamlit (mẫu `scan_ui.py`), hoặc seed `job["results"]` trong AppTest |
| AUD-142 ≡ 205 | (cùng defect escaping) | `app.py:123` | gộp với AUD-205 |
| AUD-143 ≡ 166 | Không handler nào cho logger `scan.sheet` | `sheets.py:29`; `sheet_delivery.py:32` | gộp với AUD-166 |
| AUD-145 (LIKELY) | Nút «📊 Đẩy lên Google Sheets» đẩy lại **mọi** dòng đã giao tự động | `app.py:426-433`, `:141` | Disable/confirm khi `job["da_day_sheet"]`, hoặc chỉ đẩy dòng chưa `DA_GUI` |
| AUD-146 | Sidebar ghi «Dọc (chi tiết, 15 cột)» trong khi `Engine.HEADER` có 16 | `app.py:630`; `engine.py:3317-3322` | Sửa nhãn — **kèm** `tests/test_app.py:49` vốn ghim đúng chuỗi đó |
| AUD-148 ≡ 123 | (cùng defect blocking put) | `sheet_delivery.py:155` | gộp với AUD-123 |
| AUD-149 (LIKELY) | Lỗi dựng dòng trong callback giao hàng bị nuốt; video im lặng không tới Sheets, UI hiện «—» | `app.py:117-136`; `engine.py:3252-3258`; `scan_ui.py:57-64` | Bọc riêng khối dựng dòng; ghi một `SheetDelivery` trạng thái lỗi. Chưa tìm được trigger thật |
| AUD-X09 | `ScanJobController.start()` clear 3 container nhưng **không** clear `_events` | `scan_jobs.py:182-184` vs `:158` | Quyết cùng AUD-124 |
| AUD-X32 | Panel zero-match của Streamlit chép lại ngưỡng nhạc hiệu bằng hằng số viết tay và áp **đúng quy tắc mà `chan_doan_quet.py` ghi là SAI** | `app.py:294-299` vs `chan_doan_quet.py:242-259`, `:272` | Thay `app.py:294` bằng `if cd.dau_hieu_nhac_hieu:` (cờ đúng đã có sẵn trên chính object đó) |
| AUD-X34 | Hai khối `except` phòng thủ cho "không đọc được kho" là **mã không thể chạm tới**, vì `db_clips()` biến mọi lỗi đọc thành list rỗng **được cache** | `engine.py:1052-1054` làm chết `:2425-2431` và `:2531-2533` | Phân biệt "kho rỗng" với "không đọc được kho" (cờ `self.kho_doc_loi`), **không cache** thất bại, rồi xoá hai khối chết |

**Persistence / cleanup / logging**

| ID | Một dòng | Bằng chứng | Bước tiếp |
|---|---|---|---|
| AUD-165 | Hai reader `cau_hinh.json` với ngữ nghĩa lỗi khác nhau; đường CLI nhẹ mất cookie im lặng | `ytdlp_chung.py:285-323`; `cli.py:169-172` | Cho `tu_file_cau_hinh` đi qua `luu_tru.doc_json_an_toan` **trong** `try` sẵn có |
| AUD-169 | `lichsu.db` chạy rollback-journal với busy timeout 5 s mặc định | `engine.py:895-903` | `PRAGMA journal_mode=WAL` + `busy_timeout=10000`; bọc `save_job` để lỗi ghi lịch sử không giết cả lô |
| AUD-170 | File cách ly `*.hong.*` được tạo nhưng **không bao giờ** được dọn | `luu_tru.py:107-115`, `:151` | Thêm retention vào lệnh `dondep`; thêm pattern vào `.gitignore` |
| AUD-185 ≡ 004 | (cùng defect `TIMCLIP_DATA_DIR`) | `engine.py:632` | gộp với AUD-004 |
| AUD-X04 | `<kho>/_tam` là scratch **theo kho**, có `rmtree` toàn thư mục và quét `.part` toàn thư mục | `channel.py:171`, `:614`, `:502-507` | `_tam/<uuid4>` per-sync, đúng mẫu `scan_workspace`; quét `.part` theo `v.id` |
| AUD-X08 | **Không** lời gọi ffmpeg/ffprobe nào có timeout, và không huỷ được giữa chừng | `engine.py:995`, `:2272`, `:2906`; `channel.py:81`, `:543`; `kiem_thoi_luong.py:44` | Thêm `timeout=` (mọi call site đã có handler sẵn, trừ `Engine.duration_of` cần guard riêng ở `engine.py:998`) |

**CLI / triển khai / đóng gói**

| ID | Một dòng | Bằng chứng | Bước tiếp |
|---|---|---|---|
| AUD-184 | Guard chống-lùi của updater chỉ chặn khi HEAD **đi trước** tag — nên nó đã tách HEAD của repo này khỏi `main` | `cap_nhat.py:141`, `:195-200`, `:215` | Hỏi `git symbolic-ref -q HEAD`; nếu là nhánh thì từ chối hoặc đòi cờ tường minh. Thêm test cho ca "ở ngang hoặc sau tag" |
| AUD-186 | Nâng cấp tại chỗ máy phụ ghi đè `data/cau_hinh.json` cục bộ (mất cấu hình cookie của máy đó) | `dong_goi_may_chay.py:195`; `docs/TRIEN_KHAI_MAY_PHU.md:141-142` | Đóng gói thành `cau_hinh.mau.json`, chỉ copy khi chưa có; hoặc merge giữ `KHOA_RIENG_CUA_MAY` |
| AUD-187 | Watchlist thiếu/hỏng làm `cli.py watch` **thoát 0** trong khi không giám sát gì | `cli.py:82`; `luu_tru.py:149-160`; `GiamSat.bat:11` | Phân biệt "file không tồn tại" (thoát khác 0) với "file parse được nhưng rỗng"; thêm guard `if not exist` vào `GiamSat.bat` như `ChayMayPhu.bat:15-18`. **Cập nhật cả `docs/RUNBOOK.md:100`** vốn backup sai tên file |
| AUD-188 | `docker-compose` publish UI không xác thực lên mọi interface **của host** | `docker-compose.yml:6`; `Dockerfile:20-21` | `"127.0.0.1:8501:8501"`. **Đừng** đổi `Dockerfile` — `0.0.0.0` đúng bên trong container |
| AUD-189 | `.dockerignore` loại `dong_goi.py` nhưng ship `dong_goi_may_chay.py` vốn import nó | `.dockerignore:58`; `dong_goi_may_chay.py:41` | Loại cả hai, hoặc không loại cái nào |
| AUD-190 ≡ 252 | `requirements-lock.txt` ghim phiên bản **dưới** sàn bảo mật của `constraints.txt`, và nó được git track | `constraints.txt:1-4`; `requirements-lock.txt:10`, `:13` | Quyết định: hoặc regenerate (UTF-8, thoả constraints) và dùng thật, hoặc xoá |
| AUD-225 | Cài đặt và Docker build tải mã bên thứ ba **không ghim, không checksum** rồi chạy | `cai_dat.bat:49-52`, `:63-70`; `Dockerfile:14-16` | Ghim audfprint theo commit SHA; verify SHA-256 cả hai archive. Đây là hạng mục đã ghi ở `docs/OPTIMIZATION_PLAN.md:65-66` |
| AUD-252 ≡ 190 | `requirements-lock.txt` là UTF-16LE nên grep/diff không đọc được | `requirements-lock.txt:1` (BOM `ff fe`) | Ghi lại bằng UTF-8 |
| AUD-X11 | Mỗi lần mở GUI bắt đầu bằng `git fetch` đồng bộ, tối đa 90 s | `ChayTool.bat:33`; `cap_nhat.py:137`, `:46` | **Lối thoát đã có**: `ChayTool.bat --da-cap-nhat` (`ChayTool.bat:30`). Chỉ cần đặt tên/ghi tài liệu, hoặc hạ `TIMEOUT_MANG_S` xuống ~15 s |
| AUD-X15 | Lượt `watch` theo lịch **ghi vĩnh viễn** lựa chọn kho, đổi kho mà GUI và các lệnh CLI khác dùng sau đó | `watch.py:371-374`; `engine.py:832-838` | Thêm `use_kho(ten, luu=False)` bỏ `_ghi_khos`; `watch` dùng dạng đó |

**Bảo mật (không có rò rỉ đang xảy ra)**

| ID | Một dòng | Bằng chứng | Bước tiếp |
|---|---|---|---|
| AUD-226 | Một đường tải CSV bỏ qua `o_bang_tinh_an_toan` | `app.py:1495-1497` | Dựng frame CSV riêng (mẫu `app.py:411-414`) — **không** ép kiểu chính `df` vì `app.py:1494` cũng render nó |
| AUD-227 | URL Google Sheet sản xuất bị hardcode và git-track | `GiamSat.bat:11` | Dùng `%SHEET_LINK%` như `ChayMayPhu.bat:33-37`. **Kiểm quyền chia sẻ của Sheet đó** — nếu là "anyone with the link" thì phải xoay |
| AUD-229 | `session.log` bị git track dù có luật `*.log`; masking bí mật của `nhat_ky` là denylist 2 chuỗi | `.gitignore:39-40` vs `git ls-files`; `nhat_ky.py:20-23` | `git rm --cached session.log` (hoặc đổi tên `.md`); mở rộng `che_bi_mat` sang pattern cookie-shaped |

**Test & tài liệu**

| ID | Một dòng | Bằng chứng | Bước tiếp |
|---|---|---|---|
| AUD-241 | `kiemtra.bat` bước 3/3 chạy app thật trên `data/` sản xuất | `kiemtra.bat:22`; `app.py:41-45` | Đặt `TIMCLIP_DATA_DIR`/`TIMCLIP_OUTPUT_DIR` ở đầu file, hoặc bỏ bước 3/3 (nó trùng `tests/test_app.py:28-29` vốn đã cách ly) |
| AUD-243 | Mỗi lần render AppTest mở và parse `google_key.json` thật | `app.py:636-640` → `sheets.py:96-97`, `:132` | Truyền `key_path` tường minh từ `app.py`, hoặc monkeypatch `sheets.SheetsExporter` |
| AUD-244 | `test_khong_con_file_tam_sau_khi_that_bai` assert trên temp dir **toàn máy** | `tests/test_audfprint_multiproc.py:85-98` | `monkeypatch.setattr(runner.tempfile, "tempdir", str(tmp_path))` — test đã nhận `tmp_path` mà không dùng |
| AUD-246 | 6/10 verb CLI không có test nào | `cli.py:185-314` | Fixture `cli_engine_gia` dùng chung; phủ `youtube --file`, `file <dir>`, và ba nhánh in kết quả |
| AUD-247 | `Engine.__init__` sửa `PATH` toàn tiến trình, không bao giờ khôi phục | `engine.py:645-646` | Guard `if os.path.isdir(self.bin_dir)` — xoá ~40 entry rác với 0 thay đổi hành vi |
| AUD-248 | `kiem_ngang.py` dựng `Engine()` ở cấp module | `kiem_ngang.py:62` | Bọc vào `main()` + `if __name__ == "__main__"` như 4 script anh em đã có |
| AUD-249 | Tiến trình con của `test_khoa.py` phụ thuộc cwd của pytest | `tests/test_khoa.py:61-76` | Đặt `env["PYTHONPATH"]` (mẫu `tests/test_publication_date.py:236-239`) |
| AUD-250 | `conftest.M()` dựng `Match` **bất khả thi về ngữ nghĩa** (có `start_s`, thiếu `clip_bat_dau_s`/`vung_khop_s`) — và cùng lỗi ở ~12 chỗ khác | `tests/conftest.py:65-69`; `engine.py:2489`, `:2507-2520` | Thêm `__post_init__` cho `Match`, hoặc một factory dùng chung. Sửa riêng conftest để lại bẫy ở 11 chỗ còn lại |
| AUD-261 ≡ 125 | (cùng defect bất biến khoá) | `engine.py:3043`; `CLAUDE.md:78-80` | gộp với AUD-125 |
| AUD-262 | `CLAUDE.md:187` và comment `engine.py:141` nói sai thứ tự player client mặc định | `ytdlp_chung.py:48` (`["", "android", …]`) — **kiểm trực tiếp vòng này** | Sửa/xoá comment `engine.py:140-141`; đánh dấu literal ở `CLAUDE.md:187` là giá trị **tại thời điểm sự cố 18/08** |
| AUD-263 | `HUONG_DAN.md` §B hứa một hành vi GUI **đã bị gỡ** (gợi ý hạ ngưỡng) | `HUONG_DAN.md:396-399`; `app.py:294-299` | Viết lại theo `docs/RUNBOOK.md:159-163`; §10 (`:174`) cũng nên trỏ tới panel chẩn đoán |
| AUD-264 | Hai hành vi mặc-định-BẬT đổi lượng tải/quét chỉ được ghi trong CLAUDE.md | `engine.py:170`, `:177` | Thêm 2 dòng vào bảng `HUONG_DAN.md:376-384` |
| AUD-265 | RUNBOOK + OPTIMIZATION_PLAN liệt kê workspace per-scan là "chưa làm" | `docs/RUNBOOK.md:323`; `docs/OPTIMIZATION_PLAN.md:52` vs `engine.py:2220` | Tách dòng RUNBOOK làm hai: temp dir **xong**, khoá **còn treo** |
| AUD-266 | `SYSTEM_OVERVIEW` nói ngược sự thật về git-tracking của `watchlist.json` và `requirements-lock.txt` | `docs/SYSTEM_OVERVIEW.md:110`, `:125` | Sửa; nguồn chân lý là `docs/TU_CAP_NHAT.md:101` |
| AUD-267 | Docstring của `chap_nhan_khop.py` bỏ mất rào chắn mật độ bậc A mà chính nó thực thi | `chap_nhan_khop.py:23` vs `:88-96` | Sửa cả khối dòng 19-26 (dòng 19-21 còn khẳng định một bất biến "chỉ thêm" nay không còn đúng về mặt cấu trúc) |
| AUD-268 | `DURATION_ARCHITECTURE.md` §3 nói `duration_s` một ngữ nghĩa, còn `pham_vi_quet_s` đã tồn tại | `docs/DURATION_ARCHITECTURE.md:53-56` vs `engine.py:386-390`, `:3194` | Thêm §3b nói rõ đường tải một phần |
| AUD-270 | `HUONG_DAN.md` mâu thuẫn chính nó về overlap; ncores mặc định sai | `HUONG_DAN.md:37` vs `:137`; `:139` vs `engine.py:115` | Sửa hai dòng |
| AUD-271 | `MATCH_SELECTION_ARCHITECTURE.md` §1/§4 mô tả mô hình xếp hạng **đã bị thay** mà không đánh dấu | `docs/MATCH_SELECTION_ARCHITECTURE.md:33`, `:80`, `:83` vs `engine.py:235`, `:2586-2594` | Gạch ngang + trỏ §8, đúng quy ước file đó đã dùng ở `:157` |
| AUD-272 | `CLAUDE.md:594` bảo agent kế tiếp ghi đè một kế hoạch **đã hoàn thành** | `CLAUDE.md:591-595`; `docs/EXECUTION_PLAN.md` | Đổi thành `docs/EXECUTION_PLAN_<chữ cái kế tiếp>.md` |
| AUD-273 | Trích dẫn dòng trong ba tài liệu lệch 66-1150 dòng | `docs/SCAN_PIPELINE_V2_DESIGN.md:15`; `docs/CLAUDE_HANDOFF.md:20`; `CLAUDE.md:131` | Chuyển sang trích **tên symbol**; sửa `CLAUDE.md:131` trước (file duy nhất không ghim base commit) |
| AUD-274 | `session.log` là file `.md` bị bỏ hoang, tracked, chứa đường dẫn dev cũ | `session.log:3`, `:21`; `.gitignore:40` | Đóng lại bằng một entry trỏ CLAUDE.md, hoặc `git rm --cached` |
| AUD-275 | `CLIP_METADATA_ARCHITECTURE.md` mô tả schema `clips_meta.json` thiếu 3 field | `docs/CLIP_METADATA_ARCHITECTURE.md:43-53` vs `channel.py:592-605` | Thay khối JSON; nêu thêm writer thứ hai `kiem_thoi_luong.py` |
| AUD-276 | `README.md` thiếu lệnh `vametak` | `README.md:26`; `cli.py:104-116` | Thêm, kèm một mệnh đề nói nó nhắm vào snapshot của kho **đang active** |
| AUD-X10 | Telemetry của Streamlit mặc định BẬT; hai lệnh khởi động trong tài liệu thiếu cờ tắt; `app.py:9` khẳng định ngược lại | `.venv/.../streamlit/config.py:1304-1310`; `README.md:25`; `docs/SYSTEM_OVERVIEW.md:61`; `app.py:9` | Commit `.streamlit/config.toml` (`gatherUsageStats=false` + `address=127.0.0.1`) — sửa luôn AUD-222 |
| AUD-X22 | `SO_DOAN = 5` có **hai bản sao nữa** dưới dạng số 5 viết cứng trong Apps Script, tên cột dựng bằng nối chuỗi | `apps_script/File03_XuatHangDaChon.gs:248`, `:267` | Nâng `SO_DOAN` thành hằng trong File01; mở rộng `kiem_header.py` để assert cả trần slot |
| AUD-X24 | `TOAN_BO_AppsScript.gs` (85 KB) khai là sinh tự động nhưng **không có generator** trong repo | `apps_script/README.md:77-78` | Commit generator + test so sánh, hoặc xoá file gộp và chỉ hỗ trợ đường 7-file |
| AUD-X27 | Mã thoát `cli.py watch` **ngược** với trạng thái giao Sheets: giao 0 dòng thoát 0, giao đủ dòng thoát 1 | `watch.py:394-410`, `:513-515` vs `:430-435`; `cli.py:97-98` | Suy mã thoát từ trạng thái giao hàng; gộp với AUD-144 |
| AUD-X28 (LIKELY) | Danh sách findings có nhiều cặp trùng, severity gán theo domain chứ không theo defect | (chính tài liệu này) | Đã xử lý: cột `≡` trong các bảng trên |
| AUD-X29 | Sửa P1 hàng đầu **bắt buộc** phá một test đang xanh vốn khoá defect như hợp đồng | `tests/test_clip_metadata.py:229-268` — **đọc trực tiếp vòng này** | Tính chi phí viết lại test đó vào công việc sửa AUD-061 |

---

## 9. Next recommended task

> **Khôi phục cổng kiểm thử: một môi trường duy nhất, và `kiemtra.bat` phải báo được lỗi.**

Cụ thể, ba việc nhỏ trong cùng một lần sửa:

1. Cài `pytest>=9,<10` (và `ruff`) vào `.venv` để interpreter **được test** trùng
   interpreter **chạy thật**. **Không** chạy `pip install -r requirements-dev.txt` khi app
   đang chạy: dòng 1 của nó là `-r requirements.txt`, vốn không ghim gì và sẽ nâng cấp
   numpy/scipy/yt-dlp/streamlit/pandas ngay dưới chân hai tiến trình Streamlit đang sống.
2. Thêm `|| echo   [X] LOI` vào `kiemtra.bat:18` **và** `:22` — hiện chỉ dòng 14 có guard,
   nên bước test và bước render app **không thể** báo hỏng.
3. Đặt `TIMCLIP_DATA_DIR` / `TIMCLIP_OUTPUT_DIR` trỏ vào thư mục tạm ở đầu `kiemtra.bat`
   (hoặc chỉ quanh bước 3/3), để nó thôi dựng `Engine()` trên `data/` sản xuất
   (`kiemtra.bat:22` → `app.py:41-45`).

### Vì sao đây là việc có giá trị cao nhất, không phải P1 nào đó

- **Nó là tiền đề cho mọi việc còn lại.** Sáu P1 phân biệt đều cần sửa mã có kiểm chứng.
  Hiện `kiemtra.bat` — cổng duy nhất của dự án, vì `.github/` không có workflow nào —
  **xanh theo cấu trúc**: nó ghim vào một `.venv` không có pytest và không có guard báo
  lỗi. Sửa bất cứ P1 nào trước khi sửa cái này nghĩa là sửa mà không có lưới an toàn.
- **Nó rẻ và hoàn toàn nằm trong tay kỹ sư.** Ba dòng `.bat` cộng một lệnh `pip install`.
  Không cần quyết định sản phẩm nào.
- **Ba P1 lớn nhất đều không phải "task" thuần.** AUD-061/081 là **xung đột yêu cầu**
  (kho nào là chân lý?) và sửa nó **bắt buộc** viết lại `tests/test_clip_metadata.py:229-268`
  — không nên làm khi chưa chạy được test. AUD-X19 cần một quyết định migration
  (dòng lịch sử cũ không có kho thì tính là "đã quét cho mọi kho" hay "chưa quét cho kho
  nào"?). AUD-201 cần quyết định có thêm cột vào header 34 đang đóng băng hay không.
- **Nó biến baseline thành bằng chứng thật.** Con số "952 passed" hiện đo trên Python
  3.14 + yt-dlp bản dev, không phải trên `.venv` 3.12 + yt-dlp phát hành mà người dùng
  thật chạy. Sau bước này, mọi câu "test vẫn xanh" mới có nghĩa.

**Việc kế tiếp sau đó** (không phải bây giờ): xây kênh cảnh báo của **AUD-X31**
(`ScanResult.canh_bao` tách khỏi `note`), vì AUD-201, AUD-025, AUD-143 và AUD-166 đều nằm
sau cùng một bề mặt còn thiếu đó — sửa một lần giải quyết bốn.

---

## 10. Những gì trong `CLAUDE_HANDOFF.md` cũ nay đã lỗi thời

File cũ (`docs/CLAUDE_HANDOFF.md`, 2026-08-07 → 2026-08-08) vẫn có giá trị cho **các giả
thuyết bị bác bỏ** và **số đo lịch sử**. Nhưng những khẳng định sau **không còn đúng**:

| Vị trí | Khẳng định cũ | Trạng thái hôm nay |
|---|---|---|
| `:3` | "Nhánh `main`, base `448b467`, chưa commit" | **Sai.** HEAD detached ở `7f85c8d` (tag `v2.6`); `main` cục bộ ở `f4ae37a` (= `v2.4`); cây sạch |
| `:20` | "`scan_youtube` gọi `save_job(kq)` (`engine.py:2063`, `2110`)" | Kết luận **đúng**, số dòng **lệch ~1.100**: `save_job` định nghĩa ở `engine.py:3273`, gọi ở `:3142` và `:3221` (AUD-273) |
| `:37`, `:87`, `:110`, `:114` | "449 / 470 / 496 / 504 passed" | Đều bị vượt qua. Số hiện tại: **952 passed, 1 skipped, 5 deselected** (`baseline.md:11`) |
| `:65-66` | "`_cut_chunks`/`_match_chunks` giữ nhánh cũ để tương thích ngược; mọi call site đã dùng workspace riêng" | Vẫn đúng, nhưng nhánh cũ nay là **mã chết trong sản phẩm** (`engine.py:2250-2253` chỉ còn `tests/test_tang_toc.py` gọi) và `rmtree data/chunks` ở `engine.py:3139` không bao giờ chạm gì (AUD-006) |
| `:118-127` | "Dữ liệu ngày đăng — ĐÃ XONG cả ba kho" | Số liệu vẫn là bản ghi lịch sử hợp lệ, **nhưng** kết luận vận hành nay có điều kiện: nếu kho có snapshot thì hiệu chỉnh ghi vào `clips_meta.json` **không tới được báo cáo** (AUD-061/081) |
| `:157` | "Fast Top-1 … Tối đa 2 lần nạp kho" | **Sai với video dài.** `_quet_tho` được gọi **một lần mỗi đoạn** quét tăng dần (`engine.py:3086`), nên video 35 tiếng cho tới 12 đoạn × tối đa 2 = 24 lần nạp (AUD-042) |
| `:163-164`, `:200` | "Cân nhắc siết bậc A bằng điều kiện mật độ — chưa làm" | **Đã làm.** `mat_do_bac_a = 3.0` ở `engine.py:203`, thực thi ở `chap_nhan_khop.py:88-96` |
| `:245-247` | "2.600 clip trong 3 kho chưa có `duration_media`" | Trạng thái thật **UNKNOWN** (`data/` ngoài phạm vi vòng này). Kể cả khi chạy `kiem_thoi_luong.py --sua --that-su`, kết quả **không tới được báo cáo** nếu kho đã có snapshot (AUD-061/081) |
| `:264-266` | "`watch` lọc bằng `ids_da_quet()` đọc `lichsu.db` cục bộ → N máy cùng watchlist sẽ quét trùng" | Đúng, **nhưng bỏ sót trục quan trọng hơn**: cùng một máy, `ids_da_quet` cũng không lọc theo **kho** (AUD-X19) |

---

## 11. Câu hỏi còn treo (cần người quyết định)

Không có câu nào trong số này trả lời được bằng cách đọc mã. Chúng chặn những mảng công
việc lớn.

1. **`data/metadata/kho_<slug>.json` hay `<kho>/clips_meta.json` là chân lý?**
   Chặn AUD-061/081, và chặn mọi tính năng metadata. Sửa theo hướng nào cũng phải viết lại
   `tests/test_clip_metadata.py:229-268`.
2. **Cửa sổ vi phạm trong hồ sơ nên bắt đầu ở `start_s` hay `vung_khop_s`?**
   AUD-021 (CONFIRMED, 2/2) nói phải đổi sang `vung_khop_s`, và
   `docs/PHASE2_FIX_PLAN.md:265` đã ghi quyết định đó. Nhưng phản biện đã **bác bỏ**
   AUD-203 với lập luận ngược: `start_s` = `bat_dau - t_clip` chính là giá trị **đã hiệu
   chỉnh** để triệt tiêu phần trim `--time-quantile 0.05` của audfprint
   (`audfprint-master/audfprint.py:368`), còn `vung_khop_s` mới là artifact. **Hai kết luận
   trái ngược về cùng ba call site** (`engine.py:3364`, `dossier.py:60-62`,
   `bang_ngang.py:64`). Đừng đụng `link_moc` cho tới khi giải quyết xong.
3. **Đường quét có được miễn `data/tool.lock` không?** Nếu có → sửa `CLAUDE.md:78-80` và
   nói rõ vì sao. Nếu không → cần refactor `_scan_*_da_khoa` vì khoá không reentrant.
   Hiện bất biến đang sai một cách có ý thức (§4.7).
4. **Works Registry khoá theo (kho, tác phẩm) hay theo tác phẩm?** Không đảo ngược được
   sau khi cấp `WORK_ID` đầu tiên (`engine.py:1121-1138`, `app.py:1404-1410` — AUD-X18).
5. **Một cài đặt phục vụ nhiều khách hàng, hay một cài đặt mỗi khách hàng?** Quyết định
   này đổi verdict của gần như mọi hạng mục multi-client, kể cả AUD-X19 và AUD-X20.
6. **`top_n` sống của máy này là 1 hay 5?** `data/cau_hinh.json` ngoài phạm vi. Mặc định mã
   là **5** (`engine.py:185`); `CLAUDE.md:554` nói máy operator để **1**. Severity của
   AUD-003, AUD-010, AUD-022, AUD-023 và AUD-042 lật theo giá trị này.
7. **`luoi_resample` / `luoi_tempo` sống là gì?** Mặc định mã là
   `[0.96, 0.98, 1.02, 1.04]` và `[]` (`engine.py:220-222`) — **kiểm trực tiếp vòng này**;
   `CLAUDE.md:504-506` nói cấu hình sống để **cả hai** rỗng. Quyết định độ phủ đổi cao độ.
8. **Python nào được hỗ trợ?** `README.md:9` / `Dockerfile:2` / `ruff.toml:1` nói 3.12; bộ
   test chỉ chạy được trên 3.14. Chọn một, ghi vào tài liệu (AUD-X26).
9. **`requirements-lock.txt` có phải đường cài đặt được hỗ trợ không?** Nếu có → regenerate
   thoả `constraints.txt` và ship. Nếu không → xoá (AUD-190/252).
10. **Sheet ở `GiamSat.bat:11` có đang chia sẻ "anyone with the link" không?** Quyết định
    AUD-227 là rò rỉ thật hay chỉ là mất vệ sinh.

---

*Vòng audit read-only, 2026-09-07. Không có file mã nguồn nào bị sửa. Tài liệu này là file
duy nhất được ghi.*

---

## PHỤ LỤC — cập nhật sau vòng audit (cùng ngày 2026-09-07)

Vòng audit trên là **read-only**. NGAY SAU đó, cùng ngày, có một vòng sửa lỗi thật.
Câu "không có file mã nguồn nào bị sửa" ở trên **chỉ đúng cho vòng audit**.

**Đã sửa:** `audfprint_progress_runner.py` — watchdog worker khi dựng kho vân tay.
Hằng số `CHO_WORKER_S = 1800.0` bị dùng như bộ phát hiện treo, nhưng kênh nó quan sát
(pipe) chỉ mang một message phát ra sau khi worker xong TOÀN BỘ phần việc — nên thực chất
nó là hạn chót cho tổng công việc. Kho `KhoJoeBartolozzi` 1178 clip bị giết ở mức 94,8%
**hai lần** trong sáng 2026-09-07 dù cả 8 worker đều đang chạy khoẻ, mất ~7 giờ CPU.

Nay mỗi worker đếm số file đã xong vào một `multiprocessing.Value`; cha chỉ báo lỗi khi
con số đó đứng yên suốt `CHO_WORKER_S`. Tên và giá trị hằng số giữ nguyên, chỉ ý nghĩa đổi.

**Đọc trước khi đụng vào đường dựng kho:**
* [JOEBARTOLOZZI_FAILURE_FORENSICS.md](JOEBARTOLOZZI_FAILURE_FORENSICS.md) — bằng chứng và dòng thời gian
* [FINGERPRINT_RECOVERY_ARCHITECTURE.md](FINGERPRINT_RECOVERY_ARCHITECTURE.md) — thiết kế watchdog, các phương án bị loại, bất biến phải giữ, và lý do HOÃN commit theo lô

**Hai điều cần biết ngay:**
1. `cli.py:126` để `--ncores` mặc định **1**, ghi đè cấu hình đã lưu (AUD-162). Luôn
   truyền `--ncores 0` khi dựng kho bằng CLI, nếu không sẽ chạy đơn nhân.
2. `--maxtimebits 16` (`engine.py:1909`) giới hạn định vị mốc ở **25,4 phút** mỗi clip
   gốc; quá mốc đó thời gian bị cuộn vòng im lặng. Ảnh hưởng 50,8% clip / 22,9% âm thanh
   kho Joe. Người dùng đã quyết **giữ nguyên** ngày 2026-09-07. Chi tiết ở
   FINGERPRINT_RECOVERY_ARCHITECTURE.md §6.1.
