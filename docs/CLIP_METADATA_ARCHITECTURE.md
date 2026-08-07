# Kiến trúc ánh xạ metadata clip gốc

## Phạm vi và nguyên tắc bất biến

Tài liệu này mô tả cách TimClip Pro nối một kết quả fingerprint (`Match.clip`) với metadata
video gốc dùng trong giao diện, CSV dọc, CSV/Google Sheets ngang và hồ sơ Markdown. Lớp
metadata chỉ làm việc với dữ liệu đã có trên máy; nó không tham gia tạo fingerprint, `_merge`,
threshold, shifts, top-N hay cách chọn đoạn.

Các bất biến cần giữ:

- Không dùng metadata của video đang bị quét làm metadata video gốc.
- Không sắp xếp hoặc khử trùng metadata độc lập với `ScanResult.matches`.
- Hai đoạn cùng thuộc một clip có thể lặp lại cùng metadata để giữ quan hệ đoạn ↔ nguồn.
- `ScanResult.so_dat_nguong` vẫn là số đoạn đạt ngưỡng trước top-N; số slot báo cáo ngang vẫn
  tối đa 5 và `HEADER_NGANG` vẫn có đúng 34 cột.
- Xuất báo cáo, audit và khôi phục offline không gọi yt-dlp, HTTP, YouTube hoặc Google API.
- Không đọc credential/cookie, không lưu fingerprint thô vào snapshot và không ghi lại
  `clips_meta.json` trong thao tác khôi phục offline.

## Trạng thái triển khai

| Thành phần | Trạng thái | Ghi chú |
|---|---|---|
| Model, validation, index và resolver thuần trong `clip_metadata.py` | Đã triển khai | Không phụ thuộc Streamlit, Engine hoặc mạng |
| Nạp nguồn theo kho, cache và snapshot trong `engine.py` | Đã triển khai | Có cache signature, invalidation, strict loader và guard chống ghi đè snapshot hỏng |
| Dùng resolver trong CSV dọc/ngang và Markdown | Đã triển khai | Giữ thứ tự match và contract ngang 34 cột |
| Coverage warning và audit/repair trong Streamlit | Đã triển khai | Audit theo nút bấm; cảnh báo coverage xuất hiện cùng kết quả |
| CLI chẩn đoán/khôi phục offline | Đã triển khai | `kiem_metadata_kho.py`, mặc định read-only/dry-run |
| Vá metadata qua YouTube | Đã triển khai, chỉ kích hoạt rõ ràng | `cli.py vametak` hoặc khu vực mạng có xác nhận trong UI; không thuộc resolver/exporter |

## Nguồn tạo metadata và quan hệ dữ liệu

`channel.ChannelSync` tạo tên file theo mẫu:

```text
YYYYMMDD - Tiêu đề [VIDEO_ID].opus
```

Sau khi tải và nén thành công, `ChannelSync.sync()` ghi atomically một entry vào
`<kho_thu_muc>\clips_meta.json`, dùng basename làm khóa:

```json
{
  "filename.opus": {
    "id": "abcdefghijk",
    "title": "Tiêu đề YouTube",
    "upload_date": "20250101",
    "duration": 600,
    "url": "https://youtu.be/abcdefghijk"
  }
}
```

audfprint lưu tên/đường dẫn clip trong database `.pklz`. `Engine.db_clips()` chuyển dữ liệu đó
thành `ten`, `duong_dan`, `so_hash`; `_merge()` giữ basename trong `Match.clip`. Vì vậy basename
là cầu nối lịch sử giữa fingerprint và `clips_meta.json`, nhưng không phải định danh bền vững:
file có thể được di chuyển/đổi tên, key metadata có thể là path cũ, tên Unicode có thể khác NFC/NFD,
hoặc metadata chỉ tồn tại cho một phần kho. YouTube ID 11 ký tự trong `[VIDEO_ID]` là định danh ổn
định hơn khi có đủ bằng chứng và không mơ hồ.

## Call flow trước và sau

### Trước

