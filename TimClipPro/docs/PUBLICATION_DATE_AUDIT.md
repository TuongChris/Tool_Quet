# Audit ngày đăng — hiện trạng metadata cũ

Ngày: 2026-08-07 · Công cụ: [`kiem_ngay_dang.py`](../kiem_ngay_dang.py)

---

## 1. Hiện trạng ba kho (chạy chỉ đọc, không ghi gì)

```powershell
& ".\.venv-claude\Scripts\python.exe" kiem_ngay_dang.py --kho "D:\ClipGocCory" --audit
```

| Kho | Tổng clip | Có nguồn gốc ngày | Chỉ có `upload_date` | Có epoch lưu sẵn | Thiếu ngày | Mơ hồ |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Cory | 1717 | 0 | **1717** | 0 | 0 | 0 |
| SML | 744 | 0 | **744** | 0 | 0 | 0 |
| duncanyounot | 139 | 0 | **139** | 0 | 0 | 0 |
| **Tổng** | **2600** | **0** | **2600** | **0** | **0** | **0** |

`se_doi = 0` ở cả ba kho **không có nghĩa là dữ liệu đúng**. Nó chỉ nói: với dữ liệu
đã lưu (chỉ chuỗi `YYYYMMDD`, không có giờ), resolver không thể suy ra ngày nào khác.
Muốn biết đúng/sai phải hỏi lại YouTube.

---

## 2. Mẫu kiểm chứng qua mạng — 25 clip kho Cory (dry-run, không ghi)

```powershell
& ".\.venv-claude\Scripts\python.exe" kiem_ngay_dang.py `
    --kho "D:\ClipGocCory" --repair-network --limit 25
```

| Chỉ số | Số lượng |
| --- | ---: |
| Đã kiểm | 25 |
| Không đổi | **3** |
| Sẽ đổi (lệch đúng 1 ngày) | **22** |
| Bỏ qua | 0 |
| Thất bại | 0 |
| Đã ghi | **không** (dry-run) |

Toàn bộ 22 record đổi đều có `source = timestamp` và lệch **đúng +1 ngày**:

```
19/12/2025 -> 20/12/2025  [timestamp]  At Dead of Night SPECIAL FINALE [i8rHcYHCi0Q]
15/12/2025 -> 16/12/2025  [timestamp]  yes. i literally beat the game. in this video
08/12/2025 -> 09/12/2025  [timestamp]  i did it again [3_ybkhzgKJg]
01/03/2022 -> 02/03/2022  [timestamp]  SIFU got me feeling like a TRASH GAMER [caE2GwHnIMM]
05/10/2021 -> 06/10/2021  [timestamp]  SQUID GAME THE GAME [GLhrnvylj04]
...
```

Suy ra tỉ lệ ước tính cho kho Cory: khoảng **88 %** clip đang lệch một ngày. Con số
này khớp với đặc điểm kênh CoryxKenshin đăng vào buổi tối giờ Mỹ = đêm giờ UTC.

---

## 3. Vì sao không sửa offline được

Entry cũ chỉ có:

```json
{"id": "...", "title": "...", "upload_date": "20250620", "duration": 955.0}
```

`20250620` là ngày theo lịch UTC. Không có giờ ⇒ không biết video phát hành lúc
09:00 UTC (giờ VN cùng ngày) hay 20:00 UTC (giờ VN hôm sau). Hai trường hợp cho hai
kết quả khác nhau và **không có cách nào phân biệt** từ dữ liệu đã lưu.

`--repair-offline` vì thế chỉ sửa entry đã lưu sẵn `timestamp`/`release_timestamp`.
Hiện tại cả ba kho đều có 0 entry như vậy, nên repair offline sẽ không đổi ngày nào
— nó chỉ đánh dấu nguồn gốc `upload_date` (độ tin cậy thấp).

> Dấu nguồn gốc độ tin cậy thấp **không** chặn `--repair-network` chạy sau. Điều kiện
> bỏ qua dựa trên *độ tin cậy* (chỉ nguồn suy từ epoch mới đủ chắc), không dựa trên
> việc có dấu hay chưa. Có regression test cho đúng cái bẫy này:
> `test_dau_provenance_do_tin_cay_thap_khong_chan_repair_network`.

---

## 4. Cách sửa dữ liệu thật

Luôn chạy dry-run trước, xem danh sách sẽ đổi, rồi mới `--apply`.

```powershell
# 1. Xem hiện trạng, không ghi gì
& ".\.venv-claude\Scripts\python.exe" kiem_ngay_dang.py --kho "D:\ClipGocCory" --audit

