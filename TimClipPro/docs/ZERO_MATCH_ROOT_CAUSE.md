# Điều tra "quét xong 0 đoạn" trên 11 video

Ngày điều tra: 2026-08-07. Toàn bộ số liệu dưới đây đo trên máy thật, kho thật,
audio đã tải sẵn trong `data/downloads`. Không có số nào là ước lượng.

---

## 1. Triệu chứng

Người dùng quét 11 link YouTube, tin rằng chúng chứa nội dung reup từ kho vân tay
SML. Kết quả: tải xong, quét tới 100%, báo hoàn tất, **0 đoạn, 0 clip gốc**.

Lịch sử `data/lichsu.db` xác nhận: job 365–375 đều `status=ok`, `n_matches=0`.

---

## 2. Kết luận ngắn gọn

**Cả 11 video đều là ÂM TÍNH ĐÚNG.** Chúng không chứa bản reup nào của kho SML.

Lỗi thật của phần mềm không nằm ở khâu phát hiện, mà ở khâu **giải thích**: một kết
quả 0 đoạn đúng đắn trông y hệt một con bug, nên người dùng không có cách nào phân
biệt. Ngoài ra quá trình điều tra phát hiện thêm **hai khiếm khuyết thật** trong
khâu phát hiện, không gây ra 11 ca này nhưng có gây mất kết quả ở tình huống khác.

---

## 3. Giả thuyết ban đầu đã bị bác bỏ bằng số đo

Giả thuyết được nêu khi giao việc là `min_hash_floor = 1000` cao hơn tổng số hash
của nhiều clip gốc, nên ứng viên không bao giờ đạt nổi ngưỡng (bẫy toán học).

Đo phân phối hash của toàn bộ kho đang dùng:

| Kho | Số clip | Ít hash nhất | p50 | Nhiều nhất | Clip < 1000 hash |
|---|---:|---:|---:|---:|---|
| **SML** (đang dùng) | 744 | **6.239** | 16.281 | 57.651 | **0 (0,0%)** |
| Cory | 1.717 | 134 | 47.015 | 1.010.617 | 3 (0,2%) |
| duncanyounot | 139 | 17.146 | 29.328 | 385.001 | 0 (0,0%) |

Kho SML — chính là kho được dùng cho 11 video này — có clip ít hash nhất là 6.239.
Ngưỡng 1000 luôn trong tầm với. **Bẫy toán học không tồn tại ở đây.**

(Con số minh hoạ khi giao việc — "1717 clip, 684 clip dưới 1000 hash (39,8%)" — khớp
số clip của kho Cory nhưng phân phối thực tế là 3 clip, tức 0,2%.)

Kiểm tra sức khoẻ kho: `D:\ClipGocSML` có 744 file `.opus`, kho vân tay có đúng 744
clip. Không có clip nào 0 hash. Không thiếu, không thừa.

---

## 4. Bảng phễu phát hiện — 11 video

Đo bằng cách chạy lại pipeline trên audio đã tải, đếm số ứng viên còn sống sau từng
tầng.

| Video | Thời lượng | Khúc | Dòng khớp thô | Đọc được | Qua lọc thô | Gộp | Đạt ngưỡng | Chọn |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| OVTMo5bhtN0 | 3554s | 2 | 200 | 200 | 198 | 198 | 0 | 0 |
| wcX1prb6Uqo | 3663s | 2 | 200 | 200 | 195 | 195 | 0 | 0 |
| 5reWzdUi7Gc | 3498s | 2 | 300 | 300 | 300 | 300 | 0 | 0 |
| kBBdgkZWrM4 | 3660s | 2 | 200 | 200 | 198 | 198 | 0 | 0 |
| qUrJv94OzJE | 3611s | 2 | 300 | 300 | 297 | 262 | 0 | 0 |
| sljyQs9RAhE | 3513s | 2 | 300 | 300 | 296 | 296 | 0 | 0 |
| 7BOIM2BsudM | 3804s | 2 | 200 | 200 | 157 | 157 | 0 | 0 |
| JKIvZyIvG6E | 3648s | 2 | 400 | 400 | 380 | 380 | 0 | 0 |
| CDljbMzOdjU | 3834s | 2 | 202 | 202 | 199 | 199 | 0 | 0 |
| 0wQxfJNGV_s | 3334s | 1 | 200 | 200 | 200 | 200 | 0 | 0 |
| X1e8K8OG6-Q | 3807s | 2 | 302 | 302 | 204 | 204 | 0 | 0 |

