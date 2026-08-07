# Kiến trúc quan sát tiến trình tạo vân tay

Ngày xác minh: 2026-08-06.

## Mục tiêu và phạm vi

Thiết kế này chỉ thay đổi cách quan sát, điều phối và commit tác vụ tạo/bổ sung kho vân tay.
Thuật toán `audfprint`, `_merge`, threshold, top-N, shifts và định dạng `.pklz` không thay đổi.
SQLite `data/lichsu.db` không nằm trong call flow tạo vân tay; database vân tay thực tế là gzip
pickle `.pklz` do `audfprint` ghi.

## Call flow

```text
app.py: nút Tạo lại/Bổ sung
  -> chay_van_tay()
  -> FingerprintJobController.start()
       -> một worker thread gọi Engine.build_database()
            -> khóa data/tool.lock
            -> discover + kiểm tra record đã có hash
            -> tạo data/fingerprint_jobs/<job_id>/
            -> Engine._audfprint_build_cmd()
            -> audfprint_progress_runner.py
                 -> audfprint vendored, cùng Analyzer/HashTable/CLI arguments
                 -> event JSON trước/sau wavfile2hashes của từng clip
            -> Engine._run_stream()
                 -> process_runner.run_observed_process()
                 -> đọc stdout liên tục + poll cây process + heartbeat
            -> ghi/merge database tạm
            -> os.replace(database tạm, database thật) khi thành công
       -> queue bounded
  -> main Streamlit execution drain queue
  -> cập nhật các placeholder cố định và logger
```

`cli.py taodb/themclip` gọi cùng `Engine.build_database()`. Vì tracker phát log độc lập với
Streamlit, terminal nhận cùng trạng thái clip/phase/PID trong lúc job đang chạy.

## Vì sao kiến trúc cũ im lặng

Luồng cũ đã có thread nền ở UI, nhưng chỉ truyền callback `(percent, message)` và worker sửa
trực tiếp một `dict` trong session. `Engine._build_database_da_khoa()` đưa toàn bộ danh sách vào
một lệnh audfprint. Ở chế độ nhiều core, `audfprint.multiproc_add()` chia round-robin toàn bộ file
cho worker rồi parent chỉ in `hash_table N has ... files` sau khi một worker xử lý xong cả phần
của nó. Với 1.717 clip và 8 core, tín hiệu hữu ích đầu tiên có thể phải chờ một worker hoàn tất
khoảng 215 clip.

Đồng thời `_run_stream()` cũ lặp trực tiếp trên `p.stdout`; khi process không in dòng mới, thread
bị chặn ở thao tác đọc nên không thể poll PID, heartbeat hoặc phản hồi cancel. Callback không nhận
được tên clip, phase, kết quả từng file hay bộ đếm thật. Đây là nguyên nhân xác định, không phải do
Streamlit trì hoãn render một progress bar đã được cập nhật.

## Contract `FingerprintProgress`

Dataclass immutable trong `fingerprint_progress.py` có các nhóm trường:

- Identity/state: `job_id`, `phase`, `status`, `message`.
- Vị trí: `current`, `total`, `file_name` (chỉ basename đã làm sạch).
- Bộ đếm thật: `success_count`, `skipped_count`, `failed_count`, `processed_count`.
- Thời gian: `elapsed_seconds`, `eta_seconds`, `rate_per_minute`, `updated_at`,
  `last_progress_at`, `current_clip_started_at`, `last_db_write_at`.
- Chẩn đoán: `active_subprocess_pid`, `worker_alive`, `queue_size`, `error_category`.

`percent` luôn lấy từ `processed_count / total`; heartbeat không thay đổi bộ đếm. Tracker giữ các
invariant: bộ đếm không âm, một path chỉ kết thúc một lần, `processed_count` là tổng success + skip
+ failure và phần trăm bị chặn trong `[0, 1]`.

## Phase và status

