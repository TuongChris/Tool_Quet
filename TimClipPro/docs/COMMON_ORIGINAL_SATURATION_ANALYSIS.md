# Trần `max_matches` ở chế độ nguồn chung — đo trên lô thật Joe Bartolozzi

> Vòng điều tra 04/10/2026 trên bản sao dữ liệu, offline (rào chắn chặn mọi mạng, chặn ghi
> production). Mã nguồn `fe07985` không sửa. Bằng chứng thô:
> `D:\TimClipPro_SaturationRecovery\20261004_013023\evidence\`.
>
> **Kết luận: NO_RECALL_GAIN_FOUND.** Trần 200 có cắt thật (293 dòng → 200), nhưng phần bị cắt
> chỉ là thêm các lần khớp của cùng một đoạn nhạc hiệu dùng chung. Nâng trần, thậm chí bỏ luôn trần
> `--search-depth`, không làm xuất hiện ứng viên đạt chuẩn nào và không đổi kết luận của lô.
> Không triển khai «quét lại khúc chạm trần»; giữ hành vi và cảnh báo hiện có.

## 1. Câu hỏi

Lô 25 video dài 3–9 giờ, kho `KhoJoeBartolozzi` (1.178 clip), chế độ «Một video gốc chung cho cả
lô». Lô kết luận «Không tìm thấy video gốc chung», kèm giới hạn «1 khúc chạm trần». Bộ lập kế
hoạch chỉ cần một lượt quét trọn video mốc.

Câu cần trả lời: trần 200 kết quả mỗi khúc có che mất một ứng viên đạt chuẩn — tức có làm sai kết
luận — hay không?

## 2. Tái hiện

**Video mốc.** `chon_thu_tu_xu_ly` chọn video ngắn nhất: `3ooANFVH6BM`, dài 10.847,9 s
(3:00:47). Bằng chứng: bản ghi chẩn đoán của lô thật trong `data/chan_doan/` và audio đệm
`data/downloads/3ooANFVH6BM.webm`, ghi lúc 01:01 và 00:53 ngày 04/10.

**Cấu hình đang chạy.** `chunk_s` 3600, `overlap_max_s` 180, `max_matches` 200, `shifts_quet` 4,
`min_hash` 15, `min_match_s` 5, `min_hash_floor` 1000, `quet_da_toc_do` bật, `luoi_resample`
0,96/0,98/1,02/1,04, `ncores` tự động (8).

**Một lượt thu thập trọn gồm 20 lần khớp khúc:**

- 4 khúc gốc, lưới mốc 0 / 3420 / 6840 / 10260 s;
- vì không có ứng viên đạt chuẩn, 4 lượt bù cao độ × 4 khúc.

**Cách tái hiện.** Chạy lại đúng `Engine.scan_media(muc_tieu=collect, luu_lich_su=False)` của
`fe07985` trên audio đệm và bản sao kho. Từng số của phễu trùng khớp với lô thật:

| Trường chẩn đoán | Lô thật | Tái hiện |
|---|---:|---:|
| Số khúc đã khớp (`so_khuc`) | 20 | 20 |
| Số dòng thô (`dong_tho`) | 510 | 510 |
| Số dòng đọc được (`parse_duoc`) | 489 | 489 |
| Qua `min_hash` / qua `min_match_s` | 460 / 458 | 460 / 458 |
| Số ứng viên sau gộp (`gop_lai`) | 442 | 442 |
| Số ứng viên đạt chuẩn | 0 | 0 |
| Số hash thô lớn nhất | 212 | 212 |
| Số khúc chạm trần | 1 | 1 |
| Bù tốc độ đã thử | 4 lưới cao độ | 4 lưới cao độ |
| Ứng viên mạnh nhất bị loại | 212 hash / 8,6 s / phủ 0,1% | giống hệt |

Thời gian tái hiện là 296 s:

- khớp 4 khúc gốc 154 s;
- mỗi lượt bù cao độ khoảng 30 s;
- cả 16 lần khớp bù cao độ đều ra 0 dòng.

## 3. Khúc chạm trần

| Khúc | Vùng video (s) | Dòng `Matched` | Clip | Hash mỗi dòng |
|---|---|---:|---:|---|
| `chunk_0000000.wav` | 0 – 3600 | 89 | 74 | 11 – 168 |
| **`chunk_0003420.wav`** (chỉ số 1) | **3420 – 7020** | **200 = trần** | 86 | **123 – 201** |
| `chunk_0006840.wav` | 6840 – 10440 | 91 | 80 | 11 – 175 |
| `chunk_0010260.wav` | 10260 – 10847,9 | 109 | 88 | 12 – 212 |

Cả 200 dòng của khúc chạm trần chỉ nằm ở **3 vị trí** trong video: quanh 3685 s, 4710 s và
6390–6395 s. Ở mỗi vị trí, một đoạn dài 7–10 s khớp với hàng chục clip khác nhau trong kho; 98%
số dòng khớp từ giây ≥ 60 của clip. Đây là dấu vân tay của nhạc hiệu dùng chung (cùng kiểu với
`docs/ZERO_MATCH_ROOT_CAUSE.md`), không phải một clip được dùng lại dài.

## 4. Trần nằm ở tầng nào (đọc source, không đoán)

1. **audfprint `Matcher._best_count_ids`** (`audfprint_match.py:124-147`). Chỉ xét tối đa
   `search_depth` clip có số hash thô > `--min-count`. Tool không truyền `--search-depth`, nên
   giá trị là mặc định CLI 100 (`audfprint.py`, dòng usage). Các clip được xếp theo «hash thô ÷
   tổng hash của clip». Hạng lớn nhất thấy được là 96–99 ở cả 4 khúc gốc, sát mức 100. Ở khúc
   chạm trần, bỏ giới hạn này thì có 673 clip ra dòng, nên tầng này chắc chắn đang cắt ở đó (và
   nhiều khả năng ở các khúc khác).
2. **`_exact_match_counts`** (`:196-239`). Một clip có thể ra NHIỀU dòng: mỗi đỉnh độ lệch thời
   gian đủ `--min-count` (10) hash là một dòng.
3. **`match_hashes` → `match_file`** (`:335`, `:379`). Các dòng được sắp theo số hash đã lọc,
   giảm dần, rồi bị cắt ở `rslts[:max_returns]`. Đây là nơi `--max-matches 200`
   (`Config.max_matches`, `engine.py:3554-3557`) có tác dụng. Từ khi bỏ `--sortbytime`, phần bị
   cắt là phần YẾU NHẤT.
4. **Parser `_match_chunks`** đọc 100% dòng (489/489), không cắt. `_merge` và `loc_chap_nhan`
   không có trần nào.
5. **`so_khuc_cham_tran`** (`engine.py:3665-3668`) cộng dồn qua mọi lần gọi audfprint của lượt
   quét (khúc gốc + bù tốc độ). Mỗi cặp (lần gọi, khúc) có số dòng `Matched` ≥ `max_matches` được
   đếm 1. Nghĩa đúng của nó là «kết quả của khúc này CÓ THỂ đã bị cắt», vì đúng bằng trần cũng
   được đếm. Giới hạn chuyển tới kết luận lô qua `common_original._gioi_han_ket_luan_am`.

## 5. Benchmark trần trên đúng khúc chạm trần

Benchmark chạy audfprint trên riêng `chunk_0003420.wav` (3600 s). Lệnh dựng bằng
`Engine._audfprint_cmd` và chạy qua `Engine._run_stream`, với `--ncores 8 --find-time-range
--exact-count --min-count 10 --shifts 4`. Chỉ đổi `--max-matches`. Bộ nhớ là đỉnh RSS của cả
cây tiến trình (audfprint, 8 worker joblib và bộ theo dõi).

| `--max-matches` | Số dòng | Số clip | Hash dòng mạnh nhất / yếu nhất | Qua cả hai bộ lọc | Thời gian tường | Bộ nhớ đỉnh | Dung lượng kết quả |
|---|---:|---:|---|---:|---:|---:|---:|
| 200 | 200 | 86 | 201 / 123 | 200 | 136,5 s | 2.692 MB | 56 KB |
| 400 | **293** | 86 | 201 / 10 | 270 | 136,3 s | 2.689 MB | 82 KB |
| 800 | 293 | 86 | 201 / 10 | 270 | 135,4 s | 2.691 MB | 82 KB |
| 1600 | 293 | 86 | 201 / 10 | 270 | 135,5 s | 2.689 MB | 82 KB |
| 1.000.000 (không trần) | 293 | 86 | 201 / 10 | 270 | 135,9 s | 2.695 MB | 82 KB |
| *chẩn đoán:* không trần + `--search-depth 2000` | 1.734 | 673 | 201 / 10 | 1.560 | 704,1 s | 2.694 MB | 486 KB |
| *hiệu chuẩn:* khúc 5 s, trần 200 | 0 | 0 | — | 0 | 4,7 s | 932 MB | 0,2 KB |

Đọc bảng:

- **audfprint thật sự có > 200 dòng.** Tổng là 293 (ở độ sâu 100), nên trần 200 cắt 93 dòng. Từ
  trần 400 trở lên không còn gì để cắt.
- **Trần không đổi chi phí tính toán.** audfprint tính đủ mọi dòng rồi mới cắt, nên thời gian và
  bộ nhớ giống nhau ở mọi trần. Chi phí cố định của một lần gọi là khoảng 5 s (nạp kho), phần còn
  lại là khoảng 131 s khớp một khúc 1 giờ.
- **Không có clip mới.** 93 dòng bị cắt thuộc đúng 86 clip đã thấy, có 10–123 hash mỗi dòng:
  thêm các lần khớp của 3 đoạn nhạc hiệu, cộng vài dòng thưa rải rác.
- **Ổn định tuyệt đối.** Mỗi lần nâng trần, các dòng của trần thấp hơn vẫn là các dòng đầu của
  trần cao hơn, cùng thứ tự. 200 dòng của benchmark cũng trùng 200 dòng của lượt quét thật
  (4 khúc chạy song song).

## 6. Phễu ứng viên

**Riêng khúc chạm trần.** Mỗi file benchmark được cho qua parser, `_merge` và `loc_chap_nhan`
thật, giả mỗi `_run_stream`.

| Trần | Dòng thô (clip) | ≥ 15 hash | ≥ 5 s | Sau gộp (clip) | Đạt chuẩn | Gộp mạnh nhất | Mới so với trần 200 |
|---|---|---:|---:|---|---:|---|---|
| 200 | 200 (86) | 200 | 200 | 200 (86) | **0** | 201 hash / 7,6 s | — |
| ≥ 400 | 293 (86) | 271 | 270 | 258 (86) | **0** | 201 hash | 0 clip, 63 vị trí gộp mới |

**Cả video — phát lại trọn `_scan_media`.** Mọi thứ chạy thật: ffmpeg, parser, bù tốc độ, gộp,
chấp nhận. Chỉ `_run_stream` của audfprint trả lại kết quả đã đo; dòng của khúc chạm trần được
thay bằng dòng ở trần đang xét. Lệnh nào chưa có bản ghi sẽ được chạy thật, và số đó nằm ở cột
«Lệch kịch bản».

| | Trần 200 | Đủ 293 dòng (trần ≥ 400) | *Chẩn đoán:* 1.734 dòng (bỏ cả `--search-depth`) |
|---|---:|---:|---:|
| Đọc được / qua `min_hash` / qua `min_match_s` | 489 / 460 / 458 | 582 / 531 / 528 | 2.023 / 1.830 / 1.818 |
| Sau gộp (cả video) | 442 | 500 | 1.788 |
| **Đạt chuẩn** | **0** | **0** | **0** |
| Mạnh nhất cả video | 212 hash | 212 hash | 212 hash |
| Kế hoạch bù tốc độ | 4 lưới cao độ | giống hệt | giống hệt |
| Lệch kịch bản | 0 | 0 | 0 |
| Thời gian parse / gộp | 0,02 s / 0,01 s | 0,02 s / 0,01 s | — |

Phát lại ở trần 200 ra đúng từng số của lô thật, nên cách phát lại không làm sai lệch gì. Không
trần nào làm xuất hiện ứng viên đạt chuẩn; tập đạt chuẩn ở trần 200 (rỗng) vẫn còn nguyên. Ở cấp
lô: video mốc không có ứng viên đạt chuẩn, nên tập khả dĩ S* rỗng và kết luận vẫn là «Không tìm
thấy». Không cần quét thêm video nào.

## 7. Vì sao kết quả này không phải ngẫu nhiên

**Chỉ bậc A có thể nhận ứng viên ở kho này.**

- Clip ít hash nhất có 23.951 hash (trung vị 115.101).
- Bậc B (phủ ≥ 60%) vì thế cần ≥ 14.371 hash, tức bậc A (≥ 1.000 hash sau gộp) luôn là ngưỡng
  thấp hơn.
- Dòng bị cắt có ≤ 123 hash. Cả video không có mảnh nào vượt 212 hash.

**Cách duy nhất phần bị cắt lẽ ra có thể đổi kết luận.**

- Gộp nhiều mảnh yếu của CÙNG một clip, cùng align (±`dedup_s`), nối liền nhau. Mảnh bị cắt có
  ≤ 123 hash, mảnh thấy được ≤ 201 hash, nên cần ít nhất 5–9 mảnh.
- Đó là dạng của một bản reup bị đổi tốc độ khoảng 2%: mỗi đỉnh lệch chỉ khoảng 65 hash
  (`toc_do_khop.py`), nhưng `_merge` cộng dồn được.
- Các mảnh này cũng là đầu vào của bộ đọc độ trôi.
- Phát lại với đủ dòng loại trừ chính ca này cho khúc này: không chuỗi gộp nào vượt 201 hash, và
  bộ đọc độ trôi không ra ước lượng nào.

## 8. Quyết định và giới hạn còn lại

- **Không** triển khai «quét lại khúc chạm trần».
  - Ở ca thật duy nhất có, nó không thêm bằng chứng nào.
  - Nó tốn trọn chi phí khớp lại khúc: khoảng 136 s cho một khúc 1 giờ, tức +46% thời gian quét
    của video mốc này.
- **Không** nâng `max_matches` toàn cục, không đổi ngưỡng, `_merge`, audfprint hay cấu hình.
- Giữ nguyên dòng giới hạn «N khúc chạm trần…» trên giao diện và CSV. Nó vẫn đúng: «không tìm
  thấy» chưa phải chứng minh tuyệt đối.
- **Một mẫu không phải chứng minh tổng quát.** Kịch bản ở mục 7 (reup đổi tốc độ nằm trọn trong
  một khúc dày nhạc hiệu) vẫn có thể xảy ra ở video khác.
  - Nếu cần xét lại: dùng bộ công cụ ở thư mục bằng chứng (tái hiện, benchmark, phát lại) trên
    đúng khúc đó trước khi thiết kế gì thêm.
  - Ghi nhận cho thiết kế sau này: vì trần không đổi chi phí tính toán (mục 5), nếu một ngày cần
    nhiều dòng hơn thì nâng trần ngay lượt đầu rẻ hơn hẳn quét lại. Nhưng `max_matches` nằm trong
    `TRUONG_CHINH_SACH`, nên đó là đổi chính sách nhận diện và cần thiết kế riêng.
- **`--search-depth 100` là tầng giới hạn thứ hai.** Đã đo chắc là nó cắt ở khúc chạm trần, và
  nhiều khả năng ở mọi khúc (hạng 96–99). Bỏ nó ở khúc này cho 673 clip nhưng không có gì mạnh
  hơn, và chậm gấp 5,2 lần. Không đổi; chỉ ghi nhận.
- **Lô này «không tìm thấy» vì lý do khác, không phải vì trần.**
  - Trong 3 giờ của video mốc, thứ duy nhất khớp kho là các đoạn nhạc hiệu 7–10 s ở đúng tốc độ.
  - 16 lần khớp bù cao độ (±2%, ±4%) ra 0 dòng.
  - Vì sao nội dung chính không khớp kho thì chưa được kiểm, và nằm ngoài phạm vi vòng này.
