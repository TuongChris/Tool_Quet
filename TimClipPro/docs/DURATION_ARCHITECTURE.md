# Kiến trúc thời gian trong TimClipPro

File liên quan: `engine.py::hhmmss`, `clip_metadata.py`, `channel.py::do_dai_media`,
`app.py::_thoi_luong`, `kiem_thoi_luong.py`.

---

## 1. Bốn loại thời gian, không được trộn

| Loại | Ví dụ | Nguồn | Định dạng bằng | Quy tắc |
|---|---|---|---|---|
| **A. Thời lượng media** | "Thời lượng video vi phạm 05:53:39" | FFprobe file đang quét / `duration_media` của clip gốc | `engine.hhmmss()` | **cắt** phần lẻ |
| **B. Mốc trong media** | "Đoạn khớp 00:24:01 – 00:34:38" | `Match.start_s` / `end_s` | `engine.hhmmss()` | **cắt** phần lẻ |
| **C. Hình học xử lý** | ranh giới khúc, số khúc | FFprobe (`Engine.duration_of`) | không hiển thị | **giữ float** |
| **D. Thời gian vận hành** | "Đã chạy 01:24", "ETA 03:10" | đồng hồ hệ thống | `app._thoi_luong()` | cắt (đã đúng từ trước) |

A và B dùng chung `hhmmss()` vì cùng là thời gian media và cùng quy tắc. D có
formatter riêng vì là khái niệm khác — sửa thời lượng video không được đụng vào nó.

---

## 2. Vì sao cắt chứ không làm tròn

Trình phát hiển thị giây theo kiểu cắt: playhead ở giây 1441,8 thì đồng hồ ghi 24:01.
Thời lượng cũng vậy — video còn 0,019 giây cuối vẫn hiển thị mốc giây trước.

Đo trực tiếp trên trang YouTube (đọc `.ytp-time-duration` và `video.duration`):

| Video | media thật | UI YouTube | `round()` | cắt |
|---|---:|---|---|---|
| D-sVTRR5jm0 | 21219,981 | 5:53:39 | 05:53:40 ✗ | **05:53:39** ✓ |
| 3ixKzIN0et0 | 675,861 | 11:15 | 00:11:16 ✗ | **00:11:15** ✓ |

Cắt còn khớp với link nhảy mốc `?t=`, vốn đã luôn dùng `int()`.

Thêm một lý do: `round()` của Python làm tròn về số chẵn, nên `4108,5 → 4108` nhưng
`4109,5 → 4110`. Hành vi khó đoán đó không phù hợp cho một trường báo cáo.

---

## 3. Nguồn thời lượng theo từng loại đối tượng

### Video vi phạm (quét từ YouTube)

```
yt-dlp `duration` ──► chỉ dùng cho thông báo tiến độ lúc đầu
                      (là lengthSeconds, ĐÃ LÀM TRÒN — không dùng để báo cáo)

audio tải về ──► FFprobe ──► ScanResult.duration_s ──┬──► báo cáo (cắt)
                                                      └──► cắt khúc / so khớp (float)
```

`ScanResult.duration_s` **giữ nguyên một ngữ nghĩa duy nhất**: độ dài thật của media
đang được quét. Nó vừa là con số chính xác nhất để hiển thị, vừa là hình học đúng để
cắt khúc — nên **không cần tách** thành `source_duration` và `processing_duration`.
Tách ra sẽ thêm trường, thêm migration, mà lại lấy nguồn kém chính xác hơn để hiển thị.

### Clip gốc trong kho

```
yt-dlp `duration`      ──► clips_meta.json "duration"        (lengthSeconds, làm tròn)
file .opus sau khi nén ──► clips_meta.json "duration_media"  (độ dài thật)  ◄── ưu tiên
```

`ClipMetadataResolver` dùng `duration_media` khi có, nếu không thì lùi về `duration`.
Kho cũ chưa có trường mới vẫn chạy bình thường.

