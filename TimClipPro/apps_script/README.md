# Apps Script đi kèm Google Sheet

Đây là mã Google Apps Script chạy **trên Google Sheet**, không phải mã Python của
TimClipPro. Nó đọc sheet `KetQuaQuet` mà công cụ đẩy lên, rồi:

* xuất một hàng thành đoạn văn bản có cấu trúc sang sheet `Ket_Qua_Json`;
* tô màu link "đã quét" ở các bảng `Link SML` / `Link Cory`;
* dò link bị quét trùng; auto-fit chiều cao hàng; cập nhật bảng `Tổng quan`.

Giữ mã ở đây để nó được version cùng công cụ — vì hai bên có một **hợp đồng
chung**: thứ tự và tên 34 cột trong `bang_ngang.HEADER_NGANG`.

---

## Sự cố đã xử lý: `KetQuaQuet` mất hàng tiêu đề

**Triệu chứng**: bấm «📄 Xuất hàng đang chọn» thì hiện

> Không tìm thấy các cột bắt buộc: Thời gian quét, Link kênh vi phạm, …

**Nguyên nhân**: sheet `KetQuaQuet` không còn hàng tiêu đề — hàng 1 đang là dữ
liệu thật. Script cũ luôn coi hàng 1 là tiêu đề nên đi tìm tên cột trong một
hàng dữ liệu.

Công cụ chỉ ghi hàng tiêu đề **một lần**, lúc trang tính còn trống, và nhận biết
"đã có tiêu đề" bằng cách xem ô A1 có dữ liệu chưa. Một khi hàng tiêu đề bị xoá,
A1 thành dòng dữ liệu đầu tiên nên công cụ tưởng tiêu đề vẫn còn.

**Hai tính năng khác cũng hỏng vì lỗi này, nhưng hỏng IM LẶNG** — không báo gì:

| Tính năng | Biểu hiện |
|---|---|
| Đánh dấu link "đã quét" | `xayDungTapKhoaTuKetQuaQuet_` trả về tập RỖNG → **mọi** link ở `Link SML` / `Link Cory` bị tô về trắng như chưa từng quét |
| Dò link quét trùng | `danhDauTrungLapTrongKetQuaQuet_` thoát sớm → ngừng hoạt động hoàn toàn |

**Đã sửa ở ba lớp:**

1. `layCauTrucKetQuaQuet_()` (File 01) — tự nhận ra hàng 1 là tiêu đề hay dữ
   liệu. Nếu là dữ liệu thì đọc theo thứ tự cột gốc và coi hàng 1 là dòng dữ
   liệu đầu tiên. Mọi tính năng đọc `KetQuaQuet` đều đi qua đây.
2. Menu «🩹 Khôi phục hàng tiêu đề cho KetQuaQuet» — chèn lại hàng tiêu đề vĩnh
   viễn. Chỉ chèn thêm một hàng, không xoá/sửa dữ liệu nào.
3. Phía công cụ (`sheets.py`) — `append()` nay phân biệt được ba trạng thái của
   hàng 1: `trong` / `co` / `thieu`. Gặp `thieu` thì tự chèn lại hàng tiêu đề,
   nên sự cố không tái diễn.

---

## Cách cài

### Cách 1 — một file duy nhất (khuyến nghị)

Dùng **`TOAN_BO_AppsScript.gs`** — đã gộp sẵn cả 7 phần theo đúng thứ tự.

1. Mở Google Sheet → **Tiện ích mở rộng › Apps Script**.
2. **Xoá hết các tệp `.gs` cũ** trong dự án. Bắt buộc: cả dự án dùng chung một
   phạm vi biến toàn cục, để lẫn bản cũ sẽ báo lỗi trùng tên.
3. Tạo một tệp (ví dụ `Code.gs`), dán toàn bộ nội dung, **Lưu**.
4. Quay lại Sheet, **tải lại trang (F5)**.
5. Chạy menu «🩹 Khôi phục hàng tiêu đề cho KetQuaQuet» một lần.
6. Chạy menu «⚙️ Cài đặt tự động hoá» một lần.

