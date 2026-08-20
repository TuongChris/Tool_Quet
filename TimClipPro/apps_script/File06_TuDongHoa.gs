/**
 * ============================================================================
 * FILE 06 — CÀI ĐẶT / QUẢN LÝ TỰ ĐỘNG HOÁ (TRIGGER)
 * ============================================================================
 * Chỉ cần chạy thietLapTuDongHoa() (qua menu "⚙️ Cài đặt tự động hoá") MỘT
 * LẦN DUY NHẤT. Lần đầu chạy, Google sẽ hỏi cấp quyền — đây là bước bình
 * thường (script cần quyền chỉnh sửa chính bảng tính này và quyền tạo
 * trigger). Sau đó mọi thứ tự chạy theo lịch, không cần mở lại Apps Script.
 */

/**
 * Bật tự động hoá: tạo trigger theo lịch + trigger onEdit, dọn rule định
 * dạng có điều kiện kiểu cũ, và chạy đầy đủ một lượt ngay để có kết quả
 * tức thì thay vì phải chờ tới lần chạy theo lịch đầu tiên.
 */
function thietLapTuDongHoa() {
  const ui = SpreadsheetApp.getUi();
  const lock = layKhoaAnToan_(20000);
  if (!lock) {
    ui.alert('Đang có một tiến trình khác chạy, vui lòng thử lại sau ít phút.');
    return;
  }

  try {
    const ss = SpreadsheetApp.getActiveSpreadsheet();

    xoaTriggerCuaDuAn_();

    ScriptApp.newTrigger(CAI_DAT_TU_DONG.TEN_HAM_TRIGGER_LICH)
      .timeBased()
      .everyMinutes(CAI_DAT_TU_DONG.SO_PHUT_LAP_LAI)
      .create();

    ScriptApp.newTrigger(CAI_DAT_TU_DONG.TEN_HAM_TRIGGER_ON_EDIT)
      .forSpreadsheet(ss)
      .onEdit()
      .create();

    let soRuleDaXoa = 0;
    DANG_KY_BANG_LIEN_KET.forEach(function (dangKy) {
      const sheet = ss.getSheetByName(dangKy.sheetName);
      if (sheet) soRuleDaXoa += xoaQuyTacDinhDangCuLienQuanKetQuaQuet_(sheet);
    });

    const thongKeDanhDau = danhDauLinkDaQuetTatCa_();
    const thongKeChieuCao = SHEETS_TU_DONG_CAN_CHIEU_CAO.map(function (tenSheet) {
      return capNhatChieuCaoTheoTang_(ss, tenSheet, true); // true = fit lại toàn bộ dữ liệu hiện có
    });
    capNhatTongQuan_(thongKeDanhDau, thongKeChieuCao);

    const dsBangLienKet = DANG_KY_BANG_LIEN_KET.map(function (d) { return d.sheetName; }).join(', ');
    const dsSheetChieuCao = SHEETS_TU_DONG_CAN_CHIEU_CAO.join(', ');

    ui.alert(
      'Đã bật tự động hoá ✅',
      'Cứ mỗi ' + CAI_DAT_TU_DONG.SO_PHUT_LAP_LAI + ' phút, hệ thống sẽ tự động:\n' +
      '  • Đánh dấu link đã quét trên: ' + dsBangLienKet + '\n' +
      '  • Tự căn chỉnh chiều cao hàng mới trên: ' + dsSheetChieuCao + '\n\n' +
      'Khi bạn tự sửa/dán dữ liệu trực tiếp trên Google Sheets, hệ thống cũng\n' +
      'sẽ cập nhật gần như ngay lập tức (không cần chờ 10 phút).\n\n' +
      (soRuleDaXoa > 0
        ? ('Đã dọn ' + soRuleDaXoa + ' rule định dạng có điều kiện kiểu cũ không còn cần thiết.\n\n')
        : '') +
      (thongKeDanhDau.cauTrucKetQuaQuet && thongKeDanhDau.cauTrucKetQuaQuet.dungDuPhong
        ? ('⚠️ ' + nhacMatHangTieuDe_() + '\n\n')
        : '') +
      'Xem số liệu chi tiết tại menu "📊 Mở bảng Tổng quan".',
      ui.ButtonSet.OK
    );
  } catch (err) {
    ui.alert('Không thể cài đặt tự động hoá.\n\nChi tiết lỗi: ' + err.message);
    throw err;
  } finally {
    lock.releaseLock();
  }
}

