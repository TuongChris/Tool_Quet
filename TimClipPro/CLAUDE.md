# TimClip Pro — Ngữ cảnh dự án cho Claude Code

> File này Claude Code **tự động đọc** mỗi phiên làm việc. Viết tốt file này = Claude hiểu
> dự án ngay từ câu lệnh đầu tiên, không phải giải thích lại. Cập nhật nó khi dự án đổi.

## Dự án làm gì

Tìm **video gốc của tôi** (clip 5–10 phút) xuất hiện bên trong **video vi phạm** dài
3–30 tiếng, bằng **audio fingerprinting**. Chạy 100% local trên Windows. Người dùng
là người làm nội dung, **không phải lập trình viên** — mọi thứ phải bấm nút là chạy.

## Kiến trúc — quy tắc bất di bất dịch

```
app.py (Streamlit UI)   cli.py (dòng lệnh)   ← lớp giao diện, thay được
                    ↘        ↙
                    engine.py                 ← LÕI, không biết ai gọi nó
              ↙        ↓         ↘
   channel.py    sheets.py    audfprint-master/
   (tải kênh)   (Google Sheets)  (thư viện MIT, ĐỪNG SỬA)
```

**Quy tắc:**
1. `engine.py` **không được** `import streamlit`, không `print()`, không `input()`.
   Mọi tiến độ đi qua callback `progress(pct: float, msg: str)`.
2. Logic nghiệp vụ mới → viết vào `engine.py` hoặc module riêng, **không** viết trong `app.py`.
3. `audfprint-master/` là thư viện bên thứ ba — **không sửa**. Cần đổi hành vi thì bọc lại
   trong `engine.py`.
4. Mọi chuỗi hiển thị cho người dùng viết bằng **tiếng Việt**.

## File và vai trò

| File | Vai trò | Sửa khi |
|---|---|---|
| `engine.py` | Lõi: cắt khúc, fingerprint, so khớp, gộp trùng, SQLite, xuất CSV | Thêm/đổi logic xử lý |
| `channel.py` | Đồng bộ kênh YouTube → kho audio nén + `clips_meta.json` | Đổi cách tải/nén/đặt tên |
| `sheets.py` | Đẩy kết quả lên Google Sheets (gspread + service account) | Đổi cách ghi báo cáo |
| `app.py` | Giao diện Streamlit 5 tab | Đổi giao diện |
| `cli.py` | Giao diện dòng lệnh, dùng chung engine | Thêm lệnh tự động hoá |

## Kiến thức nghiệp vụ quan trọng (đã kiểm chứng bằng thực nghiệm)

- **Chỉ audio là đủ.** Fingerprint chỉ dùng âm thanh; pixel không đóng góp gì. Đã đo:
  clip nén opus mono 64 kbps cho **225 hash** so với **221 hash** của video gốc khi
  đối chiếu với bản đã bị nén lại. Nén xuống 32 kbps vẫn tìm đúng vị trí nhưng hash
  giảm còn ~50% → **64 kbps mono 16 kHz là điểm tối ưu**, đừng hạ thấp hơn.
- audfprint hạ mẫu về 11025 Hz nên chỉ dùng phổ tới ~5.5 kHz. Lưu audio > 16 kHz là lãng phí.
- Overlap hiệu lực phải nằm trong `[60, overlap_max_s]`; mặc định
  `overlap_max_s=180`. Clip dài hơn trần có thể bị chia thành nhiều mảnh ở ranh giới
  khúc; `_merge()` phải phục hồi bằng chứng bằng hợp interval và mật độ hash tốt nhất,
  không được tăng overlap vượt trần để bao trọn clip dài nhất.
- Điểm mù đã biết: video vi phạm bị **thay/đè toàn bộ tiếng** thì phương pháp này bó tay.
  Hướng mở rộng khi cần: pHash + OpenCV, cao hơn nữa là VCSL/TransVCL (cần GPU).
- `data/db.pklz` chứa vân tay; `clips_meta.json` (trong thư mục kho) map tên file →
  tiêu đề + link YouTube gốc. Báo cáo dựa vào cả hai.

## Quy ước code

- Python 3.10+, chuẩn PEP 8, dùng type hint ở chữ ký hàm public.
- Tên hàm/biến nội bộ có thể bằng tiếng Việt không dấu (`tao_db`, `lam_sach_ten`) —
  giữ nhất quán với code hiện có.
