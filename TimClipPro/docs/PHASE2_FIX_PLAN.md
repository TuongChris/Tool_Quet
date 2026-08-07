# PHASE 2 — Kế hoạch sửa overlap và gộp hash

Ngày đo: 2026-07-29
Phạm vi Phase 2a: chỉ điều tra, benchmark, viết test đỏ và lập kế hoạch. Không sửa mã chức
năng, không chạy audfprint, không dùng dữ liệu người dùng.

Baseline trước Phase 2a:

- `231 passed, 1 skipped, 3 deselected, 0 failed`.
- Hai file test đỏ mới làm tổng suite thành
  `232 passed, 1 skipped, 3 deselected, 6 failed`.
- Chạy lại suite cũ, bỏ qua hai file test mới, vẫn đạt
  `231 passed, 1 skipped, 3 deselected`.

## 1. Chi phí overlap hiện tại

Phép tính bám đúng mã hiện tại:

```text
de_xuat = ceil(clip_dai_nhat + 30)
overlap = max(120, min(1800, de_xuat))
overlap = max(overlap, ceil(clip_dai_nhat))
if overlap >= chunk_s:
    overlap = chunk_s // 2
buoc = chunk_s - overlap
moc = range(0, int(thoi_luong_video) + 1, buoc)
```

`chunk_s = 3600`. “Số chunk” dưới đây là số file chunk hợp lệ có thời lượng lớn hơn 0;
“tổng audio” là tổng số giây mà audfprint phải phân tích sau khi cắt.

| Clip dài nhất | Overlap | Bước | Video 3h: chunk / tổng audio / hệ số | Video 12h: chunk / tổng audio / hệ số | Video 80h: chunk / tổng audio / hệ số |
|---:|---:|---:|---:|---:|---:|
| 10 phút | 630s | 2.970s | 4 / 12.690s / 1,175000× | 15 / 52.020s / 1,204167× | 97 / 348.480s / 1,210000× |
| 20 phút | 1.230s | 2.370s | 5 / 15.720s / 1,455556× | 19 / 64.650s / 1,496528× | 122 / 436.830s / 1,516771× |
| 30 phút | 1.800s | 1.800s | 6 / 19.800s / 1,833333× | 24 / 84.600s / 1,958333× | 160 / 574.200s / 1,993750× |
| 45 phút | 2.700s | 900s | 12 / 37.800s / 3,500000× | 48 / 167.400s / 3,875000× | 320 / 1.146.600s / 3,981250× |
| 50 phút | 3.000s | 600s | 18 / 55.800s / 5,166667× | 72 / 250.200s / 5,791667× | 480 / 1.719.000s / 5,968750× |
| 60 phút | 1.800s | 1.800s | 6 / 19.800s / 1,833333× | 24 / 84.600s / 1,958333× | 160 / 574.200s / 1,993750× |
| 90 phút | 1.800s | 1.800s | 6 / 19.800s / 1,833333× | 24 / 84.600s / 1,958333× | 160 / 574.200s / 1,993750× |

Khi bước chia hết thời lượng video, `_cut_chunks()` còn gọi ffmpeg một lần tại đúng EOF do
`int(tong) + 1`; file rỗng đó không được thêm vào danh sách chunk. Bảng không tính file rỗng
vào “số chunk” hoặc “tổng audio”, nhưng lần khởi động tiến trình thừa vẫn tồn tại.

### Kết luận anomaly

Anomaly được xác nhận độc lập. Với video 80 giờ:

- clip dài nhất 50 phút: overlap 3.000s, bước 600s, xử lý 5,968750 lần thời lượng gốc;
- clip dài nhất 60 phút: overlap ban đầu chạm 3.600s nên bị kẹp đột ngột về 1.800s,
  bước tăng thành 1.800s, chỉ xử lý 1,993750 lần.

Chính sách hiện tại không đơn điệu: clip dài hơn có thể làm overlap giảm và bước nhảy tăng
đột ngột. Đây là lỗi chính sách, không phải sai số làm tròn.

