# Báo cáo audit TimClip Pro

Ngày audit: 2026-08-06. Mọi location là trạng thái source trước hoặc trong lượt audit này.
Không sao chép nội dung credential vào báo cáo.

## [CRITICAL] Docker build context có thể chứa credential và 138.91 GiB dữ liệu runtime

- Location: `Dockerfile:10`, thiếu `.dockerignore`, `google_key.json:1`.
- Component: Build/packaging/security.
- Evidence: `COPY . .`; phép đo workspace cho 17.679 file, 149.158.829.165 byte. Potential credential detected at google_key.json:1
- Reproduction: Chạy `docker build .` khi Docker daemon hoạt động và quan sát build context/layer `COPY`.
- Impact: Credential, database, video, log, `.venv` có thể đi vào build daemon/cache/image; build gần như không khả thi vì context ~139 GiB.
- Root cause: Git ignore không phải Docker ignore; không có allow/deny boundary cho build context.
- Recommended fix: Thêm `.dockerignore` loại credential, data, output, VCS, venv, binary Windows, archive và cache.
- Regression risk: Low; Dockerfile tự cài FFmpeg và dependency Linux, không cần các mục bị loại.
- Validation method: Kiểm danh sách ignore, đo context khả dụng và build khi daemon sẵn sàng.
- Status: Implemented; `.dockerignore` và regression test đã có, Compose config hợp lệ. Docker build/run còn chờ daemon.

## [HIGH] Registry kho cho phép đường dẫn database thoát khỏi `data/`

- Location: `engine.py:285-318`, `engine.py:323-330`, `engine.py:364-372`, `engine.py:548-553`.
- Component: Storage/security.
- Evidence: Trường `db` từ `data/khos.json` được truyền thẳng vào `os.path.join`; absolute path hoặc `..` có thể trỏ ra ngoài. `delete_kho()` xóa path đó; `db_clips()` unpickle nội dung.
- Reproduction: Trong Engine dùng thư mục tạm, tạo registry có `db: "../outside.pklz"`, rồi gọi `use_kho`/`delete_kho`/`db_clips`.
- Impact: Có thể xóa file ngoài data hoặc thực thi payload pickle nếu registry/database bị thay độc hại.
- Root cause: Tin cậy dữ liệu registry bền vững mà không kiểm basename/extension/containment.
- Recommended fix: Chuẩn hóa và từ chối absolute path, path có directory component, non-`.pklz`; dùng một helper duy nhất tại mọi call site.
- Regression risk: Low–medium; registry cũ hợp lệ dùng basename vẫn tương thích.
- Validation method: Regression test path traversal/absolute path và test kho hợp lệ hiện có.
- Status: Implemented and validated bằng regression test + full fast suite.

## [HIGH] Test chưa cô lập hoàn toàn với dữ liệu thật

- Location: `tests/conftest.py:55-72`, `tests/test_app.py:7`, `engine.py:197-228`.
- Component: QA/data safety.
- Evidence: Fixture gọi `Engine(root=<repository>)`; constructor tạo/mở `data/lichsu.db` và đọc config/kho trước khi fixture đổi field sang `tmp_path`. AppTest cũng khởi tạo Engine mặc định.
- Reproduction: Theo dõi call `Engine._init_sqlite` khi chạy một unit test dùng fixture `engine`.
- Impact: Test có thể migrate/ghi SQLite thật, phụ thuộc preference người dùng và tranh chấp job đang chạy.
- Root cause: Constructor không cho inject riêng data/output path trước side effect.
- Recommended fix: Thêm tham số tùy chọn `data_dir`/`out_dir`, giữ mặc định cũ; fixture và AppTest dùng thư mục tạm.
- Regression risk: Low; API chỉ được mở rộng.
- Validation method: Test spy bảo đảm path SQLite/config nằm dưới `tmp_path`; chạy suite nhanh.
- Status: Implemented; constructor hỗ trợ path injection, fixture và AppTest đều dùng thư mục tạm.

## [HIGH] Hủy tác vụ không xuyên qua subprocess dài và worker con

- Location: `engine.py:430-466`, `engine.py:863-893`, `channel.py:218-248`.
- Component: Concurrency/UX/resource management.
- Evidence: FFmpeg chạy bằng `subprocess.run()` nên chỉ kiểm cancel giữa chunk/video; `_run_stream()` chỉ kiểm cờ khi nhận dòng stdout và terminate parent rồi `wait()` không timeout.
- Reproduction: Chạy FFmpeg/audfprint tác vụ dài hoặc im lặng, đặt `cancel_event` trong lúc process chưa in dòng.
- Impact: Nút Dừng có thể chờ lâu, worker audfprint có thể còn chạy, giữ CPU/file handle.
- Root cause: Không có process-tree lifecycle/cancellable polling thống nhất.
- Recommended fix: Helper process có poll timeout ngắn, terminate/kill có thời hạn và dọn descendants bằng API process; triển khai riêng với soak test.
- Regression risk: High trên Windows và audfprint multiprocessing.
- Validation method: Test process giả im lặng + child process; nghiệm thu Windows thật.
- Status: Deferred — không sửa vội khi một job thật đang chạy và chưa có soak test.

