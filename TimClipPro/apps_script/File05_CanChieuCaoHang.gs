/**
 * ============================================================================
 * FILE 05 — TÍNH NĂNG 2: TỰ ĐỘNG CĂN CHỈNH CHIỀU CAO HÀNG
 * ============================================================================
 * VÌ SAO KHÔNG THỂ "TỨC THỜI" KHI CÔNG CỤ NGOÀI ĐẨY DỮ LIỆU VÀO?
 * Google Sheets CHỈ kích hoạt onEdit/onChange khi CON NGƯỜI thao tác trực
 * tiếp trên giao diện (hoặc một add-on chạy thay mặt người dùng) — các
 * trigger này KHÔNG chạy khi dữ liệu được ghi vào qua Sheets API / một công
 * cụ bên ngoài, kể cả với trigger "installable". Đây là giới hạn của nền
 * tảng Google Sheets, không phải do cách viết script.
 *
 * Vì vậy cách khả thi để "tự động hoá" việc này là dùng trigger CHẠY THEO
 * LỊCH (time-driven, xem file 06): cứ mỗi vài phút kiểm tra một lần xem có
 * dòng mới hay không rồi mới auto-fit. Có độ trễ tối đa bằng khoảng cách
 * giữa 2 lần chạy (mặc định 10 phút, xem CAI_DAT_TU_DONG.SO_PHUT_LAP_LAI ở
 * file 01) — nhưng đây là cách DUY NHẤT hoạt động đáng tin cậy với dữ liệu
 * đến từ bên ngoài.
 *
 * Phần dưới đây chỉ là phần LÕI xử lý. Để không bị chậm dần khi dữ liệu
 * ngày càng nhiều, script KHÔNG quét lại toàn bộ sheet mỗi lần chạy — nó
 * nhớ "đã xử lý tới dòng nào" bằng PropertiesService, và mỗi lần chỉ
 * auto-fit phần DÒNG MỚI được thêm vào kể từ lần chạy trước.
 */

function capNhatChieuCaoTatCa_() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  return SHEETS_TU_DONG_CAN_CHIEU_CAO.map(function (tenSheet) {
    return capNhatChieuCaoTheoTang_(ss, tenSheet, false);
  });
}

/**
 * Auto-fit phần dòng MỚI (kể từ lần chạy trước) của một sheet.
 * @param {boolean} buocChayLai Nếu true, bỏ qua mốc đã lưu và fit lại TOÀN
 *    BỘ dữ liệu hiện có (dùng cho lần cài đặt tự động hoá đầu tiên).
 */
function capNhatChieuCaoTheoTang_(ss, tenSheet, buocChayLai) {
  const thongKe = { sheetName: tenSheet, tonTai: false, soDongDaFit: 0 };
  const sheet = ss.getSheetByName(tenSheet);
  if (!sheet) return thongKe;
  thongKe.tonTai = true;

  const lastRow = sheet.getLastRow();
  const props = PropertiesService.getDocumentProperties();
  const key = CAI_DAT_TU_DONG.KHOA_THUOC_TINH_DA_XU_LY + tenSheet;

  let lastProcessed = buocChayLai ? 1 : Number(props.getProperty(key) || 1);
  if (!lastProcessed || lastProcessed < 1) lastProcessed = 1;

  // Nếu có dòng bị xoá khiến lastRow nhỏ hơn/bằng mốc đã lưu, cập nhật lại
  // mốc cho an toàn (tránh truyền số dòng âm/0 cho autoResizeRows).
  if (lastRow <= lastProcessed) {
    props.setProperty(key, String(Math.max(lastRow, 1)));
    return thongKe;
  }

  const startRow = lastProcessed + 1;
  const numRows = lastRow - lastProcessed;

  canChinhChieuCaoChoVung_(sheet, startRow, numRows);

  props.setProperty(key, String(lastRow));
  thongKe.soDongDaFit = numRows;
  return thongKe;
}

/**
 * Auto-fit + thêm đệm cho một vùng hàng cụ thể — dùng đúng cơ chế trong hàm
 * fitAllRowHeightsWithPadding() gốc của bạn, chỉ khác là chỉ áp dụng cho
 * một khoảng hàng thay vì toàn bộ sheet mỗi lần.
 */
function canChinhChieuCaoChoVung_(sheet, startRow, numRows) {
  if (numRows <= 0) return;
  sheet.autoResizeRows(startRow, numRows);

  const padding = CAI_DAT_TU_DONG.KHOANG_DEM_CHIEU_CAO_PX;
  for (let r = startRow; r < startRow + numRows; r++) {
    const currentHeight = sheet.getRowHeight(r);
    sheet.setRowHeight(r, currentHeight + padding);
  }
}

/**
 * Giữ lại nguyên bản hàm gốc của bạn để vẫn có thể chạy thủ công bất cứ lúc
 * nào — căn chỉnh lại TOÀN BỘ sheet ĐANG MỞ (không chỉ phần dòng mới, và
 * không cập nhật mốc theo dõi của trigger tự động).
 */
function fitAllRowHeightsWithPadding(extraPixels) {
  const sheet = SpreadsheetApp.getActiveSheet();
  const lastRow = sheet.getLastRow();
  if (lastRow === 0) return;

  sheet.autoResizeRows(1, lastRow);

  const padding = extraPixels || CAI_DAT_TU_DONG.KHOANG_DEM_CHIEU_CAO_PX;
  for (let r = 1; r <= lastRow; r++) {
    const currentHeight = sheet.getRowHeight(r);
    sheet.setRowHeight(r, currentHeight + padding);
  }
}
