# EXECUTION PLAN D — Củng cố nền tảng cho vận hành tự động dài hạn

> Đặt vào `docs/`. Copy từng khối `## TASK Dn` dán vào Codex (Copilot Chat, Agent).
> Làm đúng thứ tự. Sau mỗi task xanh: `git commit -m "Task Dn: ..."`.

## Triết lý của Phase này

Không vá triệu chứng. Mỗi task xử lý một **nguyên nhân gốc** và để lại một thành phần
dùng lại được, có test, thay vì một đoạn `if` chắp vá. Sau Phase D, hệ thống phải chịu
được: máy tắt đột ngột giữa lúc ghi file, hai lượt chạy chồng nhau, ổ cứng đầy dần,
người dùng cần dừng giữa chừng, và lịch sử phình to sau hàng nghìn lượt quét.

| Task | Nguyên nhân gốc | Thành phần để lại |
|---|---|---|
| D1 | Ghi file không nguyên tử → mất dữ liệu vĩnh viễn | `luu_tru.py` |
| D2 | Không có khái niệm "một tiến trình duy nhất" | `khoa.py` |
| D3 | Dữ liệu tạm không có vòng đời | `don_dep.py` |
| D4 | Huỷ không phải khái niệm xuyên suốt hệ thống | `dung_lai.py` |
| D5 | Lọc dữ liệu trong Python thay vì trong CSDL | index + truy vấn SQL |
| D6 | Script `.bat` làm việc của Python | ghi nhật ký phía Python |

---

## TASK D1: Ghi file nguyên tử — chống mất dữ liệu vĩnh viễn

### Target File
`luu_tru.py` — TẠO MỚI; sau đó SỬA `engine.py`, `channel.py`, `watch.py` để dùng nó

### Nguyên nhân gốc
Cả ba file cấu hình (`khos.json`, `clips_meta.json`, `watchlist.json`) đều ghi bằng
`open(w)` + `json.dump`. Nếu tiến trình chết giữa lúc ghi, file bị cụt. Tệ hơn:
`Engine._doc_khos()` bắt mọi exception rồi trả về dict rỗng **mà không báo gì**, nên
thao tác kế tiếp sẽ ghi đè bằng dữ liệu rỗng — đăng ký kho mất vĩnh viễn dù các file
`.pklz` vẫn còn trên đĩa. `clips_meta.json` (744 mục) và `watchlist.json` cùng rủi ro.

### Exact Input / Output
```python
class LoiDuLieu(Exception):
    """File tồn tại nhưng không đọc được — KHÁC với file chưa tồn tại."""

def ghi_json_an_toan(path: str, du_lieu, giu_ban_sao: bool = True) -> None:
    """Ghi JSON theo kiểu nguyên tử: hoặc thành công trọn vẹn, hoặc file cũ còn nguyên."""

def doc_json_an_toan(path: str, mac_dinh=None, tu_phuc_hoi: bool = True):
    """
    Đọc JSON. Không tồn tại -> trả `mac_dinh`.
    Hỏng mà có bản sao dùng được -> phục hồi từ bản sao và trả dữ liệu đó.
    Hỏng mà không phục hồi được -> ném LoiDuLieu (KHÔNG âm thầm trả rỗng).
    """
```

### Step-by-step Implementation
1. `ghi_json_an_toan`:
   - Tạo thư mục cha nếu chưa có.
   - Nếu `giu_ban_sao` và file đích đang tồn tại: sao chép sang `<path>.bak` (ghi đè bản sao cũ).
   - Ghi ra file tạm `<path>.tmp` trong CÙNG thư mục (bắt buộc cùng ổ đĩa để `os.replace` nguyên tử).
   - Trong khối `with`: `json.dump(..., ensure_ascii=False, indent=2)`, sau đó `f.flush()` rồi
     `os.fsync(f.fileno())`. Thiếu `fsync` thì dữ liệu có thể còn nằm trong bộ đệm hệ điều hành
     khi mất điện.
   - `os.replace(tmp, path)` — thao tác nguyên tử trên cả Windows lẫn Linux.
   - Có lỗi ở bất kỳ bước nào: xoá file tạm rồi ném lại exception.
