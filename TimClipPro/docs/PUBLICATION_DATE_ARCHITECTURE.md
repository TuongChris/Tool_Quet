# Kiến trúc “Ngày đăng video”

Ngày: 2026-08-07 · Module: [`publication_date.py`](../publication_date.py)

---

## 1. Vấn đề

Người dùng báo ngày đăng sai với *một số* video, không phải tất cả. Đo trên hai
video thật bằng yt-dlp 2026.07.04:

| Video | `upload_date` | `timestamp` | UTC | Giờ VN | Tool cũ | Đúng |
| --- | --- | ---: | --- | --- | --- | --- |
| `Asv1kjFuX-4` | `20260731` | 1785528034 | 2026-07-31 **20:00:34** | 2026-08-01 03:00 | 31/07/2026 | **01/08/2026** |
| `T_mKh8IUpWw` | `20250620` | 1750445139 | 2025-06-20 **18:45:39** | 2025-06-21 01:45 | 20/06/2025 | **21/06/2025** |

Cả hai `release_timestamp` và `release_date` đều **không tồn tại** trên hai video này.

---

## 2. Root cause

`upload_date` của yt-dlp là **ngày theo lịch UTC** của thời điểm phát hành.
YouTube hiển thị cho người xem theo **múi giờ của họ**. Người dùng ở
`Asia/Ho_Chi_Minh` là **UTC+7**, nên:

```
17:00 UTC  ==  00:00 giờ Việt Nam hôm sau
```

- Video phát hành **00:00–16:59:59 UTC** → ngày UTC = ngày VN → **đúng sẵn**.
- Video phát hành **17:00–23:59:59 UTC** → ngày VN là hôm sau → **lệch đúng 1 ngày**.

Đó là lý do chỉ *một số* video sai. Kênh CoryxKenshin đăng vào buổi tối giờ Mỹ,
tức đêm giờ UTC, nên đa số clip rơi vào khoảng lệch (đo trên mẫu 25 clip: **22 lệch**).

**Offset +7 giờ không bao giờ tạo sai lệch 2 ngày.** Con số `30/07/2026` nêu trong
báo cáo ban đầu không tái hiện được: tool trước khi sửa cho `31/07/2026`. Nếu sau
này gặp lệch 2 ngày thật, đó là lỗi khác và phải điều tra riêng — tuyệt đối không
cộng trừ bù.

### Vị trí chính xác trong code (trước khi sửa)

| Luồng | File | Hàm | Trường dùng |
| --- | --- | --- | --- |
| Video vi phạm | `engine.py` | `youtube_info()` | `info.get("upload_date")` |
| Video gốc (nạp) | `channel.py` | `ngay_dang_tu_info()` | `upload_date` **trước** `timestamp` |
| Video gốc (đọc) | `clip_metadata.py` | `source_from_mapping()` | `upload_date` |
| Định dạng | `bang_ngang.py` | `dinh_dang_ngay()` | `strptime("%Y%m%d")` |

`ngay_dang_tu_info()` đã có sẵn nhánh đọc `timestamp`, nhưng đặt **sau**
`upload_date`, nên nhánh đó thực tế không bao giờ chạy khi `upload_date` tồn tại.

---

## 3. Ngữ nghĩa chính tắc

> **Ngày đăng** = ngày theo lịch của thời điểm video được công khai trên YouTube,
> tính theo múi giờ hiển thị của người dùng (mặc định `Asia/Ho_Chi_Minh`).

Không trộn với: ngày tải file, ngày xử lý, mtime của filesystem, ngày đồng bộ kênh,
ngày lấy metadata.

---

## 4. Thứ tự ưu tiên (đã kiểm chứng, không phải giả định)

| # | Trường | Vì sao | Độ tin cậy |
| --- | --- | --- | --- |
| 1 | `release_timestamp` | Thời điểm **phát hành công khai** (premiere/scheduled). Có giờ ⇒ quy đổi được múi giờ. | high |
| 2 | `timestamp` | Thời điểm đăng. Có giờ ⇒ quy đổi được múi giờ. Đây là trường cho ra ngày đúng ở cả hai video mẫu. | high |
| 3 | `release_date` | Chuỗi `YYYYMMDD` theo UTC. **Không có giờ** ⇒ không quy đổi được. | medium |
| 4 | `upload_date` | Như trên. Chính là trường gây lệch. | medium |
| 5 | `filename_date` | Suy từ tên file `YYYYMMDD - Title [ID].ext`. | low |

Nguyên tắc nền: **trường có thời điểm chính xác luôn thắng trường chỉ có ngày**,
vì chỉ nó mới quy đổi được múi giờ. Có metadata chính thức thì tuyệt đối không
lấy ngày từ tên file.

---

## 5. Timezone policy

