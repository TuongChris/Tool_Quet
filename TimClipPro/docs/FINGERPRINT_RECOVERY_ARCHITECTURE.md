# KIẾN TRÚC WATCHDOG & KHẢ NĂNG PHỤC HỒI KHI DỰNG KHO VÂN TAY

> Viết sau sự cố 2026-09-07 (xem [JOEBARTOLOZZI_FAILURE_FORENSICS.md](JOEBARTOLOZZI_FAILURE_FORENSICS.md)).
> Tài liệu này giải thích **cái gì đã đổi, cái gì cố ý KHÔNG đổi, và vì sao**.

---

## 1. Vấn đề: một hằng số gánh hai vai trò trái ngược

`CHO_WORKER_S = 1800.0` từng vừa là **ngân sách hoàn thành** vừa là **bộ phát hiện treo**
duy nhất trong toàn bộ đường dựng kho. Hai vai trò này muốn hai giá trị ngược nhau:

* muốn worker khoẻ không bị giết oan → phải ĐỦ LỚN so với tổng phần việc
* muốn phát hiện treo thật sớm → phải ĐỦ NHỎ

Không con số nào thoả cả hai. Đó là **lỗi phân loại, không phải lỗi hiệu chỉnh** — và vì
vậy nâng 1800 → 3600 không phải cách sửa.

### 1.1 Vì sao nó là ngân sách chứ không phải watchdog

```
                     TRƯỚC
worker ──[tiến độ]──> os.write(stdout) ──> tiến trình Streamlit   ← người dùng thấy
   │
   └────[hoàn tất]──> Pipe, ĐÚNG MỘT message, phát ở CUỐI
                        └──> rx[core].poll(1800)                  ← watchdog nhìn ở đây
```

Tiến trình audfprint cha **không đọc stdout của chính nó**, nên nó mù hoàn toàn với tiến
độ. Kênh duy nhất nó quan sát chỉ có tin ở phút cuối. `poll(1800)` vì thế có nghĩa:
*"worker phải xong toàn bộ phần việc trong 1800 giây"*, tỷ lệ thuận với `số_clip / ncores`.

Ngưỡng vỡ ≈ `ncores × 1800 / giây_mỗi_clip`. Với nhịp đo được 12,8 s/clip và 8 nhân:
**≈ 1125 clip**. Kho 537 và 149 clip trước đó nằm dưới ngưỡng nên chưa bao giờ lộ.

---

## 2. Cách sửa: tách hai vai trò bằng một bộ đếm dùng chung

```
                      SAU
worker ──[tiến độ]──> os.write(stdout) ──> tiến trình Streamlit   (giữ nguyên)
   │
   ├──[nhịp sống]───> multiprocessing.Value("i")  ← MỚI: +1 mỗi file HOÀN TẤT
   │                    └──> cha đọc mỗi 0,5 s, chỉ báo lỗi khi ĐỨNG YÊN 1800 s
   │
   └──[hoàn tất]────> Pipe, một message ở cuối    (giữ nguyên)
```

`CHO_WORKER_S` **giữ nguyên tên và giá trị 1800.0** — chỉ **ý nghĩa** đổi:
từ *"ngân sách cho tổng phần việc"* thành *"thời gian im lặng tối đa giữa hai file"*.

Giữ nguyên tên là có chủ đích: hai test hiện có dùng
`monkeypatch.setattr(runner, "CHO_WORKER_S", 20.0)` vẫn chạy và vẫn có tác dụng chặn.

### 2.1 Bốn yêu cầu, và cách từng cái được thoả

| Yêu cầu | Cách thoả |
|---|---|
| Worker khoẻ cần 2017 s **không bị giết** | Hạn chót tính từ nhịp cuối, không từ lúc bắt đầu. Clip lâu nhất đo được 68,4 s ⇒ biên 26 lần |
| Worker kẹt thật **vẫn bị bắt** | Ngừng tick ⇒ trip sau 1800 s im lặng |
| Worker chết **phát hiện ngay** | Không đổi. Cha đã `ghi.close()`; worker chết ⇒ pipe gãy ⇒ được xếp là "ready" ⇒ `recv()` ném `EOFError` dưới 0,1 s |
| Windows `spawn` | `Value` đi qua `args=` như mọi tham số khác; target vẫn là hàm cấp module |

### 2.2 Một chi tiết dễ làm sai: quét TỪNG core, không quét tất cả

Cách chia file là round-robin `filelists[ix % ncores]`. Khi `ncores > số file`, một số
worker nhận **danh sách RỖNG** và **không bao giờ tick**.

Nếu cha quét hạn chót cho *tất cả* core mỗi vòng, đúng những worker rỗng đó bị giết oan.
Quét theo từng core thì chúng an toàn tự nhiên: kết quả của chúng đã nằm sẵn trong pipe
nên `poll()` trả `True` ngay vòng đầu và hạn chót không bao giờ được xét tới.

