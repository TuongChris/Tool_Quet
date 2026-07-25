# TimClip Pro — Hệ thống tìm video gốc trong video dài

Chạy **100% trên máy bạn**. Giao diện hiển thị bằng trình duyệt tại `http://localhost:8501`,
nhưng không có dữ liệu nào rời khỏi máy (trừ lúc tải YouTube). Rút mạng vẫn quét được
các file có sẵn — giống hệt cách VS Code hay Zalo PC hoạt động.

---

## 1. Kiến trúc

```
        ┌─────────────┐   ┌──────────┐   ┌───────────────┐
        │  app.py     │   │  cli.py  │   │ (sau này: API │
        │ Streamlit UI│   │dòng lệnh │   │  hay desktop) │
        └──────┬──────┘   └────┬─────┘   └───────┬───────┘
               └───────────────┼─────────────────┘
                               ▼
                        ┌─────────────┐
                        │  engine.py  │  ← TOÀN BỘ phần lõi
                        └──────┬──────┘
        ┌───────────┬──────────┼──────────┬─────────────┐
        ▼           ▼          ▼          ▼             ▼
     yt-dlp     FFmpeg     audfprint   SQLite       pandas
   (tải audio) (cắt khúc) (vân tay)  (lịch sử)   (báo cáo)
```

**Nguyên tắc vàng:** `engine.py` không biết ai đang gọi nó. Đổi giao diện lúc nào cũng được
mà không phải sửa lõi. Đây là điểm khác biệt giữa "một cái script" và "một hệ thống".

Luồng xử lý một lần quét:

```
Link YouTube ──► yt-dlp tải RIÊNG audio (nhẹ hơn video ~20 lần)
                            │
File có sẵn ────────────────┤
                            ▼
        FFmpeg cắt thành khúc 1 giờ, gối nhau 10 phút
                            ▼
        audfprint so khớp vân tay với kho clip gốc
                            ▼
        Gộp trùng ► Lọc ngưỡng ► SQLite ► Bảng + CSV
```

## 2. Yêu cầu

| Thứ | Ghi chú |
|---|---|
| Windows 10/11 64-bit | Có sẵn `curl`, `tar` |
| Python 3.10 – 3.13 | python.org — **NHỚ TICK "Add python.exe to PATH"** |
| Ổ trống | Audio 30 tiếng ≈ 1–2 GB |

Đã kiểm thử: Python 3.12, numpy 2.4, Streamlit 1.60, yt-dlp 2026.07, FFmpeg 6.x.

## 3. Cài đặt (một lần)