2. `doc_json_an_toan`:
   - File không tồn tại → trả `mac_dinh` (đây là trạng thái bình thường, không phải lỗi).
   - Đọc được → trả dữ liệu.
   - Đọc lỗi và `tu_phuc_hoi` và `<path>.bak` đọc được → ghi đè `path` bằng nội dung bản sao,
     trả dữ liệu đó.
   - Đọc lỗi và không phục hồi được → đổi tên file hỏng thành `<path>.hong.<timestamp>`
     (GIỮ LẠI để cứu thủ công, tuyệt đối không xoá) rồi ném `LoiDuLieu` kèm đường dẫn cả hai file.
3. Thay thế trong `engine.py`: `_doc_khos` dùng `doc_json_an_toan(self.kho_file, {"dang_dung": "", "danh_sach": []})`,
   `_ghi_khos` dùng `ghi_json_an_toan`. Bắt `LoiDuLieu` ở `_init_kho` và đưa thông báo vào một
   thuộc tính `self.canh_bao_khoi_dong: list` để giao diện hiển thị được.
4. Thay thế tương tự trong `channel.py` (`load_meta`/`save_meta`) và `watch.py`
   (`doc_watchlist`/`ghi_watchlist`).
5. `channel.py::_mark_done` ghi nối vào `downloaded.txt` — giữ nguyên cách nối (append an toàn
   sẵn rồi), NHƯNG `sua_archive()` ghi đè toàn bộ file thì phải chuyển sang cùng kiểu nguyên tử:
   ghi `.tmp` rồi `os.replace`.

### Edge Cases & Error Handling
| Tình huống | Hành vi bắt buộc |
|---|---|
| File chưa tồn tại | `doc_json_an_toan` trả `mac_dinh`, KHÔNG ném lỗi, KHÔNG tạo file |
| File rỗng (0 byte) | Coi như hỏng: thử phục hồi từ `.bak` |
| File hỏng, có `.bak` tốt | Phục hồi, trả dữ liệu bản sao, KHÔNG ném lỗi |
| File hỏng, `.bak` cũng hỏng | Đổi tên file hỏng, ném `LoiDuLieu` |
| Ghi thất bại giữa chừng | File cũ CÒN NGUYÊN, file tạm bị xoá |
| Ổ đĩa đầy khi ghi | Ném exception, file cũ còn nguyên |
| Nội dung tiếng Việt có dấu | Đọc lại phải nguyên vẹn (`ensure_ascii=False`) |
| Ghi cùng lúc từ hai luồng | `os.replace` nguyên tử nên file không bao giờ ở trạng thái cụt |

### Constraints
- KHÔNG dùng `shutil.move` để thay `os.replace` — `move` không nguyên tử khi đích đã tồn tại.
- File tạm PHẢI nằm cùng thư mục với file đích. Lý do: `os.replace` chỉ nguyên tử trong cùng hệ thống tệp.
- KHÔNG bao giờ xoá file hỏng — luôn đổi tên giữ lại.
- KHÔNG để `doc_json_an_toan` âm thầm trả rỗng khi file hỏng. Đây chính là lỗi gốc cần diệt.
- KHÔNG `import streamlit`, KHÔNG `print()`.

### Unit Test Criteria
Tạo `tests/test_luu_tru.py`:
```python
def test_ghi_that_bai_thi_file_cu_con_nguyen(tmp_path, monkeypatch):
    # ghi thành công lần 1, rồi monkeypatch json.dump ném lỗi ở lần 2
    # -> đọc lại vẫn ra dữ liệu lần 1
    ...

def test_file_hong_phuc_hoi_tu_ban_sao(tmp_path):
    # ghi 2 lần (tạo .bak), làm hỏng file chính -> đọc ra dữ liệu bản sao
    ...

def test_file_hong_khong_cuu_duoc_thi_nem_loi_va_giu_file(tmp_path):
    # cả file chính lẫn .bak đều hỏng -> ném LoiDuLieu, file .hong.* phải tồn tại
    ...

def test_khong_am_tham_tra_rong(tmp_path):
    # KHÔNG được trả {} khi file hỏng — phải ném LoiDuLieu
    ...
```

