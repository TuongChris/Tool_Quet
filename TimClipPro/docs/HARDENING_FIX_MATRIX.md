# Ma trận khắc phục TCP-01…TCP-16

Nguồn phát hiện: `TIMCLIPPRO_INDEPENDENT_AUDIT_4b7e5bd.md` (audit độc lập, revision `4b7e5bd`).
Quyết định thiết kế: `HARDENING_PLAN.md`. Nghiệm thu tổng: `HARDENING_VALIDATION_REPORT.md`.
Dữ liệu/migration: `DATA_MIGRATION_AND_RECOVERY.md`.

**Môi trường kiểm chứng:** Windows 11 Pro 10.0.26200, Python 3.12.10 của app (`.venv`, không
cài thêm gì vào đó), pytest 9.1.1 qua `PYTHONPATH` riêng, FFmpeg/FFprobe trong `bin/` của
máy chạy thật, audfprint vendored (không sửa — hash khớp baseline).

**Trước sửa:** 3 script tái hiện của audit chạy trên bản sao nguyên trạng `4b7e5bd`: **cả 14
ca tái hiện được native Windows**. Hai ca STATIC (TCP-15, TCP-16) được tái hiện thêm bằng test.

**Bằng chứng ĐỎ (test mới chạy trên bản sao nguyên trạng `4b7e5bd`):**

| Nhóm | Kết quả trên mã cũ | Ghi chú |
|---|---|---|
| G1–G5 (TCP-01/02/03/11/13/14/15/16) | 58 đỏ · 11 xanh · 2 skip | 11 xanh là test bảo vệ hành vi vốn đúng (có chủ đích); 2 skip cần quyền tạo symlink |
| G6 (TCP-04/06) `test_pham_vi_quet.py` | 15 đỏ · 1 xanh (bản đổi điểm chạm) | Module import hàm mới nên chạy bản đổi **điểm chạm** FFmpeg sang `subprocess.run` của mã cũ; assertion giữ nguyên |
| G7 (TCP-05) | đơn vị 9 đỏ · 7 xanh; audio thật: mã cũ báo đầu clip **99,81 s**, đúng là **105,88 s** | Test audio thật dùng audfprint + FFmpeg `atempo=1.02` |
| G8 (TCP-07/08) | 15/15 + 5/6 đỏ; test watch cũ bị đảo: đỏ | 1 xanh = quét đúng kho khi chọn được (bảo vệ) |
| G9 (TCP-09/12) | 5 đỏ · 8 xanh | 8 xanh là đối chứng âm (mâu thuẫn thật vẫn ambiguous, offline dùng snapshot…) |
| G10 (TCP-10) `test_tai_nen_an_toan.py` | 13 đỏ · 1 xanh (bản đổi điểm chạm) | 1 xanh = chạy lại không nhân đôi (bảo vệ). 2 test thêm sau (khoá metadata là đường dẫn cũ) đỏ trên bản đang sửa trước khi vá |

**Sau sửa:** chạy lại 3 script audit trên mã đã sửa — **không ca nào còn tái hiện**. 11/14 ca
hỏng đúng ở assertion "hành vi lỗi" (hoặc bị chặn bởi cơ chế mới: build `0 hash` bị từ chối,
writer JSON thứ hai bị khoá chặn, cháu mồ côi đã bị dọn). 3 ca (A, B, I) hỏng vì điểm chạm đã
đổi; bản chuyển điểm chạm giữ nguyên fixture + assertion (`scratchpad/reproduce_after_adapted.py`)
cho kết quả **không tái hiện** với số liệu cụ thể (xem báo cáo nghiệm thu).

Trạng thái: `REPRODUCED` · `STATIC_CONFIRMED` · `FIXED_AND_VERIFIED` (đã sửa; test mới đỏ trên
mã cũ, xanh trên mã mới; cả suite xanh; kiểm trên Windows thật) · `IMPLEMENTED_NOT_YET_VERIFIED`.