Đọc bảng này:

* **audfprint hoạt động bình thường** — mọi video đều ra 200–400 dòng khớp.
* **Parser không mất gì** — cột "đọc được" luôn bằng cột "dòng khớp thô". 100%.
* Kết quả mất **ở tầng chấp nhận cuối cùng**, không phải ở audfprint hay parser.

Ứng viên mạnh nhất của từng video:

| Video | Hash | Phủ vân tay | Dài | Mật độ |
|---|---:|---:|---:|---:|
| OVTMo5bhtN0 | 116 | 0,8% | 11,2s | 10,4 h/s |
| wcX1prb6Uqo | 109 | 0,7% | 10,6s | 10,3 h/s |
| 5reWzdUi7Gc | 108 | 0,8% | 10,8s | 10,0 h/s |
| kBBdgkZWrM4 | 117 | 0,8% | 9,6s | 12,2 h/s |
| qUrJv94OzJE | 309 | 0,5% | 578,6s | **0,5 h/s** |
| sljyQs9RAhE | 133 | 0,9% | 8,8s | 15,1 h/s |
| 7BOIM2BsudM | 108 | 0,6% | 9,9s | 10,9 h/s |
| JKIvZyIvG6E | 107 | 0,6% | 12,7s | 8,4 h/s |
| CDljbMzOdjU | 123 | 0,9% | 11,1s | 11,1 h/s |
| 0wQxfJNGV_s | 98 | 0,7% | 10,4s | 9,4 h/s |
| X1e8K8OG6-Q | 117 | 0,8% | 11,1s | 10,5 h/s |

**Phủ vân tay 0,5–0,9% ở cả 11 video.** Một bản reup thật phủ 20–100%.

---

## 5. Bằng chứng quyết định: các dòng khớp đó là NHẠC HIỆU DÙNG CHUNG

Phân tích chi tiết output thô của `sljyQs9RAhE` (300 dòng khớp):

```
số clip gốc khác nhau bị chạm: 159
các cụm dày nhất:
  @1607s  n=100  clip khác nhau=100  hash max=106  dài nhất 11,2s
  @1844s  n= 96  clip khác nhau= 96  hash max=133  dài nhất 11,2s
  @3501s  n=100  clip khác nhau=100  hash max=112  dài nhất 10,0s
```

Ba mốc thời gian, mỗi mốc khớp với khoảng **100 clip gốc KHÁC NHAU cùng lúc**, và
trong mỗi clip gốc vị trí khớp đều rơi vào giây thứ ~640–800, tức **gần cuối phim**.

Đó là chữ ký của một đoạn âm thanh dùng chung — nhạc kết/nhạc hiệu xuất hiện ở cuối
mọi phim SML. Một bản reup thật chỉ khớp với **một** clip gốc, liên tục hàng phút.

### Đối chứng dương tính

Cùng kho, cùng tham số, video `n4Ca9SmTfi0` (marathon 6,7 giờ):

```
đoạn khớp dài nhất: 786,8 s     (13 phút liên tục)
hash lớn nhất:      15.173
mật độ:             19,3 hash/s
```

Hệ thống **phát hiện được bản reup thật** khi có bản reup thật. Chênh lệch giữa
786,8s/15.173 hash và 11,2s/133 hash không phải chuyện hiệu chỉnh ngưỡng.

### Kho có chứa đúng bản gốc không?

Tiêu đề 11 video đều dạng `SML Movie: <tên> (Parody Marathon)`. Tra kho:

| Tên trong tiêu đề | Có trong kho SML? |
|---|---|
| Jeffy Goes Surfing | không |
| Jeffy and Junior Go to Space | không |
| Jeffy The Ghostbuster | không |
| Jeffy's Pet Possum | không |
| Jeffy's Other Family | không |
| Jeffy Finds Bigfoot | không |
| Jeffy's Summer Vacation | không |
| Junior's Obsession | chỉ có "Obsession" (tên khác) |
| Jeffy's Firework Disaster | chỉ có "The Firework Problem!" (tên khác) |
| Jeffy's Diddy Prime | chỉ có "Jeffy Goes To A Diddy Party" (tên khác) |