1. Cài Python từ https://www.python.org/downloads/ — **tick "Add python.exe to PATH"**.
2. Giải nén `TimClipPro.zip` vào thư mục cố định, ví dụ `D:\TimClipPro\`
   (tránh đường dẫn có dấu tiếng Việt và tránh OneDrive).
3. Double-click **`cai_dat.bat`** → tự cài thư viện, tự tải audfprint + FFmpeg.
4. Cuối màn hình hiện đủ 3 dòng `[OK]` là xong.

> Nếu bạn đã cài Video Duplicate Finder trước đó: copy sẵn `ffmpeg.exe` và `ffprobe.exe`
> từ thư mục VDF vào `TimClipPro\bin\` để khỏi tải lại 100 MB.

## 4. Chạy

Double-click **`ChayTool.bat`** → trình duyệt tự mở. Cửa sổ đen phải để nguyên
(đó là server); đóng nó là tắt tool.

## 5. Sử dụng — 4 tab

### 🎬 Tab «Kho clip gốc» — làm một lần

Dán đường dẫn thư mục chứa hàng trăm video gốc (copy từ thanh địa chỉ File Explorer),
bấm **Tạo lại kho từ đầu**. Hệ thống đọc thẳng phần tiếng từ file `.mp4` — **không cần
tách audio trước**. Có clip mới thì dùng **Bổ sung clip mới vào kho** (nhanh hơn nhiều).

Tốc độ thực đo: ~40× thời gian thực mỗi nhân CPU → 300 clip × 7 phút ≈ **50–60 phút**
(tăng «Số nhân CPU» trong thanh bên để nhanh hơn).

### ▶️ Tab «Quét YouTube»

Dán mỗi dòng một link → **Bắt đầu quét**. Hệ thống chỉ tải audio, có thanh tiến độ
theo MB. Đứt mạng cứ chạy lại — yt-dlp tải tiếp từ chỗ dừng, file tải xong sẽ bỏ qua.

### 📁 Tab «Quét file trong máy»

Nhập đường dẫn **file** hoặc **cả thư mục** (quét hàng loạt). Cố tình không dùng nút
upload để bạn khỏi phải copy file hàng chục GB.

### 📜 Tab «Lịch sử»

Mọi lần quét đều lưu trong SQLite (`data\lichsu.db`), xem lại và tải CSV bất cứ lúc nào.

## 6. Đọc kết quả

| Cột | Ý nghĩa |
|---|---|
| Xuất hiện từ / Đến | Khoảng thời gian **trong video dài** |
| Khớp từ giây thứ (của clip) | ≈0 = dùng từ đầu clip; 120 = đã cắt bỏ 2 phút đầu |
| Số hash khớp | Bằng chứng khớp, càng cao càng chắc |
| Đánh giá | ≥100: Rất chắc chắn · ≥40: Chắc chắn · dưới: Nên kiểm tra lại |

Khoảng "từ → đến" thường ngắn hơn clip thật vài giây — bình thường, do audfprint cắt bỏ
~5% rìa hai đầu khi ước lượng vùng khớp.

## 7. Tinh chỉnh (thanh bên → ⚙️ Tham số)

| Tham số | Mặc định | Khi nào sửa |
|---|---|---|
| Độ dài mỗi khúc | 3600s | Máy yếu RAM → 1800 |
| Khúc gối nhau | 600s | **Phải > clip gốc dài nhất** |
| Số hash tối thiểu | 15 | Báo nhầm → tăng 30–40; bỏ sót → giảm 8–10 |
| Số nhân CPU | 1 | Máy nhiều nhân → 4 |

## 8. Bản dòng lệnh (chạy tự động theo lịch)

Dùng chung engine, không cần mở trình duyệt:

```bat
python cli.py taodb   "D:\ClipGoc"
python cli.py youtube --file links.txt
python cli.py file    "D:\VideoDai"
```

Ghép với Task Scheduler của Windows để chạy lúc 2h sáng.

## 9. Docker (tùy chọn — chưa cần lúc này)

Chỉ nên dùng khi muốn đem sang máy khác/NAS mà không phải cài lại gì:

```bash
docker compose up -d      # mở http://localhost:8501
```

Nhớ sửa 2 dòng `volumes` trong `docker-compose.yml` cho đúng ổ đĩa của bạn, và khi
nhập đường dẫn trong giao diện thì dùng đường dẫn **bên trong container** (`/clips`,
`/videodai`) chứ không phải `D:\...`.

## 10. Lỗi thường gặp

| Triệu chứng | Xử lý |
|---|---|
| `'python' is not recognized` | Cài lại Python, tick "Add to PATH", mở cmd mới |
| Trình duyệt không tự mở | Tự vào `http://localhost:8501` |
| Cổng 8501 bị chiếm | Sửa `--server.port=8502` trong `ChayTool.bat` |
| yt-dlp lỗi 403 / tải hỏng | `pip install -U yt-dlp` (YouTube đổi cơ chế thường xuyên) |
| Video giới hạn tuổi | Trong `engine.py`, hàm `download_audio`, thêm vào `opts`: `"cookiesfrombrowser": ("chrome",)` |
| Quét ra 0 kết quả dù chắc chắn có | ① Video dài còn tiếng gốc không? ② Giảm «Số hash tối thiểu» ③ Kiểm tra kho đã đủ clip |
| Báo nhầm | Tăng «Số hash tối thiểu» lên 30–40 |

## 11. Giới hạn cần biết

Hệ thống dựa trên **âm thanh**. Nếu video dài đã bị **thay/đè toàn bộ tiếng**
(lồng tiếng lại, nhạc nền to, mute) thì không tìm được — khi đó dùng chế độ AI visual
của Video Duplicate Finder, hoặc mở rộng hệ thống này bằng nhánh so khớp hình ảnh
(pHash + OpenCV, nâng cao hơn là VCSL/TransVCL).

