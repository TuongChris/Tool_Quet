# Runbook vận hành TimClip Pro

## Preflight mỗi lần vận hành quan trọng

```powershell
Set-Location "D:\Tool_Tim_Video_v2\TimClipPro"
git status --short
& ".\.venv\Scripts\python.exe" --version
& ".\.venv\Scripts\python.exe" -m pip check
& ".\bin\ffmpeg.exe" -version
```

Kiểm health khi GUI đã chạy:

```powershell
Invoke-WebRequest -UseBasicParsing "http://127.0.0.1:8501/_stcore/health"
```

Kết quả chuẩn là HTTP 200 và nội dung `ok`.

## Khởi động và dừng

GUI:

```powershell
& ".\ChayTool.bat"
```

Giám sát có log:

```powershell
& ".\.venv\Scripts\python.exe" cli.py watch --file ".\watchlist.local.json" --log
```

Yêu cầu dừng lượt watch từ PowerShell khác:

```powershell
& ".\.venv\Scripts\python.exe" cli.py dung
```

GUI có nút “Dừng lại”. Hiện cancellation có thể chỉ được kiểm tra giữa các subprocess dài;
không kill process bằng Task Manager trừ khi đã chấp nhận output dở dang.

Riêng tác vụ tạo/bổ sung vân tay, nút Dừng poll được cả khi audfprint im lặng và chỉ terminate PID
root của job cùng descendants. UI sẽ hiện “Đang yêu cầu dừng” cho tới khi worker xác nhận; database
thật cũ được giữ vì mọi thay đổi đang nằm trong workspace tạm. Các flow scan/channel khác chưa dùng
toàn bộ process runner mới và có thể vẫn chỉ kiểm cancel giữa các bước.

## Theo dõi tiến trình tạo vân tay

Sau khi bấm Tạo lại/Bổ sung, UI phải hiện phase chuẩn bị trong vài giây rồi có:

- `Đã hoàn tất / tổng`, phần trăm thật, clip và phase hiện tại.
- Số đã tính, đã tồn tại và lỗi.
- Elapsed, tốc độ, ETA sau tối thiểu ba completion có công việc.
- Thời điểm cập nhật, PID audfprint, thời gian clip, worker state và queue size.
- Heartbeat không tăng phần trăm khi clip/subprocess còn sống nhưng chưa hoàn tất.

Theo dõi log UTF-8 đồng thời ở PowerShell khác:

```powershell
Get-Content ".\ketqua\fingerprint.log" -Encoding UTF8 -Wait -Tail 50
```

Log quay vòng ở 5 MiB, giữ ba backup. Dòng chuẩn có `job_id`, `event`, basename, current/total,
PID hoặc exit code; không có command đầy đủ hay raw fingerprint.

Nếu UI không đổi:

1. Kiểm `Worker`, `Cập nhật gần nhất`, PID và phase; một video dài không đồng nghĩa job treo.
2. Tìm heartbeat/process child/end cùng `job_id` trong log.
3. Chỉ kiểm PID được UI/log nêu: `Get-Process -Id <PID>`. Không kill mọi `python.exe`/`ffmpeg.exe`.
4. Phase saving lâu: kiểm dung lượng, quyền ghi, antivirus/file lock. Không xóa `.pklz` hay workspace
   khi PID còn sống.
5. Worker chết/không có terminal event: giữ log, tái hiện bằng 3–10 fixture trên data/output tạm.

Kiến trúc và checklist sâu hơn nằm ở `docs/FINGERPRINT_PROGRESS_ARCHITECTURE.md`.

## Lock và chạy đồng thời

`data\tool.lock` bảo vệ dựng kho và cả lượt watch. Không xóa lock khi PID ghi trong file còn
sống. Scan tương tác trực tiếp hiện dùng các file temp chung nhưng chưa lấy cùng lock; quy tắc
vận hành là chỉ chạy một job nặng trên một repository tại một thời điểm.

Kiểm PID khóa:

```powershell
Get-Content ".\data\tool.lock"
Get-Process -Id <PID>
```

## Backup và phục hồi

Đợi mọi job dừng rồi backup:

```powershell
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$backupRoot = "D:\TimClipPro_Backup\$stamp"
New-Item -ItemType Directory -Path $backupRoot -Force | Out-Null
Copy-Item ".\data" "$backupRoot\data" -Recurse
Copy-Item ".\watchlist.local.json" "$backupRoot\watchlist.local.json" -ErrorAction SilentlyContinue
```

Thành phần quan trọng:

- `data\khos.json` + `.bak`: registry kho.
- `data\*.pklz`: vân tay, tốn nhiều giờ để tái tạo.
- `data\metadata\kho_*.json` + `.bak`: snapshot metadata báo cáo theo từng kho.
- `data\lichsu.db`: lịch sử.
- `downloaded.txt` và `clips_meta.json` trong thư mục clip gốc.
- `google_key.json`: backup ở secret manager riêng, không cùng source archive.

Khi JSON chính hỏng, lớp storage tự thử `.bak` và giữ bản lỗi dưới `.hong.*`. Không sửa cả
file chính lẫn backup cùng lúc.

## Quy trình dựng/cập nhật kho

```powershell
& ".\.venv\Scripts\python.exe" cli.py taodb "D:\ClipGoc"
& ".\.venv\Scripts\python.exe" cli.py themclip "D:\ClipMoi"
```

`taodb` có thể thay file vân tay đang dùng; backup `data\` trước. Không đặt file `.pklz` tải
từ nguồn lạ vào `data\`. Nếu shifts của kho và config lệch, tạo lại kho có kiểm soát thay vì
trộn fingerprint khác tham số.

## Quy trình quét

File cục bộ:

```powershell
& ".\.venv\Scripts\python.exe" cli.py file "D:\VideoDai\video.mp4"
```

YouTube:

```powershell
& ".\.venv\Scripts\python.exe" cli.py youtube "https://youtu.be/VIDEO_ID"
```

Kiểm báo cáo trong `ketqua\` và job trong tab Lịch sử. Exporter không ghi đè: nếu tên tồn
tại, file mới nhận hậu tố `_2`, `_3`, ... Cell có prefix công thức được xuất dưới dạng text.

## Kiểm tra và phục hồi metadata báo cáo

Tên registry phải dùng chính xác. Kho mà người dùng thường gọi “Cory toàn bộ” hiện được đăng ký
dưới tên `Cory` trong `data\khos.json`.

Audit kho active hoàn toàn chỉ đọc, kèm kiểm tra các match lịch sử của video mục tiêu:

```powershell
& ".\.venv\Scripts\python.exe" kiem_metadata_kho.py --video-id "Zlfty7Enrkg"
```

Audit một kho theo tên exact hoặc xuất JSON:

```powershell
& ".\.venv\Scripts\python.exe" kiem_metadata_kho.py --kho "Cory"
& ".\.venv\Scripts\python.exe" kiem_metadata_kho.py --kho "Cory" --json
```

Luôn xem trước trước khi ghi snapshot offline:

```powershell
& ".\.venv\Scripts\python.exe" kiem_metadata_kho.py --kho "Cory" --repair-offline
& ".\.venv\Scripts\python.exe" kiem_metadata_kho.py --kho "Cory" --repair-offline --apply
```

Lệnh `--apply` chỉ ghi atomically vào `data\metadata\kho_<slug>.json`; nó không sửa
`clips_meta.json`, không gọi YouTube, không tải media và không tạo lại fingerprint. Nếu snapshot
chính hỏng, công cụ từ chối ghi để không đè mất `.bak`. Nếu fingerprint DB thiếu hoặc API trả
không clip, công cụ cũng từ chối tạo snapshot rỗng.

Vá ngày đăng/thời lượng từ YouTube là tác vụ mạng riêng, chỉ chạy sau khi đã xem audit và backup:

```powershell
& ".\.venv\Scripts\python.exe" cli.py vametak
```

Lệnh này chỉ xử lý field còn thiếu trong snapshot của kho active, không tải audio/video, dùng
timeout và tối đa ba lần thử. Snapshot được lưu sau từng entry thành công. Có thể thực hiện tương
đương trong tab **Kho clip gốc** sau khi đánh dấu ô xác nhận mạng. Không chạy lệnh này chỉ để xuất
báo cáo; mọi exporter đều hoạt động offline.

Khi báo cáo có đoạn vi phạm nhưng thiếu video gốc:

1. Chạy audit, kiểm `Exact`, `YouTube ID`, `Filename fallback`, `Missing`, `Ambiguous`.
2. Nếu `Missing=0` và chỉ có fallback, fingerprint vẫn tốt; không tạo lại kho.
3. Kiểm tra `clips_meta.json` đúng thư mục kho và snapshot đúng warehouse.
4. Dùng dry-run/apply offline để phục hồi ID, URL và title có thể chứng minh từ filename.
5. Chỉ dùng `vametak` nếu thực sự cần ngày đăng/thời lượng chính thức.
6. Không tự chọn khi `Ambiguous>0`; sửa conflict nguồn trước rồi audit lại.

Sau sửa hiện tại, kho `Cory` có 1.717 clip, 86 entry nguồn exact, 1.631 filename fallback,
0 unresolved và 0 ambiguous. Cả 1.717 entry vẫn thiếu ít nhất một field chính thức; vì vậy UI
đúng khi cảnh báo báo cáo chưa hoàn chỉnh. Chi tiết kiến trúc nằm ở
`docs/CLIP_METADATA_ARCHITECTURE.md`.

## Cache và dung lượng

Xem trước, không xóa:

```powershell
& ".\.venv\Scripts\python.exe" cli.py dondep --xem-truoc
```

Thực hiện theo `dem_max_gb`/`dem_max_ngay`:

```powershell
& ".\.venv\Scripts\python.exe" cli.py dondep
```

File `.part`/`.ytdl` đang tải không bị dọn. Vẫn backup nếu cache là nguồn duy nhất khó tải lại.

## Google Sheets

1. Kiểm `google_key.json` tồn tại nhưng không in nội dung.
2. Chia sẻ Sheet cho service account.
3. Dùng nút “Kiểm tra kết nối” trong UI.
4. Dữ liệu được gửi với mode `RAW`, không thực thi title/link như công thức.
5. Không chạy `kiem_sheet.py` trên bảng thật nếu chưa chấp nhận một dòng test sẽ được ghi.

## Log và xử lý sự cố

- Watch log: `ketqua\giamsat_YYYY-MM-DD.log` khi dùng `--log`.
- Log giữ 30 ngày theo tên ngày; chưa có rotation theo kích thước.
- Thông báo user, URL và path có thể xuất hiện trong log; không gửi log công khai trước khi
  redact.

Khi job lỗi:

1. Ghi command, thời điểm, source type và message.
2. Chạy `pip check`, check FFmpeg và health.
3. Không chạy lại đồng thời khi process cũ còn sống.
4. Dùng một file/URL reproduction nhỏ; không dùng credential thật trong test.
5. Nếu là thay đổi matching, chạy fast suite rồi slow suite khi máy rảnh.

## QA trước release

```powershell
& ".\.venv\Scripts\python.exe" -m pytest
& ".\.venv\Scripts\python.exe" -m pytest -m slow
& ".\.venv\Scripts\ruff.exe" check .
& ".\.venv\Scripts\python.exe" -m pip_audit -r requirements.txt --progress-spinner off
& ".\.venv\Scripts\python.exe" dong_goi.py --output "$env:TEMP\TimClipPro_source_release_check.zip"
```

Source packager mặc định từ chối overwrite; chỉ dùng `--overwrite` khi target đã được xác minh.

## Docker

```powershell
docker version
docker compose build
docker compose up -d
docker compose ps
Invoke-WebRequest -UseBasicParsing "http://127.0.0.1:8501/_stcore/health"
```

`.dockerignore` phải còn rule cho `google_key.json`, `data/`, `ketqua/`, `.venv/`, `bin/`,
log và archive. Credential chỉ mount read-only khi cần.

## Hạn chế vận hành đang mở

- yt-dlp có retry hữu hạn và timeout 30 giây; Google API vẫn phụ thuộc timeout của SDK.
- Process-tree cancellation đã test cho fingerprint với process giả root + child; các flow khác và database rất lớn chưa soak-test.
- Scan tương tác chưa dùng job temp directory riêng/lock chung.
- GUI có structured technical log riêng cho fingerprint; scan/channel chưa dùng chung facade.
- Docker build cần nghiệm thu lại trên máy có daemon.


---

## Chẩn đoán nhanh hai lỗi đã gặp

### A. "Tạo vân tay có vẻ đứng im"

1. Mở `ketqua\fingerprint.log` — job đang sống thì phải có dòng mới ít nhất mỗi ~10 giây:

   ```
   INFO fingerprint.job.<k> job_id=<id> event=clip start index=<i> total=<n> file='...' pid=<pid>
   INFO fingerprint.job.<k> job_id=<id> event=heartbeat phase=fingerprinting pid=<pid>
   ```

2. Không có dòng nào trong > 30 giây ⇒ xem PID audfprint hiển thị trên màn hình tiến độ
   ("PID audfprint: <pid>") rồi kiểm tra tiến trình con:

   ```powershell
   Get-CimInstance Win32_Process -Filter "ParentProcessId=<pid>" | Select-Object ProcessId, Name
   ```

   Đừng bao giờ `Stop-Process -Name python` — sẽ giết cả GUI. Dùng nút **⏹️ Dừng lại**;
   nó dọn đúng cây PID gốc và giữ nguyên kho vân tay trước job.

3. Màn hình hiện "Clip hiện tại đang xử lý lâu hơn bình thường" là **bình thường** với
   clip dài; phần trăm cố tình không tăng giả khi clip chưa xong.

> Bối cảnh: bản cũ đếm tiến độ bằng cách bắt chuỗi `ingesting #` trên stdout audfprint.
> Với `--ncores > 1` (mặc định = số nhân CPU) audfprint **không in dòng đó**, nên giao
> diện đứng im suốt cả batch. Xem `docs/CLAUDE_AUDIT_REPORT.md` §3.