```text
ChannelSync -> clips_meta.json keyed by basename
audfprint   -> database path/name -> Match.clip basename

Match.clip
  +-> Engine.to_rows() ---------> meta.get(exact key) --------+
  +-> bang_ngang.dung_dong_ngang() -> dict.get(exact key) ----+-> chuỗi rỗng
  +-> dossier.dung_ho_so() ------> dict.get(exact key) --------+

Engine.clip_meta()
  -> suy thư mục từ db_clips() + data_dir
  -> duyệt set không có thứ tự
  -> meta.update(...)
  -> except Exception: pass
```

Một key vắng mặt hoặc file JSON lỗi đều có cùng biểu hiện: `{}` và báo cáo trống, không có bằng
chứng chẩn đoán. `kho_thu_muc` không được kiểm tra trực tiếp và metadata từ nhiều thư mục có thể
ghi đè nhau theo thứ tự không xác định.

### Sau — kiến trúc đã triển khai

```text
                         +-> snapshot đúng warehouse ---------+
Engine / kho đang dùng --+-> kho_thu_muc\clips_meta.json -----+-> validate nguồn
                         +-> thư mục clip thực tế trong DB ----+       |
                                                                  index một lần
Match.clip (+ path nếu có)                                            |
        -> ClipMetadataResolver --------------------------------------+
        -> exact / basename / canonical / unique video ID
        -> filename fallback hoặc basename fallback
        -> ResolvedClipMetadata + status + warnings
                  |
                  +-> CSV dọc / bảng Streamlit
                  +-> CSV ngang / Google Sheets
                  +-> dossier Markdown
                  +-> coverage warning / diagnostic
```

`watch.py` và `sheets.py` không tự resolve lần nữa. Chúng nhận các row đã được Engine dựng bằng
cùng resolver, nhờ đó mọi đầu ra dùng một contract và không phát sinh lookup khác nhau.

## Contract resolver

`ResolvedClipMetadata` chứa tối thiểu:

| Trường | Ý nghĩa |
|---|---|
| `clip_name` | Basename hiển thị của clip fingerprint |
| `video_id` | ID YouTube chỉ khi hợp lệ và xác định duy nhất |
| `title`, `url`, `upload_date`, `duration` | Giá trị đã validate; phần không có bằng chứng để rỗng/`None` |
| `resolution_method` | Cách ánh xạ thực tế |
| `status` | `complete`, `partial`, `unresolved` hoặc `ambiguous` |
| `metadata_key` | Key nguồn đã được chọn, rỗng khi chỉ fallback |
| `source_file`, `source_kind` | Nguồn phục vụ audit; không dùng làm nội dung báo cáo công khai |
| `complete`, `missing_fields`, `warnings` | Chất lượng và lý do thiếu dữ liệu |

`resolve_many()` giữ nguyên thứ tự và duplicate đầu vào. Đây là điều kiện để đoạn vi phạm thứ
`i` luôn đi cùng video gốc thứ `i`.

## Nguồn và thứ tự ưu tiên

Có hai trục độc lập: ưu tiên **nguồn** và thứ tự **khóa ánh xạ**.

### Ưu tiên nguồn theo kho

Engine chỉ dựng resolver cho `kho_dang_dung`:

1. Snapshot có schema hợp lệ và trường `warehouse` khớp chính xác kho đang dùng.
2. `clips_meta.json` trực tiếp trong `self.kho_thu_muc`.
3. `clips_meta.json` trong các thư mục clip thực tế lấy từ `db_clips()`, theo thứ tự đã sort và
   đã loại trùng.
4. Nguồn legacy chỉ được dùng khi chứng minh thuộc chính kho đó; không đọc mù
   `data_dir\clips_meta.json` của kho khác.

Việc hợp nhất xét **chất lượng trước priority nguồn**: entry metadata chính thức có chất lượng cao
hơn entry snapshot từng được tạo bằng `filename_fallback`. Vì vậy snapshot fallback không thể che
một entry chính thức mới xuất hiện trong `clips_meta.json`. Với các entry cùng mức chất lượng,
snapshot đúng kho có priority cao hơn; nguồn sau chỉ bổ sung trường trống. Hai giá trị không rỗng
nhưng khác nhau tạo conflict/warning, không dùng “last write wins” theo thứ tự filesystem.

### Thứ tự resolve khóa

Resolver dựng sẵn index và thử tuần tự:

