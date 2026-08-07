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

---

## Vòng điều tra zero-match + Fast Top-1 (2026-08-07, sau `2bbb7f9`)

**Vấn đề báo cáo**: 11 video quét xong báo 0 đoạn, người dùng tin chắc chúng chứa reup.

**Kết luận**: cả 11 đều là **âm tính đúng**. Chúng là video parody lồng tiếng lại; chỉ
nhạc hiệu dùng chung của kênh khớp được (phủ vân tay 0,5–0,9%, đoạn khớp ~10 giây, cùng
một mốc thời gian khớp ~100 clip gốc khác nhau). Đối chứng dương tính cùng kho: video
`n4Ca9SmTfi0` cho đoạn khớp **786,8 giây / 15.173 hash**.

**Giả thuyết bị bác bỏ**: "`min_hash_floor=1000` cao hơn tổng hash của clip gốc". Kho
SML đang dùng có clip ít hash nhất là **6.239**; không clip nào dưới 1000. Bẫy toán học
chỉ tồn tại ở kho Cory với quy mô 3/1717 clip (0,2%).

**Lỗi thật đã sửa**:
1. `--sortbytime` khiến `--max-matches` cắt cụt theo *align time* thay vì theo *độ mạnh*
   — đo được mất 207 dòng khớp trên một khúc, và **mọi khúc của cả 11 video đều chạm
   trần 200**. Đã bỏ `--sortbytime`.
2. Ngưỡng tuyệt đối một mình loại oan clip gốc ngắn. Đã thêm bậc chấp nhận thứ hai
   (phủ ≥60% + dài ≥20s + mật độ ≥3 hash/s). Thuần **thêm**, không bớt.
3. Kết quả 0 đoạn không nói được mất ở tầng nào. Đã thêm `chan_doan_quet.py` với 6 mã
   giai đoạn + ảnh chụp ứng viên mạnh nhất bị loại + lưu JSON tại `data\chan_doan\`.
4. GUI khuyên "hạ ngưỡng xuống 60% kết quả mạnh nhất" — lời khuyên này tạo dương tính
   giả (job 364: một match 126 hash/10 giây đã lọt vào báo cáo theo đúng cách đó). Đã
   thay bằng bảng chẩn đoán phễu.

**Fast Top-1**: `top_n=1` và video từ 3 khúc trở lên thì quét khúc đầu trước; vượt cổng
(≥5.000 hash **và** ≥60 giây) thì dừng, không thì quét nốt phần còn lại trong một lần
gọi và ghép kết quả thô. Tối đa 2 lần nạp kho. Xem [FAST_TOP1_SCAN.md](FAST_TOP1_SCAN.md).

### Còn lại
1. **Điểm mù đổi tốc độ** — đo được: lệch 0,5% làm đoạn khớp 263 giây vỡ còn 21 giây;
   lệch 4% mất trắng. Nén lại/đổi âm lượng/lọc tần số thì vô hại. Bịt cần so khớp đa
   tốc độ (chi phí nhân lên) — cần người dùng quyết định có đáng không.
2. Cân nhắc siết bậc A bằng điều kiện mật độ (ca "phủ thấp, hash cao"). Chưa làm vì đó
   là **bớt** kết quả người dùng đang nhận, phải hỏi trước.
3. Trần `--max-matches 200` vẫn còn; chẩn đoán nay cảnh báo khi chạm trần.

---

## Vòng bù đa tốc độ (2026-08-07, tiếp theo vòng trên)

**Yêu cầu**: bịt điểm mù đổi tốc độ đã đo được (lệch 0,5% mất 93% bằng chứng).

**Quyết định**: KHÔNG quét mù nhiều tốc độ. Lưới bước 1% để lại sai số tồn dư 0,5% —
mà 0,5% đã đủ phá bằng chứng, nên muốn mạnh phải trúng tới ~0,1%, tức hàng chục lượt.

Thay vào đó khai thác quan hệ toán học: video phát ở tốc độ `r` thì
`align = t_video · (1 − r)`, tức align **trôi tuyến tính**, độ dốc chính là `(1 − r)`.
Hồi quy độ dốc trên chính output lượt quét thường → ra tốc độ, **tốn 0 giây so khớp**,
sai số đo được ≤0,05%.

**Chi tiết kỹ thuật quan trọng**:
1. Dùng **Theil–Sen** (trung vị độ dốc từng cặp) chứ không bình phương tối thiểu —
   nhạc hiệu dùng chung tạo mảnh align ngẫu nhiên trong cùng clip gốc và kéo lệch
   bình phương tối thiểu. Đo: LSQ cho R²=0,916 lệch 0,00135 (thu 38,5% vân tay);
   Theil–Sen cho 1,03000 đúng tuyệt đối (thu 56,4%).
2. **Vòng tinh chỉnh lặp** là thứ cứu được ca đổi cao độ: lưới thô bước 2% kéo về
   trong ~1% → sinh đủ mảnh → đọc độ trôi → trúng 1,02970 → thu 85,3%. Mọi mốc đã quy
   về trục thời gian gốc nên độ dốc luôn cho **tổng** tỉ lệ, không phải phần dư.
3. **Quy đổi mốc thời gian**: hệ số mã trong tên khúc (`chunk_0003420_k097087.wav`),
   `t_video = offset + t_trong_khúc × k`. Tên không có hậu tố = k 1,0 (tương thích ngược).
4. Chỉ chạy khi lượt quét thường không ra ứng viên đạt chuẩn → đường đi bình thường
   không tốn thêm giây nào.

**Vùng phủ đo được**: đổi tốc độ giữ cao độ ±6% (đọc độ trôi); đổi cao độ ±5% (lưới +
tinh chỉnh). Ngoài đó thêm mức vào `luoi_tempo`/`luoi_resample`.

### Còn lại
1. Đổi tốc độ giữ cao độ vượt ±6% và đổi cao độ vượt ±5% chưa phủ mặc định — mỗi mức
   thêm tốn đúng một lượt so khớp, bật khi gặp thực tế.
2. Cân nhắc siết bậc A bằng điều kiện mật độ (vẫn treo, phải hỏi trước).
3. Trần `--max-matches 200` vẫn còn; chẩn đoán có cảnh báo khi chạm.
