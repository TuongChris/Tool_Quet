# EXECUTION PLAN B — Tính năng: Giám sát tự động

> Đặt file này vào `docs/`. Copy từng khối `## TASK Bn` dán thẳng vào Codex (Copilot Chat, chế độ Agent).
> Làm **đúng thứ tự**. Sau mỗi task xanh: `git commit -m "Task Bn: ..."`.

## Mục tiêu

Biến tool từ "mở ra dùng" thành "tự chạy hằng đêm, sáng ra đọc báo cáo".

```
watchlist.json ──► watch.py ──► engine.scan_youtube() ──► CSV + Google Sheets
   (kênh + link)        │
                        └── nguồn sự thật "đã quét cái nào": bảng jobs trong SQLite
                            (cột source_id đã có sẵn — KHÔNG tạo file trạng thái mới)
```

## Phân rã

| Task | File | Vai trò | Phụ thuộc |
|---|---|---|---|
| B1 | `watch.py` | Data model + đọc/ghi `watchlist.json` + tách ID từ URL | — |
| B2 | `watch.py` | Logic chống quét trùng (thuần, không I/O) | B1 |
| B3 | `watch.py` | Mở rộng kênh thành danh sách video ứng viên | B1, B2 |
| B4 | `watch.py` | Hàm điều phối `chay_giam_sat()` + báo cáo | B1–B3 |
| B5 | `cli.py` + `GiamSat.bat` | Lệnh chạy + ghép Task Scheduler | B4 |
| B6 | `tests/test_watch.py` | Bộ test đầy đủ | B1–B4 |

## Nguyên tắc xuyên suốt

- `watch.py` KHÔNG `import streamlit`, KHÔNG `print()`. Báo tiến độ qua callback `progress(pct, msg)`.
- Mọi hàm chạm mạng phải nhận tham số tiêm phụ thuộc (dependency injection) để test được offline.
- Một nguồn lỗi KHÔNG được làm đứt cả lượt quét.

---

## TASK B1: Data model, đọc/ghi watchlist và tách ID YouTube

### Target File
`watch.py` — TẠO MỚI (thư mục gốc dự án)

### Context & Tech Stack
- Python 3.10+, chỉ thư viện chuẩn (`dataclasses`, `json`, `re`, `os`, `typing`)
- Ràng buộc dự án: `.github/copilot-instructions.md`
- Tham khảo cách đọc/ghi JSON an toàn: `channel.py` các hàm `load_meta` / `save_meta`

### Exact Input / Output
```python
from dataclasses import dataclass, field

@dataclass
class MucTheoDoi:
    loai: str          # "kenh" hoặc "link"
    url: str
    ghi_chu: str = ""
    bat: bool = True   # False = tạm tắt, bỏ qua khi quét

@dataclass
class WatchList:
    muc: list = field(default_factory=list)   # list[MucTheoDoi]
    kho: str = ""                             # tên kho vân tay dùng để đối chiếu
    gioi_han_moi_lan: int = 20                # tối đa bao nhiêu video mỗi lượt chạy

def lay_id_youtube(url: str) -> str:
    """Tách ID video từ URL YouTube. Trả về "" nếu không nhận dạng được."""

def doc_watchlist(path: str) -> WatchList:
    """Đọc watchlist.json. File không tồn tại hoặc hỏng -> trả WatchList rỗng."""

def ghi_watchlist(wl: WatchList, path: str) -> None:
    """Ghi watchlist.json, encoding utf-8, ensure_ascii=False, indent=2."""
```

### Step-by-step Implementation
1. `lay_id_youtube`: nhận dạng được cả 3 dạng — `https://youtu.be/<ID>`, `https://www.youtube.com/watch?v=<ID>`, `https://www.youtube.com/shorts/<ID>`. ID gồm ký tự `A-Za-z0-9_-`, độ dài 6–20. Có tham số phụ phía sau (`?t=`, `&list=`) vẫn phải tách đúng.
2. `doc_watchlist`: nếu file không tồn tại → trả `WatchList()`. Nếu đọc/parse lỗi → cũng trả `WatchList()`, KHÔNG ném exception.
3. Khi dựng lại `MucTheoDoi` từ JSON, bỏ qua phần tử thiếu `url` hoặc có `loai` không thuộc {"kenh","link"}.
4. `ghi_watchlist`: dùng `with open(..., "w", encoding="utf-8")`, `json.dump(..., ensure_ascii=False, indent=2)`.