| ID | Mức | Kiểm chứng trước sửa | Nguyên nhân gốc (xác nhận) | Cách sửa | Test bảo vệ | Trạng thái | Windows | Rủi ro còn lại |
|---|---|---|---|---|---|---|---|---|
| TCP-01 | P1 | REPRODUCED (ca C, native) | Build/quét chạy trong thread nền trên CHÍNH Engine mà thanh bên sửa trực tiếp; job đọc `self.db_file`/`self.config` ở nhiều thời điểm | Mỗi job chạy trên bản sao Engine **ghim** kho + `deepcopy(Config)` (`_ban_sao_cho_job`), dùng chung cờ huỷ; build ghi sổ đăng ký theo tên kho đã ghim (không `update_kho`); kiểm đích trước khi thay file (`_kiem_dich_cong_bo`); quét kiểm chữ ký file kho trước mỗi lượt khớp (`_kiem_kho_khong_doi`); `delete_kho` lấy `tool.lock`; thanh bên khoá chọn kho khi có job | `test_kho_build_an_toan.py` (đổi kho giữa build, xoá kho giữa build, sổ đăng ký đổi file đích, đổi cấu hình giữa quét, đổi kho giữa hai lượt khớp, kho bị ghi lại giữa quét) | FIXED_AND_VERIFIED | native | Đổi kho giữa hai VIDEO của một batch: batch giữ kho lúc bắt đầu (đúng thiết kế) |
| TCP-02 | P1 | REPRODUCED (ca D, native) | Tiến trình thoát 0 + file tạm tồn tại được dùng thay cho tính hợp lệ của kho | `_kiem_kho_tam`: đọc kho tạm bằng loader của dự án; `new` 0 clip hữu ích → thất bại; `new` làm mất clip từng có hash → từ chối; `add` phải giữ đủ clip cũ, 0 clip mới hữu ích → không ghi; công bố xong đổi `revision` | `test_kho_build_an_toan.py` (0 hash, add toàn lỗi, mất clip tốt, chỉ clip mới lỗi, kho tạm rác, đổi phiên bản) | FIXED_AND_VERIFIED | native | 14 test cũ dùng "kho" là chuỗi rác được sửa test double sang kho hợp lệ (`tests/kho_gia.py`), assert giữ nguyên ý nghĩa. Chi phí: đọc thêm kho tạm/kho cũ một lần mỗi build (xem số đo) |
| TCP-03 | P1 | REPRODUCED (json race, native) | Khoá chỉ là `threading.RLock`; file tạm cố định `.tmp`; mọi writer đọc-cả-file-đầu, ghi-đè-cả-file-cuối | `luu_tru`: khoá OS theo thư mục (`.timclip.lock`, tái dùng `KhoaTienTrinh`, chờ có hạn, nêu PID chủ khoá), file tạm duy nhất, `.bak` chỉ làm mới từ bản đọc được, `os.replace` thử lại có hạn, `cap_nhat_json` (đọc-sửa-ghi một giao dịch); 7 writer chuyển sang chỉ gộp entry/trường mình đổi | `test_luu_tru_lien_tien_trinh.py` (2 process spawn + Event), `test_meta_giao_dich.py` (sync, va_metadata, sửa ngày, sửa thời lượng, máy phụ) | FIXED_AND_VERIFIED | native | Reader không khoá (resolver) có thể làm `replace` chậm một nhịp; đã có thử lại |
| TCP-04 | P1 | REPRODUCED (ca A, native) | `_cut_chunks` âm thầm bỏ khúc cắt/giải mã lỗi; phạm vi tính bằng `max(end)`; khúc vắng mặt trong output audfprint vẫn tính là đã khớp; lịch sử ghi `ok/0` nên Watch bỏ qua vĩnh viễn | Sổ phạm vi `_PhamViQuet` (khúc đã gửi, khúc lỗi, khúc không được phân tích, dừng sớm); thử lại khúc lỗi đúng một lần (không thử lại khi timeout); phạm vi thật = hợp các khoảng đã khớp, đo bằng độ dài WAV thật; `vung_loi` = phần lỗi không khúc nào phủ. Chính sách: có bằng chứng → `ok` + ghi rõ "Chưa quét trọn"; không có → `status=error` "hãy quét lại", KHÔNG thành âm tính | `test_pham_vi_quet.py` (khúc giữa lỗi, khúc cắt ngắn, lỗi tạm thời thử lại, khúc vắng mặt trong output, quét trọn âm tính, huỷ) | FIXED_AND_VERIFIED | native | Chỉ thử lại 1 lần; khúc lỗi vì timeout không thử lại (tránh treo gấp đôi). Vòng phản biện bịt thêm 5 đường (xem mục *Vòng phản biện độc lập*): khúc audfprint không đọc được (dòng stdout `Error reading`), WAV hỏng header, âm thanh ngắn hơn hình (cả mkv/webm), file tải về ngắn hơn video, lượt bù tốc độ chạy lỗi. Khúc IM LẶNG là âm tính thật, không phải lỗi (vòng 2, N1) |
| TCP-05 | P1 | REPRODUCED (ca K, native) | Trộn hệ tọa độ: mốc đầu clip tính `O + k·t_khúc − t_clip` (trừ trục clip vào trục video); "khớp từ giây thứ" tính trên trục video; mảnh có hệ số `k` khác nhau bị gộp chung | Parser giữ `he_so`; `_merge` chỉ gộp mảnh cùng `k`; đầu clip trên video = `O + k·(t_khúc − t_clip)`; `clip_offset` (trục clip) = `(vùng_khớp − đầu_clip)/k`. Đường `k = 1` cho kết quả **y hệt** công thức cũ. Không đổi ngưỡng, Top-N hay chiến lược nhận diện | `test_toa_do_bu_toc_do.py` (công thức affine 12 tổ hợp, ca audit 3420/0,98, hai mảnh qua ranh giới khúc, không gộp khác `k`, `k = 1` bất biến); `test_toa_do_audio_that.py` (slow, audfprint + FFmpeg thật, dung sai 1 s có giải thích) | FIXED_AND_VERIFIED | native | Báo cáo/lịch sử CŨ từ lượt có bù tốc độ có thể lệch `(1−k)·t_clip`; không viết lại — lịch sử cũ được đánh dấu "cần rà soát" |
| TCP-06 | P1 | REPRODUCED (ca E, native) | Top-1 dừng sớm và quét tăng dần đặt phạm vi = phần đã đi qua/cả video; "quét một phần" chỉ suy từ thời lượng nên kết quả dừng sớm được ghi như quét toàn bộ | Cờ `dung_som`; `quet_day_du` đòi hợp phạm vi ≥ thời lượng − 2 s và không vùng lỗi; lý do `dung_som`/`gioi_han_tai`/`loi_khuc`/`huy`; `dat_muc_tieu` tách khỏi độ phủ; hậu tố "[QUÉT MỘT PHẦN — …]" trong ô tên video vi phạm của CSV ngang/dọc + Sheets (**không thêm cột**: 34/16 giữ nguyên), dòng phạm vi trong hồ sơ Markdown, CLI, hộp thông báo giao diện, lịch sử | `test_pham_vi_quet.py` (Top-1 dừng sớm, báo cáo ngang/dọc không thêm cột, hồ sơ, mô tả từng lý do, kết quả cũ không bị gắn nhãn) | FIXED_AND_VERIFIED | native | Apps Script đọc cột theo tên: hậu tố nằm trong ô văn bản, không đổi kiểu cột |
| TCP-07 | P1 | REPRODUCED (ca G, native) | Bảng `jobs` không có danh tính kho/phạm vi; `ids_da_quet` lấy mọi `status=ok` toàn cục | `lichsu.db` lược đồ v1 (`PRAGMA user_version`), CHỈ THÊM cột `kho_id, kho_ten, kho_phien_ban, chinh_sach, day_du, dat_muc_tieu, pham_vi` + chỉ mục; nâng cấp tự động, idempotent, sao lưu bằng SQLite backup API; lượt quét ghi danh tính kho đã ghim (id bền, phiên bản hiệu lực = `revision` + kích thước file kho, không băm/không mtime) và chữ ký chính sách nhận diện. Tái dùng khi cùng `kho_id`, `ok`, và (dương tính, hoặc âm tính QUÉT TRỌN cùng phiên bản + cùng chính sách). Lịch sử cũ = chưa rõ kho: không chặn, không gán, không xoá. `watch --quet-lai`; cột Kho/Phạm vi trong tab Lịch sử; `lich_su.py` (chạy thử/nâng cấp/khôi phục) | `test_lich_su_theo_kho.py` (A→B âm/dương tính, kho được bổ sung qua build thật, đổi chính sách, dở/lỗi/không rõ phạm vi, lịch sử cũ, nâng cấp có sao lưu + chạy lại không đổi byte, chạy thử không ghi, khôi phục, hai tiến trình nâng cấp cùng lúc) | FIXED_AND_VERIFIED | native | Sau khi nâng cấp, lịch sử cũ không chặn → một lần quét lại (giới hạn bởi `gioi_han_moi_lan`); dương tính cũ quét lại có thể tạo dòng Sheet lặp. Kho cũ chưa có `id` dùng định danh suy từ tên; kho mặc định tự tạo và gói máy phụ nay mang `id` bền. `day_du` chỉ ghi 1 cho lượt `ok` |
| TCP-08 | P1 | REPRODUCED (ca L, native) | `_thuc_hien_giam_sat` bắt lỗi `use_kho`, ghi một dòng rồi quét tiếp bằng kho đang chọn trước đó | Fail-closed: không mở được kho yêu cầu (hoặc kho đang mở khác tên yêu cầu) → dừng TRƯỚC liệt kê/tải/quét/xuất CSV/Sheets, thông báo tiếng Việt; sổ đăng ký và lịch sử bất biến | `test_watch_kho_an_toan.py` (tên không tồn tại, sai hoa/thường: 0 lượt liệt kê/quét/xuất/ghi Sheets, hash `khos.json`/`lichsu.db` không đổi; quét đúng kho B). Test cũ `test_kho_khong_ton_tai_van_tiep_tuc_quet` khoá ĐÚNG hành vi lỗi → đảo kỳ vọng, ghi chú trong test | FIXED_AND_VERIFIED | native | Vòng phản biện mở rộng: `use_kho` kiểm đường dẫn kho TRƯỚC khi ghi sổ; Watch không chỉ định kho cũng dừng khi Engine đã lặng lẽ lùi về `data/db.pklz`; kho chưa có vân tay dừng trước khi liệt kê |
| TCP-09 | P1 | REPRODUCED (ca H, native) | Engine xếp snapshot (ưu tiên 0) trước `clips_meta.json` (10); merge giữ trường khác rỗng đầu tiên; lượt làm mới snapshot cũng đọc qua resolver đó nên snapshot cũ tự duy trì | Chính sách: `clips_meta.json` của thư mục kho là NGUỒN CHUẨN (nơi đồng bộ kênh và công cụ sửa ngày/thời lượng ghi); snapshot chỉ bù trường thiếu và thay thế khi thư mục kho offline. Khác biệt live↔snapshot ghi riêng `snapshot_lech` + cảnh báo "chạy Khôi phục metadata offline"; làm mới snapshot hội tụ về nguồn chuẩn. Không dùng mtime, không sửa hàng loạt | `test_metadata_nguon_chuan.py` (sửa ngày bằng chính `kiem_ngay_dang.repair` → nạp lại theo chữ ký file → báo cáo ngang ra ngày đã sửa; snapshot hội tụ; offline dùng snapshot; bù trường thiếu; mâu thuẫn danh tính thật vẫn ambiguous) | FIXED_AND_VERIFIED | native | Sửa trực tiếp vào snapshot (không qua `clips_meta.json`) cho trường mà live đã có giá trị sẽ không thắng — đúng chính sách, đã ghi trong tài liệu. Vòng phản biện: snapshot lệch cả MÃ VIDEO cũng hội tụ; bản `.bak` của `clips_meta.json` được coi là nguồn chuẩn khi bản chính hỏng |
| TCP-10 | P1 | REPRODUCED (ca B, native) | FFmpeg ghi thẳng tên file cuối; dò đĩa coi mọi `[ID].opus` là đã tải | Mỗi lượt sync có thư mục tạm riêng `_tam/<pid>_<uuid>`; nén vào `.dang_nen.opus` duy nhất → kiểm (mã thoát, ffprobe, độ dài ≥ 90% nguồn − 1 s) → `os.replace` sang tên cuối → metadata kèm dấu `xac_nhan_tep` → `downloaded.txt`. Dò đĩa `kiem_tep_tren_dia`: tin file có dấu khớp kích thước hoặc có cả archive + metadata, còn lại kiểm bằng ffprobe; file nghi hỏng được báo, tải lại, bản cũ chỉ chuyển vào `_hong/` SAU khi tải lại thành công (không bao giờ xoá); file tốt thiếu metadata/archive được đối soát tại chỗ (không gọi YouTube); chỉ dọn thư mục tạm của chính lượt; `liet_ke_media` bỏ `_tam`/`_hong`; "Kiểm tra còn thiếu" tính file hỏng là còn thiếu | `test_tai_nen_an_toan.py` (FFmpeg/FFprobe thật: 0 byte, rác mã thoát 0, cắt ngắn mã thoát 0, hết đĩa, huỷ, ghi metadata lỗi sau công bố, file hỏng từ bản cũ, tải lại thất bại giữ nguyên, chạy lại không nhân đôi, không probe lại file đã xác nhận, liệt kê bỏ thư mục làm việc, không dọn thư mục tạm lượt khác, kho cũ dùng ĐƯỜNG DẪN làm khoá metadata: vẫn được tin và đối soát không đẻ entry trùng) | FIXED_AND_VERIFIED | native | Sau phản biện: CHỈ tin dấu `xac_nhan_tep`; lượt đồng bộ đầu sau cập nhật ffprobe mọi file chưa có dấu MỘT lần rồi đóng dấu (đo ~17 ms/file opus 10 phút → kho 756 clip ~13 s; có tiến độ + Dừng). File không có độ dài tham chiếu được giữ nhưng không đóng dấu. Metadata đối soát lấy tiêu đề từ tên file đã làm sạch |
| TCP-11 | P1 | REPRODUCED (ca I, native) | Bộ lọc chỉ xét basename + đuôi; không xét thư mục cha, nội dung, liên kết; hậu kiểm gọi lại chính bộ lọc | Chặn theo thành phần đường dẫn, tên cookie/.env/khoá, dữ liệu chạy riêng; quét nội dung file dữ liệu; bỏ symlink/junction; thêm `.gs`/LICENSE; hậu kiểm ZIP độc lập `kiem_zip_doc_lap`; áp cả gói máy phụ; bổ sung `.gitignore`/`.dockerignore` | `test_dong_goi_bi_mat.py` (ZIP thật so với danh sách viết tay, junction thật, marker giả) | FIXED_AND_VERIFIED | native (junction) | Test symlink skip khi máy không cho tạo symlink |
| TCP-12 | P2 | REPRODUCED (ca M, native) | `_ids_from_value` lấy MỌI `[11 ký tự]` ở bất kỳ đâu (token trong tiêu đề, tên thư mục) làm mã video | Mã video trong tên file chỉ đọc ở hậu tố `[ID].đuôi` của basename (ngữ pháp bộ tải; cắt " ." cuối như Windows); mã trần và URL giữ nguyên; mâu thuẫn THẬT (metadata khác hậu tố, tên khác đường dẫn) vẫn ambiguous. Không đổi tên file, không sửa `.pklz` | `test_metadata_nguon_chuan.py` (ngoặc 11 ký tự trong tiêu đề/thư mục, đối chứng âm, NFC/NFD, hoa/thường, " ." cuối, nháy đơn + hai dấu cách); `test_danh_sach_video.py` — test cũ khoá cảnh báo mâu thuẫn GIẢ được cập nhật, thêm test cho mâu thuẫn thật | FIXED_AND_VERIFIED | native | Sau phản biện: chấp nhận đuôi bản sao của Windows (" (1)", " - Copy", " - Bản sao") và ".fNNN". Tên KHÔNG theo ngữ pháp bộ tải mà kết thúc bằng một từ 11 ký tự trong ngoặc ("…[Compilation].mp3") vẫn bị đọc như mã — không phân biệt được về cú pháp; nếu metadata có URL khác thì thành ambiguous (an toàn) |
| TCP-13 | P2 | REPRODUCED (ca F, native) | `scan_youtube`/`scan_media(file)` xoá cờ huỷ ở MỖI video; `scan_iter` không kiểm cờ giữa các video | Cờ huỷ thuộc job: chỉ xoá một lần ở đầu job (`scan_iter(xoa_co_huy=…)`, controller tự xoá); kiểm trước mỗi video; bản ghim không xoá cờ | `test_huy_batch.py` (huỷ ở metadata, callback, ranh giới, khớp file, controller thật) | FIXED_AND_VERIFIED | native | — |
| TCP-14 | P2 | REPRODUCED (spawn cleanup, native) | `terminate()` chỉ dừng worker; dò cây theo PID cha nên mất dấu cháu khi cha chết | `NhomTienTrinh`: Windows Job Object `KILL_ON_JOB_CLOSE` (ctypes), POSIX process group; dừng cháu mồ côi khi gốc thoát; runner tự vào job riêng; dọn worker kèm cây con | `test_so_huu_tien_trinh.py` (gốc thoát, gốc chết đột ngột, huỷ, worker lỗi; process đối chứng còn sống) | FIXED_AND_VERIFIED | native | Phát hiện thêm: runner cũ treo tới khi cháu mồ côi tự chết (giữ ống stdout) — đã sửa |
| TCP-15 | P2 | STATIC → REPRODUCED (test mới) | `subprocess.run` không timeout/huỷ cho FFprobe/FFmpeg | `chay_lenh_media`: FFprobe trần tổng 120 s; FFmpeg đo tiến độ `-progress`, dừng khi IM LẶNG 300 s, không hạn chót tổng; huỷ được; stdout/stderr rút liên tục, đuôi giới hạn; áp cho cắt khúc, đổi tốc độ, đo thời lượng, nén audio kênh | `test_ffmpeg_timeout.py`, `test_so_huu_tien_trinh.py` | FIXED_AND_VERIFIED | native | Ngân sách là hằng số mô-đun, chưa đưa ra giao diện |
| TCP-16 | P2 | STATIC → REPRODUCED (cmd.exe native) | Batch không ghi mã lỗi từng bước, AppTest không `sys.exit(1)`, `pause` chặn chạy tự động | Ghi mã lỗi từng bước, tổng kết `exit /b`, thiếu pytest là lỗi, `KIEMTRA_PY`/`KIEMTRA_KHONG_DUNG`, nhãn `goto` thay khối ngoặc, CRLF | `test_kiemtra_gate.py` (qua `cmd.exe`, đường dẫn có dấu cách: đạt, lỗi import, test hỏng, giao diện hỏng, thiếu pytest) | FIXED_AND_VERIFIED | native | — |