1. `exact`: key trùng nguyên văn `clip_name` hoặc path được cung cấp.
2. `exact_basename`: basename trùng nguyên văn, kể cả key metadata là path cũ.
3. `canonical_filename`: basename được trim biên, bỏ dấu chấm/khoảng trắng cuối theo Windows,
   chuẩn hóa Unicode NFC và `casefold` khi dùng Windows semantics. Không xóa ký tự ở giữa tên và
   không tự ý bỏ extension.
4. `video_id`: lấy đúng một ID 11 ký tự `[A-Za-z0-9_-]` từ filename/path và chọn đúng một entry
   tương ứng trong index ID.
5. `ambiguous`: nếu canonical/ID đưa tới nhiều entry có dữ liệu khác nhau, dừng; không chọn ngẫu
   nhiên và không lấy entry đầu tiên.
6. `filename_fallback`: chỉ khi tên khớp chặt mẫu `YYYYMMDD - Title [VIDEO_ID].ext`.
7. `basename_fallback`: nếu không có ID đáng tin cậy, chỉ hiển thị basename; không tạo URL giả.

Snapshot không phải phép so sánh chuỗi riêng sau video ID. Nó là nguồn metadata bền vững của đúng
kho và tham gia các index trên. Nhờ vậy exact/canonical/ID vẫn có cùng semantics dù thư mục clip
gốc đã di chuyển.

## Validation, fallback và conflict

- ID chỉ hợp lệ khi có đúng 11 ký tự chữ, số, `_` hoặc `-`; helper hỗ trợ `[ID]`, `youtu.be/ID`
  và query `youtube.com/watch?v=ID`.
- `upload_date` chỉ hợp lệ khi là ngày lịch `YYYYMMDD`; `00000000` được coi là thiếu.
- `duration` phải là số dương và `bool` không được chấp nhận như số.
- Root JSON không phải object, entry không phải object hoặc trường sai kiểu bị cô lập và ghi warning;
  trường hợp lệ khác của entry vẫn được giữ khi có thể.
- Filename fallback phục hồi ID, URL, title đã được lưu trong tên và ngày hợp lệ. Duration không
  được suy đoán. Warning phải nêu title có thể đã sanitize/cắt ngắn.
- Ambiguous không rơi tiếp xuống một candidate hoặc filename fallback có vẻ hợp lý. Kết quả giữ
  basename để người dùng còn biết clip nào liên quan, còn ID/URL/date/duration để trống nếu không
  thể khẳng định.
- “Complete” nghĩa là đủ ID, title, URL, upload date và duration. Một URL/title phục hồi được nhưng
  thiếu ngày hoặc duration vẫn là `partial`, không được báo là metadata chính thức đầy đủ.

## Snapshot metadata riêng từng kho

Snapshot đã triển khai nằm dưới:

```text
data\metadata\kho_<warehouse-slug>.json
```

Tên file được sinh từ tên kho bằng helper `_slug()` và được kiểm tra `commonpath`, không lấy path
tùy ý từ input. Snapshot production hiện tại của kho `Cory` là:

```text
data\metadata\kho_cory_72c177.json
```

Schema phiên bản 1:

```json
{
  "schema_version": 1,
  "warehouse": "Tên kho chính xác trong khos.json",
  "warehouse_id": "warehouse-slug",
  "database": "kho_<warehouse-slug>.pklz",
  "updated_at": "2026-08-06T21:05:37+07:00",
  "sources": [{"kind": "live", "file": "clips_meta.json"}],
  "stats": {
    "database_clips": 1,
    "complete": 1,
    "partial": 0,
    "filename_fallbacks": 0,
    "unresolved": 0,
    "ambiguous": 0
  },
  "clips": {
    "filename.opus": {
      "id": "abcdefghijk",
      "title": "Tiêu đề đã có bằng chứng",
      "url": "https://youtu.be/abcdefghijk",
      "upload_date": "20250101",
      "duration": 600,
      "resolution_method": "exact"
    }
  }
}
```

Snapshot chỉ được ghi bằng cơ chế file tạm + flush/fsync + atomic replace của `luu_tru.py`. Khi
tạo kho mới, snapshot chỉ được cập nhật sau khi database fingerprint đã commit thành công. Khi bổ
sung clip, merge giữ entry cũ đầy đủ và không thay bằng entry mới rỗng. Lỗi ghi snapshot phải được
báo rõ nhưng không được làm hỏng database fingerprint đã commit.