### Edge Cases & Error Handling
| Tình huống | Hành vi bắt buộc |
|---|---|
| File không tồn tại | Trả `WatchList()` rỗng, không tạo file |
| JSON hỏng / rỗng | Trả `WatchList()` rỗng, không ném lỗi |
| Phần tử thiếu `url` | Bỏ qua phần tử đó, giữ các phần tử còn lại |
| `loai` sai giá trị | Bỏ qua phần tử đó |
| URL không phải YouTube | `lay_id_youtube` trả `""` |
| URL có `?t=90` hoặc `&list=...` | Vẫn tách đúng ID |
| `ghi_watchlist` với `ghi_chu` tiếng Việt có dấu | Đọc lại phải nguyên vẹn |

### Constraints
- KHÔNG `import streamlit`, KHÔNG `print()`.
- KHÔNG dùng `open()` ngoài khối `with`.

### Unit Test Criteria
```python
def test_tach_id_cac_dang_url():
    assert lay_id_youtube("https://youtu.be/dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert lay_id_youtube("https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=X") == "dQw4w9WgXcQ"
    assert lay_id_youtube("https://example.com/abc") == ""

def test_doc_file_khong_ton_tai(tmp_path):
    assert doc_watchlist(str(tmp_path / "chua_co.json")).muc == []
```

### Definition of Done
- [ ] `python -c "import watch"` không lỗi
- [ ] `python -m pytest -q` xanh

---

## TASK B2: Logic chống quét trùng

### Target File
`watch.py` — THÊM hàm vào file đã tạo ở B1

### Context & Tech Stack
- `Engine.list_jobs(limit: int = 200) -> list` trả về list dict, mỗi dict có các khoá:
  `id, created_at, source_type, source_name, source_ref, duration_s, status, n_matches, note, source_id`
- `source_id` chính là ID video YouTube đã quét. Đây là NGUỒN SỰ THẬT DUY NHẤT cho việc "đã quét chưa" — KHÔNG tạo file trạng thái riêng.

### Exact Input / Output
```python
@dataclass
class UngVien:
    video_id: str
    url: str
    tieu_de: str = ""
    nguon: str = ""      # url của mục theo dõi đã sinh ra ứng viên này

def id_da_quet(engine, chi_thanh_cong: bool = True) -> set:
    """Trả về set các video_id đã quét, đọc từ lịch sử SQLite."""

def loc_can_quet(ung_vien: list, da_quet: set, gioi_han: int = 0) -> list:
    """Lọc ra các ứng viên CHƯA quét. Hàm THUẦN — không chạm engine, không I/O."""
```

### Step-by-step Implementation
1. `id_da_quet`: gọi `engine.list_jobs(limit=100000)`. Lấy `source_id` của các job, bỏ qua giá trị rỗng/None. Nếu `chi_thanh_cong=True` thì chỉ tính job có `status == "ok"` (job lỗi phải được quét lại ở lượt sau).
2. `loc_can_quet`: giữ ứng viên có `video_id` không nằm trong `da_quet` và `video_id` khác rỗng.
3. Khử trùng lặp trong chính danh sách ứng viên: cùng một `video_id` xuất hiện nhiều lần (do nằm ở nhiều kênh) chỉ giữ lần đầu.
4. Nếu `gioi_han > 0` thì cắt còn tối đa `gioi_han` phần tử. `gioi_han <= 0` nghĩa là không giới hạn.
5. Giữ nguyên thứ tự ban đầu của danh sách đầu vào.

### Edge Cases & Error Handling
| Tình huống | Hành vi bắt buộc |
|---|---|
| `ung_vien` rỗng | Trả `[]` |
| `da_quet` rỗng | Trả toàn bộ (sau khi khử trùng lặp và cắt giới hạn) |
| Ứng viên có `video_id` rỗng | Loại bỏ |
| Cùng `video_id` xuất hiện 3 lần | Chỉ giữ 1 |
| `gioi_han` lớn hơn số ứng viên | Trả hết, không lỗi |
| `engine.list_jobs()` trả rỗng | `id_da_quet` trả `set()` |

### Constraints
- `loc_can_quet` phải THUẦN: không gọi engine, không đọc file, không dùng thời gian hệ thống. Lý do: hàm này quyết định quét cái gì — phải test được tuyệt đối chắc chắn.
- KHÔNG tạo file trạng thái mới.