- Tác vụ dài **bắt buộc** nhận `progress` callback và kiểm tra `cancel_event`.
- Không dùng `localStorage`/`sessionStorage` (không áp dụng), không dùng biến toàn cục
  cho trạng thái job — dùng `st.session_state` ở tầng UI.
- Xử lý lỗi: hàm cấp cao trả `ScanResult(status="error", note=...)` thay vì ném exception
  ra tận UI, để quét hàng loạt không bị đứt giữa chừng.

## Quy ước khoá

- Mọi thao tác nặng có thể đọc hoặc ghi kho vân tay, lịch sử hay dữ liệu giám sát phải dùng
  chung khoá cấp hệ điều hành `data/tool.lock`. Tên chủ khoá vẫn phải mô tả đúng thao tác
  đang chạy để thông báo bận có ích cho người dùng.
- Nếu sau này thật sự cần nhiều khoá, phải quy định và tuân thủ một thứ tự lấy khoá cố định
  trên toàn dự án. Không được lấy các khoá theo thứ tự tùy ý vì sẽ tạo kẹt chéo.

## Ý nghĩa các trường thời gian trong Match

- `clip_bat_dau_s`: thời điểm **clip bắt đầu** trong video dài; dùng để hiển thị và tạo link
  nhảy mốc. `start_s` mang cùng ý nghĩa này.
- `vung_khop_s`: thời điểm **vùng vân tay bắt đầu khớp**, không phải đầu clip.
- `clip_offset_s`: độ dài phần đầu clip gốc đã bị bỏ qua trước khi vùng khớp bắt đầu.

Ba khái niệm trên không được dùng thay thế cho nhau. Khi dựng báo cáo hoặc link mốc, luôn dùng
thời điểm clip bắt đầu; khi chẩn đoán vân tay mới dùng vùng khớp và offset.

## Kiểm thử — LÀM ƠN CHẠY TRƯỚC KHI BÁO XONG

Dự án có hơn 240 test tự động. Trước khi kết luận một thay đổi là xong, phải chạy tối thiểu:

```bash
# 1) Toàn bộ suite nhanh
python -m pytest -q

# 2) Hai test tích hợp audio tổng hợp
python -m pytest -m slow

# 3) Lõi còn import sạch không
python -c "import engine, channel, sheets; print('ok')"
```

**Nếu tôi nhờ thêm tính năng, hãy tự viết test nhỏ để tự kiểm chứng trước khi báo cáo,
đừng chỉ nói "đã xong".** Với thay đổi liên quan chất lượng khớp, hãy tạo dữ liệu giả lập
(chèn 1 clip vào file dài ở mốc đã biết) rồi kiểm tra vị trí trả về có đúng không.

## Ranh giới an toàn — ĐỪNG tự ý làm

- **Đừng xoá hay ghi đè** `data/db.pklz`, `data/lichsu.db`, `downloaded.txt`,
  `clips_meta.json` — mất là phải fingerprint lại hàng chục giờ.
- **Đừng commit** `google_key.json` (khoá riêng Google) — đã có trong `.gitignore`.
- **Đừng đổi** thuật toán gộp trùng (`_merge`) hay ngưỡng mặc định nếu tôi không yêu cầu:
  chúng đã được hiệu chỉnh bằng thực nghiệm.
- **Đừng thêm** thư viện nặng (torch, tensorflow...) nếu chưa hỏi tôi — máy tôi không có GPU.
- Thay đổi lớn: giải thích phương án **trước**, chờ tôi đồng ý rồi mới code.

## Hướng phát triển đang cân nhắc

1. Tự động quét định kỳ (Task Scheduler) → đẩy Sheets → gửi email cảnh báo.
2. Sinh sẵn hồ sơ khiếu nại bản quyền (điền form YouTube) từ dòng kết quả.
3. Nhánh so khớp hình ảnh cho trường hợp video bị thay tiếng.
4. Đóng gói `.exe` bằng PyInstaller để không cần cài Python.

## Lỗi đã gặp và cách sửa (đừng để tái diễn)