Không tiêu đề nào tồn tại trong kho. Kết hợp với chữ "Parody" trong tiêu đề và việc
chỉ nhạc hiệu khớp được, đây là các video **parody lồng tiếng lại**, không phải reup.

---

## 6. Đã loại trừ giả thuyết né tránh bằng đổi tốc độ / cao độ

Vì người dùng tin chắc đây là reup, giả thuyết mạnh nhất còn lại là audio bị đổi tốc
độ để né nhận dạng. Đã đo hai chiều.

### Chiều 1 — quét chính video nghi vấn ở nhiều tốc độ

Cắt đoạn 600–900s của `sljyQs9RAhE`, sinh biến thể `atempo` 0,94 / 0,96 / 0,98 /
1,02 / 1,04 / 1,06 rồi so khớp lại: **tất cả đều 0 dòng khớp**. Bản gốc chưa biến
đổi cũng chỉ ra 2 dòng, dài nhất 1,6 giây.

### Chiều 2 — ngưỡng chịu đựng thật của audfprint

Lấy một clip gốc CÓ THẬT trong kho (`It happened again`, 11.277 hash), cắt 300 giây,
biến đổi rồi so khớp ngược lại với kho:

| Biến đổi | Số dòng | Đoạn dài nhất | Hash | Phủ |
|---|---:|---:|---:|---:|
| gốc | 1 | 263,6s | 4.610 | 40,9% |
| AAC 64k | 1 | 265,8s | 3.607 | 32,0% |
| Opus 32k | 1 | 263,7s | 2.352 | 20,9% |
| +3 dB | 1 | 265,7s | 3.904 | 34,6% |
| −6 dB | 1 | 263,2s | 4.433 | 39,3% |
| lowpass 3 kHz | 1 | 263,6s | 4.137 | 36,7% |
| highpass 300 Hz | 1 | 263,6s | 4.390 | 38,9% |
| **tempo 0,995** | 20 | **21,0s** | 323 | 2,9% |
| **tempo 1,005** | 23 | **22,5s** | 346 | 3,1% |
| tempo 0,99 | 41 | 7,0s | 154 | 1,4% |
| tempo 1,01 | 39 | 10,6s | 169 | 1,5% |
| tempo 1,02 | 62 | 4,5s | 65 | 0,6% |
| tempo 1,04 | 16 | 1,5s | 28 | 0,2% |
| pitch 1,01 | 11 | 6,4s | 45 | 0,4% |
| pitch 1,04 | 0 | — | — | 0% |
| dịch 1 nửa cung | 0 | — | — | 0% |

Hai kết luận:

1. **Nén lại, đổi âm lượng, lọc tần số: hoàn toàn vô hại.** Đây là các biến đổi
   thường gặp khi reup, và hệ thống chịu được tốt.
2. **Đổi tốc độ là điểm mù nghiêm trọng.** Chỉ 0,5% đã làm một đoạn khớp 263 giây vỡ
   thành mảnh vụn dài nhất 21 giây. Từ 4% trở lên coi như mất trắng.

Điểm mù này **không gây ra 11 ca đang xét** (đã quét ở nhiều tốc độ, vẫn 0), nhưng
là giới hạn thật của phương pháp, cần ghi nhận. Xem mục 9.

---

## 7. Hai khiếm khuyết THẬT phát hiện trong quá trình điều tra

### 7.1 `--max-matches` cắt cụt theo THỜI GIAN chứ không theo ĐỘ MẠNH

Trong `audfprint_match.py`, thứ tự thao tác là:

```python
results = results[(-results[:, 1]).argsort(),]   # sắp theo độ mạnh, mạnh nhất trước
if self.sort_by_time:
    rslts = rslts[(-rslts[:, 2]).argsort(), :]   # SẮP LẠI theo align time
return rslts[:self.max_returns, :]                # RỒI MỚI cắt bớt
```

Vì `_match_chunks()` truyền `--sortbytime`, phần bị cắt bỏ là phần có align time nhỏ
nhất — tức **các đoạn nằm sớm trong khúc**, bất kể chúng mạnh hay yếu.

