# EXECUTION PLAN — Tính năng: Xuất hồ sơ khiếu nại bản quyền

> Kế hoạch mẫu, đã chia nguyên tử. Copy từng khối `## TASK n` dán thẳng vào Codex.
> Làm **đúng thứ tự** — task sau phụ thuộc task trước.

**Mục tiêu:** từ kết quả quét, sinh file Markdown hồ sơ khiếu nại: liệt kê từng đoạn vi phạm, link nhảy tới đúng mốc, đối chiếu video gốc.

**Phân rã:**

| Task | File | Vai trò | Phụ thuộc |
|---|---|---|---|
| 1 | `dossier.py` | Data model + hàm thuần dựng dữ liệu hồ sơ | — |
| 2 | `dossier.py` | Hàm render Markdown | Task 1 |
| 3 | `engine.py` | Method `export_ho_so()` nối vào lõi | Task 1, 2 |
| 4 | `app.py` | Nút bấm trên giao diện | Task 3 |
| 5 | `tests/test_dossier.py` | Test đầy đủ | Task 1–3 |

---

## TASK 1: Data model và hàm dựng dữ liệu hồ sơ

### Target File
`dossier.py` — TẠO MỚI (thư mục gốc dự án)

### Context & Tech Stack
- Python 3.10+, chỉ dùng thư viện chuẩn (`dataclasses`, `datetime`, `typing`)
- Đọc trước: `engine.py` — class `ScanResult` (có `source_name`, `source_ref`, `source_id`, `duration_s`, `matches: list[Match]`, `status`, `note`) và class `Match` (có `clip`, `start_s`, `end_s`, `matched_s`, `clip_offset_s`, `hashes`, `ty_le`, `vung`, `start_hhmmss`, `end_hhmmss`)
- Ràng buộc dự án: `.github/copilot-instructions.md`

### Exact Input / Output
```python
from dataclasses import dataclass, field

@dataclass
class MucViPham:
    ten_clip_goc: str          # tên file clip gốc
    tieu_de_goc: str           # tiêu đề YouTube của clip gốc, "" nếu không có
    link_goc: str              # link video gốc, "" nếu không có
    tu_hhmmss: str             # mốc bắt đầu trong video vi phạm
    den_hhmmss: str            # mốc kết thúc
    link_moc: str              # link nhảy thẳng tới mốc vi phạm
    do_dai_giay: int           # độ dài đoạn khớp, làm tròn
    ty_le: float               # % vân tay khớp
    hashes: int

@dataclass
class HoSo:
    tieu_de_vi_pham: str
    link_vi_pham: str
    thoi_luong_hhmmss: str
    ngay_lap: str              # "YYYY-MM-DD"
    tong_giay_vi_pham: int     # tổng độ dài các đoạn vi phạm
    ty_le_video: float         # % thời lượng video vi phạm bị chiếm, làm tròn 1 số lẻ
    muc: list = field(default_factory=list)   # list[MucViPham]

def dung_ho_so(kq, meta: dict | None = None) -> HoSo:
    """Dựng HoSo từ một ScanResult. Hàm THUẦN — không đọc/ghi file."""
```
- `kq`: một `ScanResult`
- `meta`: dict do `Engine.clip_meta()` trả về, dạng `{ten_file: {"title": str, "url": str}}`; có thể `None`

### Step-by-step Implementation
1. Nếu `meta` là `None` thì gán `meta = {}`.
2. Với mỗi `m` trong `kq.matches`, tra `meta.get(m.clip, {})` lấy `title` và `url` (mặc định `""`).
3. Tính `link_moc` bằng cách gọi `Engine.link_moc(kq.source_id, kq.source_ref, m.start_s)` — import `from engine import Engine`.
4. Tạo `MucViPham`, `do_dai_giay = round(m.matched_s)`.
5. `tong_giay_vi_pham` = tổng `do_dai_giay` của mọi mục.
6. `ty_le_video` = `round(100 * tong_giay_vi_pham / kq.duration_s, 1)` nếu `duration_s > 0`, ngược lại `0.0`.
7. `ngay_lap` = `datetime.now().strftime("%Y-%m-%d")`.
8. `thoi_luong_hhmmss` = `hhmmss(kq.duration_s)` — import `from engine import hhmmss`.

### Edge Cases & Error Handling
| Tình huống | Hành vi bắt buộc |
|---|---|
| `kq.matches` rỗng | Trả `HoSo` với `muc=[]`, `tong_giay_vi_pham=0`, `ty_le_video=0.0`. KHÔNG ném lỗi |
| `kq.duration_s == 0` | `ty_le_video = 0.0`, không chia cho 0 |
| `kq.status != "ok"` | Vẫn trả `HoSo` rỗng, không ném lỗi |
| `meta` thiếu clip | `tieu_de_goc = ""`, `link_goc = ""` |
| `source_id` rỗng | `link_moc` lấy theo giá trị `Engine.link_moc` trả về (có thể là `""`) |

