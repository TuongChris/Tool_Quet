/**
 * ============================================================================
 * FILE 03 — XUẤT HÀNG ĐANG CHỌN THÀNH ĐOẠN VĂN BẢN CÓ CẤU TRÚC
 * ============================================================================
 * Sheet nguồn: KetQuaQuet
 * Sheet kết quả: Ket_Qua_Json
 *
 * Cách dùng:
 * 1. Chọn một ô bất kỳ, một vùng ô hoặc cả hàng trên sheet KetQuaQuet.
 * 2. Chọn menu "CHUYỂN ĐỔI DỮ LIỆU" > "Xuất hàng đang chọn".
 * 3. Mỗi hàng nguồn được xuất thành một ô văn bản trong Ket_Qua_Json.
 *
 * HAI THAY ĐỔI SO VỚI BẢN CŨ:
 *
 * 1) SỬA LỖI "Không tìm thấy các cột bắt buộc". Bản cũ luôn coi hàng 1 là
 *    hàng tiêu đề; sheet của bạn đã mất hàng tiêu đề nên nó đi tìm tên cột
 *    trong một hàng dữ liệu. Nay mọi thứ đi qua layCauTrucKetQuaQuet_()
 *    (file 01): tự nhận ra hàng 1 là tiêu đề hay dữ liệu, và nếu là dữ liệu
 *    thì đọc theo thứ tự cột gốc của công cụ + coi hàng 1 là dòng dữ liệu
 *    đầu tiên (bản cũ luôn bắt đầu từ hàng 2 nên còn bỏ sót mất dòng đầu).
 *
 * 2) BẢN MẪU XUẤT MỚI: mỗi tiêu đề mục có một dòng trống ngay sau nó, đoạn
 *    vi phạm tách thành mục riêng "3.", danh sách video gốc thành mục "4.".
 *    Hai dòng "Thời gian quét" và "Tổng số đoạn video gốc phát hiện" mặc
 *    định KHÔNG in ra — bật lại bằng MAU_XUAT ở file 01 nếu cần.
 */