## 2. Benchmark seek và segment muxer

### Môi trường và phương pháp

- Windows, ffmpeg `8.1.2-essentials_build-www.gyan.dev`.
- Chỉ thực thi read-only `bin/ffmpeg.exe` và `bin/ffprobe.exe`.
- Mọi input/output nằm trong `%TEMP%`; thư mục benchmark đã được xóa trong `finally`.
- WAV: sine 440Hz, mono 11.025Hz, PCM 16-bit, 7.200s,
  158.760.078 byte.
- WebM: sine 440Hz, mono 48kHz, Opus, 7.200,008s,
  76.291.829 byte.
- File WebM do ffmpeg tạo và đóng bình thường nên có index/Cues. Nó mô phỏng tốt đường
  decode Opus trong container WebM, nhưng không chứng minh hành vi với file thiếu/hỏng index
  hoặc luồng chưa hoàn tất.
- Mỗi mốc có một warm-up ngắn không tính vào kết quả, sau đó chạy ba lần theo thứ tự đảo ngẫu
  nhiên. Lệnh đo giữ đúng thứ tự hiện tại:

```text
ffmpeg -hide_banner -loglevel error -y -ss <mốc> -t 600 -i <nguồn> \
  -vn -ac 1 -ar 11025 out.wav
```

### Thời gian seek

| Nguồn | Mốc | Lần 1 | Lần 2 | Lần 3 | Trung vị, làm tròn 0,01s |
|---|---:|---:|---:|---:|---:|
| WAV | 0s | 0,067s | 0,075s | 0,070s | 0,07s |
| WAV | 1.800s | 0,066s | 0,070s | 0,076s | 0,07s |
| WAV | 3.600s | 0,068s | 0,066s | 0,070s | 0,07s |
| WAV | 5.400s | 0,072s | 0,072s | 0,069s | 0,07s |
| WAV | 7.000s | 0,040s | 0,040s | 0,039s | 0,04s |
| WebM/Opus | 0s | 0,581s | 0,574s | 0,571s | 0,57s |
| WebM/Opus | 1.800s | 0,574s | 0,573s | 0,564s | 0,57s |
| WebM/Opus | 3.600s | 0,605s | 0,573s | 0,568s | 0,57s |
| WebM/Opus | 5.400s | 0,598s | 0,585s | 0,572s | 0,59s |
| WebM/Opus | 7.000s | 0,206s | 0,215s | 0,206s | 0,21s |

Mốc 7.000s chỉ còn khoảng 200s audio tới EOF, nên thời gian thấp hơn không phải do seek nhanh
hơn; điều quan trọng là không có dấu hiệu thời gian tăng theo vị trí ở bốn mốc đủ 600s.

### Mười hai lệnh riêng so với segment một lượt

Mỗi phép đo xử lý đủ 7.200s thành 12 đoạn 600s. Mỗi phương án chạy ba lần, đảo thứ tự theo
từng cặp:

```text
# Hiện tại: 12 tiến trình, mốc 0, 600, ..., 6600
ffmpeg ... -ss <mốc> -t 600 -i <nguồn> ... out.wav

# Thay thế: một tiến trình
ffmpeg -i <nguồn> -vn -ac 1 -ar 11025 -f segment \
  -segment_time 600 -reset_timestamps 1 out_%07d.wav
```

| Nguồn | 12 lệnh riêng, ba lượt | Trung vị | Segment, ba lượt | Trung vị | Chênh lệch |
|---|---|---:|---|---:|---:|
| WAV | 0,935s; 0,886s; 0,905s | 0,905s | 0,783s; 0,742s; 0,675s | 0,742s | segment nhanh hơn 18,0% / 1,22× |
| WebM/Opus | 6,917s; 6,725s; 6,705s | 6,725s | 6,817s; 6,376s; 6,571s | 6,571s | segment nhanh hơn 2,3% / 1,02× |

Mỗi lượt segment sinh đúng 12 file, tổng thời lượng 7.200s.