## Test cũ đã đổi — và vì sao

Không xoá test, không `skip` rộng. Các thay đổi đều nêu lý do trong chính test:

| Test | Đổi gì | Lý do |
|---|---|---|
| 14 test fingerprint/shifts dùng audfprint giả | Test double ghi kho `.pklz` HỢP LỆ (`tests/kho_gia.py`) thay vì chuỗi rác | TCP-02: kho tạm không đọc được nay bị từ chối đúng thiết kế; assertion giữ nguyên |
| `test_quet_tang_dan.py`, `test_tang_toc.py` | Vá `engine.chay_lenh_media` thay vì `subprocess.run` | TCP-15: điểm chạm FFmpeg đổi; assertion giữ nguyên |
| `test_watch.py::test_kho_khong_ton_tai_van_tiep_tuc_quet` → `..._thi_dung_truoc_khi_quet` | Đảo kỳ vọng `quet_moi == 1` → `0`, quét/xuất bị cấm | Test cũ khoá ĐÚNG hành vi lỗi TCP-08 |
| `test_watch.py::test_chay_lai_lan_hai_khong_quet_trung`, `test_engine_core.py::test_ids_da_quet_*` | Kết quả "thành công" giả mang phạm vi quét trọn (`vung_da_khop`) | TCP-07: âm tính chỉ tính là đã kiểm xong khi biết quét trọn; assertion giữ nguyên |
| `test_danh_sach_video.py::test_tieu_de_chua_ngoac_vuong_11_ky_tu_…` | `chinh_xac` False → True, bỏ cảnh báo mâu thuẫn | Test cũ khoá cảnh báo mâu thuẫn danh tính GIẢ do TCP-12; thêm test mới cho mâu thuẫn thật |
| `test_tang_toc.py::test_cut_chunks_*` (2 test) | FFmpeg giả ghi WAV hợp lệ thay vì `b"x" * 2048` | Phản biện: khúc mà header WAV không đọc được nay là cắt lỗi; hai test kiểm lưới khúc, assertion giữ nguyên |
| `test_tai_nen_an_toan.py::test_file_da_xac_nhan_khong_bi_probe_lai`, `…khoa_la_duong_dan…` | Dựng dấu `xac_nhan_tep` thay vì "archive + metadata" | Phản biện: hai sổ đó do nút bảo trì tạo được cho cả file hỏng, không còn là bằng chứng; assertion (không probe lại) giữ nguyên |
| `test_tai_nen_an_toan.py::test_liet_ke_media_bo_qua_thu_muc_tam_va_hong` | Gọi `liet_ke_media(…, bo_thu_muc_lam_viec=True)` | Phản biện: mặc định không còn bỏ thư mục tên `_tam` của người dùng; chỉ build mới bỏ |
| `test_phan_bien_doc_lap.py::test_khuc_nomatch_0_giay_la_chua_phan_tich` → `test_khuc_audfprint_loi_doc_la_chua_phan_tich` | audfprint giả nay in dòng stdout `wavfile2peaks: Error reading … skipping` như bản thật, rồi mới ghi `NOMATCH … 0.0 sec` | Vòng 2 (N1): test cũ (do chính vòng 1 viết) khoá một tiền đề SAI — khúc im lặng cũng ghi `0.0 sec`. Khẳng định (lỗi + `vung_loi`) giữ nguyên |
| `test_phan_bien_doc_lap.py::test_file_tai_ve_ngan_hon_video_khong_phai_quet_tron` | Hàm tải giả trả độ dài KHÁC ở lần tải lại (300 s rồi 420 s) | Vòng 2: trả mãi cùng file 300 s nay là dấu hiệu âm thanh YouTube ngắn thật (được chấp nhận); tải đứt thật cho độ dài thay đổi. Khẳng định giữ nguyên |
| `test_phan_bien_vong_hai.py::_kenh` (hàm tải giả) | Ghi vào `outtmpl` như yt-dlp thật thay vì cố định `tmp_dir` | Vòng 3: lần tải lại kiểm chứng đi vào thư mục mới; khẳng định giữ nguyên |
| `test_bo_sung_lam_moi_van_tay.py`: hai test vòng 2 về clip đã cách ly | Viết lại với tên có `[ID]` và bản thay thế cùng mã; thêm ca bản thay thế hỏng / không có bản thay thế / thư mục con | Vòng 3: gỡ chỉ khi bản thay thế có vân tay (test cũ gỡ cả khi không có bản thay thế — chính là lỗi reviewer B tái hiện) |

