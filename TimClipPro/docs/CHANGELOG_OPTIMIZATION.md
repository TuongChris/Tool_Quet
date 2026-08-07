# Changelog audit và tối ưu

Ngày: 2026-08-06.

## Vòng điều tra zero-match + Fast Top-1 — 2026-08-07

Bối cảnh: 11 video báo "quét xong 0 đoạn". Điều tra kết luận **cả 11 đều là âm tính
đúng** — chúng là video parody lồng tiếng lại, chỉ có nhạc hiệu dùng chung khớp được
(phủ vân tay 0,5–0,9% so với 20–100% của một bản reup thật). Chi tiết số liệu:
[ZERO_MATCH_ROOT_CAUSE.md](ZERO_MATCH_ROOT_CAUSE.md).

Giả thuyết "ngưỡng 1000 hash cao hơn tổng hash của clip gốc" đã bị **bác bỏ bằng số
đo**: kho SML đang dùng có clip ít hash nhất là 6.239, không clip nào dưới 1000.

| File | Nội dung và lý do | Rủi ro | Test xác minh | Trước → Sau |
|---|---|---|---|---|
| `chan_doan_quet.py` (mới) | Phễu phát hiện: đếm ứng viên sống sót từng tầng, mã hoá 6 giai đoạn mất kết quả, ảnh chụp ứng viên mạnh nhất bị loại | Low | 12 test thuần | 0 kết quả không phân biệt được với bug → luôn chỉ đúng tầng đã mất |
| `chap_nhan_khop.py` (mới) | Chấp nhận hai bậc: tuyệt đối (luật cũ) **hoặc** phủ vân tay cao + đủ dài + đủ dày | Low | 9 test thuần | Clip gốc < 1000 hash không bao giờ báo được → nhận được khi khớp gần hết |
| `engine.py` | Bỏ `--sortbytime` (sửa cắt cụt sai), `_quet_tho()` đường đi nhanh Top-1, nối chẩn đoán, lưu JSON chẩn đoán cho ca 0 kết quả | Medium | 10 test + kiểm chứng 11 video thật | Cắt cụt theo thời gian làm mất 207 dòng khớp/khúc → cắt theo độ mạnh |
| `app.py` | Thay lời khuyên "hạ ngưỡng xuống 60%" bằng bảng chẩn đoán phễu + cảnh báo nhạc hiệu dùng chung | Low | Full fast suite | Lời khuyên cũ tạo dương tính giả (job 364: 126 hash/10s) → giải thích đúng |
| `cli.py` | In phễu + ứng viên mạnh nhất bị loại thay cho "Không tìm thấy clip gốc nào." | Low | Full fast suite | Một dòng vô nghĩa → chẩn đoán đủ để hành động |
| `tests/test_chan_doan_zero_match.py` (mới) | 31 test: chấp nhận, phễu, parser trên dòng thật, đường đi nhanh Top-1 | Low | 31 pass | Không có → khoá lại hành vi |

Hành vi ảnh hưởng người dùng: kết quả 0 đoạn nay luôn nói mất ở tầng nào và ứng viên
mạnh nhất thiếu bao nhiêu; `top_n=1` trên video từ 3 khúc trở lên có thể dừng sớm khi
gặp bằng chứng rất mạnh ở phần đầu.

**Đánh đổi phải biết của Fast Top-1.** Đo trên `n4Ca9SmTfi0` (6,7 giờ, 8 khúc):
quét toàn bộ 326,9s chọn clip phủ 81,2% ở 01:29:28; fast Top-1 **98,1s (−70%)** chọn
clip phủ 73,2% ở 00:25:18. Cả hai đều là reup thật trên 10.000 hash và khớp liên tục
trên 9 phút — khác nhau chỉ ở thứ tự xếp hạng theo `ty_le`. Fast Top-1 cam kết trả về
bằng chứng **rất mạnh**, không cam kết trả về ứng viên **tối ưu toàn cục**. Cần đúng
hành vi cũ thì đặt `top1_tim_nhanh = False`.

Không thay đổi: `_merge()`, `min_hash_floor`, `min_hash_strong`, thuật toán xếp hạng
Top-N, `chon_dai_dien()`, schema SQLite, định dạng vân tay, hợp đồng báo cáo/Sheets,
audfprint vendored. `so_dat_nguong` giữ nguyên ý nghĩa.

## Vòng sửa lệch 1 giây ở thời lượng — 2026-08-07

Báo cáo ghi 5:53:40 cho `D-sVTRR5jm0` trong khi YouTube hiển thị 5:53:39. Chi tiết
số đo: [DURATION_DRIFT_AUDIT.md](DURATION_DRIFT_AUDIT.md), chính sách:
[DURATION_ARCHITECTURE.md](DURATION_ARCHITECTURE.md).

**Giá trị sai đầu tiên là formatter, không phải nguồn dữ liệu.** Đọc thẳng trên trang
YouTube (`.ytp-time-duration` và `video.duration`): media thật dài 21219,981 giây, UI
hiển thị 5:53:39, còn `lengthSeconds` (nguồn của yt-dlp) là 21220. Giá trị FFprobe mà
tool đang lưu **trùng khít** `video.duration` của YouTube — tức dữ liệu vốn đã đúng và
chính xác hơn metadata YouTube. Trình phát hiển thị thời gian media bằng cách **cắt**
phần lẻ, còn `hhmmss()` lại `round()`.

Giả thuyết được nêu khi giao việc (báo cáo đang lấy nhầm thời lượng file audio trung
gian, nên phải tách `source_duration`/`processing_duration` và lấy yt-dlp làm canonical)
**bị bác bỏ bằng số đo** — làm vậy sẽ hiển thị 5:53:40, đúng cái đang sai.

