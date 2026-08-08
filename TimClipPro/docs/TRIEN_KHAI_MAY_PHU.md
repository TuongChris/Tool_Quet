# Triển khai TimClip Pro sang máy phụ

Mục tiêu: đem bản mới nhất sang các máy Windows đang nhàn rỗi để chúng tự quét theo
lịch, kết quả dồn về cùng một Google Sheet.

---

## 1. Điều quan trọng nhất: máy phụ KHÔNG cần clip gốc

Quét chỉ cần **kho vân tay** (`.pklz`) và **metadata** (`clips_meta.json`). File audio
gốc chỉ dùng lúc **tạo** vân tay (`build_database`), không dùng lúc quét — trong
`engine.py`, `kho_thu_muc` chỉ được đọc để lấy `clips_meta.json`, còn `liet_ke_media()`
duy nhất được gọi trong `build_database()`.

Đo trên kho hiện tại:

| | Dung lượng |
|---|---:|
| **Cần** — 3 kho vân tay | 343 MB |
| **Cần** — metadata + snapshot | 1,6 MB |
| **Cần** — `bin/` (ffmpeg + ffprobe) | 195 MB |
| **Cần** — mã nguồn | 1,5 MB |
| ~~Không cần~~ — clip gốc `.opus` | ~~23 GB~~ |
| ~~Không cần~~ — `data/downloads` | ~~173 GB~~ |

Gói khoảng **nửa GB** thay vì gần 200 GB.

---

## 2. Trên máy nguồn: tạo gói

```powershell
Set-Location "D:\Tool_Tim_Video_v2\TimClipPro"

# Xem trước sẽ đóng gói gì, không tạo file
& ".\.venv\Scripts\python.exe" dong_goi_may_chay.py --kho SML --kho Cory --liet-ke

# Tạo gói thật
& ".\.venv\Scripts\python.exe" dong_goi_may_chay.py --kho SML --kho Cory
```

Gói gồm mã nguồn, kho vân tay đã chọn, `clips_meta.json` của từng kho, snapshot
metadata, cấu hình quét và `bin/`. Thêm `--khong-kem-ffmpeg` nếu máy phụ đã có ffmpeg
(gói nhẹ đi ~195 MB, `cai_dat.bat` sẽ tự tải khi cài).

### Khoá Google KHÔNG nằm trong gói

`dong_goi_may_chay.py` từ chối đóng gói `google_key.json` và mọi file có từ khoá bí
mật, kể cả khi được yêu cầu. Muốn máy phụ đẩy Sheets thì **tự chép khoá sang bằng kênh
riêng** (USB, trình quản lý mật khẩu…), đừng gửi kèm zip qua chat/email.

---

## 3. Trên máy phụ: cài đặt

1. Cài **Python 3.12 64-bit** từ python.org, nhớ tick *Add python.exe to PATH*.
2. Giải nén gói vào một thư mục cố định, ví dụ `C:\TimClipPro`.
3. Chạy `cai_dat.bat` — tự tạo `.venv`, cài thư viện, kiểm tra audfprint và ffmpeg.
4. Chạy thiết lập:

```powershell
Set-Location "C:\TimClipPro"
& ".\.venv\Scripts\python.exe" thiet_lap_may_phu.py
```

Bước 4 trỏ lại đường dẫn kho: máy nguồn ghi `D:\ClipGocSML`, còn máy phụ dùng
`C:\TimClipPro\kho_meta\SML`. Nó cũng in bảng kiểm tra còn thiếu gì.