Việc tải nội dung từ YouTube bằng công cụ bên thứ ba có thể không phù hợp Điều khoản
dịch vụ của YouTube — bạn tự cân nhắc phạm vi sử dụng. audfprint theo giấy phép MIT.

## 12. Cấu trúc thư mục

```
TimClipPro\
├── ChayTool.bat        ← double-click để chạy
├── cai_dat.bat         ← chạy 1 lần đầu tiên
├── engine.py           ← LÕI (mọi xử lý nằm đây)
├── app.py              ← giao diện web local
├── cli.py              ← giao diện dòng lệnh
├── requirements.txt
├── Dockerfile / docker-compose.yml   ← tùy chọn, dùng sau
├── HUONG_DAN.md
├── audfprint-master\   ← bộ máy fingerprint (MIT)
├── bin\                ← ffmpeg.exe, ffprobe.exe
├── data\               ← db.pklz (kho vân tay), lichsu.db, downloads\
└── ketqua\             ← báo cáo CSV
```

---

# PHẦN BỔ SUNG (v2): Đồng bộ kênh gốc + Google Sheets

## A. Vì sao chỉ lưu audio, không lưu video?

Đã **đo thực nghiệm** chứ không phỏng đoán. Giấu một clip vào bản ghi dài ở mốc đã biết,
rồi thử đối chiếu bằng nhiều mức nén khác nhau (bản đối chiếu cũng bị nén lại để mô phỏng
đúng thực tế video vi phạm trên YouTube):

| Bản dùng làm đối chiếu | Dung lượng | Số hash khớp | Tìm đúng vị trí |
|---|---|---|---|
| Video gốc | 100% | 221 | ✅ |
| **Opus mono 64 kbps** | **~1%** | **225** | ✅ |
| Opus mono 32 kbps | ~0,5% | 164 | ✅ |

**Kết luận: audio mono 64 kbps cho độ chính xác NGANG BẰNG video gốc.** Lý do: fingerprint
chỉ tính từ âm thanh, pixel không đóng góp gì; hơn nữa audfprint hạ mẫu về 11025 Hz nên
chỉ dùng phổ tới ~5,5 kHz — lưu chất lượng cao hơn là lãng phí ổ cứng.

Ước tính cho 300 video × 7 phút:
- Tải cả video 1080p: **45–90 GB**
- Audio mặc định của yt-dlp: ~3 GB
- **Opus mono 64 kbps (hệ thống đang dùng): ~700 MB**

Đừng hạ dưới 64 kbps — xuống 32 kbps vẫn tìm ra nhưng bằng chứng yếu đi một nửa,
dễ bị lọc mất khi video vi phạm đã bị nén nát.

## B. Tab «Đồng bộ kênh gốc»

1. Dán link kênh (dạng `https://www.youtube.com/@TenKenh`).
2. Nhập thư mục kho (ổ D, E... tùy bạn), ví dụ `D:\KhoClipGoc`.
3. Bấm **Xem danh sách video** để xem trước và biết ước tính dung lượng — chưa tải gì cả.
4. Bấm **Bắt đầu đồng bộ kênh**.
5. Xong thì sang tab «Kho clip gốc» → **Bổ sung clip mới vào kho** để tạo vân tay.

Đặt tên file: `20250115 - Tiêu đề video [ID].opus` — giữ đúng tiêu đề trên YouTube,
kèm ID để định danh bền vững (tiêu đề có thể bị sửa, ID thì không).

**Đồng bộ tăng dần:** hệ thống ghi `downloaded.txt` trong thư mục kho theo đúng định dạng
`--download-archive` của yt-dlp. Chạy lại bất cứ lúc nào → chỉ tải video MỚI.
Kênh ra video mới hàng tuần thì cứ chạy lại tab này, mất vài phút.

## C. Báo cáo giờ có thêm 4 cột

| Cột mới | Giá trị |
|---|---|
| Thời điểm quét | Để lọc theo đợt trong Google Sheets |
| Tên video gốc (YouTube) | Tiêu đề thật, lấy từ `clips_meta.json` |
| Link video gốc | Link tới video gốc của bạn |
| **🔗 Nhảy tới đúng mốc vi phạm** | `https://youtu.be/ID?t=7605` — bấm là YouTube mở đúng giây vi phạm |

