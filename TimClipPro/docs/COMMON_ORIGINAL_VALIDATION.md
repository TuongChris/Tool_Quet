# Chế độ «Một video gốc chung cho cả lô» — Báo cáo nghiệm thu

Thiết kế: `docs/COMMON_ORIGINAL_DESIGN.md`. Nhánh `nguon-chung-ca-lo` (tách từ `f87cc85`),
worktree `ToolQuet\Tool_Quet_nguon_chung`. Báo cáo này ghi bằng chứng cho commit TÍNH NĂNG (kiểm
trên đúng nội dung commit, ngay trước khi commit). Hai commit sửa lỗi có từ trước đi ngay sau nó
trên cùng nhánh: sửa test metadata YouTube, và nhãn vùng theo thời lượng video thật. Kết quả cổng
tích hợp cuối (chạy lại toàn bộ sau cả ba commit) nằm trong báo cáo bàn giao ngoài repo, để lịch
sử giữ đúng ba thay đổi. **Chưa push, chưa triển khai lên máy chạy thật.**

## 1. Môi trường

Windows 11 Pro; Python 3.12.10 của app (`.venv` của thư mục chạy thật, chỉ dùng làm interpreter,
không cài gì vào); pytest 9.1.1 nạp qua `PYTHONPATH` shim; FFmpeg/FFprobe trong `bin\` của máy
thật (chỉ đọc); ruff 0.16.2. Không mạng, không YouTube, không Google Sheets, không dữ liệu thật
(mọi test dùng thư mục tạm).

## 2. Kết quả kiểm thử (nội dung commit tính năng)

| Bộ | Kết quả |
|---|---|
| Baseline trên worktree mới, TRƯỚC khi sửa | 1216 passed, 2 skipped (khớp nghiệm thu hardening) |
| Bộ nhanh (`pytest -q`) | 1425 passed, 2 skipped, 0 failed (1427 test, 13 test slow bỏ chọn) — 209 test mới |
| Test audio thật của chế độ mới (`-m slow tests/test_nguon_chung_audio_that.py`) | 2 passed (108 s) |
| Bộ chậm đầy đủ (`pytest -m slow`, audfprint + FFmpeg thật) | 13 passed (11 cũ + 2 mới), 0 failed, 373 s |
| `ruff check .` | All checks passed |
| `git diff --check` | sạch |
| Hash `audfprint-master/` (19 file) so với baseline | không đổi |
| Quét bí mật tập file của commit (luật `dong_goi.py` TCP-11 + mẫu token) | sạch (45 file); đối chứng dương bắt đúng khoá PEM giả |

Test mới:

| File | Nội dung |
|---|---|
| `tests/test_golden_quet_cu.py` + `tests/golden_quet.py` + `tests/golden/` (28 kịch bản) | Golden master hành vi CŨ: sinh trên `f87cc85` trước mọi sửa đổi; khoá chuỗi lần tải, cắt khúc, gọi audfprint, đổi tốc độ, thông điệp tiến độ, `ScanResult`, chẩn đoán, dòng lịch sử |
| `tests/test_muc_tieu_quet.py` | `ScanObjective`, `ung_vien_dat` (bất biến trên mọi kịch bản golden), 9 điểm quyết định ở chế độ xác minh/thu thập, không rò mục tiêu, `phien_job`, `danh_tinh_kho`; tích hợp qua parser/`_merge`/chấp nhận thật: bằng chứng bù tốc độ không làm mất A đã đạt, hai bản ghi trùng tên ra cùng `Match.clip` |
| `tests/test_nguon_chung_thuan.py` | Định danh, trạng thái bằng chứng, kết luận, xếp hạng, đại diện, cảnh báo, CSV — gồm ca bắt buộc «Top-1 mỗi video khác nhau vẫn ra A»; tên trùng không bao giờ TÌM THẤY; «không tìm thấy» mang giới hạn tới CSV |
| `tests/test_nguon_chung_ke_hoach.py` | Bộ lập kế hoạch + mô phỏng 2.000 thế giới ngẫu nhiên + 1.000 thế giới có tên trùng (mục 4) |
| `tests/test_nguon_chung_jobs.py` | Bộ điều phối với engine giả: khoá, lấy thông tin một lần + giãn nhịp, khử trùng 2 tầng, mốc ngắn nhất, link chết, kho đổi giữa lô, huỷ, không ghi lịch sử, nguồn file, tên trùng trong kho, không đọc được danh sách clip |
| `tests/test_nguon_chung_ui.py` | Helper bảng thuần + AppTest Streamlit: mặc định chế độ cũ, cần ≥2 link, màn hình đang chạy, kết quả tìm thấy / không tìm thấy (kèm giới hạn), nút Dừng, nút lưu CSV |
| `tests/test_nguon_chung_audio_that.py` (slow) | Audio thật: A có ở cả 3 file nhưng KHÔNG là Top-1 của file nào → chế độ chung ra A, mốc ±5 s, số lượt f1=1, f2=2, f3=1; ca không có nguồn chung → KHÔNG TÌM THẤY |

`tests/test_scan_thread_boundary.py`: thêm hai module mới vào guard «không đụng Streamlit».

## 3. Bằng chứng ĐỎ → XANH

* Golden (T0) xanh trên mã `f87cc85` chưa sửa, và xanh y nguyên sau mọi bước.
* Mỗi nhóm test mới đỏ trước khi cài đặt: `ImportError` (`ScanObjective`, `common_original`,
  `common_original_jobs`, helper UI) hoặc `TypeError`/`AttributeError` (`muc_tieu=`, `info=`,
  `phien_job`, `danh_tinh_kho`) — 23 test engine đỏ trước khi cài 9 điểm quyết định.
* Các test chế độ mới có phần ĐỐI CHỨNG chạy hành vi cũ ngay trong test (ví dụ chế độ cũ dừng ở
  B, không tải nốt, không bù tốc độ khi đã có B) để chứng minh khác biệt là do mục tiêu.
* Vòng kiểm cuối trước commit (design note mục 7): test tên trùng đỏ đúng lý do trước khi sửa —
  lô báo TÌM THẤY «same.opus» 2/2; xác nhận ngay dừng ở tên trùng nên video 2 không thấy A; vẫn
  chạy khi không đọc được danh sách clip; mô phỏng tên trùng xác nhận tên trùng ở 10/10 khối. Test
  bù tốc độ mới xanh ngay vì `_merge` vốn tách hệ số tốc độ — độ nhạy của nó được chứng minh bằng
  đột biến B1 (mục 4).

## 4. Kiểm đột biến (bản chép riêng, không đụng worktree)

| Đợt | Kết quả |
|---|---|
| Độ nhạy golden TRƯỚC khi sửa: đảo từng vị từ cũ (điểm 1–10, ghi chú, `dat_muc_tieu`, `so_dat_nguong`) | 14/14 bị bắt |
| Bộ lập kế hoạch/phần thuần (loại bằng lượt dở, chưa rõ = vắng, nhận bằng chứng lượt lỗi, bỏ bổ sung, 1 lượt/video, xác nhận ngay sai, giao → hợp, bỏ so kho, đại diện theo vị trí, xếp hạng theo `ty_le`) | 10/10 bị bắt (sau khi thêm 2 test và sửa 1 mẫu) |
| SAU khi cài đặt: 12 vị từ nhánh cũ (golden), 16 luật chế độ mới (engine), 9 bảo đảm bộ điều phối | 37/37 bị bắt |
| Vòng kiểm cuối: 10 luật tên trùng (T), 9 luật «không tìm thấy có giới hạn» (N), 2 luật bằng chứng bù tốc độ (B1 bỏ điều kiện hệ số tốc độ trong `_merge`, B2 xác minh không bù khi đã có nguồn khác), 2 nút AppTest (U: Dừng, lưu CSV) | 23/23 bị bắt |

Mô phỏng 2.000 thế giới (2–6 video, 1–7 video gốc, 35% thế giới có lỗi/quét dở tiêm vào):

| Kết luận | Thế giới sạch | Thế giới có lỗi |
|---|---|---|
| TÌM THẤY (có nguồn chung thật) | 890 | 378 |
| KHÔNG TÌM THẤY (không có nguồn chung thật) | 404 | 224 |
| CHƯA KẾT LUẬN | 0 | 104 |

Không dương tính giả, không âm tính giả; «chưa kết luận» chỉ xảy ra khi có lỗi. Lượt theo pha:
mốc 2.274 · nhanh 3.900 · bổ sung 1.745; 533/2.000 thế giới có video phải quét lượt 2; không
video nào quá 2 lượt.

Mô phỏng 1.000 thế giới có tên trùng (1–2 tên clip ứng với HAI video gốc khác nhau; máy quét chỉ
thấy tên): không bao giờ xác nhận một tên trùng; TÌM THẤY ⇒ nguồn chung thật, không trùng tên;
KHÔNG TÌM THẤY ⇒ không có nguồn chung nào (kể cả trùng tên); không lỗi ⇒ TÌM THẤY khi và chỉ khi
có nguồn chung không trùng tên, còn nguồn chung chỉ mang tên trùng ⇒ CHƯA KẾT LUẬN; ≤2 lượt/video.

## 5. Số đo hiệu năng (audio tổng hợp, file 6–16 phút, `chunk_s`=300, Top-1)

| Thế giới | Cách chạy | Gọi audfprint | Giây audio đã khớp | Lượt quét | Thời gian | Kết quả |
|---|---|---|---|---|---|---|
| TG1 — nguồn chung mạnh nhất ở mốc | quét cũ, mã `f87cc85` | 5 | 2.700 | 3 | 21,8 s | Top-1: G, G, G |
| | quét cũ, mã mới | 5 | 2.700 | 3 | 21,9 s | Top-1: G, G, G |
| | nguồn chung | 3 | **1.020 (−62%)** | 3 (1 trọn, 2 dừng sớm) | 13,5 s | TÌM THẤY G 3/3 |
| TG2 — nguồn chung yếu nhất, không là Top-1 ở đâu | quét cũ, mã `f87cc85` | 5 | 2.700 | 3 | 21,9 s | Top-1: B, B, C (không trả lời được câu hỏi) |
| | quét cũ, mã mới | 5 | 2.700 | 3 | 21,8 s | như trên |
| | nguồn chung | 6 | 3.000 (+11%) | 4 (3 trọn, 1 dừng sớm) | 26,3 s | TÌM THẤY A 3/3 |
| TG3 — không có nguồn chung | quét cũ, mã `f87cc85` / mã mới | 5 / 5 | 2.700 / 2.700 | 3 / 3 | 21,7 / 22,4 s | B, B, C |
| | nguồn chung | 6 | 3.000 | 4 | 26,4 s | KHÔNG TÌM THẤY (tốt nhất B 2/3) |

* Chế độ cũ trước/sau: cùng số lần gọi audfprint, cùng giây audio, cùng kết quả — chênh thời
  gian là nhiễu đo. Không có hồi quy.
* Chế độ chung rẻ hơn hẳn khi ứng viên đầu bảng của mốc là nguồn chung; khi phải bổ sung, chi phí
  cỡ «quét trọn mọi video» (cận ≤2 lượt/video).
* Với video thật nhiều giờ, chi phí chủ yếu là lượt quét TRỌN video mốc (chọn video ngắn nhất để
  giảm). Chưa đo trên YouTube thật — cần chủ dự án duyệt (mạng, nguy cơ bot-check).

## 6. Giới hạn và việc cần duyệt

* Recall TƯƠNG ĐỐI so với chế độ quét trọn cũ không giảm (chứng minh ở design note mục 3); giới
  hạn thừa hưởng: trần `max_matches` mỗi khúc, luật bù tốc độ cũ ở lượt trọn đã có ứng viên. Vì
  vậy KHÔNG TÌM THẤY không phải chứng minh tuyệt đối và luôn mang giới hạn đã được báo (mục 7
  design note).
* Tên clip có >1 bản ghi vân tay trong kho không bao giờ được xác nhận là nguồn chung — lô có thể
  CHƯA KẾT LUẬN dù thật ra các video khớp cùng một bản ghi; cần người kiểm tra hoặc dọn kho.
* V1 không đẩy Google Sheets, không ghi «Lịch sử quét»; kết quả lô mất khi đóng app nếu chưa tải/
  lưu CSV.
* Video có `keep_downloads` tắt: lượt quét lại phải tải lại (giao diện có báo).
* Cần chủ dự án duyệt: push nhánh; đo trên YouTube thật; triển khai (sau khi bản hardening đã
  nghiệm thu vận hành thật — `CLAUDE_HANDOFF_2026-09.md:56-57`).