/**
 * Tắt tự động hoá — gỡ toàn bộ trigger do dự án này tạo.
 */
function tatTuDongHoa() {
  const ui = SpreadsheetApp.getUi();
  const soLuong = xoaTriggerCuaDuAn_();
  ui.alert(
    soLuong > 0
      ? ('Đã tắt tự động hoá — đã gỡ ' + soLuong + ' trigger.')
      : 'Hiện không có trigger tự động nào đang bật.'
  );
}

function xoaTriggerCuaDuAn_() {
  const tenHamCuaDuAn = [
    CAI_DAT_TU_DONG.TEN_HAM_TRIGGER_LICH,
    CAI_DAT_TU_DONG.TEN_HAM_TRIGGER_ON_EDIT
  ];
  const triggers = ScriptApp.getProjectTriggers();
  let soLuong = 0;
  triggers.forEach(function (trigger) {
    if (tenHamCuaDuAn.indexOf(trigger.getHandlerFunction()) !== -1) {
      ScriptApp.deleteTrigger(trigger);
      soLuong++;
    }
  });
  return soLuong;
}

/**
 * Kiểm tra nhanh xem tự động hoá đang bật hay tắt.
 */
function kiemTraTrangThaiTuDongHoa() {
  const ui = SpreadsheetApp.getUi();
  const tenHamCuaDuAn = [
    CAI_DAT_TU_DONG.TEN_HAM_TRIGGER_LICH,
    CAI_DAT_TU_DONG.TEN_HAM_TRIGGER_ON_EDIT
  ];
  const dangBat = ScriptApp.getProjectTriggers().filter(function (t) {
    return tenHamCuaDuAn.indexOf(t.getHandlerFunction()) !== -1;
  });

  if (dangBat.length === 0) {
    ui.alert(
      'Tự động hoá: CHƯA BẬT ❌',
      'Chọn menu "⚙️ Cài đặt tự động hoá" để bật.',
      ui.ButtonSet.OK
    );
    return;
  }

  const moTa = dangBat.map(function (t) {
    return t.getHandlerFunction() === CAI_DAT_TU_DONG.TEN_HAM_TRIGGER_LICH
      ? '  • Chạy theo lịch: mỗi ' + CAI_DAT_TU_DONG.SO_PHUT_LAP_LAI + ' phút'
      : '  • Chạy khi chỉnh sửa trực tiếp trên Sheets (gần như tức thời)';
  }).join('\n');

  ui.alert(
    'Tự động hoá: ĐANG BẬT ✅',
    moTa + '\n\nMẹo: xem lịch sử chạy & lỗi (nếu có) tại trình soạn thảo Apps Script\n' +
    '→ mục "Executions" (Lượt thực thi) ở thanh bên trái.',
    ui.ButtonSet.OK
  );
}

/**
 * Hàm được trigger CHẠY THEO LỊCH gọi (đăng ký trong thietLapTuDongHoa()).
 * Bọc try/catch để một lỗi bất ngờ không làm hỏng các lần chạy sau — Apps
 * Script sẽ tự gửi email cảnh báo cho bạn nếu hàm này lỗi liên tục.
 */
function capNhatTuDongTheoLich() {
  const lock = layKhoaAnToan_(25000);
  if (!lock) return; // đang có tiến trình khác chạy, bỏ qua lượt này — lượt sau sẽ tự bắt kịp

  try {
    const thongKeDanhDau = danhDauLinkDaQuetTatCa_();
    const thongKeChieuCao = capNhatChieuCaoTatCa_();
    capNhatTongQuan_(thongKeDanhDau, thongKeChieuCao);
  } catch (err) {
    Logger.log('Lỗi capNhatTuDongTheoLich: ' + err.message);
  } finally {
    lock.releaseLock();
  }
}

