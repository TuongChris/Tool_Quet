# JOE BARTOLOZZI — FORENSIC PHÂN TÍCH SỰ CỐ DỰNG KHO VÂN TAY

> **Vòng forensic READ-ONLY, 2026-09-07.** Không sửa mã nguồn, không ghi vào `data/`,
> không xoá gì. Mọi con số dưới đây đo trực tiếp từ `ketqua/fingerprint.log`
> (20.851 dòng) và từ source.

---

## 1. Tóm tắt một đoạn

Job dựng kho `KhoJoeBartolozzi` **không hề bị treo**. Cả 8 worker đều đang chạy khoẻ,
hoàn tất clip đều đặn 22–34 giây/clip, cho tới đúng giây cuối cùng trước khi bị giết.
Job bị huỷ vì **`rx[0].poll(1800)` trong `audfprint_progress_runner.py:224` không phải
watchdog liveness — nó là hạn chót cứng cho TOÀN BỘ phần việc của worker 0.**

Worker chỉ gửi **đúng một** message qua pipe, ở dòng 153, **sau khi** đã fingerprint xong
toàn bộ 148 clip của mình *và* ghi xong file gzip. Trước thời điểm đó pipe hoàn toàn im
lặng theo đúng thiết kế. Nên `poll(1800)` thực chất có nghĩa:

> "Worker 0 phải làm xong cả 148 clip trong vòng 30 phút, nếu không coi như nó chết."

Worker 0 cần khoảng **1900 giây**. Worker chậm nhất (worker 6) cần khoảng **2017 giây**.
Ngân sách là 1800 giây. **Job thiếu khoảng 3–4 phút.**

Hệ quả: **1117/1178 clip (94,8%) đã fingerprint xong bị vứt bỏ hoàn toàn.**

---

## 2. Dòng thời gian

| Thời điểm | Sự kiện |
|---|---|
| 08:40:39 | Streamlit khởi động (PID 41936, cha là PID 3312 — launcher) |
| 08:40:57 | Job `06126160adbd4e26ad039e4a4d012a89` bắt đầu, ghi `data/tool.lock` |
| 08:40:5x | Sinh 8 worker (`multiprocessing.Process`), chia file round-robin |
| ... | 1117 clip hoàn tất, trung bình 12,8 s/clip |
| 09:10:52 | `clip success index=1169` — worker vẫn đang chạy bình thường |
| 09:10:57 | `clip success index=1085 elapsed=34.344s` |
| 09:10:58 | `clip success index=1120 elapsed=22.469s`, `clip start index=1128` |
| 09:10:59 | **Cả 8 worker python.exe kết thúc CÙNG MỘT GIÂY** — bị cha `terminate()` |
| 09:10:59 | `process_end audfprint-build pid=43784 exit_code=1 elapsed=1801.844s` |
| 09:10:59 | `RuntimeError: Worker vân tay 0 không phản hồi sau 1800 giây.` |
| ~09:10:59 | `finally: shutil.rmtree(workspace)` (engine.py:1962) xoá sạch workspace |

`elapsed=1801.844s` ≈ đúng `CHO_WORKER_S = 1800.0` cộng chi phí khởi động.
Đây là dấu vân tay không thể nhầm của một hạn chót cố định, không phải của một sự cố.

**Đây là lần thất bại thứ hai cùng kiểu trong cùng buổi sáng:**

| job_id | Bắt đầu | Kết thúc | Tổng | Thành công | Kết quả |
|---|---|---|---|---:|---|
| `ee3b6254…` | 2026-08-21 00:34:24 | 00:44:00 | 537 | 537 | OK |
| `649fda63…` | 2026-09-04 05:24:44 | 05:30:10 | 149 | 149 | OK |
| `72311e74…` | 2026-09-07 06:42:26 | **07:12:31** | 1178 | **944** | **FAILED — cùng lỗi** |
| `06126160…` | 2026-09-07 08:40:57 | **09:10:59** | 1178 | **1117** | **FAILED — cùng lỗi** |

