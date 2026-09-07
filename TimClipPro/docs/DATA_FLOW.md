# DATA FLOW — Dữ liệu được tạo, biến đổi, lưu và xuất như thế nào

Tài liệu tham chiếu cho kỹ sư **chưa từng đọc repo này**. Nó mô tả **thứ đang có**, không
mô tả thứ nên có. Mọi khẳng định đều kèm `file:dòng`; nếu một câu không có trích dẫn thì
đó là câu định nghĩa hoặc câu nối, không phải khẳng định về hành vi.

**Phương pháp.** Mọi dòng được trích trong tài liệu này đã được mở lại và đọc trực tiếp
trong vòng audit này. Không file nào dưới `data/`, `bin/`, `ketqua/` bị đọc hay ghi; không
chạy test, không gọi mạng, không chạy ffmpeg/audfprint/yt-dlp. Nơi nào tài liệu trong
`docs/` mâu thuẫn với source, **source thắng** và mâu thuẫn được nêu tên.

**Cách đọc nhãn trạng thái.** Tài liệu tách nghiêm ngặt ba mức:

| Nhãn | Nghĩa |
|---|---|
| **CONFIRMED** | Đã đọc trực tiếp trong source vòng này; cơ chế và hệ quả đều xác định. |
| **LIKELY** | Cơ chế đọc được trong source, nhưng điều kiện kích hoạt chưa được tái hiện. |
| **HYPOTHESIS** | Suy luận có căn cứ, chưa kiểm chứng được từ vị trí audit. |

Phần "vấn đề" nằm gọn trong §9 và được tách theo đúng ba nhãn trên. Bảy mục từng bị nghi
ngờ nhưng đã **bị bác bỏ** khi kiểm chứng thì **không xuất hiện** ở đây dưới dạng vấn đề —
nơi nào chúng chạm vào một quyết định thiết kế còn tranh cãi, tài liệu trình bày cả hai
phía kèm bằng chứng (xem §6.5).

**Gốc dự án:** `C:/Users/Admin/OneDrive/Desktop/ToolQuet/Tool_Quet/TimClipPro`.
Mọi đường dẫn `file:dòng` bên dưới là tương đối với gốc này.

---

## Mục lục