Cột cuối là thứ tiết kiệm nhiều thời gian nhất khi làm hồ sơ khiếu nại: không phải tua tay
trong video 30 tiếng.

## D. Thiết lập Google Sheets (một lần, ~10 phút)

1. https://console.cloud.google.com → tạo Project.
2. **APIs & Services → Enable APIs** → bật **Google Sheets API** và **Google Drive API**.
3. **Credentials → Create Credentials → Service account** → Create.
4. Bấm vào service account → tab **Keys** → Add key → **JSON** → tải về.
5. Đổi tên thành `google_key.json`, để trong thư mục `TimClipPro`.
6. Mở giao diện → thanh bên → **📊 Google Sheets** → nó hiện sẵn email service account.
7. Mở Google Sheet của bạn → **Chia sẻ** → dán email đó → quyền **Người chỉnh sửa**.
8. Dán link Sheet vào ô, bấm **Kiểm tra kết nối**.

Sau đó mỗi lần quét xong, kết quả **tự nối thêm** vào cuối trang tính (không ghi đè).
Bỏ tick «Tự động đẩy» nếu muốn bấm tay.

⚠️ `google_key.json` là khoá riêng — đừng gửi cho ai, đừng đẩy lên GitHub
(đã có sẵn `.gitignore` chặn).

## E. Lệnh dòng lệnh mới

```bat
python cli.py kenh "https://youtube.com/@TenKenh" --kho "D:\KhoClipGoc"
python cli.py themclip "D:\KhoClipGoc"
python cli.py youtube --file links.txt
```

Ghép 3 lệnh này vào một file `.bat` + Task Scheduler = hệ thống giám sát tự động chạy hằng đêm.

---

# PHẦN BỔ SUNG (v3): Sửa lỗi + Nhiều kho

## A. Tiếp tục tải khi bị mất mạng (715/748)

**Tin tốt: bạn không mất gì cả, và không phải tải lại từ đầu.**

Hệ thống nhận diện video đã tải bằng **hai lớp**: file `downloaded.txt` và mã ID nằm trong
tên file (`... [Ab3xY9].opus`). Từ bản này, khi đồng bộ nó lấy **hợp của cả hai** — nên dù
`downloaded.txt` có lệch thế nào, file đã nằm trên đĩa là chắc chắn không bị tải lại.

Việc cần làm:

1. Vào tab **📥 Đồng bộ kênh gốc**, nhập lại link kênh và thư mục `D:\ClipGocSML`.
2. Bấm **🔍 Kiểm tra còn thiếu video nào** → hiện đúng danh sách 33 video còn thiếu.
3. Bấm **⬇️ Bắt đầu đồng bộ kênh** → chỉ tải 33 video đó.

Nếu `downloaded.txt` bị mất hoặc bạn từng chép file thủ công vào kho, bấm thêm
**🛠️ Dựng lại danh sách đã tải** — nó quét đĩa và ghi lại danh sách cho khớp thực tế.
Nút này chỉ ghi file text, **không bao giờ đụng vào file audio**.

## B. Vì sao tạo kho đứng ở 0% — và đã sửa thế nào

Đây là lỗi thật, mình đã tái hiện được và tìm ra nguyên nhân gốc:

> Thư viện `audfprint` mở file danh sách bằng `open()` mà **không chỉ định bảng mã**.
> Trên Windows tiếng Việt (bảng mã cp1258/cp1252), đọc danh sách chứa tên file có dấu
> tiếng Việt sẽ lỗi `UnicodeDecodeError` và **chết ngay từ file đầu tiên** — không in ra
> dòng nào, nên tiến độ đứng nguyên 0%.

Kênh của bạn là kênh tiếng Việt nên gần như 100% file đều có dấu → lỗi xảy ra ngay lập tức.

Đã sửa bằng cách ép tiến trình con chạy ở chế độ UTF-8 (`PYTHONUTF8=1`), **không sửa thư
viện gốc** nên sau này cập nhật audfprint vẫn không mất bản vá. Mình đã kiểm chứng: cùng
một file tên `Hướng dẫn làm bánh chưng ngày Tết.opus`, trước khi sửa thì crash, sau khi
sửa thì chạy bình thường.