| File | Nội dung và lý do | Rủi ro | Test xác minh | Trước → Sau |
|---|---|---|---|---|
| `engine.py` | `hhmmss()` cắt phần lẻ thay vì làm tròn | Medium | 26 test + mô phỏng 387 job thật | 47% video báo dư 1 giây → khớp UI YouTube |
| `clip_metadata.py` | Đọc `duration_media` (độ dài đo từ file), ưu tiên hơn `duration` | Low | 4 test | Clip gốc chỉ có số nguyên đã làm tròn → có độ dài thật |
| `channel.py` | `do_dai_media()`; sync mới ghi kèm `duration_media` | Low | Full suite | Clip mới tự có độ dài chính xác |
| `kiem_thoi_luong.py` (mới) | Kiểm tra/bổ sung `duration_media` cho kho cũ, mặc định chỉ đọc | Low | Chạy thật 3 kho | Không có → audit được 2.600 clip |
| `tests/test_thoi_luong.py` (mới) | 26 test dựa trên số đo thật từ YouTube | Low | 26 pass | Không có → khoá lại chính sách |

Mô phỏng luật cũ/mới trên **toàn bộ 387 job** trong `lichsu.db`: **182 giảm 1 giây
(47,0%), 205 giữ nguyên (53,0%), 0 tăng lên.** Nhóm giữ nguyên chính là các video
người dùng đã thấy đúng từ trước. Video > 24 giờ vẫn đúng (35:01:20).

Mốc đoạn khớp cũng đổi ở 500/1.199 match (41,7%) — đây là **sửa mâu thuẫn có sẵn**:
link `?t=` vốn luôn dùng `int()`, nên trước đây báo cáo ghi 00:24:02 mà bấm link lại
nhảy tới 00:24:01. Nay cả hai đều là 00:24:01.

Không thay đổi: `ScanResult.duration_s` giữ nguyên ngữ nghĩa và giá trị; hình học cắt
khúc/so khớp vẫn dùng float đầy đủ; `app._thoi_luong()` (đã chạy/ETA) không đụng tới;
tên cột báo cáo giữ nguyên; kho vân tay và `clips_meta.json` chưa bị ghi.

Việc còn lại: 2.600 clip trong 3 kho chưa có `duration_media` nên clip gốc vẫn dư 1
giây ở khoảng 48% ca — chạy `kiem_thoi_luong.py --sua --that-su` khi người dùng duyệt.

## Vòng siết bậc A bằng mật độ — 2026-08-07

Theo yêu cầu người dùng. Đây là thay đổi **duy nhất trong cả đợt có thể lấy đi kết
quả**, nên hiệu chỉnh trên toàn bộ 1.199 match đã từng báo cáo trong `lichsu.db`.

Số đo cho kết quả ngược với kỳ vọng: mật độ thấp nhất trong lịch sử là **9,99 hash/s**
(p1 = 11,52; trung vị = 16,84). Không có match thật nào thưa, nên mọi ngưỡng từ 0,5
đến 5,0 hash/s loại **0/1.198** kết quả, còn từ ~10 trở lên thì cắt vào bằng chứng
thật ngay. Ca thưa thật (309 hash / 578,6s = 0,53 h/s) vốn đã bị sàn 1000 loại từ trước.

Kết luận: triển khai như **rào chắn**, không phải bộ lọc. `mat_do_bac_a = 3,0` — cách
mức thấp nhất thật 3,3 lần, mô phỏng trên 1.199 match cho **0 mất, 0 thêm**, nhưng vẫn
chặn ca bệnh lý 1.200 hash trải 2.000 giây. `validate()` từ chối giá trị > 9,0 để chặn
gõ nhầm. Để riêng khỏi `mat_do_toi_thieu` để siết bậc B không vô tình siết luôn bậc A.

Lý do loại nói rõ "quá loãng" thay vì "thiếu hash", tránh việc người dùng đi hạ nhầm
`min_hash_floor`. Sửa thêm một fixture test dùng mật độ 1,7 hash/s — loãng hơn thực tế
6 lần nên vô tình đo nhầm rào chắn thay vì đo ngưỡng hash.

## Vòng bù đa tốc độ — 2026-08-07

Bịt điểm mù đổi tốc độ đã đo ở vòng trên. Chi tiết: [DA_TOC_DO.md](DA_TOC_DO.md).

Quyết định kiến trúc: **không quét mù nhiều tốc độ.** Lưới bước 1% để lại sai số tồn
dư 0,5%, mà 0,5% đã làm mất 93% bằng chứng — muốn bằng chứng mạnh phải trúng tới ~0,1%,
tức hàng chục lượt quét. Thay vào đó khai thác một tính chất toán học: khi video phát
ở tốc độ `r`, align của các mảnh khớp **trôi tuyến tính** với độ dốc đúng bằng `(1−r)`.
Hồi quy độ dốc là ra tốc độ — dữ liệu đã nằm sẵn trong output lượt quét thường, tốn
**0 giây** so khớp thêm, sai số đo được ≤0,05% (chính xác hơn lưới 1% khoảng 100 lần).