### Constraints
- KHÔNG đọc/ghi file trong task này. Lý do: hàm thuần thì test được không cần I/O.
- KHÔNG `import streamlit`.
- KHÔNG `print()`.

### Unit Test Criteria
```python
def test_ho_so_rong_khi_khong_co_ket_qua():
    from engine import ScanResult
    h = dung_ho_so(ScanResult(source_name="v", duration_s=3600))
    assert h.muc == [] and h.tong_giay_vi_pham == 0 and h.ty_le_video == 0.0

def test_khong_chia_cho_khong():
    from engine import ScanResult
    assert dung_ho_so(ScanResult(source_name="v", duration_s=0)).ty_le_video == 0.0
```

### Definition of Done
- [ ] `python -c "import dossier"` không lỗi
- [ ] `python -m pytest -q` xanh

---

## TASK 2: Hàm render Markdown

### Target File
`dossier.py` — THÊM hàm vào file đã tạo ở Task 1

### Context & Tech Stack
- Chỉ thư viện chuẩn. Dùng `HoSo`, `MucViPham` từ Task 1.

### Exact Input / Output
```python
def render_markdown(ho_so: HoSo) -> str:
    """Trả về nội dung Markdown hoàn chỉnh của hồ sơ. Không ghi file."""
```

### Step-by-step Implementation
1. Tiêu đề cấp 1: `# Hồ sơ khiếu nại bản quyền`.
2. Khối thông tin: tiêu đề video vi phạm, link, thời lượng, ngày lập, tổng số đoạn vi phạm, tổng thời gian vi phạm (định dạng `hhmmss` — import từ `engine`), tỷ lệ % video bị chiếm.
3. Nếu `ho_so.muc` rỗng: thêm dòng `_Không phát hiện đoạn vi phạm nào._` rồi trả về ngay.
4. Với mỗi mục, đánh số từ 1, in thành một mục cấp 2 `## Đoạn N` gồm: khoảng thời gian, link nhảy tới mốc, tên và link video gốc, độ dài đoạn, tỷ lệ khớp, số hash.
5. Cuối file thêm dòng ghi chú: bằng chứng sinh tự động bằng đối chiếu vân tay âm thanh.
6. Nối các phần bằng `"\n"`, trả về một chuỗi.

### Edge Cases & Error Handling
| Tình huống | Hành vi bắt buộc |
|---|---|
| `muc` rỗng | Vẫn trả chuỗi hợp lệ có phần thông tin chung |
| `link_goc` hoặc `link_moc` rỗng | In `—` thay vì để trống lửng |
| Tiêu đề chứa ký tự Markdown (`*`, `_`, `[`) | Giữ nguyên, không cần escape |

### Constraints
- KHÔNG ghi file. Lý do: tách render khỏi I/O để test bằng so chuỗi.
- KHÔNG dùng thư viện template ngoài.

### Unit Test Criteria
```python
def test_render_ho_so_rong_van_hop_le():
    from engine import ScanResult
    s = render_markdown(dung_ho_so(ScanResult(source_name="Video X", duration_s=3600)))
    assert "Hồ sơ khiếu nại" in s and "Không phát hiện" in s

def test_render_co_du_so_muc():
    # dựng ScanResult có 2 matches rồi kiểm tra "## Đoạn 1" và "## Đoạn 2" đều xuất hiện
    ...
```

### Definition of Done
- [ ] `python -m pytest -q` xanh
- [ ] Hàm trả `str`, không ghi ra đĩa

---

## TASK 3: Nối vào lõi Engine

### Target File
`engine.py` — THÊM method vào class `Engine`, đặt ngay sau method `export_csv`

### Context & Tech Stack
- Đọc trước: `engine.py` method `export_csv` (tham khảo cách tạo tên file và dùng `self.out_dir`), method `clip_meta`.

### Exact Input / Output
```python
def export_ho_so(self, ket: Iterable, ten_file: Optional[str] = None) -> list:
    """Xuất mỗi ScanResult thành một file .md. Trả về danh sách đường dẫn đã tạo."""
```

### Step-by-step Implementation
1. `import dossier` ở đầu file `engine.py` (khối import chuẩn).
2. `os.makedirs(self.out_dir, exist_ok=True)`.
3. `meta = self.clip_meta()` — gọi MỘT LẦN, dùng lại cho mọi kết quả.
4. Với mỗi `kq` trong `ket`: bỏ qua nếu `kq.status != "ok"` hoặc `not kq.matches`.
5. Dựng `ho_so = dossier.dung_ho_so(kq, meta)`, `noi_dung = dossier.render_markdown(ho_so)`.
6. Tên file: `hoso_<tên nguồn đã lọc ký tự cấm>_<YYYYmmdd_HHMMSS>.md` trong `self.out_dir`. Lọc ký tự bằng `channel.lam_sach_ten` (import sẵn).
7. Ghi bằng `encoding="utf-8"` trong khối `with`.
8. Trả về danh sách đường dẫn.

