# Đường đi nhanh khi chỉ cần một kết quả (`top_n = 1`)

File liên quan: `engine.py::_quet_tho`, `engine.py::_du_manh_de_dung_som`.

---

## 1. Động cơ

Người dùng thường đặt `top_n = 1`: chỉ cần **một** bằng chứng đáng tin cho mỗi video
rồi chuyển sang link tiếp theo. Khi quét hàng loạt 10–11 video dài nhiều giờ, việc
quét trọn vẹn video thứ nhất trong khi đã có bằng chứng rõ ràng ở phút thứ 5 là lãng
phí lớn.

Mục tiêu: **rút ngắn thời gian tới bằng chứng hợp lệ đầu tiên mà không giảm recall.**

---

## 2. Khi nào bật

Cả ba điều kiện phải đúng:

```
config.top1_tim_nhanh == True          (mặc định bật)
config.top_n == 1
số khúc >= max(2, config.top1_khuc_toi_thieu)     (mặc định 3)
```

Điều kiện số khúc rất quan trọng. Với video 2 khúc, tách thành hai lượt gọi chỉ tổ
tốn thêm **một lần nạp kho vân tay** mà gần như không tiết kiệm được gì. Đo được:
nạp kho + phân tích file đầu mất khoảng **13 giây**. Ngưỡng 3 khúc bảo đảm phần tiết
kiệm được (ít nhất 2 khúc bỏ qua) lớn hơn hẳn phần trả thêm.

Với `top_n >= 2`, đường đi nhanh **không** kích hoạt — hành vi quét toàn bộ giữ
nguyên như cũ, vì lúc đó vẫn cần thấy hết video mới phân bổ đều được kết quả.

---

## 3. Cách chạy

```
        cắt khúc
            │
            ▼
    so khớp KHÚC ĐẦU            ← vùng người kiểm tra dễ tua tới nhất
            │
            ▼
   có ứng viên vượt cổng dừng sớm?
       │              │
      có             không
       │              │
       ▼              ▼
   trả kết quả   so khớp TOÀN BỘ KHÚC CÒN LẠI trong MỘT lần gọi
                      │
                      ▼
              ghép kết quả thô của cả hai lượt
```

Điểm mấu chốt: khi phải quét bù, kết quả thô của khúc đầu **được giữ lại và ghép**
với phần còn lại, không quét lại. Nhờ vậy khối lượng so khớp bằng đúng lượt quét
toàn bộ; chi phí phụ duy nhất là một lần nạp kho (~13 giây).

Tối đa **hai** lần nạp kho cho mỗi video, dù video dài bao nhiêu.

---

## 4. Cổng dừng sớm

```
ứng viên đạt tiêu chí chấp nhận thường (chap_nhan_khop)
VÀ  hashes    >= config.top1_hash_dung_som       (mặc định 5.000)
VÀ  matched_s >= config.top1_match_s_dung_som    (mặc định 60 giây)
```

Cổng này **chặt hơn hẳn** tiêu chí chấp nhận thường, có chủ ý: dừng sớm nghĩa là
không bao giờ nhìn phần còn lại của video, nên chỉ được dừng khi bằng chứng mạnh tới
mức phần còn lại không thể đổi kết luận.

Vì sao 5.000 hash + 60 giây (số đo thật, xem `ZERO_MATCH_ROOT_CAUSE.md`):

| Ca | Hash | Dài | Vượt cổng? |
|---|---:|---:|---|
| bản reup nguyên vẹn (marathon 6,7h) | 15.173 | 786,8s | có |
| clip gốc nguyên bản, 300s | 4.610 | 263,6s | không — quét tiếp cho chắc |
| nhiễu mạnh nhất đo trên 11 video âm tính | 309 | 578,6s | không |
| nhạc hiệu dùng chung | 133 | 8,8s | không |

Cổng nằm giữa vùng "reup rõ ràng" và vùng "nhiễu", lệch hẳn về phía an toàn. Hệ quả
là một số ca đáng lẽ dừng được vẫn quét tiếp — chấp nhận đánh đổi đó, vì **sai theo
hướng quét thừa thì chỉ chậm, sai theo hướng dừng sớm thì mất kết quả.**

---

## 5. Bảo đảm không mất recall

Ba tính chất, mỗi tính chất có test khoá lại trong
`tests/test_chan_doan_zero_match.py`:

1. **Fast pass trượt thì luôn quét nốt phần còn lại** —
   `test_khong_du_manh_thi_quet_not_phan_con_lai`.
2. **Bằng chứng của khúc đầu không bị vứt khi quét bù** —
   `test_quet_bu_giu_lai_ket_qua_tho_cua_vung_dau`.
3. **Match mạnh nằm cuối video vẫn tìm được** —
   `test_match_manh_o_cuoi_video_van_tim_duoc` (dựng bản reup ở ~90% video, fast
   pass không thấy gì, fallback phải thấy).

Nói cách khác: tập kết quả thô cuối cùng của đường đi nhanh **bằng đúng** tập của
lượt quét toàn bộ, trừ khi đã dừng sớm vì bằng chứng vượt cổng.

---

## 5b. ĐÁNH ĐỔI PHẢI BIẾT: kết quả Top-1 có thể KHÁC lượt quét toàn bộ