### Definition of Done
- [ ] `python -m pytest -q` xanh
- [ ] `grep -n "json.dump" *.py` chỉ còn kết quả trong `luu_tru.py`
- [ ] `python kiem_ngang.py` vẫn `[OK]`

---

## TASK D2: Khoá đơn tiến trình ở mức hệ điều hành

### Target File
`khoa.py` — TẠO MỚI; SỬA `watch.py::chay_giam_sat` và `engine.py::build_database`

### Nguyên nhân gốc
Task Scheduler có thể khởi động lượt mới khi lượt trước chưa xong (video 30 tiếng dễ chạy quá
24 giờ). Hai tiến trình cùng ghi `db.pklz` và `lichsu.db` sẽ làm hỏng dữ liệu.
`Engine._giu_khoa()` đã được viết nhưng **chưa từng được gọi ở đâu** — mã chết, và nó chỉ là
`threading.Lock` nên không chặn được hai tiến trình riêng biệt.

### Exact Input / Output
```python
class DangChayRoi(Exception):
    """Đã có tiến trình khác đang giữ khoá."""

class KhoaTienTrinh:
    def __init__(self, path: str, ten: str = ""): ...
    def __enter__(self) -> "KhoaTienTrinh": ...   # lấy khoá, thất bại -> DangChayRoi
    def __exit__(self, *a) -> None: ...           # nhả khoá
    @property
    def thong_tin_chu_khoa(self) -> str: ...      # mô tả tiến trình đang giữ, để báo lỗi
```

### Step-by-step Implementation
1. Dùng **khoá cấp hệ điều hành**, KHÔNG dùng file PID. Lý do: PID bị tái sử dụng, và file PID
   mồ côi khi tiến trình bị kill sẽ chặn vĩnh viễn. Khoá OS được hệ điều hành tự nhả khi tiến
   trình chết, kể cả bị kill hay mất điện — không bao giờ có khoá mồ côi.
2. Windows: `import msvcrt`, mở file bằng `open(path, "a+")`, gọi
   `msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)`. Thất bại → `OSError` → ném `DangChayRoi`.
3. POSIX: `import fcntl`, `fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)`.
4. Chọn nhánh bằng `sys.platform.startswith("win")`. Đặt hai nhánh trong hàm riêng để test được.
5. Sau khi lấy được khoá, ghi vào file: PID, thời điểm, `ten` — chỉ để CON NGƯỜI đọc khi gỡ lỗi,
   KHÔNG dùng làm cơ chế khoá.
6. `__exit__`: nhả khoá rồi đóng file. Không xoá file khoá (xoá dễ tạo tranh chấp).
7. Nối vào `watch.chay_giam_sat`: bọc toàn bộ thân hàm trong
   `with KhoaTienTrinh(os.path.join(engine.data_dir, "giamsat.lock"), "giam sat")`.
   Bắt `DangChayRoi` → trả `BaoCao` với `loi` chứa thông báo rõ ràng, KHÔNG ném ra ngoài
   (Task Scheduler cần mã thoát có ý nghĩa, không phải traceback).
8. Nối vào `engine.build_database` tương tự, dùng file khoá `data/kho.lock`.
9. XOÁ method `Engine._giu_khoa()` và thuộc tính `self._lock` nếu không còn chỗ nào dùng.

### Edge Cases & Error Handling
| Tình huống | Hành vi bắt buộc |
|---|---|
| Không có tiến trình nào đang chạy | Lấy khoá thành công |
| Tiến trình khác đang giữ | Ném `DangChayRoi` kèm nội dung file khoá |
| Tiến trình cũ bị kill/mất điện | Khoá đã được OS nhả — lượt mới lấy được bình thường |
| File khoá bị xoá thủ công lúc đang chạy | Không được crash |
| Thư mục `data/` chưa tồn tại | Tự tạo |
| Lồng hai khoá khác tên | Cả hai cùng hoạt động độc lập |