Hai kho thành công trước đây là 537 và 149 clip — **đều đủ nhỏ để mỗi worker xong dưới
30 phút**. Lỗi chỉ lộ ra khi kho vượt ngưỡng đó. Đây là lỗi **phụ thuộc quy mô**, và
1178 clip là lần đầu vượt ngưỡng.

Tổng thiệt hại: **944 + 1117 = 2061 clip-lượt fingerprint bị vứt**, tương đương khoảng
**7 giờ CPU** (14.290 CPU-giây riêng job thứ hai).

---

## 3. Cơ chế chính xác

### 3.1 Hai kênh hoàn toàn tách biệt

```
WORKER (8 tiến trình con của PID 43784)
   │
   ├── TIẾN ĐỘ ──> os.write(stdout)  "TIMCLIP_FINGERPRINT_EVENT {...}"
   │               (audfprint_progress_runner.py:36-40)
   │                     │
   │                     └──> stdout gộp của PID 43784
   │                            └──> engine._run_stream (tiến trình Streamlit)
   │                                   └──> log + UI     ← NGƯỜI DÙNG THẤY Ở ĐÂY
   │
   └── HOÀN TẤT ──> multiprocessing.Pipe   ĐÚNG MỘT message, ở CUỐI
                    (audfprint_progress_runner.py:153)
                          │
                          └──> rx[core].poll(1800)  ← WATCHDOG NHÌN Ở ĐÂY
                               (audfprint_progress_runner.py:224)
```

**Tiến trình cha PID 43784 không đọc stdout của chính nó.** Nó không thể nhìn thấy một
event tiến độ nào. Nó chỉ nhìn pipe — mà pipe im lặng theo đúng thiết kế cho tới khi
worker xong hẳn.

Đây chính là khoảng trống quan sát: **UI biết công việc đang tiến triển; tiến trình quyết
định giết công việc thì không.**

### 3.2 Event `heartbeat` trong log là heartbeat của CHA, không phải của worker

```
event=heartbeat phase=fingerprinting pid=43784
```

`pid=43784` là tiến trình audfprint cha. Heartbeat này chỉ nói "cha còn sống", không nói
worker nào còn tiến triển. Nó vẫn đập đều đặn suốt trong lúc watchdog đếm ngược tới lúc
giết một worker hoàn toàn khoẻ mạnh.

### 3.3 Comment mô tả một ý định mà code không thực hiện

`audfprint_progress_runner.py:21-24`:

```python
# Mỗi worker chờ tối đa bấy nhiêu giây sau khi tất cả worker đã báo xong. Chỉ là
# lưới an toàn cuối cùng để job không treo vĩnh viễn; đường chạy bình thường không
# bao giờ chạm tới.
CHO_WORKER_S = 1800.0
```

Tác giả tin rằng đây là lưới an toàn **sau khi** mọi worker đã báo xong. Thực tế
`rx[0].poll(1800)` bắt đầu đếm **ngay khi worker vừa được sinh ra**, và nó là toàn bộ
ngân sách cho 148 clip. **"Đường chạy bình thường không bao giờ chạm tới"** là sai:
đường chạy bình thường của một kho ≥ ~1000 clip luôn chạm tới.

Đây là lý do lỗi sống sót: không ai suy dẫn lại ngữ nghĩa thật của đoạn code từ chính nó.

### 3.4 Thông báo lỗi sai sự thật

> `Worker vân tay 0 không phản hồi sau 1800 giây.`

Worker 0 **đang phản hồi liên tục** — nó phát event stdout sau mỗi clip, clip gần nhất
chỉ vài giây trước. Nó chỉ chưa gửi message *kết thúc*, vì nó chưa kết thúc.
Thông báo này đã dẫn mọi phân tích đi sai hướng ("treo", "deadlock") trong khi sự thật là
"chưa xong".

---

## 4. Trạng thái Worker 0 (yêu cầu bắt buộc của brief §11)

