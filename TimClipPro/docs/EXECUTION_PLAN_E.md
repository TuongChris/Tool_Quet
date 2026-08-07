# EXECUTION PLAN E — Độ chính xác thời điểm, tốc độ, và lưu cấu hình

> Đặt vào `docs/`. Copy từng khối `## TASK En` dán vào Codex (Copilot Chat, Agent).
> Làm đúng thứ tự. Sau mỗi task xanh: `git commit -m "Task En: ..."`.

## Nguyên nhân gốc của lệch thời điểm (đã đo bằng thực nghiệm)

Giấu một clip 120 giây vào đúng giây **900** của file dài, rồi quét:

| Giá trị | Kết quả |
|---|---|
| Mốc thật | 900.0s |
| Tool báo (`start_s`) | 908.5s → **lệch +8.5s** |
| `clip_offset_s` | 8.5s |
| `start_s − clip_offset_s` | **900.0s → lệch 0.0s** |

`start_s` hiện là **nơi vùng khớp bắt đầu**, không phải nơi clip bắt đầu. audfprint bỏ qua
phần đầu clip cho tới khi tìm được điểm mốc phổ đủ mạnh — phần bỏ qua đó chính là
`clip_offset_s`. Video vi phạm nén mạnh hoặc clip mở đầu bằng đoạn tĩnh/nhạc nhẹ thì
`clip_offset_s` càng lớn, đúng với khoảng 20–60 giây bạn quan sát.

**Giá trị `start_s − clip_offset_s` đã có sẵn trong code** — biến `align` trong `_merge()`,
hiện chỉ dùng để gộp trùng chứ chưa từng được báo ra.

## Kết quả đo về tham số `--shifts`

| shifts | Số hash | `start − offset` | Thời gian |
|---|---|---|---|
| 0 (hiện tại) | 1516 | 899.90 | 43.4s |
| **4** | **4392** | **900.00** | 48.2s |

Tăng **2.9 lần bằng chứng** và thời điểm chính xác tuyệt đối, chỉ tốn thêm **11% thời gian**.

---

## TASK E1: Sửa gốc rễ thời điểm bắt đầu

### Target File
`engine.py` — SỬA dataclass `Match`, method `_merge`; `bang_ngang.py` — SỬA `dinh_dang_doan`

### Nguyên nhân gốc
`Match.start_s` đang mang nghĩa "vùng khớp bắt đầu" nhưng được hiển thị như "clip bắt đầu".
Hai khái niệm khác nhau bị trộn làm một. Cách sửa đúng là **tách bạch hai khái niệm**, không
phải trừ đi một hằng số.

### Exact Input / Output
```python
# Match — THÊM hai trường, TẤT CẢ có mặc định
clip_bat_dau_s: float = 0.0   # thời điểm CLIP bắt đầu trong video dài (đã bù offset)
vung_khop_s: float = 0.0      # thời điểm VÙNG KHỚP bắt đầu (giá trị start_s cũ)

@property
def clip_bat_dau_hhmmss(self) -> str: ...
```

### Step-by-step Implementation
1. Trong `_merge()`, khi dựng `Match`:
   - `vung_khop_s = g["bat_dau"]` (giữ nguyên ý nghĩa cũ)
   - `clip_bat_dau_s = max(0.0, g["bat_dau"] - g["t_clip"])` — dùng `max` để không ra số âm
     khi clip bị cắt mất phần đầu.
   - `start_s = clip_bat_dau_s` — **đây là thay đổi cốt lõi**: mọi nơi hiển thị và tạo link
     nhảy mốc đều dùng thời điểm clip bắt đầu.
   - `end_s = clip_bat_dau_s + (g["khop"] + g["t_clip"])` — nới đầu vùng khớp về đúng điểm
     clip bắt đầu.
2. `_chon_loc` và mọi chỗ sắp xếp theo thời gian: dùng `start_s` (nay đã là `clip_bat_dau_s`).
3. `Engine.link_moc` không đổi — nó nhận giây truyền vào, và giá trị truyền vào nay đã đúng.
4. `bang_ngang.dinh_dang_doan`: thêm 3 giây đệm lùi khi tạo link nhảy mốc
   (`max(0, int(m.start_s) - 3)`). Lý do: YouTube nhảy tới mốc thường trễ vài giây do buffer,
   lùi lại 3 giây đảm bảo người xem thấy được điểm bắt đầu.
   Phần văn bản hiển thị vẫn dùng mốc chính xác, KHÔNG trừ 3.
