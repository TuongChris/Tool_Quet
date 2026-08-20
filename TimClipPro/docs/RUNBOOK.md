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

## Khi một lượt quét trả về 0 đoạn

Từ 2026-08-07 hệ thống **luôn nói mất ở tầng nào**, không còn chỉ nói "không tìm thấy".
Đọc dòng giải thích trên GUI (mục "🔎 Chi tiết chẩn đoán") hoặc phần phễu ở CLI rồi xử
lý theo bảng:

| Giai đoạn báo về | Nghĩa là gì | Làm gì |
|---|---|---|
| `khong_cat_duoc_khuc` | ffmpeg không cắt được khúc nào | Kiểm file tải về trong `data\downloads` có phát được không |
| `audfprint_khong_ra_match` | Không có một dòng khớp nào | Kiểm đang chọn **đúng kho**; kiểm kho có clip (`db_clips`) |
| `parser_hong` | audfprint có ra dòng khớp nhưng đọc không được | **Lỗi code** — định dạng output đã đổi, phải sửa `RE_MATCH` |
| `bang_chung_qua_yeu` | Có dòng khớp nhưng quá ngắn/quá ít hash | Nhiều khả năng video không chứa clip gốc nào |
| `khong_dat_chap_nhan` | Có ứng viên nhưng chưa đạt chuẩn | Xem "ứng viên mạnh nhất bị loại" — xem mục dưới |
| `chon_loc_bo_het` | Đạt chuẩn nhưng Top-N bỏ hết | **Lỗi logic chọn lọc**, phải sửa |

**Đọc ứng viên mạnh nhất bị loại.** Nếu nó có *phủ vân tay dưới ~5%* và *đoạn khớp chỉ
vài giây*, gần như chắc chắn đó là **nhạc hiệu/nhạc nền dùng chung** giữa nhiều clip
gốc, không phải bản reup. Dấu hiệu xác nhận: cùng một mốc thời gian khớp với hàng chục
clip gốc khác nhau. **Không hạ ngưỡng trong trường hợp này** — hạ ngưỡng chỉ biến đoạn
nhạc hiệu 9 giây thành "bằng chứng vi phạm" trong báo cáo.

Một bản reup thật trông rất khác: hàng nghìn hash, khớp liên tục hàng phút, phủ vân
tay hàng chục phần trăm, và chỉ khớp với **một** clip gốc.

Bản ghi chẩn đoán của mỗi ca 0 kết quả được lưu tại `data\chan_doan\*.json` (giữ 200
file gần nhất, chỉ số liệu, không chứa media hay khoá bí mật):

```powershell
Get-ChildItem "data\chan_doan" | Sort-Object LastWriteTime -Descending | Select-Object -First 5
```

Chi tiết: [ZERO_MATCH_ROOT_CAUSE.md](ZERO_MATCH_ROOT_CAUSE.md).

### Video bị đổi tốc độ để né nhận dạng — đã có bù tự động

Đo thật: lệch tốc độ **0,5%** làm một đoạn khớp 263 giây vỡ thành mảnh dài nhất 21
giây; lệch 4% thì gần như mất trắng. Ngược lại, nén lại (AAC 64k, Opus 32k), đổi âm
lượng (±dB) và lọc tần số hầu như không ảnh hưởng.

Từ 2026-08-07, khi lượt quét thường không có ứng viên nào đạt chuẩn, hệ thống **tự
động thử bù tốc độ** rồi quét lại. Video có kết quả bình thường không tốn thêm giây nào.

Trên GUI, nếu một kết quả chỉ khớp được sau khi bù, sẽ có dòng thông báo riêng —
**đó là dấu hiệu né nhận dạng có chủ ý, nên đưa vào hồ sơ khiếu nại.**

Vùng phủ mặc định: đổi tốc độ giữ cao độ **±6%** (đọc trực tiếp từ độ trôi, miễn phí),
đổi cao độ **±5%** (lưới quét mù + tinh chỉnh). Ngoài vùng đó thì thêm mức vào cấu hình:

```powershell
# thêm mức cho video bị tăng/giảm tốc mạnh hơn ±6%
# eng.config.luoi_tempo = [0.90, 1.10]
```

Muốn tắt hẳn (về đúng hành vi cũ): `quet_da_toc_do = False`.
Chi tiết và số đo: [DA_TOC_DO.md](DA_TOC_DO.md).

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

## Thời lượng video hiển thị lệch 1 giây

Từ 2026-08-07 thời lượng media được **cắt** phần lẻ (giống trình phát) chứ không làm
tròn. Nếu vẫn thấy lệch, phân biệt hai trường hợp:

**Video vi phạm** — đã sửa hẳn, giá trị lấy từ FFprobe của chính file đang quét (trùng
`video.duration` của YouTube tới 3 ms).

**Clip gốc** — `clips_meta.json` chỉ lưu `lengthSeconds` của YouTube, vốn đã làm tròn,
nên khoảng 48% clip dư một giây cho tới khi bổ sung độ dài thật:

```powershell
& ".\.venv\Scripts\python.exe" kiem_thoi_luong.py                  # chỉ kiểm tra
& ".\.venv\Scripts\python.exe" kiem_thoi_luong.py --sua --that-su  # ghi thật (có .bak)
```

**Sau khi nạp lại kho hoặc đổi tham số nén** thì giá trị cũ không còn khớp file; mặc
định công cụ bỏ qua mục đã có, phải thêm `--ghi-de` để đo lại:

```powershell
& ".\.venv\Scripts\python.exe" kiem_thoi_luong.py --ghi-de --sua --that-su
```

Sau khi ghi, khởi động lại app để cache metadata nạp lại.
Chi tiết: [DURATION_ARCHITECTURE.md](DURATION_ARCHITECTURE.md).

## Tải video báo HTTP 403 Forbidden

Triệu chứng: quét ra lỗi `unable to download video data: HTTP Error 403: Forbidden`,
nhưng tool vẫn hiện đúng **tiêu đề** video.

Đó chính là dấu hiệu nhận dạng: trích metadata vẫn chạy, chỉ khâu **tải** bị chặn.
Link không hỏng — YouTube đang chặn "player client" mà yt-dlp dùng.

**Cảnh giác với cache.** `download_audio()` dùng lại file có sẵn trong `data\downloads`,
nên vài video vẫn chạy được và che mất mức độ nghiêm trọng. Kiểm bằng tỉ lệ lỗi theo ngày:

```powershell
& ".\.venv\Scripts\python.exe" -c "import sqlite3;[print(r) for r in sqlite3.connect('data/lichsu.db').execute(\"select substr(created_at,1,10),count(*),sum(status='ok'),sum(status!='ok') from jobs group by 1 order by 1 desc limit 7\")]"
```

Từ 2026-08-18, `download_audio()` **tự thử lần lượt nhiều client** nên thường tự khỏi.
Nếu vẫn lỗi hết, đổi thứ tự trong `data\cau_hinh.json`:

```json
"ytdlp_player_clients": ["android", "", "tv", "ios", "web_safari"]
```

Tìm client nào còn sống bằng cách thử tay:

```powershell
& ".\.venv\Scripts\python.exe" -m yt_dlp -f ba --extractor-args "youtube:player_client=android" -o "%TEMP%\thu.%(ext)s" "https://youtu.be/VIDEO_ID"
```

Chuỗi rỗng `""` nghĩa là để yt-dlp tự chọn. Nếu mọi client đều hỏng thì mới nên nghi
yt-dlp cũ: `& ".\.venv\Scripts\python.exe" -m pip install -U yt-dlp`.

Từ 2026-08-18, **cả hai đường tải** đều có đường lui này: quét video dài
(`engine.download_audio`) và đồng bộ kênh (`ChannelSync._tai_va_nen`). Cả hai đọc
cùng một danh sách nên chỉ cần sửa `data\cau_hinh.json` một lần.

Nếu đồng bộ kênh báo lỗi kèm chữ **"giới hạn độ tuổi"**: đó không phải lỗi tool —
YouTube bắt đăng nhập mới cho tải video đó, mọi client đều bị. Bỏ qua hoặc nạp cookie.

