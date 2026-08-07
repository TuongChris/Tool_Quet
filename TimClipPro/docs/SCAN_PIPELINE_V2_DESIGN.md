# Scan Pipeline V2 — thiết kế dựa trên source thật

Ngày: 2026-08-07 · Nhánh: `main` · Base: `448b467`

> Mọi nhận định dưới đây kèm vị trí trong source. Giả thuyết nào không tái hiện được
> thì ghi rõ là **bác bỏ**, không giữ lại cho đẹp tài liệu.

---

## 1. Call graph hiện tại (đã đọc source, không phỏng đoán)

```
app.py:918  chay_nen("scan", eng.scan_many, links, "youtube")
  └─ threading.Thread(target)            [app.py:75-94]
       └─ Engine.scan_many(nguon, type, progress)      [engine.py:2115]
            for i, x in enumerate(nguon):              ← TUẦN TỰ
              └─ scan_youtube(x, p)                    [engine.py:2076]
                   ├─ youtube_info()                   ← metadata (mạng)
                   ├─ download_audio()                 ← tải (mạng)
                   └─ scan_media(luu_lich_su=False)    [engine.py:2024]
                        ├─ _cut_chunks()               [engine.py:1747]
                        │    └─ rmtree(self.chunk_dir) ← DÙNG CHUNG
                        ├─ _match_chunks()             [engine.py:1779]
                        │    ├─ data/_ds_khuc.txt      ← DÙNG CHUNG
                        │    └─ data/_raw_match.txt    ← DÙNG CHUNG
                        ├─ _merge() / _chon_loc()
                        └─ finally: rmtree(chunk_dir)
                   └─ save_job(kq)                     ← ghi SQLite NGAY sau mỗi video
            return ket                                 ← chỉ trả về khi XONG CẢ BATCH
  └─ app.py:210  if sheet_auto and not da_day_sheet:   ← đẩy Sheets SAU cả batch
       └─ day_len_sheets(results) → SheetsExporter.append()   [sheets.py:108]
            ├─ _mo_worksheet()      ← auth + open_by_key + worksheet MỖI LẦN
            └─ ws.get_all_values()  ← đọc TOÀN BỘ sheet chỉ để kiểm tra header
```

## 2. Giả thuyết trong đề bài — đối chiếu source

| # | Giả thuyết | Kết luận | Bằng chứng |
| --- | --- | --- | --- |
| 2.1 | Progress quét quá đơn giản | **Xác nhận** | `app.py:501-509` chỉ có `st.progress(job["pct"])` + `st.info(job["msg"])`; engine biết nhiều phase hơn nhưng gộp hết vào một chuỗi |
| 2.2 | Fingerprint có kiến trúc progress tốt hơn | **Xác nhận** | `fingerprint_progress.py` có contract + tracker + controller, queue bounded, đã có test |
| 2.3 | Watch đã xử lý result từng video | **Xác nhận một phần** | `watch.py:353-392` theo dõi `da_day_sheets` theo từng `ScanResult`, nhưng vẫn đẩy Sheets ở `watch.py:465` sau vòng lặp |
| 2.4 | Manual scan batch toàn bộ rồi mới push Sheets | **Xác nhận** | `scan_many` trả `list` ở cuối; `app.py:210` đẩy Sheets một lần sau batch |
| 2.5 | Temp workspace dùng chung | **Xác nhận — nghiêm trọng nhất** | `engine.py:1751` `rmtree(self.chunk_dir)`; `1781`/`1784` dùng `data/_ds_khuc.txt`, `data/_raw_match.txt` cố định |
| 2.6 | audfprint đã tự dùng nhiều CPU | **Xác nhận** | `_audfprint_cmd` truyền `--ncores so_nhan_nen_dung()` = 8 trên máy này |
| — | Result không được persist cho tới cuối batch | **BÁC BỎ** | `scan_youtube` gọi `save_job(kq)` ngay sau mỗi video (`engine.py:2063`, `2110`). Crash ở video 8 thì 1–7 **vẫn còn** trong SQLite. P0 #4 đã đạt sẵn. |

