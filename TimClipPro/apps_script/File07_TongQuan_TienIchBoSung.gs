/**
 * ============================================================================
 * FILE 07 — BẢNG TỔNG QUAN & TIỆN ÍCH BỔ SUNG
 * ============================================================================
 * Bảng "Tổng quan" hiển thị nhanh tiến độ quét mà không cần cuộn qua hàng
 * nghìn dòng dữ liệu. Toàn bộ số liệu trên bảng này do SCRIPT ghi trực tiếp
 * (không dùng công thức) và được làm mới mỗi khi tự động hoá chạy (theo
 * lịch, khi bạn tự sửa dữ liệu, hoặc khi bấm "🔄 Cập nhật ngay") — lý do
 * không dùng công thức sống (COUNTIF/COUNTA tham chiếu chéo sheet) là vì
 * với hàng chục nghìn dòng, công thức kiểu đó sẽ làm chậm toàn bộ bảng
 * tính mỗi khi có bất kỳ thay đổi nào, kể cả ở nơi không liên quan.
 *
 * 🔧 ĐÃ SỬA: "Tổng số dòng kết quả" trước đây luôn lấy lastRow - 1 (giả định
 * luôn có hàng tiêu đề). Khi sheet mất hàng tiêu đề, con số bị thiếu đúng 1
 * dòng. Nay tính theo hàng dữ liệu đầu tiên thật sự, và thêm một dòng cảnh
 * báo ngay trên bảng khi phát hiện thiếu hàng tiêu đề.
 */

function capNhatTongQuan_(thongKeDanhDau, thongKeChieuCao) {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const sheet = layHoacTaoSheetTongQuan_(ss);

  const tz = ss.getSpreadsheetTimeZone() || Session.getScriptTimeZone();
  const capNhatLuc = Utilities.formatDate(thongKeDanhDau.thoiGianCapNhat, tz, 'dd/MM/yyyy HH:mm:ss');
  const cauTruc = thongKeDanhDau.cauTrucKetQuaQuet || layCauTrucKetQuaQuet_(ss);

  const hang = [];
  hang.push(['TỔNG QUAN HỆ THỐNG QUÉT VI PHẠM', '']);
  hang.push(['Cập nhật lần cuối', capNhatLuc]);
  hang.push(['', '']);

  if (cauTruc.tonTai && cauTruc.dungDuPhong) {
    hang.push(['⚠️ CẢNH BÁO CẤU TRÚC', '']);
    hang.push(['Sheet KetQuaQuet đang thiếu hàng tiêu đề', 'Đang đọc theo thứ tự cột gốc']);
    hang.push(['Cách khắc phục', 'Menu > 🩹 Khôi phục hàng tiêu đề']);
    hang.push(['', '']);
  }

  hang.push(['— KẾT QUẢ QUÉT (KetQuaQuet) —', '']);
  // Đếm theo hàng dữ liệu đầu tiên THẬT SỰ, không giả định luôn có tiêu đề.
  const tongDongKetQua = cauTruc.tonTai
    ? Math.max(cauTruc.sheet.getLastRow() - cauTruc.hangDauDuLieu + 1, 0)
    : 0;
  hang.push(['Tổng số dòng kết quả', tongDongKetQua]);
  hang.push(['Số dòng nghi bị quét trùng (>1 lần)', thongKeDanhDau.trungLapKetQuaQuet.tongDongTrungLap]);
  hang.push(['', '']);

  thongKeDanhDau.theoBang.forEach(function (s) {
    hang.push(['— BẢNG "' + s.sheetName + '" —', '']);
    if (!s.tonTai) {
      hang.push(['(Không tìm thấy sheet này)', '']);
    } else {
      hang.push(['Tổng số link nhận diện được', s.tongLink]);
      hang.push(['Đã quét (khớp với KetQuaQuet)', s.daQuet]);
      hang.push(['Chưa quét / đang chờ', s.choXuLy]);
      hang.push(['Tỉ lệ đã quét', s.tongLink > 0 ? (Math.round((s.daQuet / s.tongLink) * 1000) / 10 + '%') : '—']);
    }
    hang.push(['', '']);
  });

  hang.push(['— TỰ ĐỘNG CĂN CHỈNH CHIỀU CAO —', '']);
  (thongKeChieuCao || []).forEach(function (s) {
    hang.push(['Dòng mới vừa được auto-fit (' + s.sheetName + ')', s.soDongDaFit]);
  });

  const soHangCu = sheet.getMaxRows();
  if (soHangCu > 0) {
    sheet.getRange(1, 1, soHangCu, 2).clearContent().setBackground(null).setFontWeight('normal');
  }
  sheet.getRange(1, 1, hang.length, 2).setValues(hang);

  dinhDangSheetTongQuan_(sheet, hang.length);
}

