# Điều tra lệch 1 giây ở thời lượng video

Ngày: 2026-08-07. Mọi số liệu đo trực tiếp trên máy và trên chính trang YouTube.

---

## 1. Triệu chứng

```
https://www.youtube.com/watch?v=D-sVTRR5jm0
TimClipPro báo : 5:53:40
YouTube hiển thị: 5:53:39
```

Người dùng cho biết một số video khác lại đúng, và một số clip gốc trong kho cũng
lệch tương tự — nên không phải lỗi cố định chữa được bằng `-1 giây`.

---

## 2. Kết luận ngắn gọn

**Dữ liệu tool lưu đã đúng; sai ở khâu định dạng.** `hhmmss()` dùng `round()`, trong
khi trình phát — kể cả YouTube — hiển thị thời gian media bằng cách **cắt** phần lẻ.

Giả thuyết được nêu khi giao việc (báo cáo đang hiển thị nhầm thời lượng file audio
trung gian thay vì thời lượng chính tắc của YouTube) **bị bác bỏ bằng số đo**: giá
trị FFprobe mà tool đang lưu chính xác hơn metadata của YouTube, và khớp với đồng hồ
của chính trình phát YouTube tới **3 mili giây**. Đổi sang lấy metadata yt-dlp làm
nguồn hiển thị sẽ khiến kết quả **tệ đi**, không phải tốt lên.

---

## 3. Bảng pháp y — D-sVTRR5jm0

| Nguồn | Giá trị thô | `round()` | **cắt** |
|---|---:|---|---|
| yt-dlp `duration` | `21220` (int) | 05:53:40 | 05:53:40 |
| yt-dlp `duration_string` | `'5:53:40'` | — | — |
| FFprobe `format.duration` (file đã tải) | `21219.981` | 05:53:40 ✗ | **05:53:39** ✓ |
| `ScanResult.duration_s` đã lưu (job 412) | `21219.981` | 05:53:40 ✗ | **05:53:39** ✓ |
| `video.duration` đọc trên trang YouTube | `21219.981` | — | — |
| **`.ytp-time-duration` — UI YouTube** | — | — | **5:53:39** |

FFprobe của ta và `video.duration` của YouTube **trùng khít**: 21219.981.

### Đối chứng thứ hai — 3ixKzIN0et0 (clip gốc trong kho)

| Nguồn | Giá trị thô | `round()` | **cắt** |
|---|---:|---|---|
| `clips_meta.json` `duration` (từ yt-dlp) | `676` | 00:11:16 ✗ | 00:11:16 ✗ |
| FFprobe file `.opus` trong kho | `675.858` | 00:11:16 ✗ | **00:11:15** ✓ |
| `video.duration` trên trang YouTube | `675.861` | — | — |
| **UI YouTube** | — | — | **11:15** |

File `.opus` đã nén lệch bản gốc **3 mili giây** — đủ chính xác để hiển thị.

---

## 4. Mô hình đã được chứng minh

```
UI YouTube            = cắt(độ dài media thật)
lengthSeconds         = round(độ dài media thật)      ← nguồn của yt-dlp
FFprobe / .opus của ta = độ dài media thật             ← chính xác nhất
```

Chứng minh `lengthSeconds = round(media)`: đo 60 clip kho SML.

| Quan hệ | Số khớp |
|---|---|
| `duration` == `round(media)` | **58/60 (97%)** |
| `duration` == `ceil(media)` | 33/60 (55%) |
| `duration` == `floor(media)` | 27/60 (45%) |

Vì `round` lớn hơn `floor` bất cứ khi nào phần lẻ ≥ 0,5, metadata dư đúng một giây ở
khoảng nửa số clip.

---

## 5. Giá trị SAI ĐẦU TIÊN

```
File     : engine.py
Hàm      : hhmmss()
Trước    : giay = max(0, int(round(giay)))
Sau      : giay = max(0, int(giay))
```

Không có giá trị nào sai trước đó. yt-dlp đúng với ngữ nghĩa của nó (`lengthSeconds`),
FFprobe đúng, `ScanResult.duration_s` đúng. Chỉ khâu cuối — biến số thành chuỗi — dùng
sai quy tắc.