**Kèm theo, sửa luôn một lỗi thiết kế:** trước đây mọi thông báo lỗi của audfprint đều bị
nuốt mất, chỉ hiện câu chung chung. Giờ báo lỗi hiện đúng nguyên văn, và nếu chạy xong mà
xử lý 0 file thì cũng bị coi là lỗi (trước đây báo "thành công" nhầm).

## C. Nhiều kho clip gốc

Giờ bạn tạo được nhiều kho độc lập — mỗi kho có bộ vân tay riêng.

**Cách dùng:**
1. Tab **🎬 Kho clip gốc** → **➕ Tạo kho mới** → đặt tên (ví dụ: `Ẩm thực`, `Du lịch`).
2. Nhập thư mục của kho đó → **Tạo lại kho từ đầu**.
3. Khi quét video vi phạm: chọn kho ở **thanh bên → 🗄️ Kho đang dùng**.

Lợi ích: quét nhanh hơn (chỉ đối chiếu với kho liên quan) và ít báo nhầm hơn.
Kho cũ của bạn tự động được chuyển thành "Kho mặc định", không mất dữ liệu.

⚠️ Nút xoá kho chỉ xoá **file vân tay**, tuyệt đối không đụng tới video/audio gốc của bạn.

---

# PHẦN BỔ SUNG (v4): Sửa WinError 32 + Chọn lọc kết quả thông minh

## A. Lỗi WinError 32 — nguyên nhân và cách sửa

Lỗi xảy ra ở dòng `os.remove()` khi bấm «Tạo lại kho từ đầu». Bạn đoán đúng: **vì kho đã
được nạp trước đó**. Chi tiết: thư viện audfprint mở file vân tay bằng `gzip.open()` mà
**không đóng lại**. Windows (khác Linux) không cho xoá file đang có handle mở → WinError 32.
Tệ hơn, Streamlit vẽ lại màn hình liên tục, mỗi lần lại mở file một lần nữa.

Đã sửa **4 lớp phòng vệ**:
1. Đọc file vân tay vào RAM trong khối `with` rồi mới xử lý — không bao giờ giữ handle.
2. Nhớ đệm theo thời gian sửa file — không đọc lại file hàng trăm MB mỗi lần vẽ màn hình
   (**giao diện cũng nhanh hơn hẳn** với kho 748 clip).
3. Xoá file có thử lại 6 lần kèm dọn bộ nhớ — chịu được phần mềm diệt virus khoá tạm.
4. Nếu vẫn khoá: **tự chuyển sang file vân tay mới**, bạn không phải làm gì cả.

## B. Chọn lọc kết quả — chỉ giữ 5 bằng chứng mạnh nhất

### Vấn đề với cách chọn "5 cái nhiều hash nhất"

Video vi phạm 3 tiếng thường ghép 9–18 clip gốc. Nếu chỉ lấy 5 cái nhiều hash nhất,
chúng **rất dễ dồn vào một chỗ** (ví dụ 5 clip đầu video), khiến hồ sơ khiếu nại trông
như chỉ vi phạm một đoạn ngắn.

Hệ thống chia video vi phạm thành 5 vùng thời gian đều nhau, **mỗi vùng lấy 1 bằng chứng
mạnh nhất**, và ưu tiên 5 clip gốc **khác nhau**. Kết quả: hồ sơ chứng minh vi phạm trải
dài toàn bộ video — mạnh hơn nhiều.

Đã kiểm chứng bằng bài test cố tình đặt bẫy (5 clip mạnh nhất đều nằm trong 20 phút đầu):
thuật toán vẫn chọn ra kết quả trải đều Đầu / Giữa / Cuối.

### Tham số (thanh bên → ⚙️ Tham số → Chọn lọc kết quả)

| Tham số | Mặc định | Ý nghĩa |
|---|---|---|
| Chỉ lấy bao nhiêu kết quả tốt nhất | 5 | Đúng yêu cầu của bạn |
| Loại hẳn nếu dưới (hash) | 1000 | Dưới ngưỡng: vứt bỏ, không vào báo cáo |
| Coi là bằng chứng mạnh từ (hash) | 5000 | Đạt ngưỡng này được ưu tiên chọn trước |
| Phân bổ đều đầu/giữa/cuối | Bật | Tắt nếu chỉ muốn lấy đơn thuần theo hash |
| Ưu tiên các clip gốc khác nhau | Bật | Tránh 5 kết quả đều là một clip |