## [HIGH] Dependency hiện hành có ba advisory đã biết

- Location: `requirements-lock.txt` (untracked trước audit), `.venv`.
- Component: Dependency/security.
- Evidence: `pip-audit 2.10.1` báo `cryptography 49.0.0` cần 50.0.0 và `GitPython 3.1.55` cần 3.1.57 (hai advisory GitPython).
- Reproduction: `.\.venv\Scripts\python.exe -m pip_audit -r requirements-lock.txt --disable-pip --no-deps`.
- Impact: Môi trường hiện tại chứa phiên bản có lỗ hổng đã công bố, dù đây là dependency bắc cầu và code không gọi trực tiếp.
- Root cause: Lock snapshot cũ hơn bản sửa; production requirements không có constraint bảo mật.
- Recommended fix: Thêm constraint tối thiểu chính xác, cập nhật môi trường project-local và audit lại; không sửa file lock untracked của người dùng.
- Regression risk: Medium; cần full fast suite và import/UI smoke.
- Validation method: `pip check`, `pip-audit`, pytest.
- Status: Implemented trong manifest/resolver; `pip-audit -r requirements.txt` sạch. Chưa nâng trực tiếp `.venv` đang phục vụ job thật; cài lại requirements sau khi dừng job.

## [MEDIUM] CSV và Google Sheets có bề mặt formula injection

- Location: `engine.py:1311-1372`, `app.py:101-105`, `sheets.py:118-122`.
- Component: Reporting/security.
- Evidence: Tiêu đề/link lấy từ YouTube được ghi CSV; Sheets dùng `value_input_option="USER_ENTERED"`, khiến chuỗi bắt đầu bằng ký tự công thức có thể được đánh giá.
- Reproduction: Dựng `ScanResult(source_name="=1+1")`, export CSV/append Sheets và mở bằng spreadsheet.
- Impact: Công thức ngoài ý muốn, link/phép gọi nguy hiểm tùy client spreadsheet.
- Root cause: Không phân biệt dữ liệu ngoài với công thức.
- Recommended fix: Sheets ghi `RAW`; CSV escape cell bắt đầu `=`, `+`, `-`, `@` (kể cả sau whitespace điều khiển) tại biên export.
- Regression risk: Low–medium; dữ liệu hiển thị gần như giữ nguyên nhưng cell độc hại trở thành text.
- Validation method: Unit test fake worksheet và đọc lại CSV.
- Status: Implemented and validated; Sheets dùng `RAW`, cả CSV file và CSV download đều escape công thức.

## [MEDIUM] Export CSV có thể ghi đè file đã tồn tại

- Location: `engine.py:1336-1372`.
- Component: Output/data safety.
- Evidence: `open(..., "w")`; tên mặc định chỉ chính xác đến giây, `ten_file` explicit cũng không kiểm tồn tại.
- Reproduction: Export hai lần tới cùng path và so nội dung/inode.
- Impact: Mất báo cáo cũ ngoài ý muốn.
- Root cause: Không áp chính sách tên không trùng như `export_ho_so()`.
- Recommended fix: Sinh hậu tố `_2`, `_3` trước khi mở file.
- Regression risk: Low; return path đã có trong contract.
- Validation method: Test file sentinel còn nguyên và path thứ hai khác.
- Status: Implemented and validated bằng file sentinel và suffix `_2`.

## [MEDIUM] Config chỉ validate overlap, không chặn resource value bất hợp lệ

- Location: `engine.py:58-95`, `engine.py:611-616`, `cau_hinh.py:44-59`.
- Component: Configuration/reliability.
- Evidence: JSON đúng type có thể đặt `ncores` rất lớn, shifts âm/quá lớn, `max_matches <= 0`, dung lượng cache âm; loader vẫn áp vào Config.
- Reproduction: Ghi config tạm với `ncores=100000`, khởi tạo Engine và xem command audfprint.
- Impact: Tạo quá nhiều process, lỗi command, cấu hình khó chẩn đoán.
- Root cause: UI bounds không được tái kiểm ở domain layer.
- Recommended fix: Mở rộng `Config.validate()` với invariant không thay default/ngưỡng nghiệp vụ; validate trước lưu.
- Regression risk: Low–medium; config thủ công bất hợp lệ sẽ quay về default theo cơ chế hiện có.
- Validation method: Parametrized unit tests.
- Status: Implemented and validated; bao gồm timeout mạng 5–300 giây.

