# Changelog audit và tối ưu

Ngày: 2026-08-06.

## Thay đổi source/runtime

| File | Nội dung và lý do | Rủi ro | Test xác minh | Trước → Sau |
|---|---|---|---|---|
| `engine.py` | Inject `data_dir/out_dir`; validate resource/timeout config; chặn path database thoát data; yt-dlp timeout; export CSV exclusive + formula-safe | Medium | security/core/config/network/full suite | Test khởi tạo data thật, registry có thể traversal, network có thể chờ default, CSV overwrite → storage tạm, path bị từ chối, timeout 30s, suffix `_2` |
| `channel.py` | Đếm số tải thành công thực, trả `da_huy`, đặt yt-dlp socket timeout | Low | cancel/network regression/full suite | Cancel có thể báo toàn bộ đã tải và request dùng default → báo đúng số, timeout 30s |
| `sheets.py` | Gửi cell bằng `RAW` | Low–medium | fake worksheet/full suite | `USER_ENTERED` có thể chạy công thức → dữ liệu thuần |
| `app.py` | Data/output override qua env cho test/deploy; CSV download formula-safe; trạng thái cancel; help overlap đúng policy; xác nhận xóa | Low–medium | AppTest/full suite | Test/UI phụ thuộc data thật, xóa một bước → cô lập và xác nhận hai bước |
| `cli.py` | In `ĐÃ DỪNG` cho channel sync bị cancel | Low | full suite | Cancel vẫn ghi `XONG` → trạng thái rõ |
| `dong_goi.py` | Refactor thành hàm/CLI testable; deny secret case-insensitive; giữ audfprint/build file; loại runtime config; từ chối overwrite | Low | packaging tests + zip smoke | Archive cố định bị overwrite và có thể lọt nested secret → output explicit, kiểm tra hai lớp |

## Build, dependency và vận hành

| File | Nội dung và lý do | Rủi ro | Test xác minh |
|---|---|---|---|
| `.dockerignore` | Loại credential, 138.91 GiB data, venv, log, Windows binary, archive | Low | rule regression + source/context review |
| `Dockerfile` | Copy `constraints.txt` trước bước cài requirements | Low | Docker contract test + Compose config |
| `constraints.txt` | Minimum fixed cho cryptography/GitPython theo pip-audit | Medium | pip-audit resolver sạch + pip check |
| `requirements.txt` | Áp security constraint | Low–medium | pip-audit + fast suite |
| `requirements-dev.txt` | Khai báo pytest, coverage, pip-audit, Ruff riêng dev | Low | cài/run thật trong `.venv` |
| `ruff.toml` | Lint tập trung lỗi cú pháp/import/tên, không bulk restyle source cũ | Low | `ruff check .` pass |
| `cai_dat.bat` | Tạo `.venv`, ưu tiên Python 3.12 | Medium | static review; clean VM còn pending |
| `ChayTool.bat`, `GiamSat.bat`, `kiemtra.bat` | Ưu tiên `.venv`, fallback tương thích | Low | static review + UI/CLI smoke |
| `docker-compose.yml` | Gợi ý mount credential read-only, không bake | Low | review; Docker daemon pending |
| `.gitignore` | Ignore log/Ruff/coverage artifact mới | Low | `git status` |
| `watchlist.example.json` | Mẫu không chứa URL vận hành thật | Low | parser/package test |

## Test

| File | Thay đổi |
|---|---|
| `tests/conftest.py` | Fixture Engine truyền storage tạm trước mọi side effect |
| `tests/test_app.py` | AppTest dùng env data/output tạm |
| `tests/test_security_regressions.py` | Test path traversal, overwrite, formula, Sheets RAW, cancel, config, timeout/retry |
| `tests/test_packaging.py` | Test source package/Docker ignore/Docker constraint copy |
| `tests/test_core.py`, `tests/test_nhat_ky.py` | Bỏ import thừa để lint sạch |

Kết quả: fast suite tăng từ 248 pass lên 283 pass; không có test fail. Coverage module được đo
80%. Slow suite chưa kết luận vì timeout/cạnh tranh CPU với job thật.

## Tài liệu

Đã thêm/cập nhật:

- `README.md`.
- `docs/SYSTEM_OVERVIEW.md`.
- `docs/AUDIT_REPORT.md`.
- `docs/OPTIMIZATION_PLAN.md`.
- `docs/TEST_REPORT.md`.
- `docs/INSTALL_WINDOWS.md`.
- `docs/RUNBOOK.md`.
- `docs/CHANGELOG_OPTIMIZATION.md`.
- `HUONG_DAN.md` (quyền riêng tư, runtime, venv, 5 tab, overlap, cookie).

## Thay đổi có thể ảnh hưởng người dùng

1. Export CSV không còn ghi đè target; path trả về có thể có hậu tố `_2`, `_3`.
2. Cell CSV nguy hiểm có thêm apostrophe để spreadsheet coi là text; Sheets dùng RAW.
3. Config thủ công ngoài bounds bị từ chối/reset về default theo cơ chế startup hiện có.
4. Registry kho chỉ chấp nhận basename `.pklz` trực tiếp trong `data`; path tuyệt đối/legacy
   ngoài data không còn được phép.
5. Xóa kho/lịch sử trên UI cần tick xác nhận.
6. Launcher ưu tiên `.venv`; môi trường global cũ chỉ là fallback.
7. Source packager không ghi đè nếu thiếu `--overwrite` và không đưa `watchlist.json` runtime vào zip.
8. Request/tải yt-dlp có timeout socket 30 giây; `network_timeout_s` hợp lệ trong 5–300 giây.

## Không thay đổi

- Thuật toán `_merge`, overlap policy, thresholds, top-N, shifts mặc định.
- Schema CSV/Sheets 15/34 cột.
- Schema SQLite và dữ liệu thật.
- API YouTube/Google credential hoặc nội dung người dùng.
- `requirements-lock.txt` untracked ban đầu.
- `session.log` tracked ban đầu (không xóa/untrack trong audit).

## Vấn đề còn tồn tại

- Cancellation process tree/FFmpeg giữa chunk.
- Lock và temp workspace riêng cho scan tương tác.
- Timeout/backoff riêng cho Google API và hành vi mạng thật.
- Structured logging/redaction/size rotation.
- Pin/checksum supply-chain cho artifact tải.
- Docker build, Python 3.12 clean install, slow suite và API thật chưa nghiệm thu do môi trường.