### Unit Test Criteria
```python
def test_khu_trung_lap_trong_ung_vien():
    uv = [UngVien("a", "u1"), UngVien("a", "u1"), UngVien("b", "u2")]
    assert [x.video_id for x in loc_can_quet(uv, set())] == ["a", "b"]

def test_bo_qua_id_da_quet():
    uv = [UngVien("a", "u1"), UngVien("b", "u2")]
    assert [x.video_id for x in loc_can_quet(uv, {"a"})] == ["b"]
```

### Definition of Done
- [ ] `python -m pytest -q` xanh
- [ ] `loc_can_quet` không tham chiếu tới bất kỳ đối tượng nào ngoài tham số của nó

---

## TASK B3: Mở rộng kênh thành danh sách ứng viên

### Target File
`watch.py` — THÊM hàm

### Context & Tech Stack
- `ChannelSync.list_channel(url: str, limit: Optional[int] = None) -> list` là **staticmethod**, trả về list `VideoInfo` có các trường: `id, title, upload_date, duration, url`. Import: `from channel import ChannelSync`.
- Hàm này gọi mạng. Phải cho phép tiêm phụ thuộc để test offline.

### Exact Input / Output
```python
def lay_ung_vien(wl: WatchList, lister=None, gioi_han_kenh: int = 50) -> tuple:
    """
    Mở rộng watchlist thành danh sách ứng viên.
    lister: hàm (url, limit) -> list[VideoInfo]. None thì dùng ChannelSync.list_channel.
    Trả về (danh_sach_ung_vien, danh_sach_loi).
    danh_sach_loi: list[str], mỗi phần tử là một dòng mô tả lỗi.
    """
```

### Step-by-step Implementation
1. `if lister is None: lister = ChannelSync.list_channel`.
2. Duyệt `wl.muc`, bỏ qua mục có `bat == False`.
3. Với mục `loai == "link"`: gọi `lay_id_youtube(muc.url)`. ID rỗng → thêm vào `danh_sach_loi` dòng nêu rõ URL không nhận dạng được, rồi bỏ qua. ID hợp lệ → tạo `UngVien(video_id=id, url=muc.url, tieu_de="", nguon=muc.url)`.
4. Với mục `loai == "kenh"`: gọi `lister(muc.url, gioi_han_kenh)` trong `try/except`. Exception → thêm vào `danh_sach_loi` dòng gồm URL kênh và nội dung lỗi, rồi tiếp tục mục kế (KHÔNG dừng cả vòng lặp). Thành công → với mỗi `VideoInfo` tạo `UngVien(video_id=v.id, url=v.url, tieu_de=v.title, nguon=muc.url)`.
5. Trả về `(ung_vien, loi)` theo đúng thứ tự duyệt.

### Edge Cases & Error Handling
| Tình huống | Hành vi bắt buộc |
|---|---|
| `wl.muc` rỗng | Trả `([], [])` |
| Mọi mục đều `bat=False` | Trả `([], [])` |
| Một kênh ném exception | Ghi vào `danh_sach_loi`, các mục còn lại VẪN được xử lý |
| `lister` trả list rỗng | Không lỗi, không thêm ứng viên |
| Link đơn lẻ không tách được ID | Ghi vào `danh_sach_loi`, bỏ qua |
| `VideoInfo` thiếu `title` | `tieu_de = ""`, không crash |

### Constraints
- KHÔNG gọi trực tiếp `ChannelSync.list_channel` bên trong vòng lặp — luôn gọi qua biến `lister`. Lý do: có tiêm phụ thuộc mới test được mà không cần mạng.
- KHÔNG để một mục lỗi làm dừng cả hàm.

### Unit Test Criteria
```python
def test_kenh_loi_khong_lam_dut_cac_muc_con_lai():
    def lister_gia(url, limit=None):
        if "hong" in url:
            raise RuntimeError("khong ket noi duoc")
        return [type("V", (), {"id": "x1", "title": "T", "url": "u", "upload_date": "", "duration": 0})()]
    wl = WatchList(muc=[MucTheoDoi("kenh", "https://youtube.com/@hong"),
                        MucTheoDoi("kenh", "https://youtube.com/@tot")])
    uv, loi = lay_ung_vien(wl, lister=lister_gia)
    assert len(uv) == 1 and len(loi) == 1
```

### Definition of Done
- [ ] `python -m pytest -q` xanh
- [ ] Test chạy được khi máy KHÔNG có mạng

---

## TASK B4: Hàm điều phối `chay_giam_sat()`

