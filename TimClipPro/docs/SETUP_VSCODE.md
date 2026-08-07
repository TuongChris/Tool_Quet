# Setup VS Code cho quy trình Claude (Planner) + Codex (Builder)

## 1. Cài đặt (một lần, ~10 phút)

1. Mở VS Code → **File → Open Folder** → chọn thư mục `TimClipPro` (chọn cả thư mục).
2. VS Code sẽ hỏi *"Do you want to install the recommended extensions?"* → bấm **Install**.
   (Danh sách nằm sẵn trong `.vscode/extensions.json`: Python, Pylance, Copilot, Copilot Chat, Ruff.)
3. `Ctrl + Shift + P` → `Python: Select Interpreter` → chọn Python 3.1x.
4. Cài thư viện test: mở terminal (`` Ctrl + ` ``) → `pip install pytest`
5. Mở tab **Testing** (biểu tượng bình thí nghiệm bên trái) → thấy 38 test → bấm ▶ chạy thử.

> Quan trọng: **mở đúng thư mục gốc dự án**, không mở file lẻ. Copilot chỉ đọc được
> `.github/copilot-instructions.md` khi thư mục gốc được mở làm workspace.

## 2. Ba file "nguồn sự thật" — ai đọc file nào

| File | Ai đọc | Nội dung |
|---|---|---|
| `.github/copilot-instructions.md` | **Codex / Copilot** (tự động) | Quy tắc ngắn gọn, các bẫy đã gây lỗi thật |
| `CLAUDE.md` | **Claude** (tự động) | Kiến trúc, nghiệp vụ, số liệu đã hiệu chỉnh, quy trình lập kế hoạch |
| `docs/PROMPT_CONTRACT.md` | Bạn + Claude | Khuôn mẫu spec chuẩn |

VS Code tự nạp `copilot-instructions.md` vào mọi câu hỏi Copilot Chat — bạn không phải
dán lại ngữ cảnh mỗi lần. Kiểm tra: hỏi Copilot Chat *"Dự án này cấm làm gì với file .pklz?"*
Nếu nó trả lời đúng là "không gọi os.remove trực tiếp, dùng `_xoa_an_toan()`" → context đã hoạt động.

## 3. Vòng lặp làm việc hằng ngày

```
   [1] Bạn mô tả tính năng cho Claude
              ↓
   [2] Claude xuất docs/EXECUTION_PLAN.md  (4–6 task nguyên tử)
              ↓
   [3] Copy TASK 1 → dán vào Copilot Chat (chế độ Agent) → Codex viết code
              ↓
   [4] Chạy kiemtra.bat
              ↓
      Xanh? → làm TASK tiếp theo
      Đỏ?  → copy nguyên màn hình → dán cho Claude → nhận "FIX cho TASK n" → quay [3]
```

**Mẹo tiết kiệm công sức:** trong Copilot Chat chọn chế độ **Agent** (không phải Ask),
rồi dán nguyên khối TASK. Agent tự mở file, sửa, và chạy test được.

## 4. Lệnh cần nhớ

| Việc | Lệnh |
|---|---|
| Kiểm tra toàn bộ (dùng cho vòng lặp) | `kiemtra.bat` |
| Chỉ chạy test nhanh | `python -m pytest -q` |
| Chạy cả test nặng (có xử lý audio) | `python -m pytest -m slow` |
| Chạy 1 file test | `python -m pytest tests/test_selection.py -q` |
| Chạy tool | `ChayTool.bat` |

## 5. Dùng hết token Codex một cách có ích

Xếp theo thứ tự giá trị giảm dần — làm từ trên xuống:

1. **Chạy hết `docs/EXECUTION_PLAN.md`** (5 task đã viết sẵn) — tính năng xuất hồ sơ khiếu nại.
2. **Nhờ Codex viết thêm test** cho `engine.py`: bảo nó đọc `tests/test_core.py` làm mẫu rồi
   phủ thêm `_merge()`, `_cut_chunks()`, `clip_meta()`. Test là thứ càng nhiều càng tốt và
   gần như không có rủi ro làm hỏng gì.
3. **Nhờ Codex viết docstring + type hint** còn thiếu cho các hàm trong `channel.py`, `sheets.py`.
4. **Nhờ Codex refactor `app.py`**: tách mỗi tab thành một hàm `ve_tab_dong_bo()`,
   `ve_tab_kho()`... File đang dài, tách ra sẽ dễ bảo trì. Có test giao diện bảo vệ nên an toàn.
5. **Các tính năng trong danh sách cuối `CLAUDE.md`** — nhờ Claude lập plan trước, rồi giao Codex.

**Đừng** giao Codex những việc này: sửa `audfprint-master/` (thư viện ngoài), đổi ngưỡng
đã hiệu chỉnh bằng thực nghiệm, hay "tối ưu lại toàn bộ dự án" (prompt quá rộng, dễ ảo giác).

## 6. Kiểm tra bộ khung đã chạy đúng

```bat
kiemtra.bat
```
Kết quả mong đợi: `[OK] import` → `38 passed` → `[OK] Giao dien sach`.
Nếu cả ba đều xanh, vòng lặp phản hồi đã sẵn sàng và Codex có thể tự kiểm chứng.