function xuatHangDaChonSangKetQuaJson() {
  const lock = LockService.getDocumentLock();
  lock.waitLock(30000);

  try {
    const spreadsheet = SpreadsheetApp.getActiveSpreadsheet();
    const sourceSheet = spreadsheet.getActiveSheet();
    const selectedRange = spreadsheet.getActiveRange();
    const ui = SpreadsheetApp.getUi();

    if (!selectedRange) {
      ui.alert('Không tìm thấy ô hoặc hàng đang được chọn.');
      return;
    }

    if (sourceSheet.getName() !== KET_QUA_JSON_CONFIG.SOURCE_SHEET_NAME) {
      ui.alert(
        'Bạn cần chọn dữ liệu trên sheet "' +
          KET_QUA_JSON_CONFIG.SOURCE_SHEET_NAME +
          '" trước khi chạy.'
      );
      return;
    }

    const lastDataRow = sourceSheet.getLastRow();
    const lastColumn = sourceSheet.getLastColumn();

    const cauTruc = layCauTrucKetQuaQuet_(spreadsheet);
    const hangDauDuLieu = cauTruc.hangDauDuLieu;

    if (lastDataRow < hangDauDuLieu || lastColumn === 0) {
      ui.alert('Sheet nguồn chưa có dữ liệu để chuyển đổi.');
      return;
    }

    const columnMap = cauTruc.columnMap;
    // Chỉ đòi hỏi những cột THỰC SỰ được in ra theo bản mẫu hiện tại. Bắt
    // buộc cả cột không dùng tới chỉ làm người dùng bế tắc vô cớ khi họ xoá
    // một cột mà bản mẫu không cần.
    const cotBatBuoc = [
      KET_QUA_JSON_FIELDS.CHANNEL_URL,
      KET_QUA_JSON_FIELDS.CHANNEL_NAME,
      KET_QUA_JSON_FIELDS.CHANNEL_ID,
      KET_QUA_JSON_FIELDS.INFRINGING_URL,
      KET_QUA_JSON_FIELDS.INFRINGING_TITLE,
      KET_QUA_JSON_FIELDS.INFRINGING_DURATION,
      KET_QUA_JSON_FIELDS.INFRINGING_DATE
    ];
    if (MAU_XUAT.HIEN_THOI_GIAN_QUET) cotBatBuoc.push(KET_QUA_JSON_FIELDS.SCAN_TIME);
    if (MAU_XUAT.HIEN_TONG_SO_DOAN) cotBatBuoc.push(KET_QUA_JSON_FIELDS.TOTAL_MATCHES);
    kiemTraCotBatBuoc_(columnMap, cotBatBuoc);

    // Dù chỉ chọn một ô, script vẫn lấy toàn bộ dữ liệu của hàng đó.
    const firstSelectedRow = Math.max(selectedRange.getRow(), hangDauDuLieu);
    const lastSelectedRow = Math.min(selectedRange.getLastRow(), lastDataRow);

    if (lastSelectedRow < firstSelectedRow) {
      ui.alert(
        'Hàng tiêu đề không được chuyển đổi. Hãy chọn từ hàng ' +
        hangDauDuLieu + ' trở xuống.'
      );
      return;
    }

    const rowCount = lastSelectedRow - firstSelectedRow + 1;
    const dataRange = sourceSheet.getRange(firstSelectedRow, 1, rowCount, lastColumn);

    // Lấy cả giá trị thật và giá trị đang hiển thị:
    // - getValues(): nhận đúng Date và số thời lượng.
    // - getDisplayValues(): giữ nguyên link, tên và chuỗi đã định dạng.
    const rawRows = dataRange.getValues();
    const displayRows = dataRange.getDisplayValues();

    const outputSheet = layHoacTaoSheetKetQua_(spreadsheet);
    const spreadsheetTimeZone =
      spreadsheet.getSpreadsheetTimeZone() || Session.getScriptTimeZone();
    const generatedAt = new Date();
    const outputRows = [];

    rawRows.forEach(function (rawRow, index) {
      const displayRow = displayRows[index];
      const sourceRowNumber = firstSelectedRow + index;

      const isEmptyRow = displayRow.every(function (value) {
        return String(value || '').trim() === '';
      });
      if (isEmptyRow) return;

      const convertedText = chuyenHangThanhVanBanTheoMau_(
        columnMap, rawRow, displayRow, spreadsheetTimeZone
      );

      outputRows.push(['', sourceSheet.getName(), sourceRowNumber, generatedAt, convertedText]);
    });

    if (outputRows.length === 0) {
      ui.alert('Các hàng được chọn không có dữ liệu.');
      return;
    }

    const outputStartRow = Math.max(outputSheet.getLastRow() + 1, 2);
    outputRows.forEach(function (row, index) {
      row[0] = outputStartRow - 1 + index;
    });

    outputSheet
      .getRange(outputStartRow, 1, outputRows.length, KET_QUA_JSON_CONFIG.OUTPUT_HEADERS.length)
      .setValues(outputRows);

    dinhDangDongKetQua_(outputSheet, outputStartRow, outputRows.length);

    outputSheet.activate();
    outputSheet.getRange(outputStartRow, 1, outputRows.length, 5).activate();

    spreadsheet.toast(
      'Đã chuyển đổi ' + outputRows.length + ' hàng sang "Ket_Qua_Json".',
      'Hoàn tất', 5
    );

    if (cauTruc.dungDuPhong) {
      ui.alert('Đã xuất xong, nhưng cần lưu ý', nhacMatHangTieuDe_(), ui.ButtonSet.OK);
    }
  } catch (error) {
    SpreadsheetApp.getUi().alert(
      'Không thể chuyển đổi dữ liệu.\n\nChi tiết lỗi: ' + error.message
    );
    throw error;
  } finally {
    lock.releaseLock();
  }
}

/**
 * Chuyển một hàng thành đoạn văn bản theo bản mẫu.
 *
 * BỐ CỤC (mỗi tiêu đề mục có một dòng trống ngay sau nó):
 *
 *   [Thời gian quét : ...]            <- chỉ khi MAU_XUAT.HIEN_THOI_GIAN_QUET
 *
 *   1. Thông tin chi tiết chanel vi phạm :
 *
 *   Link kênh vi phạm : ...
 *   Tên kênh vi phạm : ...
 *   Id kênh vi phạm : ...
 *
 *   2. Thông tin chi tiết video vi phạm :
 *
 *   Link video vi phạm : ...
 *   Tên video vi phạm : ...
 *   Thời lượng video vi phạm : ...
 *   Ngày đăng video vi phạm : ...
 *
 *   3. Đoạn vi phạm 1 trong video vi phạm : ...
 *   Đoạn vi phạm 2 trong video vi phạm : ...      <- nếu có nhiều đoạn
 *
 *   4. Danh sách các video gốc :
 *
 *   Link video gốc 1 : ...
 *   Tên video gốc 1 : ...
 *   Ngày đăng video gốc 1 : ...
 *   Thời lượng video gốc 1 : ...
 *
 *   [5. Tổng số đoạn video gốc phát hiện : ...]   <- chỉ khi MAU_XUAT.HIEN_TONG_SO_DOAN
 *
 * SỐ THỨ TỰ MỤC ĐƯỢC ĐÁNH ĐỘNG: hàng nào không có đoạn vi phạm nào thì mục
 * "Danh sách các video gốc" lùi lên thành "3." thay vì để trống một số —
 * đoạn văn bản không bao giờ nhảy số.
 */
