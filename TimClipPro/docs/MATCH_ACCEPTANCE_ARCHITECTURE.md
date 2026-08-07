# Kiến trúc tiêu chí chấp nhận ứng viên

File liên quan: `chap_nhan_khop.py`, `chan_doan_quet.py`, `engine.py::_chon_loc`.

---

## 1. Bài toán

Sau `_merge()`, mỗi ứng viên có bốn tín hiệu:

| Tín hiệu | Ý nghĩa | Nhược điểm khi dùng một mình |
|---|---|---|
| `hashes` | số hash khớp tuyệt đối | phụ thuộc độ dài clip gốc → loại oan clip ngắn |
| `ty_le` | % vân tay clip gốc khớp được | bỏ qua độ lớn → đoạn 9s có thể "phủ cao" |
| `matched_s` | độ dài đoạn khớp | không nói gì về chất lượng bằng chứng |
| mật độ = `hashes / matched_s` | bằng chứng trên mỗi giây | không nói gì về tổng lượng |

Luật cũ chỉ dùng một tín hiệu: `hashes >= min_hash_floor` (mặc định 1000).

---

## 2. Vì sao ngưỡng tuyệt đối một mình chưa đủ

Số hash một clip gốc sinh ra phụ thuộc độ dài và độ phong phú âm thanh của chính nó.
Đo trên kho thật:

| Kho | Số clip | Ít hash nhất | Clip < 1000 hash | Clip < 5000 hash |
|---|---:|---:|---:|---:|
| SML | 744 | 6.239 | 0 (0,0%) | 0 (0,0%) |
| Cory | 1.717 | 134 | 3 (0,2%) | 27 (1,6%) |
| duncanyounot | 139 | 17.146 | 0 (0,0%) | 0 (0,0%) |

Với 3 clip của kho Cory, ngay cả khi video vi phạm chứa **trọn vẹn** clip gốc và
khớp **100%** vân tay, ứng viên vẫn không thể đạt 1000 hash. Đó là false negative do
cấu trúc, không phải do bằng chứng yếu.

Quy mô nhỏ (0,2%) nên đây **không** phải nguyên nhân của 11 ca zero-match đang điều
tra — nhưng nó vẫn là lỗi đúng/sai, và sửa được mà không đánh đổi gì.

---

## 3. Chính sách hiện tại: hai bậc chấp nhận

```
Bậc A — bằng chứng tuyệt đối
    hashes >= min_hash_floor                       (mặc định 1000)

Bậc B — phủ vân tay cao (đường mới, dành cho clip gốc ngắn)
    ty_le      >= ty_le_chap_nhan                  (mặc định 60,0 %)
VÀ  matched_s  >= min_match_chap_nhan              (mặc định 20,0 giây)
VÀ  mật độ     >= mat_do_toi_thieu                 (mặc định 3,0 hash/giây)
```

Ứng viên đạt **một trong hai** bậc thì được nhận.

### Tính chất quan trọng: thay đổi CHỈ THÊM, không bao giờ BỚT

Bậc A giữ nguyên nguyên văn luật cũ. Bậc B là một nhánh `hoặc`. Vì vậy mọi ứng viên
luật cũ đã nhận thì luật mới vẫn nhận — không thể gây hồi quy trên kết quả đang
đúng. Rủi ro duy nhất cần canh là dương tính giả mới do bậc B, và đó là lý do bậc B
phải thoả cả ba điều kiện.

---

## 4. Vì sao bậc B cần đủ CẢ BA điều kiện

Mỗi điều kiện chặn đúng một kiểu dương tính giả đã đo được trên dữ liệu quét thật:

| Bỏ điều kiện nào | Lọt cái gì | Số đo thật |
|---|---|---|
| bỏ `matched_s` | nhạc hiệu/nhạc nền dùng chung | 133 hash / 8,8s / phủ 0,9% / **15,1 h/s** — mật độ cao nên bộ lọc mật độ KHÔNG chặn được |
| bỏ mật độ | trùng khớp thưa ngẫu nhiên | 309 hash / **578,6s** / phủ 0,5% / 0,53 h/s — dài nên bộ lọc độ dài KHÔNG chặn được |
| bỏ `ty_le` | mọi đoạn ngắn chất lượng tốt | — |