### Edge Cases & Error Handling
| Tình huống | Hành vi bắt buộc |
|---|---|
| `ket` rỗng | Trả `[]` |
| Mọi kết quả đều lỗi/không match | Trả `[]`, không tạo file rác |
| Trùng tên file | Dấu thời gian tới giây đã đủ; nếu vẫn trùng, thêm hậu tố `_2` |

### Constraints
- KHÔNG `import streamlit`.
- KHÔNG dùng `open()` trần — luôn dùng `with`. Lý do: Windows khoá file nếu handle không đóng (đã gây WinError 32 trước đây).

### Unit Test Criteria
```python
def test_export_ho_so_tao_dung_so_file(engine, tmp_path):
    engine.out_dir = str(tmp_path)
    # 1 kết quả có match + 1 kết quả rỗng -> phải tạo đúng 1 file
    ...
```

### Definition of Done
- [ ] `python -m pytest -q` xanh
- [ ] File `.md` sinh ra mở được, tiếng Việt hiển thị đúng

---

## TASK 4: Nút bấm trên giao diện

### Target File
`app.py` — SỬA hàm `bang_ket_qua(results)`

### Context & Tech Stack
- Streamlit. Đọc trước: `app.py` hàm `bang_ket_qua` (hiện có 3 cột `c1, c2, c3`).

### Exact Input / Output
Không đổi chữ ký hàm. Thêm một nút vào hàng nút hiện có.

### Step-by-step Implementation
1. Đổi `c1, c2, c3 = st.columns(3)` thành `c1, c2, c3, c4 = st.columns(4)`.
2. Trong `with c4:` thêm nút `st.button("📄 Xuất hồ sơ khiếu nại", width="stretch")`.
3. Khi bấm: gọi `eng.export_ho_so(results)` trong `try/except`.
4. Nếu trả về danh sách rỗng → `st.info("Không có kết quả nào đủ điều kiện lập hồ sơ.")`.
5. Nếu có file → `st.success(f"Đã tạo {len(fs)} hồ sơ trong ketqua\\")` và hiện `st.code("\n".join(fs))`.
6. Nếu exception → `st.error(str(e))`.

### Edge Cases & Error Handling
| Tình huống | Hành vi bắt buộc |
|---|---|
| `results` rỗng | Nút vẫn hiện nhưng báo info, không crash |
| Lỗi ghi file (hết dung lượng, không có quyền) | Bắt exception, `st.error`, không làm sập trang |

### Constraints
- KHÔNG đặt logic nghiệp vụ trong `app.py`. Lý do: lõi phải dùng được từ CLI. Chỉ gọi `eng.export_ho_so()`.

### Unit Test Criteria
```python
def test_giao_dien_khong_loi_render():
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_file("app.py", default_timeout=120).run()
    assert not at.exception
```

### Definition of Done
- [ ] Chạy `kiemtra.bat`, mục 3/3 báo `[OK] Giao dien sach`

---

## TASK 5: Bộ test đầy đủ

### Target File
`tests/test_dossier.py` — TẠO MỚI

### Context & Tech Stack
- pytest. Đọc trước: `tests/conftest.py` — có fixture `engine` và helper `M()` tạo `Match` giả.

### Step-by-step Implementation
Viết các test sau, mỗi test một `assert` chính:
1. `test_ho_so_rong` — `ScanResult` không match → `muc == []`, không ném lỗi.
2. `test_duration_bang_khong` — `duration_s=0` → `ty_le_video == 0.0`.
3. `test_tong_giay_dung` — 3 match mỗi cái 60s → `tong_giay_vi_pham == 180`.
4. `test_ty_le_video_dung` — `duration_s=3600`, tổng 180s → `ty_le_video == 5.0`.
5. `test_meta_thieu_clip` — `meta={}` → `tieu_de_goc == ""`, không `KeyError`.
6. `test_render_chua_du_so_muc` — 2 match → chuỗi chứa `## Đoạn 1` và `## Đoạn 2`.
7. `test_render_ho_so_rong` — chuỗi vẫn hợp lệ, chứa `Không phát hiện`.
8. `test_export_tao_file` — dùng fixture `engine`, `engine.out_dir = str(tmp_path)`, kiểm tra số file `.md` tạo ra.
9. `test_export_bo_qua_ket_qua_loi` — `ScanResult(status="error")` → không tạo file.
10. `test_file_md_doc_lai_dung_tieng_viet` — ghi rồi đọc lại bằng `encoding="utf-8"`, so chuỗi có dấu.

### Edge Cases & Error Handling
Không có — đây là file test.

### Constraints
- KHÔNG dùng audio thật. Lý do: test phải chạy dưới 1 giây.
- KHÔNG ghi ra `ketqua/` thật, luôn dùng `tmp_path`.

### Definition of Done
- [ ] `python -m pytest -q` xanh toàn bộ
- [ ] `python -m pytest tests/test_dossier.py -q` có ít nhất 10 test pass
