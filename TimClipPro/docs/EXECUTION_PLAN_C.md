# EXECUTION PLAN C — Xuất báo cáo dạng ngang khớp Google Sheet

> Đặt file này vào `docs/`. Copy từng khối `## TASK Cn` dán vào Codex (Copilot Chat, Agent).
> Làm đúng thứ tự. Sau mỗi task xanh: `git commit -m "Task Cn: ..."`.

## Mục tiêu

Chuyển báo cáo từ **dạng dọc** (1 dòng = 1 đoạn vi phạm) sang **dạng ngang**
(1 dòng = 1 video vi phạm, 5 đoạn trải ngang) để khớp Google Sheet người dùng đã thiết kế.

## Bảng 34 cột đích (thứ tự BẮT BUỘC giữ nguyên)

| # | Tên cột | Nguồn dữ liệu |
|---|---|---|
| 1 | Thời gian quét | thời điểm chạy |
| 2 | Link kênh vi phạm | `ScanResult.channel_url` *(C1 thêm)* |
| 3 | Tên kênh vi phạm | `ScanResult.channel_name` *(C1)* |
| 4 | Id kênh vi phạm | `ScanResult.channel_id` *(C1)* |
| 5 | Link video vi phạm | `ScanResult.source_ref` |
| 6 | Tên video vi phạm | `ScanResult.source_name` |
| 7 | Thời lượng video vi phạm | `hhmmss(ScanResult.duration_s)` |
| 8 | Ngày đăng video vi phạm | `ScanResult.upload_date` *(C1)* |
| 9–13 | Đoạn vi phạm 1–5 | `matches[i]` — định dạng ở C2 |
| 14 | Link video gốc 1 | `clips_meta[clip]["url"]` |
| 15 | Tên video gốc 1 | `clips_meta[clip]["title"]` |
| 16 | Ngày đăng video gốc 1 | `clips_meta[clip]["upload_date"]` *(C4 vá dữ liệu)* |
| 17 | Thời lượng video gốc 1 | `clips_meta[clip]["duration"]` |
| 18–21 | ... video gốc 2 | như trên |
| 22–25 | ... video gốc 3 | như trên |
| 26–29 | ... video gốc 4 | như trên |
| 30–33 | ... video gốc 5 | như trên |
| 34 | Tổng số đoạn phát hiện | `ScanResult.so_dat_nguong` *(C1)* |

---

## TASK C1: Bổ sung metadata kênh, ngày đăng và số đoạn đạt ngưỡng

### Target File
`engine.py` — SỬA method `youtube_info`, SỬA dataclass `ScanResult`, SỬA method `scan_media` và `scan_youtube`

### Context & Tech Stack
- `yt_dlp.YoutubeDL.extract_info()` trả về dict đã chứa sẵn các khoá: `channel`, `channel_id`,
  `channel_url`, `uploader`, `upload_date`. Hiện `youtube_info()` chỉ lấy 4 khoá và **vứt phần còn lại**.
  Lấy thêm KHÔNG tốn lượt gọi mạng nào.
- `ScanResult` hiện có: `source_name, source_ref, source_id, duration_s, matches, matches_loai, status, note, job_id`.

### Exact Input / Output
```python
# ScanResult — THÊM các trường sau, TẤT CẢ phải có giá trị mặc định
channel_name: str = ""
channel_id: str = ""
channel_url: str = ""
upload_date: str = ""     # dạng "YYYYMMDD" như yt-dlp trả về
so_dat_nguong: int = 0    # số đoạn vượt min_hash_floor TRƯỚC khi cắt top N

# youtube_info — trả về dict có THÊM các khoá
{"id", "title", "duration", "uploader",
 "channel", "channel_id", "channel_url", "upload_date"}
```

### Step-by-step Implementation
1. `youtube_info`: bổ sung vào dict trả về — `"channel": info.get("channel") or info.get("uploader") or ""`,
   `"channel_id": info.get("channel_id", "")`, `"channel_url": info.get("channel_url") or info.get("uploader_url") or ""`,
   `"upload_date": str(info.get("upload_date") or "")`. Giữ nguyên 4 khoá cũ.
2. `ScanResult`: thêm 5 trường trên, đặt SAU các trường hiện có, tất cả có mặc định.
3. `scan_youtube`: sau khi gọi `youtube_info`, gán 4 trường metadata vào đối tượng `ScanResult`
   trả về (cả nhánh thành công lẫn nhánh gọi `scan_media` rồi gán lại).
