# Chế độ «Một video gốc chung cho cả lô» — Design note

Trạng thái: đã triển khai và commit cục bộ trên nhánh `nguon-chung-ca-lo` (từ `f87cc85`); chưa
push, **chưa** triển khai lên máy chạy thật. Kết quả kiểm thử và số đo:
`docs/COMMON_ORIGINAL_VALIDATION.md`.

## 1. Bài toán

Người dùng dán N link video vi phạm. Cần MỘT video gốc (clip trong kho vân tay) có mặt trong
**cả N video**, kèm một bằng chứng đại diện cho từng video — để gom một khiếu nại cho cả lô.
Chế độ cũ «mỗi video tự chọn kết quả» (Top-N từng video) không trả lời được câu này: video gốc
chung có thể không bao giờ là Top-1 của video nào.

Thiết kế này xuất phát từ một Plan do GPT soạn; Plan được coi là đặc tả cần kiểm chứng, không
phải mệnh lệnh. Mục 2 liệt kê các chỗ source `f87cc85` cho thấy Plan cần sửa.

## 2. Những giả định của Plan đã được sửa (có bằng chứng)

| # | Plan | Source `f87cc85` | Quyết định |
|---|---|---|---|
| P1 | Chỉ 3 điểm (`top_n`, `_du_de_dung_som`, `len(r.matches)`), gom vào một `objective_satisfied` | 9 điểm quyết định dừng/quét tiếp/tải tiếp, ≥5 luật khác nhau. Luật dừng giữa các đoạn đếm clip KHÁC NHAU đạt chuẩn (`engine.py:4017`), luật tải nốt đếm đoạn ĐÃ CHỌN (`:4424`) — khác nhau khi một clip chiếm nhiều suất | Nhánh cũ giữ NGUYÊN VĂN từng biểu thức; chỉ chế độ mới đi qua MỘT hàm `ScanObjective.da_dat` |
| P2 | — | Đường nhanh Top-1 (`_quet_tho`) dừng khi BẤT KỲ clip ≥5000 hash; máy thật để `top_n: 1` | Theo mục tiêu |
| P3 | — | Bù tốc độ chỉ chạy khi KHÔNG có ứng viên đạt (`:4262`), thoát khi có bất kỳ (`:4154`); vùng hỏng lượt bù chỉ tính khi `not kq.matches` (`:4290`); `_xu_ly_tai_thieu` có thể thay `r` bằng kết quả lỗi (`:4541`) | Theo mục tiêu; không mất bằng chứng |
| P4 | Không lấy thông tin video trước | Mỗi lượt quét đã gọi `youtube_info` (`:4405`); mốc phải quét TRỌN, chi phí tỉ lệ thời lượng | Lấy trước (giãn nhịp), truyền `info=` vào lượt quét — tổng request không tăng |
| P5 | Cần cache tải riêng | Đã có đệm `data/downloads` (`keep_downloads`) | Dùng đệm có sẵn |
| P6 | Khoá `kho_id + video_id`, trạng thái AMBIGUOUS | `Match.clip` chỉ là basename (`_merge` bỏ đường dẫn audfprint trả về); `[ID]` trong tên có thể giả (`X [Compilation].mp3`, `clip_metadata.py:36-37`); resolver có thể mất mã thật | Khoá = `(kho_id, basename)`; không gộp theo mã. Tên có >1 bản ghi vân tay trong kho: không bao giờ TÌM THẤY, không làm đích (mục 7) |
| P7 | Ghim kho lúc bắt đầu là đủ | Phiên bản kho chụp lại MỖI video (`:4206-4208`), lượt quét không lấy `tool.lock` | Giữ `tool.lock` suốt lô + so định danh kho/chính sách từng lượt |
| P8 | — | Báo cáo cũ tra metadata theo kho ĐANG chọn lúc vẽ | Kết quả lô đóng băng metadata bằng resolver chụp lúc bắt đầu |
| P9 | Bổ sung = quét trọn mọi video còn thiếu | Đúng nhưng đắt | Lượt bổ sung nhắm đúng phần chưa rõ, dừng khi đủ; cận vẫn ≤2 lượt/video |
| P10 | Đẩy Sheets khi tìm thấy | `KetQuaQuet` được Apps Script đọc theo tên cột | V1 không Sheets (chủ dự án chọn); xuất CSV |
| P11 | — | Lượt quét có kết quả được lưu thì Watch bỏ qua video đó mãi mãi (`ids_da_quet`) | Chế độ mới KHÔNG ghi `lichsu.db` |
| P12 | Trạng thái `VERIFIED` | Brief cấm tự điền `VERIFIED` theo nghĩa sở hữu | Trạng thái tiếng Việt; giao diện ghi rõ «không phải xác nhận quyền sở hữu» |

## 3. Ba quyết định kiến trúc

