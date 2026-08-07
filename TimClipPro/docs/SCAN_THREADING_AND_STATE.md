# Ranh giới thread và state trong Scan Pipeline

Ngày: 2026-08-07 · Base: `6cad9d9`

---

## 1. Triệu chứng

```
Thread 'scan-2924d458': missing ScriptRunContext!
KeyError: st.session_state has no key "sheet_link"
event=scan.on_video_callback_failed index=3 total=3
```

và, lặp mỗi lần UI vẽ lại (0,75 giây một lần):

```
pyarrow.lib.ArrowInvalid: ("Could not convert '—' with type str:
 tried to convert to int64", 'Conversion failed for column Đoạn with type object')
Serialization of dataframe to Arrow table was unsuccessful.
Applying automatic fixes for column types...
```

Cả hai đều do code viết ở vòng Scan Pipeline V2 ngay trước đó.

---

## 2. Root cause — `sheet_link`

### `sheet_link` có bị thiếu khởi tạo không? **KHÔNG.**

```python
# cau_hinh.py:16-22
GIA_TRI_GIAO_DIEN_MAC_DINH = {"sheet_link": "", "sheet_auto": True, ...}

# app.py:44-47
for khoa, mac_dinh in GIA_TRI_GIAO_DIEN_MAC_DINH.items():
    if khoa not in st.session_state:
        st.session_state[khoa] = ...
```

Key **đã** tồn tại trên main thread. `KeyError` chỉ là **triệu chứng**.

### Root cause thật

Thread nền không có `ScriptRunContext`. Khi code trong thread đó chạm
`st.session_state`, Streamlit cảnh báo `missing ScriptRunContext` rồi trả về một
`SessionState` **rỗng** — nên key có ở main thread vẫn báo thiếu.

Chuỗi gọi vi phạm (cả hai đều là code của vòng trước):

| # | Vị trí | Thread | Vi phạm |
| --- | --- | --- | --- |
| 1 | `app.py::chay_quet.sau_moi_video` → `lay_sheets()` | `scan-xxxxxxxx` | `st.session_state.sheet_link` |
| 2 | `SheetDeliveryWorker(sender=lambda h, r: lay_sheets().append(...))` | `sheet-delivery` | `st.session_state.sheet_link` |

Vi phạm #2 chưa kịp lộ ra vì #1 chết trước — đúng như lo ngại "có thể còn callback
khác chạm Streamlit nhưng chưa trigger".

> Thêm `if "sheet_link" not in st.session_state: ...` sẽ **che** root cause: worker
> vẫn đọc session state, vẫn nhận proxy rỗng, chỉ là im lặng lấy giá trị mặc định
> rồi gửi lên **sai bảng**. Đó là hỏng âm thầm, tệ hơn báo lỗi.

---

## 3. Root cause — ArrowInvalid

`app.py` dựng bảng trạng thái bằng dict có biểu thức điều kiện:

```python
"Đoạn": "—" if v.matches is None else v.matches      # int trộn str
```

pandas suy ra `object`; PyArrow không ép nổi `'—'` sang `int64` nên ném
`ArrowInvalid`, sau đó Streamlit mới chạy nhánh sửa dtype tự động. Tức **một
exception cho mỗi lần render**, lặp suốt lượt quét.

Đã tái hiện và đối chứng:

```
CŨ  — dtype cột 'Đoạn': object
CŨ  — chuyển Arrow: LỖI -> ArrowInvalid: Could not convert '—' with type str...
MỚI — dtype cột 'Đoạn': string
MỚI — chuyển Arrow: THÀNH CÔNG      giá trị: ['3', '0', '—']
```

Gốc rễ không phải "PyArrow khó tính" mà là **bảng UI không có schema**.

---

## 4. Phương án đã cân nhắc

| Phương án | Lợi | Rủi ro | Quyết định |
| --- | --- | --- | --- |
| A. `add_script_run_ctx()` gắn context vào worker | Không phải đổi kiến trúc | Dùng API nội bộ; worker sống lâu hơn một lần script run; tab đóng/rerun/session thay thế đều làm context hỏng; worker vẫn phụ thuộc vòng đời UI | **Loại** |
| B. Khởi tạo thêm key session state | Một dòng | Che root cause: worker vẫn đọc proxy rỗng rồi im lặng dùng mặc định → gửi sai bảng | **Loại** |
| C. **Snapshot cấu hình ở main thread, worker thuần Python** | Cắt hẳn phụ thuộc; deterministic; rerun-safe; test được không cần Streamlit | Phải đổi chữ ký `sender` | **CHỌN** |
| D. `astype(str)` cả DataFrame | Hết lỗi Arrow | Mất semantic; không giải quyết việc bảng thiếu schema | **Loại** |
| E. **Builder DataFrame riêng, dtype tường minh** | Schema một chỗ, test được bằng `pa.Table.from_pandas` | Thêm một module nhỏ | **CHỌN** |