4. `scan_media`: sau khi có `tat_ca` (danh sách đã gộp, đã lọc tự khớp) và TRƯỚC khi gọi `_chon_loc`,
   gán `kq.so_dat_nguong = len([m for m in tat_ca if m.hashes >= self.config.min_hash_floor])`.
5. `save_job` / bảng `jobs`: KHÔNG đổi. Các trường mới chỉ tồn tại trong bộ nhớ, không cần lưu SQLite.

### Edge Cases & Error Handling
| Tình huống | Hành vi bắt buộc |
|---|---|
| yt-dlp không trả `channel` | Dùng `uploader`; cả hai rỗng → `""` |
| yt-dlp không trả `channel_url` | Dùng `uploader_url`; cả hai rỗng → `""` |
| `upload_date` là None | Trả `""`, KHÔNG trả chuỗi `"None"` |
| Quét file local (không qua YouTube) | 4 trường metadata giữ `""`, không lỗi |
| `tat_ca` rỗng | `so_dat_nguong = 0` |
| Code cũ tạo `ScanResult` không truyền trường mới | Vẫn chạy được nhờ giá trị mặc định |

### Constraints
- KHÔNG thêm lượt gọi mạng nào. Lý do: `extract_info` đã trả sẵn mọi thứ cần.
- KHÔNG đổi thứ tự các trường ĐANG CÓ trong `ScanResult`.
- KHÔNG đổi `Engine.HEADER` hay `to_rows()` ở task này.
- KHÔNG sửa schema bảng SQLite.

### Unit Test Criteria
Bổ sung `tests/test_engine_meta.py`:
```python
def test_scanresult_co_truong_moi_voi_mac_dinh():
    from engine import ScanResult
    r = ScanResult(source_name="x")
    assert r.channel_name == "" and r.so_dat_nguong == 0

def test_youtube_info_lay_du_khoa(monkeypatch):
    # giả lập extract_info trả dict đầy đủ -> kiểm tra 8 khoá đều có
    ...

def test_upload_date_none_tra_chuoi_rong(monkeypatch):
    # extract_info trả {"upload_date": None} -> kết quả phải là "" chứ không phải "None"
    ...
```

### Definition of Done
- [ ] `python -m pytest -q` xanh
- [ ] `python -m pytest -m slow` xanh (không làm hỏng luồng quét)
- [ ] `python -c "from engine import ScanResult; print(ScanResult(source_name='x').channel_url)"` in ra dòng trống

---

## TASK C2: Hàm dựng dòng dạng ngang

### Target File
`bang_ngang.py` — TẠO MỚI (thư mục gốc dự án)

### Context & Tech Stack
- Python 3.10+, chỉ thư viện chuẩn.
- Dùng `from engine import Engine, hhmmss`. `Engine.link_moc(source_id, source_ref, giay)` là **staticmethod**.
- `Match` có: `clip, start_s, end_s, matched_s, clip_offset_s, hashes, ty_le, vung, start_hhmmss, end_hhmmss`.
- `clips_meta` là dict `{ten_file: {"id","title","upload_date","duration","url"}}`.

### Exact Input / Output
```python
SO_DOAN = 5   # số đoạn tối đa hiển thị ngang

HEADER_NGANG: list = [...]   # đúng 34 chuỗi theo bảng ở đầu tài liệu này

def dinh_dang_ngay(s: str) -> str:
    """Đổi "20250115" -> "15/01/2025". Rỗng hoặc sai định dạng -> ""."""

def dinh_dang_doan(m, source_id: str, source_ref: str) -> str:
    """Trả về "00:14:10 – 00:30:46 · https://youtu.be/xxx?t=850". Link rỗng -> bỏ phần link."""

def dung_dong_ngang(kq, clips_meta: dict | None = None) -> list:
    """Dựng ĐÚNG MỘT dòng 34 phần tử từ một ScanResult. Hàm THUẦN, không I/O."""
```

### Step-by-step Implementation
1. `HEADER_NGANG` viết đúng 34 chuỗi theo bảng đầu tài liệu, giữ nguyên dấu tiếng Việt và
   cách viết hoa. Đây là hợp đồng với Google Sheet của người dùng — sai một ký tự là lệch cột.
2. `dinh_dang_ngay`: chuỗi 8 ký tự toàn số → `"DD/MM/YYYY"`. Mọi trường hợp khác (rỗng, `"00000000"`,
   độ dài khác, có chữ) → trả `""`.