### Kết luận benchmark

Giả thuyết “seek tăng tuyến tính theo vị trí và làm tổng chi phí O(N²)” của PM **bị bác bỏ**
trong điều kiện đã đo. `-ss` đứng trước `-i` cho seek gần như hằng số trên WAV và WebM/Opus
có index/Cues. Tổng chi phí quan sát phù hợp hơn với:

```text
O(số lần khởi động ffmpeg + tổng số giây phải decode/chuyển mã + I/O WAV)
```

Segment giảm chi phí khởi động rõ trên WAV nhưng chỉ hơn 2,3% trên WebM/Opus, là nguồn gần
với file YouTube hơn. Nút thắt cần ưu tiên là số giây audio bị xử lý lặp do overlap; sau đó
mới profiling audfprint, decode Opus và I/O WAV. Không được suy rộng kết luận này sang WebM
thiếu/hỏng index nếu chưa có mẫu tổng hợp riêng.

## 3. Chính sách overlap đề xuất

### Cấu hình

Thêm trường:

```python
overlap_max_s: int = 180
```

`180s` là trần mặc định đã được PM chọn cho chế độ lấy mẫu theo vùng tương lai. Công thức đề
xuất cho Phase 2b:

```text
tran = overlap_max_s
san = min(120, tran)
de_xuat = max(san, ceil(clip_dai_nhat + 30))  # nếu có metadata
de_xuat = overlap_s                           # nếu không có metadata
overlap = min(tran, de_xuat)
```

Kết quả:

- không bao giờ vượt trần cấu hình;
- đơn điệu không giảm khi clip dài hơn, rồi phẳng sau khi chạm trần;
- bước `chunk_s - overlap` không còn nhảy tăng ngược ở mốc 60 phút;
- với bộ clip 10–90 phút và trần 180s, overlap phẳng ở 180s.

### `Config.validate()`

Giữ điều kiện overlap hiệu lực tối thiểu 60s, đồng thời bổ sung:

```text
60 <= overlap_max_s < chunk_s
60 <= overlap_hieu_luc < chunk_s
```

Nếu `overlap_tu_dong=False`, overlap thủ công vẫn phải chịu trần để hợp đồng “không bao giờ
vượt trần” luôn đúng. File cấu hình cũ chưa có khóa mới sẽ nhận mặc định 180 nhờ dataclass.
Giá trị sai kiểu vẫn bị `cau_hinh.ap_vao_config()` bỏ qua như hiện tại.

### Thay đổi chủ đích đối với bất biến cũ

Quy tắc cũ “overlap phải lớn hơn clip dài nhất” không thể đồng thời đúng với trần 180s khi
clip dài 10–90 phút. Phase 2b phải sửa quy ước này trong `CLAUDE.md` và comment `Config`;
không được để hai chính sách mâu thuẫn cùng tồn tại.

Đổi lại, clip dài nằm qua ranh giới sẽ được nhận diện thành nhiều mảnh. Vì vậy sửa overlap
phải đi cùng sửa cộng hash mảnh không chồng nhau ở mục 4. Vẫn còn rủi ro nếu từng mảnh riêng
lẻ không qua `min_hash`/`min_match_s` sơ cấp; cần test audio tổng hợp ở ranh giới trước khi
phát hành.

## 4. Thiết kế sửa `_merge`

> Cập nhật theo quyết định PM Phase 2b: quy tắc nhị phân “chồng → max, rời → cộng”
> đã bị thay thế vì vùng overlap dương có thể chứa hai nửa khác nhau của cùng một clip.

### Điều kiện cùng nhóm

Hai mảnh chỉ thuộc cùng một lần xuất hiện khi:

- cùng `clip`;
- `abs(align_a - align_b) <= dedup_s`;
- khoảng cách giữa hai interval không lớn hơn `dedup_s`.

`dedup_s` tiếp tục dùng cho cả dung sai align và khoảng trống tối đa. Nếu dữ liệu thực
cho thấy hai ngưỡng cần hiệu chỉnh độc lập, phase sau mới tách cấu hình.

