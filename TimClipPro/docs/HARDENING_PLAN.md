# Kế hoạch hardening sau audit độc lập 4b7e5bd

Tài liệu này ghi **quyết định** cho vòng khắc phục 16 phát hiện TCP-01…TCP-16 của
`TIMCLIPPRO_INDEPENDENT_AUDIT_4b7e5bd.md`. Trạng thái từng mục, test và bằng chứng nằm ở
`HARDENING_FIX_MATRIX.md`; kết quả nghiệm thu ở `HARDENING_VALIDATION_REPORT.md`; dữ liệu và
quay lui ở `DATA_MIGRATION_AND_RECOVERY.md`.

**Trạng thái (02/10/2026):** G1–G10 đã triển khai, cả 16 mục `FIXED_AND_VERIFIED` trên Windows
native; hai vòng phản biện độc lập đã xử lý (vòng 2 bắt và sửa một hồi quy do chính vòng 1 gây ra
— mục *Bổ sung sau vòng phản biện 2*). Chưa commit; chưa chạy bước ghi nào trên dữ liệu thật (chờ
phê duyệt — xem báo cáo).

## 0. Phạm vi và môi trường làm việc

| | |
|---|---|
| Repo | `C:\Users\Admin\OneDrive\Desktop\ToolQuet\Tool_Quet` (git toplevel) |
| Revision gốc | `4b7e5bd` (nhánh `sua-watchdog-van-tay`), trùng commit audit khai báo |
| Nơi sửa | **worktree riêng** `…\ToolQuet\Tool_Quet_hardening`, nhánh `hardening-sau-audit` |
| Thư mục chạy thật | `Tool_Quet\TimClipPro` (có `data/`, `.venv`, `bin/`) — **không sửa**, chỉ đọc |
| Interpreter nghiệm thu | `Tool_Quet\TimClipPro\.venv\Scripts\python.exe` (3.12.10, đúng bản app chạy) + pytest 9.1.1 nạp qua `PYTHONPATH` từ thư mục nháp, `PYTHONDONTWRITEBYTECODE=1` để không ghi vào `.venv` |

Vì sao worktree riêng: `ChayTool.bat` chạy app từ thư mục thật. Nếu sửa tại chỗ, lần mở app
kế tiếp sẽ chạy code dở dang trên `data/` thật — kể cả migration SQLite chưa nghiệm thu.

Baseline trước khi sửa (interpreter của app, worktree sạch ở `4b7e5bd`):
`955 passed, 1 skipped` (nhóm thường) và `5 passed` (nhóm `slow`). Cả 14 ca tái hiện của
audit **tái hiện được trên Windows 11 / Python 3.12.10** với mã gốc.

## 1. Nguyên tắc không đổi

- Không sửa `audfprint-master/`; hash 19 file vendor được chụp ở đầu vòng để đối chiếu cuối vòng.
- Không đổi ngưỡng, Top-N, chiến lược nhận diện. TCP-05 là sửa **toán tọa độ**, đường `k = 1`
  phải cho ra kết quả y hệt.
- Hợp đồng báo cáo: ngang 34 cột (`bang_ngang.HEADER_NGANG`), dọc 16 cột (`Engine.HEADER`) giữ
  nguyên tên/thứ tự. Apps Script đọc cột theo **tên**.
- Dữ liệu thật (`.pklz`, `lichsu.db`, `clips_meta.json`, snapshot, `khos.json`, cấu hình, cookie,
  khoá Google) chỉ đọc trong vòng này. Mọi test chạy trên thư mục tạm.
- Không thêm thư viện. Mọi thứ mới dùng stdlib + `psutil` (đã có trong `requirements.txt`).

## 2. Thứ tự triển khai

Thứ tự đi theo phụ thuộc thật trong code, khác đề xuất một chút: hạ tầng process (TCP-14/15)
làm sớm vì TCP-04 (cắt khúc), TCP-10 (nén audio) và TCP-13 (huỷ) đều cần nó.