### QĐ1 — Lộ ứng viên đạt chuẩn trước Top-N mà không phá báo cáo/lịch sử

* `ScanResult.ung_vien_dat: list = field(default_factory=list, repr=False, compare=False)`, gán
  `list(dat_chuan)` ngay chỗ `so_dat_nguong` được đếm trong `_scan_media`. `dat_chuan` chính là
  tập `_chon_loc` dùng (cùng `tat_ca`, cùng config) nên đây là đúng «đạt chuẩn trước Top-N».
* Không đổi gì ở `save_job` (liệt kê cột tường minh), `to_rows` (16 cột), `bang_ngang` (34 cột),
  `dossier`; không nơi nào serialize `ScanResult`. `compare=False` giữ ngữ nghĩa `==`.
* Bất biến được test trên TOÀN BỘ kịch bản golden: `len == so_dat_nguong`, `matches ⊆
  ung_vien_dat`, bằng đúng phần đạt chuẩn của `matches + matches_loai`.
* Bác: suy ngược từ `matches + matches_loai` (dựa vào hợp đồng ngầm, ai đó cắt bớt
  `matches_loai` là mất recall lặng lẽ); giao Top-N (sai ngay ca chuẩn).

### QĐ2 — `ScanObjective` đi qua `scan_youtube → scan_media → các điểm dừng`

```python
@dataclass(frozen=True)
class ScanObjective:              # engine.py
    mode: str                     # "collect" | "verify"  (None ở nơi gọi = hành vi cũ)
    nhom_can_du: tuple = ()       # mỗi nhóm = basename clip của MỘT video gốc; đạt khi MỌI nhóm có mặt
    nhom_du_mot: tuple = ()       # đạt ngay khi MỘT nhóm có mặt (khoá đã có ở mọi video khác)
    def da_dat(self, dat) -> bool # collect: luôn False
```

* Truyền TƯỜNG MINH bằng tham số chỉ-từ-khoá `muc_tieu=` (và `info=` cho `scan_youtube`);
  `None` luôn là hành vi cũ, không kế thừa. `_scan_youtube` chỉ chuyển `muc_tieu=` xuống lượt
  quét lồng khi khác `None`, nên lời gọi kiểu cũ y nguyên và các hàm giả chữ ký cố định trong
  test cũ không vỡ.
* Bên trong một lượt, mục tiêu nằm trong sổ phạm vi `_PhamViQuet` (tạo đầu `_scan_media`, xoá ở
  `finally`) — không thể rò sang video sau hay sang Engine gốc.
* Không đụng `Config`, `top_n`, `TRUONG_CHINH_SACH` → `chinh_sach` không đổi, Watch không bị kích
  quét lại.

| # | Điểm | Cũ (nguyên văn) | collect | verify |
|---|---|---|---|---|
| 1 | đường nhanh khúc đầu `_quet_tho` | `top_n==1`, cổng ≥5000 hash | tắt | bật theo `top1_tim_nhanh`, cổng `da_dat` |
| 2 | dừng giữa các đoạn quét tăng dần | `_du_de_dung_som` | không dừng | `da_dat` |
| 3 | kích hoạt bù tốc độ | không có ứng viên đạt | như cũ | `not da_dat` |
| 4 | thoát vòng bù | có ứng viên đạt | như cũ | `da_dat` |
| 5 | vùng hỏng lượt bù → `vung_loi` | `not kq.matches` | như cũ | `not da_dat` |
| 6 | tải một phần | `_gioi_han_tai` | tải trọn | như cũ |
| 7 | tải nốt | `len(r.matches) < top_n` | — | `not da_dat` |
| 8 | tải lại khi file ngắn | `not r.matches` | luôn thử | `not da_dat` |
| 10 | `_xu_ly_tai_thieu` thay `r` | như cũ | `r_moi` lỗi mà `r` có bằng chứng → giữ `r` | như collect |

Ghi chú dừng sớm, `cd.duong_di` (`dung_som_thay_dich`) có giá trị riêng ở chế độ verify; xét
mục tiêu luôn bỏ ứng viên tự khớp. `dat_muc_tieu` và quyết định `status` giữ cách tính cũ.

### QĐ3 — Fast path → bổ sung không tạo âm tính giả

Trạng thái một cặp (video, video gốc), tính từ các lượt `status == "ok"` cùng định danh lô:
`CO_MAT` (có ứng viên đạt chuẩn ở một lượt bất kỳ, kể cả dừng sớm) > `VANG_MAT_DU` (có lượt
`quet_day_du` mà không có) > `CHUA_RO` / `LOI_QUET` / `CHUA_QUET`. Ba trạng thái cuối không bao
giờ thành «vắng mặt».