---

## 5. Kiến trúc sau

```
MAIN STREAMLIT THREAD
  ├─ đọc st.session_state
  ├─ ScanLaunchConfig(auto_sheet, sheet_link, dang_ngang)   ← SNAPSHOT ở đây
  ├─ build_scan_status_dataframe(...)  → st.dataframe
  └─ controller.start(..., on_result=sau_moi_video)
                 │
                 ▼
SCAN WORKER  "scan-xxxxxxxx"        ← chỉ đọc cau_hinh_quet, KHÔNG chạm Streamlit
  └─ Engine.scan_iter() → ScanResult → save_job() → enqueue(SheetDelivery)
                 │
                 ▼
SHEET WORKER "sheet-delivery"       ← nhận sheet_link KÈM công việc
  └─ sender(sheet_link, header, rows) → tao_sheets_exporter(sheet_link).append(...)
```

Ba ranh giới:

| Tầng | Được phép | Không được |
| --- | --- | --- |
| Main Streamlit | `st.*`, `session_state` | tính toán nặng |
| Scan worker | Python thuần, engine, subprocess | mọi API Streamlit |
| Sheet worker | gspread, retry | mọi API Streamlit |

`lay_sheets()` vẫn còn, nhưng chỉ là bản tiện dụng cho main thread; phần thuần là
`tao_sheets_exporter(sheet_link)`.

### Lợi ích nghiệp vụ kèm theo

Snapshot bất biến ⇒ đổi link Sheet **giữa batch** không làm batch đang chạy bắn sang
bảng khác. Batch sau mới dùng cấu hình mới.

---

## 6. Schema bảng trạng thái

| Cột | dtype | "chưa có" |
| --- | --- | --- |
| `#` | `string` | — |
| `Video` | `string` | — |
| `Quét` | `string` | — |
| `Đoạn` | `string` | `—` |
| `Sheets` | `string` | `—` |

**Vì sao `Đoạn` là chuỗi chứ không phải `Int64` + `pd.NA`:** cần phân biệt ba trạng
thái — chưa quét, quét xong 0 đoạn, quét xong N đoạn. Với `Int64`, "chưa quét" hiển
thị thành ô trống, dễ nhìn nhầm là dữ liệu lỗi và khó phân biệt với `0`. Đây là bảng
**trạng thái tạm thời** trong lúc quét, không dùng để sắp xếp hay tính toán, nên ưu
tiên đọc hiểu. Khung rỗng cũng được khai báo dtype để lần render đầu không rơi vào
nhánh sửa dtype.

---

## 7. Tách biệt trạng thái quét và trạng thái giao hàng

Đã có sẵn từ vòng trước và được giữ: `VideoState.scan_status` độc lập với trạng thái
trong `SheetDeliveryWorker.snapshot()`. Một video có thể là `scan=completed` +
`sheet=failed` — **không** phải `video=failed`.

Callback lỗi được `Engine.scan_iter` bắt, ghi log `scan.on_video_callback_failed` và
đi tiếp; `ScanResult` đã được `save_job()` **trước** callback nên không mất.

---

## 8. Chống ghi trùng

Chỉ còn **một** đường giao hàng cho lượt quét: incremental per-video.
`chay_quet()` đặt `job["da_day_sheet"] = True` ngay lúc khởi động, nên nhánh đẩy
cả-batch trong `bang_ket_qua()` (`app.py`, điều kiện `not job.get("da_day_sheet")`)
không bao giờ chạy cho batch đó. Nút "Đẩy lên Google Sheets" thủ công vẫn còn cho
trường hợp người dùng chủ động muốn đẩy lại.

Khoá idempotency (`khoa_giao_hang`) gồm `scan_job_id` nên quét lại cùng video vẫn tạo
dòng mới — đúng nghiệp vụ — nhưng retry cùng một lần giao thì không ghi trùng.

---

## 9. Giới hạn còn lại

- Hàng đợi Sheets nằm trong RAM: tắt app khi còn `pending` là mất phần chưa gửi.
  Kết quả quét vẫn còn trong SQLite nên đẩy lại thủ công được.
- `ScanJobController` và `SheetDeliveryWorker` sống trong `st.session_state`, tức
  theo phiên trình duyệt. TimClipPro chạy local một người dùng nên chấp nhận được;
  nếu sau này phục vụ nhiều phiên thì cần xem lại.