/**
 * Hàm menu "🔄 Cập nhật ngay" — chạy thủ công, có thông báo kết quả.
 */
function chayCapNhatNgay() {
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

    const dongDaFit = thongKeChieuCao.reduce(function (sum, s) { return sum + s.soDongDaFit; }, 0);
    const tomTat = thongKeDanhDau.theoBang.map(function (s) {
      return s.tonTai
        ? ('  • ' + s.sheetName + ': ' + s.daQuet + '/' + s.tongLink + ' link đã quét')
        : ('  • ' + s.sheetName + ': không tìm thấy sheet này');
    }).join('\n');

    SpreadsheetApp.getActiveSpreadsheet().toast(
      'Đã cập nhật đánh dấu link' + (dongDaFit > 0 ? (' và auto-fit ' + dongDaFit + ' dòng mới') : ''),
      'Hoàn tất', 6
    );
    ui.alert(
      'Cập nhật hoàn tất ✅',
      tomTat +
      (thongKeDanhDau.cauTrucKetQuaQuet && thongKeDanhDau.cauTrucKetQuaQuet.dungDuPhong
        ? ('\n\n⚠️ ' + nhacMatHangTieuDe_())
        : ''),
      ui.ButtonSet.OK
    );
  } catch (err) {
    ui.alert('Có lỗi khi cập nhật.\n\nChi tiết lỗi: ' + err.message);
    throw err;
  } finally {
    lock.releaseLock();
  }
}

/**
 * Trigger onEdit (installable) — cập nhật GẦN NHƯ TỨC THỜI khi bạn tự sửa/
 * dán dữ liệu trực tiếp trên Google Sheets. KHÔNG thay thế trigger theo
 * lịch, vì trigger này không chạy khi dữ liệu tới từ công cụ ngoài/API
 * (xem giải thích ở đầu file 05).
 */
function xuLyKhiChinhSuaTucThoi(e) {
  if (!e || !e.range) return;

  const sheet = e.range.getSheet();
  const tenSheet = sheet.getName();

  if (e.range.getLastRow() < 2) return; // toàn bộ vùng sửa nằm trong hàng tiêu đề, bỏ qua

  const lock = layKhoaAnToan_(5000);
  if (!lock) return; // tránh chồng chéo; nếu bỏ lỡ, trigger theo lịch sẽ tự bắt kịp

  try {
    const laBangLienKet = DANG_KY_BANG_LIEN_KET.some(function (d) { return d.sheetName === tenSheet; });
    const laKetQuaQuet = tenSheet === KET_QUA_JSON_CONFIG.SOURCE_SHEET_NAME;

    if (laBangLienKet || laKetQuaQuet) {
      // Sửa ở bảng link HOẶC ở KetQuaQuet đều có thể làm thay đổi "tập đã
      // quét", nên chạy lại toàn bộ đánh dấu cho chắc chắn. Các bảng này
      // hiện không quá lớn nên chi phí không đáng kể; nếu sau này có hàng
      // chục nghìn dòng và thao tác chỉnh sửa trực tiếp trở nên chậm, hãy
      // tắt trigger onEdit (menu "🛑 Tắt tự động hoá" rồi bật lại chỉ với
      // trigger theo lịch) để chỉ cập nhật định kỳ thay vì mỗi lần sửa.
      danhDauLinkDaQuetTatCa_();
    }

    if (laKetQuaQuet && SHEETS_TU_DONG_CAN_CHIEU_CAO.indexOf(tenSheet) !== -1) {
      const hangBatDau = Math.max(e.range.getRow(), 2);
      const hangKetThuc = Math.max(e.range.getLastRow(), hangBatDau);
      canChinhChieuCaoChoVung_(sheet, hangBatDau, hangKetThuc - hangBatDau + 1);
    }
  } catch (err) {
    Logger.log('Lỗi xuLyKhiChinhSuaTucThoi: ' + err.message);
  } finally {
    lock.releaseLock();
  }
}