Hai ca đầu là số thật lấy từ log quét 11 video: chúng chứng minh rằng **không tín
hiệu đơn lẻ nào đủ**, phải kết hợp.

---

## 5. Số liệu hiệu chỉnh

Mốc tham chiếu, tất cả đo thật (xem `ZERO_MATCH_ROOT_CAUSE.md`):

| Ca | Hash | Dài | Mật độ | Phủ | Bậc B nhận? |
|---|---:|---:|---:|---:|---|
| bản reup thật (marathon 6,7h) | 15.173 | 786,8s | 19,3 h/s | — | (đã qua bậc A) |
| clip gốc nguyên bản | 4.610 | 263,6s | 17,5 h/s | 40,9% | (đã qua bậc A) |
| clip gốc nén Opus 32k | 2.352 | 263,7s | 8,9 h/s | 20,9% | (đã qua bậc A) |
| clip gốc ngắn khớp gần hết | 830 | 55,0s | 15,1 h/s | 92,2% | **nhận** |
| nhạc hiệu dùng chung | 133 | 8,8s | 15,1 h/s | 0,9% | loại (phủ + dài) |
| trùng khớp thưa | 309 | 578,6s | 0,53 h/s | 0,5% | loại (phủ + mật độ) |

Khoảng cách giữa vùng nhận và vùng loại rất rộng: phủ 92,2% so với 0,9%, tức gấp
100 lần. Ngưỡng 60% nằm giữa, không sát mép bên nào.

### Vì sao chọn đúng ba con số này

* `ty_le_chap_nhan = 60%` — dưới mức này thì "phủ cao" không còn là mô tả đúng. Mọi
  dương tính giả đo được đều ở mức phủ **dưới 1%**, nên biên an toàn rất lớn.
* `min_match_chap_nhan = 20s` — dài hơn hẳn nhạc hiệu dùng chung dài nhất đo được
  (11,4 giây) nhưng vẫn cho phép clip gốc ngắn lọt qua.
* `mat_do_toi_thieu = 3,0 hash/s` — thấp hơn nhiều so với ca nén nặng nhất còn dùng
  được (Opus 32k: 8,9 h/s) nhưng cao gấp gần 6 lần trùng khớp thưa (0,53 h/s).

Cả ba đều nằm trong `Config` nên chỉnh được mà không phải sửa code. Đặt
`ty_le_chap_nhan = 0` là tắt hẳn bậc B, quay về đúng hành vi cũ.

---

## 6. Những gì CỐ Ý không đổi

* **`min_hash_floor` giữ nguyên 1000.** Số đo cho thấy nó không phải nguyên nhân
  zero-match; hạ nó xuống chỉ tạo dương tính giả.
* **Không thêm điều kiện mật độ vào bậc A.** Ca "phủ thấp, hash cao" (ví dụ 1.200
  hash trải 2.000 giây) đúng là bằng chứng yếu, và về lý nên siết. Nhưng siết bậc A
  sẽ **bỏ bớt** kết quả người dùng đang nhận được — đó là thay đổi hành vi, không
  phải sửa lỗi, nên cần người dùng quyết định. Hiện mật độ được hiển thị trong chẩn
  đoán để theo dõi trước.
* **`_merge()` và thuật toán xếp hạng Top-N giữ nguyên.** `CLAUDE.md` ghi rõ chúng
  đã được hiệu chỉnh bằng thực nghiệm; điều tra này không đưa ra bằng chứng nào cần
  đổi chúng.

---

## 7. Hợp đồng dữ liệu giữ nguyên

* `ScanResult.so_dat_nguong` — vẫn là "số ứng viên đạt chuẩn TRƯỚC khi cắt còn
  Top-N". Chỉ định nghĩa "đạt" mở rộng thêm bậc B.
* `ScanResult.matches_loai` — vẫn giữ, vẫn là ứng viên bị loại; nay chẩn đoán còn
  kèm lý do loại cụ thể cho ứng viên mạnh nhất.
* `ScanResult.chan_doan` — trường **mới**, mặc định `None`. Mọi call site cũ không
  đụng tới nó vẫn chạy nguyên vẹn.