### Tích phân mật độ hash lớn nhất theo đoạn

Trong mỗi nhóm, coi mảnh là interval nửa mở `[bat_dau, bat_dau + khop)`:

1. Thu thập, sắp xếp và khử trùng mọi mốc đầu/cuối để chia thành các đoạn con.
2. Với từng đoạn `[a, b)`, tìm các mảnh phủ trọn đoạn đó. Khoảng trống không có mảnh phủ
   không được tính vào hợp interval.
3. Mật độ của đoạn là `max(hash_i / khop_i)` trong các mảnh phủ; mảnh có `khop_i <= 0`
   bị bỏ để không chia cho 0.
4. `hash_uoc = round(sum((b - a) * mat_do_doan))`.
5. Nếu tra được tổng hash clip từ `db_clips()`, kết quả bị kẹp ở tổng đó. Khi chạm cận
   trên phải phát cảnh báo; nếu không tra được thì giữ nguyên ước tính và cũng cảnh báo.

Quy tắc này tự động giữ quan sát tốt hơn khi cùng nội dung được thấy nhiều lần, đồng thời
cộng đủ bằng chứng ở phần clip liền kề. Ví dụ
`[100,130)h50 + [100,130)h80 + [130,160)h80` cho `80 + 80 = 160`, không phải `140`.

Các biên thời gian:

- `vung_khop_s = min(bat_dau)` của mọi mảnh;
- `end_s = max(bat_dau + khop)` của mọi mảnh;
- `matched_s` là tổng độ dài hợp interval, không tính khoảng trống;
- `clip_bat_dau_s` tiếp tục suy ra từ align đại diện và kẹp không âm;
- `clip_offset_s` lấy theo mảnh bắt đầu sớm nhất hoặc tính lại từ
  `vung_khop_s - clip_bat_dau_s`, tránh lấy `min(t_clip)` từ một mảnh không tương ứng.

### Vai trò của `dedup_s`

Phase 2b dùng `dedup_s` cho cả dung sai align và khoảng trống tối đa để tránh thêm quá
nhiều cấu hình trong một lượt sửa.

### Ảnh hưởng tới ngưỡng chọn lọc

Không đổi `min_hash_floor=1000` hoặc `min_hash_strong=5000` ngay trong Phase 2b. Hash cộng dồn
khôi phục bằng chứng của một clip bị chia mảnh, nên một số kết quả trước đây dưới ngưỡng sẽ:

- vượt `min_hash_floor` và xuất hiện trong báo cáo;
- vượt `min_hash_strong` và được ưu tiên;
- làm tăng `so_dat_nguong`;
- thay đổi clip được `_chon_loc()` chọn vào top N.

Đây là thay đổi có chủ đích. Sau khi có test audio ranh giới, mới hiệu chỉnh ngưỡng nếu tỷ lệ
dương tính giả tăng. Overlap dương vẫn lấy max nên không được làm phồng hash.

## 5. Quyết định cho `_cut_chunks`

Giữ cách cắt từng chunk bằng `-ss` trước `-i` trong Phase 2b.

Lý do dựa trên số đo:

- không có hiệu ứng seek O(N²);
- segment chỉ nhanh hơn 2,3% trên WebM/Opus;
- segment muxer đơn giản không sinh overlap, nên không tương đương chính sách phát hiện hiện
  tại và sẽ buộc thay đổi cách ánh xạ offset;
- cách hiện tại giữ tên `chunk_<offset>.wav`, cho phép `_match_chunks()` lấy offset tuyệt đối
  trực tiếp bằng regex và hỗ trợ hủy giữa các chunk.

Không cần thay regex `chunk_(\d+)\.wav` vì không chọn segment muxer.