Log hiện tại **không** ghi worker index. Nhưng cách chia file là tất định
(`audfprint_progress_runner.py:190-192`):

```python
filelists = [[] for _ in range(ncores)]
for ix, filename in enumerate(filename_iter):
    filelists[ix % ncores].append(filename)
```

Round-robin thuần → **worker của clip index `i` là `i % ncores`**. Với `ncores = 8`
(đếm được 8 PID con riêng biệt trong `event=clip start`), tái dựng được toàn bộ:

| worker | được giao | đã start | đã xong | còn lại | ước tính tổng thời gian cần |
|---:|---:|---:|---:|---:|---:|
| **0** | 148 | 141 | **140** | **8** | **~1900 s** |
| 1 | 148 | 148 | 147 | 1 | ~1805 s |
| 2 | 147 | 141 | 140 | 7 | ~1866 s |
| 3 | 147 | 144 | 143 | 4 | ~1835 s |
| 4 | 147 | 146 | 145 | 2 | ~1806 s |
| 5 | 147 | 137 | 136 | 11 | ~1943 s |
| 6 | 147 | 131 | **130** | **17** | **~2017 s** ← chậm nhất |
| 7 | 147 | 137 | 136 | 11 | ~1919 s |

**Worker 0 lúc bị giết:**

```
worker_id            : 0
đã hoàn tất          : 140 / 148 clip  (94,6%)
clip đang xử lý      : 1 (một trong 8 clip "started but not finished")
phase                : fingerprinting
tiến độ gần nhất     : vài giây trước khi bị giết
lý do timeout kích hoạt: chưa gửi message KẾT THÚC — vì chưa kết thúc
process_alive        : TRUE (bị cha terminate(), không tự chết)
```

**Không worker nào hoàn tất.** Worker gần nhất (worker 1) còn thiếu 1 clip.
Đúng 8 clip ở trạng thái "started but not finished" — **đúng một clip đang bay cho mỗi
worker**, khớp hoàn hảo với việc cả 8 worker đều đang bận làm việc lúc bị giết.

> Việc phải suy ra worker index bằng số học thay vì đọc thẳng từ log **chính là một
> finding**: instrumentation hiện tại không ghi `worker_id`. Xem §7.

---

## 5. Các giả thuyết khác — đã bác bỏ bằng số đo

| # | Giả thuyết | Kết luận | Bằng chứng |
|---|---|---|---|
| H1 | Watchdog false positive | **CONFIRMED** | §3; `elapsed=1801.844s` ≈ `CHO_WORKER_S` |
| H2 | Một clip cực dài (> 30 phút) | **REFUTED** | clip lâu nhất **68,4 s**; p99 = 35,5 s; p50 = 11,5 s |
| H3 | Media hỏng làm FFmpeg treo | **REFUTED** | 1117/1117 clip thành công, **0 thất bại**; mọi ffmpeg con đều có `process_child_end` |
| H4 | Thuật toán fingerprint treo | **REFUTED** | clip vẫn hoàn tất ở giây 09:10:58, một giây trước khi chết |
| H5 | Deadlock multiprocessing queue | **REFUTED** | không dùng Queue cho kết quả; pipe một chiều, cha đã `ghi.close()` đúng cách |
| H6 | Backpressure pipe/event | **REFUTED** | pipe mang đúng 1 dict nhỏ; tiến độ đi qua stdout, không qua pipe |
| H7 | Worker exception bị mất | **REFUTED** | có nhánh `except BaseException` gửi lỗi về cha (dòng 154-161); không lỗi nào được gửi |
| H8 | Worker đã chết mà cha chưa biết | **REFUTED** | cả 8 worker còn sống, `process_child_end` chỉ xuất hiện lúc 09:10:59 khi bị terminate |
| H9 | OneDrive / AV giữ lock | **KHÔNG LIÊN QUAN** | mỗi worker bận 1780–1800 s trên 1802 s tường ⇒ ~99% thời gian là compute |
| H10 | Áp lực bộ nhớ | **KHÔNG LIÊN QUAN** | worker ghi gzip ra file tạm, không đẩy HashTable qua pipe (bản vá cũ đã xử lý) |
| — | Hết dung lượng đĩa | **REFUTED** | C: còn 109 GB, D: còn 1,7 TB |