### Target File
`watch.py` — THÊM hàm và dataclass

### Context & Tech Stack
- `Engine.use_kho(ten: str) -> None`
- `Engine.scan_youtube(url: str, progress=None, luu_lich_su: bool = True) -> ScanResult`
- `Engine.to_rows(ket: Iterable) -> list` và `Engine.HEADER`
- `Engine.export_csv(ket: Iterable, ten_file=None) -> str`
- `SheetsExporter(key_path=None, sheet="", worksheet="KetQuaQuet")`, có `.san_sang() -> bool` và `.append(header, rows) -> int`. Import: `from sheets import SheetsExporter`.
- `ScanResult` có `.status`, `.note`, `.matches`, `.source_name`

### Exact Input / Output
```python
@dataclass
class BaoCao:
    tong_ung_vien: int = 0
    da_quet_truoc: int = 0
    quet_moi: int = 0
    nguon_co_vi_pham: int = 0
    tong_bang_chung: int = 0
    csv_path: str = ""
    sheets_ok: bool = False
    sheets_note: str = ""
    loi: list = field(default_factory=list)

    def tom_tat(self) -> str:
        """Trả về bản tóm tắt nhiều dòng, tiếng Việt, để in ra console hoặc gửi email."""

def chay_giam_sat(engine, wl: WatchList, progress=None,
                  lister=None, sheet_link: str = "") -> BaoCao:
    """Chạy một lượt giám sát đầy đủ."""
```

### Step-by-step Implementation
1. Nếu `wl.kho` khác rỗng: gọi `engine.use_kho(wl.kho)` trong `try/except`; lỗi thì ghi vào `bao_cao.loi` và tiếp tục với kho đang dùng.
2. `ung_vien, loi = lay_ung_vien(wl, lister=lister)`; đưa `loi` vào `bao_cao.loi`.
3. `da_quet = id_da_quet(engine)`.
4. `can_quet = loc_can_quet(ung_vien, da_quet, wl.gioi_han_moi_lan)`.
5. Gán `tong_ung_vien = len(ung_vien)`, `da_quet_truoc = len(ung_vien) - len(can_quet)`.
6. Duyệt `can_quet`, với mỗi ứng viên: gọi `engine.scan_youtube(uv.url, progress=<callback bọc lại>)` trong `try/except`. Callback bọc lại phải quy đổi tiến độ của từng video thành tiến độ tổng: `progress((i + pct) / len(can_quet), f"[{i+1}/{len(can_quet)}] {msg}")`.
7. Gom mọi `ScanResult` vào một list. Đếm: `quet_moi` = số đã gọi quét; `nguon_co_vi_pham` = số kết quả có `matches` khác rỗng; `tong_bang_chung` = tổng số phần tử `matches`.
8. Kết quả có `status != "ok"` → thêm một dòng vào `bao_cao.loi` gồm tên nguồn và `note`.
9. Nếu có ít nhất một kết quả: gọi `engine.export_csv(ket)` và gán `csv_path`.
10. Nếu `sheet_link` khác rỗng: dựng `SheetsExporter(sheet=sheet_link)`; nếu `.san_sang()` thì gọi `.append(engine.HEADER, engine.to_rows(ket))` trong `try/except`, gán `sheets_ok` và `sheets_note` tương ứng. Không sẵn sàng → `sheets_ok=False`, `sheets_note` nêu lý do.
11. Trả về `BaoCao`.

### Edge Cases & Error Handling
| Tình huống | Hành vi bắt buộc |
|---|---|
| Không có ứng viên nào | Trả `BaoCao` với mọi số đếm bằng 0, KHÔNG tạo file CSV |
| Tất cả đã quét trước đó | `quet_moi = 0`, không tạo CSV, không lỗi |
| Một video quét thất bại | Ghi vào `loi`, các video còn lại VẪN được quét tiếp |
| `engine.scan_youtube` ném exception | Bắt lại, ghi vào `loi`, tiếp tục |
| Google Sheets chưa cấu hình | `sheets_ok=False`, `sheets_note` nêu lý do, KHÔNG ném lỗi |
| Ghi Sheets thất bại giữa chừng | Bắt lại, ghi `sheets_note`, CSV vẫn phải được tạo |
| `wl.kho` trỏ tới kho không tồn tại | Ghi vào `loi`, tiếp tục với kho hiện tại |