### B. "Báo cáo thiếu danh sách video gốc"

Chạy diagnostic **chỉ đọc** (không sửa gì, không gọi mạng):

```powershell
& ".\.venv\Scripts\python.exe" kiem_metadata_kho.py --video-id <YOUTUBE_ID>
```

Đọc ba con số đầu:

| Quan sát | Ý nghĩa | Xử lý |
|---|---|---|
| `Số metadata entry` ≪ `Số clip trong database` | Kho tải trước khi có tính năng metadata | Chạy `vameta` (xem dưới) |
| `Fallback từ filename` cao | Có link + tên, thiếu ngày đăng/thời lượng | Chạy `vametak` (cần mạng) |
| `Ánh xạ mơ hồ` > 0 | Nhiều candidate cùng ID/tên — hệ thống **cố ý không tự chọn** | Kiểm tra `clips_meta.json` thủ công |
| `Không thể ánh xạ` > 0 | Tên file không có `[VIDEO_ID]` | Đổi tên file hoặc bổ sung entry thủ công |

Vá metadata (chỉ khi bạn chủ động muốn gọi mạng):

```powershell
# Vá clips_meta.json của một thư mục kho; tự bổ sung entry cho clip đã có trên đĩa
& ".\.venv\Scripts\python.exe" cli.py vameta --kho "D:\ClipGocCory"

# Vá snapshot của kho đang dùng, duyệt toàn bộ clip trong fingerprint DB
& ".\.venv\Scripts\python.exe" cli.py vametak
```

Khôi phục **offline** (không mạng, chỉ dựng lại snapshot từ tên file):

```powershell
& ".\.venv\Scripts\python.exe" kiem_metadata_kho.py --repair-offline          # dry-run
& ".\.venv\Scripts\python.exe" kiem_metadata_kho.py --repair-offline --apply  # ghi snapshot
```

> Lưu ý: clip **tải từ 2026-08-07 trở đi** đã có tên `YYYYMMDD - ...` và đủ ngày đăng
> trong `clips_meta.json` — ngày đăng thật được lấy sẵn trong lượt tải, không tốn thêm
> request. Clip tải **trước** đó vẫn mang tiền tố `00000000` (bản cũ dùng `extract_flat`
> của yt-dlp, chế độ này không trả `upload_date`). Ngày đăng của nhóm cũ **không thể phục
> hồi offline** — bắt buộc chạy `vameta`/`vametak`. Không đổi tên file đã có: sẽ làm lệch
> khoá `clips_meta.json` và `downloaded.txt`.