5. `Engine.HEADER` (dạng dọc): đổi tên cột `"Xuất hiện từ"` thành `"Clip bắt đầu từ"` và thêm
   một cột `"Vùng khớp từ"` ngay sau. Cập nhật `to_rows` cho khớp số cột.
   **KHÔNG đổi `bang_ngang.HEADER_NGANG`** — bảng 34 cột của người dùng phải giữ nguyên.

### Edge Cases & Error Handling
| Tình huống | Hành vi bắt buộc |
|---|---|
| `t_clip > bat_dau` (clip bị cắt đầu) | `clip_bat_dau_s = 0.0`, không ra số âm |
| `t_clip == 0` | `clip_bat_dau_s == vung_khop_s`, không đổi gì |
| Match tạo thủ công trong test cũ | Vẫn chạy nhờ giá trị mặc định |
| Sắp xếp kết quả | Theo `start_s` mới, thứ tự có thể đổi so với trước — chấp nhận |

### Constraints
- KHÔNG đổi `bang_ngang.HEADER_NGANG` — sẽ làm lệch bảng Google Sheet đang dùng.
- KHÔNG xoá trường `clip_offset_s` — vẫn cần để biết clip bị cắt bao nhiêu ở đầu.
- KHÔNG trừ một hằng số cố định. Phải dùng đúng `t_clip` của từng kết quả.

### Unit Test Criteria
Tạo/bổ sung `tests/test_thoi_diem.py`:
```python
def test_clip_bat_dau_bu_dung_offset(engine):
    # dựng dict thô: bat_dau=908.5, t_clip=8.5 -> clip_bat_dau_s == 900.0
    ...

def test_khong_ra_so_am(engine):
    # bat_dau=5, t_clip=30 -> clip_bat_dau_s == 0.0
    ...

def test_offset_bang_0_thi_khong_doi(engine): ...

def test_link_moc_lui_3_giay():
    # dinh_dang_doan với start_s=850 -> link chứa t=847
    ...
```

### Definition of Done
- [ ] `python -m pytest -q` xanh
- [ ] `python kiem_ngang.py` vẫn `[OK] Đường ống 34 cột hoạt động`
- [ ] `python kiem_header.py` vẫn `[OK]`

---

## TASK E2: Tăng độ chính xác bằng subframe shifts

### Target File
`engine.py` — SỬA `Config`, `build_database`, `_match_chunks`

### Nguyên nhân gốc
audfprint mặc định `--shifts 0`: chỉ băm phổ tại một vị trí khung duy nhất. Khi video vi phạm
bị nén/dịch pha, các điểm mốc rơi lệch khung và bị bỏ sót. `--shifts 4` băm tại 4 vị trí lệch
nhau trong khung, bắt được nhiều điểm mốc hơn hẳn. Đo thực tế: hash tăng từ 1516 lên 4392,
thời điểm chính xác tuyệt đối, chỉ tốn thêm 11% thời gian.

### Exact Input / Output
```python
# Config — THÊM
shifts_kho: int = 4     # subframe shifts khi tạo kho vân tay (0 = tắt)
shifts_quet: int = 4    # subframe shifts khi quét video dài (0 = tắt)
```

### Step-by-step Implementation
1. Thêm hai trường vào `Config` với ghi chú: giá trị cao hơn = chính xác hơn nhưng chậm hơn
   và kho vân tay lớn hơn; đặt `0` để trở về hành vi cũ.
2. `build_database`: thêm `"--shifts", str(self.config.shifts_kho)` vào lệnh audfprint khi
   giá trị lớn hơn 0.
3. `_match_chunks`: thêm `"--shifts", str(self.config.shifts_quet)` tương tự.
4. Thêm cảnh báo trong `build_database`: nếu kho đã tồn tại và được tạo với `shifts` khác
   giá trị hiện tại, ghi một dòng vào kết quả trả về (khoá `canh_bao`) nhắc người dùng nên
   tạo lại kho để đồng bộ. Lưu giá trị `shifts` đã dùng vào đăng ký kho (`khos.json`,
   khoá `shifts`) để so sánh được.
5. Giao diện `app.py`: thêm hai ô chỉnh trong nhóm tham số, kèm chú thích ngắn về đánh đổi.

### Edge Cases & Error Handling
| Tình huống | Hành vi bắt buộc |
|---|---|
| `shifts = 0` | KHÔNG truyền cờ `--shifts`, hành vi y như trước |
| Kho cũ tạo với shifts khác | Vẫn quét được, nhưng phải cảnh báo rõ |
| `khos.json` chưa có khoá `shifts` | Coi như 0, không crash |
| Giá trị âm | Kẹp về 0 |