### Constraints
- KHÔNG `print()` — mọi thông tin đi qua `progress` hoặc `BaoCao`.
- KHÔNG để bất kỳ nguồn lỗi nào làm dừng cả lượt quét. Lý do: chạy hằng đêm không có người ngồi canh.
- KHÔNG gọi `sys.exit()`.

### Unit Test Criteria
```python
def test_mot_video_loi_khong_lam_dut_luot_quet(engine, monkeypatch):
    # giả lập scan_youtube: video thứ 2 ném exception
    # kỳ vọng: quet_moi == 3, len(bao_cao.loi) >= 1
    ...

def test_khong_co_ung_vien_thi_khong_tao_csv(engine):
    bc = chay_giam_sat(engine, WatchList())
    assert bc.quet_moi == 0 and bc.csv_path == ""
```

### Definition of Done
- [ ] `python -m pytest -q` xanh
- [ ] Test chạy được offline (dùng `lister` giả và monkeypatch `scan_youtube`)

---

## TASK B5: Lệnh CLI và file chạy cho Task Scheduler

### Target File
`cli.py` — THÊM lệnh; `GiamSat.bat` — TẠO MỚI

### Context & Tech Stack
- Đọc trước: `cli.py` — hàm `main()` dùng `argparse`, đã có các lệnh `kenh`, `taodb`, `themclip`, `youtube`, `file`.
- Hàm in tiến độ có sẵn: `in_tien_do(pct, msg)`.

### Exact Input / Output
```
python cli.py watch                          # dùng watchlist.json ở thư mục gốc
python cli.py watch --file duong/dan.json    # chỉ định file khác
python cli.py watch --sheet "<link Google Sheet>"
python cli.py watch --gioi-han 5             # ghi đè gioi_han_moi_lan
```

### Step-by-step Implementation
1. Thêm `"watch"` vào danh sách `choices` của tham số `lenh`.
2. Thêm các tham số: `--file` (mặc định `watchlist.json`), `--sheet` (mặc định `""`), `--gioi-han` (kiểu int, mặc định `0` nghĩa là dùng giá trị trong file).
3. Trong `main()`, xử lý nhánh `watch`: `wl = watch.doc_watchlist(a.file)`.
4. Nếu `wl.muc` rỗng: in hướng dẫn tạo `watchlist.json` kèm ví dụ nội dung mẫu, rồi `return`.
5. Nếu `a.gioi_han > 0`: gán đè `wl.gioi_han_moi_lan`.
6. Gọi `bc = watch.chay_giam_sat(eng, wl, in_tien_do, sheet_link=a.sheet)`.
7. In `bc.tom_tat()`.
8. Thoát với mã 0 nếu không có lỗi, mã 1 nếu `bc.loi` khác rỗng. Lý do: Task Scheduler dựa vào mã thoát để báo trạng thái.

### GiamSat.bat
File batch ASCII (không dấu tiếng Việt trong file .bat), dòng kết thúc CRLF, nội dung:
1. `cd /d "%~dp0"`
2. Xác định lệnh Python như các file .bat khác trong dự án (thử `py -3` rồi `python`).
3. Gọi `cli.py watch`, ghi toàn bộ output ra `ketqua\giamsat_<ngày>.log` bằng cách nối `>> "ketqua\giamsat_%date:~-4%%date:~3,2%%date:~0,2%.log" 2>&1`.
4. KHÔNG có lệnh `pause` — Task Scheduler chạy nền, `pause` sẽ treo tiến trình vĩnh viễn.

### Đồng thời cập nhật tài liệu
Thêm vào cuối `HUONG_DAN.md` một mục hướng dẫn ghép Task Scheduler:
mở Task Scheduler → Create Basic Task → chọn tần suất → Action là Start a program →
Program/script trỏ tới `GiamSat.bat` → Start in trỏ tới thư mục dự án.
Kèm ví dụ đầy đủ nội dung `watchlist.json`.

### Edge Cases & Error Handling
| Tình huống | Hành vi bắt buộc |
|---|---|
| `watchlist.json` không tồn tại | In hướng dẫn + ví dụ mẫu, thoát mã 0 (không phải lỗi) |
| `watchlist.json` rỗng | Như trên |
| Có lỗi trong lượt quét | In tóm tắt đầy đủ rồi thoát mã 1 |
| Chạy khi không có mạng | Lỗi được gom vào `bc.loi`, không crash, vẫn in tóm tắt |

