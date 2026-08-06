# Hợp đồng giao tiếp Claude → Codex

Mọi spec do Claude (Kiến trúc sư) sinh ra cho Codex (Lập trình viên) phải theo đúng khuôn dưới đây.
Copy nguyên khối, dán vào Copilot Chat / Codex, không thêm văn xuôi.

## Khuôn mẫu

````markdown
## TASK <số>: <tên ngắn, 1 dòng>

### Target File
`<đường/dẫn/file.py>` — <TẠO MỚI | SỬA hàm `ten_ham` | THÊM method vào class `X`>

### Context & Tech Stack
- Python 3.10+, chỉ dùng thư viện đã có trong `requirements.txt`
- Đọc trước: `<file liên quan>` (dòng ~N, class/hàm `<tên>`)
- Ràng buộc dự án: xem `.github/copilot-instructions.md`

### Exact Input / Output
```python
@dataclass
class TenKieu:
    truong_a: str
    truong_b: int = 0

def ten_ham(tham_so: KieuVao, tuy_chon: int = 5) -> KieuRa:
    """<một câu mô tả>"""
```
- Input: <mô tả từng tham số, đơn vị, khoảng giá trị hợp lệ>
- Output: <mô tả chính xác cấu trúc trả về>

### Step-by-step Implementation
1. <bước 1, cụ thể tới mức không phải đoán>
2. <bước 2>
3. <bước 3>

### Edge Cases & Error Handling
| Tình huống | Hành vi bắt buộc |
|---|---|
| <input rỗng> | <trả về [] chứ không ném lỗi> |
| <file không tồn tại> | <ném RuntimeError kèm đường dẫn> |

### Constraints
- KHÔNG <điều cấm 1>
- KHÔNG <điều cấm 2>

### Unit Test Criteria
Tạo/bổ sung `tests/<test_x>.py`, phải pass `python -m pytest -q`:
```python
def test_<tên>():
    assert ten_ham(<đầu vào>) == <mong đợi>
```

### Definition of Done
- [ ] `python -m pytest -q` xanh toàn bộ
- [ ] `python -c "import <module>"` không lỗi
- [ ] <tiêu chí riêng của task>
````

## Quy tắc nguyên tử

| Được | Không được |
|---|---|
| 1 file hoặc 1 hàm mỗi prompt | Gộp nhiều file vào một prompt |
| Nêu rõ type của mọi tham số | Để Codex tự đoán kiểu dữ liệu |
| Liệt kê edge case dạng bảng | Viết "xử lý lỗi hợp lý" |
| Đưa sẵn test case cụ thể | Viết "nhớ thêm test" |
| Nêu lý do khi cấm điều gì | Cấm khơi khơi không giải thích |

## Vòng lặp sửa lỗi

Khi code Codex viết bị lỗi, **đừng mô tả lỗi bằng lời**. Chạy `kiemtra.bat`, copy nguyên văn màn hình, dán vào Claude kèm đúng một dòng:

> Task <số> lỗi. Log dưới đây. Phân tích nguyên nhân gốc và cho tôi Fix Prompt ngắn cho Codex.

Claude trả về khối `## FIX cho TASK <số>` theo cùng khuôn trên, chỉ chứa phần thay đổi.
