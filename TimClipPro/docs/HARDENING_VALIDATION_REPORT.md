# Báo cáo nghiệm thu — hardening sau audit độc lập 4b7e5bd

Ngày: 01–02/10/2026. Quyết định: `HARDENING_PLAN.md`. Từng mục: `HARDENING_FIX_MATRIX.md`.
Dữ liệu/migration: `DATA_MIGRATION_AND_RECOVERY.md`. Audit gốc không bị sửa.

## 1. Môi trường và ranh giới

| | |
|---|---|
| Máy | Windows 11 Pro 10.0.26200 (native, không WSL/Linux) |
| Interpreter | `Tool_Quet\TimClipPro\.venv\Scripts\python.exe` 3.12.10 — đúng bản app chạy; không cài/nâng gói nào; pytest 9.1.1 nạp qua `PYTHONPATH` từ thư mục nháp, `PYTHONDONTWRITEBYTECODE=1` |
| FFmpeg/FFprobe | `Tool_Quet\TimClipPro\bin` (bản app dùng) |
| Mã | worktree `Tool_Quet_hardening`, nhánh `hardening-sau-audit` từ `4b7e5bd`; chưa commit |
| Dữ liệu thật | **không đọc, không ghi** (`data\`, thư mục kho, cookie, khoá Google). Mọi phép thử dùng thư mục tạm / dữ liệu tổng hợp |
| Vendor | `audfprint-master/`: 19/19 file khớp hash chụp đầu vòng; `git status` không có thay đổi |
| Tự cập nhật | không chạy `cap_nhat.py`; worktree không bị đổi source ngoài ý muốn |

## 2. Kết quả kiểm thử

| Lượt | Trước (`4b7e5bd`) | Sau |
|---|---|---|
| Suite nhanh (`pytest -q`, `-m "not slow"`) | 955 passed, 1 skipped | **1216 passed, 2 skipped, 0 failed** (1218 test, 122 s, mã cuối) |
| Suite chậm (`-m slow`, audfprint + FFmpeg thật) | 5 passed | **11 passed, 0 failed** (208 s, mã cuối) — gồm video tắt tiếng, đuôi im lặng + bù tốc độ, khúc hỏng sau khi cắt, gỡ clip đã cách ly (bản thay thế có sẵn và thêm mới) |
| `ruff check .` | — | sạch |
| `kiemtra.bat` thật qua `cmd.exe` (`KIEMTRA_PY` = interpreter có pytest) | mã thoát 0 dù có bước hỏng (TCP-16) | **mã thoát 0, cả 3 bước `[OK]`** (128 s, mã cuối) |
| `kiemtra.bat` khi bước hỏng / thiếu pytest | — | mã thoát ≠ 0 (5 ca trong `test_kiemtra_gate.py`, chạy qua `cmd.exe`) |
| `git diff --check` | — | sạch |

Số test tăng do test mới cho 16 mục; không test cũ nào bị xoá hay `skip` rộng. Test cũ đã đổi và
lý do: `HARDENING_FIX_MATRIX.md` mục *Test cũ đã đổi*.

## 3. Bằng chứng ĐỎ trên mã cũ

Test mới được chép vào một bản sao NGUYÊN TRẠNG `4b7e5bd` và chạy ở đó:

| Nhóm | Kết quả trên mã cũ |
|---|---|
| G1–G5 (TCP-01/02/03/11/13/14/15/16) | 58 đỏ · 11 xanh (bảo vệ) · 2 skip (symlink) |
| G6 TCP-04/06 | 15 đỏ · 1 xanh — bản đổi điểm chạm FFmpeg sang `subprocess.run` của mã cũ (module gốc import hàm mới nên không nạp được trên mã cũ); assertion giữ nguyên |
| G7 TCP-05 | 9 đỏ · 7 xanh (đơn vị); audio thật: mã cũ báo đầu clip **99,81 s**, đúng là **105,88 s** |
| G8 TCP-07/08 | 15/15 + 5/6 đỏ; test watch cũ đã đảo kỳ vọng: đỏ |
| G9 TCP-09/12 | 5 đỏ · 8 xanh (đối chứng âm) |
| G10 TCP-10 | 13 đỏ · 1 xanh (bản đổi điểm chạm); 2 test thêm sau (khoá metadata là đường dẫn cũ) đỏ trên bản đang sửa trước khi vá |

Một số ca đỏ vì thiếu trường/hàm mới (ví dụ `ScanResult.vung_da_khop`); các ca then chốt đỏ ở
assertion hành vi: "vùng chưa kiểm không được báo là quét xong" (TCP-04), "lịch sử B không được
chặn video ở A" (TCP-07), "file nén dở không được nằm trong kho" (TCP-10), báo cáo ra ngày cũ dù
`clips_meta.json` đã sửa (TCP-09)…

**Vòng phản biện 2** — test mới chạy trên mã NGAY TRƯỚC từng bản sửa (JUnit trong
`scratchpad/hardening/v2_red_*.xml`):

| Nhóm | Đỏ trước sửa |
|---|---|
| N1/N2 (khúc im lặng, bù tốc độ) | 6/8 đỏ — gồm **2 test audfprint THẬT** (video tắt tiếng hoàn toàn; đuôi im lặng + bù tốc độ); 2 xanh = test bảo vệ việc bắt lỗi đọc thật |
| Thiếu đuôi khi tải / nguồn kênh ngắn / tự tham chiếu | 7 đỏ (2 xanh bảo vệ: tải đứt khác độ dài vẫn lỗi; đã có bằng chứng thì không tải lại) |
| Watch / sổ kho hỏng | 3 đỏ · 1 xanh (cài mới vẫn tự nâng cấp — bảo vệ) |
| mkv/webm, `-map 0:a:0` | 4/4 đỏ |
| «Bổ sung»: mốc build, clip đã cách ly, clip vắng | 4 đỏ (3 test cũ cùng file vẫn xanh) |
| Lời khuyên app, CLI bận, bản chép dở, seed bản sao | 7/7 đỏ (quan sát trực tiếp trên console; được xác nhận lại bằng phép thử đột biến) |

Rồi **phép thử đột biến**: hoàn tác TỪNG bản sửa vòng 2 trên bản chép riêng và chạy đúng test của
nó — **22/22 đột biến bị bắt** (`scratchpad/hardening/dot_bien_v2.json`, chạy lại trên mã cuối).
Hai đột biến lọt ở lần chạy đầu đã dẫn tới sửa định nghĩa đột biến (N2) và thêm một test cô lập
lớp phòng thủ thứ hai (tham chiếu từ `duration_media` do công cụ bảo trì ghi).

**Vòng phản biện 3** — `scratchpad/hardening/v3_red.xml`: 26 test mới đỏ trên mã ngay trước khi sửa
(7 xanh = 1 test bảo vệ "nhiễu −70 dBFS vẫn là âm tính" + 6 test cũ cùng file). Năm test thêm ở đợt
kiểm lại (lệch DC, nhãn lý do, `.part` ở `lan2_*`, giữ bản sao `.bak`, tên không có ngày) đỏ trước
khi sửa — trường hợp cuối do chính **test chậm audfprint thật** của vòng 3 bắt được. Phép thử đột
biến trên mã cuối: **32/32 bị bắt** (`dot_bien_v3.json`).

## 4. Script tái hiện của audit — trước và sau

| Ca | Mục | Mã cũ | Mã mới |
|---|---|---|---|
| A partial FFmpeg failure | TCP-04 | tái hiện | không (bản đổi điểm chạm): `status=error`, ghi rõ vùng 00:05:00–00:10:00, khúc lỗi được thử lại 1 lần |
| B failed channel encode | TCP-10 | tái hiện | không (bản đổi điểm chạm): lần sync sau tải lại, không bỏ qua |
| C live warehouse switch | TCP-01 | tái hiện | không — assertion hành vi lỗi thất bại |
| D zero-hash build | TCP-02 | tái hiện | không — build bị từ chối: "Kho mới không có clip nào có vân tay dùng được" |
| E fast Top-1 claims full | TCP-06 | tái hiện | không |
| F cancel batch | TCP-13 | tái hiện | không |
| G history dedup across warehouses | TCP-07 | tái hiện | không |
| H snapshot shadows repair | TCP-09 | tái hiện | không |
| I packager | TCP-11 | tái hiện | không (API mới `tao_goi(goc=…)`): ZIP chỉ còn `app.py` |
| K speed time reference | TCP-05 | tái hiện | không |
| L watch missing warehouse | TCP-08 | tái hiện | không |
| M title bracket identity | TCP-12 | tái hiện | không |
| JSON race (2 process spawn) | TCP-03 | tái hiện | không — writer thứ hai bị khoá chặn, không thể xen vào |
| Spawn cleanup | TCP-14 | tái hiện | không — tiến trình cháu đã bị dọn khi runner lỗi |

Kết quả thô: `scratchpad/hardening/repro_before/`, `repro_after/` (kể cả
`reproduce_after_adapted.json`). Chạy lại trên mã CUỐI (sau vòng phản biện 2):
`repro_after_v2/` (sau vòng 2) và `repro_after_v3/` (mã cuối, sau vòng 3) — vẫn **0/14 tái hiện**.

## 5. Nghiệm thu tích hợp (brief §17)

Kịch bản `nghiem_thu_tich_hop.py` chạy **audfprint + FFmpeg thật** trên dữ liệu tổng hợp —
**14/14 đạt** (chạy lại trên mã cuối sau vòng phản biện 2: vẫn 14/14,
`scratchpad/hardening/nghiem_thu_tich_hop_v2.json`; mã cuối sau vòng 3: 14/14,
`nghiem_thu_tich_hop_v3.json`):

| Yêu cầu §17 | Bằng chứng |
|---|---|
| Hai kho A/B; tạo/add/scan/chuyển kho; A không ghi vào B | build A, B thật (~10 s mỗi kho); bổ sung A → hash `.pklz` của B không đổi, `revision` A đổi |
| `.pklz` staging 0 hash; last-known-good giữ nguyên | bổ sung chỉ có clip im lặng → không ghi kho, hash A không đổi, cảnh báo nêu tên clip |
| JSON hai process thật | `test_luu_tru_lien_tien_trinh.py` (spawn + Event) + reproducer JSON race không còn tái hiện |
| Video có khúc lỗi không thành âm tính | `test_pham_vi_quet.py` + reproducer A (bản đổi điểm chạm) |
| Fast Top-1 không bị nâng thành full | `test_pham_vi_quet.py::test_top1_dung_som_khong_duoc_ghi_la_da_quet_toan_video` |
| Audio biến đổi có ground truth | `test_toa_do_audio_that.py` (atempo 1,02, mốc đầu clip 105,88 s ± 1 s) + kịch bản tích hợp: a1 ở giây 100 → báo **100,0 s** |
| Watch thất bại khi chọn kho | 0 lượt quét/xuất/Sheets, lỗi tiếng Việt "Đã dừng lượt giám sát…" |
| Metadata được sửa tới mọi exporter; snapshot offline | sửa ngày bằng `kiem_ngay_dang.repair` → báo cáo ngang 01/01 → **02/01/2026**; offline dùng snapshot (`test_metadata_nguon_chuan.py`) |
| Sync bị ngắt rồi chạy lại | `test_tai_nen_an_toan.py` (0 byte, rác, cắt ngắn, hết đĩa, huỷ, metadata lỗi sau công bố, file hỏng cũ, chạy lại không nhân đôi) |
| Cancel batch/process | kịch bản: huỷ sau video 1 → đúng 1 kết quả; Job Object (`test_so_huu_tien_trinh.py`) |
| ZIP thật không chứa bí mật; quality gate đúng mã thoát | `dong_goi.tao_goi` trên worktree (mã cuối): 216 mục, hậu kiểm độc lập sạch, không cookie/khoá/dữ liệu chạy (hai tên chứa "cookie" là file test mã nguồn `test_cookie_*.py` dùng marker giả); `kiemtra.bat` như mục 2 |
| Lịch sử: migration/recovery trên bản sao | CLI `lich_su.py` chạy thử (không ghi) → nâng cấp (có sao lưu) → khôi phục ra file mới đủ 25 dòng; bản cũ `4b7e5bd` dùng được DB v1 |
| Lịch sử theo kho với quét thật | B âm tính trọn → B chặn, A không chặn; A dương tính → tái dùng; A bổ sung → âm tính cũ phải quét lại, dương tính giữ |

Giữ nguyên các bản sửa tốt có từ trước: Arrow schema (`COT_SO`), worker không chạm Streamlit,
chính sách ngày đăng/thời lượng, xuất từng video và Sheets không chặn quét — các test cũ của chúng
vẫn xanh.

## 6. Đo hiệu năng (brief §18)

Dữ liệu tổng hợp, cùng máy, trung vị:

| Phần do bản sửa thêm | Đo |
|---|---|
| Giao dịch JSON (`cap_nhat_json`, 800 mục / 250 KB) | 25,7 ms/lần (ghi cả file kiểu cũ: 21,5 ms) |
| Lịch sử 50.000 job: truy vấn theo kho (mới) | 14,7 ms (truy vấn toàn cục cũ: 24,5 ms) |
| Nâng cấp `lichsu.db` 50.000 job + 50.000 match (15,3 MB) kể cả sao lưu | 0,09 s; lần mở sau 0,3 ms (chỉ đọc) |
| Dựng resolver metadata (800 live + 800 snapshot) | 38,8 ms |
| Đồng bộ kênh: phân loại 800 file đã xác nhận | 17 ms, **0 lần ffprobe** |
| Kiểm kho tạm `.pklz` cỡ thật (2^20×100, ~35% đầy, 187 MB nén, 800 clip) | 1,6 s; đỉnh RAM ~0,9 GB (tiến trình riêng) |
| Huỷ / timeout tiến trình | trong hạn của test (`test_so_huu_tien_trinh.py`, `test_ffmpeg_timeout.py`) |

Không tối ưu thêm: không có overhead nào vượt tầm thao tác nó bảo vệ.

Vòng phản biện 3: lớp phòng thủ theo nội dung chỉ đọc khúc 0 hash (đọc từng khối bằng numpy, khúc 200 s ≈ 4,4 MB); đo luồng tiếng vẫn là MỘT lần ffprobe; lần tải lại kiểm chứng vào thư mục mới không tốn thêm so với vòng 2.

Vòng phản biện 2 không thêm chi phí trên đường bình thường: lớp phòng thủ đọc WAV chỉ chạy cho khúc
0 hash (đọc header); ffprobe nguồn ở đồng bộ kênh chỉ chạy khi bản nén đã trượt kiểm; liệt kê
`_hong/` và đọc `moc_build` một lần mỗi build. Chi phí đáng kể duy nhất có chủ đích: video YouTube
tải về thiếu đuôi > 5 s mà không có bằng chứng được **tải thêm một lần** (đổi lại không còn vòng lặp
tải lại ở mọi lượt Watch như trước).

## 7. Reviewer độc lập (brief §19)

Ba reviewer chỉ-đọc, mỗi người một phạm vi hẹp: (1) lịch sử theo kho + Watch + sổ đăng ký;
(2) tải-nén kênh + build «Bổ sung»; (3) phạm vi quét, tọa độ bù tốc độ, metadata. Họ tái hiện
bằng FFmpeg/audfprint thật trong thư mục nháp riêng, không đụng repo. Ba vòng (vòng 3: hai reviewer,
phạm vi quét và kênh/build/Watch):

| Vòng | Phát hiện | Xử lý |
|---|---|---|
| 1 — rà bản sửa TCP-01…16 | 25 phát hiện (4 cao, 8 trung bình, 13 thấp) — bảng *Vòng phản biện độc lập* trong ma trận | 24 sửa có test đỏ trước; 1 giữ nguyên có chủ đích (`clip_offset` khi `k = 1`, hợp đồng bit-identical) |
| 2 — kiểm lại chính các bản sửa vòng 1 | Đã sửa trọn: lịch sử/Watch 5/7, kênh 7/10, phạm vi quét 6/8 (+1 giữ nguyên). Mới: **N1 (cao) — hồi quy do vòng 1**: khúc im lặng bị coi là lỗi đọc → video tắt tiếng lỗi vĩnh viễn; N2 bù tốc độ; âm thanh ngắn hợp lệ gây vòng lặp tải lại; `duration_media` tự tham chiếu; sổ kho hỏng; mkv/webm; «Bổ sung» so sai mốc; 4 việc nhỏ | 13 mục sửa — bảng *Vòng phản biện 2* trong ma trận. Mỗi mục: test đỏ trước, rồi phép thử đột biến hoàn tác TỪNG bản sửa trên bản chép riêng: **22/22 đột biến bị test bắt** (`scratchpad/hardening/dot_bien_v2.json`) |
| 3 — kiểm lại các bản sửa vòng 2 | Reviewer phạm vi quét: **1 cao** — ncores > 1 làm dòng stdout của các worker audfprint xen nhau, khúc lỗi đọc bị tính là đã phân tích (6/15 lượt quét ra âm tính trọn sai); 2 thấp; 3 hợp lý (2 sửa, 1 ghi nhận). Reviewer kênh/build/Watch: 3 trung bình (lần tải lại có thể là file cũ; nguồn video không nhận "ngắn thật"; sổ kho hỏng chỉ chặn Watch), 2 thấp–trung bình, 5 thấp; 2 hợp lý (1 sửa, 1 ghi nhận) | Tất cả sửa có test đỏ trước; 32/32 đột biến bị bắt. Hai reviewer **chạy lại kịch bản của mình trên mã mới: mọi phát hiện đã sửa** (0/160 khúc tính nhầm, 20/20 lượt đúng; kiểm im lặng/nhiễu/ù/dither đều đúng) và nêu 4 điểm nhỏ — đã sửa cùng vòng, cùng một lỗi do chính test chậm của vòng 3 bắt |

Bài học ghi lại: bản sửa N1 của vòng 1 được viết từ một giả định về định dạng output của
audfprint mà chưa đối chiếu mã nguồn vendored — test giả của chính nó khoá luôn giả định sai.
Từ vòng 2, mọi test giả của audfprint mô phỏng theo `audfprint_analyze.py`/`audfprint_match.py`
và có đối chứng bằng audfprint THẬT (`-m slow`). Vòng 3 thêm: test giả chạy MỘT tiến trình nên không
lộ được việc nhiều worker (ncores > 1, cấu hình mặc định) ghi xen nhau vào cùng ống stdout — bộ đọc
stdout của tiến trình con phải neo vào cụm từ, không vào "đầu dòng".

## 8. Chưa kiểm / giới hạn

- Không chạy với YouTube thật, Google Sheets thật, kho thật cỡ 756 clip hay video 30+ giờ (cần phê
  duyệt và mạng). Đường tải/YouTube được thay đúng ở điểm chạm `youtube_info`/`download_audio`.
- Docker chưa build lại (không có daemon trong vòng này).
- Bản đổi điểm chạm cho bằng chứng đỏ G6/G10 là bản chép riêng; module test chính thức dùng điểm chạm mới.
- Lịch sử/báo cáo cũ không được viết lại; được đánh dấu "chưa rõ — cần rà soát" (mục 4 của
  `DATA_MIGRATION_AND_RECOVERY.md`).
- Phân biệt "tải đứt" với "âm thanh YouTube ngắn thật" dựa trên hai lần tải độc lập cùng độ dài.
  Một fragment hỏng CỐ ĐỊNH ở phía YouTube, hoặc một client/format đã nhớ luôn cắt cụt đúng chỗ đó
  (lần tải kiểm chứng dùng cùng client đã nhớ), sẽ bị coi là âm thanh ngắn thật; ghi chú của lượt
  quét và lý do `am_thanh_ngan_hon` trong lịch sử nêu rõ để rà lại. Chưa gặp trên thực tế (cần
  mạng), chưa đo được tần suất YouTube phục vụ luồng tiếng ngắn hơn lengthSeconds. Trạng thái này
  không được lưu: quét lại đúng video đó lại tải hai lần.
- Đồng bộ kênh vẫn dùng ngưỡng "≥ 90% độ dài nguồn − 1 s" để bắt file cụt; thiếu đuôi nhỏ hơn mức
  đó ở kho tham chiếu chỉ làm mất phần vân tay của đuôi (không tạo âm tính sai cho video quét). File
  không có độ dài tham chiếu bên ngoài vẫn được ffprobe mỗi lượt đồng bộ (~17–22 ms/file, không ghi).
- Lớp phòng thủ theo nội dung dùng ngưỡng −50 dBFS (độ lệch chuẩn quanh trung bình). Đã kiểm với
  audfprint thật: im lặng tuyệt đối, nhiễu −70/−40 dBFS, dither ±1 LSB, ù 60 Hz, lệch DC hằng số
  đều cho kết quả đúng. Một khúc có tiếng thật mà audfprint vẫn ra 0 hash sẽ bị báo "chưa phân tích"
  (an toàn: lượt quét thành lỗi, không thành âm tính sai) — chưa gặp ca nào như vậy.
- Bắt lỗi đọc qua stdout dựa trên việc mỗi lần `print` thông điệp lỗi của audfprint được ghi liền một
  khối (đã kiểm ở ncores 1/4/8); lớp phòng thủ theo nội dung che phần còn lại.
- File có NHIỀU luồng tiếng: chỉ luồng a:0 được quét (điểm mù có từ trước); nay không còn bị coi nhầm
  là "phần sau không có tiếng".
- Khe rất nhỏ (reviewer nêu, chưa tái hiện): Watch tạo Engine trước khi lấy `tool.lock`; nếu đúng
  trong khe đó một lượt build công bố sang file kho MỚI (đường lui khi file cũ bị khoá), Watch có thể
  quét bằng file cũ của cùng kho.