| File | Nội dung và lý do | Rủi ro | Test xác minh | Trước → Sau |
|---|---|---|---|---|
| `toc_do_khop.py` (mới) | Ước lượng tốc độ bằng hồi quy **Theil–Sen** trên độ trôi align; bộ lọc ffmpeg cho 2 họ biến đổi | Low | 33 test thuần | Không có → đọc được tốc độ, sai số ≤0,05% |
| `engine.py` | `_quet_da_toc_do()` có vòng tinh chỉnh lặp; quy đổi mốc thời gian theo hệ số mã trong tên khúc | Medium | 4 ca fixture thật + đối chứng âm | Video bị đổi tốc độ = 0 kết quả → tìm ra đúng clip |
| `app.py`, `cli.py` | Báo rõ khi kết quả chỉ khớp được sau khi bù | Low | Full suite | Người dùng không biết → biết đây là dấu hiệu né nhận dạng |

**Vì sao Theil–Sen chứ không bình phương tối thiểu:** nhạc hiệu dùng chung tạo mảnh
align ngẫu nhiên trong cùng clip gốc, kéo lệch bình phương tối thiểu. Đo thật: với
fixture 3%, bình phương tối thiểu cho R²=0,916 (sát ngưỡng tới mức dựng lại file là
lật kết quả) và lệch 0,00135 → chỉ thu lại 38,5% vân tay. Theil–Sen cho **1,03000**
đúng tuyệt đối → 56,4%.

Kiểm chứng đầu-cuối (fixture: nhiễu 60s + clip gốc thật bị biến đổi + nhiễu 60s):

| Ca | Trước | Sau | Mốc báo về |
|---|---|---|---|
| nhanh 3%, giữ cao độ | **0** | 6.365 hash, phủ 56,4% | 00:00:59 (thật: 00:01:00) |
| chậm 3%, giữ cao độ | **0** | 6.625 hash, phủ 58,7% | 00:01:01 |
| nhanh 3% + đổi cao độ | **0** | 9.615 hash, phủ 85,3% | 00:00:59 |
| chỉ có nhiễu (đối chứng âm) | 0 | **0** — không bịa kết quả | — |

Chi phí: chỉ chạy khi lượt quét thường không ra ứng viên nào đạt chuẩn, nên video có
kết quả bình thường **không tốn thêm giây nào**. Đo sạch trên một video âm tính 59
phút: 54,2s → 158,2s (**×2,9**). Muốn giữ lợi ích mà không mất tốc độ thì đặt
`luoi_resample = []` — bỏ lưới quét mù, chỉ giữ phần đọc độ trôi (miễn phí, vẫn phủ
đổi tốc độ ±6%).

Kiểm chứng không hồi quy: chạy lại đủ 11 video thật với bù tốc độ bật → **vẫn 0/11**,
và cả 4 lượt bù cao độ đều cho **0 dòng khớp**.

Không thay đổi: mọi thứ ở vòng trước, cộng thêm hợp đồng `_match_chunks()` (tên khúc
không có hậu tố hệ số vẫn hiểu là 1,0).

## Vòng observability tạo vân tay — 2026-08-06

| File | Nội dung và lý do | Rủi ro | Test xác minh | Trước → Sau |
|---|---|---|---|---|
| `fingerprint_progress.py` | Event immutable, tracker invariant/ETA, terminal + rotating file logger, một worker/controller và queue bounded | Medium | Progress/controller unit + Unicode/queue/cancel | Callback phần trăm nghèo, shared dict → event thật, snapshot, queue 256/recent 50 |
| `process_runner.py` | Reader/poll loop, heartbeat, child PID, tail bounded, timeout/cancel đúng process tree | Medium | Output-live/silent/nonzero/timeout/cancel tests | Block trên stdout và terminate parent → poll được khi im lặng, dọn root + descendants |
| `audfprint_progress_runner.py` | Instrument trước/sau từng `wavfile2hashes` mà không sửa vendor/thuật toán/DB format | Medium | Multi-core integration thật | Parent chỉ report sau cả core-list → JSON event per-file ngay khi worker chạy |
| `engine.py` | Nối event, skip positive hash/retry zero-hash, workspace per job, atomic DB replace, summary success/skip/fail/cancel | Medium | Engine regressions + real audfprint smoke | Một subprocess ghi thẳng DB, progress cuối batch → per-file + DB cũ sống qua cancel/failure |
| `app.py` | Controller trong session, placeholder cố định, phase/clip/count/elapsed/rate/ETA/PID/heartbeat/recent log, duplicate guard | Low–medium | App tests + browser smoke 6 fixture | UI gần như im lặng → cập nhật sau 250 ms và trong lúc job còn chạy |
| `cli.py` | Summary tạo mới/skip/lỗi/cancel theo result mới | Low | Full fast suite | Chỉ tổng clip/thời gian → outcome rõ |
| `tests/test_fingerprint_progress.py` | Contract, invariant, ETA, Unicode, queue, duplicate, cancel | Low | 6 tests pass | Không có → regression coverage |
| `tests/test_process_runner.py` | Output tức thời, silent heartbeat, nonzero, timeout/cancel tree | Low | 5 tests pass | Không có → chứng minh không chờ process kết thúc/deadlock |
| `tests/test_fingerprint_engine_progress.py` | Parse event, skip/retry, atomic DB, Windows logger handle | Low | 4 tests pass | Không có → regression storage/process boundary |
| `tests/test_audfprint_progress_integration.py` | FFmpeg + audfprint multi-core thật trên WAV tạm | Low | 1 slow test pass | Không có → event phải đến trước commit được chứng minh |
| `tests/test_app.py`, `tests/test_shifts.py`, `tests/test_tang_toc.py` | Cập nhật fake/signature theo API additive và DB temp | Low | Full fast suite | Fake cũ không phản ánh staging → test tương thích |

Hành vi ảnh hưởng người dùng: màn hình tạo vân tay có trạng thái chi tiết và nút dừng chính xác hơn;
CLI có thêm outcome; mode add cần dung lượng tạm xấp xỉ kích thước DB hiện có để đảm bảo atomic.
API cũ `build_database(..., progress=...)` vẫn được giữ; event/job ID là tham số tùy chọn mới.