# 2. Thử trên mẫu nhỏ, xem trước thay đổi, vẫn không ghi
& ".\.venv-claude\Scripts\python.exe" kiem_ngay_dang.py `
    --kho "D:\ClipGocCory" --repair-network --limit 25

# 3. Ghi thật (tự sao lưu clips_meta.json trước khi ghi)
& ".\.venv-claude\Scripts\python.exe" kiem_ngay_dang.py `
    --kho "D:\ClipGocCory" --repair-network --apply
```

Bước 3 gọi mạng một lần cho mỗi clip chưa có nguồn epoch. Kho Cory 1717 clip mất
khoảng **30 phút** (đo được ~1 clip/giây ở lượt `vameta` trước).

Đảm bảo của công cụ:

- Mặc định chỉ đọc; thiếu `--apply` là dry-run, tuyệt đối không ghi.
- Sao lưu `clips_meta.json.truoc_ngay_dang_<timestamp>` trước khi ghi.
- Ghi nguyên tử qua `luu_tru.ghi_json_an_toan`.
- Một video bị xoá/riêng tư chỉ tính là thất bại, không làm hỏng cả kho.
- `--limit N` để chạy từng phần, chạy lại được (resume tự nhiên vì entry đã có epoch
  sẽ bị bỏ qua).
- **Không** đụng tới database vân tay, **không** đổi tên file, **không** tải media.

---

## 5. Kết quả chạy thật — 2026-08-07

| Kho | Clip | Đã sửa | Không đổi | Thất bại | Đã ghi |
| --- | ---: | ---: | ---: | ---: | --- |
| duncanyounot | 139 | **138** | 1 | 0 | **có** |
| SML | 744 | — | — | 324+ | **không** |
| Cory | 1717 | — | — | — | **không** (chưa chạy) |

### YouTube chặn chống bot giữa chừng

Sau khoảng 139 + vài trăm request liên tiếp (cộng dồn với ~1900 request của lượt
`vameta` cùng ngày), YouTube trả:

```
ERROR: [youtube] KWh0-WmsMyk: Sign in to confirm you're not a bot.
```

Lượt SML bị dừng thủ công. **Không có hư hại**: `--apply` chỉ ghi ở CUỐI vòng lặp,
và fetch lỗi thì entry bị bỏ qua nguyên vẹn. Đã xác minh `clips_meta.json` của SML
và Cory giữ nguyên mtime.

### Đã bổ sung để chạy lại an toàn

| Cải tiến | Tác dụng |
| --- | --- |
| `--nghi` (mặc định **1.5** giây) | Giãn nhịp gọi mạng, tránh bị chặn |
| Dừng sớm sau 25 lỗi **liên tiếp** | Bị chặn thì mọi request sau đều hỏng; chạy tiếp chỉ tốn thời gian và làm bị chặn nặng hơn |
| In tiến độ mỗi 25 clip | Lượt chạy 30 phút không còn im lặng |
| Resume tự nhiên | Entry đã có nguồn epoch bị bỏ qua ⇒ chạy lại là tiếp tục từ chỗ dở |

Regression test: `test_dung_som_khi_bi_chan_lien_tiep_va_khong_ghi_gi`,
`test_nghi_giua_cac_lan_goi_mang`.

### Chạy tiếp

Chờ **30–60 phút** cho hết chặn, rồi chạy lại đúng lệnh cũ. Với `--nghi 1.5`,
kho SML mất ~19 phút, kho Cory ~43 phút.

```powershell
& ".\.venv-claude\Scripts\python.exe" kiem_ngay_dang.py --kho "D:\ClipGocSML"  --repair-network --apply
& ".\.venv-claude\Scripts\python.exe" kiem_ngay_dang.py --kho "D:\ClipGocCory" --repair-network --apply
```

Muốn chắc hơn thì chia nhỏ: thêm `--limit 200` và chạy nhiều lượt.

---

## 6. Trạng thái sau vòng này

| Hạng mục | Trạng thái |
| --- | --- |
| Fingerprint DB | **không sửa** |
| `clips_meta.json` duncanyounot | **đã sửa** (138/139), có backup |
| `clips_meta.json` SML, Cory | **không sửa** |
| Snapshot metadata | **không sửa** |
| Backup | `clips_meta.json.truoc_ngay_dang_20260807_092956` (duncanyounot) |

Audit lại duncanyounot sau khi sửa: `co_provenance=139`, `co_epoch_luu_san=139`,
`se_doi=0`, `thieu_ngay=0`. Từ nay kho này còn sửa được **offline** vì đã lưu epoch.