| Phase | Ý nghĩa quan sát được |
|---|---|
| `discovering` | Đang duyệt thư mục để lập danh sách media |
| `validating` | Đang kiểm record có hash và chuẩn bị database làm việc |
| `probing` | Dành cho adapter có bước probe riêng; build hiện tại không gọi FFprobe riêng |
| `decoding` | Có descendant `ffmpeg.exe` đang sống |
| `fingerprinting` | audfprint/worker Python đang chạy |
| `saving` | audfprint đang merge/store hoặc Engine đang thay database tạm |
| `completed` | Đã có terminal event hoàn tất |
| `cancelled` | Worker đã xác nhận cancel và dọn process/workspace |
| `failed` | Lỗi cấp job; chi tiết kỹ thuật ở log |

Status của clip phân biệt `success`, `skipped_existing`, `failed`; controller còn dùng
`cancel_requested` trong khoảng người dùng yêu cầu dừng nhưng worker chưa xác nhận.

## Worker, queue và Streamlit session

- Mỗi session giữ đúng một `FingerprintJobController` trong `st.session_state`.
- `start()` từ chối khi thread/job cũ còn chạy và sinh một `job_id` duy nhất.
- Worker chỉ gọi Engine và publish dataclass; không gọi API Streamlit.
- Queue thread-safe có tối đa 256 phần tử. Khi đầy, event cũ nhất bị bỏ để snapshot mới nhất vẫn
  đến UI; snapshot tổng hợp không bị mất.
- UI chỉ giữ 50 event gần nhất và render 20 dòng; không giữ stdout audfprint/FFmpeg vô hạn.
- Main Streamlit thread drain queue, dùng các placeholder cố định và rerun 0,75 giây/lần. Không
  tạo hàng nghìn component và không update theo mỗi dòng stderr.
- Refresh/rerun không tự gọi `start()`. Session mới cũng không tự tạo job; khóa liên tiến trình
  `data/tool.lock` vẫn chặn hai job thật dùng chung data directory.

## Theo dõi subprocess và heartbeat

`process_runner.py` chạy root process với stdout/stderr gộp, một reader thread và queue output
bounded 256 dòng. Main loop poll mỗi tối đa 0,2 giây nên không chờ `readline()` khi process im lặng.
Nó giữ 30 dòng cuối, không giữ toàn bộ output, và quan sát descendant bằng `psutil`.

Heartbeat chứa PID audfprint, số worker Python, số FFmpeg và thời gian không có output. Nó phát khi
cây process đổi hoặc theo chu kỳ 10 giây; tracker chặn tần suất tối đa khoảng 4 event/giây. Heartbeat
không tăng phần trăm. Sau 120 giây process có warning kỹ thuật; UI cảnh báo clip lâu từ 120 giây hoặc
không có event mới 15 giây trong khi worker vẫn sống.

Cancel chỉ terminate root PID của job và descendants được xác định từ root đó, chờ có hạn rồi mới
kill PID còn sống. Không có thao tác kill theo tên process.

## Logging

Mỗi job ghi đồng thời ra stdout và `ketqua/fingerprint.log` (hoặc output directory đã inject).
Format gồm timestamp, level, logger, `job_id`, event, current/total, basename và PID. File quay vòng
ở 5 MiB, giữ ba backup và dùng UTF-8. Handler được flush ngay và đóng cuối job để Windows không giữ
file handle.

Không log raw fingerprint, command đầy đủ, URL/token/cookie/header hay absolute path của clip. Khi
subprocess lỗi, UI chỉ nhận thông báo dễ hiểu; log kỹ thuật giữ exit code, loại process, duration và
tail tối đa 30 dòng đã loại structured event chứa path.

## Commit database và lỗi từng clip

- Chế độ `add` copy database hiện tại sang workspace theo chunk 8 MiB và fsync.
- audfprint chỉ sửa database tạm. Database thật chỉ được `os.replace()` sau exit code 0 và file tạm
  hợp lệ; cancel/lỗi giữ nguyên kho cũ.
- Clip có record với `so_hash > 0` được skip và vẫn tính vào tổng đã xử lý.
- Record zero-hash không được coi là hợp lệ nên sẽ được thử lại lần sau.
- File không decode/không sinh hash phát `failed`, tăng bộ đếm, và các clip độc lập còn lại tiếp tục
  nhờ `--continue-on-error` hiện có của audfprint.
- Vì audfprint chỉ store `.pklz` cuối batch, các success đang hiển thị lúc chạy là “đã tính xong”;
  nếu cancel thì phần staged chưa commit bị bỏ, không báo là đã lưu thành công.