| Nhóm | Mục | Lý do đứng ở vị trí này |
|---|---|---|
| G1 | TCP-16, TCP-11 | Cổng kiểm thử phải đỏ được trước khi tin vào nó; chặn rò bí mật trước khi đóng gói thêm |
| G2 | TCP-03 | Giao thức ghi JSON là nền cho sổ đăng ký kho (TCP-01), metadata (TCP-09), tải kênh (TCP-10) |
| G3 | TCP-14, TCP-15 | Sở hữu cây process + timeout/huỷ cho FFmpeg/FFprobe, dùng lại ở G4/G6/G10 |
| G4 | TCP-13 | Vòng đời huỷ ở cấp batch |
| G5 | TCP-01, TCP-02 | Ghim job vào kho; kiểm tra kho tạm trước khi thay kho đang dùng |
| G6 | TCP-04, TCP-06 | Mô hình phạm vi quét; đưa phạm vi tới mọi artifact |
| G7 | TCP-05 | Hệ tọa độ khi bù tốc độ |
| G8 | TCP-07, TCP-08 | Lịch sử theo phạm vi kho/phiên bản; Watch fail-closed; migration SQLite |
| G9 | TCP-09, TCP-12 | Nguồn chuẩn metadata; định danh theo grammar tên file |
| G10 | TCP-10 | Nén vào staging, xác nhận rồi mới công bố |

Mỗi nhóm: test tái hiện (đỏ trên mã cũ) → sửa → test xanh → cả suite → cập nhật ma trận.

## 3. Quyết định theo nhóm

### G1 — TCP-16 cổng kiểm thử, TCP-11 đóng gói

**TCP-16.** `kiemtra.bat` ghi mã lỗi từng bước, bước AppTest phải `sys.exit(1)` khi
`at.exception` khác rỗng, kết thúc bằng `exit /b` mang mã lỗi gộp. `pause` chỉ chạy khi không
có biến `KIEMTRA_KHONG_DUNG` (để chạy tự động không bị treo chờ phím). Thiếu pytest là **lỗi**,
không được bỏ qua. Biến `KIEMTRA_PY` cho phép chỉ định interpreter có pytest (vì `.venv` của app
không cài pytest) — mặc định giữ thứ tự cũ. Giữ CRLF cho file `.bat`.

**TCP-11.** Phân loại file theo mục đích thay vì chỉ theo đuôi:
- chặn theo **từng thành phần đường dẫn** (thư mục `credentials`, `secrets`, `.ssh`, `cookies`…);
- chặn tên cookie (`*cookie*` với file dữ liệu), `.env` ở mọi cấp, khoá (`*.pem`, `*.key`, `*.p12`, `*.pfx`);
- với file dữ liệu (`.json/.txt/.toml/.ini/.cfg/.yml/.yaml/.env`) kiểm **nội dung**: khối PEM private
  key, `"private_key"`, `"type": "service_account"`, `client_secret`, `refresh_token`, header/dòng
  cookie Netscape. File `.py/.md` không bị quét nội dung (test của chính dự án chứa marker giả);
- bỏ qua symlink/junction/reparse point;
- thêm `.gs` (Apps Script là mã nguồn thật, trước đây bị bỏ sót);
- hậu kiểm ZIP bằng **bộ kiểm độc lập** (đọc lại từng entry, quy tắc riêng), không gọi lại helper lọc.
`dong_goi_may_chay.py` dùng chung bộ lọc mã nguồn và chịu cùng hậu kiểm.

### G2 — TCP-03 ghi JSON an toàn giữa các process

Ba vấn đề tách bạch, ba cơ chế:
1. **Va chạm staging** — tên tạm duy nhất mỗi lần ghi: `<file>.<pid>.<ngẫu nhiên>.tmp`, cùng thư mục.
2. **Loại trừ lẫn nhau** — khoá OS trên file `<file>.lock` (msvcrt/fcntl, có chờ + hạn), lồng trong
   `RLock` theo đường dẫn để cùng một thread vào lại được (đường phục hồi từ `.bak` gọi ghi bên trong đọc).