## Vòng phản biện độc lập (brief §19)

Ba reviewer chỉ-đọc, phạm vi hẹp (lịch sử/Watch; tải-nén kênh; phạm vi quét/tọa độ/metadata) rà
bản sửa và tái hiện bằng FFmpeg/audfprint thật trong thư mục nháp. Mọi phát hiện được kiểm lại
trên code trước khi sửa; mỗi bản sửa có test đỏ trước (`tests/test_phan_bien_doc_lap.py`,
`tests/test_tai_nen_an_toan.py`, `tests/test_bo_sung_lam_moi_van_tay.py`).

| Phát hiện | Mức | Mục | Sửa |
|---|---|---|---|
| Khúc audfprint không đọc được vẫn ghi `NOMATCH … 0.0 sec` (mã thoát 0) nên bị tính là đã khớp | cao | TCP-04 | Dòng stdout `Error reading` = khúc chưa phân tích; test với audfprint THẬT. (Luật "`NOMATCH` 0 giây" của bản sửa đầu SAI — khúc im lặng cũng ghi y hệt — đã bỏ ở vòng 2, xem dưới) |
| WAV hỏng header được coi như đủ độ dài | cao | TCP-04 | Header không đọc được = cắt lỗi (thử lại 1 lần) |
| Âm thanh ngắn hơn hình → đuôi bị báo lỗi mãi | trung bình | TCP-04 | Lập khúc theo độ dài LUỒNG âm thanh; phần sau đó là "không có tiếng" |
| File tải về ngắn hơn video được tính là quét trọn | trung bình | TCP-04/07 | So với độ dài YouTube; phần thiếu là vùng lỗi; bỏ file đệm cụt |
| Lượt bù tốc độ chạy lỗi vẫn ghi âm tính trọn | thấp | TCP-04/07 | Không thấy gì mà bù tốc độ thiếu khúc → vùng chưa kiểm |
| `day_du` không xét trạng thái | thấp | TCP-07 | Chỉ ghi 1 cho lượt `ok` |
| `use_kho` ghi sổ trước khi kiểm đường dẫn kho | trung bình | TCP-08 | Kiểm trong giao dịch, trước khi ghi |
| Watch không chỉ định kho chạy trên kho mặc định do Engine lặng lẽ lùi về | trung bình | TCP-08 | So sổ đăng ký với kho đang mở; kho chưa có vân tay cũng dừng |
| Kho mặc định tự tạo / gói máy phụ không có `id` bền | thấp | TCP-07 | `id` uuid; gói mang `id`/`revision` |
| `PRAGMA user_version` có thể bị hạ | thấp | TCP-07 | `max(cũ, 1)` |
| Công cụ chẩn đoán metadata đọc lịch sử toàn cục | thấp | TCP-07 | Lọc theo `kho_id`, lùi về lịch sử cũ kèm cảnh báo |
| Tin "archive + metadata" → file hỏng thành tin cậy sau hai nút bảo trì | cao | TCP-10 | Chỉ tin dấu `xac_nhan_tep`; file cũ kiểm một lần rồi đóng dấu |
| Không có độ dài tham chiếu vẫn đóng dấu file bị cắt | cao | TCP-10 | Tham chiếu từ danh sách kênh/metadata; không có thì không đóng dấu |
| Đổi tên vào kho thất bại sau khi đã cách ly → kẹt | trung bình | TCP-10 | Giữ bản cũ bằng hard link/bản chép; thay có thử lại; thất bại thì hoàn nguyên |
| Hai lượt đồng bộ / mã trùng → cách ly nhầm bản tốt | trung bình | TCP-10 | Khoá đồng bộ theo kho; lọc mã trùng; kiểm lại dấu trước khi cách ly |
| File thay lại vẫn giữ vân tay cũ khi «Bổ sung» | trung bình | TCP-10 | Clip đổi file sau lần công bố được `audfprint remove` khỏi kho tạm rồi tạo lại; test audfprint THẬT |
| Danh sách video trong kho liệt kê `_hong`/`_tam` | trung bình | TCP-10 | Bỏ hai thư mục làm việc |
| Đối soát lỗi chặn cả lượt đồng bộ | thấp | TCP-10 | Báo lỗi rồi tiếp tục |
| `liet_ke_media` bỏ `_tam`/`_hong` cho mọi nơi gọi | thấp | TCP-10 | Chỉ khi build (`bo_thu_muc_lam_viec=True`) |
| Tên trong `_hong` quá dài khi chưa bật long path | thấp | TCP-10 | Rút gọn còn mã video khi chạm 240 ký tự |
| Bước kiểm file không có tiến độ / không Dừng được | thấp | TCP-10 | Báo `i/n` và hỏi cờ huỷ trước mỗi file |
| Lời khuyên "tắt Quét tăng dần" sai cho Top-1 / vùng lỗi | thấp | TCP-06 | Lời khuyên theo đúng lý do |
| Ngữ pháp mã video bỏ sót bản sao Windows | thấp | TCP-12 | Chấp nhận " (n)", " - Copy", " - Bản sao", ".fNNN" |
| Snapshot lệch MÃ VIDEO không hội tụ; `.bak` của live bị gọi là "xung đột" | thấp | TCP-09 | Nguồn chuẩn (kể cả `.bak`) thắng snapshot cả về mã |
| `clip_offset` khi đầu clip bị kẹp về 0 (k = 1) | thấp | TCP-05 | KHÔNG đổi — hợp đồng `k = 1` bit-identical; ghi nhận là hành vi có từ trước |