### Constraints
- KHÔNG tự động tạo lại kho vân tay. Kho 744 clip mất hàng chục phút — phải do người dùng quyết định.
- KHÔNG đặt `shifts` lớn hơn 4 làm mặc định. Lợi ích giảm dần trong khi kho phình nhanh.

### Unit Test Criteria
```python
def test_shifts_0_khong_truyen_co(engine):
    # kiểm lệnh dựng ra không chứa "--shifts"
    ...
def test_shifts_4_co_trong_lenh(engine): ...
def test_canh_bao_khi_kho_lech_shifts(engine): ...
```

### Definition of Done
- [ ] `python -m pytest -q` xanh
- [ ] Tạo lại kho với `shifts_kho=4` → số hash mỗi clip tăng rõ rệt so với trước

---

## TASK E3: Tăng tốc quét

### Target File
`engine.py` — SỬA `Config`, `_cut_chunks`, `_audfprint_cmd`

### Nguyên nhân gốc
Ba chỗ lãng phí: (a) `ncores` mặc định 1 trong khi máy nhiều nhân; (b) chồng lấn 600s trên
khúc 3600s nghĩa là **16.7% audio bị quét hai lần**; (c) mỗi khúc ghi ra file WAV 11 kHz rồi
audfprint đọc lại — vòng ghi/đọc đĩa không cần thiết.

### Exact Input / Output
```python
# Config — SỬA mặc định và THÊM
ncores: int = 0          # 0 = tự dò theo số nhân CPU
overlap_tu_dong: bool = True   # tự tính overlap theo clip dài nhất trong kho
```

### Step-by-step Implementation
1. `ncores = 0` nghĩa là tự dò: dùng `os.cpu_count() or 1`, trừ đi 1 để chừa cho hệ thống,
   kẹp trong khoảng 1–8. Tính trong một hàm riêng `so_nhan_nen_dung()` để test được.
2. `overlap_tu_dong`: khi bật, tính overlap = (thời lượng clip dài nhất trong kho) + 30 giây đệm,
   kẹp trong khoảng 120–1800 giây. Lấy thời lượng từ `clip_meta()` (khoá `duration`).
   Không có metadata → dùng `config.overlap_s` như cũ.
   Lý do: kho toàn clip 10–20 phút thì overlap 600s là dư; giảm được overlap là giảm thẳng
   phần trăm audio bị quét lặp.
3. Ghi log qua `progress` mức overlap thực tế đang dùng, để người dùng thấy được hiệu quả.
4. **KHÔNG** đổi cách cắt khúc sang đường ống (pipe). Ghi ra file WAV giúp `--list` chạy một
   lệnh audfprint duy nhất cho mọi khúc, và cho phép hủy giữa chừng. Đổi sang pipe sẽ phải gọi
   audfprint từng khúc một, mất nhiều hơn được.

### Edge Cases & Error Handling
| Tình huống | Hành vi bắt buộc |
|---|---|
| `os.cpu_count()` trả None | Dùng 1 |
| Máy 2 nhân | Dùng 1, không dùng 0 hay số âm |
| Máy 16 nhân | Kẹp về 8 |
| Kho rỗng / không có metadata | Dùng `config.overlap_s` |
| Clip dài nhất 25 phút | overlap = 1530s, vẫn nhỏ hơn `chunk_s` |
| overlap tính ra ≥ `chunk_s` | Kẹp về `chunk_s // 2` và cảnh báo |

### Constraints
- KHÔNG để overlap nhỏ hơn clip dài nhất — sẽ bỏ sót clip nằm vắt qua ranh giới hai khúc.
  Đây là ràng buộc đúng đắn quan trọng hơn tốc độ.
- KHÔNG dùng hết số nhân CPU. Máy phải còn dùng được việc khác.

### Unit Test Criteria
```python
def test_so_nhan_kep_trong_khoang(monkeypatch): ...
def test_overlap_tu_dong_theo_clip_dai_nhat(engine): ...
def test_overlap_khong_bao_gio_nho_hon_clip_dai_nhat(engine): ...
def test_kho_rong_dung_gia_tri_cau_hinh(engine): ...
```

### Definition of Done
- [ ] `python -m pytest -q` xanh
- [ ] `python -m pytest -m slow` xanh (độ chính xác không giảm)
- [ ] Quét cùng một file trước/sau task này: kết quả giống nhau, thời gian giảm

---

## TASK E4: Lưu cấu hình bền vững

### Target File
`cau_hinh.py` — TẠO MỚI; SỬA `app.py`, `engine.py`