### Constraints
- KHÔNG dùng file PID làm cơ chế khoá.
- KHÔNG dùng `threading.Lock` — không chặn được liên tiến trình.
- KHÔNG để `DangChayRoi` thoát ra khỏi `chay_giam_sat`.
- KHÔNG xoá file khoá trong `__exit__`.

### Unit Test Criteria
Tạo `tests/test_khoa.py`:
```python
def test_lay_va_nha_khoa(tmp_path):
    with KhoaTienTrinh(str(tmp_path / "a.lock")): pass
    with KhoaTienTrinh(str(tmp_path / "a.lock")): pass   # lấy lại được

def test_khoa_thu_hai_bi_tu_choi(tmp_path):
    with KhoaTienTrinh(str(tmp_path / "a.lock")):
        with pytest.raises(DangChayRoi):
            with KhoaTienTrinh(str(tmp_path / "a.lock")): pass

def test_chay_giam_sat_khi_dang_khoa_tra_bao_cao_loi(engine, tmp_path):
    # giữ khoá rồi gọi chay_giam_sat -> phải trả BaoCao có loi, KHÔNG ném exception
    ...
```

### Definition of Done
- [ ] `python -m pytest -q` xanh
- [ ] `grep -n "_giu_khoa" *.py` không còn kết quả
- [ ] Mở 2 cửa sổ chạy `python cli.py watch` cùng lúc → cửa sổ thứ hai báo lỗi rõ ràng và thoát

---

## TASK D3: Vòng đời dữ liệu tạm — kho đệm có ngân sách

### Target File
`don_dep.py` — TẠO MỚI; SỬA `watch.py::chay_giam_sat` và `engine.py::Config`

### Nguyên nhân gốc
`data/downloads/` chỉ tăng, không bao giờ giảm. Chạy hằng đêm 20 video × 1–2 GB
= 20–40 GB mỗi đêm, tích luỹ vô hạn. Xoá theo tuổi đơn thuần là vá: một đêm nhiều video
có thể lấp đầy ổ trước khi tới hạn tuổi. Gốc rễ là hệ thống chưa có khái niệm
**kho đệm có ngân sách** — bị chặn đồng thời bởi dung lượng VÀ tuổi.

### Exact Input / Output
```python
@dataclass
class MucDem:
    path: str
    kich_thuoc: int      # byte
    lan_dung_cuoi: float # timestamp

def chon_can_xoa(muc: list, max_byte: int, max_giay: float,
                 bay_gio: float | None = None) -> list:
    """
    Hàm THUẦN: quyết định file nào cần xoá. Không chạm đĩa.
    Trả về danh sách MucDem cần xoá.
    """

def don_kho_dem(thu_muc: str, max_gb: float = 20.0, max_ngay: int = 7,
                thuc_hien: bool = True) -> dict:
    """
    Quét thư mục, quyết định, rồi xoá. thuc_hien=False = chỉ xem trước.
    Trả về {"tong_file", "tong_gb", "xoa_file", "xoa_gb", "loi": [...]}
    """
```

### Step-by-step Implementation
1. `chon_can_xoa` (thuần, dễ test tuyệt đối):
   - Bước 1 — theo tuổi: mọi mục có `bay_gio - lan_dung_cuoi > max_giay` đều vào danh sách xoá.
   - Bước 2 — theo ngân sách: với các mục CÒN LẠI, nếu tổng dung lượng vẫn vượt `max_byte`
     thì xoá tiếp theo thứ tự **cũ nhất trước** cho tới khi lọt ngân sách.
   - `max_byte <= 0` hoặc `max_giay <= 0` nghĩa là KHÔNG giới hạn theo chiều đó.
   - `bay_gio` mặc định `time.time()`; cho truyền vào để test không phụ thuộc đồng hồ thật.
2. `don_kho_dem`: liệt kê file trong thư mục (không đệ quy), dùng `st_mtime` làm `lan_dung_cuoi`,
   gọi `chon_can_xoa`, rồi xoá nếu `thuc_hien`. Lỗi xoá một file → ghi vào `loi`, tiếp tục file kế.