## Vòng phản biện 2 — kiểm lại các bản sửa ở trên

Ba reviewer kiểm lại đúng các bản sửa vòng 1 bằng FFmpeg/audfprint thật. Kết quả kiểm lại:
lịch sử/Watch 5/7 đã sửa trọn, kênh 7/10, phạm vi quét 6/8 (+1 giữ nguyên có chủ đích). Phát
hiện nặng nhất là **hồi quy do chính vòng 1 gây ra** (N1). Mỗi mục dưới đây có test đỏ trên mã
trước khi sửa (`tests/test_phan_bien_vong_hai.py`, `tests/test_bo_sung_lam_moi_van_tay.py`), và
một phép thử đột biến hoàn tác TỪNG bản sửa trên bản chép riêng: **22/22 đột biến bị test bắt**.

| Phát hiện (kiểm lại) | Mức | Mục | Sửa |
|---|---|---|---|
| **N1 — hồi quy vòng 1:** luật "`NOMATCH` 0,0 sec = lỗi đọc" coi khúc IM LẶNG là lỗi (audfprint lấy "độ dài" từ mốc hash cuối, khúc 0 hash nào cũng ghi 0,0). Video bị tắt tiếng (Content ID) thành lỗi vĩnh viễn, Watch tải lại mãi | cao | TCP-04 | Bỏ luật 0,0 sec. Tín hiệu chính: dòng stdout `Error reading` (reviewer xác nhận đủ ở ncores 1 và 8). Lớp phòng thủ thứ hai: khúc 0 hash mà bộ đọc WAV của tool cũng không đọc được. Test audfprint THẬT: video tắt tiếng hoàn toàn → `ok`, quét trọn |
| **N2:** lượt bù tốc độ biến đuôi im lặng thành lỗi (cấu hình mặc định chạy 4 lượt); lỗi tính theo MỐC KHÚC nên hệ số chạy được che hệ số hỏng; không trừ phần khúc gối đã phủ | trung bình | TCP-04/07 | Sửa N1 + sổ bù tốc độ khoá theo (lượt, mốc); vùng chưa kiểm của MỖI lượt = khúc hỏng trừ khúc chạy được của chính lượt đó. Test audfprint THẬT: âm tính có 30 s cuối im lặng + lưới cao độ → `ok`, quét trọn |
| Âm thanh hợp lệ ngắn hơn lengthSeconds → lỗi + bỏ đệm + tải lại ở MỌI lượt (quét); dung sai `max(5 s; 0,2%)` cho video 10 giờ bỏ qua 72 s đuôi | trung bình | TCP-04/07 | Dung sai cố định 5 s. Thiếu đuôi mà chưa có bằng chứng → tải lại MỘT lần ngay: bản mới đủ → quét lại; ngắn ĐÚNG như lần trước (±1 s) → âm thanh YouTube ngắn thật, phần sau "không có tiếng", ghi chú rõ; khác → vùng lỗi như cũ. Đã có bằng chứng thì không tải lại |
| Như trên ở đồng bộ kênh (Short 15 s tiếng dừng ở giây 12: lỗi mãi) | thấp–trung bình | TCP-10 | Chỉ khi bản nén trượt kiểm VÀ chính nguồn đã ngắn: tải lại một lần; cùng độ dài → nhận, dấu `xac_nhan_tep` mang `am_thanh_ngan_hon_youtube`, bản nén vẫn phải đủ so với NGUỒN; khác → lỗi như cũ |
| `duration_media` (số đo của CHÍNH file) được dùng làm "tham chiếu" → file cụt tự xác nhận chính nó ở lượt thứ hai | trung bình | TCP-10 | Tham chiếu chỉ từ danh sách kênh / `duration` (lengthSeconds). Đối soát không ghi `duration_media` cho file chưa có tham chiếu. Số do «kiem_thoi_luong --sua» ghi cũng không thành thước đo |
| `khos.json` hỏng không có `.bak` → Engine lùi về `data/db.pklz`, Watch quét tiếp; lần mở sau còn tự dựng «Kho mặc định» | trung bình | TCP-08 | Còn bản hỏng `khos.json.hong.*` thì KHÔNG tự dựng «Kho mặc định» (cảnh báo + hướng khôi phục); Watch dừng khi sổ trống vì vừa hỏng. Cài mới chưa từng có sổ giữ hành vi cũ |
| Watch gọi `use_kho` (ghi «kho đang dùng») TRƯỚC khi biết kho chưa có vân tay | thấp | TCP-08 | Tra sổ (chỉ đọc) và kiểm file vân tay trước; lượt bị dừng không đổi kho giao diện đang chọn |
| mkv/webm: ffprobe báo độ dài luồng tiếng `N/A` → đuôi không tiếng vẫn bị báo lỗi; khúc cắt không chỉ định luồng | thấp | TCP-04 | Đọc thẻ `DURATION` khi `duration` là N/A; cắt khúc `-map 0:a:0` (đúng luồng đã đo) |
| «Bổ sung» so mốc với giờ CÔNG BỐ kho: file bị thay trong lúc build không bao giờ được làm mới; clip đã bị cách ly vẫn giữ vân tay | trung bình | TCP-10 | Sổ đăng ký lưu `moc_build` (lúc BẮT ĐẦU đọc file); so với `min(moc_build, mtime kho)`. Clip vắng có bản trong `_hong/` → `audfprint remove` khỏi kho tạm, kiểm đã thật sự ra khỏi kho. Clip vắng KHÔNG rõ lý do (ổ chưa gắn…) → giữ vân tay + cảnh báo |
| Top-1 dừng sớm bên trong lượt tải một phần / quét tăng dần chỉ được khuyên tắt tìm nhanh | thấp | TCP-06 | `scan_ui.goi_y_quet_mot_phan` đưa cả hai lời khuyên khi video vượt ngưỡng quét tăng dần |
| `cli.py kenh`: kho đang đồng bộ ở lượt khác → traceback | thấp | TCP-10 | Báo «ĐANG BẬN», mã thoát 2 (khác lỗi thật = 1) cho mọi lệnh CLI |
| Chép vào `_hong/` hỏng giữa chừng (đầy ổ) để lại bản chép dở | thấp | TCP-10 | Bản dở do chính lượt tạo (`xb`) thì gỡ; bản gốc không đổi |
| `seed_meta_tu_dia` tạo mục cho bản sao Windows → `ambiguous_video_id` | thấp | TCP-12 | Một mã video một mục; tên chuẩn `… [ID].opus` xét trước |