3. **Mất cập nhật** — API giao dịch `cap_nhat_json(path, ham_sua)`: dưới cùng một khoá, đọc bản mới
   nhất → hàm sửa → ghi. Mọi chỗ đọc-sửa-ghi (`khos.json`, `clips_meta.json` khi sync/vá/sửa ngày/
   thời lượng, `cau_hinh.json`, watchlist, snapshot) chuyển sang API này và chỉ gộp **các entry mình
   đổi** vào bản mới nhất.

`.bak` chỉ được làm mới từ file chính **đọc được**; file chính hỏng thì giữ `.bak` cũ.
`os.replace` trên Windows thử lại có giới hạn khi gặp `PermissionError` (reader khác đang mở file).
Không giữ khoá JSON trong lúc gọi mạng hay chạy tác vụ dài.

### G3 — TCP-14/15 sở hữu process, timeout và huỷ

- Windows: mỗi subprocess dài chạy trong một **Job Object** `KILL_ON_JOB_CLOSE` (ctypes, không thêm
  thư viện). Huỷ/timeout/kết thúc đều `TerminateJobObject` → giết trọn cây kể cả khi process cha
  đã chết; nếu chính app chết, handle đóng và Windows tự dọn cây. POSIX: process group.
- Không giết theo tên, không giết PID cũ chưa xác minh.
- Helper chung cho FFmpeg/FFprobe: đọc `-progress pipe:1` để đo **tiến triển thật**; timeout theo
  **im lặng** (không có tiến triển), không đặt hạn chót tổng cho tác vụ đang chạy khoẻ. FFprobe là
  thao tác ngắn nên có hạn tổng riêng. stdout/stderr được rút liên tục, giữ phần đuôi có giới hạn.
- `audfprint_progress_runner`: khi dọn worker lỗi, dừng cây con của worker trước rồi mới worker,
  `join` có hạn; runner tự gắn vào Job Object riêng để mọi hậu duệ chết theo nó.
- Bản sửa watchdog 1800 s (commit `f3befe8`) giữ nguyên.

### G4 — TCP-13 vòng đời huỷ

Cờ huỷ thuộc về **job/batch**: chỉ xoá đúng một lần lúc bắt đầu job. `scan_iter` kiểm cờ trước mỗi
video và dừng hẳn sau video bị huỷ; `scan_youtube`/`scan_media` khi chạy bên trong batch không xoá
cờ. API quét đơn lẻ vẫn tự xoá cờ ở đầu như cũ. Kết quả đã lưu giữ nguyên.

### G5 — TCP-01/02 ghim job vào kho, kiểm kho tạm

- Mỗi job (build, quét batch, quét đơn, Watch) chạy trên một **bản sao Engine được ghim**: tên kho,
  file `.pklz`, thư mục kho và một bản `deepcopy` của `Config` chụp lúc bắt đầu; dùng chung cờ huỷ
  và bộ nhớ client. Thanh bên đổi kho/tham số giữa chừng không chạm được job đang chạy.
- Bản sao không tự đổi kho theo `dang_dung` của sổ đăng ký. Mọi ghi sổ đăng ký trong job sửa đúng
  entry theo **tên kho đã ghim** qua giao dịch JSON (G2).
- Trước khi thay `.pklz`: kiểm sổ đăng ký vẫn trỏ kho đó tới đúng file đích (kho bị xoá/đổi file
  giữa chừng → từ chối công bố). Đọc kho tạm bằng loader an toàn của dự án, kiểm:
  - đọc được, có `names`/`hashesperid`;
  - **`new` mà 0 clip có hash** → thất bại, kho cũ nguyên vẹn;
  - `new` thay kho đang có: clip **từng có hash trong kho cũ** mà lần này lỗi → từ chối thay (không
    được âm thầm làm hẹp vùng phủ); clip mới/hỏng sẵn thì chỉ cảnh báo;
  - `add`: kho tạm phải chứa đủ mọi clip hữu ích của kho cũ; 0 clip mới hữu ích → không ghi gì.