## 3. Vấn đề thật, xếp theo mức độ

| Hạng | Vấn đề | Hệ quả |
| --- | --- | --- |
| **P0-a** | Workspace dùng chung (`chunk_dir`, `_ds_khuc.txt`, `_raw_match.txt`) | Hai luồng quét đồng thời (GUI + Watch) sẽ **xoá chunk của nhau** → kết quả sai, không phải chỉ chậm. Đây là lỗi **đúng/sai**, không phải hiệu năng. |
| **P0-b** | `scan_many` trả list ở cuối | Không thể hiện kết quả sớm, không thể đẩy Sheets sớm |
| **P0-c** | Sheets chặn luồng | Sheets chậm/lỗi làm cả batch treo hoặc mất kết quả |
| **P0-d** | Progress một chiều | Không biết video nào, phase nào, còn bao lâu |
| P1 | `sheets.append()` auth + `get_all_values()` mỗi lần | Chậm và tốn quota; `get_all_values()` trên sheet lớn rất nặng |
| P2 | Không có download/match overlap | Mạng nhàn rỗi khi đang match |

## 4. Phương án đã cân nhắc

| Phương án | Ưu | Nhược | Quyết định |
| --- | --- | --- | --- |
| A. Giữ `scan_many`, chỉ thêm callback | Nhỏ nhất | Không giải quyết được persistence/Sheets sớm một cách tự nhiên; callback lồng nhau khó test | Loại |
| B. **`scan_iter()` generator + controller + sheet worker** | Streaming tự nhiên; `scan_many = list(scan_iter())` giữ nguyên contract; tái dùng đúng pattern `FingerprintJobController` đã được kiểm chứng | Thêm 2 module | **CHỌN** |
| C. Full async/await | Hợp thời | Cả project là synchronous + subprocess; đổi sang async là rewrite lớn, rủi ro cao, không giải quyết thêm vấn đề nào | Loại |
| D. SQLite outbox bền vững cho Sheets | Sống sót restart | Thêm schema + migration; hiện chưa có bằng chứng người dùng cần gửi Sheets sau khi tắt app | **Hoãn** — ghi rõ giới hạn, làm khi có nhu cầu thật |
| E. Concurrency download/matcher | Nhanh hơn | Chưa benchmark; audfprint đã dùng 8 nhân nên dễ oversubscribe | **Hoãn** — P2, cần benchmark trước |

**Nguyên tắc chọn:** ưu tiên sửa lỗi đúng/sai (P0-a) trước lỗi trải nghiệm, và tái dùng
abstraction đã có test thay vì phát minh cái mới.

## 5. Kiến trúc chọn

```
Streamlit (main thread)
   │  drain() / snapshot() / results()
   ▼
ScanJobController          [scan_jobs.py]   ← mô phỏng FingerprintJobController
   │  worker thread
   ▼
Engine.scan_iter(urls)     [engine.py]      ← generator, yield từng ScanResult
   │      ├─ workspace riêng mỗi video: data/scan_jobs/<uuid>/
   │      └─ save_job() ngay sau mỗi video   (đã có sẵn)
   ├──► controller.results  ← UI hiện ngay
   └──► SheetDeliveryWorker [sheet_delivery.py]  ← thread riêng, queue bounded
              ├─ retry có phân loại + backoff
              ├─ khoá idempotency chống ghi trùng
              └─ KHÔNG chặn scan worker
```

**Engine vẫn không import Streamlit.** Controller là tầng trung gian, giống hệt cách
`fingerprint_progress.py` đang làm.

## 6. Phạm vi vòng này

Làm: P0-a, P0-b, P0-c, P0-d + test cho từng phần.

Hoãn kèm lý do: outbox bền vững (D), concurrency (E), persistent matcher, tối ưu
`sheets.append()` session reuse — tất cả cần benchmark hoặc nhu cầu thật mới đáng độ phức tạp.

Không đụng: thuật toán matching, `_merge`, `_chon_loc`, ngưỡng, thứ tự cột báo cáo.
