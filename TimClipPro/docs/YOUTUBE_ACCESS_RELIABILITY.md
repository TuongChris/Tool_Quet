# Truy cập YouTube có kiểm soát — phân loại lỗi, thử lại hữu hạn, cầu dao, cookie an toàn

Nhánh `hardening/youtube-access-reliability` (từ `d67ce31`, 03/10/2026). Đây KHÔNG phải công cụ
vượt chặn: không CAPTCHA, không đổi proxy/dấu vân tay, không tự lấy cookie trình duyệt, không
PO-token, không đăng nhập tự động. YouTube từ chối thì tool **chẩn đoán, giảm request và dừng an
toàn**.

## 1. Vì sao (đo trên source `d67ce31`)

| # | Vấn đề | Bằng chứng |
|---|---|---|
| 1 | Không vòng lặp nào có cầu dao: bị nghi là bot vẫn chạy tiếp hết batch / lượt Watch / lô nguồn chung / đồng bộ kênh | `engine.scan_iter`, `watch._thuc_hien_giam_sat`, `common_original_jobs._chuan_bi`, `channel._sync_da_khoa` — mục 6c: bot-check chặn theo IP, request sau đều hỏng |
| 2 | Đường lui player client thử đủ 5 client cho MỌI lỗi | `ytdlp_chung.thu_tung_client` — bot-check đánh ở khâu trích xuất, đổi client vô ích |
| 3 | Phân loại chỉ bằng vài phép so chuỗi; không nhận ra `Video unavailable` (chữ ký THẬT Job 43/130, Tier 2) | `giai_thich_loi` |
| 4 | Liệt kê kênh `ignoreerrors=True` nuốt lỗi → `[]` → "Kiểm tra lại link kênh" (đổ lỗi sai), Watch lặng lẽ 0 ứng viên | `channel.list_channel` |
| 5 | Link kênh lọt vào ô quét video: yt-dlp resolve từng video của kênh (N request) | `engine.youtube_info` không `extract_flat` |
| 6 | Thử lại rải rác: `va_metadata_thieu` thử 3 lần cả lỗi vĩnh viễn với `time.sleep` không huỷ được; yt-dlp `retries=10` không nghỉ | engine/channel |
| 7 | Watch dạng dọc (`--dang-doc`) đẩy dòng "(LỖI…)" của lỗi truy cập lên Sheets (dạng ngang mặc định và giao diện thì không) | `watch.py` + `Engine.to_rows` vs `to_rows_ngang`, `app.py:137` |
| 8 | `kiem_ngay_dang --repair-network` bỏ qua cookie + nhịp người dùng | `_fetcher_mac_dinh` |
| 9 | Cổng cookie bỏ qua dòng `#HttpOnly_` (yt-dlp nạp và IN NGUYÊN VĂN dòng hỏng ra stderr), không kiểm dòng tiêu đề mà `MozillaCookieJar` bắt buộc | `kiem_tra_file_cookie` vs `yt_dlp/cookies.py:1362-1389` |

## 2. Kiến trúc

```
engine.py · channel.py · watch.py · common_original_jobs.py · kiem_ngay_dang.py · cli.py · app.py
                         │ (mọi thao tác YouTube)
                         ▼
ytdlp_chung.py  ── nguồn DUY NHẤT của tuỳ chọn yt-dlp (`CauHinhMang.tuy_chon(thao_tac, …)`),
                   đường lui cookie/client, `BoGhiYtdlp` (logger yt-dlp đã che bí mật)
                         │
                         ▼
truy_cap_youtube.py ── THUẦN: phân loại lỗi, che bí mật, chẩn đoán cookie, bảng ngân sách thử
                       lại, `PhienYouTube` (cầu dao + bộ chạy thử lại huỷ được + số đo)
```

- **Phân loại — một nơi** (`phan_loai_loi`): đọc cả chuỗi ngoại lệ (`exc_info` của DownloadError,
  `cause` của ExtractorError, `__cause__`) và mã HTTP thật (`HTTPError.status`). Thứ tự luật cố
  định: bot → 429/giới hạn → cookie hỏng → cần đăng nhập → vĩnh viễn → đầu vào sai → 403 → mạng
  tạm thời → định dạng/trích xuất → tải hỏng → khác. Không có luật kiểu `"sign" in loi` (câu riêng
  tư có "Sign in if you've been granted access").
- **Kết quả**: `YoutubeAccessFailure(category, operation, video_id, retryable, auth_related,
  rate_limited, human_message_vi, technical_summary, http_status, attempt, max_attempts)`; ngoại lệ
  `LoiTruyCapYouTube`; `ScanResult.loi_truy_cap` (chỉ trong bộ nhớ).
- **Phiên = một lượt chạy**: bản Engine ghim của một job tự tạo phiên (scan_iter, scan lẻ, lô nguồn
  chung); Watch mở một phiên cho cả lượt (`Engine.mo_phien_youtube`); mỗi `ChannelSync` một phiên;
  `kiem_ngay_dang.repair` một phiên. Bộ điều phối hỏi `phien.mo` trước MỖI việc mạng.