Khôi phục offline ghi snapshot mới/cập nhật, không sửa nguồn production `clips_meta.json`. Chạy
lặp lại trên cùng dữ liệu là idempotent. Strict loader từ chối JSON duplicate key, constant không
hữu hạn, schema snapshot không hỗ trợ và warehouse không khớp. Backup chỉ được đọc như fallback,
không tự động rename/phục hồi file chính. Nếu snapshot chính tồn tại nhưng malformed, apply từ chối
ghi — kể cả khi `.bak` hợp lệ — để không biến file hỏng thành backup mới và ghi đè bản backup tốt.
Chẩn đoán/dry-run không làm thay đổi timestamp, tạo `.tmp` hay tạo `.bak`.

## Cache và invalidation

Dựng ba index (`exact`, `canonical filename`, `video ID`) một lần cho mỗi bộ nguồn; resolve sau đó
gần O(1), không quét 1717 entry cho mỗi match.

Cache Engine đang dùng signature:

```text
(warehouse, kho_thu_muc, db path/existence/mtime_ns/size,
 từng source kind/priority/path/existence/mtime_ns/size,
 từng source .bak path/existence/mtime_ns/size)
```

Cache được invalidate khi:

- đổi hoặc sửa cấu hình kho;
- tạo lại/bổ sung database thành công;
- khôi phục metadata offline hoặc vá metadata mạng;
- snapshot/source/backup đổi existence, mtime hoặc size;
- caller yêu cầu `bo_cache=True` để chẩn đoán.

Một lần export batch dùng lại một resolver; không đọc JSON hoặc database cho từng row/match.

## Tích hợp exporter và coverage

- `Engine.to_rows()`: resolve từng `Match` và điền “Clip gốc tìm thấy”, title, URL bằng cùng object.
- `Engine.to_rows_ngang()` → `bang_ngang.dung_dong_ngang()`: truyền resolver; năm segment slot và
  năm nhóm metadata đều duyệt cùng `matches[:5]` theo index. Cột cuối vẫn dùng `so_dat_nguong`.
- `Engine.export_ho_so()` → `dossier.dung_ho_so()`: cùng resolver; basename luôn xuất hiện ngay cả
  khi metadata chưa đầy đủ.
- `export_csv*`, Streamlit, watch và Sheets chỉ tiêu thụ các row trên. Không exporter nào gọi mạng.

`bang_ngang.dung_dong_ngang()` và `dossier.dung_ho_so()` vẫn nhận mapping cũ để tương thích, nhưng
Engine truyền một `ClipMetadataResolver` dùng chung. UI gọi `Engine.metadata_coverage()` trước khi
vẽ kết quả và giải thích riêng số đoạn đạt ngưỡng với số match được chọn.

Trước khi hiển thị/xuất, coverage cho các match được chọn gồm:

```text
selected_matches
resolved_complete
resolved_partial
filename_fallbacks
unresolved
ambiguous
```

Nếu có match nhưng không có metadata complete, UI/logger phải cảnh báo báo cáo đang dùng metadata
một phần. Nếu có filename fallback, cảnh báo title có thể đã rút gọn. Unresolved/ambiguous phải nêu
clip đã làm sạch và cách chẩn đoán; báo cáo vẫn hiển thị basename thay vì làm biến mất danh sách
video gốc.

## Audit và khôi phục

### Audit chỉ đọc

`Engine.kiem_tra_metadata_kho()` và công cụ `kiem_metadata_kho.py` đã triển khai các bước:

1. Chọn kho từ `data/khos.json`, xác nhận DB/folder tồn tại.
2. Đọc clip bằng `Engine.db_clips()` thay vì mở pickle từ path chưa xác minh.
3. Nạp JSON bằng strict loader không ghi/rename/auto-restore.
4. Báo số clip, entry, exact, basename, normalized, ID, fallback, unresolved, ambiguous, invalid,
   conflict và orphan.
5. Giới hạn mẫu khoảng 10–20; chỉ in basename/thư mục rút gọn, không in credential hoặc toàn bộ kho.
6. Với `--video-id`, đối chiếu các match đã lưu và in method/status/missing fields.