Bố cục này **có thật** trong bộ test: `tests/test_audfprint_progress_integration.py`
chạy `ncores=8` với 6 clip. Test `test_worker_khong_co_file_nao_thi_khong_bi_giet_oan`
khoá lại đúng cái bẫy này.

### 2.3 Vì sao dùng `multiprocessing.Value` chứ không phải pipe hay file

Hai phương án hiển nhiên hơn đều đã được đo và **đều hỏng**:

| Phương án | Vì sao loại |
|---|---|
| Gửi ping qua chính pipe | `Pipe(False)` trên Windows giữ **đúng 8192 byte** chưa đọc. Ping kèm tên file pickle ra ~79 byte ⇒ đầy ở ~103 message. Sản xuất giao mỗi worker 148 file ⇒ **mọi worker sẽ nghẽn ở `send()`**. Không có `send` non-blocking. |
| File nhịp tim, cha đọc mtime | Con giữ handle mở trong thư mục mà `finally` gọi `terminate()` **không join** rồi `shutil.rmtree(ignore_errors=True)` ⇒ **rò thư mục tạm 4/4 lần đo**. Ngoài ra `st_mtime` là đồng hồ tường: một lần chỉnh NTP là cả 8 worker khoẻ cùng bị đánh dấu kẹt. |

`Value` không có cả hai khuyết điểm: O(1) byte nên **không thể** nghẽn; không tạo file
nên không có lớp lỗi rò; cha đo bằng `time.monotonic()` nên không dính đồng hồ tường; và
nó mang một **con số đếm**, nhờ đó thông báo lỗi nói được *"đã xong 130 file, không tiến
thêm"* — đúng dữ kiện mà một thiết kế chỉ có dấu thời gian không bao giờ nêu được.

`lock=False` là cố ý: một người ghi, một người đọc, `int32` căn thẳng. Cha chỉ so sánh
**thay đổi**, không phụ thuộc giá trị tuyệt đối, nên mất một nhịp cũng vô hại.

---

## 3. Khả năng phục hồi: cái ĐÃ CÓ và cái CỐ Ý CHƯA LÀM

### 3.1 Đã có sẵn — mode `add` là đường resume

`engine.py:1788-1799` đọc `db_clips()` lọc `so_hash > 0`, so khớp bằng
`os.path.normcase(os.path.abspath(...))`, và **chỉ fingerprint phần thiếu**.
Không thiếu gì thì trả về sớm *"Mọi clip đều đã có vân tay"*.

`engine.py:1826-1836` sao chép kho hiện có sang staging trước khi thêm, và commit bằng
`os.replace` — nên **một lần dựng thất bại không bao giờ phá kho hợp lệ đang có**.

Nghĩa là hôm nay đã có:

```bash
py -3 cli.py themclip "D:\KhoJoeBartolozzi" --ncores 0
```

→ bỏ qua mọi clip đã có, chỉ thêm clip mới. Chạy hai lần thì lần hai thêm **0 clip**.

> ⚠️ `cli.py:126` để `--ncores` mặc định **1**, ghi đè cấu hình đã lưu. **Luôn truyền
> `--ncores 0`** (0 = tự dò, ra 8 trên máy này) nếu không muốn chạy đơn nhân.

### 3.2 Cố ý CHƯA làm — commit theo lô (checkpoint)

Đã cân nhắc nghiêm túc và **hoãn lại**, không phải vì lười mà vì bốn rủi ro đo được:

| Rủi ro | Bằng chứng |
|---|---|
| **Kho dở dang không phân biệt được với kho đủ** | `khos.json` chỉ có `{ten, thu_muc, db, shifts}`, không có trường độ phủ; `list_khos()` chỉ phơi `co_van_tay = os.path.exists(db)`. Dựng chết ở lô 3/4 để lại một file **trông y hệt kho hoàn chỉnh**. Hôm nay tín hiệu rõ ràng: **không có .pklz nào cả** |
| **Resume làm hỏng `names`** | `hash_table.py:298` là `self.names += ht.names`, **không khử trùng**. Skip set lọc `so_hash > 0` nên clip 0 hash bị xếp lại mỗi lần resume và cộng thêm một mục trùng |
| **Huỷ bắt đầu nói dối** | `engine.py:1704-1719` hardcode `"thanh_cong": 0` và câu *"Kho vân tay trước job vẫn nguyên"* — cả hai thành sai ngay khi một lô đã commit. Test huỷ hiện dùng 1-2 clip nên vẫn xanh ⇒ **yên tâm giả** |
| **Giá thường trực 15–59% thời gian** | Chi phí thật **không phải** bản sao staging (đo ~0,2 s cho kho 128 MB) mà là `gzip.open(name,'wb')` compresslevel 9 trên bảng cố định 400 MiB trong `hash_table.py:189` — ~109 s mỗi lô ở kho 104 MB, **nằm trong mã vendored mà CLAUDE.md cấm sửa** |