### Nguyên nhân gốc
Mọi tham số sống trong `st.session_state` và `Config` khởi tạo mới mỗi lần chạy. Không có
lớp lưu trữ nào cho **tuỳ chọn người dùng** — khác với `khos.json` (dữ liệu hệ thống).
Đóng tool là mất sạch: tham số quét, link Google Sheet, định dạng đẩy, thư mục kho.

### Exact Input / Output
```python
TEN_FILE = "cau_hinh.json"

def doc_cau_hinh(data_dir: str) -> dict:
    """Đọc cấu hình người dùng. Chưa có -> trả {} (không phải lỗi)."""

def ghi_cau_hinh(data_dir: str, du_lieu: dict) -> None:
    """Ghi cấu hình. Dùng luu_tru.ghi_json_an_toan."""

def ap_vao_config(cfg, du_lieu: dict) -> list:
    """
    Áp các khoá trong `du_lieu` vào đối tượng Config.
    Chỉ nhận khoá có thật trong Config và ĐÚNG KIỂU. Trả về danh sách khoá bị bỏ qua.
    """

def lay_tu_config(cfg) -> dict:
    """Trích toàn bộ trường của Config thành dict để lưu."""
```

### Step-by-step Implementation
1. Dùng `luu_tru.ghi_json_an_toan` / `doc_json_an_toan` — KHÔNG viết lại cơ chế ghi file.
2. `ap_vao_config` kiểm tra kiểu bằng `type(getattr(cfg, k))`; sai kiểu hoặc khoá lạ thì bỏ qua
   và ghi vào danh sách trả về. Lý do: file cấu hình có thể do người dùng sửa tay hoặc còn sót
   từ phiên bản cũ — không được để nó làm sập tool.
3. `Engine.__init__`: sau khi tạo `self.config`, đọc `cau_hinh.json` trong `data_dir` và áp vào.
   Bọc `try/except` — lỗi cấu hình KHÔNG được ngăn tool khởi động, chỉ ghi vào
   `self.canh_bao_khoi_dong`.
4. `Engine` thêm method `luu_cau_hinh(self, them: dict | None = None)`: gộp
   `lay_tu_config(self.config)` với `them` rồi ghi xuống đĩa.
5. `app.py`:
   - Khi khởi tạo `st.session_state`, đọc các khoá giao diện từ cấu hình đã lưu:
     `sheet_link`, `sheet_auto`, `sheet_dang_ngang`, `kho_dir`, `thu_muc_quet_gan_nhat`.
   - Thêm nút **"💾 Lưu cấu hình"** trong thanh bên, gọi
     `eng.luu_cau_hinh({...các khoá giao diện...})` rồi báo thành công.
   - Thêm nút **"↩️ Khôi phục mặc định"**: xoá file cấu hình và tạo lại `Config()` mặc định.
6. Ghi rõ trong chú thích: `cau_hinh.json` KHÔNG chứa `google_key.json` hay bất kỳ bí mật nào —
   chỉ chứa link sheet và tham số. Thêm `cau_hinh.json` vào `.gitignore`.

### Edge Cases & Error Handling
| Tình huống | Hành vi bắt buộc |
|---|---|
| File chưa tồn tại | Dùng mặc định, KHÔNG tạo file cho tới khi người dùng bấm Lưu |
| File hỏng | Dùng mặc định + ghi cảnh báo, tool VẪN khởi động |
| Khoá lạ từ phiên bản cũ | Bỏ qua khoá đó, áp các khoá còn lại |
| Sai kiểu (chuỗi thay vì số) | Bỏ qua khoá đó, ghi vào danh sách bị bỏ |
| `overlap_s >= chunk_s` sau khi áp | Gọi `cfg.validate()`, lỗi thì quay về mặc định |
| Bấm Khôi phục mặc định | Xoá file, áp `Config()` mới, không cần khởi động lại |

### Constraints
- KHÔNG lưu bất kỳ khoá bí mật nào vào `cau_hinh.json`.
- KHÔNG để lỗi cấu hình ngăn tool khởi động.
- KHÔNG tự động ghi cấu hình sau mỗi thay đổi nhỏ — chỉ ghi khi người dùng bấm nút. Lý do:
  ghi liên tục theo mỗi lần Streamlit vẽ lại màn hình sẽ mòn ổ SSD và gây tranh chấp file.