3. `dinh_dang_doan`: ghép `m.start_hhmmss` + `" – "` + `m.end_hhmmss`. Gọi
   `Engine.link_moc(source_id, source_ref, m.start_s)`; link khác rỗng thì nối thêm `" · " + link`.
4. `dung_dong_ngang`:
   - `clips_meta` là None → `{}`.
   - Cột 1: thời điểm hiện tại `"%Y-%m-%d %H:%M:%S"`.
   - Cột 2–8 lấy từ `kq`. Cột 7 dùng `hhmmss(kq.duration_s)`. Cột 8 dùng `dinh_dang_ngay(kq.upload_date)`.
   - Cột 9–13: duyệt `i` từ 0 tới `SO_DOAN-1`; có `matches[i]` thì `dinh_dang_doan(...)`, không thì `""`.
   - Cột 14–33: với mỗi `i`, tra `clips_meta.get(matches[i].clip, {})` lấy 4 giá trị theo thứ tự
     url, title, `dinh_dang_ngay(upload_date)`, `hhmmss(duration)`. Không có match thứ `i` → 4 ô rỗng.
     `duration` rỗng hoặc 0 → ô thời lượng để `""` (KHÔNG in `00:00:00`).
   - Cột 34: `kq.so_dat_nguong`.
   - Kết quả có `status != "ok"` → vẫn trả đủ 34 ô, ô 6 ghi `f"(LỖI: {kq.note})"`, các ô đoạn để rỗng.
5. Mọi giá trị trả về phải là `str` hoặc `int`, KHÔNG có `None`.

### Edge Cases & Error Handling
| Tình huống | Hành vi bắt buộc |
|---|---|
| `matches` rỗng | 34 ô, cột 9–33 rỗng, cột 34 vẫn ghi `so_dat_nguong` |
| Chỉ có 2 match | Ô đoạn 3–5 và nhóm gốc 3–5 để rỗng |
| Nhiều hơn 5 match | Chỉ lấy 5 cái ĐẦU TIÊN (đã được `_chon_loc` sắp theo thời gian) |
| `clips_meta` thiếu clip đó | 4 ô của nhóm gốc đó để rỗng, KHÔNG ném `KeyError` |
| `upload_date == "00000000"` | `dinh_dang_ngay` trả `""` |
| `source_id` rỗng (quét file local) | `dinh_dang_doan` chỉ có khoảng thời gian, không có link |
| `status != "ok"` | Vẫn đủ 34 ô |

### Constraints
- KHÔNG `import streamlit`, KHÔNG `print()`, KHÔNG đọc/ghi file. Lý do: hàm thuần mới test được bằng so sánh danh sách.
- KHÔNG sửa `engine.py`.
- Độ dài dòng trả về phải LUÔN bằng `len(HEADER_NGANG)`.

### Unit Test Criteria
Tạo `tests/test_bang_ngang.py`:
```python
def test_luon_du_34_cot():
    from engine import ScanResult
    assert len(dung_dong_ngang(ScanResult(source_name="x"))) == len(HEADER_NGANG) == 34

def test_dinh_dang_ngay():
    assert dinh_dang_ngay("20250115") == "15/01/2025"
    assert dinh_dang_ngay("00000000") == ""
    assert dinh_dang_ngay("") == ""

def test_chi_lay_5_doan_dau():
    # dựng ScanResult 7 match -> ô đoạn 5 là match thứ 5, không có ô nào cho match 6,7
    ...
```

### Definition of Done
- [ ] `python -m pytest -q` xanh
- [ ] `len(HEADER_NGANG) == 34`
- [ ] Mọi test đều khẳng định độ dài dòng bằng 34

---

## TASK C3: Nối vào CSV và Google Sheets

### Target File
`engine.py` — THÊM method; `cli.py` — THÊM tham số

### Context & Tech Stack
- `Engine.export_csv(ket, ten_file=None) -> str` đang xuất dạng dọc — GIỮ NGUYÊN, không đổi.
- `SheetsExporter.append(header: list, rows: list, ghi_header_neu_trong: bool = True) -> int`
- `watch.chay_giam_sat(...)` đang gọi `engine.to_rows(ket)` và `engine.HEADER` để đẩy Sheets.

