# Dữ liệu, migration và phục hồi — vòng hardening sau audit 4b7e5bd

Đi kèm `HARDENING_PLAN.md` (quyết định), `HARDENING_FIX_MATRIX.md` (từng mục) và
`HARDENING_VALIDATION_REPORT.md` (bằng chứng). Tài liệu này dành cho người **vận hành**: bản mới
đổi gì trên dữ liệu, chạy lần đầu ra sao, quay lui thế nào.

## 1. Trạng thái: CHƯA chạm dữ liệu thật

Trong vòng này **không có lệnh nào đọc hay ghi** `Tool_Quet\TimClipPro\data`, thư mục kho clip
gốc, cookie hay khoá Google. Chỉ dùng `.venv` (làm interpreter, không cài thêm gì) và `bin\`
(FFmpeg/FFprobe) của máy chạy thật. Mọi migration/recovery dưới đây được thử trên **bản sao và dữ
liệu tổng hợp** trong thư mục tạm.

Các bước ghi dữ liệu thật (mục 8) cần người dùng phê duyệt và tự bấm.

## 2. Bản mới đổi gì trên đĩa

| Dữ liệu | Thay đổi | Khi nào | Bản cũ (4b7e5bd) đọc được không |
|---|---|---|---|
| `data\lichsu.db` | Lược đồ v0 → v1: CHỈ THÊM 7 cột + 1 chỉ mục + `PRAGMA user_version = 1`; sao lưu trước khi thêm | Lần ĐẦU tiên Engine khởi động (app, CLI, Watch) | **Được** — đã thử: bản cũ đọc/ghi/xoá job bình thường trên DB v1 |
| `data\khos.json` | Kho mới (kể cả "Kho mặc định" tự tạo) có `id` (bền) và `revision`; kho cũ được thêm `id` (suy từ tên) + `revision` khi build lại thành công; build thành công ghi thêm `moc_build` (giây epoch lúc BẮT ĐẦU đọc file). Sổ hỏng mà không có `.bak` (bản hỏng giữ ở `khos.json.hong.<thời điểm>`), hoặc sổ bị MẤT mà còn `khos.json.bak`: tool KHÔNG tự dựng lại «Kho mặc định» từ `db.pklz`, không ghi đè `.bak`, và chặn quét/tạo kho cho tới khi khôi phục (mục 4.9) | Khi thêm kho / build xong | Được — khoá lạ bị bỏ qua |
| `data\*.pklz` | Chỉ được thay khi kho tạm đọc được và qua kiểm tra (không mất clip tốt, có clip hữu ích). «Bổ sung» làm mới vân tay của clip có file bị thay SAU khi lần build trước BẮT ĐẦU (`audfprint remove` trên kho tạm rồi tạo lại), và GỠ vân tay của clip đã bị đồng bộ kênh cách ly vào `_hong\` (mục 5) | Khi build | Không đổi định dạng |
| `data\metadata\kho_*.json` | Lần làm mới snapshot nay lấy giá trị của `clips_meta.json` (nguồn chuẩn) | Khi build xong / bấm khôi phục metadata offline | Không đổi định dạng |
| `clips_meta.json` (thư mục kho) | Thêm `xac_nhan_tep` `{kich_thuoc, do_dai}`: entry tải mới, và — ở **lượt đồng bộ đầu tiên** sau cập nhật — mọi file cũ kiểm đạt có độ dài tham chiếu. Video mà âm thanh YouTube thật sự ngắn hơn lengthSeconds (đã tải lại hai lần cùng độ dài) có thêm `am_thanh_ngan_hon_youtube: true`. Đối soát tại chỗ KHÔNG còn ghi `duration_media` cho file chưa có độ dài tham chiếu | Khi đồng bộ kênh | Được — khoá lạ bị bỏ qua |
| `data\downloads\` (đệm tải) | Không đổi định dạng. File tải về thiếu đuôi > 5 s mà chưa có bằng chứng thì bản đệm bị bỏ và tải lại MỘT lần trong cùng lượt quét (mục 4.8) | Khi quét YouTube | Không liên quan |
| Thư mục kho | `_tam\<pid>_<mã>` (tạm từng lượt, tự xoá), `_hong\` (file nghi hỏng đã được thay, tên `<yymmdd-HHMMSS>_<tên gốc>`), `.dong_bo_kenh.lock` (khoá: mỗi kho một lượt đồng bộ) | Khi đồng bộ kênh | Bản cũ: `liet_ke_media` của nó **sẽ** đi vào `_hong\` (xem mục 7) |
| `.timclip.lock` | File khoá liên tiến trình ở mỗi thư mục có JSON được ghi | Khi ghi JSON | Vô hại; đã thêm vào `.gitignore` |

## 3. `lichsu.db` — lược đồ v1

| Cột | Ý nghĩa | Dòng cũ |
|---|---|---|
| `kho_id` | Định danh bền của kho (`id` trong `khos.json`; kho cũ chưa có `id`: `ten:<slug>`) | `''` = chưa rõ kho |
| `kho_ten` | Tên kho lúc quét (hiển thị) | `''` |
| `kho_phien_ban` | `revision` của kho + `:` + kích thước file `.pklz` lúc quét | `''` |
| `chinh_sach` | Chữ ký tham số nhận diện (`engine.TRUONG_CHINH_SACH`) | `''` |
| `day_du` | 1 = đã so khớp trọn video, 0 = một phần | `NULL` = không biết |
| `dat_muc_tieu` | Đủ Top-N trong phần đã quét | `NULL` |
| `pham_vi` | JSON: vùng đã khớp, vùng lỗi, lý do (`dung_som`, `gioi_han_tai`, `loi_khuc`, `huy`) | `''` |

**Quy tắc Watch bỏ qua video** (`Engine.ids_da_quet`): cùng `kho_id` với kho đang dùng, `status =
ok`, và (có kết quả) **hoặc** (không kết quả + quét trọn + cùng `kho_phien_ban` + cùng
`chinh_sach`). Lỗi, huỷ, quét dở và **mọi dòng cũ** không chặn quét lại.

**Nâng cấp an toàn thế nào** (`lich_su.dam_bao_luoc_do`):
- Đường nhanh chỉ ĐỌC `user_version` + danh sách cột: mọi lần mở app sau khi đã nâng cấp không ghi gì.
- Cần nâng cấp: `BEGIN IMMEDIATE` (chặn writer khác) → kiểm lại → sao lưu bằng SQLite backup API
  qua một kết nối đọc riêng (bản sao nhất quán) → `ALTER TABLE … ADD COLUMN` → `user_version = 1` →
  `COMMIT`. Lỗi giữa chừng thì `ROLLBACK`, DB giữ nguyên v0 (bản sao lưu vẫn còn).
- Hai tiến trình mở cùng lúc: một bên nâng cấp, bên kia thấy đã xong (đã thử bằng 2 process thật).
- Bản sao lưu: `data\lichsu.db.v0_<YYYYmmdd_HHMMSS>.bak` (chỉ tạo khi DB đã có dữ liệu).
- Đo trên DB tổng hợp 50.000 job + 50.000 match (15,3 MB): nâng cấp kể cả sao lưu **0,09 s**.

**Công cụ tay** (mặc định chỉ thống kê, không ghi):

```powershell
& ".\.venv\Scripts\python.exe" lich_su.py --kiem .\data\lichsu.db
& ".\.venv\Scripts\python.exe" lich_su.py --nang-cap .\data\lichsu.db
& ".\.venv\Scripts\python.exe" lich_su.py --khoi-phuc .\data\lichsu.db.v0_20261002_090000.bak .\data\lichsu_khoi_phuc.db
```

`--khoi-phuc` không ghi đè file đang có: khôi phục ra file MỚI, kiểm (`--kiem`), rồi khi app đã
dừng mới đổi tên thay `lichsu.db`.

## 4. Hệ quả vận hành sau khi cập nhật

1. **Watch quét lại các video đã quét bằng bản cũ** (vì lịch sử cũ là "chưa rõ kho"), mỗi lượt
   tối đa `gioi_han_moi_lan` video. Đây là chủ đích: lịch sử cũ không chứng minh được video đã
   được đối chiếu với kho nào, quét trọn hay không, và có thể mang lỗi TCP-04/05/06.
2. Video cũ ĐÃ có vi phạm, khi quét lại, sẽ tạo **dòng mới trên Google Sheet** (bản cũ không ghi
   danh tính kho nên không đối soát được). Nên giữ `gioi_han_moi_lan` nhỏ trong vài lượt đầu và
   lọc trùng trên Sheet theo "Link video vi phạm" nếu cần.
3. Muốn chủ động quét lại một kho mà không xoá lịch sử: chạy tay
   `cli.py watch --log --sheet "<link Sheet>" --quet-lai` (`GiamSat.bat` không chuyển tiếp tham số
   thêm, và đã cố ý không sửa file đó vì Task Scheduler đang dùng). Lịch sử chỉ được thêm dòng.
4. Máy phụ: lịch sử là CỤC BỘ từng máy (như trước). Gói máy phụ tạo bằng bản mới mang `id` và
   `revision` của kho; gói tạo bằng bản cũ thì danh tính ở máy phụ suy từ tên kho.
5. Watch không chỉ định kho mà kho đang chọn hỏng (sổ đăng ký trỏ sai file vân tay) hoặc chưa có vân
   tay: lượt dừng ngay với lý do cụ thể, thay vì lặng lẽ quét bằng `data\db.pklz`.
6. **Lượt đồng bộ kênh đầu tiên sau cập nhật chạy lâu hơn một lần:** mọi file `.opus` cũ chưa có dấu
   xác nhận được ffprobe một lần (đo: ~17 ms mỗi file opus 10 phút trên ổ cục bộ → kho 756 clip
   ~13 s, 1.717 clip ~30 s; ổ mạng/USB chậm hơn; có tiến độ "Kiểm file trên đĩa i/n" và bấm Dừng
   được). File đạt được đóng dấu
   `xac_nhan_tep` (một giao dịch ghi `clips_meta.json`) nên các lượt sau không kiểm lại. Mỗi kho chỉ
   chạy được MỘT lượt đồng bộ tại một thời điểm.
7. **CLI báo bận bằng mã thoát 2.** Khi kho/lịch sử đang bị lượt khác giữ khoá, mọi lệnh
   `cli.py` — kể cả `watch` (đường `GiamSat.bat`/`ChayMayPhu.bat`) — in «ĐANG BẬN …» ra stderr và
   thoát mã **2** (lỗi thật vẫn là 1) thay vì traceback. Script lịch nào đang coi mọi mã ≠ 0 là lỗi
   vẫn đúng; muốn phân biệt "bận" thì đọc mã 2. CLI nay cũng in cảnh báo lúc khởi động (sổ kho
   hỏng…) ra stderr và in cảnh báo của `taodb`/`themclip`.
8. **Quét YouTube có thể tải hai lần một video.** File tải về ngắn hơn lengthSeconds quá 5 s (dung sai
   cũ `max(5 s; 0,2%)` cho video 10 giờ là 72 s) mà lượt quét không có bằng chứng nào: bỏ bản đệm và
   tải lại MỘT lần ngay. Bản mới đủ → quét lại bằng bản mới. Ngắn đúng như lần trước (±1 s) → âm
   thanh YouTube thật sự ngắn hơn: phần sau được ghi "không có tiếng", ghi chú nêu rõ, lịch sử ghi lý
   do `am_thanh_ngan_hon` ("Trọn video (âm thanh YouTube ngắn hơn …)") để rà lại được, video không
   còn bị quét/tải lại ở mọi lượt Watch. Độ dài khác → vùng lỗi như trước. Đồng bộ kênh làm tương tự
   (chỉ khi bản nén trượt kiểm và chính nguồn — đo theo LUỒNG TIẾNG — đã ngắn); lần tải lại kiểm
   chứng luôn vào một thư mục tạm MỚI nên không bao giờ "kiểm" lại chính file cũ.
9. **Sổ đăng ký kho hỏng không có `.bak`, hoặc bị MẤT mà còn `.bak`:** lần mở đầu giữ bản hỏng ở
   `data\khos.json.hong.*` và báo lỗi; mọi lần mở KHÔNG tự dựng «Kho mặc định» từ `data\db.pklz`
   (trước đây làm vậy, nên Watch lặng lẽ quét bằng kho mặc định — và lần ghi sổ kế tiếp đè mất
   `khos.json.bak`, bản sao cuối cùng). Quét, tạo/bổ sung kho (giao diện, CLI) và Watch đều bị chặn
   với lý do cụ thể (`SoKhoHong`); dữ liệu không bị ghi. Ca sổ mất-còn-`.bak`: tool chép ngay
   `khos.json.bak` ra `data\khos.json.bak.giu_<thời điểm>` — bản này KHÔNG bao giờ bị ghi đè, kể cả
   khi người dùng tạo kho mới trong lúc đó. Khôi phục khi app đã dừng: sửa bản hỏng hoặc chép
   `khos.json.bak` (hoặc bản `.giu_*`) thành `data\khos.json`; nếu chắc chắn muốn dùng `db.pklz` làm
   «Kho mặc định» thì chuyển các file `khos.json.hong.*` / `khos.json.bak` ra chỗ khác rồi mở lại.
10. **Video tắt tiếng / đuôi im lặng là âm tính trọn.** Bản sửa vòng 1 từng coi khúc im lặng là lỗi
    đọc (hồi quy, đã sửa ở vòng 2) — chỉ ảnh hưởng nếu bản giữa hai vòng từng được chạy thật; lịch sử
    của nó (nếu có) là các dòng `error` nên tự được quét lại.

## 5. Kho vân tay

- Build không còn thay kho đang dùng bằng kho tạm hỏng/0 hash/làm mất clip đã có; khi từ chối,
  kho cũ giữ nguyên byte và giao diện báo lý do.
- Mỗi lần công bố thành công đổi `revision` → âm tính cũ của kho đó hết hiệu lực (đúng ý: kho mới
  có clip mới thì phải quét lại).
- Chi phí: build đọc thêm danh sách clip của kho tạm (và kho cũ khi `add`). Đo trên kho tổng hợp
  cỡ thật (bảng 2^20 × 100, ~35% đầy, 187 MB nén, 800 clip): **1,6 s**, đỉnh RAM **~0,9 GB** trong
  lúc đọc (bằng chi phí `db_clips()` vốn có). Máy ít RAM nên đóng bớt ứng dụng khi build kho lớn.
- «Bổ sung clip mới vào kho» làm mới vân tay của clip có file bị THAY sau khi lần build trước BẮT
  ĐẦU (so mtime file clip với `min(moc_build, mtime file kho)`, dung sai 2 s — kho cũ chưa có
  `moc_build` thì so với mtime file kho như trước): gỡ vân tay cũ khỏi kho tạm bằng `audfprint
  remove` rồi tạo lại. Nếu file mới không tạo được vân tay thì từ chối ghi — kho dùng tiếp vân tay cũ
  và giao diện nêu tên clip. Đã thử với audfprint thật (clip cụt 10 s được thay bằng bản 30 s).
- Clip có vân tay mà file đã VẮNG khỏi thư mục kho:
  - có bản trong `_hong\` của đúng thư mục chứa nó (kể cả thư mục con) VÀ một clip khác cùng mã
    video đã có vân tay (bản thay thế, ví dụ tên mới khi tiêu đề đổi) → «Bổ sung» GỠ vân tay bản cũ
    SAU khi thêm bản thay thế, kiểm đã thật sự ra khỏi kho rồi mới công bố; giao diện/CLI nêu tên.
    Đã thử với audfprint thật;
  - có bản cách ly nhưng bản thay thế chưa có vân tay (tạo lỗi, chưa tải) → GIỮ vân tay cũ, cảnh
    báo; chạy lại «Bổ sung» sau khi bản thay thế tạo được vân tay;
  - KHÔNG có bản cách ly (ổ chưa gắn, OneDrive chưa tải về, người dùng chuyển đi…) → GIỮ vân tay,
    chỉ cảnh báo kèm tên: gỡ nhầm là mất hàng giờ tạo lại. Muốn gỡ hẳn thì «Tạo mới» kho.

## 6. Metadata báo cáo

- Nguồn chuẩn là `clips_meta.json` của thư mục kho; snapshot chỉ bù trường thiếu và dùng khi thư mục
  kho offline. Sau khi cập nhật, nếu snapshot đang khác `clips_meta.json`, giao diện cảnh báo
  "Snapshot metadata lệch với clips_meta.json ở N clip". Bấm **Khôi phục metadata offline** (chạy
  thử trước) để làm mới snapshot — không có gì được tự sửa hàng loạt.
- Báo cáo CSV/Sheet ĐÃ xuất trước đây bằng snapshot cũ không được viết lại. Cần số liệu đúng cho
  hồ sơ thì xuất lại từ lần quét mới.

## 7. Thư mục kho: `_tam`, `_hong`, dấu xác nhận

- Lượt đồng bộ đầu tiên sau cập nhật: mọi file `.opus` CHƯA có dấu `xac_nhan_tep` được kiểm bằng
  ffprobe (không tin "có trong archive + metadata": hai nút bảo trì tạo được hai sổ đó cho cả file
  hỏng). Độ dài tham chiếu lấy từ danh sách kênh, rồi `duration` (lengthSeconds) trong metadata —
  KHÔNG bao giờ từ `duration_media` (số đo của chính file, do đối soát hay «kiem_thoi_luong --sua»
  ghi ra: file cụt so với chính nó thì luôn đạt); không có tham chiếu thì file được giữ nhưng KHÔNG
  đóng dấu. File hỏng/nén dở/ngắn bất thường được
  báo và tải lại; bản cũ chỉ được giữ trong `_hong\` (hard link hoặc bản chép) ngay trước khi thay,
  tên `<yymmdd-HHMMSS>_<tên gốc>` — đường dẫn quá 240 ký tự thì `<yymmdd-HHMMSS>_<mã video>.opus`.
  Thay thất bại (file bị chương trình khác giữ) thì bản trong `_hong\` bị gỡ, bản gốc nằm nguyên
  tại chỗ. Không file nào bị xoá.
- Muốn trả một file từ `_hong\` về kho: đổi tên bỏ tiền tố thời điểm rồi chép lại vào thư mục kho
  (trước đó xoá/chuyển bản mới nếu trùng tên).
- **Lưu ý khi quay lui code:** `liet_ke_media` của bản cũ duyệt cả thư mục con nên sẽ lấy file
  trong `_hong\` khi tạo vân tay. Trước khi chạy build bằng bản cũ, chuyển `_hong\` ra ngoài thư
  mục kho.
- File tốt nhưng thiếu metadata/archive (ví dụ ghi metadata lỗi ngay sau khi đặt file) được
  đối soát tại chỗ từ tên file + ffprobe, không gọi YouTube; tiêu đề lấy từ tên file đã làm sạch,
  có thể vá lại bằng "Vá metadata".

## 8. Bước cần phê duyệt trên máy thật (theo thứ tự)

1. Dừng app/Watch; sao lưu `data\` và các thư mục kho (lệnh trong `RUNBOOK.md` mục *Backup*).
2. (Tuỳ chọn) chép `data\lichsu.db` ra chỗ khác và chạy `lich_su.py --kiem` trên BẢN CHÉP để xem
   số dòng sẽ thành "chưa rõ kho".
3. Đưa code mới vào thư mục chạy thật (merge/tag theo quy trình `cap_nhat.py`). Lần mở đầu tiên
   tự nâng cấp `lichsu.db` và để lại `lichsu.db.v0_*.bak`.
4. Mở tab **Lịch sử**: cột Kho/Phạm vi; dòng cũ hiện "Chưa rõ (lịch sử cũ — cần rà soát)".
5. Chạy Watch với `gioi_han_moi_lan` nhỏ, xem số "Quét mới" và Sheet.
6. Bấm **Khôi phục metadata offline** (chạy thử rồi mới ghi) nếu có cảnh báo snapshot lệch.
7. Đồng bộ kênh một lần (lượt đầu kiểm mọi file cũ, xem mục 4.6), đọc mục "file nghi hỏng" nếu
   có; quyết định xoá `_hong\` sau khi đối chiếu.
8. Nếu đồng bộ đã thay file nghi hỏng: chạy «Bổ sung clip mới vào kho» để làm mới vân tay của đúng
   các clip đó (mục 5).

## 9. Quay lui

- **Code:** chuyển về `4b7e5bd` không cần đụng dữ liệu — đã thử bản cũ chạy trên `lichsu.db` v1;
  `khos.json`/`clips_meta.json` chỉ có khoá thêm. Dòng lịch sử do bản cũ ghi trong lúc quay lui sẽ
  là "chưa rõ kho" khi lên lại bản mới. Nhớ lưu ý `_hong\` ở mục 7.
- **`lichsu.db`:** khôi phục từ `lichsu.db.v0_*.bak` bằng `lich_su.py --khoi-phuc` ra file mới,
  kiểm, rồi thay khi app dừng. Không xoá DB hiện tại trước khi bản khôi phục đã được kiểm.
- **Kho vân tay:** kho bị từ chối thì vốn không bị thay; muốn bỏ một kho vừa công bố thì dùng bản
  sao lưu `data\` ở bước 1.

## 10. Đã thử trên bản sao

| Thử | Kết quả |
|---|---|
| Nâng cấp DB cũ có dữ liệu: cột, `user_version`, số dòng, bản sao lưu `integrity_check = ok` | đạt (`test_lich_su_theo_kho.py`) |
| Chạy lại nâng cấp: không ghi byte nào, không tạo sao lưu thứ hai | đạt |
| Chạy thử (`thong_ke`): hash file không đổi, không tạo file | đạt |
| Khôi phục ra file mới, không ghi đè file đang có | đạt |
| Hai tiến trình nâng cấp cùng lúc | đạt — một `True`, một `False`, cột không nhân đôi |
| Bản cũ `4b7e5bd` dùng DB v1 rồi bản mới đọc lại | đạt (`scratchpad/kiem_quay_lui_lichsu.py`) |
| CLI `lich_su.py --kiem/--nang-cap/--khoi-phuc` qua tiến trình thật | đạt (nghiệm thu tích hợp) |
| 50.000 job + 50.000 match | nâng cấp 0,09 s; truy vấn lọc theo kho 15 ms (cũ: 25 ms) |
| `khos.json` hỏng không `.bak` + `db.pklz` có sẵn: lần mở 1 và lần mở 2 | không tự dựng «Kho mặc định», Watch dừng; cài mới chưa từng có sổ vẫn tự nâng cấp như cũ (`test_phan_bien_vong_hai.py`) |
| `khos.json` hỏng hoặc mất-còn-`.bak`: quét, «Bổ sung», Watch | đều bị chặn (`SoKhoHong`), `db.pklz` không đổi byte, `.bak` giữ nguyên (`test_phan_bien_vong_ba.py`) |
| «Bổ sung» khi bản cũ đã vào `_hong\` và bản thay thế cùng mã đã có vân tay (audfprint thật) | kho còn a + bản thay thế, số hash giữ nguyên, bản cũ đã gỡ |
| «Bổ sung» khi bản thay thế không tạo được vân tay / chưa có | kho giữ nguyên byte (vân tay cũ còn), cảnh báo nêu tên |
| «Bổ sung» khi một clip vắng không rõ lý do | kho giữ nguyên byte, cảnh báo nêu tên |
