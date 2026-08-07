# Chọn kết quả đại diện — kiến trúc xếp hạng

Ngày: 2026-08-07 · Base: `8cb2597` · Hàm: `engine.chon_dai_dien`, `Engine._chon_loc`

---

## 1. Xếp hạng hiện tại (đọc từ source)

```
audfprint raw match
  → _merge()               gộp khúc gối nhau thành đoạn liền
  → _gan_chi_so()          tính ty_le (% vân tay clip khớp được), vung (Đầu/Giữa/Cuối)
  → _chon_loc()            lọc ngưỡng + chọn top_n
       ├─ lọc: hashes >= min_hash_floor (1000)
       ├─ uu_tien = (hashes >= min_hash_strong, clip chưa dùng, hashes)
       ├─ phan_bo_deu: chia video thành top_n vùng đều, mỗi vùng lấy 1
       └─ sort theo start_s cho dễ đọc
  → ScanResult.matches
```

### Ngữ nghĩa `top_n`

`top_n` = **số ĐOẠN vi phạm được xuất**, không phải số video gốc. Cùng một clip gốc
có thể xuất hiện nhiều đoạn; `uu_tien_clip_khac_nhau` chỉ *ưu tiên* clip chưa dùng chứ
không cấm trùng. Ngữ nghĩa này **được giữ nguyên**.

### Với `top_n = 1`

`buoc = duration / 1` ⇒ **cả video là một vùng** ⇒ vòng lặp vùng chọn
`max(dat, key=uu_tien)` trên toàn bộ ứng viên. Vì `da_dung` còn rỗng nên vế thứ hai
luôn `True`, khoá rút gọn thành `(hashes >= 5000, hashes)`.

> Nghĩa là **Top-1 hiện tại thuần tuý là `max(hashes)`; vị trí không đóng vai trò gì.**

---

## 2. Phân bố thật (200 job trong `lichsu.db`, chỉ đọc)

| Chỉ số | Kết quả |
| --- | --- |
| `hashes(#2) / hashes(#1)` | min 0,268 · p25 0,856 · **trung vị 0,921** · p75 0,965 · p90 0,982 |
| Số ứng viên mỗi job | trung vị 3, tối đa 5 |
| Vị trí #1 (tỉ lệ) | p25 0,098 · **trung vị 0,399** · p75 0,684 · p90 0,836 |

Tỉ lệ job có #2 nằm trong dải của #1:

| Dung sai | 1% | 3% | 5% | 10% | 15% | 20% |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Số job | 5% | **24%** | 32% | 62% | 77% | 84% |

**Hai kết luận:**

1. Near-tie là chuyện **thường**, không phải ngoại lệ (trung vị 0,92). Dung sai lỏng
   (≥10%) sẽ đảo phần lớn kết quả — đúng dấu hiệu red flag.
2. Hơn 25% Top-1 hiện nằm sâu quá 68% video ⇒ có dư địa thật cho tiện lợi kiểm tra.

Chọn **`dung_sai_gan_bang = 0.03`**: chỉ 24% job có ứng viên lọt dải, và chỉ một phần
trong đó thực sự sớm hơn.

---

## 3. Phương án đã cân nhắc

| Phương án | Rủi ro độ chính xác | Rủi ro hồi quy | Dễ giải thích | Quyết định |
| --- | --- | --- | --- | --- |
| A. `score - start_seconds` hoặc cộng điểm theo vị trí | **Cao** — đoạn yếu đầu video có thể vượt đoạn mạnh cuối video | Cao | Kém | **Loại** |
| B. Weighted sum mới (confidence + duration + continuity + position) | Trung bình — trọng số không có bằng chứng, dễ thành magic number | Cao — đổi định nghĩa "tốt nhất" | Kém | **Loại** |
| C. Lọc cứng `start_ratio <= 0.5` | Cao — mất hẳn ứng viên tốt nhất ở 90% | Cao | Trung bình | **Loại** |
| D. **Giữ nguyên khoá chất lượng, thêm bước chọn đại diện trong nhóm ngang bằng** | **Thấp** — không đổi định nghĩa chất lượng | **Thấp** — 94% kết quả giữ nguyên | **Cao** | **CHỌN** |

Phương án D không đụng gì tới việc "chất lượng là gì" — nó chỉ trả lời câu hỏi mới:
*trong những ứng viên thực sự tương đương, chọn cái nào?*

---

## 4. Chính sách cuối cùng

