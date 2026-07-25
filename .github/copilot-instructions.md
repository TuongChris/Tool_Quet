# Chỉ dẫn cho Copilot / Codex — dự án TimClipPro

Dự án Python 3.10+ (KHÔNG phải TypeScript). Tìm video gốc trong video vi phạm bằng audio fingerprinting. Chạy local trên Windows.

## Quy tắc bắt buộc

- Viết Python, không viết TypeScript/JavaScript. Type hint ở mọi hàm public.
- `engine.py` là lõi: KHÔNG được `import streamlit`, KHÔNG `print()`, KHÔNG `input()`. Lý do: lõi phải dùng được từ CLI, web UI và test — biết về giao diện là mất tính tái sử dụng.
- Báo tiến độ qua callback `progress(pct: float, msg: str)`, không print. Lý do: mỗi giao diện hiển thị tiến độ một kiểu khác nhau.
- Tác vụ dài phải kiểm tra `self.cancel_event.is_set()` và ném `Cancelled`. Lý do: người dùng phải dừng được job chạy hàng giờ.
- Mọi chuỗi hiển thị cho người dùng viết bằng tiếng Việt có dấu.
- KHÔNG sửa file trong `audfprint-master/`. Đó là thư viện bên thứ ba giấy phép MIT; cần đổi hành vi thì bọc lại trong `engine.py`.

## Bẫy đã từng gây lỗi thật — đừng lặp lại

- KHÔNG gọi `os.remove()` trực tiếp lên file `.pklz`. Dùng `Engine._xoa_an_toan()`. Lý do: Windows không cho xoá file đang có handle mở → WinError 32.
- KHÔNG dùng `hash_table.HashTable(path)` ở tiến trình cha. Dùng `Engine.db_clips()`. Lý do: thư viện gọi `gzip.open()` mà không đóng, rò rỉ handle.
- Mọi lệnh gọi Python con phải qua `Engine._run_stream()`. Lý do: hàm này ép `PYTHONUTF8=1`, thiếu nó thì tên file tiếng Việt gây `UnicodeDecodeError` trên Windows.
- Hàm cấp cao trả `ScanResult(status="error", note=...)` thay vì ném exception ra UI. Lý do: quét hàng loạt không được đứt giữa chừng vì một nguồn hỏng.
- Số cột trong `Engine.to_rows()` phải luôn bằng `len(Engine.HEADER)` ở CẢ BA nhánh (ok / rỗng / lỗi). Lý do: lệch cột là hỏng CSV và Google Sheets.

## Kiểm thử

- Mỗi hàm mới phải có test trong `tests/`.
- Chạy `python -m pytest -q` trước khi báo xong. Test chậm: `python -m pytest -m slow`.
- Test logic thuần dùng helper `M()` trong `tests/conftest.py` để tạo `Match` giả, không cần audio thật.

## Tham chiếu sâu

Kiến trúc, ràng buộc nghiệp vụ và số liệu đã hiệu chỉnh: xem `CLAUDE.md`.