## Vòng phản biện 3 — kiểm lại chính các bản sửa vòng 2

Hai reviewer (phạm vi quét; kênh/build/Watch/CLI) chỉ rà các thay đổi của vòng 2, tái hiện bằng
audfprint/FFmpeg/yt-dlp thật (yt-dlp offline qua `file://`). Phát hiện nặng nhất là một lỗ **cao**
có từ vòng 1 mà vòng 2 chưa bịt: dòng stdout của nhiều worker audfprint xen nhau. Mỗi mục có test đỏ
trước (`tests/test_phan_bien_vong_ba.py`, `tests/test_phan_bien_vong_ba_quet.py`,
`tests/test_bo_sung_lam_moi_van_tay.py`) và phép thử đột biến trên mã cuối: **32/32 bị bắt**
(`scratchpad/hardening/dot_bien_v3.json`; đột biến của vòng 2 chạy lại trên mã cuối: 22/22).
Sau khi sửa, hai reviewer chạy lại đúng kịch bản tái hiện của mình: mọi phát hiện **đã sửa**
(lỗi stdout xen nhau: 0/160 khúc bị tính nhầm, trước 4/160; quét trọn 20/20 đúng, trước 6/15 sai;
kiểm im lặng — im lặng tuyệt đối, nhiễu −70/−40 dBFS, dither ±1 LSB, ù 60 Hz, sin −20 dBFS — đều
đúng), và nêu thêm 4 điểm nhỏ đã sửa ở dòng cuối bảng.