```
1. Loại ứng viên dưới ngưỡng (min_hash_floor).           ← không đổi
2. Xếp theo chất lượng: (bằng chứng mạnh, clip chưa dùng, số hash).  ← không đổi
3. Lập nhóm NGANG BẰNG với ứng viên tốt nhất:
     - cùng bậc phân loại (mạnh/yếu, clip chưa dùng hay chưa)
     - số hash >= 97% của ứng viên tốt nhất
     - thời lượng khớp >= 97% của ứng viên tốt nhất
4. Nếu nhóm chỉ có một → chọn ứng viên tốt nhất.
5. Nếu nhiều hơn → chọn cái có chi phí kiểm tra thấp nhất.
6. Hoà tiếp → phá hoà tất định: số hash, rồi tên clip.
```

Điều kiện **thời lượng** ở bước 3 là thứ chặn ca "đoạn 20 giây ở đầu video thắng đoạn
15 phút rõ ràng": số hash có thể xấp xỉ, nhưng thời lượng thì không.

### Ranh giới chất lượng ↔ tiện lợi kiểm tra

Tiện lợi kiểm tra **không bao giờ** cạnh tranh với chất lượng — nó chỉ hoạt động
*bên trong* nhóm đã ngang bằng. Nên:

- Đoạn mạnh hơn đáng kể ở cuối video ⇒ **vẫn thắng**.
- Đoạn ngang bằng ở đầu video ⇒ thắng.
- Không có vách 50%: đoạn ở 55% vẫn hơn đoạn ở 60% nếu ngang bằng.

### Chi phí kiểm tra

```python
(round(start_s / duration, 4), start_s)
```

Dùng **cả** tỉ lệ lẫn giây tuyệt đối: 45% của video 12 tiếng vẫn là hơn 5 tiếng tua,
nên tỉ lệ một mình chưa đủ. Không biết thời lượng ⇒ lùi về giây tuyệt đối.

Dùng `start_s` chứ không phải điểm giữa vì chi phí tua của người kiểm tra gắn với chỗ
họ phải nhảy tới.

> Đây **không** phải chỉ số pháp lý. Tên trong code là `chi_phi_kiem_tra` /
> `review accessibility`, tuyệt đối không dùng từ ngữ kiểu "legal strength".

---

## 5. Tác động thật (200 job lịch sử)

| | Số job | Tỉ lệ |
| --- | ---: | ---: |
| Top-1 **giữ nguyên** | 188 | **94 %** |
| Top-1 **thay đổi** | 12 | 6 % |

Ví dụ các ca đổi:

| Job | Thời lượng video | Vị trí cũ → mới | Hash đánh đổi |
| ---: | ---: | --- | ---: |
| 291 | **50,1 h** | 70 % → **8 %** | −0,2 % |
| 279 | 4,1 h | 95 % → 49 % | −2,4 % |
| 302 | 3,1 h | 34 % → 7 % | −2,2 % |
| 172 | 2,1 h | 47 % → **0 %** | −2,5 % |

Job 291 là ca thuyết phục nhất: video 50 tiếng, Top-1 cũ nằm ở giờ thứ 35; bản mới
đưa về giờ thứ 4 mà chỉ đánh đổi **0,2 %** bằng chứng.

Tỉ lệ đổi 6 % nằm xa ngưỡng cảnh báo — chính sách chỉ chạm vào đúng các ca near-tie.

---

## 6. Không thay đổi

- `_merge()`, audfprint, ngưỡng, shifts, offset — **không đụng**. Đã review `_merge`:
  nó gộp theo hợp interval và mật độ hash, không phát hiện lỗi độc lập.
- Ngữ nghĩa `top_n`, phân bổ đều theo vùng, `uu_tien_clip_khac_nhau` — giữ nguyên.
- Cột báo cáo, contract Sheets/CSV, metadata — giữ nguyên.
- `_chon_loc` vẫn sắp kết quả theo `start_s` trước khi trả về.

---

## 7. Hạn chế còn lại

- Chưa dùng tín hiệu **liên tục** (`matched_s / (end_s - start_s)`). `_merge` đã gộp
  theo hợp interval nên đa số đoạn vốn đã liền; thêm tín hiệu này lúc chưa có bằng
  chứng nó phân biệt được ca thật sẽ là phức tạp không cần thiết.
- Chưa dùng `ty_le` (% vân tay clip khớp được) làm khoá chất lượng chính, dù CLAUDE.md
  ghi đó mới là chỉ số **chuẩn hoá** còn `hashes` phụ thuộc độ dài clip. Đổi khoá chính
  là đổi định nghĩa "tốt nhất" — việc riêng, cần dữ liệu và nghiệm thu riêng.
  **Đây là hướng tối ưu tiếp theo đáng giá nhất.**
- Ngưỡng `dung_sai_gan_bang` hiệu chỉnh trên 200 job của một số kênh; kênh có đặc tính
  âm thanh khác có thể cần giá trị khác. Đã đưa thành trường `Config` để chỉnh được
  mà không phải sửa code.