5. Nếu muốn đẩy Sheets: chép `google_key.json` vào `C:\TimClipPro\`, rồi chia sẻ
   Google Sheet cho địa chỉ `client_email` trong khoá đó (quyền Editor).

---

## 4. Chia việc để các máy không quét trùng

`watch` lọc video đã quét bằng `Engine.ids_da_quet()`, mà hàm này đọc `lichsu.db`
**cục bộ của từng máy**. Chép nguyên một watchlist sang N máy thì cả N máy cùng tải và
quét đúng những video giống nhau.

Cách rẻ nhất là chia danh sách trước, trên **máy nguồn**:

```powershell
& ".\.venv\Scripts\python.exe" chia_watchlist.py --so-may 3            # xem trước
& ".\.venv\Scripts\python.exe" chia_watchlist.py --so-may 3 --that-su  # ghi file
```

Sinh ra `watchlist.may1.json`, `watchlist.may2.json`, `watchlist.may3.json` — chia
luân phiên nên mục nặng/nhẹ rải đều. Chép mỗi file sang đúng một máy.

Trên máy phụ, đổi tên thành `watchlist.json`, hoặc trỏ thẳng:

```powershell
.\ChayMayPhu.bat watchlist.may2.json
```

**Không** trỏ `lichsu.db` vào ổ mạng dùng chung: SQLite qua SMB hay lỗi khoá file và
dễ hỏng dữ liệu.

---

## 5. Chạy tự động bằng Task Scheduler

Chạy thử tay trước, chắc chắn ra kết quả rồi mới đặt lịch:

```powershell
Set-Location "C:\TimClipPro"
.\ChayMayPhu.bat watchlist.may2.json
```

Đặt lịch (chạy PowerShell với quyền Administrator):

```powershell
$act = New-ScheduledTaskAction -Execute "C:\TimClipPro\ChayMayPhu.bat" `
    -Argument "watchlist.may2.json" -WorkingDirectory "C:\TimClipPro"
$trg = New-ScheduledTaskTrigger -Daily -At 1:00AM
$set = New-ScheduledTaskSettingsSet -StartWhenAvailable `
    -DontStopOnIdleEnd -ExecutionTimeLimit (New-TimeSpan -Hours 12)
Register-ScheduledTask -TaskName "TimClipPro giam sat" -Action $act `
    -Trigger $trg -Settings $set -RunLevel Highest -User "$env:USERNAME"
```

Ghi chú:

* `-StartWhenAvailable` để máy tắt lúc tới giờ thì chạy bù khi bật lại.
* `-ExecutionTimeLimit 12h` tránh job treo chiếm máy vô hạn; chỉnh theo khối lượng.
* Muốn chỉ chạy khi máy rảnh thì thêm `-RunOnlyIfIdle` vào `New-ScheduledTaskSettingsSet`
  — nhưng Windows sẽ **dừng** job khi anh động vào máy, nên chỉ hợp với máy không ai dùng.
* Task chạy dưới tài khoản người dùng để đọc được thư mục cài; không cần SYSTEM.

Theo dõi:

```powershell
Get-ScheduledTaskInfo -TaskName "TimClipPro giam sat"
Get-Content "C:\TimClipPro\ketqua\*.log" -Tail 50
```

---

## 6. Cập nhật máy phụ khi máy nguồn có bản mới

Tạo gói mới rồi giải nén đè lên thư mục cài. Những thứ **không** bị đè vì không nằm
trong gói: `.venv`, `google_key.json`, `watchlist.json`, `data\lichsu.db`, `ketqua\`.

Sau khi đè, chạy lại:

```powershell
& ".\.venv\Scripts\python.exe" thiet_lap_may_phu.py
& ".\.venv\Scripts\python.exe" -m pip install -r requirements.txt
```

Nếu kho vân tay ở máy nguồn được **nạp lại** (không chỉ thêm clip), nhớ đóng gói lại
kho đó và chạy `kiem_thoi_luong.py --ghi-de --sua --that-su` ở máy nguồn trước.

---

## 7. Giới hạn đã biết

* **Mỗi máy có lịch sử riêng.** Chia watchlist là cách tránh trùng; không có cơ chế
  điều phối tự động giữa các máy.
* **Kho vân tay là ảnh chụp tại thời điểm đóng gói.** Thêm clip gốc mới ở máy nguồn thì
  máy phụ không tự biết — phải đóng gói và chép lại kho đó.
* **Máy phụ không tạo được vân tay mới** vì không có clip gốc. Đó là chủ ý: việc tạo kho
  vẫn tập trung ở máy nguồn.
* Nhiều máy cùng ghi một Google Sheet có thể chạm giới hạn API của Google nếu chạy dày;
  giãn giờ chạy giữa các máy nếu gặp lỗi quota.
