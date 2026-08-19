# Tự cập nhật theo tag phiên bản

Máy người dùng tự lấy bản mới từ GitHub mỗi lần mở tool. Bạn không phải chép source
thủ công sang từng máy nữa.

## Vì sao theo tag chứ không theo nhánh `main`

Bạn vẫn làm việc trên `main` hằng ngày. Nếu máy người dùng bám `main` thì mọi commit
dở dang đều rơi xuống máy họ. Bám **tag** nghĩa là bạn quyết định lúc nào phát hành.

## Phát hành một bản mới

```bash
git tag v2.2 && git push origin v2.2
```

Xong. Mọi máy nhận được ở lần mở tool kế tiếp.

## ⚠️ Việc phải làm MỘT LẦN trước khi dùng cơ chế này

**Cả 5 tag hiện có (`v1.0` … `v2.1`) đều CŨ HƠN lần tái cấu trúc dự án.** Ở các tag đó,
file nằm ngay thư mục gốc repo; còn bây giờ chúng nằm trong `TimClipPro/`. Chưa có tag
nào mang cấu trúc hiện tại.

Nghĩa là phải tạo một tag mới từ `main` trước:

```bash
git tag v2.2 && git push origin v2.2
```

Và **máy nào đang ở `v2.0`/`v2.1` thì clone lại từ đầu**, đừng cập nhật lên — vì
`ChayTool.bat` mà họ đang bấm sẽ chuyển từ thư mục gốc vào `TimClipPro/`, tức biến mất
khỏi chỗ cũ giữa chừng.

## Cài lần đầu trên máy mới

```bash
git clone https://github.com/TuongChris/Tool_Quet.git
cd Tool_Quet/TimClipPro
git checkout v2.2
cai_dat.bat
```

Remote đang là SSH (`git@github.com:`) nên mỗi máy cần khoá SSH. Nếu repo để công khai
thì dùng HTTPS như trên là xong, không cần khoá. Repo riêng tư thì tạo **deploy key
chỉ-đọc** cho từng máy.

## Người dùng làm gì

Không làm gì cả. `ChayTool.bat` và `ChayMayPhu.bat` tự chạy `cap_nhat.py` trước khi
khởi động. Muốn cập nhật thủ công thì bấm `CapNhat.bat`.

| Lệnh | Tác dụng |
|---|---|
| `CapNhat.bat` | Lên bản mới nhất |
| `CapNhat.bat --kiem-tra` | Chỉ xem có bản mới không, không đổi gì |
| `CapNhat.bat --ban v2.1` | Về đúng một bản cũ (lùi phiên bản khi bản mới lỗi) |

## Ba rào chắn an toàn

**1. Không bao giờ làm mất việc của người dùng.** Cây làm việc có thay đổi chưa commit
thì `cap_nhat.py` DỪNG và báo rõ. Không `checkout --force`, không `stash`, không
`reset --hard` — có test dùng AST soi đối số thật của mọi lệnh git để giữ điều này.

**2. Không bao giờ để tool không chạy được.** Thiếu git, mất mạng, khoá SSH sai, tag
không tồn tại — tất cả đều trả về "bỏ qua" và tool vẫn mở bằng bản đang có.
`GIT_TERMINAL_PROMPT=0` và `BatchMode=yes` để git thất bại ngay thay vì treo chờ nhập
mật khẩu — quan trọng với máy chạy qua Task Scheduler.

**3. Không tự lùi bản trên máy phát triển.** Trên máy bạn, `main` gần như luôn đi trước
tag mới nhất. Không có rào này thì mở tool trên chính máy dev sẽ lùi về tag cũ và ném
bạn vào detached HEAD. `cap_nhat.py` chỉ tiến, không lùi — trừ khi bạn gõ `--ban` tường
minh.

## Vì sao .bat khởi động lại chính nó sau khi cập nhật

`git checkout` có thể thay chính file `.bat` đang chạy, mà `cmd` đọc file lệnh theo
**vị trí byte** trong lúc thực thi — file đổi giữa chừng là các dòng sau bị đọc lệch.

Nên `cap_nhat.py` trả mã thoát riêng để `.bat` biết:

| Mã | Nghĩa | `.bat` làm gì |
|---|---|---|
| 0 | Không đổi gì | Chạy tiếp bình thường |
| 10 | Đã đổi bản | Mở lại chính mình rồi thoát |
| 11 | Đã đổi bản, thư viện cũng đổi | `pip install` rồi mở lại |

`ChayMayPhu.bat` thì thoát luôn và bỏ qua lượt giám sát đó; Task Scheduler gọi lại theo
lịch và lượt sau chạy bằng mã mới.

Lưu ý cho batch: `if errorlevel 10` nghĩa là **>= 10**, nên phải kiểm `11` TRƯỚC `10`.
Có test giữ đúng thứ tự này.

## Dữ liệu người dùng không bao giờ bị ghi đè

Những thứ sau nằm trong `.gitignore` nên `git checkout` không chạm tới:

`data/` · `ketqua/` · `bin/` · `google_key.json` · `cau_hinh.json` · `watchlist.json` ·
`cookies.txt`

`watchlist.json` từng bị git theo dõi — đã gỡ ngày 18/08/2026, vì mỗi lần cập nhật nó
sẽ đè danh sách giám sát riêng của từng máy. Bản mẫu `watchlist.example.json` vẫn được
theo dõi để người dùng biết định dạng.

**Thêm file dữ liệu mới thì PHẢI thêm vào `.gitignore` trước.** Test
`test_du_lieu_nguoi_dung_khong_bi_git_theo_doi` chặn việc quên.

## Gói triển khai và cấu hình riêng của máy

`dong_goi_may_chay.py` gỡ các khoá chỉ đúng trên máy nguồn — xem `KHOA_RIENG_CUA_MAY`:

| Khoá | Vì sao gỡ |
|---|---|
| `kho_dir`, `thu_muc_quet_gan_nhat` | Đường dẫn không tồn tại ở máy khác |
| `ytdlp_cookiefile` | Rào chắn cookie sẽ NÉM LỖI và chặn mọi lượt tải ở máy đích |
| `ytdlp_cookies_browser` | Máy đích sẽ quét bằng tài khoản Google của người khác |

Cố ý **giữ lại** `sheet_link` (mục đích của máy phụ là dồn kết quả về cùng một Sheet)
và `ytdlp_sleep_*` (tham số chống bị chặn, máy nào cũng cần).