Mặc định lệnh là read-only. `--repair-offline` vẫn chỉ dry-run; chỉ tổ hợp rõ ràng
`--repair-offline --apply` mới ghi snapshot. `--json` phục vụ automation, giới hạn mẫu và không in
credential/nội dung fingerprint.

### Khôi phục offline

`Engine.khoi_phuc_metadata_offline(dry_run=True)` dùng nguồn hợp lệ, snapshot hiện có và pattern
filename. Dry-run chỉ trả audit/diff. Apply lấy `data/tool.lock`, kiểm tra DB tồn tại và đọc được clip,
validate payload, áp dụng guard snapshot/backup, ghi atomically, invalidate cache và trả `updated`,
`unchanged`, `skipped_ambiguous`, `unresolved`, `errors`. Nó không gọi mạng, không sửa fingerprint,
không sửa `clips_meta.json` và không bịa duration/ngày.

### Vá từ YouTube

Có hai tác vụ mạng, đều chỉ chạy sau hành động rõ ràng của người dùng:

- `python cli.py vametak`: gọi `Engine.va_metadata_thieu()` cho snapshot của kho active. Luồng này
  chuẩn bị snapshot offline, chỉ chọn entry thiếu có ID không mơ hồ, dùng timeout và retry/backoff
  hữu hạn, kiểm tra identity/schema trả về, ghi snapshot atomically sau từng entry thành công và
  invalidate cache.
- `python cli.py vameta --kho "<thư mục kho>"`: luồng legacy
  `ChannelSync.va_metadata()` vá trực tiếp `clips_meta.json` của thư mục được chỉ định.

Streamlit đặt tác vụ `va_metadata_thieu()` trong expander riêng, yêu cầu checkbox xác nhận mạng và
chạy nền có progress. Không tác vụ mạng nào được gọi tự động từ resolver, audit, UI render hoặc
export.

## Chẩn đoán khi báo cáo thiếu video gốc

1. Xác nhận tên kho chính xác trong `data\khos.json`; tên hiển thị người dùng nói có thể khác tên
   registry thực tế.
2. Chạy audit read-only, kiểm tra `database_exists`, `warehouse_folder_exists`, nguồn metadata và
   warning parse/schema.
3. Kiểm tra coverage của đúng `Match.clip`: exact key, canonical key, ID trích được, method, status,
   missing fields.
4. Nếu chỉ thiếu snapshot/coverage nhưng filename có ID hợp lệ, chạy dry-run khôi phục offline;
   xem mẫu/conflict rồi mới apply.
5. Chỉ chạy `vametak` (snapshot kho active) hoặc `vameta --kho ...` (nguồn legacy) khi cần dữ liệu
   chính thức và đã chấp nhận truy cập YouTube.
6. Tạo lại fingerprint chỉ khi DB không còn tên/path liên hệ với file, file vật lý sai nội dung hoặc
   DB thực sự hỏng. Thiếu `clips_meta.json` đơn thuần không phải lý do tạo lại 1717 fingerprint.

Các failure mode chính:

| Hiện tượng | Hành vi an toàn |
|---|---|
| JSON chính malformed | Warning rõ, thử nguồn/backup đã validate để đọc; apply từ chối ghi đè file chính hỏng |
| Snapshot thuộc kho khác | Bỏ qua với `snapshot_warehouse_mismatch` |
| Nhiều candidate cùng canonical/ID nhưng khác dữ liệu | `ambiguous`, không chọn tùy ý |
| Kho clip đã di chuyển | Dùng snapshot đúng kho hoặc ID/path legacy đã xác minh |
| Filename không có ID | Hiển thị basename, không tạo link giả |
| Nguồn thiếu ngày/duration | `partial`, không quảng cáo là complete |
| Cache cũ | Stat-key thay đổi hoặc explicit invalidation dựng resolver mới |
| Snapshot write lỗi | Giữ DB/source cũ, log lỗi; không rollback fingerprint đã commit |
| Coverage complete bằng 0 | Warning UI/terminal; vẫn cho export fallback có nhãn cảnh báo |

## Bằng chứng thực tế: kho Cory và video `Zlfty7Enrkg`