Không thay đổi: audfprint vendored, Analyzer/HashTable, `_merge`, threshold, top-N, shifts, schema
SQLite, fingerprint format, dữ liệu/credential production.

Vấn đề còn lại: chưa nghiệm thu 1.717 clip thật; chưa resume phần staged sau cancel; chưa nhận biết
file cùng path đổi nội dung; progress structured chưa mở rộng sang toàn bộ scan/channel.

## Thay đổi source/runtime

| File | Nội dung và lý do | Rủi ro | Test xác minh | Trước → Sau |
|---|---|---|---|---|
| `engine.py` | Inject `data_dir/out_dir`; validate resource/timeout config; chặn path database thoát data; yt-dlp timeout; export CSV exclusive + formula-safe | Medium | security/core/config/network/full suite | Test khởi tạo data thật, registry có thể traversal, network có thể chờ default, CSV overwrite → storage tạm, path bị từ chối, timeout 30s, suffix `_2` |
| `channel.py` | Đếm số tải thành công thực, trả `da_huy`, đặt yt-dlp socket timeout | Low | cancel/network regression/full suite | Cancel có thể báo toàn bộ đã tải và request dùng default → báo đúng số, timeout 30s |
| `sheets.py` | Gửi cell bằng `RAW` | Low–medium | fake worksheet/full suite | `USER_ENTERED` có thể chạy công thức → dữ liệu thuần |
| `app.py` | Data/output override qua env cho test/deploy; CSV download formula-safe; trạng thái cancel; help overlap đúng policy; xác nhận xóa | Low–medium | AppTest/full suite | Test/UI phụ thuộc data thật, xóa một bước → cô lập và xác nhận hai bước |
| `cli.py` | In `ĐÃ DỪNG` cho channel sync bị cancel | Low | full suite | Cancel vẫn ghi `XONG` → trạng thái rõ |
| `dong_goi.py` | Refactor thành hàm/CLI testable; deny secret case-insensitive; giữ audfprint/build file; loại runtime config; từ chối overwrite | Low | packaging tests + zip smoke | Archive cố định bị overwrite và có thể lọt nested secret → output explicit, kiểm tra hai lớp |

## Build, dependency và vận hành

| File | Nội dung và lý do | Rủi ro | Test xác minh |
|---|---|---|---|
| `.dockerignore` | Loại credential, 138.91 GiB data, venv, log, Windows binary, archive | Low | rule regression + source/context review |
| `Dockerfile` | Copy `constraints.txt` trước bước cài requirements | Low | Docker contract test + Compose config |
| `constraints.txt` | Minimum fixed cho cryptography/GitPython theo pip-audit | Medium | pip-audit resolver sạch + pip check |
| `requirements.txt` | Áp security constraint | Low–medium | pip-audit + fast suite |
| `requirements-dev.txt` | Khai báo pytest, coverage, pip-audit, Ruff riêng dev | Low | cài/run thật trong `.venv` |
| `ruff.toml` | Lint tập trung lỗi cú pháp/import/tên, không bulk restyle source cũ | Low | `ruff check .` pass |
| `cai_dat.bat` | Tạo `.venv`, ưu tiên Python 3.12 | Medium | static review; clean VM còn pending |
| `ChayTool.bat`, `GiamSat.bat`, `kiemtra.bat` | Ưu tiên `.venv`, fallback tương thích | Low | static review + UI/CLI smoke |
| `docker-compose.yml` | Gợi ý mount credential read-only, không bake | Low | review; Docker daemon pending |
| `.gitignore` | Ignore log/Ruff/coverage artifact mới | Low | `git status` |
| `watchlist.example.json` | Mẫu không chứa URL vận hành thật | Low | parser/package test |

## Test

| File | Thay đổi |
|---|---|
| `tests/conftest.py` | Fixture Engine truyền storage tạm trước mọi side effect |
| `tests/test_app.py` | AppTest dùng env data/output tạm |
| `tests/test_security_regressions.py` | Test path traversal, overwrite, formula, Sheets RAW, cancel, config, timeout/retry |
| `tests/test_packaging.py` | Test source package/Docker ignore/Docker constraint copy |
| `tests/test_core.py`, `tests/test_nhat_ky.py` | Bỏ import thừa để lint sạch |

Kết quả: fast suite tăng từ 248 pass lên 283 pass; không có test fail. Coverage module được đo
80%. Slow suite chưa kết luận vì timeout/cạnh tranh CPU với job thật.

## Tài liệu

Đã thêm/cập nhật:

- `README.md`.
- `docs/SYSTEM_OVERVIEW.md`.
- `docs/AUDIT_REPORT.md`.
- `docs/OPTIMIZATION_PLAN.md`.
- `docs/TEST_REPORT.md`.
- `docs/INSTALL_WINDOWS.md`.
- `docs/RUNBOOK.md`.
- `docs/CHANGELOG_OPTIMIZATION.md`.
- `HUONG_DAN.md` (quyền riêng tư, runtime, venv, 5 tab, overlap, cookie).

## Thay đổi có thể ảnh hưởng người dùng

1. Export CSV không còn ghi đè target; path trả về có thể có hậu tố `_2`, `_3`.
2. Cell CSV nguy hiểm có thêm apostrophe để spreadsheet coi là text; Sheets dùng RAW.
3. Config thủ công ngoài bounds bị từ chối/reset về default theo cơ chế startup hiện có.
4. Registry kho chỉ chấp nhận basename `.pklz` trực tiếp trong `data`; path tuyệt đối/legacy
   ngoài data không còn được phép.