## [MEDIUM] Đồng bộ bị hủy báo sai số video tải thành công

- Location: `channel.py:274-295`, `app.py:316-323`.
- Component: Correctness/UX.
- Evidence: Khi `cancel_check()` break, `moi = len(can_tai) - len(loi)` vẫn tính các video chưa hề thử là thành công.
- Reproduction: Ba ứng viên chưa tải, cancel trước video đầu; kết quả ban đầu báo `moi=3`.
- Impact: Người dùng tin rằng kho đã đồng bộ đủ; quy trình fingerprint tiếp theo có thể thiếu clip.
- Root cause: Suy số thành công từ tổng trừ lỗi, không đếm completion/cancellation.
- Recommended fix: Đếm `da_tai`, trả cờ `da_huy` bổ sung và hiển thị trạng thái rõ.
- Regression risk: Low; giữ toàn bộ key cũ, sửa đúng giá trị.
- Validation method: Unit test cancel trước/giữa và lỗi một video.
- Status: Implemented and validated; contract cũ được giữ và chỉ thêm key `da_huy`.

## [MEDIUM] Khóa dùng không nhất quán cho scan tương tác

- Location: `engine.py:618-629`, `engine.py:1140-1241`, `watch.py:255-280`.
- Component: Concurrency/data integrity.
- Evidence: Build và watch lấy `data/tool.lock`, nhưng gọi `scan_media/scan_many` trực tiếp từ GUI/CLI không lấy khóa; mọi scan dùng chung `data/chunks`, `_ds_khuc.txt`, `_raw_match.txt`.
- Reproduction: Hai process CLI scan cùng repository; process sau xóa/thay file tạm của process trước.
- Impact: Sai kết quả, crash, file tạm bị tranh chấp.
- Root cause: Lock boundary nằm ở một số entry point thay vì workspace/job abstraction.
- Recommended fix: Thiết kế wrapper `_scan_*_da_khoa` để tránh nested lock trong watch, sau đó áp chung.
- Regression risk: High vì watch đang giữ lock ngoài và khóa hiện không reentrant liên tiến trình.
- Validation method: Multi-process test Windows.
- Status: Deferred — cần refactor có kiểm soát.

## [MEDIUM] Network timeout mới chỉ được chuẩn hóa cho yt-dlp

- Location: `engine.py:761-818`, `channel.py:89-106`, `channel.py:174-203`, `channel.py:218-230`, `sheets.py:81-122`.
- Component: Networking/reliability.
- Evidence: Baseline yt-dlp đặt retry=10 nhưng không đặt socket timeout; Google client dùng default. Sau sửa, mọi call site yt-dlp có timeout 30 giây, Engine có config giới hạn 5–300 giây; Google client vẫn dùng default.
- Reproduction: Endpoint blackhole/mạng half-open.
- Impact: Job có thể chờ rất lâu và cancellation không phản hồi trong network call.
- Root cause: Các adapter phát triển độc lập và trước audit phụ thuộc default của thư viện.
- Recommended fix: Giữ timeout/retry hữu hạn đã thêm cho yt-dlp; ở phase riêng, bọc Google API với timeout/backoff phù hợp SDK và test lỗi quota.
- Regression risk: Medium–high với video chậm/mạng yếu.
- Validation method: Fake downloader/client timeout + test retry count.
- Status: Partially implemented and validated bằng fake downloader; phần Google API/live network deferred vì không dùng credential.

## [MEDIUM] Installer/launcher không dùng môi trường project-local và dependency không tái lập

- Location: `cai_dat.bat`, `ChayTool.bat`, `GiamSat.bat`, `kiemtra.bat`, `requirements.txt`.
- Component: Installation/operations.
- Evidence: Ban đầu chọn `py -3`/`python`, pip install trực tiếp; requirements không pin/bound; pytest không được khai báo cho dev.
- Reproduction: Máy có nhiều Python hoặc package global xung đột; chạy installer và kiểm interpreter/site-packages.
- Impact: “Works on my machine”, khó rollback, có thể chọn Python chưa tương thích.
- Root cause: Không có venv bootstrap và tách runtime/dev.
- Recommended fix: `cai_dat.bat` tạo `.venv`; launcher ưu tiên `.venv`; thêm requirements dev/constraint và tài liệu PowerShell.
- Regression risk: Medium; giữ fallback rõ ràng cho cài đặt cũ.
- Validation method: Static launcher check + clean-venv install trên VM khi có.
- Status: Implemented ở script/manifest; static check và smoke pass, clean Python 3.12 VM còn pending.

## [MEDIUM] Logging chưa đủ chẩn đoán và có file log được track