function layHoacTaoSheetTongQuan_(ss) {
  let sheet = ss.getSheetByName('Tổng quan');
  if (!sheet) {
    sheet = ss.insertSheet('Tổng quan', 0); // chèn làm sheet đầu tiên cho dễ thấy
  }
  return sheet;
}

function dinhDangSheetTongQuan_(sheet, soHang) {
  sheet.setColumnWidth(1, 320);
  sheet.setColumnWidth(2, 220);

  const full = sheet.getRange(1, 1, soHang, 2);
  full.setFontFamily('Arial').setFontSize(10).setVerticalAlignment('middle');

  sheet.getRange(1, 1, 1, 2).merge()
    .setFontSize(14).setFontWeight('bold')
    .setBackground('#1f4e78').setFontColor('#ffffff')
    .setHorizontalAlignment('center');
  sheet.setRowHeight(1, 30);

  const nhanCot1 = sheet.getRange(1, 1, soHang, 1).getValues();
  for (let i = 1; i < nhanCot1.length; i++) { // bỏ qua hàng 0 (tiêu đề lớn, đã merge)
    const text = String(nhanCot1[i][0] || '');
    if (text.indexOf('—') === 0) {
      sheet.getRange(i + 1, 1, 1, 2).setFontWeight('bold').setBackground('#f3f3f3');
    } else if (text.indexOf('⚠️') === 0) {
      sheet.getRange(i + 1, 1, 1, 2)
        .setFontWeight('bold')
        .setBackground(MAU_SAC.CANH_BAO_NEN)
        .setFontColor(MAU_SAC.CANH_BAO_CHU);
    }
  }

  sheet.setFrozenRows(1);
}

/**
 * Hàm menu "📊 Mở bảng Tổng quan" — làm mới số liệu rồi mở sheet.
 */
function moBangTongQuan() {
  const ui = SpreadsheetApp.getUi();
  const lock = layKhoaAnToan_(20000);
  if (!lock) {
    ui.alert('Đang có một tiến trình khác chạy, vui lòng thử lại sau ít phút.');
    return;
  }
  try {
    const thongKeDanhDau = danhDauLinkDaQuetTatCa_();
    const thongKeChieuCao = capNhatChieuCaoTatCa_();
    capNhatTongQuan_(thongKeDanhDau, thongKeChieuCao);
    layHoacTaoSheetTongQuan_(SpreadsheetApp.getActiveSpreadsheet()).activate();
  } finally {
    lock.releaseLock();
  }
}

// =============================================================================
// TIỆN ÍCH BỔ SUNG: CHUẨN HOÁ CỘT "TRẠNG THÁI" TRONG KetQuaQuet
// =============================================================================
// Phát hiện thấy dữ liệu hiện có bị lệch cách viết hoa/thường ("đã làm" và
// "Đã làm" đang được tính là 2 giá trị khác nhau). Hàm dưới đây sửa các ô
// hiện có về một cách viết thống nhất, và thêm danh sách thả xuống để tránh
// lặp lại vấn đề này về sau. Muốn thêm trạng thái mới, chỉ cần thêm vào
// mảng DANH_SACH_TRANG_THAI_HOP_LE bên dưới rồi chạy lại menu này.
const DANH_SACH_TRANG_THAI_HOP_LE = ['đã làm', 'đã xong'];
const SO_HANG_AP_DUNG_VALIDATION_TRANG_THAI = 5000;

