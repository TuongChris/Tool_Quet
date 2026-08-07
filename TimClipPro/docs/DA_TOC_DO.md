# Bù video bị đổi tốc độ để né vân tay

File liên quan: `toc_do_khop.py`, `engine.py::_quet_da_toc_do`.

---

## 1. Điểm mù cần bịt

audfprint cực kỳ nhạy với co giãn thời gian. Đo thật trên một clip gốc 300 giây
(4.610 hash, khớp liền 263,6 giây khi nguyên bản):

| Lệch tốc độ | Đoạn khớp dài nhất | Hash | Còn lại |
|---|---:|---:|---:|
| 0% | 263,6s | 4.610 | 100% |
| 0,5% | 21,0s | 323 | 7% |
| 1% | 10,6s | 169 | 4% |
| 2% | 4,5s | 65 | 1% |
| 4% | 1,5s | 28 | 0,6% |

Chỉ cần tăng tốc **2%** — tai người gần như không nhận ra — là bản reup tàng hình.
Ngược lại, nén lại (AAC 64k, Opus 32k), đổi âm lượng (±dB), lọc tần số đều **vô hại**
(vẫn giữ 20–40% hash và một đoạn khớp liền 263 giây).

---

## 2. Ý tưởng: đọc độ trôi, không quét mù

Quét mù ở nhiều tốc độ là phản xạ đầu tiên, nhưng nó **vừa đắt vừa không đủ chính xác**:
với lưới bước 1%, sai số tồn dư tệ nhất là 0,5%, mà theo bảng trên thì 0,5% đã làm mất
93% bằng chứng. Muốn bằng chứng mạnh phải trúng tốc độ với sai số ~0,1%, tức cần hàng
chục lượt quét.

Điểm mấu chốt: **các mảnh khớp còn sót lại không nằm ngẫu nhiên.** Nếu video phát nội
dung gốc ở tốc độ `r` thì điểm ở giây `t_o` của bản gốc xuất hiện ở giây `t_q = t_o/r`
trong video. audfprint báo `align = t_q − t_clip`, mà `t_clip = t_o = r·t_q`, nên:

```
align = t_q − r·t_q = t_q · (1 − r)
```

`align` **tuyến tính** theo thời gian, độ dốc đúng bằng `(1 − r)`. Hồi quy độ dốc là ra
tốc độ — dữ liệu cần thiết đã nằm sẵn trong output của lượt quét thường, tốn **0 giây**
so khớp thêm.

Kiểm chứng trên 8 mức biến đổi thật (sai số ≤ 0,05%):

| Tốc độ thật | Ước lượng | Sai số |
|---|---|---|
| 0,940 | 0,9398 | 0,0002 |
| 0,980 | 0,98001 | 0,00001 |
| 0,995 | 0,99491 | 0,00009 |
| 1,005 | 1,00497 | 0,00003 |
| 1,010 | 1,00996 | 0,00004 |
| 1,020 | 1,01991 | 0,00009 |
| 1,040 | 1,03999 | 0,00001 |
| 1,050 | 1,0504 | 0,00044 |

Chính xác hơn lưới bước 1% khoảng **100 lần**, và miễn phí.

---

## 3. Vì sao dùng Theil–Sen chứ không bình phương tối thiểu

Trong cùng một clip gốc luôn lẫn hai loại mảnh: mảnh thật của bản reup (thẳng hàng
trên đường trôi) và mảnh của **nhạc hiệu dùng chung** (align ngẫu nhiên). Bình phương
tối thiểu bị nhóm thứ hai kéo lệch.

Đo thật: với fixture đổi tốc độ 3%, bình phương tối thiểu cho R² = 0,916 — sát ngưỡng
0,90 tới mức chỉ cần **dựng lại file** là kết quả lật từ "phát hiện được" thành "không
phát hiện được", và ước lượng lệch tới 0,00135 (chỉ thu lại được 38,5% vân tay).

Theil–Sen lấy **trung vị độ dốc của từng cặp điểm** nên chịu được tới ~29% điểm nhiễu.
Sau khi có đường, đếm số điểm nằm trong 1,5 giây quanh nó (tỉ lệ "thẳng hàng"), rồi
khớp lại bằng bình phương tối thiểu **chỉ trên nhóm điểm hợp**. Kết quả trên cùng
fixture: ước lượng **1,03000** — đúng tuyệt đối, 99% mảnh thẳng hàng.

---

## 4. Vùng phủ đo được

| Họ biến đổi | Bộ dò độ trôi thấy được | Ghi chú |
|---|---|---|
| `atempo` (đổi tốc độ, **giữ** cao độ) | **0,94 … 1,05** | từ ±8% trở đi audfprint không còn mảnh nào |
| `resample` (đổi **cả** cao độ) | chỉ ~±2% | từ ±4% là **0 mảnh** ở mọi mức tới ±25% |

Cao độ bị đổi thì các mốc phổ dịch đi, vân tay hỏng hoàn toàn — không mảnh nào sống
sót nên không có gì để hồi quy. Vùng đó phải quét mù bằng `luoi_resample`.

---

## 5. Cách chạy

```
lượt quét thường
        │
   có ứng viên đạt chuẩn?  ── có ──> xong, KHÔNG chạy gì thêm
        │ không
        ▼
   đọc độ trôi từ mảnh khớp đã có
        │
   ├── đọc được ──> bù theo tốc độ đã đo (họ tempo)
   └── không ────> lưới quét mù `luoi_resample` (bù cao độ)
        │
        ▼
   so khớp lại, quy mốc thời gian về trục video gốc
        │
   đạt chuẩn? ── có ──> xong
        │ không
        ▼
   ĐỌC LẠI ĐỘ TRÔI trên toàn bộ mảnh đã có (nhiều hơn hẳn) -> tinh chỉnh, lặp
```