5. Xóa kho/lịch sử trên UI cần tick xác nhận.
6. Launcher ưu tiên `.venv`; môi trường global cũ chỉ là fallback.
7. Source packager không ghi đè nếu thiếu `--overwrite` và không đưa `watchlist.json` runtime vào zip.
8. Request/tải yt-dlp có timeout socket 30 giây; `network_timeout_s` hợp lệ trong 5–300 giây.

## Không thay đổi

- Thuật toán `_merge`, overlap policy, thresholds, top-N, shifts mặc định.
- Schema CSV/Sheets 15/34 cột.
- Schema SQLite và dữ liệu thật.
- API YouTube/Google credential hoặc nội dung người dùng.
- `requirements-lock.txt` untracked ban đầu.
- `session.log` tracked ban đầu (không xóa/untrack trong audit).

## Vấn đề còn tồn tại

- Cancellation process tree của scan/channel và soak test database fingerprint rất lớn; fingerprint flow cơ bản đã triển khai/test.
- Lock và temp workspace riêng cho scan tương tác.
- Timeout/backoff riêng cho Google API và hành vi mạng thật.
- Structured logging/redaction/size rotation cho scan/channel; fingerprint flow đã có logger riêng.
- Pin/checksum supply-chain cho artifact tải.
- Docker build, Python 3.12 clean install, slow suite và API thật chưa nghiệm thu do môi trường.


---

## 2026-08-06 — Vòng review độc lập của Claude

### Sửa lỗi

- **`tests/test_app.py`** — `AppTest.from_file("app.py")` giải đường dẫn tương đối theo
  `tests/` trên Streamlit 1.61 ⇒ suite đỏ. Đổi sang đường dẫn tuyệt đối dựng từ `__file__`.
- **`channel.py` — `ChannelSync.va_metadata()`** chỉ lặp qua các key đã có trong
  `clips_meta.json`. Kho Cory có 1717 file trên đĩa nhưng chỉ 86 entry ⇒ **1631 clip
  không thể vá metadata bằng bất kỳ thao tác nào**. Thêm `seed_meta_tu_dia()`: tạo entry
  từ tên file `<ngày> - <tiêu đề> [<VIDEO_ID>].opus` (chỉ `id`/`title`/`url`;
  `upload_date`/`duration` để trống cho fetcher điền bằng dữ liệu thật). Không ghi đè
  metadata chính thức đã có.
- **`channel.py`** — `save_meta()` được gọi sau **mỗi** mục ⇒ O(n²) I/O trên 1631 mục.
  Đổi sang ghi theo lô 25 mục + ghi ở `finally` để crash giữa chừng không mất dữ liệu.

### Thay đổi hỗ trợ kiểm thử

- **`engine._run_stream()`** nhận thêm tham số `heartbeat_seconds` (mặc định 10.0, không
  đổi hành vi) để test heartbeat không phải chờ 10 giây thật.
- **`clip_metadata.filename_fallback_parts()`** — API công khai, để `channel.py` và
  resolver dùng chung **một** cách bóc tách tên file thay vì hai định nghĩa lệch nhau.

### Thay đổi contract

- `ChannelSync.va_metadata()` trả thêm khoá `da_them_tu_dia`. `cli.py vameta` in thêm số
  này. Đã cập nhật call site và test.

### Đã xác nhận đúng, giữ nguyên

`fingerprint_progress.py`, `process_runner.py`, `audfprint_progress_runner.py`,
`clip_metadata.py`, `kiem_metadata_kho.py`, màn hình tiến độ trong `app.py`,
resolver dùng chung ở `bang_ngang.py`/`dossier.py`/`engine.to_rows()`, lệnh `vametak`.

### Sửa deadlock nhánh đa nhân của audfprint

- **`audfprint_progress_runner.py` — `instrumented_multiproc_add()`**: thay
  `audfprint.multiproc_add`. Bản vendored đẩy nguyên một `HashTable` **419 MB mỗi worker**
  (~3,3 GB với `--ncores 8`) qua `multiprocessing.Pipe`, giữ mọi đầu ghi ở tiến trình cha
  và không có timeout ⇒ treo cứng **40 % số lần** (đo 8/20 lượt trên chính audfprint gốc).
  Bản mới: worker ghi bảng ra file tạm gzip, pipe chỉ mang dict trạng thái; cha đóng đầu
  ghi ngay sau `start()` nên worker chết thành `EOFError`; `recv()` có `poll(1800 s)` làm
  lưới an toàn; file tạm xoá ngay sau merge.
  → **0/20 lượt treo**, trung bình **6,4 s** so với 8,2 s của bản gốc.
  → Bảng hash, `counts` và danh sách file **giống hệt từng ô** so với audfprint gốc.
- **`audfprint_progress_runner.py` — `_emit()`**: ghi bằng đúng một `os.write()` thay vì
  `print()`. Tám tiến trình con ghi chung một pipe stdout; `print()` tách nhiều lần ghi
  làm lồng dòng và mất progress event (quan sát 7/8 thay vì 8/8).
- **`audfprint_progress_runner.py` — `cai_dat_instrumentation()`**: tách phần gắn bản vá
  ra khỏi `main()` để test được cả ba điểm vá.
- **`process_runner.py`**: rút stdout theo lô và soi cây process theo nhịp 0,2 giây thay vì
  sau mỗi dòng. Thông lượng **138 → 15.094 dòng/giây**.

Test mới: `tests/test_audfprint_multiproc.py` (4 test) và
`tests/test_audfprint_progress_integration.py::test_nhanh_da_nhan_that_khong_treo_va_khong_mat_event`
(slow, 3 lượt build thật với `ncores=8`).