Đo trên khúc đầu của `sljyQs9RAhE` (một khúc, 4 cấu hình):

| Cấu hình | Số dòng | Vùng thời gian thấy được |
|---|---:|---|
| `--max-matches 200 --sortbytime` (cũ) | 200 | t = [1482 … 1847]s |
| `--max-matches 20000 --sortbytime` | 408 | t = [1482 … 3505]s |
| `--max-matches 200` (không sortbytime) | 200 | t = [1607 … 3505]s |
| `--max-matches 20000` (không sortbytime) | 408 | t = [1482 … 3505]s |

Cấu hình production **bỏ sót 207 dòng khớp**, trong đó có nguyên hai cụm ở t≈3313s
và t≈3502s. Và **mọi khúc của cả 11 video đều chạm trần 200**, nên việc cắt cụt xảy
ra ở mọi lượt quét chứ không phải ca hiếm.

Với 11 video này, sửa lỗi trên không đổi kết luận (dòng bị mất mạnh nhất chỉ 98 hash
/ 10,0 giây). Nhưng trên video ghép nhiều clip gốc thì đây là mất bằng chứng thật.

**Đã sửa:** bỏ `--sortbytime`. Phần bị cắt giờ là phần yếu nhất, đúng ngữ nghĩa mong
muốn. Thứ tự thời gian vẫn đảm bảo vì `_merge()` tự sắp theo `start_s` ở cuối.
Ngoài ra chẩn đoán nay đếm số khúc chạm trần và cảnh báo cho người dùng.

### 7.2 Ngưỡng tuyệt đối một mình loại oan clip gốc ngắn

Đúng như lo ngại khi giao việc, chỉ là quy mô nhỏ hơn nhiều: kho Cory có 3/1717 clip
tổng hash dưới 1000, và 27 clip dưới 5000 (`min_hash_strong`). Với 3 clip đó, dù
video vi phạm chứa trọn vẹn clip gốc và khớp 100% vân tay thì ứng viên vẫn bị loại.

**Đã sửa:** thêm đường chấp nhận thứ hai theo chỉ số chuẩn hoá. Xem
[MATCH_ACCEPTANCE_ARCHITECTURE.md](MATCH_ACCEPTANCE_ARCHITECTURE.md).

---

## 8. Phân nhóm nguyên nhân

| Nhóm | Số video | Nguyên nhân |
|---|---:|---|
| Âm tính đúng — không có nội dung reup trong kho | 11 | Video parody lồng tiếng lại; chỉ nhạc hiệu dùng chung khớp được |
| Lỗi parser | 0 | Đọc được 100% dòng khớp ở cả 11 video |
| Sai kho / kho hỏng | 0 | Kho SML đúng, 744/744 clip có vân tay |
| Lỗi tải audio | 0 | Thời lượng tải về khớp metadata YouTube |
| Ngưỡng chặn oan | 0 (trong 11 ca này) | Clip ít hash nhất của kho SML là 6.239 |

Không có video nào trong 11 ca cần "hạ ngưỡng để ra kết quả". Hạ ngưỡng chỉ biến
đoạn nhạc hiệu 9 giây thành "bằng chứng vi phạm" — chính là điều đã xảy ra ở job 364
(một match 126 hash / 10 giây được báo cáo khi ngưỡng bị hạ tay).

---

## 9. Kiểm chứng sau khi sửa — 11 video

Chạy lại toàn bộ 11 video bằng code sau khi sửa, trên audio đã tải sẵn, không ghi lịch
sử, không đẩy Sheets, không đụng kho vân tay.