Quan trọng hơn cả: **bản vá watchdog LOẠI BỎ nguyên nhân mất mát, còn commit theo lô chỉ
GIỚI HẠN nó.** Tiêu cùng một cửa sổ thay đổi cho thứ chặn trên một tổn thất mà ta sắp làm
cho không thể xảy ra nữa là đánh đổi sai.

Và `CLAUDE.md` xếp *"SAI MÀ KHÔNG CÓ DẤU HIỆU NÀO"* (mục 13) là loại hỏng tệ nhất, còn
mục 14 là trọn một ngày mất vì đúng kiểu nhập nhằng đó. Ship "độ phủ một phần im lặng"
dưới danh nghĩa tính năng an toàn là **tăng** rủi ro ròng.

### 3.3 Nếu sau này thật sự làm commit theo lô

Ghi lại số học để khỏi phải tìm lại:

* **Làm lớp bọc `compresslevel=1` TRƯỚC** tại điểm vá đã được phép
  (`audfprint_progress_runner.py`, cùng đánh đổi dự án đã chọn ở dòng ghi gzip của worker).
  Nó cắt thời gian lưu từ ~110 s xuống ~5,5 s đổi lấy file lớn hơn ~14% — tức đổi kích
  thước lô khuyến nghị **2,5 lần** và thuế thời gian **6 lần**. Làm lô trước là mua bản
  đắt tiền của tính năng.
* Chia lô theo **THỜI GIAN mỗi worker**, không theo số clip, để sống sót với kho có clip
  1–3 tiếng: `kich_thuoc = ncores × (600 / giây_mỗi_clip)`, sàn cứng 100 clip.
  Ở 12,8 s/clip và 8 nhân ⇒ ~375 clip/lô ⇒ +15% thời gian, mất tối đa ~8 phút.
* Điểm hoà vốn (thời gian gzip = thời gian fingerprint): **44 clip/lô** khi dựng mới,
  **84 clip/lô** khi thêm vào kho 128 MB. Dưới mức đó là nén tốn hơn cả tính.
* Phải làm kèm: trường độ phủ trong `khos.json` + chỉ báo trên giao diện, và sửa
  `engine.py:1704-1719` để câu thông báo huỷ thôi nói dối.

---

## 4. Bất biến phải giữ (đừng phá khi sửa tiếp)

1. **Cha KHÔNG giữ đầu ghi pipe** (`ghi.close()`). Worker chết phải thành EOF, không
   phải treo. Thiết kế mới **phụ thuộc** vào tính chất này để phát hiện chết dưới 0,1 s.
2. **Worker ghi HashTable ra file gzip; pipe chỉ mang dict nhỏ.** Bản vendored đẩy
   ~419 MB/worker qua Pipe (≈3,3 GB ở 8 nhân) và treo 3/6 lần. Tham số `pipe=` của
   `instrumented_make_ht_from_list` **vẫn mang nghĩa cũ đó** — nhịp sống dùng tham số
   `nhip` keyword-only riêng, tuyệt đối không gộp vào `pipe`.
3. **`_emit` dùng đúng một `os.write`.** `print()` bị xé và mất event (đo 7/8) khi 8
   worker cùng ghi một stdout.
4. **Nhịp phát SAU `clip_finished`**, để một nhịp chứng minh việc ĐÃ XONG.
   **Không bao giờ phát nhịp từ thread hẹn giờ** — thread vẫn tick khi luồng chính kẹt,
   biến watchdog thành đồ trang trí.
5. **Quét theo từng core** (xem §2.2).
6. `cai_dat_theo_doi_giai_ma()` vẫn là lệnh đầu tiên trong worker (Windows dùng `spawn`).
7. Commit vẫn là `os.replace(db_tam, self.db_file)` có đường lui `PermissionError`.

---

## 5. Test khoá lại

| Test | Khoá điều gì | Với mã CŨ |
|---|---|---|
| `test_worker_cham_hon_han_chot_nhung_van_tien_thi_khong_bi_giet` | Worker chạy lâu hơn hạn chót nhưng còn tiến ⇒ **không bị giết**. Regression trực tiếp của sự cố | **ĐỎ** |
| `test_worker_con_song_nhung_ngung_tien_thi_bi_phat_hien_va_bao_ro_so_file` | Kẹt thật vẫn bị bắt, và thông báo nêu **số file đã xong** | **ĐỎ** |
| `test_worker_khong_co_file_nao_thi_khong_bi_giet_oan` | `ncores > số file` ⇒ worker rỗng không bị giết oan (chặn lỗi mà phương án "quét tất cả" sẽ gây ra) | xanh (chặn hồi quy tương lai) |
| `test_worker_chet_khong_gui_gi_thi_bao_loi_chu_khong_treo` (có sẵn) | Worker chết ⇒ lỗi rõ, không treo | xanh — **không sửa** |
| `test_khong_con_file_tam_sau_khi_that_bai` (có sẵn) | Dọn thư mục tạm kể cả khi lỗi | xanh — **không sửa** |