Một sửa nhỏ, độc lập và có test nên làm: không tạo mốc đúng bằng EOF. Dùng điều kiện
`bat_dau < tong` khi dựng danh sách mốc, để bỏ một lần gọi ffmpeg chắc chắn không sinh chunk.
Segment muxer chỉ nên được xem lại nếu profiling trên file YouTube thật cho thấy chi phí khởi
động tiến trình hoặc I/O chiếm đáng kể hơn số đo tổng hợp.

Theo quyết định PM, link vi phạm về sau phải dùng `vung_khop_s` thay vì `start_s` suy diễn.
Đây là thay đổi báo cáo riêng, không trộn vào sửa overlap/seek của Phase 2b.

## 6. Rủi ro hồi quy và test bị ảnh hưởng

### Test overlap phải đổi kỳ vọng trong Phase 2b

- `tests/test_tang_toc.py::test_overlap_tu_dong_theo_clip_dai_nhat`
- `tests/test_tang_toc.py::test_overlap_khong_bao_gio_nho_hon_clip_dai_nhat`
- `tests/test_tang_toc.py::test_kho_rong_dung_gia_tri_cau_hinh`
- `tests/test_tang_toc.py::test_overlap_lon_hon_khuc_duoc_kep_va_canh_bao`
- `tests/test_tang_toc.py::test_cut_chunks_dung_overlap_tu_dong`
- `tests/test_overlap_policy.py::test_config_co_tran_overlap_mac_dinh_180_giay`
- `tests/test_overlap_policy.py::test_overlap_khong_bao_gio_vuot_tran_cau_hinh`
- `tests/test_overlap_policy.py::test_overlap_don_dieu_khong_giam_theo_do_dai_clip`

Các test mới phải chuyển từ đỏ sang xanh. Test cũ “overlap không nhỏ hơn clip dài nhất” phải
được thay bằng hợp đồng trần; không được giữ hai kỳ vọng mâu thuẫn.

### Test `_merge` phải giữ xanh hoặc được mở rộng

- `tests/test_engine_core.py::test_merge_list_rong`
- `tests/test_engine_core.py::test_merge_loai_ket_qua_duoi_min_hash`
- `tests/test_engine_core.py::test_merge_loai_ket_qua_duoi_min_match_s`
- `tests/test_engine_core.py::test_merge_cung_clip_align_gan_nhau`
- `tests/test_engine_core.py::test_merge_cung_clip_align_cach_xa_nhau`
- `tests/test_engine_core.py::test_merge_khong_gop_hai_clip_khac_nhau`
- `tests/test_engine_core.py::test_merge_giu_hash_lon_hon`
- `tests/test_engine_core.py::test_merge_doan_chong_lan_lay_bien_ngoai_cung`
- `tests/test_engine_core.py::test_merge_sap_xep_tang_dan_theo_start_s`
- `tests/test_engine_core.py::test_merge_chi_tra_ten_file_clip`
- `tests/test_merge_hash_split.py::test_merge_manh_chong_nhau_chi_lay_hash_lon_nhat`
- `tests/test_merge_hash_split.py::test_merge_hai_manh_lien_ke_cong_hash`
- `tests/test_merge_hash_split.py::test_merge_hai_manh_roi_nhau_trong_nguong_dedup_cong_hash`
- `tests/test_merge_hash_split.py::test_merge_khoang_cach_dung_bang_dedup_van_cong_hash`

### Test thời điểm, chọn lọc và báo cáo phải chạy hồi quy