### Exact Input / Output
```python
# engine.py — THÊM 2 method vào class Engine
def to_rows_ngang(self, ket: Iterable) -> list:
    """Mỗi ScanResult -> đúng 1 dòng 34 cột. Bỏ qua kết quả status != 'ok'."""

def export_csv_ngang(self, ket: Iterable, ten_file: Optional[str] = None) -> str:
    """Xuất CSV dạng ngang, encoding utf-8-sig. Trả về đường dẫn."""
```

### Step-by-step Implementation
1. `import bang_ngang` ở đầu `engine.py`.
2. `to_rows_ngang`: gọi `self.clip_meta()` MỘT LẦN, rồi với mỗi `kq` gọi `bang_ngang.dung_dong_ngang(kq, meta)`.
   Bỏ qua `kq` có `status != "ok"` hoặc `not kq.matches` (không ghi dòng rỗng vào sheet theo dõi hồ sơ).
3. `export_csv_ngang`: giống `export_csv` nhưng dùng `bang_ngang.HEADER_NGANG` và `to_rows_ngang`,
   tên file mặc định `ketqua_ngang_<YYYYmmdd_HHMMSS>.csv`.
4. `watch.chay_giam_sat`: thêm tham số `dang_ngang: bool = True`. Khi `True` thì đẩy Sheets bằng
   `bang_ngang.HEADER_NGANG` và `engine.to_rows_ngang(ket)`, đồng thời xuất `export_csv_ngang`.
   Khi `False` giữ nguyên hành vi cũ.
5. `cli.py`: thêm cờ `--dang-doc` cho lệnh `watch` (mặc định tắt, nghĩa là mặc định dùng dạng ngang).
   Truyền `dang_ngang = not a.dang_doc`.

### Edge Cases & Error Handling
| Tình huống | Hành vi bắt buộc |
|---|---|
| Mọi kết quả đều lỗi hoặc không match | `to_rows_ngang` trả `[]`, KHÔNG tạo file CSV |
| `clip_meta()` trả `{}` | Vẫn dựng đủ dòng, các ô metadata gốc để rỗng |
| Google Sheets lỗi | CSV vẫn phải được tạo (giữ hành vi cũ) |
| Người dùng chạy `--dang-doc` | Xuất y như trước khi có task này |

### Constraints
- KHÔNG sửa `export_csv` và `to_rows` đang có. Lý do: giao diện web và các test hiện tại đang phụ thuộc chúng.
- KHÔNG đổi `Engine.HEADER`.
- KHÔNG để `bang_ngang` import ngược `engine` ở cấp module nếu gây vòng lặp import — nếu vòng lặp
  xảy ra, import cục bộ bên trong hàm.

### Unit Test Criteria
Bổ sung `tests/test_bang_ngang.py`:
```python
def test_to_rows_ngang_bo_qua_ket_qua_loi(engine):
    # 1 kết quả ok có match + 1 status="error" -> chỉ 1 dòng
    ...

def test_export_csv_ngang_co_bom_utf8(engine, tmp_path):
    engine.out_dir = str(tmp_path)
    # kiểm tra 3 byte đầu là BOM và dòng header có 34 cột
    ...
```

### Definition of Done
- [ ] `python -m pytest -q` xanh
- [ ] `python cli.py watch --help` hiện cờ `--dang-doc`
- [ ] File CSV ngang mở bằng Excel hiện đúng 34 cột, tiếng Việt có dấu

---

## TASK C4: Vá ngày đăng và thời lượng cho clip đã tải

### Target File
`channel.py` — THÊM method vào `ChannelSync`; `cli.py` — THÊM lệnh `vameta`

### Context & Tech Stack
- `clips_meta.json` hiện lưu `{ten_file: {"id","title","upload_date","duration","url"}}`.
- Vì `list_channel()` dùng `extract_flat` (chế độ nhanh), `upload_date` của các clip đã tải đang rỗng
  hoặc `"00000000"`. Đây là dữ liệu cho 5 cột "Ngày đăng video gốc" trong sheet.
- Kho của người dùng có ~748 clip → phải chịu được gián đoạn.

### Exact Input / Output
```python
def va_metadata(self, progress=None, fetcher=None, chi_thieu: bool = True) -> dict:
    """
    Bổ sung upload_date / duration còn thiếu trong clips_meta.json.
    KHÔNG tải lại video, chỉ lấy metadata.
    fetcher: hàm (video_id) -> dict, None thì dùng yt_dlp. Cho phép test offline.
    Trả về {"tong": n, "da_va": n, "bo_qua": n, "loi": [...]}
    """
```