function chuyenHangThanhVanBanTheoMau_(columnMap, rawRow, displayRow, timeZone) {
  const lines = [];
  let soMuc = 0;

  function hienThi(header) {
    return giaTriHoacTrong_(layDisplay_(columnMap, displayRow, header));
  }
  function themDong(header, giaTri) {
    lines.push(header + ' : ' + giaTri + ',');
  }
  function moMuc(tieuDe) {
    soMuc += 1;
    lines.push(soMuc + '. ' + tieuDe);
    lines.push('');
  }

  if (MAU_XUAT.HIEN_THOI_GIAN_QUET) {
    const scanTime = dinhDangNgayGio_(
      layRaw_(columnMap, rawRow, KET_QUA_JSON_FIELDS.SCAN_TIME),
      layDisplay_(columnMap, displayRow, KET_QUA_JSON_FIELDS.SCAN_TIME),
      timeZone
    );
    themDong('Thời gian quét', giaTriHoacTrong_(scanTime));
    lines.push('');
  }

  // ----- Mục 1: kênh vi phạm -------------------------------------------------
  moMuc('Thông tin chi tiết chanel vi phạm :');
  themDong('Link kênh vi phạm', hienThi(KET_QUA_JSON_FIELDS.CHANNEL_URL));
  themDong('Tên kênh vi phạm', hienThi(KET_QUA_JSON_FIELDS.CHANNEL_NAME));
  themDong('Id kênh vi phạm', hienThi(KET_QUA_JSON_FIELDS.CHANNEL_ID));
  lines.push('');

  // ----- Mục 2: video vi phạm ------------------------------------------------
  moMuc('Thông tin chi tiết video vi phạm :');
  themDong('Link video vi phạm', hienThi(KET_QUA_JSON_FIELDS.INFRINGING_URL));
  themDong('Tên video vi phạm', hienThi(KET_QUA_JSON_FIELDS.INFRINGING_TITLE));
  themDong('Thời lượng video vi phạm', giaTriHoacTrong_(dinhDangThoiLuong_(
    layRaw_(columnMap, rawRow, KET_QUA_JSON_FIELDS.INFRINGING_DURATION),
    layDisplay_(columnMap, displayRow, KET_QUA_JSON_FIELDS.INFRINGING_DURATION)
  )));
  themDong('Ngày đăng video vi phạm', giaTriHoacTrong_(dinhDangNgay_(
    layRaw_(columnMap, rawRow, KET_QUA_JSON_FIELDS.INFRINGING_DATE),
    layDisplay_(columnMap, displayRow, KET_QUA_JSON_FIELDS.INFRINGING_DATE),
    timeZone
  )));
  lines.push('');

  // ----- Mục 3: các đoạn vi phạm --------------------------------------------
  // Gom trước rồi mới quyết định có mở mục hay không, để hàng không có đoạn
  // nào không để lại một số mục trống lơ lửng.
  const dongDoanViPham = [];
  for (let segmentNumber = 1; segmentNumber <= 5; segmentNumber += 1) {
    const segmentHeader = 'Đoạn vi phạm ' + segmentNumber + ' trong video vi phạm';
    const segmentValue = layDisplay_(columnMap, displayRow, segmentHeader);
    if (coDuLieu_(segmentValue)) {
      dongDoanViPham.push(segmentHeader + ' : ' + String(segmentValue).trim() + ',');
    }
  }
  if (dongDoanViPham.length > 0) {
    soMuc += 1;
    // Đoạn đầu tiên đi liền số mục trên CÙNG MỘT DÒNG, đúng bản mẫu.
    lines.push(soMuc + '. ' + dongDoanViPham[0]);
    for (let i = 1; i < dongDoanViPham.length; i += 1) {
      lines.push(dongDoanViPham[i]);
    }
    lines.push('');
  }

  // ----- Mục 4: danh sách video gốc -----------------------------------------
  moMuc('Danh sách các video gốc :');
  for (let originalNumber = 1; originalNumber <= 5; originalNumber += 1) {
    const originalLinkHeader = 'Link video gốc ' + originalNumber;
    const originalTitleHeader = 'Tên video gốc ' + originalNumber;
    const originalDateHeader = 'Ngày đăng video gốc ' + originalNumber;
    const originalDurationHeader = 'Thời lượng video gốc ' + originalNumber;

    const originalLink = layDisplay_(columnMap, displayRow, originalLinkHeader);
    const originalTitle = layDisplay_(columnMap, displayRow, originalTitleHeader);
    const originalDateRaw = layRaw_(columnMap, rawRow, originalDateHeader);
    const originalDateDisplay = layDisplay_(columnMap, displayRow, originalDateHeader);
    const originalDurationRaw = layRaw_(columnMap, rawRow, originalDurationHeader);
    const originalDurationDisplay = layDisplay_(columnMap, displayRow, originalDurationHeader);

    const hasOriginal = [
      originalLink, originalTitle, originalDateDisplay,
      originalDurationDisplay, originalDateRaw, originalDurationRaw
    ].some(coDuLieu_);

    if (!hasOriginal) continue;

    themDong(originalLinkHeader, giaTriHoacTrong_(originalLink));
    themDong(originalTitleHeader, giaTriHoacTrong_(originalTitle));
    themDong(originalDateHeader, giaTriHoacTrong_(
      dinhDangNgay_(originalDateRaw, originalDateDisplay, timeZone)));
    themDong(originalDurationHeader, giaTriHoacTrong_(
      dinhDangThoiLuong_(originalDurationRaw, originalDurationDisplay)));
    lines.push('');
  }

  while (lines.length > 0 && lines[lines.length - 1] === '') {
    lines.pop();
  }

  // ----- Mục cuối (tuỳ chọn): tổng số đoạn ----------------------------------
  if (MAU_XUAT.HIEN_TONG_SO_DOAN) {
    soMuc += 1;
    lines.push('');
    lines.push(
      soMuc + '. Tổng số đoạn video gốc phát hiện : ' +
      giaTriHoacTrong_(layDisplay_(columnMap, displayRow, KET_QUA_JSON_FIELDS.TOTAL_MATCHES))
    );
  }

  return lines.join('\n');
}