Băng thông: client `android` không có format audio-only nên đồng bộ kênh tải cả video
rồi mới bóc tiếng (khoảng 80 MB thay vì 16 MB cho clip 15 phút). File `.opus` trong kho
vẫn nhỏ như cũ. Khi client mặc định hết bị chặn, đưa `""` lên đầu danh sách để tiết kiệm.


## Lỗi «Sign in to confirm you're not a bot»

Khác hẳn lỗi 403 ở mục trên, dù nhìn cũng giống "không tải được".

**Cách nhận ra ngay:** thử lại một video mà **hôm qua vẫn tải được**. Nếu nó cũng hỏng
thì đây là chặn theo ĐỊA CHỈ MẠNG, không phải link hỏng. Dấu hiệu phụ: liệt kê danh
sách kênh vẫn chạy bình thường, chỉ lấy thông tin từng video mới hỏng.

Đổi player client **không** cứu được: bot-check đánh ở khâu lấy thông tin, còn đường
lui client chỉ chữa khâu tải.

### Xử lý theo thứ tự

1. **Dừng quét, nghỉ vài tiếng.** Chặn này tự hết hạn. Quét tiếp trong lúc bị chặn chỉ
   làm nó kéo dài thêm.
2. **Giãn nhịp** — thanh bên → «🔐 Kết nối YouTube» → *Nghỉ giữa các lượt hỏi
   YouTube*. Mặc định 1 giây; đang bị chặn thường xuyên thì nâng lên 2–3 giây.
   Trong `data\cau_hinh.json` là `ytdlp_sleep_requests_s`.
3. **Nạp cookie** nếu vẫn cần chạy ngay. Hai cách, chỉ cần một:
   * Gõ tên trình duyệt đang đăng nhập YouTube vào ô *Lấy thẳng từ trình duyệt*
     (`chrome`, `edge`, `firefox`... — nhiều profile thì `edge:Profile 1`).
     **Đóng hẳn trình duyệt trước khi quét**, nếu không nó khoá file cookie.
   * Hoặc xuất `cookies.txt` bằng tiện ích trình duyệt rồi trỏ đường dẫn vào ô còn lại.

⚠️ Cookie là chìa khoá vào tài khoản — đừng chia sẻ file đó, nên dùng tài khoản phụ,
và biết rằng nó hết hạn sau vài tuần. Tool chỉ lưu **đường dẫn**, không bao giờ đọc hay
lưu lại nội dung cookie vào cấu hình.

Lưu ý khi bật cookie: yt-dlp tự gỡ các cách tải không dùng được cookie (`android`,
`ios`), nên tool đẩy chúng xuống cuối danh sách. Nếu cookie hết hạn, chúng vẫn là
đường lui.

## Bảng kết quả trắng xoá / trang lỗi sau khi quét

Nếu terminal có `ArrowInvalid ... Conversion failed for column ...`: một nguồn quét bị
lỗi làm cột số lẫn kiểu, PyArrow từ chối và cả bảng không vẽ được. Đã sửa từ
2026-08-18 (`Engine.COT_SO` + `app.df_ket_qua`). Nếu tái diễn ở cột MỚI, thêm tên cột
đó vào `Engine.COT_SO` — đừng vá riêng lẻ ở giao diện.

## File cookie báo «sai định dạng Netscape ở dòng N»

Tool tự kiểm file cookie trước khi dùng và **cố tình không in nội dung dòng hỏng** —
dòng đó chính là bí mật đăng nhập của bạn.

Nguyên nhân gần như luôn là: mở `cookies.txt` bằng Notepad rồi lưu lại, TAB biến thành
dấu cách. Cách sửa: **xuất lại bằng tiện ích trình duyệt, đừng sửa tay**.

Không cần lo cho các file log cũ: tính năng cookie chỉ có từ 18/08/2026 và rào chắn
này ra đời cùng ngày, nên chưa có bản nào từng chạy với cookie mà thiếu nó.