### Cách 2 — giữ nhiều tệp như cũ

Dán từng file vào đúng tệp tương ứng:

| Tệp ở đây | Thay cho | Đổi gì |
|---|---|---|
| `File01_CauHinh_TienIch.gs` | File 01 | thứ tự cột dự phòng, `layCauTrucKetQuaQuet_()`, `MAU_XUAT` |
| `File02_Menu.gs` | File 02 | thêm menu khôi phục hàng tiêu đề |
| `File03_XuatHangDaChon.gs` | File 03 | sửa lỗi cột + **bản mẫu xuất mới** |
| `File04_DanhDauLinkDaQuet.gs` | File 04 | sửa hai tính năng hỏng im lặng |
| `File05_CanChieuCaoHang.gs` | File 05 | không đổi (chép lại để bộ file đầy đủ) |
| `File06_TuDongHoa.gs` | File 06 | thêm nhắc khi sheet thiếu hàng tiêu đề |
| `File07_TongQuan_TienIchBoSung.gs` | File 07 | đếm đúng số dòng, cảnh báo trên bảng Tổng quan |

`TOAN_BO_AppsScript.gs` được **sinh ra từ 7 tệp trên**, không sửa tay. Đổi gì thì
sửa ở tệp gốc rồi gộp lại, để hai bên không lệch nhau.

---

## Bản mẫu xuất

Mỗi tiêu đề mục có một dòng trống ngay sau nó. Đoạn vi phạm tách thành mục
riêng, danh sách video gốc lùi xuống mục kế tiếp:

```
1. Thông tin chi tiết chanel vi phạm :

Link kênh vi phạm : …,
Tên kênh vi phạm : …,
Id kênh vi phạm : …,

2. Thông tin chi tiết video vi phạm :

Link video vi phạm : …,
Tên video vi phạm : …,
Thời lượng video vi phạm : …,
Ngày đăng video vi phạm : …,

3. Đoạn vi phạm 1 trong video vi phạm : …,

4. Danh sách các video gốc :

Link video gốc 1 : …,
Tên video gốc 1 : …,
Ngày đăng video gốc 1 : …,
Thời lượng video gốc 1 : …,
```

Số mục được đánh **động**: hàng nào không có đoạn vi phạm nào thì «Danh sách các
video gốc» lùi lên thành mục 3 — đoạn văn bản không bao giờ nhảy số.

### Hai dòng đã bỏ khỏi bản mẫu

Bản mẫu mới **không** in hai dòng sau. Muốn lấy lại, sửa `MAU_XUAT` ở đầu File 01
(`false` → `true`), phần đánh số mục tự điều chỉnh theo:

```js
const MAU_XUAT = Object.freeze({
  HIEN_THOI_GIAN_QUET: false,  // "Thời gian quét : …" ở đầu
  HIEN_TONG_SO_DOAN: false     // "Tổng số đoạn video gốc phát hiện : …" ở cuối
});
```

---

## Khi công cụ đổi cột

`KETQUAQUET_COT_MAC_DINH` trong File 01 phải khớp **đúng thứ tự** với
`bang_ngang.HEADER_NGANG` của công cụ. Đổi cột bên công cụ thì sửa cả hai nơi —
nếu không, lớp đọc dự phòng sẽ đọc lệch cột khi sheet thiếu hàng tiêu đề.

Lưu ý: cột `Trạng thái` là cột **bạn tự thêm**, công cụ không ghi ra nó nên nó
không nằm trong danh sách trên. Vì vậy menu «🏷️ Chuẩn hoá cột Trạng thái» yêu cầu
sheet phải có hàng tiêu đề thật thì mới chạy — đoán vị trí cột đó sẽ có nguy cơ
ghi đè nhầm một cột dữ liệu.