| Phát hiện | Mức | Mục | Sửa |
|---|---|---|---|
| ncores > 1 (mặc định): các worker audfprint ghi chung ống stdout, dòng xen nhau → chỉ khúc ĐẦU dòng được ghi lỗi; lỗi chen giữa dòng `Analyzed <khúc khác>` gán nhầm. Đo: 6/15 lượt quét có khúc bị khoá tạm thời ra "âm tính trọn" | **cao** | TCP-04 | Bắt MỌI lần xuất hiện, neo vào cụm "Error reading" (`RE_LOI_DOC_KHUC`). Lớp phòng thủ thứ hai theo NỘI DUNG: khúc 0 hash mà WAV không đọc được HOẶC có tiếng rõ (RMS > −50 dBFS — audfprint chuẩn hoá phổ theo đỉnh của khúc nên tiếng thật luôn sinh hash) = chưa phân tích; im lặng/nhiễu nền (−70 dBFS) vẫn là âm tính. Tiến độ đếm cả dòng `Analyzed` không có `#N` |
| mkv nhiều luồng tiếng: thẻ `DURATION` của a:0 làm phần sau bị ghi "không tiếng" dù a:1 còn tiếng (hồi quy vòng 2) | thấp | TCP-04 | Độ dài luồng tiếng chỉ dùng khi file có ĐÚNG một luồng tiếng; mốc kết thúc = `start_time` + độ dài (luồng bắt đầu trễ). Một bộ đọc chung (`channel.doc_moc_het_tieng`) cho quét và đồng bộ kênh |
| Bản tải một phần `<id>__p…` không được dọn khi không giữ đệm | thấp | TCP-04 | Bỏ ngay trước khi tải bản đầy đủ |
| "Âm thanh ngắn thật" được nhận mà không để lại dấu để rà lại | thấp (hợp lý) | TCP-07 | `ly_do_pham_vi = "am_thanh_ngan_hon"` (lịch sử: "Trọn video (âm thanh YouTube ngắn hơn …)") |
| Kênh: "lần tải độc lập thứ hai" có thể CHÍNH là file cũ (xoá thất bại vì bị giữ + yt-dlp không ghi đè) → file cụt bị đóng dấu "ngắn thật", tin vĩnh viễn | trung bình (hậu quả cao) | TCP-10 | Tải lại vào thư mục MỚI `_tam/<lượt>/lan2_<mã>` |
| Kênh: nguồn là video (client `android`) → đo luồng DÀI NHẤT (hình), nhánh "ngắn thật" không bao giờ chạy; lỗi + tải lại mọi lượt | trung bình | TCP-10 | Đo LUỒNG TIẾNG của nguồn (`do_dai_luong_tieng`), lùi về độ dài file khi không đo được |
| Sổ kho hỏng: chỉ Watch được chặn; quét/build qua giao diện và CLI vẫn dùng `data/db.pklz` (build có thể ghi vào đó) | trung bình | TCP-08 | `SoKhoHong`: `require()` chặn quét VÀ build khi sổ trống vì hỏng/mất; CLI in cảnh báo khởi động, báo gọn (mã 1, không traceback) |
| `khos.json` bị xoá mà còn `.bak` → tự dựng «Kho mặc định», lần ghi sau đè mất bản sao cuối cùng | thấp–trung bình | TCP-08 | Coi là dấu vết sổ mất: không tự dựng, không ghi đè `.bak`, chặn như trên, hướng dẫn khôi phục |
| «Bổ sung» gỡ vân tay clip đã cách ly dù bản thay thế (tên mới) không tạo được vân tay → kho không còn vân tay nào cho video đó | thấp–trung bình | TCP-10 | Chỉ gỡ SAU bước thêm, khi một clip khác CÙNG mã video có hash trong kho tạm; không có bản thay thế → giữ + cảnh báo |
| Clip trong thư mục con có `_hong/` riêng không được xét | thấp | TCP-10 | Tra `_hong/` theo đúng thư mục chứa clip (mọi cấp dưới thư mục build) |
| `cli.py watch` bận vẫn thoát mã 1; build bận ghi cả traceback | thấp | TCP-16 | `BaoCao.ban` → mã 2; build bận chỉ một dòng nhật ký |
| Đối soát báo "đã bổ sung N file" ở mọi lượt dù không đổi gì | thấp | TCP-10 | Chỉ đếm mục thật sự đổi |
| Seed metadata chỉ nhận mã từ trường `id` | thấp | TCP-12 | Nhận cả từ URL và tên khoá của mục cũ |
| Cảnh báo build in tên đã viết thường; CLI không in cảnh báo build | thấp | — | Tên gốc từ kho cũ; CLI in `canh_bao` |
| Dấu "ngắn thật" có thể rò sang lượt đồng bộ sau trên cùng đối tượng | thấp (hợp lý) | TCP-10 | Xoá ở đầu mỗi lượt |
| *Kiểm lại:* đuôi lệch DC hằng số (−45 dBFS, 0 hash) bị lớp phòng thủ nội dung coi là "có tiếng" → lỗi mãi | thấp | TCP-04 | Đo độ lệch chuẩn (RMS quanh trung bình) thay vì RMS quanh 0 |
| *Kiểm lại:* lý do "âm thanh ngắn thật" đè lý do "lỗi khúc" khi lượt đầu đã có vùng lỗi | thấp | TCP-07 | Chỉ ghi khi không có vùng lỗi |
| *Kiểm lại:* dọn `.part`/`.ytdl` khi đổi client bỏ sót thư mục `lan2_*` | thấp | TCP-10 | Dọn mọi thư mục con của lượt |
| *Kiểm lại:* sổ kho mất-còn-`.bak` — người dùng tạo kho mới thì lần ghi sổ thứ hai đè mất `.bak` | thấp | TCP-08 | Giữ một bản sao cố định `khos.json.bak.giu_<thời điểm>` ngay khi phát hiện (không bao giờ bị ghi đè) |
| *Kiểm lại (chính test chậm của vòng 3 bắt được):* mã video của bản thay thế chỉ đọc khi tên đủ dạng `<ngày> - <tiêu đề> [ID]` → kho có tên không ngày không bao giờ gỡ được bản đã cách ly | thấp | TCP-10 | Đọc hậu tố `[ID]` (chấp nhận đuôi bản sao Windows) bằng `extract_youtube_id`, cả ở seed metadata |

Còn để lại có chủ đích (ghi ở báo cáo nghiệm thu): lần tải kiểm chứng dùng cùng client/format đã
nhớ nên một kiểu cắt cụt CỐ ĐỊNH của client đó sẽ bị nhận như "ngắn thật" (có lý do riêng trong lịch
sử để rà lại); trạng thái "ngắn thật" không được lưu nên mỗi lần quét lại video đó tải hai lần; file
không có độ dài tham chiếu bên ngoài vẫn được ffprobe mỗi lượt đồng bộ (~17–22 ms/file, không ghi
gì); file nhiều luồng tiếng chỉ được quét luồng a:0 (điểm mù có từ trước, nay không còn bị coi nhầm
là "phần sau không có tiếng").