function thietLapChuanHoaTrangThai() {
  const ui = SpreadsheetApp.getUi();
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const cauTruc = layCauTrucKetQuaQuet_(ss);

  if (!cauTruc.tonTai) {
    ui.alert('Không tìm thấy sheet "' + KET_QUA_JSON_CONFIG.SOURCE_SHEET_NAME + '".');
    return;
  }

  // Cột "Trạng thái" là cột BẠN TỰ THÊM, công cụ không ghi ra nó nên nó
  // KHÔNG có trong thứ tự cột dự phòng. Khi sheet mất hàng tiêu đề thì
  // không có cách nào biết chắc nó nằm ở đâu — nói thẳng thay vì đoán bừa
  // rồi ghi đè nhầm một cột dữ liệu thật.
  if (cauTruc.dungDuPhong) {
    ui.alert(
      'Cần khôi phục hàng tiêu đề trước',
      'Cột "' + KET_QUA_JSON_FIELDS.STATUS + '" là cột bạn tự thêm nên chỉ nhận ' +
      'ra được qua TÊN TIÊU ĐỀ.\n\n' + nhacMatHangTieuDe_(),
      ui.ButtonSet.OK
    );
    return;
  }

  const sheet = cauTruc.sheet;
  const lastRow = sheet.getLastRow();
  const colIndex = cauTruc.columnMap[chuanHoaTieuDe_(KET_QUA_JSON_FIELDS.STATUS)];

  if (colIndex === undefined) {
    ui.alert('Không tìm thấy cột "' + KET_QUA_JSON_FIELDS.STATUS + '" trong ' + KET_QUA_JSON_CONFIG.SOURCE_SHEET_NAME + '.');
    return;
  }

  let soDaSua = 0;
  if (lastRow >= cauTruc.hangDauDuLieu) {
    const soDong = lastRow - cauTruc.hangDauDuLieu + 1;
    const range = sheet.getRange(cauTruc.hangDauDuLieu, colIndex + 1, soDong, 1);
    const values = range.getValues();
    for (let i = 0; i < values.length; i++) {
      const v = String(values[i][0] || '').trim();
      if (!v) continue;
      const chuan = chuanHoaKhoaVanBan_(v);
      if (DANH_SACH_TRANG_THAI_HOP_LE.indexOf(chuan) !== -1 && chuan !== v) {
        values[i][0] = chuan;
        soDaSua++;
      }
    }
    range.setValues(values);
  }

  const ruleValidation = SpreadsheetApp.newDataValidation()
    .requireValueInList(DANH_SACH_TRANG_THAI_HOP_LE, true)
    .setAllowInvalid(false)
    .setHelpText('Chọn 1 trạng thái trong danh sách để tránh gõ sai/không đồng nhất.')
    .build();

  sheet.getRange(cauTruc.hangDauDuLieu, colIndex + 1, SO_HANG_AP_DUNG_VALIDATION_TRANG_THAI, 1)
    .setDataValidation(ruleValidation);

  ui.alert(
    'Đã chuẩn hoá cột "Trạng thái" ✅',
    'Đã sửa ' + soDaSua + ' ô bị lệch cách viết hoa/thường.\n' +
    'Đã thêm danh sách thả xuống cho ' + SO_HANG_AP_DUNG_VALIDATION_TRANG_THAI + ' hàng ' +
    '(tự áp dụng cho cả các dòng mới thêm sau này).\n\n' +
    'Danh sách hợp lệ hiện tại: ' + DANH_SACH_TRANG_THAI_HOP_LE.join(', ') + '.\n' +
    'Muốn thêm trạng thái khác? Sửa mảng DANH_SACH_TRANG_THAI_HOP_LE trong code (file 07) rồi chạy lại menu này.',
    ui.ButtonSet.OK
  );
}