---

## 6. Đánh giá khả năng phục hồi

**Không có gì phục hồi được. Không phải vì đã bị xoá nhầm — mà vì chưa từng tồn tại.**

Ba tầng đều trống, và có lý do cấu trúc:

1. **Không có DB đích.** `data/kho_khojoebartolozzi_69b7bc.pklz` (tên đăng ký trong
   `data/khos.json`) **không tồn tại**. `data/` chỉ có kho Jordan Matter và Duncanyounot.
2. **Không có staging.** `engine.py:1962` — `finally: shutil.rmtree(workspace, ignore_errors=True)`
   xoá `data/fingerprint_jobs/<job_id>/` trên **mọi** đường thoát, kể cả lỗi. Thư mục
   `data/fingerprint_jobs/` hiện rỗng, mtime 09:10.
3. **Không có hash table tạm của worker.** Đây là điểm quyết định: worker chỉ ghi file
   gzip **sau khi** xử lý xong TOÀN BỘ danh sách của mình
   (`audfprint_progress_runner.py:149-152`). **Không worker nào hoàn tất**, nên
   **không một file gzip nào từng được tạo ra**. Kể cả nếu `shutil.rmtree` không chạy thì
   thư mục tạm vẫn rỗng.

Đã tìm toàn bộ C: và D: (độ sâu 6): không có `timclip_ht_*`, không có file nào tên
`*joebart*` ngoài chính thư mục nguồn.

> **Đây mới là bài học kiến trúc thật.** Không phải "watchdog quá chặt", mà:
> **kiến trúc hiện tại không có bất kỳ điểm lưu trung gian nào.** Một job 1178 clip là
> một giao dịch tất-cả-hoặc-không-gì kéo dài 34 phút. Bất kỳ lỗi nào ở phút thứ 33 đều
> xoá sạch 33 phút. Nâng timeout lên 3600 **không sửa điều này** — nó chỉ dời vách đá
> tới kho ~2400 clip.

---

## 7. Khoảng trống instrumentation

| Thiếu gì | Hệ quả |
|---|---|
| Log không ghi `worker_id` | Phải suy ra bằng `index % ncores`; nếu cách chia file đổi thì mất luôn khả năng này |
| Log không ghi `ncores` | Phải đếm PID con riêng biệt để suy ra |
| Thông báo timeout không kèm ngữ cảnh | Không có `current_file`, `phase`, `last_progress_at`, `process_alive`, `child_pid` |
| Heartbeat không phân biệt cha/worker | `pid=43784` là cha; không có tín hiệu per-worker |
| Worker chết không được phát hiện sớm | Phải chờ hết `poll()` mới biết (một phần được `EOFError` cứu, xem §8) |

Sau khi sửa, một sự kiện dừng phải luôn ghi được:
`worker_id`, `worker_pid`, `current_file`, `phase`, `started_at`, `last_progress_at`,
`elapsed_on_current_file`, `process_alive`, `child_pid`.

---

## 8. Những thứ hiện đã ĐÚNG (không được phá khi sửa)

Ghi lại để lần sửa tới không vô tình làm hỏng:

1. **Cha đóng đầu ghi pipe** (`ghi.close()`, dòng 216) → worker chết thành `EOFError`
   thay vì treo vĩnh viễn. Đây là bản vá cho một bug treo có thật.
2. **Worker ghi HashTable ra file gzip**, pipe chỉ mang dict nhỏ. Bản vendored gốc đẩy
   ~419 MB/worker qua Pipe (≈3,3 GB với 8 core) và treo 3/6 lần. **Không được quay lại.**
3. **`_emit` dùng đúng một `os.write`** — `print()` bị xé thành nhiều lần ghi và mất
   event khi 8 worker cùng ghi vào một stdout (đã quan sát 7/8).