/**
 * Mở nhanh sheet kết quả.
 */
function moBangKetQuaJson() {
  const spreadsheet = SpreadsheetApp.getActiveSpreadsheet();
  const outputSheet = layHoacTaoSheetKetQua_(spreadsheet);
  outputSheet.activate();
}

/**
 * Lấy hoặc tạo sheet Ket_Qua_Json và thiết lập giao diện.
 */
function layHoacTaoSheetKetQua_(spreadsheet) {
  let outputSheet = spreadsheet.getSheetByName(KET_QUA_JSON_CONFIG.OUTPUT_SHEET_NAME);
  if (!outputSheet) {
    outputSheet = spreadsheet.insertSheet(KET_QUA_JSON_CONFIG.OUTPUT_SHEET_NAME);
  }

  const headerRange = outputSheet.getRange(1, 1, 1, KET_QUA_JSON_CONFIG.OUTPUT_HEADERS.length);
  headerRange
    .setValues([KET_QUA_JSON_CONFIG.OUTPUT_HEADERS])
    .setBackground('#1F4E78')
    .setFontColor('#FFFFFF')
    .setFontWeight('bold')
    .setHorizontalAlignment('center')
    .setVerticalAlignment('middle');

  outputSheet.setFrozenRows(1);
  outputSheet.setColumnWidth(1, 60);
  outputSheet.setColumnWidth(2, 140);
  outputSheet.setColumnWidth(3, 95);
  outputSheet.setColumnWidth(4, 165);
  outputSheet.setColumnWidth(5, 680);
  outputSheet.setRowHeight(1, 32);

  return outputSheet;
}

/**
 * Định dạng các hàng vừa xuất.
 */
function dinhDangDongKetQua_(outputSheet, startRow, rowCount) {
  outputSheet.getRange(startRow, 4, rowCount, 1).setNumberFormat('dd/MM/yyyy HH:mm:ss');
  outputSheet.getRange(startRow, 5, rowCount, 1).setNumberFormat('@').setWrap(true).setVerticalAlignment('top');
  outputSheet.getRange(startRow, 1, rowCount, 4).setVerticalAlignment('top');
  outputSheet.autoResizeRows(startRow, rowCount);
}