### Unit Test Criteria
Tạo `tests/test_cau_hinh.py`:
```python
def test_luu_roi_doc_lai_giu_nguyen(tmp_path): ...
def test_khoa_la_bi_bo_qua(tmp_path): ...
def test_sai_kieu_bi_bo_qua(tmp_path): ...
def test_file_hong_van_khoi_dong_duoc(tmp_path): ...
def test_khong_luu_khoa_bi_mat(tmp_path): ...
def test_khoi_phuc_mac_dinh(tmp_path): ...
```

### Definition of Done
- [ ] `python -m pytest -q` xanh
- [ ] Chạy tool, đổi tham số, bấm Lưu, tắt, mở lại → tham số còn nguyên
- [ ] `cau_hinh.json` có trong `.gitignore`

---

## TASK E5: Ba điểm còn thiếu từ audit

### Target File
`watch.py`, `engine.py`, `CLAUDE.md`

### Sửa 1 — Gộp về một khoá duy nhất
`watch.py` dùng `giamsat.lock`, `engine.py` dùng `kho.lock`. Hai khoá độc lập nên nạp kho và
quét giám sát có thể chạy đồng thời, cùng đụng `db.pklz` — trên Windows dễ hỏng lượt nạp kho.
Đổi cả hai sang dùng chung `data/tool.lock`, giữ nguyên tham số `ten` khác nhau để thông báo
lỗi vẫn cho biết thao tác nào đang giữ khoá.

### Sửa 2 — Ghi lại kết quả từng phần khi bị dừng
Hiện `chay_giam_sat` chỉ xuất CSV/Sheets sau khi vòng lặp kết thúc. Nếu tiến trình bị kill
(không phải dừng có kiểm soát), toàn bộ kết quả của các video đã quét xong bị mất.
Thêm tuỳ chọn `Config.ghi_tung_phan: bool = True`: sau **mỗi** video quét xong, đẩy ngay dòng
kết quả của video đó lên Google Sheets (nếu có link). CSV vẫn ghi một lần ở cuối.
Lý do chọn Sheets mà không phải CSV: `append` lên Sheets là thao tác nối, an toàn khi lặp lại;
còn ghi lại CSV nhiều lần sẽ tạo nhiều file rác.

### Sửa 3 — Ghi quy ước vào CLAUDE.md
Thêm mục "Quy ước khoá": mọi thao tác nặng dùng chung `data/tool.lock`; nếu sau này cần nhiều
khoá thì phải quy định thứ tự lấy khoá cố định để tránh kẹt chéo.
Thêm mục "Ý nghĩa các trường thời gian trong Match": `clip_bat_dau_s` là thời điểm clip bắt đầu
(dùng để hiển thị và tạo link), `vung_khop_s` là nơi vùng khớp bắt đầu, `clip_offset_s` là phần
đầu clip bị bỏ qua. Ghi rõ để không ai trộn lẫn lại lần nữa.

### Edge Cases & Error Handling
| Tình huống | Hành vi bắt buộc |
|---|---|
| Ghi từng phần thất bại | Ghi vào `bao_cao.loi`, lượt quét VẪN tiếp tục |
| `ghi_tung_phan=False` | Hành vi y như hiện tại |
| Không có link Sheets | Bỏ qua ghi từng phần, không lỗi |
| Ghi từng phần rồi ghi lại ở cuối | KHÔNG được ghi trùng — đánh dấu dòng đã đẩy |

### Constraints
- KHÔNG đổi lớp `KhoaTienTrinh`.
- KHÔNG ghi trùng dòng lên Google Sheets.

### Unit Test Criteria
```python
def test_mot_khoa_chan_ca_hai_thao_tac(engine, tmp_path): ...
def test_ghi_tung_phan_khong_trung_dong(engine, monkeypatch): ...
def test_ghi_tung_phan_that_bai_van_tiep_tuc(engine, monkeypatch): ...
```

### Definition of Done
- [ ] `python -m pytest -q` xanh
- [ ] Giữ `tool.lock` rồi chạy cả `watch` lẫn `build_database` → cả hai đều báo bận

---

## Sau khi xong cả 5 task

```
git add . && git commit -m "Phase E: chinh xac thoi diem, toc do, luu cau hinh"
git tag v2.1
```

### Nghiệm thu quan trọng nhất

Quét lại **đúng video 35 tiếng đã quét trước đây** (audio còn trong `data/downloads/`,
không phải tải lại), rồi mở CSV mới và bấm vào link nhảy mốc. So với kết quả cũ:
mốc mới phải sớm hơn mốc cũ đúng bằng `clip_offset_s`, và khi bấm vào phải rơi **ngay
đầu clip gốc** thay vì giữa clip.

Đây là phép thử duy nhất chứng minh vấn đề bạn báo đã được giải quyết thật.