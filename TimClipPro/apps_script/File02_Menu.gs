/**
 * ============================================================================
 * FILE 02 — MENU
 * ============================================================================
 * Nếu dự án Apps Script của bạn có nhiều tệp, CHỈ được có DUY NHẤT một hàm
 * onOpen() trong toàn bộ dự án — vì vậy đây là nơi duy nhất khai báo menu.
 * Nếu bạn dán các file này vào một dự án đã có sẵn onOpen() khác, hãy gộp
 * nội dung addItem(...) bên dưới vào onOpen() hiện có thay vì giữ cả hai.
 */
function onOpen() {
  SpreadsheetApp.getUi()
    .createMenu('CHUYỂN ĐỔI DỮ LIỆU')
    .addItem('📄 Xuất hàng đang chọn', 'xuatHangDaChonSangKetQuaJson')
    .addItem('📂 Mở bảng Ket_Qua_Json', 'moBangKetQuaJson')
    .addSeparator()
    .addItem('🔄 Cập nhật ngay (đánh dấu link + auto-fit)', 'chayCapNhatNgay')
    .addItem('📊 Mở bảng Tổng quan', 'moBangTongQuan')
    .addSeparator()
    .addItem('⚙️ Cài đặt tự động hoá', 'thietLapTuDongHoa')
    .addItem('🔍 Kiểm tra trạng thái tự động hoá', 'kiemTraTrangThaiTuDongHoa')
    .addItem('🛑 Tắt tự động hoá', 'tatTuDongHoa')
    .addSeparator()
    .addItem('🩹 Khôi phục hàng tiêu đề cho KetQuaQuet', 'khoiPhucHangTieuDeKetQuaQuet')
    .addItem('🏷️ Chuẩn hoá cột "Trạng thái"', 'thietLapChuanHoaTrangThai')
    .addToUi();
}

/**
 * Chèn lại hàng tiêu đề đã mất cho sheet KetQuaQuet.
 *
 * VÌ SAO CẦN: công cụ TimClipPro chỉ ghi hàng tiêu đề MỘT LẦN, lúc trang
 * tính còn trống. Nó nhận biết "đã có tiêu đề" bằng cách xem ô A1 có dữ
 * liệu hay chưa — nên một khi hàng tiêu đề bị xoá, ô A1 trở thành dòng dữ
 * liệu đầu tiên và công cụ sẽ KHÔNG BAO GIỜ ghi lại tiêu đề nữa.
 *
 * Không có tiêu đề thì ba tính năng hỏng cùng lúc: xuất hàng đang chọn báo
 * lỗi đỏ, còn đánh dấu "đã quét" và dò trùng lặp hỏng ÂM THẦM (coi như
 * không có link nào từng được quét). Script đã có lớp đọc dự phòng theo thứ
 * tự cột nên vẫn chạy đúng, nhưng khôi phục hàng tiêu đề vẫn tốt hơn: sau
 * đó bạn chèn/xoá/di chuyển cột tuỳ ý mà không lo hỏng.
 */
function khoiPhucHangTieuDeKetQuaQuet() {
  const ui = SpreadsheetApp.getUi();
  const lock = layKhoaAnToan_(20000);
  if (!lock) {
    ui.alert('Đang có một tiến trình khác chạy, vui lòng thử lại sau ít phút.');
    return;
  }

  try {
    const ss = SpreadsheetApp.getActiveSpreadsheet();
    const cauTruc = layCauTrucKetQuaQuet_(ss);

    if (!cauTruc.tonTai) {
      ui.alert('Không tìm thấy sheet "' + KET_QUA_JSON_CONFIG.SOURCE_SHEET_NAME + '".');
      return;
    }

    if (!cauTruc.dungDuPhong) {
      ui.alert(
        'Không cần khôi phục ✅',
        'Sheet "' + KET_QUA_JSON_CONFIG.SOURCE_SHEET_NAME + '" đã có hàng tiêu đề ' +
        '(nhận ra ' + cauTruc.soCotNhanRa + ' tên cột ở hàng 1).',
        ui.ButtonSet.OK
      );
      return;
    }

    const sheet = cauTruc.sheet;
    const soCotHienCo = sheet.getLastColumn();
    const soCotChuan = KETQUAQUET_COT_MAC_DINH.length;
    const soCotThua = Math.max(soCotHienCo - soCotChuan, 0);

    const traLoi = ui.alert(
      'Khôi phục hàng tiêu đề?',
      'Sẽ CHÈN THÊM một hàng mới lên trên cùng của sheet "' +
      KET_QUA_JSON_CONFIG.SOURCE_SHEET_NAME + '" và điền ' + soCotChuan +
      ' tên cột gốc của công cụ.\n\n' +
      '• Không xoá và không sửa bất kỳ dữ liệu nào đang có.\n' +
      '• Toàn bộ dữ liệu bị đẩy xuống 1 hàng (dòng đầu hiện tại thành hàng 2).\n' +
      (soCotThua > 0
        ? ('• ' + soCotThua + ' cột bạn tự thêm phía sau (ví dụ "Trạng thái") sẽ ' +
           'ĐỂ TRỐNG ô tiêu đề — bạn tự gõ tên cho chúng sau khi chạy xong.\n')
        : '') +
      '\nTiếp tục?',
      ui.ButtonSet.YES_NO
    );
    if (traLoi !== ui.Button.YES) return;

    sheet.insertRowBefore(1);

    const hangTieuDe = KETQUAQUET_COT_MAC_DINH.slice();
    sheet.getRange(1, 1, 1, hangTieuDe.length).setValues([hangTieuDe]);
    sheet.getRange(1, 1, 1, Math.max(soCotHienCo, hangTieuDe.length))
      .setFontWeight('bold')
      .setBackground('#1f4e78')
      .setFontColor('#ffffff')
      .setVerticalAlignment('middle');
    sheet.setFrozenRows(1);

    // Mốc auto-fit đang đếm theo số hàng; chèn thêm một hàng làm lệch mốc.
    // Đặt lại để lần chạy tới fit đúng phần dòng mới thay vì bỏ sót một dòng.
    PropertiesService.getDocumentProperties().deleteProperty(
      CAI_DAT_TU_DONG.KHOA_THUOC_TINH_DA_XU_LY + KET_QUA_JSON_CONFIG.SOURCE_SHEET_NAME
    );

    ui.alert(
      'Đã khôi phục hàng tiêu đề ✅',
      'Đã chèn ' + hangTieuDe.length + ' tên cột vào hàng 1 và cố định hàng đó.\n\n' +
      (soCotThua > 0
        ? ('Nhớ gõ tên cho ' + soCotThua + ' cột bạn tự thêm ở phía sau ' +
           '(cột thứ ' + (soCotChuan + 1) + ' trở đi).\n\n')
        : '') +
      'Từ giờ bạn có thể chèn/xoá/di chuyển cột tuỳ ý — script đọc theo TÊN ' +
      'cột nên không bị vỡ.',
      ui.ButtonSet.OK
    );
  } catch (err) {
    ui.alert('Không thể khôi phục hàng tiêu đề.\n\nChi tiết lỗi: ' + err.message);
    throw err;
  } finally {
    lock.releaseLock();
  }
}