Bất biến: (I1) chỉ loại bằng `VANG_MAT_DU` — tập khả dĩ S* là giao tập ứng viên của các video
đã quét TRỌN; (I2) verify chỉ dừng khi `da_dat`, thấy nguồn khác không bao giờ làm dừng;
(I3) verify chưa đạt thì tải nốt, tải lại file ngắn, bù tốc độ cho đích trước khi có
`VANG_MAT_DU`; (I4) kho/chính sách cố định suốt lô.

Phác thảo chứng minh. Giả sử A* được một lượt quét TRỌN theo chính sách cũ chấp nhận ở cả N
video. (1) Mốc quét `collect` = lượt quét trọn cũ ⇒ A* ∈ C_mốc. (2) Mọi lượt trọn mới cắt cùng
lưới khúc, cùng kho (I4), cùng `_merge`/`loc_chap_nhan`; verify chỉ bù tốc độ NHIỀU hơn (kích
hoạt rộng hơn, thoát muộn hơn, cùng thứ tự lượt) ⇒ A* không bao giờ `VANG_MAT_DU` ⇒ A* ∈ S*.
(3) Mọi video còn chưa rõ với A* được quét với A* trong nhóm đích ⇒ hoặc thấy, hoặc chạy trọn
và (theo 2) thấy. (4) KHÔNG TÌM THẤY chỉ khi S* = ∅ — không xảy ra. Kết quả là TÌM THẤY (A* hoặc
nguồn chung khác) hoặc CHƯA KẾT LUẬN (lỗi/huỷ/kho đổi). (5) TÌM THẤY luôn có bằng chứng đạt chuẩn
ở cả N video ⇒ không thêm dương tính giả ngoài tiêu chí chấp nhận sẵn có.

Giới hạn thừa hưởng chế độ cũ (recall TƯƠNG ĐỐI không giảm): trần `max_matches` mỗi khúc có thể
che clip rất ngắn trong khúc dày nhạc hiệu; lượt quét trọn đã có ứng viên đạt chuẩn thì không thử
bù tốc độ (luật cũ, áp cho video mốc). Vì vậy KHÔNG TÌM THẤY nghĩa là «không tìm thấy trong phạm vi
đã quét», không phải «chắc chắn không có»: kết luận mang `gioi_han` nêu đúng các điều lượt quét
trọn đã báo (mục 7).

## 4. Thuật toán (`common_original.py` thuần + `common_original_jobs.py`)

1. Giữ `data/tool.lock` («quét nguồn chung cả lô»), ghim job (`Engine.phien_job()`), chụp định
   danh `(kho_id, kho_phien_ban, chinh_sach)` (kho rỗng định danh → không chạy), chụp resolver.
2. Khử trùng offline (mã trong URL), lấy `youtube_info` từng video có giãn nhịp
   (`ytdlp_sleep_requests_s`), khử trùng lần 2 theo mã thật. Link chết → dừng ngay. Cần ≥2 video.
3. `dieu_phoi` lặp: kết luận → `buoc_tiep` → quét → ghi, tới khi dứt điểm:
   * chưa video nào trọn: `collect` video ngắn nhất (mốc); mốc lỗi → video kế;
   * pha nhanh: ứng viên đầu bảng của mốc (mạnh → đoạn khớp dài → hash) — mỗi video chưa quét
     một lượt `verify(nhom_can_du={t}, nhom_du_mot=khoá đã có ở mọi video khác)`;
   * bổ sung: video còn chưa rõ với phần tử của S* được thêm MỘT lượt
     `verify(nhom_can_du=S* ∩ chưa rõ, nhom_du_mot=khoá xác nhận ngay)`;
   * cận ≤2 lượt/video ⇒ luôn dừng.
4. Kết luận: khoá KHÔNG trùng tên có mặt ở cả N → TÌM THẤY (nhiều khoá: số video có bằng chứng
   mạnh → đoạn khớp ngắn nhất dài nhất → `ty_le` thấp nhất cao nhất); S* = ∅ → KHÔNG TÌM THẤY
   (kèm «ứng viên tốt nhất k/N» và giới hạn của kết luận); S* chỉ còn khoá trùng tên → CHƯA KẾT
   LUẬN (nêu tên trùng); còn lại CHƯA KẾT LUẬN; huỷ → ĐÃ DỪNG. Không âm thầm chuyển về «mỗi video
   một nguồn».
5. Đại diện mỗi video = `chon_dai_dien` (chất lượng trước, vị trí chỉ phá hoà gần bằng).
   Cảnh báo: tên trùng trong kho, chỉ đạt nhờ phủ vân tay cao, link có thể chính là video gốc,
   mâu thuẫn giữa hai lượt quét.

## 5. Ngoài phạm vi V1

Đẩy Google Sheets (tab riêng); gộp khoá theo mã có điều kiện resolver; mốc «lười» (quét mốc
tăng dần — vẫn vừa bộ lập kế hoạch và cận 2 lượt); quét tiếp từ chỗ dừng thay vì quét lại từ 0;
bù tốc độ theo độ trôi cho lượt `collect`; lệnh CLI; radio ở tab quét file; tự thử lại video lỗi;
sổ «tác phẩm» bền; đo trên YouTube thật.