## ETA

ETA chỉ xuất hiện sau tối thiểu ba completion có công việc thực, dùng tốc độ của tối đa 20 completion
gần nhất. Tổng 0, job đã hoàn tất, span thời gian 0 và tốc độ 0 đều trả ETA rỗng; không chia cho 0.
Skip vẫn tăng progress nhưng không làm tốc độ xử lý audio bị phóng đại.

## Chẩn đoán khi progress không đổi

1. Xem `Cập nhật gần nhất`, `Worker`, PID audfprint và thời gian clip hiện tại trên UI.
2. Mở log trực tiếp:

   ```powershell
   Get-Content ".\ketqua\fingerprint.log" -Encoding UTF8 -Wait -Tail 50
   ```

3. Tìm `event=process_start`, `process_child_start`, `event=heartbeat` và `event=process_end` cùng
   `job_id`; không chỉ nhìn phần trăm.
4. Kiểm PID cụ thể, không kill theo tên:

   ```powershell
   Get-Process -Id <PID>
   ```

5. Nếu `worker_alive=False` nhưng không có terminal event, xem traceback trong log và chạy lại bằng
   một fixture nhỏ trên data/output tạm.
6. Nếu phase `saving` lâu, kiểm disk free, antivirus/file lock và quyền ghi data directory. Không xóa
   `.pklz` hoặc `data\fingerprint_jobs` khi PID job còn sống.

## Hạn chế còn lại

- Chưa chạy nghiệm thu trên toàn bộ 1.717 clip production theo yêu cầu an toàn.
- Database audfprint không lưu mtime/size/content hash, nên hiện chỉ phân biệt fingerprint hợp lệ với
  zero-hash; chưa tự biết một file cùng path đã đổi nội dung.
- Commit vẫn ở cuối batch theo định dạng/CLI audfprint. Cancel giữ kho cũ nhưng không resume phần staged.
- `probing` không phát trong build hiện tại vì adapter audfprint gọi FFmpeg trực tiếp, không có bước
  FFprobe riêng.
- Controller là in-process. Khóa file ngăn hai job trên cùng data directory, nhưng chưa có registry
  bền vững để một browser session mới tiếp quản UI của worker thuộc process Streamlit đã chết.
- Logging có cấu trúc đầy đủ cho fingerprint flow; các flow scan/channel cũ chưa dùng cùng facade.


---

## Vì sao audfprint không in gì khi `--ncores > 1`

Tài liệu này mô tả đúng cơ chế **đọc stdout bị chặn**. Nhưng nguyên nhân **đầu tiên** khiến
giao diện đứng im còn nằm ở tầng cao hơn: ở cấu hình production, audfprint **không in một
dòng per-file nào để mà đọc**.

`Config.ncores = 0` (giá trị trong `data/cau_hinh.json` thật) ⇒ `so_nhan_nen_dung()` = 8 trên
máy này. Với `ncores > 1`, `audfprint.py:474` chuyển sang `do_cmd_multiproc` →
`multiproc_add` (`audfprint.py:272`) → `make_ht_from_list` (`audfprint.py:130`), hàm này gọi
**thẳng** `analyzer.wavfile2hashes()`. Chuỗi `"ingesting #"` chỉ được in ở `audfprint.py:178`
— nhánh **một nhân** — và `audfprint_analyze.py:572` (hàm không được dùng).

Đo trực tiếp trên audfprint vendored, 3 file WAV tổng hợp:

| `--ncores` | tổng dòng stdout | dòng chứa `ingesting #` |
| ---: | ---: | ---: |
| 1 | 23 | **3** |
| 2 | 6 | **0** |
| 8 | 12 | **0** |

Vì vậy `audfprint_progress_runner.py` bắt buộc phải bọc **cả hai** đường:
`make_ht_from_list` cho nhánh đa nhân và `Analyzer.ingest` cho nhánh một nhân. Chỉ sửa
`_run_stream` thành non-blocking là **chưa đủ** — sẽ vẫn không có event nào để phát.

Regression test giữ tính chất này: `tests/test_fingerprint_progress_streaming.py` dùng
audfprint giả **không in `ingesting #`** và khẳng định bằng
`assert "ingesting #" not in AUDFPRINT_GIA`.