3. `Config` thêm: `dem_max_gb: float = 20.0`, `dem_max_ngay: int = 7`.
   Ghi chú rõ: đặt `0` để tắt giới hạn tương ứng.
4. `chay_giam_sat`: sau khi quét xong toàn bộ (kể cả khi có lỗi), gọi `don_kho_dem` trên
   `engine.dl_dir`. Đưa kết quả vào `BaoCao` qua hai trường mới `da_don_file: int` và
   `da_don_gb: float`, hiển thị trong `tom_tat()`.
5. Thêm lệnh CLI `python cli.py dondep [--xem-truoc]` để chạy tay và xem trước khi xoá thật.

### Edge Cases & Error Handling
| Tình huống | Hành vi bắt buộc |
|---|---|
| Thư mục không tồn tại | Trả số đếm 0, KHÔNG tạo thư mục, không lỗi |
| Thư mục rỗng | Trả 0, không lỗi |
| Tổng dung lượng dưới ngân sách và mọi file còn mới | Không xoá gì |
| Một file đang bị tiến trình khác mở (Windows khoá) | Ghi vào `loi`, tiếp tục file khác |
| `max_gb = 0` | Bỏ qua ràng buộc dung lượng |
| `max_ngay = 0` | Bỏ qua ràng buộc tuổi |
| Cả hai bằng 0 | Không xoá gì cả |
| `thuc_hien=False` | KHÔNG xoá file nào, vẫn trả đúng số liệu dự kiến |

### Constraints
- `chon_can_xoa` PHẢI thuần: không I/O, không gọi `time.time()` trực tiếp khi có tham số `bay_gio`.
  Lý do: hàm này quyết định xoá dữ liệu — phải test được tuyệt đối chắc chắn.
- KHÔNG đệ quy vào thư mục con. Lý do: chỉ dọn kho đệm, tránh xoá nhầm thứ khác.
- KHÔNG bao giờ chạm tới `db.pklz`, `lichsu.db`, `khos.json`, hay thư mục `ketqua/`.
- KHÔNG xoá file có đuôi `.part` hoặc `.ytdl` (đang tải dở).

### Unit Test Criteria
Tạo `tests/test_don_dep.py`:
```python
def test_xoa_theo_tuoi(): ...
def test_xoa_theo_ngan_sach_cu_nhat_truoc(): ...
def test_ca_hai_rang_buoc_cung_luc(): ...
def test_gioi_han_bang_0_thi_khong_xoa(): ...
def test_xem_truoc_khong_xoa_file_that(tmp_path): ...
def test_khong_xoa_file_dang_tai_do(tmp_path): ...
```

### Definition of Done
- [ ] `python -m pytest -q` xanh
- [ ] `python cli.py dondep --xem-truoc` chạy được, không xoá gì
- [ ] `chon_can_xoa` không có lệnh I/O nào

---

## TASK D4: Huỷ có kiểm soát, xuyên suốt hệ thống

### Target File
`dung_lai.py` — TẠO MỚI; SỬA `watch.py`, `cli.py`

### Nguyên nhân gốc
`watch.py` không có một dòng nào nhắc tới huỷ. Muốn dừng một lượt quét đang chạy chỉ còn cách
tắt tiến trình — có thể để lại `.pklz` ghi dở. Gốc rễ: huỷ không phải khái niệm xuyên suốt,
mỗi module tự xoay xở.

### Exact Input / Output
```python
class YeuCauDung:
    """Gom mọi nguồn tín hiệu dừng về một chỗ."""
    def __init__(self, engine=None, file_dung: str = ""): ...
    def bat_tin_hieu(self) -> None:
        """Đăng ký bắt Ctrl+C (SIGINT) và SIGTERM."""
    def can_dung(self) -> bool:
        """True nếu: đã nhận tín hiệu, HOẶC file dừng tồn tại, HOẶC engine.cancel_event bật."""
    def dat(self) -> None: ...
    def don_file_dung(self) -> None:
        """Xoá file dừng nếu có, để lượt sau không bị dừng oan."""
```