**1. Tiến độ tạo kho đứng ở 0% trên Windows tiếng Việt.**
Nguyên nhân gốc: `audfprint.py` dòng 48 dùng `open(listfilename, 'r')` không chỉ định
encoding. Windows tiếng Việt dùng cp1258/cp1252 → đọc file danh sách UTF-8 có dấu tiếng
Việt là `UnicodeDecodeError` → chết ngay, không in dòng nào → tiến độ 0%.
Đã sửa: `_run_stream()` truyền `env` có `PYTHONUTF8=1`, `PYTHONIOENCODING=utf-8`,
`PYTHONUNBUFFERED=1` và chạy Python con với cờ `-u`. **Không sửa thư viện bên thứ ba.**
→ Mọi lần gọi subprocess Python trong dự án này đều phải đi qua `_run_stream()`.

**2. Lỗi bị nuốt mất.** Trước đây `_run_stream` bỏ qua mọi dòng không khớp "ingesting #",
nên lỗi thật không bao giờ hiện ra. Đã sửa: giữ 30 dòng cuối, báo lỗi kèm nội dung thật,
và coi "chạy xong nhưng xử lý 0 file" cũng là lỗi.

**3. Archive lệch với thực tế.** `sync()` giờ lấy hợp của `downloaded.txt` **và** ID đọc
từ tên file trên đĩa, nên tải đứt giữa chừng không bao giờ gây tải trùng.

**4. WinError 32 khi nạp lại kho (Windows).**
`os.remove(db_file)` trong `build_database(mode="new")` thất bại vì Windows không cho xoá
file đang có handle mở. Nguồn handle: `hash_table.HashTable(path)` gọi `gzip.open()` mà
không đóng, và `db_clips()` bị Streamlit gọi lại mỗi lần vẽ màn hình.
Đã sửa 4 lớp: (a) `db_clips()` tự đọc file vào RAM trong khối `with` rồi mới unpickle —
không bao giờ giữ handle; (b) cache theo mtime nên không đọc lại liên tục; (c)
`_xoa_an_toan()` thử lại 6 lần kèm `gc.collect()` để chịu được phần mềm diệt virus khoá
tạm; (d) nếu vẫn khoá thì tự chuyển sang file vân tay mới và cập nhật đăng ký kho.
→ **Không bao giờ gọi `os.remove()` trực tiếp lên file .pklz — dùng `_xoa_an_toan()`.**
→ **Không bao giờ dùng `hash_table.HashTable(path)` ở tiến trình cha.**

**5. Chọn lọc kết quả.** `_chon_loc()` chia video vi phạm thành `top_n` vùng thời gian đều
nhau, mỗi vùng lấy 1 bằng chứng mạnh nhất, ưu tiên clip gốc khác nhau. Lý do: bằng chứng
trải đều cả video thì hồ sơ khiếu nại mạnh hơn nhiều so với 5 đoạn dồn ở đầu video.
Chỉ số `ty_le` (% vân tay của clip khớp được) là thước đo CHUẨN HOÁ — dùng nó khi so sánh
các clip dài ngắn khác nhau, vì số hash tuyệt đối phụ thuộc độ dài và độ phong phú âm thanh.

**Bài học quy trình:** khi vá code bằng tìm-thay chuỗi, PHẢI kiểm tra lại là bản vá đã áp
dụng thật (chạy test tích hợp), vì chuỗi cũ có thể đã bị đổi ở lần vá trước.

## Quy trình Spec-Driven (Claude lập kế hoạch → Codex viết code)

Khi tôi yêu cầu một tính năng mới, ĐỪNG viết code ngay. Hãy:
1. Đọc `CLAUDE.md` + `.github/copilot-instructions.md` để nắm ràng buộc.
2. Chia tính năng thành 4–6 task nguyên tử, mỗi task đúng 1 file hoặc 1 hàm.
3. Xuất ra `docs/EXECUTION_PLAN.md` theo đúng khuôn trong `docs/PROMPT_CONTRACT.md`.
4. Không viết văn xuôi giải thích ngoài kế hoạch.

Khi tôi dán log lỗi: phân tích nguyên nhân gốc, trả về đúng một khối `## FIX cho TASK n`.

Thứ tự task chuẩn cho dự án này: (1) data model thuần → (2) hàm xử lý thuần →
(3) nối vào `engine.py` → (4) giao diện `app.py` → (5) test.
Lý do: task 1–2 là hàm thuần nên test được ngay không cần I/O, sai sót lộ ra sớm.