- Quét không chạy song song với nửa kho cũ/nửa kho mới: job ghi lại chữ ký file kho (đường dẫn,
  kích thước, mtime) lúc bắt đầu và kiểm lại trước mỗi lượt so khớp; đổi giữa chừng → lỗi rõ ràng
  "kho vừa được cập nhật, hãy quét lại", không trộn.
- `delete_kho` lấy `tool.lock` (không xoá kho khi đang có build/Watch). Giao diện khoá chọn kho,
  nút xoá/sửa kho và ô tham số khi có job chạy.
- Sổ đăng ký thêm (additive) `id` (uuid khi tạo kho mới; kho cũ dùng định danh suy ra từ tên, **không
  ghi lại file**) và `revision` (đổi mỗi lần công bố kho). Phiên bản hiệu lực dùng cho lịch sử =
  `revision` + kích thước file kho, nên kể cả khi ghi sổ đăng ký thất bại sau khi đã thay kho, lịch
  sử vẫn thấy kho đã đổi.

### G6 — TCP-04/06 phạm vi quét

Tách rõ: đã cắt khúc / đã thực sự so khớp / đủ mục tiêu Top-N / đã kiểm đủ phạm vi yêu cầu.
- `_cut_chunks` thử lại khúc lỗi một lần; khúc vẫn lỗi, hoặc ngắn hơn kỳ vọng, được ghi thành
  **vùng lỗi**. Độ dài khúc đo từ header WAV.
- Khúc "đã so khớp" là khúc xuất hiện trong output của audfprint (dòng `Matched` hoặc `NOMATCH`);
  đường nhanh Top-1 chỉ tính đúng khúc đã gửi đi.
- `ScanResult` thêm: `vung_da_khop`, `vung_loi`, `ly_do_pham_vi` (`dung_som`, `gioi_han_tai`,
  `loi_khuc`, `huy`), `dat_muc_tieu`; `quet_day_du` = hợp các khoảng đã khớp phủ hết video và không
  có vùng lỗi. `pham_vi_quet_s` vẫn là trục đã quét tới (dùng chia vùng chọn lọc), không còn được
  dùng để khẳng định độ phủ.
- Chính sách khi có vùng lỗi: **không có bằng chứng đạt chuẩn** → `status = "error"` (chưa được kết
  luận âm tính, lịch sử không chặn quét lại); **có bằng chứng** → giữ `ok` + bằng chứng, đánh dấu
  chưa quét trọn.
- Đưa phạm vi tới người nhận mà không thêm cột: cột "Tên video vi phạm" (ngang) và "Nguồn video dài"
  (dọc) mang hậu tố `[QUÉT MỘT PHẦN: …]` — đúng quy ước sẵn có của dự án, vốn đã dùng chính cột này
  cho `(LỖI: …)`. Hồ sơ Markdown, CLI, giao diện và lịch sử (`note` + cột phạm vi mới) cùng ghi rõ.

### G7 — TCP-05 tọa độ khi bù tốc độ

Đã suy ra từ `toc_do_khop`: `he_so = 1/r`, bộ lọc làm khúc nhanh lên `he_so` lần nên
`t_video = offset + he_so·t_khúc`. Mốc đầu clip gốc trong video = `offset + he_so·(t_khúc − t_clip)`.
Mỗi mảnh thô mang `he_so`; `align` = mốc đầu clip trên trục video; `_merge` không gộp mảnh khác hệ
số; `clip_offset_s` ("khớp từ giây thứ của clip") giữ trên trục **clip gốc** (`t_clip`). Với
`he_so = 1` mọi giá trị y hệt trước — được khoá bằng test so sánh trước/sau. Ước lượng độ trôi
(`uoc_luong_toc_do`) vẫn dùng `bat_dau − t_clip` thô như thiết kế.