## 3. Ma trận lỗi

| Loại | Ví dụ (khuôn câu yt-dlp) | Thử lại | Đổi client | Mở cầu dao sau | Kết quả |
|---|---|---|---|---|---|
| PERMANENT_UNAVAILABLE | `Video unavailable`, private, removed, terminated, geo, 404 | không | dừng | không bao giờ | error, video đó |
| AUTH_REQUIRED | confirm your age, members-only, login details are needed | không | dừng | 3 liên tiếp | error |
| BOT_CHALLENGE | not a bot, captcha, IP likely blocked | không | dừng | **1** | error + dừng lượt |
| RATE_LIMITED | HTTP 429 / too many requests | 1 lần sau 30 s (metadata/liệt kê) | dừng | **1** | error + dừng lượt |
| RATE_LIMITED (phiên) | "try again later … rate-limited … up to an hour" | không | dừng | 1 | error + dừng lượt |
| HTTP_FORBIDDEN | HTTP 403 (KHÔNG tự suy ra cookie/bot) | không | **vẫn đổi** (mục 6) | 3 liên tiếp | error |
| TRANSIENT_NETWORK | timed out, connection reset, DNS, 5xx | 1 lần sau 3 s (metadata/liệt kê); tải: yt-dlp tự nối tiếp | vẫn đổi | 3 liên tiếp | error |
| COOKIE_INVALID_OR_EXPIRED | cổng cookie từ chối file | không | dừng | **1** | error + dừng lượt |
| FORMAT_OR_EXTRACTOR_ERROR | format not available, page needs reload, n challenge | không | vẫn đổi | 5 liên tiếp | error |
| PARTIAL_OR_CORRUPT_DOWNLOAD | không thấy file sau khi tải, file rỗng | không | — | không | error |
| INVALID_INPUT | link kênh/playlist ở ô video, danh sách là TAB | không | dừng | không | error |
| UNKNOWN_YOUTUBE_ERROR | còn lại | không | vẫn đổi | 5 liên tiếp | error |
| BLOCKED_BY_BREAKER | (không gửi request) | — | — | — | "Chưa quét", không lịch sử |

"Liên tiếp" = không xen thao tác thành công nào. Cầu dao không tự nửa mở: mở là dừng hẳn lượt
đó, người dùng chạy lại sau khi nghỉ / sửa cookie / sửa mạng.

**Lỗi truy cập không bao giờ là âm tính**: status luôn `error`; video bị bỏ qua không vào
`lichsu.db` (Watch quét lại lượt sau); lô nguồn chung kết luận CHƯA KẾT LUẬN kèm lý do; Watch
không đẩy dòng lỗi YouTube lên Sheets; CLI thoát mã 3.

## 4. Ngân sách thử lại (một bảng: `truy_cap_youtube.NGAN_SACH`)

| Thao tác | Thử lại ngoài (mạng / 429) | yt-dlp tự thử lại bên trong | Nghỉ bên trong |
|---|---|---|---|
| metadata, listing | 1 (3 s) / 1 (30 s) | trích xuất 3 lần (mặc định yt-dlp) | 2–5 s, có trần |
| download | **0** — đường lui client + yt-dlp tự nối tiếp; vòng ngoài sẽ đụng `.part` của client khác | 10 / 10 (giữ như cũ) | 1, 2, 4, 5… s, trần 5 s |

Nghỉ của phiên huỷ được (`Event.wait`; với `cancel_check()` thì hỏi lại mỗi 0,2 s). Nhịp giữa
request vẫn chỉ do `ytdlp_sleep_requests_s` (yt-dlp) và bộ điều phối lô nguồn chung lo — không có
`time.sleep` mới nào.

## 5. Cookie

- Cổng `kiem_tra_file_cookie` kiểm ĐÚNG luật nạp của yt-dlp: dòng 1 là tiêu đề Netscape; dòng
  `#HttpOnly_` là bản ghi thật; mỗi bản ghi 7 trường TAB, hạn dùng là số; nhận diện file HTML/JSON.
  Thông báo chỉ nêu SỐ DÒNG.
- `chan_doan_cookie`: chỉ metadata + số đếm (bản ghi, youtube/google, hết hạn, dòng hỏng, có cookie
  đăng nhập theo đúng luật `_has_auth_cookies` của yt-dlp). `COOKIE_FILE_STRUCTURALLY_VALID` khác
  `COOKIE_SESSION_ACCEPTED_BY_YOUTUBE`: cái sau chỉ một request thật trả lời được (lùi không-cookie
  thành công, hoặc cảnh báo "cookies are no longer valid" mà `BoGhiYtdlp` giờ nghe được).
- Không đọc profile trình duyệt, không tự bật `cookiesfrombrowser`, không chép cookie ra đâu cả.
  Giữ nguyên cơ chế yt-dlp ghi lại file cookie sau mỗi phiên (`YoutubeDL.close → save_cookies`).

## 6. Che bí mật