- `tests/test_thoi_diem.py::test_clip_bat_dau_bu_dung_offset`
- `tests/test_thoi_diem.py::test_khong_ra_so_am`
- `tests/test_thoi_diem.py::test_offset_bang_0_thi_khong_doi`
- `tests/test_thoi_diem.py::test_merge_sap_xep_theo_thoi_diem_clip_bat_dau`
- `tests/test_thoi_diem.py::test_bao_cao_doc_tach_moc_clip_va_vung_khop`
- `tests/test_engine_meta.py::test_scan_media_dem_so_doan_dat_nguong_truoc_khi_cat_top_n`
- `tests/test_engine_meta.py::test_scan_media_tat_ca_rong_co_so_dat_nguong_bang_khong`
- `tests/test_selection.py::test_loai_bo_ket_qua_duoi_nguong`
- `tests/test_selection.py::test_phan_bo_deu_khi_ket_qua_manh_don_o_dau_video`
- `tests/test_selection.py::test_ket_qua_tra_ve_theo_thu_tu_thoi_gian`
- `tests/test_selection.py::test_uu_tien_clip_khac_nhau`
- `tests/test_selection.py::test_khong_vuot_qua_top_n`
- `tests/test_selection.py::test_it_ket_qua_hon_top_n_van_tra_ve_du`
- `tests/test_selection.py::test_tat_ca_bi_loai_thi_tra_ve_rong_nhung_giu_danh_sach_loai`
- `tests/test_selection.py::test_khong_biet_thoi_luong_van_chay`
- `tests/test_selection.py::test_tat_phan_bo_deu_thi_lay_theo_hash`
- `tests/test_selection.py::test_danh_sach_rong`
- `tests/test_core.py::test_so_cot_luon_khop_header`
- `tests/test_bang_ngang.py::test_dung_day_du_thong_tin_nguon_va_clip_goc`
- `tests/test_dossier.py::test_dung_day_du_ho_so_va_meta`
- `tests/test_integration.py::test_toan_bo_luong_tim_dung_vi_tri`
- `tests/test_integration.py::test_khong_bao_nham_khi_video_khong_chua_clip`

Hai test integration mang marker `slow`; phải chạy riêng bằng `python -m pytest -m slow`.

### Thay đổi hành vi người dùng phải thông báo

- Số hash hiển thị tăng với clip bị chia qua ranh giới vì các phần bằng chứng không chồng
  nhau được cộng. Đây là sửa đúng có chủ đích, không phải số liệu bị nhân đôi.
- `confidence`, `ty_le`, `so_dat_nguong`, số kết quả vượt ngưỡng, clip lọt top N và thứ tự ưu
  tiên có thể thay đổi.
- `matched_s`, tổng giây vi phạm trong hồ sơ và `end_s` có thể thay đổi nếu chuyển từ span có
  khoảng trống sang độ dài hợp interval.
- Overlap nhỏ hơn làm số chunk, thời gian cắt, dung lượng WAV tạm và thời gian audfprint giảm
  mạnh; đồng thời tăng xác suất clip dài bị chia thành nhiều mảnh.
- Các vùng bị nhiều mảnh phủ chỉ lấy mật độ hash cao nhất, nên quan sát kém không kéo thấp
  quan sát tốt và vùng overlap không bị cộng lặp.
- Không đổi `Engine.HEADER` hoặc `bang_ngang.HEADER_NGANG` trong Phase 2b.

## 7. Thứ tự triển khai Phase 2b

1. Giữ hai test đỏ làm hợp đồng; bổ sung test cho mốc EOF và cấu hình cũ thiếu
   `overlap_max_s`.
2. Thêm `Config.overlap_max_s=180`, cập nhật `validate()`, lưu cấu hình và tài liệu quy ước.
3. Sửa `_overlap_thuc_te()` theo công thức có trần; cập nhật năm test kỳ vọng cũ trong
   `test_tang_toc.py`.
4. Sửa `_merge()` bằng các thành phần interval; làm bốn test hash-split xanh mà giữ toàn bộ
   test `_merge` cũ xanh.
5. Bỏ lần gọi ffmpeg ở đúng EOF; không chuyển sang segment muxer.
6. Chạy suite nhanh, rồi suite `slow` với clip tổng hợp đặt sát và vắt qua ranh giới chunk;
   so sánh hash, thời điểm, số kết quả và báo cáo trước/sau.
7. Chỉ sau khi số đo ranh giới xanh mới cân nhắc hiệu chỉnh ngưỡng. Kiến trúc lấy mẫu theo
   vùng và đổi link sang `vung_khop_s` để phase sau, không trộn vào Phase 2b.