### G8 — TCP-07/08 lịch sử theo phạm vi, Watch fail-closed

- Migration SQLite **additive, có version** (`PRAGMA user_version` 0 → 1, module `lich_su.py`),
  idempotent: cột `kho_id`, `kho_ten`, `kho_phien_ban`, `chinh_sach`, `day_du`, `dat_muc_tieu`,
  `pham_vi` (JSON). Hàng cũ giữ giá trị trống = **không rõ kho**; không gán cho kho đang dùng,
  không xoá.
- Danh tính kho = `id` trong sổ đăng ký (kho cũ chưa có `id`: suy ổn định từ tên). Phiên bản hiệu
  lực = `revision` (đổi đúng lúc công bố kho mới) + kích thước file kho — không băm kho trăm MB,
  không dùng mtime. Chữ ký chính sách = băm các tham số làm đổi kết luận âm tính
  (`engine.TRUONG_CHINH_SACH`); Top-N, phân bố đều, cách tải không nằm trong đó.
- Quy tắc tái sử dụng (Watch bỏ qua video): cùng `kho_id`, `status = ok`, và
  (có bằng chứng) **hoặc** (không bằng chứng + quét trọn + cùng phiên bản kho + cùng chữ ký chính
  sách phát hiện). Lỗi/huỷ/chưa trọn không chặn quét lại. Có cờ quét lại chủ động
  (`--quet-lai`) không xoá lịch sử.
- Hệ quả vận hành cần biết: sau khi cập nhật, các video đã quét bằng bản cũ (không rõ kho) sẽ được
  Watch quét lại một lần, giới hạn bởi `gioi_han_moi_lan` mỗi lượt.
- Watch: watchlist chỉ định kho mà không mở được → dừng lượt **trước** liệt kê/tải/quét/xuất/Sheets.

### G9 — TCP-09/12 metadata

- **Nguồn chuẩn**: `clips_meta.json` của kho là nguồn chuẩn cho trường nó có; snapshot là bản dẫn
  xuất, dùng để điền trường trống và phục vụ khi thư mục kho offline. Lý do: mọi công cụ sửa
  (`kiem_ngay_dang`, `kiem_thoi_luong`, `ChannelSync.va_metadata`) ghi vào `clips_meta.json`, còn
  `va_metadata_thieu` chỉ vá trường còn thiếu nên vẫn hiện được. Đổi chính sách nằm ở CHỖ GÁN
  ưu tiên trong engine (`_metadata_source_candidates`: live 0, snapshot 10); resolver vẫn là "số
  ưu tiên nhỏ thắng" nên test resolver cũ (ưu tiên tường minh) giữ nguyên. Không dùng mtime.
  Khác biệt live/snapshot được ghi là `snapshot_lech` và cảnh báo "snapshot cũ", gợi ý chạy khôi
  phục metadata offline; lượt làm mới đó nay hội tụ về nguồn chuẩn.
- **Định danh**: chỉ token `[ID]` ngay trước phần mở rộng (grammar tên file của downloader) là ID của
  tên file; token 11 ký tự trong tiêu đề không còn tạo xung đột giả. Mâu thuẫn thật (tên file vs
  metadata vs URL) vẫn `ambiguous`.

### G10 — TCP-10 tải/nén có xác nhận