Với clip gốc thì nguyên nhân **khác**: thông tin đã mất từ khâu nạp metadata, vì
`clips_meta.json` chỉ lưu số nguyên đã làm tròn của YouTube (100% mục là số nguyên,
đo trên 744 clip kho SML). Cắt một số nguyên vẫn ra chính nó, nên sửa formatter không
đủ — cần độ dài media thật, xem `duration_media` trong
[DURATION_ARCHITECTURE.md](DURATION_ARCHITECTURE.md).

---

## 6. Quy mô ảnh hưởng

### Video vi phạm

Đo phần lẻ của 60 file đã tải trong `data/downloads`:

```
phần lẻ >= 0,5 (round dư 1 giây): 26/60 = 43,3%
phân bố phần lẻ                 : đều trên [0, 1), đúng như media thật
```

Mô phỏng luật cũ/mới trên **toàn bộ 387 job** trong `lichsu.db`:

| | Số job | Tỉ lệ |
|---|---:|---:|
| Giảm 1 giây (trước đây sai) | **182** | 47,0% |
| Giữ nguyên (trước đây đã đúng) | 205 | 53,0% |
| **Tăng lên** | **0** | 0,0% |

Không job nào tăng — đúng như mô hình dự đoán, vì cắt không bao giờ lớn hơn làm tròn.
Nhóm giữ nguyên chính là các video có phần lẻ < 0,5, tức những video người dùng đã
thấy đúng từ trước.

### Clip gốc

Đo mẫu 120 clip trên cả ba kho (`kiem_thoi_luong.py`):

| Kho | Mẫu | Sẽ đổi hiển thị |
|---|---:|---:|
| Cory | 40 | 18 (45,0%) |
| duncanyounot | 40 | 22 (55,0%) |
| SML | 40 | 18 (45,0%) |
| **Tổng** | **120** | **58 (48,3%)** |

Toàn bộ 2.600 mục của ba kho hiện **chưa** có `duration_media`.

### Mốc thời gian của đoạn khớp

500/1.199 mốc (41,7%) đổi. Đây là **sửa một mâu thuẫn có sẵn**, không phải tác dụng
phụ: link nhảy mốc `?t=` vốn đã luôn dùng `int()`, nên trước đây báo cáo ghi
`00:24:02` mà bấm link lại nhảy tới `00:24:01`. Nay cả hai đều là `00:24:01`.

---

## 7. Điều KHÔNG phải nguyên nhân

| Giả thuyết | Bằng chứng bác bỏ |
|---|---|
| FFprobe ghi đè nhầm lên thời lượng YouTube | FFprobe khớp `video.duration` của YouTube tới 3 ms; nó là nguồn **chính xác nhất** |
| Nên lấy yt-dlp làm nguồn chính tắc để hiển thị | yt-dlp = `round(media)`, hiển thị ra **5:53:40** — đúng cái đang sai |
| Encoder delay / Opus pre-skip / padding container | `format.start_time` = 0,000000; lệch FFprobe↔YouTube là 0,000 s |
| Lỗi cố định +1 giây | 53% video vốn đã đúng; mô phỏng cho 0 job tăng lên |
| Metadata cũ lấy từ nguồn khác | 744/744 mục kho SML là số nguyên, khớp `round(media)` ở 97% |

---

## 8. Kiểm chứng ca thật sau khi sửa

Dựng lại báo cáo từ job 412 đã lưu, bằng code mới:

```
duration_s đã lưu : 21219.981   (không đổi — dữ liệu vốn đã đúng)
Thời lượng báo cáo: 05:53:39    ← khớp UI YouTube
Đoạn khớp         : 00:24:01 – 00:34:38
Link nhảy mốc     : https://youtu.be/D-sVTRR5jm0?t=1441   ← 00:24:01, khớp hiển thị
```

---

## 9. Việc còn lại

Kho hiện có **2.600 clip chưa có `duration_media`**, nên clip gốc vẫn hiển thị theo
số nguyên đã làm tròn của YouTube (khoảng 48% dư một giây). Sửa được bằng:

```powershell
& ".\.venv\Scripts\python.exe" kiem_thoi_luong.py                 # xem trước
& ".\.venv\Scripts\python.exe" kiem_thoi_luong.py --sua --that-su # ghi thật
```

Chưa chạy vì đây là ghi vào metadata production; cần người dùng duyệt. Clip đồng bộ
mới đã tự có trường này.