### Lấy đúng ngày đăng khi đồng bộ kênh

- **`channel._tai_va_nen()`**: đổi `ydl.download()` → `ydl.extract_info(download=True)`.
  Lượt tải vốn đã trích xuất đầy đủ trang video nhưng giá trị trả về bị vứt đi; giờ dùng
  nó để lấy `upload_date`/`duration`/`title` thật — **không thêm request mạng nào**.
  Trả về `(đường_dẫn, VideoInfo đã bổ sung)`.
- **`channel.ngay_dang_tu_info()`** / **`bo_sung_video_info()`**: rút ngày từ
  `upload_date`, hoặc `release_timestamp`/`timestamp` khi có; không bao giờ ghi đè dữ
  liệu tốt bằng rỗng.
- **`channel.list_channel()`**: thêm `lay_ngay_dang=False` (mặc định giữ nguyên tốc độ —
  một request cho cả kênh) và `chi_tiet=` để test offline. Bật cờ thì chỉ hỏi lại những
  video còn thiếu ngày, có báo tiến độ, một video lỗi không làm hỏng cả danh sách.
- **`channel._ten_file()`**: lọc qua `valid_upload_date()` — `00000000` chỉ khi thật sự
  không có ngày, không bịa ngày hôm nay.
- **`ChannelSync.lay_info_video()`**: một điểm trích xuất đầy đủ dùng chung.
  `channel.va_metadata` và `engine.va_metadata_thieu` cùng dùng `ngay_dang_tu_info()`.
- **`clip_metadata.valid_upload_date()`**: API công khai để hai module dùng chung một
  định nghĩa "ngày đăng hợp lệ".
- **`app.py`**: thêm ô chọn "Lấy cả ngày đăng chính xác" cho bảng xem trước (mặc định
  tắt) và caption cho biết bao nhiêu video chưa có ngày trong danh sách nhanh.

Test mới: `tests/test_ngay_dang.py` (12 test, không gọi mạng).

### Phase `decoding` trở thành tín hiệu tất định

- **`audfprint_progress_runner.cai_dat_theo_doi_giai_ma()`**: bọc
  `audio_read.audio_read()` — đúng nơi `audfprint_analyze.wavfile2peaks` gọi FFmpeg —
  để phát event `clip_phase` với `phase=decoding` / `fingerprinting`.
  Trước đây phase `decoding` chỉ được suy ra khi *bắt gặp* tiến trình ffmpeg lúc lấy mẫu
  cây process; clip ngắn thì ffmpeg chỉ sống vài chục mili giây nên giao diện lúc hiện lúc
  không và `pytest -m slow` flaky. Phải cài trong **mỗi tiến trình con** vì Windows dùng
  spawn nên bản vá ở cha không đi theo sang con.
- **`engine._build_database_da_khoa`**: xử lý event `clip_phase`, lọc qua
  `PHASES_FINGERPRINT = {decoding, fingerprinting, probing}` để một dòng stdout hỏng
  không đẩy job sang trạng thái kết thúc giả.

Test mới trong `tests/test_fingerprint_engine_progress.py`: phase `decoding` đến từ event
thật (có tên clip + PID), và `clip_phase` mang pha kết thúc/không hợp lệ thì bị bỏ qua.
`pytest -m slow` chạy **3 lượt liên tiếp, 5 passed mỗi lượt** — hết flaky.

### Ngày đăng video: chốt theo múi giờ người dùng

`upload_date` của yt-dlp là ngày theo lịch **UTC**. Người dùng ở `Asia/Ho_Chi_Minh`
(UTC+7) thấy ngày khác khi video phát hành từ **17:00 UTC** trở đi — đúng 1 ngày,
không bao giờ 2. Đó là lý do chỉ một số video sai.

- **`publication_date.py`** (mới): `PublicationDateResolver` + `PublicationDateResult`
  (date, source_field, raw_value, confidence, warnings) + `format_publication_date()`.
  Ưu tiên `release_timestamp` → `timestamp` → `release_date` → `upload_date` →
  tên file. Trường có thời điểm chính xác luôn thắng trường chỉ có ngày, vì chỉ nó
  mới quy đổi được múi giờ.
- **`engine.youtube_info()`**: chốt ngày chính tắc ngay tại tầng nạp metadata, trả
  thêm `upload_date_raw`, `publication_date_source`, `publication_date_confidence`.
- **`channel.ngay_dang_tu_info()`**: trước đây ưu tiên `upload_date` nên nhánh đọc
  `timestamp` không bao giờ chạy; nay uỷ quyền cho resolver.
- **`channel.sync()`**: ghi thêm `publication_date` + `publication_date_source` vào
  `clips_meta.json`, giữ `upload_date` cho bản đọc cũ.
- **`clip_metadata.source_from_mapping()`**: đọc `publication_date` trước, lùi về
  `upload_date` cho kho cũ (đường bình thường, không phát cảnh báo).
- **`bang_ngang.dinh_dang_ngay()`**: uỷ quyền cho `format_publication_date()` — một
  hàm định dạng duy nhất cho CSV ngang, Sheets và UI.
- **`kiem_ngay_dang.py`** (mới): audit / repair-offline / repair-network, mặc định
  chỉ đọc, có dry-run, backup, ghi nguyên tử, `--limit`.

Kiểm chứng: hai video mẫu qua đúng đường của tool cho `01/08/2026` và `21/06/2025`,
khớp giá trị người dùng đã xác minh. Mẫu 25 clip kho Cory: 22 lệch 1 ngày, 3 đúng,
0 lỗi (dry-run, không ghi). 400 passed, 1 skipped.