4. **Commit là `os.replace(db_tam, self.db_file)`** với fallback `PermissionError` →
   kho cũ hợp lệ không bao giờ bị hỏng bởi một lần dựng thất bại.
5. **Mode `add` đã có sẵn khả năng bỏ qua clip đã có** (`engine.py:1788-1799`): đọc
   `db_clips()` lọc `so_hash > 0`, so khớp bằng `os.path.normcase(os.path.abspath(...))`,
   chỉ fingerprint phần thiếu. Nếu không thiếu gì thì trả về sớm.
6. **Mode `add` sao chép kho hiện có sang staging trước khi thêm** (`engine.py:1826-1836`)
   → kho gốc không bị chạm cho tới lúc `os.replace`.
7. **`cai_dat_theo_doi_giai_ma()` được gọi lại trong worker** — trên Windows dùng `spawn`,
   bản vá của cha không tự đi theo sang con.

Điểm 5 và 6 rất quan trọng: **cơ chế resume về cơ bản ĐÃ TỒN TẠI.** Thứ còn thiếu là
điểm lưu trung gian để một lần chạy thất bại vẫn để lại thành quả.

---

## 9. Trạng thái hiện tại của hệ thống

| Hạng mục | Trạng thái |
|---|---|
| Streamlit | **ĐANG CHẠY** — PID 41936, khởi động 08:40:39, hiện rảnh (52 MB, đỉnh 145 MB) |
| Job vân tay | **KHÔNG có job nào đang chạy** |
| `data/tool.lock` | File còn nội dung cũ `PID: 41936 / dựng kho vân tay / 08:40:57` — **nội dung đã lỗi thời**, khoá OS đã được nhả khi `with` thoát. File tồn tại ≠ khoá đang giữ |
| `data/fingerprint_jobs/` | **rỗng** |
| Kho đang dùng | `KhoJoeBartolozzi` — **trỏ tới một file DB không tồn tại** |
| `D:\KhoJoeBartolozzi` | 1178 file `.opus`, 17 GB, + `downloaded.txt`, `clips_meta.json`, 1 `.bak` |
| Đĩa | C: còn 109 GB · D: còn 1,7 TB |
| Git | detached HEAD @ `v2.6` (`7f85c8d`), cây sạch trừ 6 file docs mới |

> ⚠️ Vì `khos.json` đặt `dang_dung: "KhoJoeBartolozzi"` mà file DB không tồn tại,
> **mọi thao tác quét lúc này đều sẽ lỗi**. Đây là trạng thái người dùng đang gặp.

---

## 10. Kết luận nguyên nhân gốc

**CONFIRMED — một nguyên nhân duy nhất, không phải tổ hợp:**

> `audfprint_progress_runner.py:224` dùng `rx[core].poll(CHO_WORKER_S)` như một watchdog
> liveness, nhưng kênh mà nó quan sát (pipe) chỉ mang **một** message duy nhất phát ra
> **sau khi worker đã làm xong toàn bộ phần việc**. Vì vậy nó thực sự là hạn chót cứng
> 1800 giây cho tổng thời gian làm việc của mỗi worker, tỷ lệ thuận với
> `số_clip / ncores`. Với 1178 clip trên 8 core, worker chậm nhất cần ~2017 giây.
> Job bị giết trong lúc cả 8 worker đều khoẻ, ở mức 94,8% hoàn thành.

Điều kiện kích hoạt: `(số_clip / ncores) × giây_mỗi_clip > 1800`.
Với nhịp đo được 12,8 s/clip và 8 core, ngưỡng vỡ là **khoảng 1125 clip**.
Kho 537 và 149 clip trước đây nằm dưới ngưỡng nên chưa bao giờ lộ.

---

*Forensic 2026-09-07. Không sửa mã nguồn, không ghi vào `data/`, không xoá gì.
Mọi số liệu đo từ `ketqua/fingerprint.log` và source tại `7f85c8d`.*