### ⚠️ Lưu ý quan trọng về con số 5000

**Số hash không phải đại lượng tuyệt đối** — nó phụ thuộc độ dài clip và độ phong phú
âm thanh. Clip 15 phút nhạc sôi động có thể cho 8000 hash, còn clip 10 phút chủ yếu là
lời nói chỉ được 2000 hash dù khớp 100%.

Vì vậy mình bổ sung cột **«Tỷ lệ vân tay khớp (%)»** — đây mới là thước đo chuẩn:
nó cho biết **bao nhiêu phần trăm vân tay của clip gốc được tìm thấy**, không phụ thuộc
độ dài. Trên 80% là gần như chắc chắn dùng trọn clip.

Hệ thống có **lưới an toàn**: nếu ngưỡng đặt quá cao khiến mọi kết quả bị loại, giao diện
sẽ **cảnh báo rõ**, cho xem danh sách bị loại và **gợi ý con số nên hạ xuống** — chứ không
im lặng trả về 0 kết quả. Bạn hãy chạy thử một video thật rồi xem cột hash và tỷ lệ để
hiệu chỉnh ngưỡng cho đúng kho của mình.

## C. Báo cáo có thêm 2 cột

| Cột mới | Ý nghĩa |
|---|---|
| **Vùng** | Đầu / Giữa / Cuối video vi phạm |
| **Tỷ lệ vân tay khớp (%)** | Thước đo chuẩn hoá, không phụ thuộc độ dài clip |

## D. Chống tự khớp

Nếu bạn lỡ để video vi phạm nằm chung thư mục với clip gốc, trước đây nó sẽ khớp 100%
với chính nó và chiếm mất một suất trong top 5. Giờ hệ thống tự loại trường hợp này.

---

# PHẦN BỔ SUNG (v5): Chạy giám sát tự động bằng Task Scheduler

## A. Tạo danh sách theo dõi

Tạo file `watchlist.json` trong thư mục dự án với nội dung mẫu đầy đủ:

```json
{
  "muc": [
    {
      "loai": "kenh",
      "url": "https://www.youtube.com/@TenKenh",
      "ghi_chu": "Kênh cần theo dõi",
      "bat": true
    },
    {
      "loai": "link",
      "url": "https://youtu.be/dQw4w9WgXcQ",
      "ghi_chu": "Video cần kiểm tra",
      "bat": true
    }
  ],
  "kho": "Kho mặc định",
  "gioi_han_moi_lan": 20
}
```

- `loai` nhận `kenh` hoặc `link`.
- Đặt `bat` thành `false` để tạm bỏ qua một mục.
- `kho` là tên kho vân tay dùng để đối chiếu.
- `gioi_han_moi_lan` giới hạn số video mới quét trong mỗi lượt.

Có thể chạy thử bằng lệnh:

```text
python cli.py watch
python cli.py watch --file duong\dan\watchlist.json --gioi-han 5
python cli.py watch --sheet "https://docs.google.com/spreadsheets/d/..."
```

## B. Ghép lịch chạy trong Windows Task Scheduler

1. Mở **Task Scheduler**.
2. Chọn **Create Basic Task** và đặt tên cho tác vụ.
3. Chọn tần suất chạy mong muốn, ví dụ mỗi ngày.
4. Ở bước **Action**, chọn **Start a program**.
5. Trong **Program/script**, chọn file `GiamSat.bat` trong thư mục dự án.
6. Trong **Start in**, nhập đường dẫn đầy đủ tới thư mục dự án.
7. Hoàn tất trình hướng dẫn và chạy thử tác vụ một lần.

`GiamSat.bat` chạy nền, không dừng chờ bàn phím. Nhật ký của từng ngày được nối vào
`ketqua\giamsat_YYYYMMDD.log`. Task Scheduler nhận mã thoát `0` khi lượt chạy không có
lỗi và mã `1` khi báo cáo có lỗi.