### Step-by-step Implementation
1. `can_dung()` kiểm ba nguồn theo thứ tự rẻ trước: cờ nội bộ → `engine.cancel_event.is_set()`
   → `os.path.exists(file_dung)`. Chỉ kiểm file khi `file_dung` khác rỗng.
2. `bat_tin_hieu()`: `signal.signal(signal.SIGINT, handler)` và `SIGTERM` nếu nền tảng có.
   Handler chỉ ĐẶT CỜ, tuyệt đối không thoát chương trình. Lý do: phải để vòng lặp tự dừng
   ở điểm an toàn rồi mới lưu kết quả — thoát ngay sẽ mất công đã làm.
   Lần nhấn Ctrl+C **thứ hai** thì cho thoát ngay (`raise KeyboardInterrupt`) để người dùng
   không bị kẹt.
3. `chay_giam_sat` thêm tham số `dung_lai=None`. Kiểm `dung_lai.can_dung()` **giữa các video**
   (không cắt ngang một video đang quét dở — dở dang gây file rác). Khi phát hiện: dừng vòng lặp,
   ghi vào `bao_cao.loi` một dòng nêu rõ đã dừng theo yêu cầu và số video còn lại chưa quét,
   rồi **vẫn tiếp tục** xuất CSV và đẩy Sheets cho phần đã quét.
4. Truyền `engine.cancel_event` xuống `scan_youtube` như hiện tại, để video đang tải/quét
   cũng dừng được (Engine đã hỗ trợ sẵn).
5. `cli.py` lệnh `watch`: khởi tạo `YeuCauDung(engine, os.path.join(engine.data_dir, "DUNG"))`,
   gọi `bat_tin_hieu()`, truyền vào `chay_giam_sat`, và gọi `don_file_dung()` khi kết thúc.
6. Thêm lệnh `python cli.py dung` — chỉ tạo file `data/DUNG` rồi in thông báo. Đây là cách dừng
   lượt chạy nền mà không cần tìm và kill tiến trình.

### Edge Cases & Error Handling
| Tình huống | Hành vi bắt buộc |
|---|---|
| Không có yêu cầu dừng | Chạy hết bình thường |
| Dừng giữa chừng | Kết quả đã quét VẪN được lưu CSV và Sheets |
| Dừng trước video đầu tiên | `quet_moi = 0`, không tạo CSV, không lỗi |
| File `DUNG` còn sót từ lượt trước | `don_file_dung()` ở cuối mỗi lượt phải xoá nó |
| Nhấn Ctrl+C hai lần | Lần hai thoát ngay |
| Nền tảng không có `SIGTERM` | Bỏ qua êm, không crash |
| `dung_lai=None` | Hoạt động y như trước, không huỷ được |

### Constraints
- KHÔNG cắt ngang giữa lúc đang quét một video. Lý do: `.pklz` và file tạm ghi dở gây hỏng dữ liệu.
- Handler tín hiệu KHÔNG được gọi `sys.exit()` ở lần đầu.
- KHÔNG bỏ qua việc xuất kết quả khi bị dừng.

### Unit Test Criteria
Tạo `tests/test_dung_lai.py`:
```python
def test_file_dung_kich_hoat(tmp_path): ...
def test_dung_giua_chung_van_xuat_ket_qua(engine, monkeypatch): ...
def test_don_file_dung_sau_khi_xong(tmp_path): ...
def test_dung_lai_none_van_chay_binh_thuong(engine): ...
```

### Definition of Done
- [ ] `python -m pytest -q` xanh
- [ ] `python cli.py dung` tạo file `data/DUNG`
- [ ] Chạy `watch` rồi nhấn Ctrl+C → dừng gọn, vẫn in tóm tắt

---

## TASK D5: Truy vấn lịch sử có chỉ mục

### Target File
`engine.py` — THÊM chỉ mục và method; `watch.py` — SỬA `id_da_quet`