```python
datetime.fromtimestamp(epoch, timezone.utc).astimezone(ZoneInfo(tz)).date()
```

- Epoch của yt-dlp là **POSIX UTC**. Luôn gắn `timezone.utc` khi dựng datetime.
- **Cấm** `datetime.fromtimestamp(ts)` không kèm tzinfo — kết quả sẽ phụ thuộc múi
  giờ của máy đang chạy (Windows, Docker, Streamlit process đều có thể khác nhau).
- **Cấm** `.replace(tzinfo=...)` để “quy đổi” — nó đổi nhãn chứ không đổi thời điểm.
- Chuỗi `YYYYMMDD` **không** được quy đổi múi giờ (không có giờ để quy đổi); lấy
  nguyên và hạ độ tin cậy.
- Múi giờ đổi được qua biến môi trường `TIMCLIP_MUI_GIO`. Múi giờ không tồn tại →
  lùi về UTC kèm cảnh báo, không crash.

Test `test_case12_ket_qua_khong_phu_thuoc_mui_gio_cua_may` chạy lại trong tiến trình
con với `TZ` = UTC / America/Los_Angeles / Asia/Tokyo / Pacific/Kiritimati và khẳng
định kết quả canonical y hệt.

---

## 6. Provenance

```python
PublicationDateResult(
    date=date(2025, 6, 21),
    source_field="timestamp",
    raw_value=1750445139,
    confidence="high",
    warnings=("khac_upload_date",),
)
```

Luôn trả lời được: *ngày này lấy từ đâu?* Cảnh báo bắt đầu bằng `khac_` nghĩa là các
trường ngày mâu thuẫn nhau — dấu hiệu cần xem lại, **không** mặc nhiên là lỗi.

---

## 7. Schema metadata

```jsonc
{
  "id": "T_mKh8IUpWw",
  "title": "...",
  "url": "https://youtu.be/T_mKh8IUpWw",
  "publication_date": "20250621",            // chính tắc, giờ VN
  "publication_date_source": "timestamp",    // nguồn gốc
  "upload_date": "20250621",                 // giữ tên cũ, bản đọc cũ vẫn chạy
  "timestamp": 1750445139,                   // lưu lại để audit offline về sau
  "duration": 955.0
}
```

`clip_metadata.source_from_mapping()` đọc `publication_date` trước, thiếu thì lùi về
`upload_date`. **Rơi về schema cũ là đường chạy bình thường, không phát cảnh báo.**

---

## 8. Luồng dữ liệu

```
Video vi phạm:
  yt-dlp extract_info
    -> engine.youtube_info()  [resolve NGAY TAI DAY]
    -> ScanResult.upload_date (đã chính tắc) + publication_date_source
    -> bang_ngang.dung_dong_ngang -> format_publication_date -> "DD/MM/YYYY"

Video gốc:
  yt-dlp (lúc tải hoặc lúc vameta)
    -> channel.ngay_dang_tu_info() / bo_sung_video_info()  [resolve]
    -> clips_meta.json {publication_date, publication_date_source, timestamp}
    -> ClipMetadataResolver -> Match -> bang_ngang -> format_publication_date
```

Hai luồng dùng **cùng một** resolver và **cùng một** hàm định dạng.

---

## 9. Exporter

Chỉ `publication_date.format_publication_date()` được phép sinh chuỗi `DD/MM/YYYY`.
Ba test cấu trúc canh giữ điều này:

- `test_khong_module_nao_tu_dinh_dang_ngay_rieng`
- `test_khong_module_nao_tu_doi_epoch_sang_ngay_dang`
- `test_khong_co_hotfix_cong_tru_ngay_dang`

Ngoại lệ được liệt kê tường minh: `app.py` (đồng hồ màn hình tiến độ) và
`nhat_ky.py` (cửa sổ giữ log) — cả hai không liên quan ngày đăng.

Exporter **không được** gọi mạng: `test_exporter_khong_goi_mang_khi_dinh_dang`.

> Ghi chú thực tế: trong các báo cáo hiện tại, ngày đăng chỉ xuất hiện ở **bảng
> ngang** (CSV ngang, Google Sheets, xem trước trên UI). CSV dọc và dossier Markdown
> hiện không có cột ngày.

---

## 10. Di trú metadata cũ

Xem [PUBLICATION_DATE_AUDIT.md](PUBLICATION_DATE_AUDIT.md) và
[`kiem_ngay_dang.py`](../kiem_ngay_dang.py).

Giới hạn quan trọng: entry cũ **chỉ lưu chuỗi `YYYYMMDD`**, không lưu epoch. Không có
giờ thì **không thể** biết ngày giờ VN có lệch hay không. `--repair-offline` chỉ sửa
được entry đã có epoch; phần còn lại bắt buộc `--repair-network`. Công cụ không đoán.