### Constraints
- KHÔNG thêm `pause` vào `GiamSat.bat`.
- KHÔNG đổi hành vi của các lệnh CLI đang có.
- File `.bat` không được chứa ký tự tiếng Việt có dấu. Lý do: console Windows mặc định không hiển thị đúng.

### Definition of Done
- [ ] `python cli.py watch --help` chạy được, hiện đủ tham số
- [ ] `python cli.py watch` khi chưa có `watchlist.json` in hướng dẫn, không crash
- [ ] `python -m pytest -q` xanh
- [ ] `GiamSat.bat` không chứa `pause`

---

## TASK B6: Bộ test đầy đủ cho watch.py

### Target File
`tests/test_watch.py` — TẠO MỚI

### Context & Tech Stack
- pytest. Đọc trước `tests/conftest.py`: có fixture `engine` (dữ liệu ghi vào `tmp_path`, không đụng `data/` thật) và helper `M()` tạo `Match` giả.
- Đọc `tests/test_engine_core.py` để theo cùng phong cách.

### Bước 1 — Rà soát
Liệt kê các test đã có trong `tests/test_watch.py` (nếu Codex đã tạo ở B1–B4). Không viết lại test đã có.

### Bước 2 — Đảm bảo phủ đủ bảng sau
| # | Tình huống cần phủ |
|---|---|
| 1 | `lay_id_youtube` với 3 dạng URL hợp lệ |
| 2 | `lay_id_youtube` với URL có `?t=` và `&list=` |
| 3 | `lay_id_youtube` với URL không phải YouTube → `""` |
| 4 | `doc_watchlist` file không tồn tại → rỗng |
| 5 | `doc_watchlist` file JSON hỏng → rỗng, không ném lỗi |
| 6 | `ghi_watchlist` rồi `doc_watchlist` → `ghi_chu` tiếng Việt nguyên vẹn |
| 7 | `doc_watchlist` bỏ qua phần tử thiếu `url` nhưng giữ phần tử hợp lệ |
| 8 | `loc_can_quet` khử trùng lặp cùng `video_id` |
| 9 | `loc_can_quet` bỏ ứng viên đã có trong `da_quet` |
| 10 | `loc_can_quet` tôn trọng `gioi_han` |
| 11 | `loc_can_quet` giữ nguyên thứ tự đầu vào |
| 12 | `id_da_quet` chỉ lấy job `status == "ok"` |
| 13 | `lay_ung_vien` bỏ qua mục `bat=False` |
| 14 | `lay_ung_vien` một kênh lỗi không làm đứt các mục còn lại |
| 15 | `lay_ung_vien` link đơn lẻ không tách được ID → vào `danh_sach_loi` |
| 16 | `chay_giam_sat` không ứng viên → không tạo CSV |
| 17 | `chay_giam_sat` một video lỗi → vẫn quét hết các video còn lại |
| 18 | `chay_giam_sat` Sheets chưa cấu hình → `sheets_ok=False`, không ném lỗi |
| 19 | `BaoCao.tom_tat()` trả chuỗi khác rỗng kể cả khi mọi số đếm bằng 0 |
| 20 | Chạy lại lần hai ngay sau lần một → `quet_moi == 0` (chống quét trùng thật sự hoạt động) |

### Constraints
- KHÔNG gọi mạng. Dùng `lister` giả và `monkeypatch` cho `engine.scan_youtube`.
- KHÔNG ghi vào `ketqua/` thật — dùng `tmp_path`.
- Toàn bộ file test phải chạy dưới 2 giây.
- KHÔNG đánh dấu `@pytest.mark.slow` cho bất kỳ test nào trong file này.

### Definition of Done
- [ ] `python -m pytest -q` xanh
- [ ] Cả 20 tình huống đều có ít nhất 1 test phủ
- [ ] `python -m pytest tests/test_watch.py -q` chạy dưới 2 giây

---

## Sau khi xong cả 6 task

```
git add . && git commit -m "Phase B: giam sat tu dong"
git tag v1.1-giamsat
```

Kiểm tra thật (không thay được bằng test tự động):
1. Tạo `watchlist.json` với **1 link** video mà bạn biết chắc có chứa clip gốc.
2. Chạy `python cli.py watch` — phải tìm ra bằng chứng và tạo CSV.
3. Chạy **lại lần nữa** — phải báo `quet_moi = 0` (chống quét trùng hoạt động).
4. Ghép Task Scheduler, đặt chạy sau 5 phút để kiểm tra, xem file log trong `ketqua\`.