### Nguyên nhân gốc
`watch.id_da_quet()` gọi `engine.list_jobs(limit=100000)` rồi lọc trong Python. Mỗi lượt quét
nạp toàn bộ lịch sử thành đối tượng Python chỉ để lấy ra một tập ID. Bảng `jobs` cũng không có
chỉ mục trên `source_id`. Sau vài nghìn lượt, mỗi lần chạy tốn thêm thời gian và bộ nhớ vô ích.
Gốc rễ: làm việc của CSDL bằng Python.

### Exact Input / Output
```python
# engine.py — THÊM method vào Engine
def ids_da_quet(self, chi_thanh_cong: bool = True) -> set:
    """Trả về tập source_id đã quét, truy vấn thẳng trong SQLite."""
```

### Step-by-step Implementation
1. Trong `_init_sqlite`, thêm sau phần tạo bảng:
   ```sql
   CREATE INDEX IF NOT EXISTS idx_jobs_source_id ON jobs(source_id);
   CREATE INDEX IF NOT EXISTS idx_matches_job_id ON matches(job_id);
   ```
   Dùng `CREATE INDEX IF NOT EXISTS` nên chạy được trên CSDL đã có sẵn, không cần di trú.
2. `ids_da_quet`: một câu truy vấn duy nhất
   `SELECT DISTINCT source_id FROM jobs WHERE source_id IS NOT NULL AND source_id != ''`
   cộng thêm `AND status = 'ok'` khi `chi_thanh_cong`. Trả về `set`.
3. `watch.id_da_quet(engine, chi_thanh_cong)`: nếu `engine` có `ids_da_quet` thì gọi nó;
   không có thì giữ cách cũ. Lý do giữ nhánh dự phòng: các test hiện tại dùng engine giả.
4. KHÔNG đổi chữ ký `watch.id_da_quet` — nhiều test đang gọi nó.

### Edge Cases & Error Handling
| Tình huống | Hành vi bắt buộc |
|---|---|
| CSDL trống | Trả `set()` |
| CSDL cũ chưa có chỉ mục | `CREATE INDEX IF NOT EXISTS` tự tạo, không lỗi |
| `source_id` là NULL hoặc chuỗi rỗng | Bị loại khỏi kết quả |
| Có job lỗi cùng `source_id` với job thành công | `chi_thanh_cong=True` vẫn tính là đã quét |
| `engine` là đối tượng giả trong test | Nhánh dự phòng vẫn chạy |

### Constraints
- KHÔNG đổi schema bảng (không `ALTER TABLE`), chỉ thêm chỉ mục.
- KHÔNG đổi chữ ký `watch.id_da_quet`.
- KHÔNG nạp toàn bộ lịch sử vào bộ nhớ nữa.

### Unit Test Criteria
Bổ sung `tests/test_engine_core.py`:
```python
def test_ids_da_quet_loc_dung(engine): ...
def test_ids_da_quet_bo_source_id_rong(engine): ...
def test_chi_muc_duoc_tao(engine):
    # truy vấn sqlite_master kiểm tra idx_jobs_source_id tồn tại
    ...
```

### Definition of Done
- [ ] `python -m pytest -q` xanh
- [ ] `watch.py` không còn gọi `list_jobs(limit=100000)`

---

## TASK D6: Nhật ký do Python quản lý

### Target File
`nhat_ky.py` — TẠO MỚI; SỬA `cli.py` và `GiamSat.bat`

### Nguyên nhân gốc
`GiamSat.bat` đặt tên file log bằng cách cắt chuỗi `%date%` theo vị trí cố định — phụ thuộc
định dạng ngày của vùng, đổi cài đặt là tên file thành rác. Log cũng không bao giờ được dọn.
Gốc rễ: script `.bat` làm việc logic mà Python nên làm.

### Exact Input / Output
```python
def mo_nhat_ky(thu_muc: str, ten: str = "giamsat", giu_ngay: int = 30) -> str:
    """
    Bật ghi song song ra màn hình VÀ file <thu_muc>/<ten>_YYYY-MM-DD.log.
    Dọn các file log cùng tiền tố cũ hơn `giu_ngay`. Trả về đường dẫn file log.
    """

def dong_nhat_ky() -> None:
    """Khôi phục stdout/stderr về ban đầu."""
```