### Scan Pipeline V2 — streaming result, Sheets không chặn, workspace riêng

- **`engine.Engine.scan_workspace()`** (mới): mỗi lượt quét có `data/scan_jobs/<uuid>/`
  riêng. Trước đây `_cut_chunks` `rmtree` thư mục CHUNG `data/chunks` ngay đầu hàm và
  `_match_chunks` ghi `data/_ds_khuc.txt` / `data/_raw_match.txt` cố định — hai luồng
  quét đồng thời (GUI + Watch) xoá chunk của nhau. Đây là lỗi ĐÚNG/SAI, không phải chậm.
- **`engine.Engine.scan_iter()`** (mới): generator, yield từng `ScanResult` ngay khi
  xong, kèm `on_video` callback. `scan_many()` giờ là `list(scan_iter(...))` nên mọi
  call site cũ (CLI, Watch, test) giữ nguyên hành vi.
- **`scan_jobs.py`** (mới): `ScanJobController` + `VideoState` + `BatchSnapshot`. Một
  worker thread, snapshot bất biến cho UI, ETA theo trung bình trượt, tách hẳn trạng
  thái QUÉT khỏi trạng thái GIAO SHEETS.
- **`sheet_delivery.py`** (mới): `SheetDeliveryWorker` chạy thread riêng. Scan worker
  chỉ `enqueue()` rồi đi tiếp. Retry phân loại (429/5xx/timeout thử lại;
  PERMISSION_DENIED/404 dừng ngay), backoff mũ, khoá idempotency SHA-256 chống ghi trùng.
- **`app.py`**: màn hình quét mới — batch progress, Hoàn tất/Lỗi/Đã chạy/ETA, video
  hiện tại kèm công đoạn, bảng từng video (Quét · Đoạn · Sheets), tóm tắt Sheets.

Đo được (10 video, quét 0,3 s/video, Sheets 1,5 s/lần): người dùng thấy kết quả sau
**3,00 s** thay vì **18,01 s** — sớm hơn 83 %.

### Dùng lại kết nối Google Sheets

`sheets.append()` trước đây mỗi lần gọi đều `service_account()` → `open_by_key()` →
`worksheet()` → `get_all_values()`. Riêng `get_all_values()` **tải toàn bộ bảng** chỉ
để hỏi «bảng có trống không», nên chi phí tăng theo số dòng đã tích luỹ. Với
incremental delivery, số lần append tăng từ 1/batch lên 1/video nên điểm này thành nút thắt.

- Cache kết nối ở **cấp module** (không phải cấp instance) vì `app.py` tạo
  `SheetsExporter` mới mỗi lần đẩy; khoá cache gồm mtime của `google_key.json` nên
  thay khoá là tự xác thực lại.
- Kiểm tra header bằng cách đọc **ô A1** thay vì tải cả bảng, và chỉ đọc **một lần**
  cho cả phiên.
- Lỗi khi ghi thì bỏ cache để lần sau kết nối lại, nhưng **không tự thử lại append** —
  lượt ghi có thể đã tới Google, thử lại tại đây sẽ tạo dòng trùng. Việc thử lại là
  của `SheetDeliveryWorker`.
- `kiem_tra()` vẫn mở kết nối mới để «Kiểm tra kết nối» thật sự chạm tới Google.

Đo được (10 video, bảng đã có 2000 dòng, 0,25 s/lượt API):

| | Lượt gọi API | Thời gian |
| --- | ---: | ---: |
| Trước | 50 | 22,54 s |
| Sau | **14** | **3,50 s** |

Test mới: `tests/test_scan_streaming.py` (12), `tests/test_sheet_delivery.py` (14),
`tests/test_sheets_session.py` (15), `tests/test_app_scan_progress.py` (1).

### Sửa ranh giới thread và schema bảng trạng thái

Hai lỗi do chính vòng Scan Pipeline V2 gây ra, lộ ra khi chạy thật.

**`missing ScriptRunContext` + `KeyError: sheet_link`.** `sheet_link` **không** thiếu
khởi tạo (`cau_hinh.py:17` + `app.py:44-47` đã tạo sẵn). Root cause là thread nền
không có `ScriptRunContext`, nên `st.session_state` đọc từ đó trả về proxy **rỗng** —
key có ở main thread vẫn báo thiếu. Hai chỗ vi phạm, đều là code vòng trước:
`chay_quet.sau_moi_video` → `lay_sheets()`, và `sender` của `SheetDeliveryWorker`.

- `scan_jobs.ScanLaunchConfig` (mới): ảnh chụp bất biến `auto_sheet`/`sheet_link`/
  `dang_ngang`, chụp trên main thread lúc bấm Bắt đầu quét. Kèm lợi ích nghiệp vụ:
  đổi link Sheet giữa batch không làm batch đang chạy bắn sang bảng khác.
- `app.tao_sheets_exporter(sheet_link)` (mới): hàm thuần. `lay_sheets()` giữ lại
  nhưng chỉ là bản tiện dụng cho main thread.
- `SheetDelivery.sheet_link` (mới) và `sender(sheet_link, header, rows)`: công việc tự
  mang đích đến nên thread giao hàng không phải hỏi lại UI.

**`ArrowInvalid` lặp mỗi lần render.** Bảng trạng thái dựng bằng
`"—" if v.matches is None else v.matches` → cột `object` trộn `int`/`str`; PyArrow ném
exception rồi Streamlit mới sửa dtype — mỗi lần vẽ lại một exception, suốt lượt quét.
Gốc rễ là **bảng UI không có schema**.