Độ tin cậy của file đã nén: `.opus` của 3ixKzIN0et0 dài 675,858 s, `video.duration`
trên trang YouTube là 675,861 s — lệch 3 ms.

### File local

Không có metadata YouTube, `Engine.duration_of()` chính là nguồn duy nhất và cũng là
nguồn đúng. Không có chính sách riêng nào cần thêm.

---

## 4. Vì sao KHÔNG tách `source_duration` / `processing_duration`

Phương án tách được cân nhắc và **loại bỏ dựa trên số đo**:

| | Giá trị cho D-sVTRR5jm0 | Hiển thị ra |
|---|---:|---|
| "canonical" theo yt-dlp | 21220 | 05:53:40 ✗ |
| FFprobe (đang dùng) | 21219,981 | **05:53:39** ✓ |

Tách ra chỉ có nghĩa khi hai nguồn phục vụ hai mục đích khác nhau **và** nguồn
"canonical" chính xác hơn cho hiển thị. Ở đây điều ngược lại mới đúng: FFprobe vừa
chính xác hơn cho hiển thị, vừa là hình học đúng cho xử lý. Một trường là đủ.

Nguyên tắc chung vẫn giữ: **metadata báo cáo ≠ hình học xử lý.** Chỉ là trong trường
hợp này chúng tình cờ trùng nguồn, và nguồn đó là nguồn tốt nhất.

---

## 5. Provenance

Trường `duration_media` mang sẵn ý nghĩa "đo từ file", còn `duration` mang ý nghĩa
"lengthSeconds của YouTube". Hai tên khác nhau là đủ để biết giá trị đến từ đâu — không
cần thêm trường `duration_source` riêng.

Giá trị `duration_media` không hợp lệ (âm, 0, NaN, chuỗi) bị bỏ qua và ghi cảnh báo
`invalid_duration_media`; hệ thống lùi về `duration` chứ không bịa số.

---

## 6. Điều KHÔNG được làm

* **Không** `duration - 1` ở bất cứ đâu — 53% video vốn đã đúng.
* **Không** ép `processing duration == source duration` bằng cách cắt/đệm audio. Cắt
  khúc cần biết audio thật dài bao nhiêu.
* **Không** dùng `hhmmss()` cho thời gian vận hành (đã chạy / ETA) — đó là loại D.
* **Không** gọi mạng lúc xuất báo cáo. `duration_media` được chốt ở khâu đồng bộ,
  exporter chỉ định dạng.

---

## 7. Bổ sung `duration_media` cho kho cũ

```powershell
& ".\.venv\Scripts\python.exe" kiem_thoi_luong.py                  # chỉ kiểm tra
& ".\.venv\Scripts\python.exe" kiem_thoi_luong.py --kho SML        # một kho
& ".\.venv\Scripts\python.exe" kiem_thoi_luong.py --sua            # thử ghi
& ".\.venv\Scripts\python.exe" kiem_thoi_luong.py --sua --that-su  # ghi thật
```

Ghi qua `ghi_json_an_toan()` nên có bản sao `.bak` và ghi nguyên tử. Không đụng kho
vân tay, không tải lại gì, không gọi mạng.

### Khi kho được nạp lại hoặc đổi tham số nén

Mặc định công cụ **bỏ qua** mục đã có `duration_media`, nên nạp lại kho xong thì giá
trị cũ vẫn còn và có thể không khớp file mới. Dùng `--ghi-de` để đo lại:

```powershell
& ".\.venv\Scripts\python.exe" kiem_thoi_luong.py --ghi-de                 # xem trước
& ".\.venv\Scripts\python.exe" kiem_thoi_luong.py --ghi-de --sua --that-su # ghi đè
```

Ở chế độ này, cột "ĐỔI hiển thị" so với `duration_media` **cũ** (thứ đang thực sự điều
khiển hiển thị), không phải so với `duration` của yt-dlp. `--ghi-de` không kèm `--sua`
chỉ để xem trước, tuyệt đối không ghi. `duration` gốc không bao giờ bị đụng tới.
