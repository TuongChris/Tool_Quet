# CLAUDE_HANDOFF — Scan Pipeline V2

Ngày: 2026-08-07 · Nhánh `main`, base `448b467` · Chưa commit

---

## Quyết định kiến trúc

Chọn **phương án B** trong [SCAN_PIPELINE_V2_DESIGN.md](SCAN_PIPELINE_V2_DESIGN.md):
`scan_iter()` generator + `ScanJobController` + `SheetDeliveryWorker`, tái dùng đúng
pattern của `FingerprintJobController` (đã có test, đã được nghiệm thu ở vòng trước).

Loại bỏ: async rewrite (cả project là synchronous + subprocess).
Hoãn kèm lý do: SQLite outbox bền vững, concurrency download/matcher, persistent
matcher — đều cần benchmark hoặc nhu cầu thật mới đáng độ phức tạp.

## Giả thuyết bị bác bỏ

**"Result chỉ được persist ở cuối batch"** — sai. `scan_youtube` gọi `save_job(kq)` ngay
sau mỗi video (`engine.py:2063`, `2110`). Crash ở video 8 thì 1–7 vẫn còn trong SQLite.
P0 #4 đã đạt sẵn, không cần làm gì.

## Đã hoàn thành

| Phase | Nội dung | Test |
| --- | --- | --- |
| P0-a | Workspace riêng mỗi lượt quét (`Engine.scan_workspace`) | `test_scan_streaming.py` — 3 test, có test hai luồng song song |
| P0-b | `Engine.scan_iter()` streaming; `scan_many = list(scan_iter())` | 4 test |
| P0-c | `sheet_delivery.py` — worker riêng, retry phân loại, chống ghi trùng | `test_sheet_delivery.py` — 14 test |
| P0-d | `scan_jobs.py` — controller, phase, per-video state, ETA | 4 test |
| UI | Màn hình quét mới trong `app.py` | `test_app_scan_progress.py` — AppTest |
| P1 | `sheets.append()` dùng lại kết nối, bỏ `get_all_values()` | `test_sheets_session.py` — 15 test |

## Trạng thái kiểm thử

```
449 passed, 1 skipped, 5 deselected
ruff / compileall / pip check / git diff --check : sạch
```

## Bằng chứng "Sheets không chặn quét"

10 video, quét 0,3 s/video, Sheets 1,5 s/lần:

| | Quét xong | Sheets xong |
| --- | ---: | ---: |
| Đồng bộ (trước) | 18,01 s | 18,01 s |
| Worker (sau) | **3,00 s** | 15,31 s |

Người dùng thấy kết quả sớm hơn **15 giây (83 %)**. Sheets chạy tiếp nền.

## Việc còn lại (theo thứ tự ưu tiên)

1. **Smoke thật với 3–5 video YouTube** — chưa chạy vì hôm nay đã bị YouTube chặn
   chống bot sau ~2000 request của vòng ngày đăng. Chờ hết chặn rồi chạy.
2. ~~Session reuse cho `sheets.append()`~~ — **ĐÃ LÀM**. Cache kết nối cấp module,
   đọc ô A1 thay vì cả bảng. Đo: 50 → **14** lượt API, 22,54 s → **3,50 s**.
3. Outbox bền vững (sống sót restart) — hiện hàng đợi nằm trong RAM.
4. Benchmark concurrency download/matcher (P2) — chưa có bằng chứng nên chưa làm.

## Giới hạn đã biết

- Hàng đợi Sheets **không bền vững**: tắt app khi còn `pending` là mất phần chưa gửi.
  Kết quả quét vẫn còn trong SQLite nên đẩy lại thủ công được.
- `_cut_chunks`/`_match_chunks` giữ nhánh cũ khi gọi không kèm `workspace` để tương
  thích ngược; mọi call site trong repo đều đã dùng workspace riêng.
- Chưa đo pipeline concurrency; quét vẫn tuần tự từng video.


---

## Vòng sửa thread boundary + Arrow schema (2026-08-07, sau `6cad9d9`)

Hai lỗi do chính vòng Scan Pipeline V2 gây ra. Chi tiết:
[SCAN_THREADING_AND_STATE.md](SCAN_THREADING_AND_STATE.md).

| Root cause | Kết luận |
| --- | --- |
| `sheet_link` thiếu khởi tạo? | **KHÔNG** — đã có sẵn. Chỉ là triệu chứng. |
| Thật sự là gì? | Thread nền không có `ScriptRunContext` ⇒ `st.session_state` là proxy rỗng |
| `ArrowInvalid` | Bảng UI không có schema: cột `Đoạn` trộn `int`/`str` |

Đã sửa: `ScanLaunchConfig` snapshot, `tao_sheets_exporter()` thuần,
`SheetDelivery.sheet_link`, `sender(sheet_link, header, rows)`, `scan_ui.py` với dtype
tường minh.

**470 passed, 1 skipped.** Streamlit thật: terminal sạch.

### Còn lại
1. Smoke với video YouTube thật (chưa chạy — chờ hết chặn chống bot).
2. Outbox bền vững cho hàng đợi Sheets (hiện trong RAM).
3. Benchmark concurrency download/matcher — chưa có bằng chứng nên chưa làm.


---

## Vòng chọn kết quả đại diện (2026-08-07, sau `8cb2597`)

Chi tiết: [MATCH_SELECTION_ARCHITECTURE.md](MATCH_SELECTION_ARCHITECTURE.md).

**Ngữ nghĩa `top_n`** = số ĐOẠN vi phạm được xuất, không phải số video gốc. Giữ nguyên.

**Vấn đề**: với `top_n=1`, `_chon_loc` tạo một vùng duy nhất nên Top-1 thuần
`max(hashes)`; vị trí không có vai trò gì.

**Đã làm**: `chon_dai_dien()` + `chi_phi_kiem_tra()` + `Config.dung_sai_gan_bang=0.03`.
Chất lượng quyết định trước; dễ kiểm tra chỉ phá hoà trong nhóm ngang bằng (≥97% cả
hash lẫn thời lượng).

**Đo trên 200 job thật**: 94% giữ nguyên, 6% đổi. **496 passed, 1 skipped.**

### Còn lại
1. ~~Đổi khoá chất lượng sang `ty_le`~~ — **ĐÃ LÀM** kèm sàn bằng chứng 0,70.
   Đo 283 job: 46 % Top-1 đổi, 28 ca đánh đổi nặng bị sàn chặn. **504 passed.**
2. Smoke Scan Pipeline V2 với video YouTube thật (chưa chạy).
3. Outbox bền vững cho hàng đợi Sheets.

### Dữ liệu ngày đăng — ĐÃ XONG cả ba kho
| Kho | Clip | Đã sửa | Lỗi |
| --- | ---: | ---: | ---: |
| duncanyounot | 139 | 138 | 0 |
| SML | 744 | 377 | 0 |
| Cory | 1717 | 1124 | 0 |

Audit sau sửa cả ba kho: `co_provenance` = `co_epoch_luu_san` = tổng số clip,
`se_doi` = 0, `thieu_ngay` = 0.