Nén vào file staging `.dang_nen.opus` trong thư mục tạm RIÊNG của lượt (`_tam/<pid>_<uuid>`, cùng
ổ với kho, giữ đuôi `.opus` cho FFmpeg chọn muxer), kiểm mã thoát + ffprobe + độ dài ≥ 90% nguồn
− 1 s (chỉ chặn chiều ngắn) → `os.replace` sang tên thật → ghi metadata (giao dịch G2) kèm dấu
`xac_nhan_tep` (kích thước, độ dài) → ghi archive. Lỗi/huỷ: xoá đúng staging của lượt đó; cuối
lượt chỉ xoá thư mục tạm của chính lượt (thư mục tạm của lượt chết > 3 ngày được dọn). Lần sync
sau: file trên đĩa chỉ được tính "đã có" khi có dấu `xac_nhan_tep` khớp kích thước (vòng phản
biện bỏ luật "có cả archive + metadata" vì hai nút bảo trì tạo được hai sổ đó cho file hỏng);
còn lại kiểm bằng ffprobe một lần rồi đóng dấu, chỉ khi có độ dài tham chiếu. File nghi hỏng
được **báo**, và chỉ được giữ vào `_hong/` (hard link/bản chép) ngay trước khi bản tải lại thay
chỗ; thay thất bại thì hoàn nguyên. File đã công bố mà thiếu metadata được đối soát cục bộ (tên
file + ffprobe), không gọi lại YouTube. Mỗi kho một lượt đồng bộ (`.dong_bo_kenh.lock`), mã trùng
trong danh sách bị lọc. Khi build, `liet_ke_media(…, bo_thu_muc_lam_viec=True)` bỏ qua `_tam/` và
`_hong/`; «Bổ sung» gỡ (`audfprint remove`) rồi tạo lại vân tay của clip có file bị thay sau lần
công bố kho gần nhất.

### Bổ sung sau vòng phản biện độc lập

- G6: khúc audfprint không đọc được (`Error reading`) và WAV hỏng header là vùng chưa khớp; lập
  khúc theo độ dài LUỒNG âm thanh (đuôi không tiếng là "đã kiểm"); file tải về ngắn hơn độ dài
  YouTube → phần thiếu là vùng lỗi; lượt bù tốc độ chạy lỗi khi không có kết quả → vùng chưa kiểm;
  `day_du` chỉ cho lượt `ok`.
- G8: `use_kho` kiểm đường dẫn kho trước khi ghi sổ; Watch so sổ đăng ký với kho Engine đang mở
  (bắt trường hợp Engine lặng lẽ lùi về `data/db.pklz`) và đòi kho có vân tay; kho mặc định tự
  tạo có `id`; gói máy phụ mang `id`/`revision`; không hạ `user_version`.
- G9: nguồn chuẩn (kể cả `.bak` của nó) thắng snapshot cả về mã video; ngữ pháp tên file chấp
  nhận đuôi bản sao của Windows.

### Bổ sung sau vòng phản biện 2 (kiểm lại chính các bản sửa trên)

- G6 — **hồi quy N1**: luật "`NOMATCH` 0,0 sec = lỗi đọc" của vòng 1 SAI (audfprint ghi 0,0 cho
  mọi khúc 0 hash, kể cả im lặng) → bỏ. Lỗi đọc = dòng stdout `Error reading`; lớp phòng thủ thứ
  hai = khúc 0 hash mà bộ đọc WAV của tool không đọc được. Video tắt tiếng là âm tính trọn.
- G6 — bù tốc độ: sổ theo (lượt, mốc khúc); vùng chưa kiểm của MỖI lượt = khúc hỏng trừ khúc chạy
  được của chính lượt đó. mkv/webm đọc thẻ `DURATION`; cắt khúc `-map 0:a:0`.
- G6/G8 — thiếu đuôi khi tải: dung sai cố định 5 s; chưa có bằng chứng thì tải lại MỘT lần để phân
  biệt tải đứt với âm thanh YouTube ngắn thật (cùng độ dài ±1 s → chấp nhận, ghi chú rõ).
- G8 — sổ kho hỏng không `.bak`: không tự dựng «Kho mặc định» khi còn `khos.json.hong.*`; Watch dừng.
  Watch kiểm file vân tay của kho chỉ định TRƯỚC `use_kho`. CLI báo bận bằng mã thoát 2.