Hai test cũ **không bị sửa một dòng nào** — đó chính là bằng chứng bất biến 1 và việc dọn
thư mục tạm còn nguyên.

> **Lưu ý về hạn chót trong test:** phải LỚN HƠN HẲN chi phí spawn+import của tiến trình
> con, vì nhịp **đầu tiên** chỉ tới sau khi con nạp xong module. Đo được ~0,4 s khi máy
> rảnh nhưng **vượt 2 s** khi chạy cả bộ test. Bản đầu dùng 1,5–2,0 s và flaky đúng theo
> kiểu đó. Bản chạy thật để 1800 s nên chuyện này không bao giờ là vấn đề.

---

## 6. Điều KHÔNG đổi trong lần này

* `engine.py`, `process_runner.py`, `fingerprint_progress.py`, `app.py`, `cli.py`:
  **không chạm một dòng nào.**
* `audfprint-master/`: **không chạm** (CLAUDE.md cấm).
* `--maxtimebits 16` tại `engine.py:1909`: **giữ nguyên theo quyết định của người dùng
  ngày 2026-09-07.** Xem cảnh báo dưới đây.

### 6.1 Còn tồn: giới hạn định vị 25,4 phút

`--maxtimebits 16` cho phép định vị mốc thời gian tối đa **1521,7 s = 25,4 phút** trong
một clip gốc (`n_hop=256`, `sr=11025`). Quá mốc đó `hash_table.py` làm `time_ &= timemask`
— **cuộn vòng, im lặng, không cảnh báo**.

Đo trên các kho hiện có:

| Kho | Clip TB | Dài nhất | Clip vượt 25,4 ph | Âm thanh bị cuộn |
|---|---:|---:|---:|---:|
| **KhoJoeBartolozzi** | 28,4 ph | 155,1 ph | **598/1178 (50,8%)** | **22,9%** |
| KhoJordanMatter | 17,2 ph | 126,5 ph | 117/537 (21,8%) | 14,3% |
| KhoDuncanyounot | 14,6 ph | 131,3 ph | 7/149 (4,7%) | 14,9% |

Hệ quả: với phần âm thanh nằm sau mốc 25,4 phút của clip gốc, mốc thời gian báo cáo lệch
đúng một bội của 25,4 phút; và một match vắt qua ranh giới bị tách thành hai đỉnh offset
nên **yếu đi**, có thể tụt dưới ngưỡng chấp nhận.

**Đã đo trực tiếp trên kho `KhoJoeBartolozzi` sau khi dựng xong (2026-09-07)** — đọc thẳng
giá trị thời gian lưu trong `.pklz`, không suy luận:

| Clip | Độ dài thật | Mốc lớn nhất lưu trong kho | Kết luận |
|---|---:|---:|---|
| `How I Would Survive A Draft` | 699 s (11,7 ph) | **698 s** | khớp chính xác, không cuộn |
| `I Reviewed Chat Suggested Etsy Products` | 9306 s (155,1 ph) | **1522 s** | đúng bằng trần ⇒ **bị cuộn** |

9306 giây nội dung bị gấp vào khoảng 0–1522 s, **chồng nhau 6,1 lần**. Kho khai báo
`maxtimebits = 16`, `maxtime = 65536` đơn vị.

Cần nói rõ điều này **KHÔNG** làm hỏng: smoke test 6/6 trích đoạn vẫn **nhận đúng clip**,
kể cả trích đoạn lấy từ giây 2122 của clip 155 phút. Việc **phát hiện** vẫn chạy; thứ sai
là **mốc thời gian báo cáo** trong clip gốc.

Nếu sau này muốn sửa: `maxtimebits=18` đưa giới hạn lên 101,4 phút (còn 3 clip vượt,
0,20% âm thanh, sức chứa 16.383 clip/kho); `=19` lên 202,9 phút (0 clip vượt, sức chứa
8.191 clip/kho). **Đổi đồng nghĩa phải dựng lại kho** — nên thời điểm rẻ nhất luôn là
ngay trước một lần dựng lại.

---

*Sửa ngày 2026-09-07. Thay đổi gói gọn trong `audfprint_progress_runner.py`
(+3 test trong `tests/test_audfprint_multiproc.py`). Không chạm mã nghiệp vụ.*