`che_bi_mat` (luỹ đẳng): header Cookie/Set-Cookie/Authorization, Bearer, SAPISIDHASH, giá trị tham
số URL (giữ `v`, `list`, `index`, `t`), cặp token/key/sig/password, tên cookie đăng nhập + giá trị,
dòng Netscape, dòng cảnh báo cookie của yt-dlp, khối PEM. Áp ở: `giai_thich_loi` (ghi chú → lịch
sử/CSV), tóm tắt kỹ thuật của mọi lỗi, `BoGhiYtdlp`, log đổi client, `nhat_ky.che_bi_mat` (stderr
→ file nhật ký Watch).

## 7. Dùng lại metadata và đếm request

`scan_youtube(info=…)` không hỏi lại YouTube (lô nguồn chung dùng). Test đếm đúng từng lần mở
phiên yt-dlp (`tests/ytdlp_gia.py`): lô nguồn chung 3 video = đúng 3 lần lấy thông tin; batch 20
link bị bot-check = đúng 1 request; Watch 50 link cần đăng nhập = đúng 3 request. Số đo mỗi lượt
(`PhienYouTube.tom_tat()`): `youtube_operations`, `metadata_requests`, `download_attempts`,
`listing_requests`, `retries`, `auth_failures`, `bot_challenges`, `rate_limited`, `http_403`,
`transient`, `cookie_fallbacks`, `client_fallbacks`, `skipped_by_breaker`, `breaker_events`.

Liệt kê kênh: mục không phải video (tab, playlist con — `ie_key=YoutubeTab`, id `UC…`, url tới
kênh/tab) bị loại; chỉ toàn tab thì báo INVALID_INPUT kèm hướng dẫn. Link `/channel/UC…` thiếu
`/videos` nay tự thêm `/videos` như link `@tên` (commit riêng, `tests/test_kenh_link_videos.py`).

## 8. Giao diện và CLI

- Thanh bên «🔐 Kết nối YouTube» → **Trạng thái YouTube**: lượt gần nhất (bình thường / bị chặn /
  cookie bị từ chối) + cấu trúc cookie (chỉ số đếm).
- Quét lô bị dừng: banner đỏ "Đã dừng yêu cầu mới tới YouTube…", video còn lại "Chưa quét".
- CLI: mã thoát 0 xong · 1 lỗi · 2 bận · **3 YouTube chặn truy cập**; lỗi vận hành đã phân loại
  không in traceback.
- `python cli.py youtube-doctor [--network URL]`: chẩn đoán chỉ đọc (yt-dlp, bộ giải JS, JS runtime,
  cấu hình mạng, cookie dạng số đếm, bảng thử lại, ngưỡng cầu dao); chỉ gọi đúng MỘT request khi
  người dùng tự đưa `--network`. Không bao giờ gọi Google.

## 9. Test

| File | Khoá điều gì |
|---|---|
| `tests/test_truy_cap_youtube.py` | phân loại theo khuôn câu thật (cả mã màu ANSI, chuỗi ngoại lệ, mã HTTP), che bí mật mọi đường, chẩn đoán cookie, cổng cookie mới |
| `tests/test_phien_youtube.py` | thử lại đúng số lần, không thử lại lỗi vĩnh viễn/bot, 429 có nghỉ rồi mở cầu dao, huỷ trong lúc nghỉ thoát < 3 s, ngưỡng theo loại, không ghi hai lần, `dung_ngay` của đường lui client, bảng tuỳ chọn nội bộ yt-dlp |
| `tests/test_truy_cap_youtube_lo.py` | batch 20 link, video gỡ không dừng lô, 429, `info=` không hỏi lại, tải bị chặn không đổi client, link kênh ở ô video, cookie chết, bí mật không vào lịch sử, Watch 50 link, Watch chỉ đẩy kết quả hợp lệ, Watch liệt kê 429, lô nguồn chung (lấy thông tin bị chặn / đếm 3 request / chặn giữa lượt quét), bảng điều khiển |
| `tests/test_truy_cap_youtube_kenh.py` | đồng bộ dừng sau video đầu bị chặn và không đụng file cũ, liệt kê bị 429 không thành danh sách rỗng, TAB thay vì video, `lay_ngay_dang`, vá metadata, `kiem_ngay_dang` dừng ngay + dùng cấu hình người dùng |
| `tests/test_truy_cap_youtube_cli.py` | mã thoát 3, mã 2 giữ nguyên, không traceback |
| `tests/test_youtube_doctor.py` | mặc định 0 request, `--network` đúng 1 request, không lộ cookie |
| `tests/test_trang_thai_youtube_ui.py` | câu chữ trạng thái + AppTest không lộ cookie |

## 10. Giới hạn

- YouTube có thể chặn bất cứ lúc nào; tool chỉ làm cho việc bị chặn ít xảy ra hơn và không tệ thêm.
- Cookie hết hạn/bị xoay vòng là bình thường; tool chỉ phát hiện và nói rõ.
- Video riêng tư/đã gỡ vẫn không xem được nếu không có quyền.
- Không vượt CAPTCHA, không đổi proxy để né giới hạn.