Audit read-only ngày 2026-08-06 cho thấy tên kho active chính xác trong registry là `Cory` (không
phải chuỗi `Cory toàn bộ` trong mô tả người dùng). Database `kho_cory_72c177.pklz` có 1717 clip;
1717 đường dẫn tuyệt đối đều tồn tại, không có duplicate basename/canonical và khớp 1:1 với 1717
file media trong thư mục kho. Vì vậy fingerprint/path không hỏng và không cần dựng lại kho.

Nguồn chính `clips_meta.json` đọc được nhưng chỉ có 86 entry; backup có 85. Cả 86 entry chính đều
thiếu `upload_date`. Đối chiếu 1717 clip cho kết quả:

| Chỉ số | Số lượng |
|---|---:|
| Clip trong fingerprint DB | 1717 |
| Metadata entry nguồn chính | 86 |
| Exact basename | 86 |
| Canonical bổ sung | 0 |
| ID-resolved từ metadata cũ | 0 |
| Filename fallback khả dụng | 1631 |
| Unresolved | 0 |
| Ambiguous | 0 |
| Complete | 0 |
| Partial | 1717 |

Job lịch sử 307 cho nguồn `Zlfty7Enrkg` lưu ba match được chọn. Cả ba exact key đều vắng trong
metadata chính, backup và archive metadata; lookup `.get()` cũ vì thế trả `{}`:

| Đoạn | Match clip | Resolution an toàn | Trường còn thiếu |
|---:|---|---|---|
| 1 | `00000000 - Pedro Pascal Wants You. [SSS #070] [iiPCTnSoj9w].opus` | `filename_fallback` | upload date, duration |
| 2 | `00000000 - DO NOT CLICK THIS VIDEO. [SSS #003] [Nkr7YLIlAdU].opus` | `filename_fallback` | upload date, duration |
| 3 | `00000000 - what would you do if she asked for a ride home_ [SSS #031] [pqzrFR3anuo].opus` | `filename_fallback` | upload date, duration |

Fallback phục hồi riêng ID/title/URL từ từng filename; tiền tố `00000000` không được coi là ngày
hợp lệ và duration không được suy đoán. Không trường nào lấy từ video vi phạm. SQLite xác nhận ba
match được chọn nhưng không lưu `so_dat_nguong`; con số 12 đến từ artifact báo cáo và đúng với
contract “đạt ngưỡng trước top-N”, không nên bị đổi thành 3.

## Riêng tư, mạng và dữ liệu production

- Resolver, strict loader, coverage, audit và offline repair không import/gọi yt-dlp hay HTTP.
- Log chỉ dùng warehouse/job ID, basename đã làm sạch, method, count và error category; không log
  cookie, Authorization header, URL có token, credential hoặc fingerprint thô.
- Audit trên Cory là read-only. Không sửa `clips_meta.json`, `.bak`, fingerprint DB hoặc clip gốc.
- Snapshot là artifact báo cáo theo kho, không phải bản sao credential và không chứa nội dung âm
  thanh/hash.
- Mạng chỉ xuất hiện trong `ChannelSync.va_metadata()` sau hành động rõ ràng của người dùng.

## Hạn chế còn lại

- 1631 filename fallback có ID/title/URL dùng được nhưng title có thể đã sanitize/cắt ngắn.
- Với Cory, tiền tố ngày của toàn bộ 1717 filename là `00000000`; ngày đăng không thể phục hồi chắc
  chắn offline. Duration của 1631 entry thiếu cũng không thể suy ra từ fingerprint metadata.
- 86 entry nguồn hiện có vẫn thiếu ngày đăng; chúng chỉ trở thành complete sau khi có dữ liệu chính
  thức hợp lệ.
- SQLite lịch sử không lưu `so_dat_nguong`, nên không thể độc lập tái chứng minh số 12 chỉ từ job 307.
- Snapshot giải quyết độ bền metadata nhưng không chứng minh nội dung file đã bị thay thế dưới cùng
  tên; trường hợp nghi ngờ integrity nội dung cần quy trình kiểm tra riêng.
- Chỉ nên tạo lại fingerprint khi chẩn đoán chứng minh DB/file thực sự sai hoặc hỏng; thiếu metadata,
  đổi thư mục hay key lệch tên đều xử lý ở resolver/snapshot trước.