- `scan_ui.py` (mới): `build_scan_status_dataframe()` khai báo dtype tường minh cho
  cả năm cột (kể cả khung rỗng), tách khỏi `app.py` nên test được bằng
  `pa.Table.from_pandas` mà không cần chạy Streamlit.
- Cột `Đoạn` là `string`: cần phân biệt ba trạng thái — chưa quét (`—`), quét xong 0
  đoạn (`0`), quét xong N đoạn. `Int64` + `pd.NA` sẽ hiển thị "chưa quét" thành ô
  trống, khó phân biệt với 0.

Đã đối chứng: cách cũ `dtype=object` → `ArrowInvalid`; cách mới `dtype=string` →
chuyển Arrow thành công, giá trị `['3', '0', '—']`.

Test mới: `tests/test_scan_ui_schema.py` (9), `tests/test_scan_thread_boundary.py` (10),
`tests/test_app_scan_no_warnings.py` (1). Có guard cấu trúc dùng `tokenize` để chặn
`scan_jobs.py`/`sheet_delivery.py`/`scan_ui.py` chạm Streamlit — và một test tự kiểm
tra guard đó thật sự bắt được vi phạm.

### Chọn kết quả đại diện: ngang bằng thì ưu tiên đoạn dễ kiểm tra

Với `top_n = 1`, `_chon_loc` chia video thành `duration/1` tức **một vùng duy nhất**,
nên Top-1 trước đây thuần tuý là `max(hashes)` — vị trí không đóng vai trò gì. Video
compilation dài có thể trả về đoạn nằm ở giờ thứ 35, dù có đoạn tương đương ở giờ thứ 4.

- **`engine.chon_dai_dien()`** (mới, hàm thuần): chọn đại diện trong một nhóm ứng viên.
  Chất lượng quyết định trước; chỉ trong nhóm **ngang bằng** mới xét độ dễ kiểm tra.
- **`engine.chi_phi_kiem_tra()`** (mới): `(start_s/duration, start_s)` — dùng cả tỉ lệ
  lẫn giây tuyệt đối vì 45% của video 12 tiếng vẫn là hơn 5 tiếng tua. Không biết thời
  lượng thì lùi về giây tuyệt đối.
- **`Config.dung_sai_gan_bang = 0.03`** (mới, có validate 0..0.5).
- `_chon_loc` dùng `chon_dai_dien` ở cả nhánh phân bổ đều lẫn nhánh thường.

"Ngang bằng" đòi hỏi **cả** số hash **và** thời lượng khớp đạt ≥97% của ứng viên tốt
nhất, cùng bậc phân loại. Điều kiện thời lượng chặn ca đoạn 20 giây ở đầu video thắng
đoạn 15 phút rõ ràng.

Hiệu chỉnh dung sai bằng dữ liệu thật (200 job trong `lichsu.db`): trung vị
`hashes(#2)/hashes(#1)` = **0,921** nên near-tie là chuyện thường; dung sai 10% sẽ đảo
62% kết quả. Ở mức 3% chỉ 24% job có ứng viên lọt dải.

Tác động đo được trên 200 job: **188 giữ nguyên (94%), 12 thay đổi (6%)**. Ví dụ job
291 — video 50,1 giờ — Top-1 chuyển từ vị trí 70% về 8%, đánh đổi **0,2%** bằng chứng.

Không đụng: `_merge`, audfprint, ngưỡng, shifts, ngữ nghĩa `top_n`, phân bổ đều theo
vùng, cột báo cáo, contract Sheets.

Test mới: `tests/test_match_selection.py` (26).

### Khoá chất lượng đổi sang ty_le, kèm sàn bằng chứng

`CLAUDE.md` ghi `ty_le` (% vân tay clip gốc khớp được) mới là chỉ số **chuẩn hoá**;
`hashes` tuyệt đối phụ thuộc độ dài clip nên xếp hạng bằng nó thiên vị clip dài.

Đo trên **283 job thật** trước khi đổi: chuyển thuần sang `ty_le` làm 58 % Top-1 thay
đổi, trong đó **18 % là đánh đổi nặng** — ví dụ job 316 thay đoạn 22,8 phút / 36.939
hash bằng đoạn 9,4 phút / 13.129 hash chỉ vì phần trăm cao hơn. `ty_le` cố tình bỏ qua
độ lớn, mà với hồ sơ khiếu nại thì 22,8 phút vi phạm mạnh hơn 9,4 phút.

- **`engine.loc_du_bang_chung()`** (mới): loại ứng viên có `hashes` hoặc `matched_s`
  dưới 70 % của ứng viên mạnh nhất trong nhóm, trước khi xếp hạng bằng `ty_le`. Ứng
  viên mạnh nhất luôn tự thoả sàn nên không bao giờ trả về rỗng.
- **`Config.khoa_chat_luong = "ty_le"`** — đặt `"hashes"` để khôi phục hành vi cũ.
- **`Config.san_bang_chung = 0.70`** — đặt `0` để tắt sàn.
- Tự lùi về `hashes` khi mọi `ty_le` bằng 0 (`_gan_chi_so` chưa chạy) thay vì cho ra
  thứ tự tuỳ tiện.

Kết quả: tỉ lệ đổi Top-1 từ 58 % xuống **46 %**, và **28 ca đánh đổi nặng bị sàn chặn**.
Các ca cải thiện vẫn giữ — job 315 hash chỉ kém 6 % mà `ty_le` tăng từ 9,7 lên 48,6.

Test mới: 8 test trong `tests/test_match_selection.py`, gồm tái hiện đúng job 316 và
job 315, và test chứng minh chính cái sàn tạo ra khác biệt.