### Step-by-step Implementation
1. Tên file dùng `datetime.now().strftime("%Y-%m-%d")` — độc lập hoàn toàn với cài đặt vùng.
2. Ghi song song: thay `sys.stdout` và `sys.stderr` bằng một lớp nhỏ có `write()` và `flush()`
   ghi ra cả hai đích. Mở file với `encoding="utf-8"` và chế độ nối. Lý do ghi cả màn hình:
   chạy tay vẫn thấy tiến độ, chạy nền vẫn có log.
3. Dọn log: quét file khớp `<ten>_*.log` trong thư mục, đọc ngày từ tên, xoá file cũ hơn
   `giu_ngay`. Tên không đọc được ngày → BỎ QUA, không xoá (an toàn hơn xoá nhầm).
4. `cli.py`: thêm cờ `--log` cho lệnh `watch`. Có cờ thì gọi `mo_nhat_ky(engine.out_dir)`
   ở đầu và `dong_nhat_ky()` trong khối `finally`.
5. `GiamSat.bat`: bỏ toàn bộ phần đổi hướng `>>` và cắt chuỗi ngày. Chỉ còn gọi
   `%PY% cli.py watch --log --sheet "..."` và truyền lại `%errorlevel%`.
   File `.bat` vẫn không được có `pause`.

### Edge Cases & Error Handling
| Tình huống | Hành vi bắt buộc |
|---|---|
| Thư mục log chưa tồn tại | Tự tạo |
| Chạy hai lần trong ngày | Nối vào cùng file, không ghi đè |
| Không mở được file log | In cảnh báo ra màn hình, chương trình VẪN chạy tiếp |
| File log tên lạ | Bỏ qua khi dọn |
| `giu_ngay = 0` | Không dọn gì |
| Ngoại lệ giữa chừng | `dong_nhat_ky()` trong `finally` vẫn được gọi |

### Constraints
- KHÔNG đặt tên file dựa vào `%date%` của Windows.
- KHÔNG nuốt output khỏi màn hình — phải ghi song song.
- KHÔNG để lỗi ghi log làm sập lượt quét.
- `GiamSat.bat` KHÔNG được có `pause`.

### Unit Test Criteria
Tạo `tests/test_nhat_ky.py`:
```python
def test_ghi_song_song_ra_file_va_man_hinh(tmp_path, capsys): ...
def test_don_log_cu(tmp_path): ...
def test_khong_xoa_file_ten_la(tmp_path): ...
def test_giu_ngay_0_khong_don(tmp_path): ...
```

### Definition of Done
- [ ] `python -m pytest -q` xanh
- [ ] `python cli.py watch --log` tạo file `ketqua/giamsat_YYYY-MM-DD.log`
- [ ] `GiamSat.bat` không còn chuỗi `%date:`

---

## Sau khi xong cả 6 task

```
git add . && git commit -m "Phase D: cung co nen tang van hanh"
git tag v2.0
```

### Nghiệm thu thật (không thay được bằng test)

1. **Ghi nguyên tử:** chạy `python cli.py watch`, giữa chừng tắt nguồn máy (hoặc kill tiến trình).
   Bật lại, chạy `python -c "from engine import Engine; print([k['ten'] for k in Engine().list_khos()])"`
   — danh sách kho phải còn nguyên.
2. **Khoá:** mở hai cửa sổ chạy `python cli.py watch` cùng lúc — cửa sổ thứ hai phải báo lỗi rõ ràng.
3. **Dọn kho đệm:** `python cli.py dondep --xem-truoc` xem số liệu trước khi cho xoá thật.
4. **Dừng:** chạy `watch`, mở cửa sổ khác gõ `python cli.py dung` — lượt quét phải dừng gọn
   và vẫn xuất kết quả phần đã quét.
5. **Nhật ký:** chạy `GiamSat.bat`, kiểm file `ketqua/giamsat_YYYY-MM-DD.log`.