### Step-by-step Implementation
1. Đọc `clips_meta.json`. Nếu rỗng → trả về ngay với `tong=0`.
2. Nếu `chi_thieu=True`: chỉ xử lý mục có `upload_date` rỗng / `"00000000"` / thiếu khoá,
   HOẶC `duration` rỗng / 0. Ngược lại xử lý toàn bộ.
3. Với mỗi mục cần vá: gọi `fetcher(video_id)`. Mặc định fetcher dùng
   `yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True, "skip_download": True})` và
   `extract_info(f"https://youtu.be/{vid}", download=False)`, trả dict có `upload_date`, `duration`.
4. Cập nhật mục, rồi **ghi lại `clips_meta.json` NGAY sau mỗi mục** (không đợi tới cuối).
   Lý do: 748 mục mất nhiều phút, đứt giữa chừng không được mất công đã làm.
5. Lỗi ở một mục → ghi vào `loi`, tiếp tục mục kế.
6. Báo tiến độ qua `progress(pct, msg)` với `pct = i / tong_can_va`.
7. `cli.py`: thêm lệnh `vameta` nhận `--kho` (thư mục kho), gọi `ChannelSync(kho).va_metadata(in_tien_do)`,
   in tóm tắt cuối.

### Edge Cases & Error Handling
| Tình huống | Hành vi bắt buộc |
|---|---|
| `clips_meta.json` không tồn tại | Trả `{"tong": 0, ...}`, không ném lỗi |
| Không mục nào thiếu | `da_va = 0`, không gọi mạng lần nào |
| Một video đã bị xoá khỏi YouTube | Ghi vào `loi`, giữ nguyên metadata cũ, tiếp tục |
| Mất mạng giữa chừng | Các mục đã vá vẫn được lưu; chạy lại chỉ xử lý phần còn thiếu |
| `fetcher` trả `upload_date` None | Giữ nguyên giá trị cũ, không ghi `"None"` |

### Constraints
- KHÔNG tải lại file audio nào. Lý do: 748 clip đã có sẵn trên đĩa.
- KHÔNG đổi tên file audio đã tồn tại. Lý do: đổi tên sẽ làm lệch khoá trong `clips_meta.json`
  và lệch `downloaded.txt`.
- KHÔNG đổi `list_channel` sang chế độ đầy đủ — sẽ chậm gấp nhiều lần cho mọi lần đồng bộ sau này.

### Unit Test Criteria
Tạo `tests/test_va_meta.py`, dùng `fetcher` giả, KHÔNG gọi mạng:
```python
def test_chi_va_muc_thieu(tmp_path):
    # meta có 1 mục đủ + 1 mục upload_date="00000000"
    # -> fetcher chỉ được gọi đúng 1 lần
    ...

def test_ghi_ngay_sau_moi_muc(tmp_path):
    # fetcher ném lỗi ở mục thứ 2 -> mục thứ 1 vẫn phải đã được lưu xuống file
    ...
```

### Definition of Done
- [ ] `python -m pytest -q` xanh
- [ ] `python cli.py vameta --kho "D:\ClipGocSML"` chạy được, in tiến độ
- [ ] Sau khi chạy, mở `clips_meta.json` thấy `upload_date` dạng `"20250115"`

---

## Sau khi xong cả 4 task

```
git add . && git commit -m "Phase C: bao cao dang ngang khop Google Sheet"
git tag v1.2-bangngang
```

### Kiểm tra thật

1. Chạy `python cli.py vameta --kho "<thư mục kho>"` (mất ~10 phút cho 748 clip).
2. Mở Google Sheet → đổi tên tab `KetQuaQuet` cũ thành `KetQuaQuet_cu` (giữ lại để đối chiếu).
3. Đổi tên tab `Sheet1` (33 cột) thành `KetQuaQuet`, **thêm cột 34** tiêu đề `Tổng số đoạn phát hiện`.
4. Thêm một link video mới vào `watchlist.json`, chạy `python cli.py watch --sheet "<link>"`.
5. Kiểm tra: dữ liệu rơi đúng cột, ngày tháng dạng `DD/MM/YYYY`, ô đoạn vi phạm bấm được link.

> Nếu tiêu đề cột trong `HEADER_NGANG` khác dù chỉ một ký tự so với hàng tiêu đề trong sheet,
> gspread vẫn ghi được nhưng dữ liệu sẽ nằm lệch. Đối chiếu kỹ ở bước 3.