| Video | Kết quả | Giai đoạn mất | Dòng khớp thô | Gộp | Khúc chạm trần | Ứng viên mạnh nhất bị loại |
|---|---:|---|---:|---:|---:|---|
| OVTMo5bhtN0 | 0 | `khong_dat_chap_nhan` | 200 | 200 | 1 | 117 hash / phủ 0,8% / 12,1s / 9,7 h/s |
| wcX1prb6Uqo | 0 | `khong_dat_chap_nhan` | 200 | 196 | 1 | 109 hash / phủ 0,7% / 10,6s / 10,3 h/s |
| 5reWzdUi7Gc | 0 | `khong_dat_chap_nhan` | 300 | 272 | 1 | 111 hash / phủ 0,9% / 9,6s / 11,6 h/s |
| kBBdgkZWrM4 | 0 | `khong_dat_chap_nhan` | 200 | 200 | 1 | 117 hash / phủ 0,8% / 10,8s / 10,8 h/s |
| qUrJv94OzJE | 0 | `khong_dat_chap_nhan` | 300 | 299 | 1 | 359 hash / phủ 0,6% / 30,3s / 11,9 h/s |
| sljyQs9RAhE | 0 | `khong_dat_chap_nhan` | 300 | 276 | 1 | 133 hash / phủ 0,9% / 8,8s / 15,1 h/s |
| 7BOIM2BsudM | 0 | `khong_dat_chap_nhan` | 200 | 194 | 1 | 108 hash / phủ 0,6% / 9,9s / 10,9 h/s |
| JKIvZyIvG6E | 0 | `khong_dat_chap_nhan` | 400 | 391 | 2 | 130 hash / phủ 0,8% / 9,6s / 13,5 h/s |
| CDljbMzOdjU | 0 | `khong_dat_chap_nhan` | 202 | 201 | 1 | 123 hash / phủ 0,9% / 11,1s / 11,1 h/s |
| 0wQxfJNGV_s | 0 | `khong_dat_chap_nhan` | 200 | 200 | 1 | 150 hash / phủ 0,8% / 13,9s / 10,8 h/s |
| X1e8K8OG6-Q | 0 | `khong_dat_chap_nhan` | 302 | 282 | 1 | 117 hash / phủ 0,8% / 11,1s / 10,5 h/s |

Ba điều đáng chú ý:

1. **Vẫn đúng 0/11.** Tiêu chí chấp nhận mới không tạo dương tính giả nào — đúng như
   thiết kế, vì phủ vân tay cao nhất chỉ 0,9% trong khi bậc B đòi 60%.
2. **Mọi video đều nói được mất ở tầng nào** kèm ứng viên mạnh nhất và lý do loại cụ
   thể. Trước đây tất cả chỉ hiện "Không tìm thấy clip gốc nào."
3. **Mọi video đều chạm trần `--max-matches`** (cột "khúc chạm trần"). Nay có cảnh báo
   hiển thị cho người dùng. Sau khi bỏ `--sortbytime`, phần giữ lại là phần mạnh nhất
   — thấy rõ ở `qUrJv94OzJE`: ứng viên mạnh nhất tăng từ 309 lên **359 hash**.

Lưu ý: các số thời gian của lượt kiểm chứng này bị tranh chấp CPU với một lượt quét
thật đang chạy song song trên máy, nên không dùng làm mốc hiệu năng.

## 10. Việc còn lại / giới hạn đã biết

1. ~~**Điểm mù đổi tốc độ.**~~ — **ĐÃ BỊT** ngày 2026-08-07. Không dùng quét mù nhiều
   tốc độ (vừa đắt vừa không đủ chính xác) mà **đọc tốc độ từ độ trôi align** của
   chính các mảnh khớp đã có: sai số ≤0,05%, tốn 0 giây so khớp thêm. Chỉ chạy khi
   lượt quét thường không ra ứng viên nào đạt chuẩn. Kiểm chứng đầu-cuối: video bị
   tăng tốc 3% từ **0 kết quả** thành tìm ra đúng clip với 6.365 hash. Chi tiết:
   [DA_TOC_DO.md](DA_TOC_DO.md).

   Với 11 video này, bù tốc độ **không đổi kết luận**: cả 4 lượt bù cao độ đều cho
   **0 dòng khớp**, xác nhận thêm rằng chúng không chứa nội dung SML ở bất kỳ tốc độ
   hay cao độ nào trong vùng đã thử.
2. **Trần `--max-matches`.** Đã hết cắt nhầm phần mạnh, nhưng trần 200/khúc vẫn còn.
   Chẩn đoán nay cảnh báo khi chạm trần để người dùng tự nâng khi cần soi kỹ.
3. **Video bị thay toàn bộ tiếng** vẫn nằm ngoài tầm của vân tay âm thanh — đã ghi
   trong `CLAUDE.md` từ trước. 11 video này chính là ví dụ của trường hợp đó.