- Location: `nhat_ky.py`, `app.py:58-64`, `session.log`.
- Component: Observability/privacy.
- Evidence: GUI chỉ giữ `str(e)` không traceback/file log; CLI log là tee không timestamp/level/context; `session.log` được Git track và chứa Windows path.
- Reproduction: Ném lỗi background GUI; chỉ thấy message người dùng, không có stack kỹ thuật tập trung.
- Impact: Khó tìm nguyên nhân job; đường dẫn/ngữ cảnh có thể vào Git.
- Root cause: Chưa có logging facade/redaction/rotation theo size.
- Recommended fix: Ignore log mới, bỏ track log trong commit được chủ sở hữu duyệt; thêm logger tập trung ở phase riêng.
- Regression risk: Medium vì thay print/progress máy móc sẽ phá CLI.
- Validation method: Test log rotation/redaction và lỗi GUI.
- Status: Partially implemented; log mới đã được ignore, nhưng logging facade và quyết định untrack `session.log` được để lại. File người dùng không bị xóa/sửa.

## [LOW] UI có thao tác xóa một bước và trợ giúp overlap đã lỗi thời

- Location: `app.py:193-197`, `app.py:229-230`, `app.py:508-512`, `app.py:616-618`, `HUONG_DAN.md`.
- Component: UI/UX.
- Evidence: Xóa kho/lịch sử không có xác nhận; UI nói overlap phải lớn hơn clip dài nhất dù policy hiện có trần 180 giây.
- Reproduction: Chọn kho/job và bấm xóa một lần; so help text với `_overlap_thuc_te()`.
- Impact: Xóa nhầm dữ liệu fingerprint/lịch sử; người dùng chỉnh config theo quy tắc sai.
- Root cause: UI/docs chưa đồng bộ Phase 2b.
- Recommended fix: Checkbox/xác nhận hai bước; cập nhật help theo overlap hiệu lực có trần.
- Regression risk: Low.
- Validation method: AppTest render/control state; config tests.
- Status: Implemented and validated bằng AppTest/full suite.

## [LOW] Source package có chốt bí mật chưa đầy đủ và ghi đè archive cố định

- Location: `dong_goi.py:24-48`, `dong_goi.py:74`.
- Component: Packaging/security.
- Evidence: Tên cấm so khớp case-sensitive/chỉ vài basename; file JSON nhạy cảm trong thư mục con có tên khác có thể lọt; output cố định bị ghi đè.
- Reproduction: Tạo nested `Service_Account.JSON`, gọi `nen_lay`; tên có thể được allow do extension.
- Impact: Rò cấu hình khi gửi source package hoặc mất archive cũ.
- Root cause: Allowlist theo extension rộng hơn mô tả; logic chạy top-level khó unit test.
- Recommended fix: Pattern casefold, deny key/token/credential/secret basename, refactor `main` + output tùy chọn/atomic.
- Regression risk: Low.
- Validation method: Unit test tên nhạy cảm và inspect zip.
- Status: Implemented and validated bằng package tests và source zip smoke.

## [LOW] Coupling và module lớn làm tăng regression risk

- Location: `engine.py` (~61 KB/1.400 dòng), `app.py` (~30 KB), import vòng `engine` ↔ `dossier` và `engine`/`bang_ngang`.
- Component: Architecture/maintainability.
- Evidence: Engine chứa storage, process, download, match, report; module báo cáo import Engine để dùng helper/type.
- Reproduction: Xem import graph và số symbol (`engine.py` có khoảng 72 def/class).
- Impact: Khó thay thế từng adapter, test constructor kéo side effect.
- Root cause: Kiến trúc flat-module phát triển tăng dần.
- Recommended fix: Dài hạn tách adapter subprocess/storage/report bằng protocol nhỏ; chưa di chuyển hàng loạt.
- Regression risk: High nếu refactor ngay.
- Validation method: Contract tests trước/sau và slow suite.
- Status: Deferred by design.

## [INFORMATIONAL] Secret scan và Git history

- Location: Toàn repository/Git history.
- Component: Security hygiene.
- Evidence: Scan tên file/literal phổ biến không thấy key trong file tracked hoặc history; `google_key.json` đang bị ignore. `watchlist.json` và `session.log` vẫn tracked.
- Reproduction: `git log --all -- google_key.json`; `git rev-list --all --objects` với các basename credential; regex scan trả rỗng.
- Impact: Không có bằng chứng credential đã commit trong lịch sử được kiểm tra.
- Root cause: `.gitignore` đã có rule credential nhưng chưa có rule log/watchlist runtime.
- Recommended fix: Duy trì scan; dùng sample config và quyết định untrack dữ liệu vận hành ở commit riêng.
- Regression risk: None.
- Validation method: Lặp secret filename/content scan không in giá trị.
- Status: Verified.