## 6. Phát hiện phụ (hành vi cũ — KHÔNG sửa trong commit tính năng này)

Hai lỗi có từ trước, sửa ở hai commit RIÊNG ngay sau commit này để xem lại/hoàn tác được độc lập:

* Sau khi TẢI MỘT PHẦN, nhãn Đầu/Giữa/Cuối tính theo độ dài file 3 tiếng chứ không theo video
  thật (`_gan_chi_so(tat_ca, tong)` dùng `tong` của file; `_scan_youtube` chỉ sửa `duration_s`).
* `tests/test_engine_meta.py` (dòng ~178 và ~213) giả `download_audio` bằng `lambda *args` trong
  khi lời gọi thật truyền `gioi_han_giay=` — test đi vào nhánh lỗi và vẫn xanh vì chỉ kiểm metadata.

## 7. Kiểm tra cuối trước commit (vòng tích hợp)

**Tên trùng trong kho.** `_merge` đặt `Match.clip = os.path.basename(g["clip"])`
(`engine.py`, đoạn dựng `Match` trong `_merge`), dù audfprint trả đường dẫn đầy đủ của bản ghi.
`dir1/same.opus` (nội dung A) và `dir2/same.opus` (nội dung B) vì thế cho cùng `"same.opus"` —
test tích hợp `test_hai_ban_ghi_cung_ten_ra_cung_match_clip_va_lo_khong_tim_thay_gia` tái hiện
đúng điều này qua parser và `_merge` thật, và cho thấy nếu không chặn thì lô báo TÌM THẤY giả.
Không đổi định danh toàn dự án ở vòng này. Thay vào đó:

* bộ điều phối đếm bản ghi theo tên từ `db_clips()` lúc bắt đầu
  (`common_original.dem_ten_kho`); không đọc được danh sách thì không chạy lô;
* tên có >1 bản ghi không bao giờ thành TÌM THẤY. Nó không làm đích nhanh, không nằm trong nhóm
  đích hay nhóm xác nhận ngay — tức không bao giờ làm một lượt quét dừng sớm;
* loại bằng bằng chứng âm vẫn đúng với tên trùng (vắng tên ⇒ vắng mọi bản ghi mang tên đó). Vì
  vậy S* chỉ còn tên trùng → CHƯA KẾT LUẬN kèm lý do; tên trùng có mặt ở mọi video bên cạnh một
  nguồn chung rõ ràng → được nêu trong cảnh báo, không tính;
* mô phỏng 1.000 thế giới có tên trùng (`test_mo_phong_ten_trung_khong_tao_nguon_chung_gia`)
  khoá: không xác nhận tên trùng, không dương tính/âm tính giả, không lỗi ⇒ TÌM THẤY khi và chỉ
  khi có nguồn chung không trùng tên.

**Độ đủ của ứng viên.** Trần `max_matches` chạm ở gần như mọi lượt quét thật: 11/11 video trong
`docs/ZERO_MATCH_ROOT_CAUSE.md` mục 9. Hạ mọi KHÔNG TÌM THẤY có chạm trần thành CHƯA KẾT LUẬN sẽ
làm chế độ này không bao giờ nói được «không tìm thấy». Bù bằng cách nâng `max_matches` là đổi
chính sách nhận diện, ngoài phạm vi. Chọn phương án «cảnh báo phù hợp»:

* nhãn đổi thành «Không tìm thấy video gốc chung» (không còn «Không có»);
* `KetLuan.gioi_han` / `KetQuaLo.gioi_han` nêu đúng điều lượt quét TRỌN đã báo: số khúc chạm
  trần, số lượt trọn không thử bù tốc độ, hoặc bù tốc độ đang tắt;
* giới hạn hiện ở giao diện (hộp thông tin, không chìm trong chú thích) và ở cột «Ghi chú» của
  MỌI dòng CSV, cùng các cảnh báo của lô.

**Bằng chứng thêm từ lượt bù tốc độ.** `_merge` không bao giờ gộp mảnh của hai hệ số tốc độ khác
nhau (điều kiện `g["he_so"] == he_so(x)`, audit TCP-05), nên bằng chứng bù chỉ THÊM ứng viên. Test
`test_bang_chung_them_tu_luot_bu_toc_do_khong_lam_mat_A_da_dat` khoá điều đó qua parser, `_merge`
và chấp nhận thật, ở hai dạng: đoạn đổi tốc độ nằm chỗ khác, và đoạn đổi tốc độ chồng đúng vùng
của A thường. A của lượt thường phải giữ nguyên từng trường, so với đối chứng ở chế độ cũ.