**Vòng tinh chỉnh là phần quan trọng nhất.** Vì mọi mốc đều đã quy về trục thời gian
gốc, độ dốc luôn cho ra **tổng** tỉ lệ chứ không phải phần dư, nên cứ ước lượng lại
trên toàn bộ mảnh là hội tụ. Nhờ nó mà lưới thô bước 2% vẫn cứu được ca đổi cao độ 3%:
lưới kéo về trong khoảng 1% → sinh đủ mảnh → đọc độ trôi → trúng 1,02970 → thu lại
85,3% vân tay.

Tổng số lượt so khớp phụ bị chặn cứng bởi `toc_do_toi_da_thu` (mặc định 6).

---

## 6. Quy đổi mốc thời gian

Đây là chỗ dễ sai nhất. Khúc đã bị đổi tốc độ `k` lần thì mọi mốc **đo trong khúc**
phải nhân với `k` mới về đúng trục thời gian video; mốc **bắt đầu khúc** thì không đổi:

```
t_video = offset_khúc + t_trong_khúc × k
độ_dài_video = độ_dài_đo_được × k
```

Hệ số `k` được mã vào tên file khúc (`chunk_0003420_k097087.wav`) và đọc lại trong
`_match_chunks()`. Tên khúc **không có** hậu tố được hiểu là `k = 1,0`, nên định dạng
cũ vẫn đọc được.

Kiểm chứng: fixture đặt clip gốc ở đúng giây thứ 60; sau khi bù, mốc báo về là
00:00:59 – 00:01:01 ở cả bốn ca.

---

## 7. Kết quả đầu-cuối

Fixture: `[nhiễu 60s] + [clip gốc thật trong kho, bị biến đổi] + [nhiễu 60s]`.

| Ca | Trước | Sau | Cách bù | Mốc báo về |
|---|---|---|---|---|
| không đổi (đối chứng) | tìm ra | tìm ra, 11.277 hash, phủ 100% | không cần | 00:01:00 |
| nhanh 3%, giữ cao độ | **0** | tìm ra, 6.365 hash, phủ **56,4%** | đọc độ trôi → r=1,03000 | 00:00:59 |
| chậm 3%, giữ cao độ | **0** | tìm ra, 6.625 hash, phủ **58,7%** | đọc độ trôi → r=0,97001 | 00:01:01 |
| nhanh 3% + đổi cao độ | **0** | tìm ra, 9.615 hash, phủ **85,3%** | lưới → tinh chỉnh → r=1,02970 | 00:00:59 |
| chỉ có nhiễu (đối chứng âm) | 0 | **0** | đã thử 4 phương án, không bịa | — |

Phủ vân tay sau khi bù ở hai ca `atempo` thấp hơn ca `resample` vì bản thân bộ lọc
`atempo` là phase vocoder, và ta phải chạy nó **hai lần** (một lần khi kẻ vi phạm tạo
video, một lần khi ta bù lại) nên tín hiệu bị mài thêm. `resample` là phép biến đổi
sạch nên bù xong gần như nguyên vẹn. Dù vậy 56% vẫn thừa sức vượt ngưỡng chấp nhận.

---

## 8. Chi phí

Chỉ chạy khi lượt quét thường **không có ứng viên nào đạt chuẩn**, nên **video có kết
quả bình thường không tốn thêm một giây nào.**

Đo sạch (máy rảnh) trên `OVTMo5bhtN0`, video 59 phút, âm tính:

| | Thời gian | Khúc đã so khớp | Lượt bù |
|---|---:|---:|---:|
| `quet_da_toc_do = False` | 54,2s | 2 | 0 |
| `quet_da_toc_do = True` | **158,2s** | 10 | 4 |

Tức **×2,9** cho video âm tính. Đó là cái giá của việc chắc chắn rằng "0 kết quả" không
phải do bị né tránh. Trần `toc_do_toi_da_thu = 6` chặn trường hợp xấu nhất.

### Chọn cấu hình theo nhu cầu

| Nhu cầu | Cấu hình | Chi phí thêm khi âm tính |
|---|---|---|
| Nhanh nhất, vẫn phủ đổi tốc độ ±6% | `luoi_resample = []` | gần **0** (đọc độ trôi là miễn phí) |
| Mặc định — phủ thêm đổi cao độ ±5% | (như hiện tại) | ×2,9 |
| Tắt hẳn, về hành vi cũ | `quet_da_toc_do = False` | 0 |

Nếu phần lớn video quét là âm tính thật (như 11 video parody), đặt `luoi_resample = []`
giữ được gần hết lợi ích mà không mất tốc độ: bộ dò độ trôi vẫn bắt mọi ca đổi tốc độ
±6% — họ biến đổi phổ biến nhất — mà không tốn giây nào.

---

## 9. Chỉnh và tắt

```python
eng.config.quet_da_toc_do = False        # tắt hẳn, về đúng hành vi cũ
eng.config.toc_do_toi_da_thu = 2         # giảm trần số lượt quét phụ
eng.config.luoi_resample = []            # bỏ lưới quét mù, chỉ giữ đọc độ trôi (miễn phí)
eng.config.luoi_tempo = [0.90, 1.10]     # thêm lưới cho đổi tốc độ vượt ±6%
eng.config.toc_do_thang_hang = 0.75      # siết: đòi mảnh thẳng hàng hơn
```

Vùng **chưa** phủ mặc định: đổi tốc độ giữ cao độ vượt quá ±6%, và đổi cao độ vượt
±5%. Thêm mức vào `luoi_tempo`/`luoi_resample` nếu gặp thực tế — mỗi mức thêm đúng một
lượt so khớp.