- G10 — độ dài tham chiếu chỉ từ nguồn bên ngoài (danh sách kênh, lengthSeconds), không từ
  `duration_media`; nguồn ngắn thật được nhận sau hai lần tải cùng độ dài (dấu riêng). «Bổ sung» so
  với mốc BẮT ĐẦU build (`moc_build`), gỡ vân tay clip đã bị cách ly vào `_hong/`, giữ (cảnh báo)
  clip vắng không rõ lý do. Bản chép dở trong `_hong/` được gỡ; seed metadata không nhân đôi mã.
- Quy trình: mọi test giả của audfprint phải mô phỏng đúng mã vendored và có đối chứng audfprint
  THẬT; mỗi bản sửa vòng 2 được kiểm bằng phép thử đột biến (22/22 bị bắt).

### Bổ sung sau vòng phản biện 3 (kiểm lại các bản sửa vòng 2)

- G6 — **cao**: ncores > 1 làm dòng stdout của các worker audfprint xen nhau → bắt mọi lần "Error
  reading", neo vào cụm từ; lớp phòng thủ thứ hai theo nội dung (khúc 0 hash có tiếng rõ = chưa
  phân tích). Độ dài luồng tiếng chỉ khi file có đúng một luồng tiếng; tính `start_time`.
- G8 — sổ kho hỏng/mất-còn-`.bak` chặn MỌI quét và build (`SoKhoHong`), không chỉ Watch; CLI in cảnh
  báo khởi động; Watch bận thoát mã 2.
- G10 — lần tải lại kiểm chứng vào thư mục mới; đo luồng tiếng của nguồn video; gỡ clip đã cách ly
  chỉ khi bản thay thế cùng mã có vân tay, xét `_hong/` của mọi thư mục con; đối soát đếm đúng.
- Phép thử đột biến trên mã cuối: vòng 3 32/32, vòng 2 22/22 bị bắt. Hai reviewer chạy lại kịch bản
  tái hiện của mình: mọi phát hiện đã sửa; 4 điểm nhỏ mới (lệch DC, nhãn lý do, `.part` ở `lan2_*`,
  giữ bản sao `.bak`) đã sửa cùng vòng.

## 4. Thứ tự khoá (toàn dự án)

`tool.lock` (tác vụ nặng: build, Watch, sửa metadata, xoá kho) → khoá JSON của `khos.json` →
khoá JSON khác. Khoá JSON chỉ giữ trong thời gian đọc-sửa-ghi, không lồng hai file JSON khác nhau
ngoài thứ tự trên, không giữ khi gọi mạng.

## 5. Dữ liệu có thể bị ảnh hưởng khi triển khai và cách quay lui

| Dữ liệu | Thay đổi | Quay lui |
|---|---|---|
| `lichsu.db` | Thêm cột + `user_version` (không xoá, không sửa hàng cũ) | Bản cũ của app bỏ qua cột thừa; backup SQLite (API `backup`) trước migration; `lich_su.py --khoi-phuc` |
| `khos.json` | Kho mới có `id`/`revision`; kho cũ được thêm `id` (suy từ tên) + `revision` khi build lại; build thành công ghi `moc_build` | Bản cũ bỏ qua khoá lạ |
| `clips_meta.json` | Ghi theo giao dịch, chỉ gộp entry thay đổi; entry tải mới/đối soát có thêm `xac_nhan_tep` | Định dạng không đổi, khoá lạ bị bỏ qua; `.bak` giữ như cũ |
| Thư mục kho | `_tam/` (tạm từng lượt), `_hong/` (file nghi hỏng đã được thay) | Không xoá gì; `_hong/` do người dùng tự dọn sau khi đối chiếu |
| `.pklz` | Chỉ thay khi kho tạm qua kiểm tra | Kho cũ giữ nguyên khi từ chối |
| Báo cáo/Sheets | Thêm hậu tố phạm vi ở cột tên video khi quét chưa trọn | Không thêm cột |

Không bước nào ở trên được chạy trên dữ liệu thật trong vòng này; migration được thử trên bản sao.