Đây là hệ quả tất yếu của việc dừng sớm, không phải lỗi — nhưng phải nói rõ.

Đo thật trên `n4Ca9SmTfi0` (marathon 6,7 giờ, 8 khúc), cùng kho, cùng cấu hình:

| Đường đi | Thời gian | Khúc đã quét | Top-1 chọn được |
|---|---:|---:|---|
| Quét toàn bộ | 326,9s | 8 | *Jeffy's Disney Show!* — 10.436 hash, phủ **81,2%**, 562,2s, @01:29:28 |
| Fast Top-1 | **98,1s** | 1 | *Jeffy The Fly!* — **13.316 hash**, phủ 73,2%, **711,0s**, @00:25:18 |

Tiết kiệm **70%** thời gian. Nhưng hai lượt trả về **hai clip gốc khác nhau**.

Cả hai đều là bản reup **thật và rất mạnh** (đều trên 10.000 hash, đều khớp liên tục
trên 9 phút, đều vượt sàn bằng chứng 0,70). Chênh lệch chỉ nằm ở thứ tự xếp hạng:
`khoa_chat_luong = "ty_le"` nên lượt quét toàn bộ chọn ứng viên có **phần trăm phủ**
cao hơn (81,2% > 73,2%), dù ứng viên kia mạnh hơn về **lượng tuyệt đối** (13.316 >
10.436 hash) và dài hơn (711,0s > 562,2s).

Nói chính xác thì:

> Fast Top-1 trả về **một bằng chứng đã được xác minh là rất mạnh**, chứ không cam
> kết trả về ứng viên tối ưu toàn cục theo `khoa_chat_luong`.

Trong ví dụ trên, ứng viên fast còn nằm **sớm hơn một tiếng** trong video (00:25:18
so với 01:29:28), tức dễ cho người kiểm tra tua tới hơn — đúng hướng ưu tiên đã nêu
ở mục 6.

**Khi nào nên tắt:** nếu cần đúng ứng viên tối ưu toàn cục (ví dụ đang so sánh chất
lượng bằng chứng giữa các video, hoặc muốn kết quả tái lập chính xác với lượt quét
cũ), đặt `top1_tim_nhanh = False`. Xem mục 9.

## 6. Thứ tự quét ≠ tiêu chuẩn chấp nhận

Khúc đầu được quét trước vì nếu có bằng chứng ở đó thì người kiểm tra tua tới nhanh
hơn. Đây thuần tuý là **thứ tự tìm kiếm**, không phải bộ lọc: một ứng viên yếu ở đầu
video không bao giờ được chọn thay cho ứng viên mạnh hơn ở cuối, vì nó không vượt
nổi cổng dừng sớm và lượt quét bù sẽ nhìn thấy cả hai.

Quy tắc ưu tiên "chất lượng trước, dễ kiểm tra chỉ dùng để phá hoà" trong
`chon_dai_dien()` giữ nguyên, không bị đường đi nhanh đụng tới.

---

## 7. Giao diện

Khi đường đi nhanh chạy, thanh tiến độ nói rõ nó đang làm gì:

```
Tìm nhanh 1 kết quả đáng tin — đang kiểm tra phần đầu video...
✓ Đã tìm thấy bằng chứng đủ mạnh ở phần đầu (15173 hash, khớp 00:13:06) — bỏ qua phần còn lại.
```

hoặc khi phải quét bù:

```
Chưa có bằng chứng đủ mạnh ở phần đầu — đang mở rộng quét toàn bộ video...
```

`ScanResult.chan_doan.duong_di` ghi lại đường đã đi (`quet_toan_bo`,
`dung_som_vung_dau`, `quet_bu_toan_bo`) để đối chiếu khi cần.

---

## 8. Các phương án đã cân nhắc

| Phương án | Ưu | Nhược | Quyết định |
|---|---|---|---|
| A. Chỉ sửa bộ lọc, luôn quét toàn bộ | đơn giản nhất, không rủi ro | Top-1 vẫn chậm trên video nhiều giờ | không đủ cho mục tiêu tốc độ |
| **B. Khúc đầu rồi quét bù phần còn lại** | tối đa 2 lần nạp kho; không tăng khối lượng so khớp | tiết kiệm 0 khi bằng chứng nằm cuối | **đã chọn** |
| C. Quét tăng dần từng nhóm nhỏ | ra kết quả sớm hơn nữa | mỗi nhóm một lần nạp kho (~13s); video 7 khúc có thể tốn thêm ~78s | loại — chi phí nạp kho lớn |
| D. Giữ tiến trình matcher thường trú | tốt nhất về lý thuyết | phức tạp, rủi ro hồi quy cao, phải sửa cách gọi thư viện bên thứ ba | loại — chưa có bằng chứng cần tới |

Phương án C và D chỉ đáng cân nhắc nếu đo được rằng thời gian nạp kho chiếm phần lớn
tổng thời gian. Số đo hiện tại: nạp kho ~13 giây, so khớp một khúc một giờ ~50–110
giây — nạp kho chỉ chiếm khoảng 10–20%. Chưa đủ để biện minh cho D.

---

## 9. Tắt đi khi cần

```python
eng.config.top1_tim_nhanh = False     # quay về đúng hành vi quét toàn bộ như cũ
```

Hoặc nâng `top1_khuc_toi_thieu` để chỉ bật với video thật dài.