1. [Stage-by-stage transform table](#1-stage-by-stage-transform-table) — từ URL tới một dòng Google Sheets
2. [Matching tier definitions](#2-matching-tier-definitions) — raw / parsed / chunk / merged / accepted / selected, và Top-N thật sự đếm gì
3. [Source-of-truth matrix](#3-source-of-truth-matrix)
4. [Data ownership matrix](#4-data-ownership-matrix)
5. [Temp & workspace map](#5-temp--workspace-map)
6. [**Timestamp reference frames**](#6-timestamp-reference-frames) — **đọc phần này trước khi động vào bất kỳ mốc thời gian nào**
7. [Duration](#7-duration) — bốn loại thời lượng và ai dùng loại nào
8. [Publication date](#8-publication-date)
9. [Các sai lệch đã biết](#9-các-sai-lệch-đã-biết-tách-theo-mức-chắc-chắn)
10. [Khoảng trống — thứ tài liệu này KHÔNG trả lời được](#10-khoảng-trống)

---

## 1. Stage-by-stage transform table

Đường đi đầy đủ của một link YouTube cho tới một dòng 34 cột trên Google Sheets. Mỗi hàng
là một phép biến đổi thật, tên hàm là tên thật trong source.

| # | Stage | Input type | Output type | Where (file:line) | Notes |
|---|---|---|---|---|---|
| 1 | Điểm vào lô | `list[str]` link | `Generator[ScanResult]` | `Engine.scan_iter` — `engine.py:3224` | `scan_many` (`engine.py:3261`) chỉ là `list(scan_iter(...))`. Vòng lặp lô **không** kiểm tra `cancel_event` giữa các video. |
| 2 | Điểm vào một URL | `url: str` | `ScanResult` | `Engine.scan_youtube` — `engine.py:3145` | `self.cancel_event.clear()` là câu lệnh thứ hai (`engine.py:3149`), sau `require()`. |
| 3 | Lấy metadata video vi phạm | `url: str` | `dict` 11 khoá | `Engine.youtube_info` — `engine.py:2009`, dict dựng ở `engine.py:2026-2043` | **Một** request yt-dlp. Ngày đăng được chốt CỨNG ở đây (`engine.py:2024`); exporter không bao giờ hỏi lại. |
| 4 | Chốt ngày đăng chính tắc | `dict` metadata | `PublicationDateResult` | `resolve_publication_date` — `publication_date.py:172`, gọi tại `engine.py:2024` | Kết quả ghi vào `"upload_date": ngay.yyyymmdd` (`engine.py:2038`); `confidence` tính ở `engine.py:2042` rồi **bị bỏ** (§8.4). |
| 5 | Quyết định tải bao nhiêu giây | `tong: float` (source) | `Optional[float]` | `Engine._gioi_han_tai` — `engine.py:2790`, gọi tại `engine.py:3166` | Trả `None` trừ khi bật **cả** `quet_tang_dan` (`engine.py:170`) và `tai_mot_phan` (`engine.py:177`) và video dài hơn `quet_tang_dan_tu_gio` (`engine.py:171`, mặc định 10h). |
| 6 | Tải audio | `url, video_id` | đường dẫn file | `Engine.download_audio` — `engine.py:2054`, gọi tại `engine.py:3167` | Bỏ qua hoàn toàn nếu đã có file không phải `.part` (`engine.py:2070-2074`). `outtmpl` tại `engine.py:2093`. Bản tải một phần mang hậu tố `__p<giây>` (`engine.py:2052`) để `glob` không nhầm là bản đầy đủ. |
| 7 | Quét một file media | đường dẫn file | `ScanResult` | `Engine.scan_media` — `engine.py:3043`, gọi tại `engine.py:3169` | **Không bao giờ raise**: cả `Cancelled` lẫn `Exception` đều thành `status="error"` (`engine.py:3134-3137`). |
| 8 | Đo thời lượng media | đường dẫn file | `Optional[float]` | `Engine.duration_of` — `engine.py:994`, gọi tại `engine.py:3064` | Kết quả gán thẳng vào `kq.duration_s` (`engine.py:3067`). Đây là loại **(b) MEDIA** — xem §7. |
| 9 | Chia trục thời gian thành đoạn | `tong: float` | `list[(tu, den)]` | `Engine._doan_quet_tang_dan` — `engine.py:2817`, gọi tại `engine.py:3068` | Trả `[(0, tong)]` khi tắt quét tăng dần hoặc video ngắn hơn ngưỡng. |
| 10 | Cấp workspace riêng cho lượt quét | — | thư mục `data/scan_jobs/<uuid4>` | `Engine.scan_workspace` — `engine.py:2229-2230`, mở tại `engine.py:3063` | `finally: shutil.rmtree` (`engine.py:2233-2234`). Xem §5. |
| 11 | Cắt WAV | file media + cửa sổ `(tu, den)` | `list[str]` đường dẫn chunk | `Engine._cut_chunks` — `engine.py:2236`, gọi tại `engine.py:3081` | Lưới mốc **luôn tính từ giây 0 của cả file** rồi mới lọc theo cửa sổ (`engine.py:2260-2265`), nên quét tăng dần và quét trọn sinh ra biên chunk giống hệt nhau. ffmpeg mono 11025 Hz (`engine.py:2273-2276`). |
| 12 | So khớp thô (có đường tắt Top-1) | `list[str]` chunk | `list[dict]` | `Engine._quet_tho` — `engine.py:2735`, gọi tại `engine.py:3086` | Đường tắt chỉ mở khi `top_n == 1` (`engine.py:2753`); mặc định `top_n = 5` (`engine.py:185`). |
| 13 | Chạy audfprint và đọc kết quả | `list[str]` chunk | `list[dict]` thô | `Engine._match_chunks` — `engine.py:2283` | Ghi `_ds_khuc<hậu_tố>.txt` (`engine.py:2305`), đọc `_raw_match<hậu_tố>.txt` (`engine.py:2308`). Tham số tại `engine.py:2320-2327`; **cố ý không** dùng `--sortbytime`. |
| 14 | Parse thành dict | dòng text audfprint | `dict{clip,bat_dau,khop,t_clip,hash,align}` | `engine.py:2340-2372` | `bat_dau = offset + t_khuc * he_so`, `khop *= he_so` (`engine.py:2368-2369`); `t_clip` **không** nhân hệ số vì nó là thời gian trong clip gốc chưa biến đổi. |
| 15 | Bù tốc độ (chỉ khi chưa có ứng viên đạt) | `list[dict]` | `list[dict]` bổ sung | `Engine._quet_da_toc_do` — `engine.py:2944`, gọi tại `engine.py:3100-3102` | Chỉ chạy khi `not self._co_ung_vien_dat(...)` (`engine.py:3099`) — video có kết quả bình thường không tốn thêm giây nào. |
| 16 | Lọc ngưỡng mảnh + gộp thành ứng viên | `list[dict]` | `list[Match]` | `Engine._merge` — `engine.py:2395`; lọc `engine.py:2406-2412`; dựng `Match` `engine.py:2492-2521` | Đây là nơi mốc thời gian ĐO ĐƯỢC và mốc SUY DIỄN được sinh ra cùng lúc — xem §6. |
| 17 | Chặn tự khớp | `list[Match]` | `list[Match]` | `engine.py:3110-3111` | Loại match có `m.clip.lower()` trùng basename của chính file đang quét. |
| 18 | Tính `ty_le` và nhãn `Vùng` | `list[Match]`, `duration` | mutate tại chỗ | `Engine._gan_chi_so` — `engine.py:2535-2543`, gọi tại `engine.py:3112` | `ty_le = 100 * hashes / tổng hash clip` (`engine.py:2540`); `vung` chia theo `start_s / duration` (`engine.py:2541-2543`). |
| 19 | Áp chính sách chấp nhận | `list[Match]` + `Config` | `(dat, loai, ly_do)` | `chap_nhan_khop.loc_chap_nhan` — `chap_nhan_khop.py:129`, gọi tại `engine.py:3116` | `kq.so_dat_nguong = len(dat_chuan)` (`engine.py:3117`) — đếm **trước** khi cắt Top-N. |
| 20 | Chọn Top-N | `list[Match]` | `(matches, matches_loai)` | `Engine._chon_loc` — `engine.py:2545`, gọi tại `engine.py:3122-3123` | Trục chia vùng là `kq.pham_vi_quet_s or tong` — **phần đã quét**, không phải cả video. Chủ đích, giải thích tại `engine.py:3118-3121`. |
| 21 | Ghi lịch sử | `ScanResult` | 1 dòng `jobs` + N dòng `matches` | `Engine.save_job` — `engine.py:3273`, gọi tại `engine.py:3221` | Chạy **trước** callback `on_video` (`engine.py:3252-3258`), nên lỗi giao hàng Sheets không bao giờ làm mất kết quả quét. |
| 22 | Dựng dòng 34 cột | `Iterable[ScanResult]` | `list[list]` 34 ô | `Engine.to_rows_ngang` — `engine.py:3385` → `bang_ngang.dung_dong_ngang` — `bang_ngang.py:69` | Hàm thuần, không I/O (`bang_ngang.py:75`). Bỏ qua mọi kết quả `status != "ok"` hoặc không có match (`engine.py:3392-3393`). |
| 23 | Giải danh tính clip gốc | `Match.clip` (basename) | `ResolvedClipMetadata` | `resolver.resolve(...)` — `bang_ngang.py:102` | Resolver dựng **một lần cho cả lô** (`engine.py:3389`), không phải mỗi dòng. Hoàn toàn offline (§3). |
| 24 | Ghi lên Google Sheets | header + rows | dòng trong worksheet | `SheetsExporter.append` → `ws.append_rows(...)` — `sheets.py:241-243` | Luôn `value_input_option="RAW"` (`sheets.py:243`) nên Sheets lưu nguyên văn, không diễn giải công thức. |

**Hai nhánh xuất khác dùng chung stage 1–21 rồi rẽ:**

| Nhánh | Hàm | file:line | Khác biệt |
|---|---|---|---|
| CSV dọc 16 cột | `Engine.to_rows` → `Engine.export_csv` | `engine.py:3344`, `engine.py:3369` | Một dòng cho **mỗi match**, không phải mỗi video. Giữ cả kết quả lỗi và kết quả rỗng dưới dạng dòng placeholder (`engine.py:3351-3357`). |
| Hồ sơ khiếu nại Markdown | `dossier.dung_ho_so` → `Engine.export_ho_so` | `dossier.py:41`, `engine.py:3420` | Hàm thuần (`dossier.py:47`). Không có cột ngày đăng (§8.5). |

---

## 2. Matching tier definitions

Code phân biệt **bảy** mức. Chúng không được gộp lẫn nhau — mỗi mức có số lượng khác nhau,
và một finding nói về mức này không áp dụng cho mức kia.

### T0 — ứng viên nội bộ của audfprint *(không bao giờ ra khỏi subprocess)*

`audfprint_match.Matcher._best_count_ids` — `audfprint-master/audfprint_match.py:124-147`.
Xếp hạng theo **tỷ lệ** `rawcounts / ht.hashesperid[ids]` (`audfprint_match.py:136`) rồi cắt
tại `search_depth`, mặc định **100** (`audfprint-master/audfprint.py:372`). TimClipPro
**không bao giờ** truyền `--search-depth` (danh sách tham số đầy đủ tại `engine.py:2320-2327`).

Hệ quả cần biết: vì xếp hạng theo tỷ lệ, clip gốc **ngắn** được ưu tiên cấu trúc.

### T1 — dòng "Matched" thô

`Matcher.file_match_to_msgs` — `audfprint-master/audfprint_match.py:400-414`. Số dòng mỗi
chunk bị chặn bởi `--max-matches` (`engine.py:2323`, mặc định `max_matches = 200`,
`engine.py:114`).

**Điều quan trọng chưa từng được ghi trong `docs/`:** `min_time`/`max_time` là cực trị
**đã bị cắt theo `--time-quantile`** của thời điểm các hit (`audfprint_match.py:173-194`),
mặc định CLI là **0.05** (`audfprint-master/audfprint.py:368`) và TimClipPro không ghi đè.
Do đó:

* độ dài "Matched X s" là khoảng 5–95%, **ngắn hơn thực tế khoảng 10%**;
* mốc bắt đầu **trễ** khoảng 5% độ dài;
* `hashes` là số đếm đầy đủ, nên **mật độ hash bị thổi lên ≈ 1/0.9 = 1.11×**.

Bốn ngưỡng mật độ/độ dài của tầng chấp nhận (`mat_do_bac_a`, `mat_do_toi_thieu`,
`min_match_chap_nhan`, `top1_match_s_dung_som`) đều được hiệu chỉnh **trên đại lượng đã lệch
này**, nên chúng nhất quán với nhau — nhưng đừng so chúng với một phép đo lấy từ nguồn khác.

### T2 — **parsed**: dict đã parse

`engine.py:2340-2372`. Regex `RE_MATCH` (`engine.py:585-588`) và `RE_TEN_KHUC`
(`engine.py:592`). Khoá: `clip`, `bat_dau`, `khop`, `t_clip`, `hash`, `align`.

`align = bat_dau - t_clip` (`engine.py:2372`) là một đại lượng **lai**: thời gian trên trục
video trừ thời gian trên trục clip. Nó chính xác bằng `-aligntime·t_hop + offset`, tức là
**độ lệch modal** — và **độc lập với `--time-quantile`**. Đây là nền tảng toán học của §6.

### T3 — **chunk**: lọc ngưỡng mảnh

`engine.py:2406-2412`:

```python
qua_hash = [x for x in tho if x["hash"] >= cfg.min_hash]
loc = [x for x in qua_hash if x["khop"] >= cfg.min_match_s and x["khop"] > 0]
```

`min_hash = 15` (`engine.py:112`), `min_match_s = 5.0` (`engine.py:113`).

**Bẫy:** `--min-count` được **hard-code là 10** trong lệnh audfprint (`engine.py:2322`), nên
mọi giá trị `min_hash` dưới 10 là vô nghĩa — audfprint đã lọc trước rồi.

### T4 — **merged**: ứng viên đã gộp (`Match`)

`engine.py:2455-2522`. Khoá gộp: **cùng `clip`**, `abs(align_nhóm - align_x) <= dedup_s`,
**và** khoảng cách interval `<= dedup_s` tới *bất kỳ* mảnh nào đã có trong nhóm
(`engine.py:2461-2483`). `dedup_s = 20.0` (`engine.py:116`).

Tích hợp hash (`engine.py:2435-2454`): hợp của các interval được cắt tại mọi điểm đầu-cuối;
mỗi khoảng con đóng góp `(b-a) × max(hash_i/khop_i)` trên các mảnh phủ trọn nó. **Khoảng
trống không đóng góp** vào cả tổng hash lẫn `do_dai_hop`.

Sau đó `hashes` bị kẹp trần bằng tổng hash thật của clip trong kho (`engine.py:2500-2505`) —
vượt trần thì ghi cảnh báo `"có dấu hiệu đếm trùng"`.

### T5 — **accepted**: ứng viên được chấp nhận

`chap_nhan_khop.loc_chap_nhan` — `chap_nhan_khop.py:129` → `danh_gia_chap_nhan` —
`chap_nhan_khop.py:81`. **Hai bậc, bậc B chỉ THÊM chứ không bao giờ lấy đi ứng viên bậc A**
(bậc A `return` trước khi bậc B được xét — `chap_nhan_khop.py:93-96` đứng trước
`chap_nhan_khop.py:104`).

| Bậc | Điều kiện | file:line | Mặc định |
|---|---|---|---|
| **A — bằng chứng tuyệt đối** | `hashes >= min_hash_floor` **VÀ** `mật độ >= mat_do_bac_a` | `chap_nhan_khop.py:88-96` | `min_hash_floor = 1000` (`engine.py:186`), `mat_do_bac_a = 3.0` (`engine.py:203`) |
| **B — phủ vân tay cao** | `ty_le >= ty_le_chap_nhan` **VÀ** `matched_s >= min_match_chap_nhan` **VÀ** `mật độ >= mat_do_toi_thieu` — cả ba | `chap_nhan_khop.py:104` | `60.0` / `20.0` / `3.0` (`engine.py:194-196`) |

`mat_do_bac_a` là **tham số duy nhất trong nhóm có thể LẤY ĐI kết quả**, nên nó được để
riêng khỏi `mat_do_toi_thieu` một cách có chủ đích (giải thích tại `engine.py:197-202`).
Nó được hiệu chỉnh trên 1.198 match lịch sử, mật độ thấp nhất đo được là 9,99 hash/s —
tức mức 3,0 loại 0/1.198 kết quả cũ.

### T6 — **selected**: kết quả được chọn (Top-N)

`Engine._chon_loc` — `engine.py:2545-2628`.

### T7 — dòng báo cáo

`Engine.to_rows` (`engine.py:3344`), `bang_ngang.dung_dong_ngang` (`bang_ngang.py:69`),
`dossier.dung_ho_so` (`dossier.py:41`).

**Metadata (`title`, `url`) được giải quyết TẠI ĐÂY — sau khi chọn lọc.** Nó **không** nằm
trong phễu phát hiện. Một clip gốc không định danh được vẫn tính là một kết quả và chỉ làm
rỗng vài cột; nó không bao giờ biến một lượt quét thành "0 kết quả".

### Top-N thật sự đếm gì

> **`top_n` đếm ỨNG VIÊN ĐÃ GỘP (đối tượng `Match`) — mức T6.**
> **Không** đếm mảnh thô, **không** đếm video, **không** đếm tác phẩm gốc khác nhau.

Ba hệ quả phải nói chính xác:

1. **Một clip có thể chiếm nhiều slot.** `uu_tien_clip_khac_nhau` (`engine.py:225`) chỉ là
   một boolean **trong tuple xếp hạng** (`engine.py:2583`) — nó là *ưu tiên*, không phải
   *ràng buộc*. Nếu chỉ một clip có ứng viên đạt chuẩn, `top_n=5` trả về 5 mảnh của **cùng
   một** clip.
2. **Chia vùng dùng `m.start_s`** (`engine.py:2612`) — một giá trị **SUY DIỄN** (§6) — và
   trục là `pham_vi_quet_s or tong` (`engine.py:3123`), tức **phần đã quét**. Trong khi đó
   nhãn `Đầu/Giữa/Cuối` của `_gan_chi_so` (`engine.py:2541-2543`) dùng **toàn bộ video**.
   Hai trục khác nhau, **có chủ đích**, giải thích tại `engine.py:3118-3121`.
3. **`ScanResult.so_dat_nguong`** (`engine.py:3117`) là số ứng viên **đạt chuẩn TRƯỚC** khi
   cắt Top-N, tức `len(T5)`. Nó xuất ra cột 34 "Tổng số đoạn phát hiện"
   (`bang_ngang.py:115-120`). **Cột này luôn ≥ số đoạn được liệt kê** — đó không phải lỗi.

Khoá xếp hạng là một tuple (`engine.py:2581-2584`):
`(hashes >= min_hash_strong, clip chưa dùng, ty_le hoặc hashes)`, mặc định
`khoa_chat_luong = "ty_le"` (`engine.py:235`) — **không phải** `hashes` thô.

---

## 3. Source-of-truth matrix

*Phần này được đưa vào nguyên văn từ tài liệu tổng hợp đã kiểm chứng. Mọi dòng trong đó đã
được mở lại tại `file:dòng` được trích.*

Mọi ô bên dưới đã được kiểm chứng bằng cách mở file tại dòng được trích. Nơi nào bản tổng
hợp và source bất đồng, source thắng và bất đồng được nêu tên. Ô không xác định được ghi
`UNKNOWN`.

### 3.1 Danh tính TÁC PHẨM GỐC (clip trong kho vân tay)

| Concept | Canonical source (file:line) | Secondary / derived copies | Divergence risk | Notes |
|---|---|---|---|---|
| **Original video ID** | `clip_metadata.py:312` — `raw_id = raw_value.get("id")` through `extract_youtube_id`, then re-derived and cross-checked against key + URL at `clip_metadata.py:377-391` | (a) filename bracket token, `clip_metadata.py:26` `_BRACKET_ID_PATTERN`, used as resolver level 4 at `:899-909`; (b) strict filename parse, `clip_metadata.py:27-30` `_FILENAME_PATTERN`, used at level 6 `:918-919`; (c) snapshot `id` key, written from `ResolvedClipMetadata.public_dict` `clip_metadata.py:194` via `engine.py:1289-1291` | **HIGH** | Three extractors of different strictness exist: anywhere-in-string bracket (`clip_metadata.py:100`), strict full-filename (`:628`), and `channel.py:473` substring `f"[{vid}]" in f`. The lenient one runs first as a *veto* — more than one id anywhere in the name returns `_ambiguous_result` at `clip_metadata.py:844-848` before any lookup. Level 6 then re-derives with the strict pattern instead of reusing the id already in hand. |
| **Original title** | `clip_metadata.py:317` — `title = raw_value.get("title")` in `clips_meta.json`; originally written by `channel.py:593` `"title": v.title` | (a) snapshot copy `clip_metadata.py:195` then `engine.py:1291`; (b) sanitised copy baked into the filename, `channel.py:469` `f"{ngay} - {lam_sach_ten(v.title)} [{v.id}].{AUDIO_EXT}"`; (c) filename-fallback title `clip_metadata.py:926`; (d) `danh_sach_video.py` deliberately reads the RAW entry title, not `r.title` | **HIGH** | The filename copy is lossy (`lam_sach_ten` strips `<>:"/\|?*`) and is what the report shows on the `basename_fallback` path (`clip_metadata.py:947` `title=name`). No writer other than `ChannelSync` ever sets `title`: `Engine.va_metadata_thieu` writes only the snapshot, and `kiem_ngay_dang`/`kiem_thoi_luong` touch date/duration only. |
| **Original URL** | Derived, not stored as given: `clip_metadata.py:385` — `url = f"https://youtu.be/{video_id}"` rewrites whatever was in the file once the id set is unambiguous | (a) raw `url` key `clip_metadata.py:324` (validated `:330-341`, blanked on failure); (b) snapshot `url` `clip_metadata.py:196`; (c) filename fallback `clip_metadata.py:927`; (d) `channel.py:604` `"url": f"https://youtu.be/{v.id}"` at write time | MEDIUM | Canonicalisation is deliberate — it drops userinfo/query/fragment. Only `youtu.be/<id>` and `youtube.com/watch?v=` are accepted; `/shorts/` and `/embed/` are blanked with `invalid_url`. An empty URL is the visible symptom of an unresolvable identity. |
| **Publication date (original clip)** | `clip_metadata.py:347` — `raw_value.get("publication_date")`, falling back to legacy `upload_date` at `clip_metadata.py:354`. Both are produced by `PublicationDateResolver.resolve`, `publication_date.py:172-235` | (a) snapshot `upload_date` key `clip_metadata.py:197` — the snapshot has **no** `publication_date` key, the field is renamed on the way out; (b) filename date prefix `channel.py:468`, re-read at `clip_metadata.py:628`; (c) `publication_date_source`, written at `channel.py:598` and `kiem_ngay_dang.py:217` but read by **no** resolver | **HIGH** | Precedence is `release_timestamp` → `timestamp` → `release_date` → `upload_date` → `filename` (`publication_date.py:65-66`), with confidences at `:68-74`. The `filename` tier (`:218-227`) has no production caller. `confidence` and `warnings` are never persisted anywhere. |
| **Canonical source duration (original clip)** | `clip_metadata.py:366` `raw_value.get("duration")` — yt-dlp `lengthSeconds`, already rounded when written (`channel.py:601`) | Snapshot `duration` key `clip_metadata.py:198` | **HIGH** | Overwritten in memory the moment a media duration exists: `clip_metadata.py:370-375`, `if duration_media is not None: duration = duration_media`. Past that point the two categories are indistinguishable inside `ResolvedClipMetadata`. |
| **Processing / media duration (original clip)** | `clip_metadata.py:370` `raw_value.get("duration_media")` — ffprobe on the produced `.opus`, written at `channel.py:603` `do_dai_media(f)` and back-filled by `kiem_thoi_luong.py:115` `muc[TRUONG] = round(media, 3)` | **None that survives.** `public_dict` (`clip_metadata.py:192-199`) has no `duration_media` key, so `engine.py:1291` writes the value into the snapshot's `duration` slot | **CRITICAL** | Two writers store two precisions for the same value: `channel.py:603` raw float vs `kiem_thoi_luong.py:115` `round(media, 3)`. More importantly the snapshot is a **lossy, non-round-trippable projection** — it keeps the value but drops the key that identified it as measured. |

### 3.2 Danh tính VIDEO VI PHẠM (nguồn đang được quét)

| Concept | Canonical source (file:line) | Secondary / derived copies | Divergence risk | Notes |
|---|---|---|---|---|
| **Infringing video ID** | `engine.py:2027` — `"id": info.get("id", "")` from one `yt_dlp.extract_info`, assigned to `ScanResult.source_id` at `engine.py:3156` / `:3202` | (a) `jobs.source_id` column `engine.py:878`, written `engine.py:3282`; (b) rebuilt into every jump link by `Engine.link_moc` `engine.py:3335-3342` | LOW | The one identity field that IS persisted. `ScanResult.source_id` defaults `""` (`engine.py:367`) and `scan_media` never sets it (`engine.py:3058`), so **file scans always store `source_id=''`** and are permanently invisible to `ids_da_quet` (`engine.py:3297-3299`). Intentional — `watch` is YouTube-only — but it means history de-duplication silently does not apply to local-file scans. |
| **Infringing video title** | `engine.py:2028` `"title": info.get("title", url)`, into `ScanResult.source_name` `engine.py:3155` | `jobs.source_name` `engine.py:874`, written `engine.py:3281` | LOW | Persisted. Falls back to the URL string when yt-dlp returns no title. |
| **Infringing video URL / channel** | `engine.py:2030-2036` (`uploader`, `channel`, `channel_id`, `channel_url`), into `ScanResult` at `engine.py:3157-3159` / `:3203-3205` | Report columns 2-4 of `HEADER_NGANG` (`bang_ngang.py:16-18`), emitted at `bang_ngang.py:82-84` | **HIGH** | `channel_url`, `channel_name` and `channel_id` are **not** columns of the `jobs` table (`engine.py:874-878`). They exist only in memory and in whatever artefact was exported. |
| **Publication date (infringing video)** | `engine.py:2024` `ngay = resolve_publication_date(info)`, then `engine.py:2040` `"upload_date": ngay.yyyymmdd`, into `ScanResult.upload_date` `engine.py:3160` / `:3206` | Column 8 "Ngày đăng video vi phạm" (`bang_ngang.py:22`), rendered at `bang_ngang.py:88` | **HIGH** | Also **not** persisted to `jobs`. `publication_date_source` and `publication_date_confidence` are computed at `engine.py:2041-2042` and then dropped — `ScanResult` has no field for either (`engine.py:362-391`). Frozen at metadata-load time by design; exporters never re-query. |
| **Canonical source duration (infringing video)** | Two sources depending on path: **(a)** ffprobe on the file on disk, `engine.py:3067` `kq.duration_s = tong` (from `Engine.duration_of`, `engine.py:994-1001`); **(b)** yt-dlp `lengthSeconds`, `engine.py:3194` `r.duration_s = float(info.get("duration") or r.duration_s)` | `jobs.duration_s` `engine.py:876`, written `engine.py:3281`; `hhmmss(kq.duration_s)` in column 7 (`bang_ngang.py:87`) and in the dossier (`dossier.py:78`) | **HIGH** | Path (b) fires only on the partial-download early-accept branch (`engine.py:3189-3200`). One field, two measurement sources, no provenance marker. `Engine.duration_of` also lacks the `math.isfinite`/`> 0` guard its two siblings have (`channel.py:88`, `kiem_thoi_luong.py:51`). |
| **Processing media duration (infringing video)** | `engine.py:3064` `tong = self.duration_of(path)` — always the length of the file actually on disk | `ScanResult.pham_vi_quet_s` `engine.py:391`, set `engine.py:3095`, corrected `engine.py:3195` | **HIGH** | On the partial-download path `tong` is the *truncated* file, so `_gan_chi_so(tat_ca, tong)` at `engine.py:3112` labels `Match.vung` against the wrong axis while `duration_s` is corrected afterwards at `:3194`. `pham_vi_quet_s` is **not** persisted; only the prose `note` (`engine.py:3124-3128`) reaches `jobs.note`. |

### 3.3 Lưu trữ vân tay và registry

| Concept | Canonical source (file:line) | Secondary / derived copies | Divergence risk | Notes |
|---|---|---|---|---|
| **Fingerprint warehouse (the `.pklz`)** | `engine.py:794` — `self.db_file = self._duong_dan_db_kho(kho["db"]) if kho else os.path.join(self.data_dir, "db.pklz")` | (a) the `--dbase` argv of every audfprint call, `engine.py:1655`; (b) in-process clip-list cache `Engine._cache_clips`, populated `engine.py:1044-1054`; (c) the deployment-zip copy, `dong_goi_may_chay.py:94` | **HIGH** | Read into the parent process only through `db_clips` (`engine.py:1007-1055`), never `hash_table.HashTable(path)`, to avoid the documented Windows handle leak (`engine.py:1010-1019`). `self.db_file` is re-read on **every** audfprint invocation, so a mid-scan warehouse switch takes effect immediately. Commit is a single `os.replace` (`engine.py:1944`). |
| **Warehouse registry** | `data/khos.json` — read `engine.py:733-737` `_doc_khos`, written `engine.py:739-740` `_ghi_khos`; the `db` field is gated by `_duong_dan_db_kho` `engine.py:743-765` | (a) `Engine.db_file` / `kho_dang_dung` / `kho_thu_muc` derived at `engine.py:794-797`; (b) regenerated copy in the deployment zip, `dong_goi_may_chay.py:177`; (c) rewritten on the secondary machine by `thiet_lap_may_phu.py:52` | **HIGH** | Two raw-join readers bypass the containment guard: `dong_goi_may_chay.py:90` and `thiet_lap_may_phu.py:70`. Every mutator (`add_kho`/`use_kho`/`update_kho`/`delete_kho`, `engine.py:817-861`) is an unlocked read-modify-write, while `build_database` writes the same file under `tool.lock` at `engine.py:1974`. Shape errors escape `__init__` as `KeyError`/`TypeError` (`engine.py:779`, `:791`, `:794`). |
| **Total hashes per clip (the `ty_le` denominator)** | `engine.py:1044-1050` — `ht.hashesperid[i]`, keyed by `os.path.basename(ht.names[i])` | `Engine._tong_hash_kho` `engine.py:2528-2533`, consumed at `engine.py:2539-2540` | MEDIUM | Key identity is **safe** here: audfprint prints `ht.names[tophitid]` (`audfprint-master/audfprint_match.py:407`), the same array `db_clips` reads, so `Match.clip` and `db_clips()["ten"]` are byte-identical basenames. This was checked specifically because `_tong_hash_kho` compares case-sensitively (`:2539`) while the self-match guard 570 lines later compares case-*in*sensitively (`engine.py:3111`) and the resolver normcases (`clip_metadata.py:68`) — three rules on one string, but no reachable divergence on the normal path. The real risk is a mid-scan warehouse switch changing the denominator. |

### 3.4 Mối nối: clip → metadata

| Concept | Canonical source (file:line) | Secondary / derived copies | Divergence risk | Notes |
|---|---|---|---|---|
| **Clip -> metadata identity key** | The **bare filename with extension**: `engine.py:2492` `ten_clip = os.path.basename(g["clip"])`, into `Match(clip=ten_clip)` `engine.py:2512` | (a) warehouse side, `engine.py:1049` `"ten": os.path.basename(ten)`; (b) metadata side, `channel.py:592` `meta[os.path.basename(f)] = {...}`; (c) snapshot side, `engine.py:1349` `name = str(clip.get("ten") or basename_compatible(...))` | **CRITICAL** | Resolution is a 7-level chain: multi-id veto `clip_metadata.py:844`; exact `:853`; exact-basename `:865`; canonical, NFC + Windows normcase (`:57-68`) `:885`; unique video id `:899`; ambiguous stop `:913`; filename fallback `:918`; basename fallback `:944`. The **three report exporters all call `resolve(m.clip)` with one argument** — `engine.py:3359`, `bang_ngang.py:102`, `dossier.py:53` — so the `clip_path` argument that `audit` passes (`engine.py:1351`) never participates on the report path. |
| **Metadata source set and precedence** | `engine.py:1109-1138` `_metadata_source_candidates` — snapshot `engine.py:1121-1122` priority **0**, live `clips_meta.json` `engine.py:1123-1124` priority **10**, legacy db-folder 20+, legacy `data/` 100 (only for warehouse `""` / `"Kho mặc định"`, `engine.py:1137`) | `danh_sach_video.py:376` builds a **completely different** source set — `load_metadata_strict(<kho>/clips_meta.json, kind="live", priority=10)` and nothing else | **CRITICAL** | Merge rule: `clip_metadata.py:549-558` sorts by `(_entry_quality, priority, source_file, key)`; the winner's non-empty fields stand and later sources fill only blanks (`:586-590`); disagreements become `conflict:<field>:<key>` (`:601`). `_entry_quality` (`:541-546`) demotes only `filename_fallback`/`basename_fallback`, so an `"exact"`-stamped snapshot entry wins every field. Consequence: the "Danh sách video" tab can show a corrected title while the CSV / Sheets / dossier show the stale one. |
| **Snapshot freshness signal** | `engine.py:1371` `"updated_at": now` in the payload; parsed back at `clip_metadata.py:510`, exposed at `clip_metadata.py:698-699` and `:1055` | Displayed only, `app.py:1184` | MEDIUM | Verified with a tree-wide grep: `updated_at` is **never** consulted by `_merge_entries` (`clip_metadata.py:549-558` keys on quality / priority / source_file / key alone). The freshness data needed to break the stale-snapshot tie already exists and is deliberately unused. |

### 3.5 Kết quả quét

| Concept | Canonical source (file:line) | Secondary / derived copies | Divergence risk | Notes |
|---|---|---|---|---|
| **Scan result** | `ScanResult`, `engine.py:362-397`; produced by `scan_media` `engine.py:3043-3143` and enriched by `scan_youtube` `engine.py:3145-3222` | (a) `jobs` row `engine.py:3275-3283`; (b) 16-column rows `engine.py:3344-3367`; (c) 34-column row `bang_ngang.py:69-121`; (d) dossier `dossier.py:41-83`; (e) UI `BatchSnapshot` / `VideoState` `scan_jobs.py:90-113` | **HIGH** | `scan_media` never raises — `Cancelled` and `Exception` both become `status="error"` (`engine.py:3134-3137`). `save_job` runs **before** the `on_video` delivery callback (`engine.py:3142` / `:3221` vs `:3252-3258`), so a delivery failure can never lose a result. Of the 18 `ScanResult` fields, `jobs` persists 6. |
| **Match timestamps — MEASURED** | `engine.py:2489` `vung_khop_s = min(x["bat_dau"] for x in manh)`; `engine.py:2490` `end_s = max(x["bat_dau"] + x["khop"] for x in manh)`; `matched_s = do_dai_hop` (union length) `engine.py:2515` | `matches.start_s` / `end_s` / `matched_s` `engine.py:884`; `hhmmss(m.vung_khop_s)` column 9 `engine.py:3362` | MEDIUM | Subject to audfprint's `--time-quantile` 0.05 trim (`audfprint-master/audfprint.py:368`, never overridden by `engine.py:2320-2327`), so every "measured" span is really a 5-95 % window. |
| **Match timestamps — DERIVED** | `engine.py:2507-2510` `clip_bat_dau_s = max(0.0, som_nhat["bat_dau"] - som_nhat["t_clip"])`, aliased to `start_s` at `engine.py:2513`; `clip_offset_s = vung_khop_s - clip_bat_dau_s` `engine.py:2516` | (a) all three report jump links — `engine.py:3364`, `dossier.py:60-62`, `bang_ngang.py:64-65` (the last with an extra `-3 s` lookback); (b) `matches.clip_offset_s` `engine.py:885` | **CRITICAL** | `start_s <= vung_khop_s` always, so the reported window can only start *earlier* than any confirmed match. `bang_ngang.py:63-64` displays `start_hhmmss` but links `int(start_s) - 3`, so the horizontal report's own text and link disagree by 3 s — the only exporter that does this. `clip_offset_s` collapses to `min(bat_dau, t_clip)` when the clamp fires. |
| **Match zone label (`vung`)** | `engine.py:2541-2543` — `p = m.start_s / duration`, with `duration` being the length of the file **on disk**, passed at `engine.py:3112` | Column 7 of `Engine.HEADER` (`engine.py:3319`), emitted `engine.py:3362` | MEDIUM | Derived from the DERIVED `start_s`, against an axis that `engine.py:3194` may later correct without recomputing the label. Not persisted. Absent from `HEADER_NGANG` and from the dossier. |
| **Acceptance thresholds** | `chap_nhan_khop.danh_gia_chap_nhan` `chap_nhan_khop.py:81-126` — tier A `:90-96` (`hashes >= min_hash_floor` **and** `density >= mat_do_bac_a`), tier B `:103` (`ty_le >= 60` **and** `matched_s >= 20` **and** `density >= 3`) | Values live in `Config`: `min_hash_floor` `engine.py:186`, `mat_do_bac_a` `engine.py:203`, `ty_le_chap_nhan` `engine.py:194`, `min_match_chap_nhan` `engine.py:195`, `mat_do_toi_thieu` `engine.py:196` | MEDIUM | Read via `getattr(cfg, ..., default)` throughout, so the literal defaults are duplicated as fallbacks in `chap_nhan_khop.py:98-100` — a second, silent copy of 60.0 / 20.0 / 3.0. Only `min_hash_floor` and `min_hash_strong` have UI controls (`app.py:526-531`); `mat_do_bac_a`, `ty_le_chap_nhan`, `min_match_chap_nhan` and `mat_do_toi_thieu` are edit-the-JSON only. `so_dat_nguong` (`engine.py:3117`) counts acceptances **before** the Top-N cut. |
| **Config values** | `engine.Config` dataclass defaults, `engine.py:105-241` | (a) `data/cau_hinh.json`, applied in place by `cau_hinh.ap_vao_config` `cau_hinh.py:66` `setattr(cfg, khoa, gia_tri)`; (b) live sidebar mutation `app.py:503-565`; (c) `cli.py:183` `eng.config.ncores = a.ncores`; (d) **a second independent reader**, `CauHinhMang.tu_file_cau_hinh` `ytdlp_chung.py:299-323` | **CRITICAL** | Precedence: dataclass default -> `cau_hinh.json` (`engine.py:683`) -> sidebar / CLI mutation. Environment variables affect **paths only** (`TIMCLIP_DATA_DIR` `engine.py:608` + `app.py:43`, `TIMCLIP_OUTPUT_DIR` `app.py:44`, `TIMCLIP_MUI_GIO` `publication_date.py:56`) — no env var can set a `Config` field. Any exception during load discards the **entire** config: `engine.py:695-696` `self.config = Config()`. `lay_tu_config` (`cau_hinh.py:70-72`) serialises **every** field with no allowlist, which is why `ytdlp_cookiefile` (`engine.py:150`) must hold a path. `ytdlp_chung.py:299-306` reads the same file with a bare `json.load` inside `except Exception -> defaults`, so it never sees `.bak` recovery and range-checks nothing. |
| **Google delivery state** | `SheetDeliveryWorker._trang_thai`, `sheet_delivery.py:137` — an in-memory `dict[str, SheetDelivery]` keyed by the sha256 of `sheet_delivery.py:84-89` | (a) `VideoState.delivery_key` `scan_jobs.py:105`, set `app.py:136`; (b) the delivered rows themselves in the sheet; (c) `watch.py` uses a *different* mechanism — `da_day_sheets: set[int]` of `id(ScanResult)` | **CRITICAL** | Not persisted anywhere and never pruned. Dies with the process; `stop()` (`sheet_delivery.py:172`) has no production caller. The idempotency key includes `scan_job_id` and the row content (`sheet_delivery.py:87`), so a deliberate re-scan is *not* deduped. Streamlit and `watch` have two unrelated delivery-state implementations with different retry semantics. |
| **Scan history** | `data/lichsu.db`: `jobs` `engine.py:874-878`, `matches` `engine.py:882-885`; written by `Engine.save_job` `engine.py:3273-3288` | `Engine.list_jobs` `:3290`, `ids_da_quet` `:3295`, `job_matches` `:3306`; rendered `app.py:1486-1497` | **CRITICAL** | `jobs` stores 10 columns; `matches` stores 8. **Not stored:** on the job side `channel_name` / `channel_id` / `channel_url` / `upload_date` / `pham_vi_quet_s` / `so_dat_nguong` / `chan_doan`; on the match side `ty_le` / `vung` / `clip_bat_dau_s` / `vung_khop_s`, and any work identity at all. Migration is one suppressed `ALTER TABLE` with **no backfill** (`engine.py:880-881`), so pre-migration rows keep `source_id=''` and get re-scanned once. |
| **Client / workspace** | There is **no client entity**. The three things that play that role: (a) *warehouse* = a `khos.json` entry `{ten, thu_muc, db}` (`engine.py:781`), applied `engine.py:791-797`; (b) *scan workspace* = `data/scan_jobs/<uuid4>` `engine.py:2229`, removed in `finally` `:2234`; (c) *UI session* = `st.session_state.eng`, one `Engine` per browser session `app.py:41-45` | Fingerprint-build workspace `data/fingerprint_jobs/<job_id>` `engine.py:1818-1819`; machine identity in the deployment package `dong_goi_may_chay.py:152-157` (`KHOA_RIENG_CUA_MAY`) | **HIGH** | Warehouse is the only tenant-like boundary, and it is enforced only in `_metadata_source_candidates` (`engine.py:1109`) and in `db_file` selection. Nothing else scopes by warehouse: `lichsu.db` is global — the `jobs` schema (`engine.py:874-878`) has no warehouse column — so scan history mixes results from every warehouse the machine has ever used, with no way to tell which fingerprint set produced a given row. |

### 3.6 Nơi hai đường code đọc NGUỒN KHÁC NHAU cho cùng một khái niệm

| Concept | Path A | Path B | Status |
|---|---|---|---|
| Original title / date / duration | reports, through `Engine.clip_metadata_resolver()` where snapshot priority 0 wins — `engine.py:3346`, `bang_ngang.py:102`, `dossier.py:53` | "Danh sách video" tab, `clips_meta.json` **only** — `danh_sach_video.py:376` | CONFIRMED |
| Infringing-video duration | ffprobe on the file, `engine.py:3067` | yt-dlp `lengthSeconds`, `engine.py:3194` | CONFIRMED |
| Zone-label axis vs duration field | `_gan_chi_so(tat_ca, tong)` — file on disk, `engine.py:3112` | `duration_s` corrected to the real video, `engine.py:3194` | CONFIRMED |
| Region-division axis vs zone-label axis | `_chon_loc(tat_ca, kq.pham_vi_quet_s or tong)`, `engine.py:3122-3123` | `_gan_chi_so(..., tong)`, `engine.py:3112` | **Intentional** — stated at `engine.py:3118-3121` |
| Network config (cookies, pacing) | `Engine.cau_hinh_mang()` from `Config` from `cau_hinh.doc_cau_hinh`, `engine.py:683` | `CauHinhMang.tu_file_cau_hinh`, `ytdlp_chung.py:299-323`, used by `cli.py:171` | CONFIRMED |
| The `data/` directory | `Engine.__init__`, `engine.py:632` — **no** env lookup | `thu_muc_data_mac_dinh`, `engine.py:608` — honours `TIMCLIP_DATA_DIR` | CONFIRMED |
| Clip-name comparison rule | `_tong_hash_kho` exact and case-sensitive, `engine.py:2539` | self-match guard `.lower()`, `engine.py:3111`; resolver NFC + normcase, `clip_metadata.py:68` | **Not a defect.** All three consume `ht.names` (`audfprint_match.py:407` = `engine.py:1049`), so the strings are byte-identical. Recorded so nobody "fixes" one of them into divergence. |
| Delivery retry ownership | `SheetDeliveryWorker` queue + backoff, `sheet_delivery.py:220-256` | `watch.py` per-video attempt plus end-of-run sweep, `watch.py:418-435` / `:497-515` | CONFIRMED |
| Original-clip `duration` key semantics | `clips_meta.json`: `duration` = yt-dlp rounded, `duration_media` = ffprobe — `channel.py:601-603` | snapshot: a single `duration` key holding the *media* value — `clip_metadata.py:198` via `engine.py:1291` | CONFIRMED |
| Report header fields vs persisted job | `bang_ngang.py:82-88` emits channel URL / name / id plus publication date | `jobs` schema has none of them, `engine.py:874-878` | CONFIRMED |

### 3.7 Năm quy tắc rút ra từ ma trận

1. **Basename là khoá nối của toàn hệ thống.** `Match.clip`, `db_clips()["ten"]` và khoá
   `clips_meta.json` đều là `os.path.basename` của cùng một chuỗi (`engine.py:2492`,
   `engine.py:1049`, `channel.py:592`). Bất kỳ thay đổi nào ở cách sinh tên file
   (`channel.py:469`) sẽ **âm thầm đánh khoá lại toàn hệ thống**.
2. **Snapshot đứng trên file mà mọi công cụ sửa chữa ghi vào.** Priority 0 so với 10
   (`engine.py:1121-1124`), cộng với `_entry_quality` chỉ hạ cấp filename-fallback
   (`clip_metadata.py:541-546`), nghĩa là `ChannelSync.va_metadata`, `kiem_ngay_dang` và
   `kiem_thoi_luong` không tới được báo cáo chừng nào snapshot còn tồn tại.
3. **Mốc ĐO ĐƯỢC và mốc SUY DIỄN cùng nằm trong `Match`, và báo cáo chọn cái suy diễn.**
   `start_s` là alias của `clip_bat_dau_s` (`engine.py:2513`), và cả ba link nhảy mốc dùng nó.
4. **Lịch sử là một chỉ mục, không phải một bản ghi.** `jobs` + `matches` cộng lại lưu 16
   trong khoảng 30 trường mà exporter tiêu thụ. Không có code path nào dựng lại báo cáo từ
   lịch sử — đó là lý do điều này chưa bao giờ lộ ra.
5. **Chỉ ĐƯỜNG DẪN đến từ môi trường, không bao giờ là GIÁ TRỊ.** Ba biến môi trường tồn tại
   (`TIMCLIP_DATA_DIR`, `TIMCLIP_OUTPUT_DIR`, `TIMCLIP_MUI_GIO`) và không cái nào đặt được
   một trường `Config`. Precedence: mặc định dataclass → `cau_hinh.json` → sửa trong tiến
   trình, và **reset toàn bộ config** khi nạp lỗi (`engine.py:695-696`).

---

## 4. Data ownership matrix

Ai ghi, ai đọc, lưu ở đâu, sống bao lâu, hỏng thì sao. Mọi dòng đã được mở lại trong vòng này.

### 4.1 Dưới `data/`

`self.data_dir` cố định tại `engine.py:632` và **không đọc `TIMCLIP_DATA_DIR`** — chỉ
`app.py:43` truyền biến đó vào. Ba thư mục được tạo sẵn tại `engine.py:641-642`
(`data_dir`, `dl_dir`, `out_dir`); các thư mục còn lại do chính người ghi tạo lazily.

| Dữ liệu | Writer(s) | Reader(s) | Persistence | Lifetime | Hỏng thì sao |
|---|---|---|---|---|---|
| **Registry kho** | `_ghi_khos` `engine.py:741` ← `add_kho` `:828`, `use_kho` `:837`, `update_kho` `:845`, `delete_kho` `:861`, fallback commit `:1956`, ghi shifts `:1974`; `thiet_lap_may_phu.py:52` | `_doc_khos` `engine.py:735`; `dong_goi_may_chay.py:61`; `thiet_lap_may_phu.py:33,66` | `data/khos.json` + `.bak` | Vĩnh viễn, **không có reaper** | Ghi atomic `.bak` → `.tmp` → fsync → `os.replace` (`luu_tru.py:86-92`). Parse lỗi → phục hồi từ `.bak` (`luu_tru.py:136-147`); cả hai hỏng → đổi tên `.hong.<ts>` + `LoiDuLieu` (`luu_tru.py:149-160`), bắt tại `engine.py:771`. **JSON sai SHAPE nhưng parse được thì trả nguyên văn** (`luu_tru.py:130-131`) và crash tại `engine.py:779`. |
| **Cấu hình người dùng** | `cau_hinh.ghi_cau_hinh` `cau_hinh.py:41` ← `Engine.luu_cau_hinh` `engine.py:709` ← `app.py:656` | `cau_hinh.doc_cau_hinh` `cau_hinh.py:31` ← `engine.py:681`; **reader thứ hai, khác biệt**: `ytdlp_chung.CauHinhMang.tu_file_cau_hinh` `ytdlp_chung.py:301` ← `cli.py:171` | `data/cau_hinh.json` + `.bak` | Chỉ ghi khi bấm Lưu trên GUI. **CLI không bao giờ ghi.** | Như trên. Nhưng `ytdlp_chung.py:300-306` bỏ qua `luu_tru` hoàn toàn — `io.open` + `json.load` trần trong `except Exception: return mac_dinh`, nên **không có phục hồi `.bak`**. Một giá trị ngoài dải reset **toàn bộ** config cho phiên đó (`engine.py:693-696`). |
| **Lịch sử quét** | `Engine.save_job` `engine.py:3273-3288` (một dòng `jobs` + N dòng `matches`, cùng transaction) | `list_jobs` `:3290`, `ids_da_quet` `:3295`, `job_matches` `:3306`; `kiem_metadata_kho.py:96` (read-only URI `:82`) | `data/lichsu.db`, SQLite | Ghi **mỗi video**, **ngoài** khối `try` (`engine.py:3141-3142`, `:3220-3221`) → crash ở video 8/10 vẫn giữ 1–7 | Không có `FOREIGN KEY`; toàn vẹn dựa vào `delete_job` xoá cả hai bảng trong một transaction (`engine.py:3312-3315`). Migration: một `ALTER TABLE ... ADD COLUMN source_id` trong `contextlib.suppress` (`engine.py:880-881`) — idempotent, **không backfill**. |
| **Snapshot metadata mỗi kho** | `ghi_json_an_toan(snapshot_path, payload)` `engine.py:1400` (dựng lại offline, tự chạy sau mỗi lần build) và `engine.py:1621` (vá mạng, **mỗi entry một lần ghi**) | Đăng ký **priority 0** tại `engine.py:1121-1122`; nạp `engine.py:1176-1181`; `.bak` priority 1 tại `engine.py:1188-1192`; đóng gói `dong_goi_may_chay.py:113` | `data/metadata/kho_<slug>.json` + `.bak`, đường dẫn dựng tại `engine.py:1080-1094` có guard `commonpath` | Tạo ở lần build/sửa đầu tiên của kho **có tên**; không có reaper | `luu_tru` atomic + `.bak`. Sai `warehouse` → `snapshot_warehouse_mismatch` (`clip_metadata.py:493-500`); sai `schema_version` → `snapshot_schema_unsupported` (`:501-507`). Snapshot chính hỏng thì **chặn** ghi đè để không phá `.bak` (`engine.py:1342-1346`). |
| **Kho vân tay** | Commit bằng `os.replace(db_tam, self.db_file)` `engine.py:1944`; `PermissionError` → file mới `engine.py:1946-1952` + ghi lại registry. Xoá qua `_xoa_an_toan` `engine.py:1060-1078` ← `delete_kho` `:856` | `db_clips` `engine.py:1039-1043` (gzip → `pickle.loads`, cache theo `(path, mtime_ns, size)` `:1024-1029`); audfprint con qua `--dbase` `:1654` | `data/kho_<slug>_<md5[:6]>.pklz`, gzip-pickle `HashTable` | Vĩnh viễn tới khi `delete_kho`. **Không reaper** — file bị thay thế trong nhánh `PermissionError` mồ côi vĩnh viễn | Commit atomic. Huỷ/lỗi để file cũ **nguyên vẹn từng byte**. Đọc luôn qua `db_clips` để tránh rò handle của `load_pkl` (giải thích `engine.py:1010-1019`). Tên file trong registry qua guard `_duong_dan_db_kho` `engine.py:743-765`. |
| **Cache tải** | `download_audio` `engine.py:2093`; quét `.part`/`.ytdl` giữa các client `engine.py:2136-2139`; xoá đơn lẻ khi tắt `keep_downloads` `engine.py:3207-3209` | Cache hit `engine.py:2070-2074` | `data/downloads/<id>[.__p<sec>].<ext>` | `keep_downloads` mặc định **True** (`engine.py:179`) nên nhánh xoá thường là code chết | GC bởi `don_dep.don_kho_dem` (`don_dep.py:60`) theo tuổi rồi ngân sách. `.part`/`.ytdl` bị loại khỏi ứng viên xoá (`don_dep.py:99-100`). **Chỉ CLI và watch chạy GC — GUI không bao giờ.** |
| **Chẩn đoán 0 kết quả** | `Engine._luu_chan_doan` `engine.py:2671-2695`; tên file qua `luu_tru.ten_file_hop_le` `engine.py:2694` | Không có consumer trong sản phẩm | `data/chan_doan/<tên>_<epoch>.json` | Chỉ ghi khi `status == "ok"` mà phễu mất hết (`engine.py:2660-2662`). Tự dọn: giữ 200 bản mới nhất (`engine.py:2696-2699`) | `luu_tru` atomic. Dùng `ten_file_hop_le` chứ **không** dùng `fingerprint_progress.ten_file_an_toan` — lý do NTFS ADS ghi tại `engine.py:2690-2693`. |
| **Khoá tiến trình** | `KhoaTienTrinh.__enter__` `khoa.py:64-107` | `thong_tin_chu_khoa` `khoa.py:55-59` đọc từ offset 1, **ngoài** vùng bị khoá | `data/tool.lock` | File **không bao giờ bị xoá**; kernel tự nhả khoá khi tiến trình chết | Giữ bởi đúng bốn chỗ: `engine.py:1436`, `:1495`, `:1690`, `watch.py:287`. **Đường quét GUI/CLI không lấy khoá này.** |

### 4.2 Trong thư mục kho của người dùng (`<kho_thu_muc>/`)

| Dữ liệu | Writer(s) | Reader(s) | Lifetime | Hỏng thì sao |
|---|---|---|---|---|
| **`clips_meta.json`** | `ChannelSync.save_meta` `channel.py:182` ← `sync` `:606`, `va_metadata`, `seed_meta_tu_dia`; `kiem_ngay_dang.py:229`; `kiem_thoi_luong.py:135`. **Engine không bao giờ ghi** (quy tắc ghi tại `engine.py:1264`) | `load_meta` `channel.py:179`; `_metadata_source_candidates` priority **10** `engine.py:1124`; `danh_sach_video.py:376` (nguồn **duy nhất** nó đọc); `dong_goi_may_chay.py:97` | Vĩnh viễn, không reaper | `luu_tru` atomic + `.bak` cho ba writer dùng `ghi_json_an_toan`. `danh_sach_video` **cố ý** dùng `load_metadata_strict` thay vì `doc_json_an_toan` để file hỏng **không bao giờ** bị đổi tên (`danh_sach_video.py:11-14`). |
| **`downloaded.txt`** | `channel.py:360` (append), dựng lại bởi `sua_archive` `channel.py:647-654` | `channel.py:351-352` | Vĩnh viễn | Dựng lại được từ đĩa bằng `quet_id_tren_dia` (`channel.py:622`). |
| **Clip gốc `.opus`** | `ChannelSync._tai_va_nen` `channel.py:542-551`, đặt tên bởi `_ten_file` `channel.py:465-469` | audfprint khi build; `danh_sach_video._duyet_file` `:257`; `liet_ke_media` `engine.py:574-581` | Vĩnh viễn. `delete_kho` **không bao giờ** chạm vào (`engine.py:849`) | Tên file là bằng chứng offline cuối cùng khi mất `clips_meta.json` (`channel.py:467`). |

### 4.3 Đầu ra dưới `ketqua/`

**Không có code nào trong sản phẩm đọc lại `ketqua/`** — mọi tham chiếu `out_dir` đều là
writer, cộng hai chỗ dựng logger.

| Dữ liệu | Writer | Format | Lifetime | Ghi chú |
|---|---|---|---|---|
| CSV dọc | `Engine.export_csv` `engine.py:3369-3383` | `ketqua/ketqua_<ts>.csv`, utf-8-sig, 16 cột | Không reaper | Không bao giờ ghi đè: mở mode `x`, va chạm thì thêm `_2`, `_3`. Mọi ô qua `o_bang_tinh_an_toan` (`engine.py:3379-3381`) chống công thức Excel. |
| CSV ngang | `Engine.export_csv_ngang` `engine.py:3396-3418` | `ketqua/ketqua_ngang_<ts>.csv`, 34 cột | Không reaper | Trả `""` và **không tạo file** khi rỗng (`engine.py:3400-3401`). |
| Hồ sơ khiếu nại | `Engine.export_ho_so` `engine.py:3420-3453` | `ketqua/hoso_<nguồn>_<ts>.md` | Không reaper | `open(..., "w")` thường (`engine.py:3449`) — không atomic, nhưng tên có timestamp + hậu tố chống va chạm. |
| Log build vân tay | `fingerprint_progress.py:67-68` ← `engine.py:1686` | `ketqua/fingerprint.log`, xoay 5 MB × 3 | Tự xoay | Log **duy nhất** bị giới hạn kích thước. |
| Log watch | `nhat_ky.mo_nhat_ky` `nhat_ky.py:131-143` ← **chỉ** `cli.py:233` | `ketqua/giamsat_<YYYY-MM-DD>.log` | Giữ 30 ngày (`nhat_ky.py:84-119`) | Chỉ theo NGÀY, không xoay theo kích thước. Streamlit **không bao giờ** mở file log. |

### 4.4 Ngoài dự án

| Dữ liệu | Writer | Reader | Ghi chú |
|---|---|---|---|
| **Watchlist** | **Không có writer trong sản phẩm.** `watch.ghi_watchlist` `watch.py:164-171` chỉ được gọi trong tests. Người vận hành sửa tay. | `watch.doc_watchlist` `watch.py:123-125` ← `cli.py:52` | Đọc qua `luu_tru`, nên file hỏng không có `.bak` dùng được sẽ **bị đổi tên** `.hong.<ts>` (`luu_tru.py:149-160`) — một input do người duy trì mà tool không tự dựng lại được. |
| **Khoá service account** | Không bao giờ ghi bởi codebase này | `sheets.py:96-97` (chỉ đường dẫn, đưa thẳng cho gspread); chỉ `client_email` được nạp vào Python (`sheets.py:130-134`) | Đường dẫn hard-code tương đối với `sheets.py` (`TEN_FILE_KEY`, `sheets.py:27`), **không có env override**. Khoá riêng **không bao giờ** được đọc vào Python. Tệp được `.gitignore` và bị loại khỏi cả hai packager. |
| **Google Sheet — kết quả quét** | `SheetsExporter.append` `sheets.py:241-243` ← delivery tăng dần trong app, nút đẩy tay `app.py:250`, `watch.py:426` và sweep `watch.py:509` | Apps Script `layCauTrucKetQuaQuet_` (`apps_script/File01_CauHinh_TienIch.gs:319-330`), ánh xạ theo TÊN cột | Worksheet mặc định `KetQuaQuet` (`sheets.py:95,99`); **cả hai schema 34 cột và 16 cột đều nhắm vào đây**. `append` **không tự retry** (`sheets.py:245-250`) — retry là việc của `SheetDeliveryWorker`. |
| **Google Sheet — danh sách kho** | `danh_sach_video.day_len_sheet` → `SheetsExporter.ghi_de` `sheets.py:253-338` | Người đọc | **Ghi đè phá huỷ** (`resize` rồi `update`), idempotent về kết quả nhưng **không atomic** về quá trình (`sheets.py:271-273`). Từ chối danh sách rỗng (`danh_sach_video.py:621-623`). |

### 4.5 Chỉ trong RAM (mất khi tiến trình chết)

Liệt kê vì vài thứ trong đây **trông giống** kho lưu trữ và hay bị nhầm là bền vững.

| State | Owner (file:line) | Bền vững? |
|---|---|---|
| Cache clip của kho `(_cache_khoa, _cache_clips)` | `engine.py:652`, `:1054` | Không — dựng lại theo `(path, mtime_ns, size)` |
| Cache resolver metadata | `engine.py:653-654`, `:1222-1223` | Không |
| `canh_bao_gop` / `canh_bao_mang` / `canh_bao_metadata` | `engine.py:620`, `:624`, `:655` | Không |
| `ChanDoanQuet` của lượt quét | `engine.py:628`, reset `:3059` | Chỉ phần 0-kết-quả, ra `data/chan_doan/` |
| Trạng thái giao hàng Sheets `_trang_thai` | `sheet_delivery.py:137` | **Không** — ghi rõ tại `sheet_delivery.py:15-19` |
| `watch.da_day_sheets` (set các `id(ScanResult)`) | `watch.py:390` | Không — vì vậy sweep cuối lượt là retry **duy nhất** |
| Cache kết nối gspread | `sheets.py:41-44` | Không |

---

## 5. Temp & workspace map

"Scope" = tập rộng nhất các thao tác đồng thời cùng dùng một đường dẫn. Đây là điều kiện
tiên quyết cho bất kỳ công việc nào về concurrency.

| Path | Scope | Tạo tại | Xoá bởi | Sống sót sau kill? | Rủi ro va chạm |
|---|---|---|---|---|---|
| `data/scan_jobs/<uuid4-hex>/` | **VIDEO-SCOPED** — mỗi lần gọi `scan_media`, tức **hai lần** cho một video trên đường tải-một-phần rồi tải-nốt (`engine.py:3169` rồi `:3186`) | `engine.py:2229-2230` | `finally: shutil.rmtree` `engine.py:2233-2234` | Có → mồ côi | **Không có.** Tên uuid4; không call site production nào truyền `scan_job_id` (chỉ một chỗ gọi: `engine.py:3063`). |
| `…/chunks/chunk_<mốc>.wav` và `chunk_<mốc>_k<hệ số>.wav` | Bên trong thư mục trên | `engine.py:2271`, `:2905` | cùng workspace | Có | Không có |
| `…/_ds_khuc<hậu_tố>.txt`, `…/_raw_match<hậu_tố>.txt` | Bên trong thư mục trên; hậu tố `""`, `_uu_tien` (`engine.py:2765`), `_con_lai` (`:2783`), `_k<hệ số>_<họ>` (`:3009`) | `engine.py:2305`, `:2308` | cùng workspace | Có | Không có **trong** một lượt quét: vòng lặp đoạn dùng lại cùng hậu tố nhưng chạy **tuần tự**, và `engine.py:2309-2310` xoá opfile trước mỗi lần chạy. |
| `data/fingerprint_jobs/<job_id>/` | **JOB-SCOPED** — mỗi lần build kho | `engine.py:1818-1819` | `engine.py:1962-1963` — nhưng khối `try` bao nó chỉ mở tại `engine.py:1913` | Có → mồ côi, và **không có reaper nào** | Không có giữa các build (`tool.lock` `engine.py:1690` tuần tự hoá chúng giữa các tiến trình). |
| `%TEMP%/timclip_ht_<ngẫu nhiên>/` | **JOB-SCOPED** — mỗi lần gọi audfprint build đa nhân | `audfprint_progress_runner.py:195` `tempfile.mkdtemp(prefix="timclip_ht_")` | `audfprint_progress_runner.py:264` `finally: shutil.rmtree` | **Không** — `TerminateProcess` trên Windows bỏ qua `finally` | Không có (tên duy nhất); rủi ro là **rò rỉ**, không phải va chạm. |
| `data/downloads/<id>[.__p<sec>].<ext>` | **GLOBAL-SHARED, toàn tiến trình, khoá chỉ theo video id** | `engine.py:2093` `outtmpl=os.path.join(self.dl_dir, ten + ".%(ext)s")` | `don_dep.don_kho_dem` (tuổi/ngân sách); `engine.py:3209` khi tắt `keep_downloads` | Có — đó chính là mục đích (nó là cache) | **CÓ THẬT.** Hai lượt quét đồng thời cùng **một** video id dùng chung một `outtmpl` và một `.part`; `engine.py:2136-2139` quét `.part`/`.ytdl` theo `<id>.*`. |
| `<kho>/_tam/` | **GLOBAL theo THƯ MỤC KHO** | `channel.py:171` `os.path.join(self.dest, "_tam")` | `channel.py:614` `shutil.rmtree` ở **cuối mỗi** `sync()`, cộng quét `.part`/`.ytdl` **toàn thư mục** tại `channel.py:502-507` | Có | **CÓ THẬT.** Hai `sync()` đồng thời trên cùng thư mục kho phá scratch của nhau. |
| `data/chunks/` | Sẽ là global-shared | `engine.py:637` | chỉ nhánh chết `if not workspace:` `engine.py:2250-2253` | — | Không tới được trong production; nhánh còn lại để tương thích test. |
| `data/_ds_khuc.txt`, `data/_raw_match.txt` | Sẽ là global-shared | `engine.py:2304` `goc = workspace or self.data_dir` | **không có gì** | — | Không tới được trong production. |
| `data/tool.lock` | **MACHINE-GLOBAL** | `khoa.py:66` | không bao giờ xoá | Có (kernel nhả khoá, file ở lại) | Chủ đích — đây **chính là** mutex. Không được lấy bởi bất kỳ đường quét nào. |
| `bin/` trong `PATH` | **PROCESS-GLOBAL**, không bao giờ khôi phục | `engine.py:645-646` | không bao giờ | — | Chỉ đọc; vô hại ngoài việc PATH dài thêm sau nhiều lần dựng `Engine`. |

### 5.1 Một câu tóm tắt cho việc concurrency

`Engine.scan_workspace` (`engine.py:2219-2234`) đã giải quyết **nửa SO KHỚP** của bài toán
scratch dùng chung, và docstring của chính nó nói thẳng lý do: trước đây hai lượt quét đồng
thời `rmtree` chunk của nhau. Nó **không** chạm vào **nửa TẢI VỀ**. Hôm nay:

* Cắt chunk, so khớp và biến đổi tốc độ: cô lập theo **video**. An toàn.
* Build vân tay: cô lập theo **job** *và* tuần tự hoá bởi `tool.lock`. An toàn.
* **Tải audio: không cô lập gì cả** — cả đường quét (`data/downloads`, khoá theo video id)
  lẫn đường đồng bộ kênh (`<kho>/_tam`, khoá theo kho).
* Registry (`khos.json`), config (`cau_hinh.json`) và `clips_meta.json` đều là
  read-modify-write **không khoá** giữa các tiến trình.

---

## 6. TIMESTAMP REFERENCE FRAMES

> **ĐỌC TRƯỚC KHI ĐỘNG VÀO BẤT KỲ MỐC THỜI GIAN NÀO.**
>
> Đây là lớp lỗi lặp lại nhiều nhất trong dự án. `Match` mang **bốn** trường thời gian và
> chúng **không** thay thế được cho nhau. `CLAUDE.md:92` nói thẳng:
> *"Ba khái niệm trên không được dùng thay thế cho nhau."*

### 6.1 Bảng bốn trường — MEASURED hay DERIVED

`Match` được dựng tại `engine.py:2492-2521`. Định nghĩa trường tại `engine.py:334-347`.

| Trường | Công thức | file:line | **Trạng thái** | Nghĩa chính xác |
|---|---|---|---|---|
| `vung_khop_s` | `min(x["bat_dau"] for x in manh)` | `engine.py:2489` | **MEASURED** | Giây đầu tiên trên trục video mà audfprint **thật sự** báo có hash khớp. |
| `end_s` | `max(x["bat_dau"] + x["khop"] for x in manh)` | `engine.py:2490` | **MEASURED** | Giây cuối cùng trên trục video có hash khớp. |
| `matched_s` | `do_dai_hop` — độ dài **hợp** của các interval mảnh | `engine.py:2515`, tính tại `:2435-2454` | **MEASURED** | Tổng độ dài thực sự khớp. **Bỏ qua khoảng trống** — nên nó ≠ `end_s - start_s`. |
| `clip_bat_dau_s` | `max(0.0, som_nhat["bat_dau"] - som_nhat["t_clip"])` | `engine.py:2507-2510` | **DERIVED** | Vị trí **ngoại suy** của giây 0 của clip gốc trên trục video. |
| `start_s` | **= `clip_bat_dau_s`** | `engine.py:2513` | **DERIVED** | Alias. Cùng một giá trị, cùng một object. |
| `clip_offset_s` | `vung_khop_s - clip_bat_dau_s` | `engine.py:2516` | **DERIVED** | Số giây đầu clip gốc bị bỏ qua trước khi vùng khớp bắt đầu. |
| `hashes` | `min(tích phân mật độ, tổng hash clip)` | `engine.py:2491`, kẹp `:2500-2505` | **DERIVED** | |
| `ty_le` | `100 * hashes / tổng hash clip`, kẹp 100 | `engine.py:2540` | **DERIVED** | Khoá xếp hạng mặc định (`engine.py:235`). |
| `vung` | bucket của `start_s / duration` | `engine.py:2541-2543` | **DERIVED từ một giá trị DERIVED** | |

**Bất biến toán học luôn đúng:** `start_s == clip_bat_dau_s <= vung_khop_s <= end_s`, vì
`t_clip >= 0` và `som_nhat["bat_dau"] == vung_khop_s` theo cách chọn `som_nhat`
(`engine.py:2488-2489`). Cửa sổ báo cáo **chỉ có thể bắt đầu sớm hơn**, không bao giờ muộn
hơn, so với bằng chứng đã xác nhận.

### 6.2 Vì sao phép ngoại suy tồn tại — và nó ĐÚNG trong trường hợp nào

Đây là phần dễ hiểu sai nhất, nên nói bằng toán:

* audfprint báo `bat_dau = min_time·t_hop (+offset)` và `t_clip = (min_time + aligntime)·t_hop`
  (`audfprint-master/audfprint_match.py:400-414`).
* Do đó `bat_dau - t_clip = -aligntime·t_hop + offset` — **đúng bằng độ lệch modal**, và
  **độc lập hoàn toàn với `--time-quantile`**.

Nói cách khác: `vung_khop_s` bị lệch ~5% độ dài do quantile trim (§2/T1), còn phép trừ
`bat_dau - t_clip` **triệt tiêu chính xác** phần lệch đó.

Dự án đã **đo** điều này. `docs/EXECUTION_PLAN_E.md:7-16` ghi lại một thí nghiệm có kiểm
soát — giấu một clip 120 giây vào **đúng giây 900** của một file dài rồi quét:

| Giá trị | Kết quả |
|---|---|
| Mốc thật | 900.0s |
| Tool báo bằng `start_s` **cũ** (= `vung_khop_s`) | 908.5s → **lệch +8.5s** |
| `clip_offset_s` | 8.5s |
| `start_s − clip_offset_s` (tức `clip_bat_dau_s` hôm nay) | **900.0s → lệch 0.0s** |

**Kết luận công bằng:** khi bản reup chứa clip **từ đầu clip**, `clip_bat_dau_s` là giá trị
CHÍNH XÁC và `vung_khop_s` mới là giá trị lệch. Phép ngoại suy không phải một lỗi — nó là
một phép hiệu chỉnh đã được đo.

### 6.3 Trường hợp phép ngoại suy đi sai — và không có gì chặn nó

Trường hợp ngược lại: bản reup chỉ chứa một **lát giữa** của clip gốc. Khi đó `t_clip` là
phần đầu clip **thật sự bị cắt bỏ** — một đại lượng được mô hình hoá hẳn hoi
(`clip_offset_s`, `CLAUDE.md:89`) — và `bat_dau - t_clip` ngoại suy **lùi vào vùng audio mà
fingerprinter chưa bao giờ khớp**.

Không có code path nào kẹp `start_s` về phía `vung_khop_s`, và không có cảnh báo nào khi
`clip_offset_s` lớn. Bảng edge-case trong `docs/EXECUTION_PLAN_E.md` chỉ liệt kê
`t_clip > bat_dau` (đã có clamp về 0) và `t_clip == 0`; trường hợp lát giữa **không được
liệt kê**.

Sai số bị chặn trên bởi độ dài clip gốc. **Tần suất thực tế: UNKNOWN** — xem §10.

### 6.4 QUY TẮC: report interval dùng gì, jump link dùng gì

**Quy tắc đang được thi hành trong code hôm nay** — `CLAUDE.md:91-92` phát biểu, và code khớp:

> *"Khi dựng báo cáo hoặc link mốc, luôn dùng thời điểm clip bắt đầu; khi chẩn đoán vân tay
> mới dùng vùng khớp và offset."* — `CLAUDE.md:91-92`

Nghĩa là: **cả khoảng thời gian báo cáo lẫn link nhảy mốc đều dùng `start_s`
(= `clip_bat_dau_s`, DERIVED).** Đã kiểm chứng từng chỗ:

| Bề mặt | Text hiển thị | Link nhảy mốc | file:line |
|---|---|---|---|
| CSV dọc 16 cột | Cột "Clip bắt đầu từ" = `m.start_hhmmss`; cột "Vùng khớp từ" = `hhmmss(m.vung_khop_s)`; cột "Đến" = `m.end_hhmmss` | `Engine.link_moc(..., m.start_s)` | `engine.py:3362`, `:3364` |
| Bảng ngang 34 cột (mặc định đẩy Sheets) | `f"{m.start_hhmmss} – {m.end_hhmmss}"` | `link_moc(..., max(0, int(m.start_s) - 3))` | `bang_ngang.py:63`, `:64-65` |
| Hồ sơ Markdown | `tu_hhmmss=m.start_hhmmss`, `den_hhmmss=m.end_hhmmss` | `link_moc(..., m.start_s)` | `dossier.py:58-62` |

**Ba điều bắt buộc phải biết về bảng trên:**

1. **Chỉ CSV dọc hiển thị cả hai mốc.** Nó có cả "Clip bắt đầu từ" (derived) **và** "Vùng
   khớp từ" (measured) đứng cạnh nhau (`engine.py:3319`, giá trị `:3362`). Bảng ngang và hồ
   sơ Markdown **chỉ có mốc derived** — chúng là hai artefact thực sự gửi cho chủ sở hữu
   quyền, và chúng không mang mốc đo được.
2. **Bảng ngang là exporter DUY NHẤT trừ thêm 3 giây cho link.** `bang_ngang.py:64`
   `giay_link = max(0, int(m.start_s) - 3)`. Đây là khoảng lùi có chủ đích cho độ trễ
   buffer của YouTube, được ghi **duy nhất** tại `docs/EXECUTION_PLAN_E.md:68-70` — trong
   `bang_ngang.py` không có comment nào giải thích. Hệ quả: text và link của **chính bảng
   ngang** lệch nhau 3 giây.
3. **`hhmmss` CẮT, `link_moc` cũng CẮT.** `hhmmss` kết thúc bằng `giay = max(0, int(giay))`
   (`engine.py:430`) và `link_moc` dựng `?t={int(giay)}` (`engine.py:3338`, `:3341`). Hai
   cái này phải giữ song hành — trước đây báo cáo ghi `00:24:02` mà link nhảy tới `00:24:01`
   (`engine.py:421-422`).

### 6.5 Quyết định đã ghi nhưng CHƯA thi hành

`docs/PHASE2_FIX_PLAN.md:265` ghi một quyết định PM:

> *"Theo quyết định PM, link vi phạm về sau phải dùng `vung_khop_s` thay vì `start_s` suy diễn.
> Đây là thay đổi báo cáo riêng, không trộn vào sửa overlap/seek của Phase 2b."*

**Trạng thái: CHƯA LÀM.** Đã kiểm chứng: cả ba call site (`engine.py:3364`, `dossier.py:60-62`,
`bang_ngang.py:64-65`) vẫn truyền `start_s`.

Hai tài liệu này **mâu thuẫn nhau**: `CLAUDE.md:91-92` nói dùng clip-start, `PHASE2_FIX_PLAN.md:265`
nói phải đổi sang `vung_khop_s`. Cả hai đều là tài liệu của dự án. Code theo `CLAUDE.md`.

**Ai định đổi phải biết trước:** `tests/test_thoi_diem.py:52-56` và `tests/test_dossier.py:73`
đang khoá hành vi hiện tại (link dùng `start_s`). Đổi mà không sửa test thì suite đỏ.

### 6.6 Trường bị mất khi ghi lịch sử

`save_job` (`engine.py:3283-3287`) ghi đúng bảy trường của `Match`:
`clip, start_s, end_s, matched_s, clip_offset_s, hashes, confidence`.

**KHÔNG ghi:** `ty_le` (khoá xếp hạng mặc định), `vung`, `clip_bat_dau_s`, `vung_khop_s`.
Schema tại `engine.py:882-885`. Hệ quả: mở lại một job cũ chỉ thấy mốc **derived**, và
**không thể tái dựng** thứ hạng đã sinh ra dòng đó. Không có code path nào dựng lại báo cáo
từ lịch sử, nên hôm nay điều này chưa gây ra output sai — nó là một khoảng trống forensics.

### 6.7 Danh sách kiểm tra khi sửa bất kỳ mốc thời gian nào

1. Trường này **MEASURED** hay **DERIVED**? Tra bảng §6.1.
2. Nếu sửa `duration_s`, đã rà lại **mọi** thứ tính từ nó chưa? `CLAUDE.md:448-449` ghi
   đúng bài học này. Ba thứ phái sinh: `quet_mot_phan` (`engine.py:393-396`), `note`
   (`engine.py:3124-3128`), và `Match.vung` (`engine.py:2541-2543`).
3. Thay đổi có chạm vào cả **ba** exporter không? Chúng không dùng chung một hàm dựng.
4. `hhmmss` và `link_moc` có còn song hành (cùng CẮT) không?
5. Test nào đang khoá hành vi cũ? Tối thiểu: `tests/test_thoi_diem.py`, `tests/test_dossier.py`.

---

## 7. Duration

### 7.1 Bốn loại — không bao giờ được trộn

| Loại | Nguồn thật trong code | Ghi ở đâu |
|---|---|---|
| **(a) SOURCE** — YouTube nói tác phẩm dài bao nhiêu | `info["duration"]` của yt-dlp = `lengthSeconds` = **đã làm tròn** — `engine.py:2029` | `clips_meta.json["duration"]` — `channel.py:602` |
| **(b) MEDIA** — ffprobe đo trên file thật | `Engine.duration_of` `engine.py:994`; `channel.do_dai_media` `channel.py:68`; `kiem_thoi_luong.do_dai_media` `kiem_thoi_luong.py:41` | `clips_meta.json["duration_media"]` — `channel.py:603` |
| **(c) MATCH timestamps** | `Match.start_s/end_s/matched_s/clip_offset_s/vung_khop_s` — `engine.py:335-347`, sinh tại `engine.py:2492-2521` | `matches` table `engine.py:882-885` |
| **(d) OPERATIONAL** — đã chạy / ETA | đồng hồ hệ thống | `app._thoi_luong` `app.py:188-192` — **bản sao độc lập, đúng chủ đích** (`engine.py:425-427`) |

Vì sao `duration` của YouTube lệch: comment đo đạc tại `clip_metadata.py:359-365` ghi rằng
trên 60 clip kho SML thì 58/60 khớp `round(media)`, và 55% trong số đó **cao hơn
`floor(media)` đúng 1 giây**. Trình phát hiển thị theo kiểu **cắt**, nên báo cáo theo số
nguyên đó sẽ **dư 1 giây ở hơn nửa số clip**.

### 7.2 Trường báo cáo nào dùng loại nào

| Trường báo cáo | Loại | Bằng chứng |
|---|---|---|
| "Thời lượng video vi phạm" (CSV ngang, Sheets) | **(b) media** — trừ nhánh tải-một-phần thì là **(a) source** | `bang_ngang.py:87` `hhmmss(kq.duration_s)`; nguồn `engine.py:3067` vs `engine.py:3194` |
| "Thời lượng" trong hồ sơ Markdown | như trên | `dossier.py:78` |
| "Thời lượng video gốc N" | **(b)** khi có `duration_media`, ngược lại **(a)** | `clip_metadata.py:370-375`; `bang_ngang.py:103-112` |
| "Thời lượng" bảng Lịch sử | giá trị `duration_s` **đã lưu** | `app.py:1478`; ghi tại `engine.py:3281` |
| "Thời lượng" bảng xem trước kênh | **(a) source** | `app.py:994`, `:1039` |
| "Đoạn khớp (giây)" / "Độ dài đoạn" | **(c)**, `round()` | `engine.py:3365`, `dossier.py:63` |
| "Tổng thời gian vi phạm" | tổng của **(c)** đã `round()`, rồi `hhmmss` | `dossier.py:68`, `:100` |
| "Tỷ lệ video bị chiếm" | **(c)** chia cho `duration_s` | `dossier.py:69-73` |
| `Vùng` (Đầu/Giữa/Cuối) | **(b) của file ĐÃ TẢI** | `engine.py:2541-2543`, gọi tại `engine.py:3112` |
| Ngưỡng chấp nhận | **(c)** `matched_s` | `chap_nhan_khop.py:81-126` |
| `_gioi_han_tai` / `_doan_quet_tang_dan` | **(a)** / **(b)** tương ứng | `engine.py:3166` (source), `engine.py:3068` (media) |

`ty_le` tính **hoàn toàn bằng số hash**, không dùng thời lượng (`engine.py:2540`) — không có
nguy cơ trộn loại ở đó.

### 7.3 `duration_s` mang HAI ngữ nghĩa tuỳ đường đi — CONFIRMED

Đây là điểm quan trọng nhất của mục này.

* **Đường thường:** `kq.duration_s = tong` với `tong = self.duration_of(path)` —
  loại **(b) MEDIA**, ffprobe trên file trên đĩa (`engine.py:3064`, `:3067`).
* **Đường tải-một-phần + đủ bằng chứng:** `r.duration_s = float(info.get("duration") or r.duration_s)`
  — loại **(a) SOURCE**, `lengthSeconds` đã làm tròn của yt-dlp (`engine.py:3194`).

Nhánh (a) chỉ chạy khi đi vào `elif gioi_han:` tại `engine.py:3189`. Việc ghi đè là **cần
thiết** — file trên đĩa chỉ dài `gioi_han` giây và không đại diện cho video 66 tiếng — nhưng
**không trường nào ghi lại `duration_s` hiện đang mang ngữ nghĩa nào**. `jobs.duration_s`
(`engine.py:3281`) thừa hưởng sự nhập nhằng đó, nên so sánh lịch sử trộn hai đơn vị đo.

Tài liệu `docs/DURATION_ARCHITECTURE.md:53-55` khẳng định điều **ngược lại** — rằng
`duration_s` "giữ nguyên một ngữ nghĩa duy nhất". Tài liệu đó không nhắc gì tới tính năng
tải-một-phần; nó có trước tính năng này.

### 7.4 CẮT hay LÀM TRÒN

`hhmmss` **CẮT**, không làm tròn: `giay = max(0, int(giay))` (`engine.py:430`).

Quyết định này có số đo hậu thuẫn, ghi ngay trong docstring `engine.py:411-421`:

| video | duration thật | UI YouTube | `round()` | cắt |
|---|---|---|---|---|
| `D-sVTRR5jm0` | 21219,981 | 5:53:39 | 5:53:40 ✗ | 5:53:39 ✓ |
| `3ixKzIN0et0` | 675,861 | 11:15 | 11:16 ✗ | 11:15 ✓ |

Làm tròn khiến **43,3%** video quét được bị báo dư 1 giây (`engine.py:419`).

**Ngoại lệ chưa được giải thích:** `matched_s` là thời lượng media (loại c) nhưng được
`round()` chứ không cắt — `engine.py:3365`, `dossier.py:63`, `app.py:1490-1491`. Ba nơi nhất
quán với nhau nên không lệch nhau, nhưng ngược quy tắc CẮT. Cùng đại lượng đó lại dùng
`hhmmss` (cắt) trong thông báo tiến độ tại `engine.py:2775`.

**Ba bản sao của `hhmmss`:** bản chính `engine.py:407`; bản sao byte-for-byte
`kiem_thoi_luong.py:54-56` (tồn tại để `--help` không phải nạp `engine` — `kiem_thoi_luong.py:155`);
và `app._thoi_luong` `app.py:188-192` là loại (d), **đúng chủ đích**. Không có test cấu trúc
nào chặn bản sao thứ tư.

### 7.5 `duration_of` thiếu guard mà hai hàm anh em đều có

```python
# channel.py:86-88 và kiem_thoi_luong.py:49-51 — CÓ guard
    return gia_tri if math.isfinite(gia_tri) and gia_tri > 0 else None
```

`Engine.duration_of` (`engine.py:994-1001`) **không có** guard `isfinite`/`> 0`. Guard phía
caller là `if not tong` (`engine.py:3065`) — không bắt được `NaN`/`inf`. Đây là nguồn của
`kq.duration_s`, tức của `bang_ngang.py:87` và `dossier.py:78`.

---

## 8. Publication date

### 8.1 Chuỗi precedence — nguồn sự thật là `publication_date.py`

```python
# publication_date.py:65-66
TRUONG_EPOCH = ("release_timestamp", "timestamp")
TRUONG_NGAY  = ("release_date", "upload_date")
```

`PublicationDateResolver.resolve()` (`publication_date.py:172-235`) chạy đúng ba pha:

| Bậc | Trường | `confidence` | file:line | Ghi chú |
|---|---|---|---|---|
| 1 | `release_timestamp` | `high` | `publication_date.py:178-198`, `:69` | Epoch → đổi múi giờ được → **return ngay** |
| 2 | `timestamp` | `high` | như trên, `:70` | |
| 3 | `release_date` | `medium` | `publication_date.py:200-216`, `:71` | Chuỗi `YYYYMMDD`, **luôn kèm** cảnh báo `khong_co_gio_de_quy_doi_mui_gio` |
| 4 | `upload_date` | `medium` | như trên, `:72` | |
| 5 | `filename` | `low` | `publication_date.py:218-227`, `:73` | **CODE CHẾT** — xem §8.3 |
| — | không có gì | `none` | `publication_date.py:229-235` | `warnings=("khong_co_du_lieu_ngay",)` |

Vì sao epoch được ưu tiên: `upload_date` của yt-dlp là ngày theo lịch **UTC**, còn người dùng
Việt Nam nhìn thấy ngày theo `Asia/Ho_Chi_Minh` — hai cái lệch nhau một ngày với video đăng
buổi tối. Chỉ trường có **giờ** mới quy đổi múi giờ được.

### 8.2 Múi giờ

```python
# publication_date.py:141-150
datetime.fromtimestamp(so, timezone.utc).astimezone(_mui_gio(ten_mui_gio)).date()
```

`MUI_GIO_MAC_DINH = os.environ.get("TIMCLIP_MUI_GIO", "Asia/Ho_Chi_Minh")` —
`publication_date.py:56`, đọc **lúc import**; `_MAC_DINH = PublicationDateResolver()` cũng
dựng lúc import (`publication_date.py:238`). Đổi biến môi trường **sau** khi import không có
tác dụng.

Epoch hợp lệ nằm trong `[1104537600, 4102444800]` (`publication_date.py:59-60`). Giá trị rơi
vào dải mili-giây **không** tự chia 1000 — chỉ trả cảnh báo `epoch_co_the_la_mili_giay`
(`publication_date.py:134-137`), đúng nguyên tắc "không đoán".

### 8.3 Bậc `filename` là code chết

`grep -rn "filename_date"` chỉ ra `publication_date.py:218,224` và
`tests/test_publication_date.py:172,184`. **Không production caller nào** đặt khoá `filename_date`.

Fallback theo tên file thực sự xảy ra ở **hai chỗ khác**, cả hai **không** đi qua bậc này:

* `clip_metadata.py:782` — `upload_date = entry.upload_date or str(fallback["upload_date"])`
* `channel.py:210` — `"upload_date": str(phan.get("upload_date") or "")` trong `seed_meta_tu_dia`

Hệ quả: ngày suy từ tên file được lưu và đọc **như một `upload_date` bình thường**, nên
`resolve()` gán `confidence="medium"` / `source_field="upload_date"` thay vì `"low"`/`"filename"`.

Tín hiệu **vẫn còn ở tầng resolver**: `warnings=("fields_enriched_from_filename",)` và
`resolution_method="filename_fallback"` (`clip_metadata.py:793-799`), và `app.py:374-379`
có hiện cảnh báo cho phiên UI. Nhưng **dòng CSV/Sheets gửi đi khiếu nại không mang dấu nào** —
`bang_ngang.py:102-113` chỉ lấy `meta.url/title/upload_date/duration`.

### 8.4 Provenance được ghi ở đâu

| Nơi ghi | `publication_date` | `publication_date_source` | `confidence` | `warnings` |
|---|---|---|---|---|
| `ChannelSync.sync` — `channel.py:596-598` | ✔ | ✔ | ✘ | ✘ |
| `ChannelSync.va_metadata` — `channel.py:307-310` | ✘ (chỉ `upload_date`) | ✘ | ✘ | ✘ |
| `ChannelSync.seed_meta_tu_dia` — `channel.py:205-212` | ✘ (chỉ `upload_date` **suy từ TÊN FILE**) | ✘ | ✘ | ✘ |
| `kiem_ngay_dang.repair` — `kiem_ngay_dang.py:216-221` | ✔ | ✔ | ✘ | ✘ |
| `Engine.youtube_info` — `engine.py:2038-2042` | (trả dict, không lưu) | ✔ | ✔ | ✘ |
| Snapshot `_snapshot_entry` — `engine.py:1288-1292` | ✘ (**mất hoàn toàn**) | ✘ | ✘ | ✘ |

`channel.provenance_ngay_dang()` (`channel.py:110-112`) — hàm **duy nhất** trả đủ
`to_dict()` gồm `confidence` + `warnings` — **không được gọi ở đâu cả**.
`Engine.youtube_info` trả `publication_date_confidence` (`engine.py:2042`) nhưng
`scan_youtube` chỉ lấy `info["upload_date"]` (`engine.py:3160`, `:3206`) — confidence bị vứt.

`MetadataEntry.public_dict()` (`clip_metadata.py:153-160`) chỉ có 5 khoá
`id/title/url/upload_date/duration`. Đây **chính là** payload của snapshot
(`engine.py:1288-1292`), nên **snapshot không bao giờ mang provenance**.

### 8.5 Exporter nào đồng ý với nhau

| Exporter | Ngày video vi phạm | Ngày video gốc | Hàm định dạng |
|---|---|---|---|
| CSV ngang 34 cột | `kq.upload_date` (`bang_ngang.py:88`) | `resolver.resolve(clip).upload_date` (`bang_ngang.py:107`) | `format_publication_date` qua `bang_ngang.py:58` |
| Google Sheets | dùng **đúng** `to_rows_ngang` (`engine.py:3385-3394`; `watch.py:414`) | như trên | như trên |
| Xem trước UI | như trên (`app.py:118`, `:238`) | như trên | như trên |
| CSV dọc 16 cột | **không có cột ngày** (`engine.py:3317-3322`) | **không có** | — |
| Hồ sơ Markdown | **không có ngày** (`dossier.py:86-127`) | **không có** | — |
| `danh_sach_video` | **không có trường ngày** (`danh_sach_video.py:117-133`) | — | — |

> **Kết luận: KHÔNG exporter nào lệch nguồn.** Ngày đăng chỉ tồn tại trên **một** đường duy
> nhất — bảng ngang — và đi qua **đúng một** formatter. Điều này được khoá bằng test cấu trúc
> `tests/test_publication_date_exporters.py:90-102`: chỉ `publication_date.py` được phép chứa
> `%d/%m/%Y`.

Hai lưu ý:

* Cả `kq.upload_date` lẫn `resolver.resolve().upload_date` đều **chịu sự chi phối của
  snapshot** (§3.4, §9.1).
* `app.py:993`, `:1038` in `v.upload_date` **thô** (`20250620`) trong bảng xem trước danh
  sách kênh, **không** qua `format_publication_date`. Đó chỉ là preview, không phải báo cáo,
  nhưng lệch định dạng với mọi chỗ khác.

### 8.6 Định dạng lưu trữ chính tắc

* Trong metadata / `ScanResult`: chuỗi **`YYYYMMDD`** (`publication_date.py:88-90`).
* Trong báo cáo: **`DD/MM/YYYY`**, chỉ qua `format_publication_date()` (`publication_date.py:251-264`).
* **`"00000000"` KHÔNG phải ngày hợp lệ** (`clip_metadata.py:118-119` từ chối nó);
  `channel._ten_file` dùng nó **có chủ đích** để nghĩa là "không biết" (`channel.py:466-468`).

---

## 9. Các sai lệch đã biết (tách theo mức chắc chắn)

Phần này liệt kê những chỗ luồng dữ liệu **không** làm điều mà một người đọc hợp lý sẽ trông
đợi. Ba nhãn được tách nghiêm ngặt và **không** trộn.

### 9.1 CONFIRMED — đã đọc trực tiếp trong source vòng này

| # | Điều gì | Bằng chứng | Ảnh hưởng tới luồng dữ liệu |
|---|---|---|---|
| C1 | **Snapshot (priority 0) che clips_meta.json (priority 10)** | `engine.py:1121-1124`; merge `clip_metadata.py:549-558`, fill-empty-only `:586-590`; `_entry_quality` chỉ hạ cấp filename-fallback `:541-546`; `_snapshot_entry` đóng dấu `"exact"` `engine.py:1288-1292` | Sửa `title`/`publication_date`/`duration_media` trong `clips_meta.json` **không tới được** CSV, Sheets, hồ sơ. Xung đột **có** được ghi (`conflict:<field>:<key>`, `clip_metadata.py:601`) nhưng chỉ `kiem_metadata_kho.py:229` đọc. **Đây là hành vi có chủ đích và bị khoá bởi test** `tests/test_clip_metadata.py:229-266`. |
| C2 | **`duration_s` mang hai ngữ nghĩa** | `engine.py:3067` (media) vs `engine.py:3194` (source) | §7.3. Cột "Thời lượng video vi phạm" và `jobs.duration_s` trộn hai đơn vị đo, không có cờ phân biệt. |
| C3 | **`Match.vung` tính trên trục file đã tải, không được tính lại sau khi `duration_s` được sửa** | `_gan_chi_so(tat_ca, tong)` `engine.py:3112` với `tong` từ `:3064`; `duration_s` sửa sau tại `:3194` | Trên đường tải-một-phần, mọi match thực ra nằm trong phần đầu video nhưng được rải nhãn Đầu/Giữa/Cuối theo trục đoạn đã tải. Chỉ hiển thị (CSV dọc + bảng UI); **không** ảnh hưởng chọn Top-N, không được lưu, không có trong Sheets/hồ sơ. |
| C4 | **Snapshot đổi tên `duration_media` thành `duration`** | `clip_metadata.py:370-375` (gán đè) → `public_dict` `:192-199` (không có khoá `duration_media`) → `engine.py:1291` | Sau một vòng round-trip qua snapshot, không ai phân biệt được số đó là `lengthSeconds` làm tròn hay số đo ffprobe. §3.1. |
| C5 | **`pham_vi_quet_s` không được lưu; phạm vi quét không tới bất kỳ artefact xuất nào** | Trường tại `engine.py:391`, đặt `:3095`; schema `jobs` `engine.py:874-878` không có cột; `bang_ngang.py:86` chỉ đọc `note` trên **nhánh lỗi** | Một lượt quét dừng sớm xuất ra CSV/Sheets/hồ sơ **không có dấu hiệu gì**. Cảnh báo tồn tại nhưng chỉ ở màn hình Streamlit (`app.py:396-407`). |
| C6 | **Lịch sử mất bốn trường của `Match`** | `save_job` `engine.py:3283-3287` vs `Match` `engine.py:334-347` | `ty_le`, `vung`, `clip_bat_dau_s`, `vung_khop_s` không tới `lichsu.db`. §6.6. |
| C7 | **`clip_offset_s` báo mốc video khi clamp bắn** | `engine.py:2507-2510` + `:2516`; cột "Khớp từ giây thứ (của clip)" `engine.py:3321`, giá trị `:3365` | Khi `t_clip > bat_dau`, `clip_offset_s` co về đúng `vung_khop_s` — một mốc trên trục **video** báo dưới nhãn "của clip". Chỉ một cột chẩn đoán; không ảnh hưởng phát hiện, xếp hạng hay link. |
| C8 | **Bảng ngang là exporter duy nhất lệch 3 giây giữa text và link** | `bang_ngang.py:63` vs `:64` | §6.4. Có chủ đích (`docs/EXECUTION_PLAN_E.md:68-70`) nhưng không có comment tại chỗ. |
| C9 | **`danh_sach_video` đọc tập nguồn metadata KHÁC hoàn toàn** | `danh_sach_video.py:376` — chỉ `clips_meta.json`, không snapshot | Tab "Danh sách video" có thể hiện tên **đã sửa** trong khi CSV/Sheets/hồ sơ hiện tên **cũ**. |
| C10 | **Hai schema báo cáo cùng nhắm vào một worksheet** | `sheets.py:95`, `:99`; app không truyền `worksheet=` (`app.py:224`) | Đổi định dạng đẩy Sheets giữa chừng làm dòng 16 ô rơi xuống dưới header 34 cột. |
| C11 | **`data/downloads` và `<kho>/_tam` là scratch dùng chung** | `engine.py:2093` (khoá theo video id); `channel.py:171` (khoá theo thư mục kho) | §5. Hai lượt quét/đồng bộ đồng thời có thể giẫm chân nhau. |
| C12 | **Bậc `filename` của `publication_date` là code chết** | `grep filename_date` → chỉ `publication_date.py:218,224` + tests | §8.3. Ngày suy từ tên file bị gán nhầm `confidence="medium"`. |
| C13 | **`Engine.duration_of` thiếu guard `isfinite`/`>0`** | `engine.py:994-1001` vs `channel.py:88`, `kiem_thoi_luong.py:51` | §7.5. |

### 9.2 LIKELY — cơ chế đọc được, điều kiện kích hoạt chưa tái hiện

| # | Điều gì | Bằng chứng | Vì sao chỉ là LIKELY |
|---|---|---|---|
| L1 | **`pham_vi_quet_s` báo thừa khi đường tắt Top-1 cắt ngắn một đoạn** | `_quet_tho` có thể chỉ khớp `chunks[:1]` rồi `return` (`engine.py:2764-2777`) nhưng `scan_media` vẫn ghi trọn cửa sổ đoạn: `da_quet_den = min(den, tong)` (`engine.py:3087`) | Chỉ xảy ra khi `top_n == 1` (`engine.py:2753`); mặc định là 5 (`engine.py:185`). Giá trị `top_n` thật trên máy vận hành **UNKNOWN** (§10). |
| L2 | **Ứng viên bù tốc độ có thể bị `_merge` xé nhỏ** | `align` của một match đã đổi tốc độ biến thiên tuyến tính theo thời gian (`engine.py:2368` + `:3033-3036`), nhưng nhóm gộp dùng dung sai **hằng** `dedup_s` (`engine.py:2468`, `:2478`) | Phép toán suy ra từ source, chưa chạy pipeline. Cần một match dài hơn `dedup_s/|1-r|` (~667 s ở r=1.03) mới lộ. |
| L3 | **Múi giờ rơi về UTC âm thầm nếu tên múi giờ không hợp lệ** | `_mui_gio` `publication_date.py:115-122` trả `ZoneInfo("UTC")` và chỉ ghi một `LOGGER.warning`; `confidence` vẫn `"high"`, `warnings` vẫn rỗng | Kích hoạt thực tế cần `--mui-gio` sai hoặc `TIMCLIP_MUI_GIO` sai — chưa tái hiện. `tzdata` **có mặt** trong `.venv` trên máy này. |
| L4 | **Một đoạn không cắt được chunk bị bỏ qua, đoạn sau ghi đè phạm vi** | `if not moi: continue` (`engine.py:3084-3085`) rồi `da_quet_den = min(den, tong)` ở đoạn sau (`engine.py:3087`) — một biến đơn điệu, không phải tập interval | Cần **mọi** ffmpeg trong một cửa sổ 3 giờ thất bại. Với lưới mặc định (bước 3420 s so với đoạn 10800 s) mỗi đoạn giữa luôn có ≥3 mốc. |

### 9.3 HYPOTHESIS — suy luận có căn cứ, chưa kiểm chứng được

| # | Điều gì | Vì sao chưa xác định được |
|---|---|---|
| H1 | Tần suất thực tế của trường hợp "lát giữa" ở §6.3 — tức bao nhiêu % match có `clip_offset_s` lớn | `lichsu.db` **có** lưu `clip_offset_s` (`engine.py:885`), nên phân bố này trả lời được — nhưng `data/` nằm ngoài phạm vi vòng audit này. |
| H2 | Liệu có snapshot nào trên máy đang thực sự lệch với `clips_meta.json` của nó (biến C1 từ tiềm ẩn thành đang xảy ra) | `python kiem_metadata_kho.py --json` là read-only theo thiết kế (`kiem_metadata_kho.py:290`, mở `lichsu.db` với `?mode=ro&immutable=1` tại `:82`) và sẽ trả lời trực tiếp. Không chạy vòng này. |
| H3 | Giá trị thật của `top_n`, `luoi_resample`, `luoi_tempo`, `max_matches` trong `data/cau_hinh.json` | Quyết định L1 và một phần §2 có tới được hay không. `CLAUDE.md:554` nói máy vận hành chạy `top_n: 1`, nhưng đó là **doc claim chưa kiểm chứng**; mặc định code là 5 (`engine.py:185`). |

---

## 10. Khoảng trống

Những thứ tài liệu này **không** trả lời được, kèm cách trả lời chúng.

| # | Không xác định được | Cách giải quyết |
|---|---|---|
| G1 | Cấu hình sống: `top_n`, `luoi_resample`, `luoi_tempo`, `max_matches`, `keep_downloads`, `min_hash_floor` | Đọc `data/cau_hinh.json`. Nằm ngoài phạm vi vòng này. Quyết định mức nghiêm trọng của L1 và §2/T0. |
| G2 | Có snapshot nào đang lệch với `clips_meta.json` không | `python kiem_metadata_kho.py --json`, đọc `audit.conflicts`. Read-only theo thiết kế. |
| G3 | Trạng thái schema và số dòng thật của `lichsu.db` | `sqlite3` với URI `?mode=ro&immutable=1`. |
| G4 | Có snapshot mồ côi nào cho kho đã bị xoá không | So `ls data/metadata/kho_*.json` với `_slug(ten)` của từng mục trong `khos.json`. |
| G5 | Tần suất thực tế của trường hợp "lát giữa" (H1) | Truy vấn phân bố `clip_offset_s` trong `matches`. |
| G6 | Va chạm ở §5 (`data/downloads`, `<kho>/_tam`) có thực sự làm hỏng file trên Windows không, hay lần `open` thứ hai fail trước | Cần hai tiến trình gọi `download_audio` cùng một id — cần mạng, ngoài phạm vi. |
| G7 | `--time-quantile` 0.05 dịch ra bao nhiêu giây trên dữ liệu thật | Cần chạy audfprint trên media thật, ngoài phạm vi. Ảnh hưởng cách đọc "MEASURED" trong §6.1. |

---

## Phụ lục — bất biến không được phá khi sửa luồng dữ liệu

Rút từ source, mỗi mục kèm nơi nó được thi hành. Đây là danh sách "đừng sửa nếu chưa đọc".

1. **`hhmmss` CẮT, không làm tròn** — `engine.py:430`. Phải song hành với `link_moc` cũng cắt
   (`engine.py:3338`, `:3341`).
2. **Chỉ `publication_date.format_publication_date` được sinh chuỗi `DD/MM/YYYY`** —
   `publication_date.py:251-264`, khoá bởi `tests/test_publication_date_exporters.py:90-102`.
3. **`_cut_chunks` tính lưới mốc từ giây 0 của cả file rồi mới LỌC theo cửa sổ** —
   `engine.py:2260-2265`. Làm nó tương đối với `tu_giay` sẽ khiến quét tăng dần và quét trọn
   bất đồng.
4. **Bản tải một phần phải giữ hậu tố `__p<giây>`** — `engine.py:2044-2052`, để
   `glob("<id>.*")` không bao giờ nhầm bản một phần là bản đầy đủ.
5. **`save_job` chạy TRƯỚC callback `on_video`** — `engine.py:3221` so với `:3252-3258`.
6. **`resolve_many` giữ nguyên thứ tự và duplicate** — `clip_metadata.py:961`, để đoạn *i*
   luôn ứng với video gốc *i*.
7. **Mọi ghi Google Sheets dùng `value_input_option="RAW"`** — `sheets.py:243` và ba chỗ khác.
8. **`ScanResult.pham_vi_quet_s` phải tách khỏi `duration_s`** — `engine.py:384-396`; và mọi
   thứ tính từ `duration_s` phải được rà lại khi `duration_s` bị sửa (`CLAUDE.md:448-449`).
9. **Bậc B của tầng chấp nhận chỉ THÊM, không bao giờ lấy đi ứng viên bậc A** —
   `chap_nhan_khop.py:93-96` `return` trước `:104`.
10. **Không được thêm `--sortbytime` vào lệnh match** — audfprint cắt theo `--max-matches`
    **sau khi** sắp lại, nên bật nó sẽ giữ dòng muộn nhất thay vì mạnh nhất
    (`engine.py:2289-2303`).
11. **Ngưỡng chấp nhận chỉ dùng `matched_s` và `hashes`, không bao giờ dùng thời lượng
    source/media** — `chap_nhan_khop.py:81-126`.
12. **Không trường nào mang giá trị bí mật được thêm vào `Config`** — `cau_hinh.lay_tu_config`
    serialise **mọi** trường không có allowlist (`cau_hinh.py:70-72`); đó là lý do
    `ytdlp_cookiefile` chỉ lưu **đường dẫn** (`engine.py:150`).
