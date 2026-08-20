/**
 * ============================================================================
 * FILE 04 — TÍNH NĂNG 1: TỰ ĐỘNG ĐÁNH DẤU LINK "ĐÃ QUÉT"
 * ============================================================================
 * Thay thế cơ chế Conditional Formatting cũ (dùng công thức COUNTIF/INDIRECT
 * chạy lại trên TỪNG Ô mỗi khi sheet thay đổi — rất chậm khi dữ liệu lớn:
 * với N hàng bên bảng link và M hàng bên KetQuaQuet, chi phí gần như N×M)
 * bằng cách xử lý trực tiếp bằng script:
 *
 *   1) Đọc toàn bộ dữ liệu cần thiết MỘT LẦN.
 *   2) So khớp trong bộ nhớ bằng Set/Map (gần như tức thời dù có hàng chục
 *      nghìn dòng — độ phức tạp chỉ còn khoảng N+M thay vì N×M).
 *   3) Ghi màu MỘT LẦN DUY NHẤT cho cả vùng (setBackgrounds/setFontColors/
 *      setFontWeights theo lô — không lặp setBackground() từng ô).
 *
 * 🔧 ĐÃ SỬA MỘT LỖI HỎNG ÂM THẦM:
 * Hai hàm đọc KetQuaQuet bên dưới trước đây tự đọc hàng 1 làm tiêu đề. Khi
 * sheet mất hàng tiêu đề, chúng KHÔNG báo lỗi gì cả — chúng chỉ lặng lẽ trả
 * về "tập đã quét" RỖNG, khiến toàn bộ link bên Link SML / Link Cory bị tô
 * về màu trắng như thể chưa từng được quét, và tính năng dò trùng lặp thì
 * ngừng hoạt động hoàn toàn. Nay cả hai đi qua layCauTrucKetQuaQuet_()
 * (file 01) nên vẫn đọc đúng dù hàng tiêu đề còn hay mất, và còn đọc thêm
 * được dòng dữ liệu ở hàng 1 mà bản cũ luôn bỏ sót.
 *
 * Quét TOÀN BỘ các cột đang có dữ liệu trong mỗi bảng đăng ký ở
 * DANG_KY_BANG_LIEN_KET (file 01) — không giới hạn cứng vào cột A/D như
 * cách cũ, đúng như yêu cầu "cột A, B, C, D...".
 *
 * Ô nào trích được khoá hợp lệ (video ID YouTube, hoặc khoá TEXT tuỳ cấu
 * hình):
 *   - có trong "tập đã quét"  → tô xanh + chữ xanh đậm + in đậm
 *   - KHÔNG có trong tập đó   → trả định dạng về mặc định (trắng/đen/thường)
 * Ô nào KHÔNG trích được khoá hợp lệ (không phải link) → bỏ qua hoàn toàn,
 * giữ nguyên định dạng đang có.
 *
 * ⚠️ Vì trạng thái "đã quét/chưa quét" luôn được TÍNH LẠI TỪ ĐẦU mỗi lần
 * chạy (không cộng dồn), nếu một link từng "đã quét" nhưng dòng tương ứng
 * bên KetQuaQuet bị xoá, lần chạy sau nó sẽ tự động trả về màu mặc định —
 * đây là hành vi có chủ đích để bảng luôn phản ánh đúng dữ liệu hiện tại.
 */

/**
 * Chạy đánh dấu cho TẤT CẢ các bảng đã đăng ký + phát hiện trùng lặp trong
 * KetQuaQuet. Trả về đối tượng thống kê để hiển thị / ghi vào bảng Tổng quan.
 */
function danhDauLinkDaQuetTatCa_() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  // Đọc cấu trúc KetQuaQuet đúng MỘT LẦN cho cả lượt chạy.
  const cauTruc = layCauTrucKetQuaQuet_(ss);
  const tapDaQuetCache = {};
  const theoBang = DANG_KY_BANG_LIEN_KET.map(function (dangKy) {
    return danhDauLinkDaQuetChoBang_(ss, dangKy, tapDaQuetCache, cauTruc);
  });

  const trungLapKetQuaQuet = danhDauTrungLapTrongKetQuaQuet_(ss, cauTruc);

  return {
    thoiGianCapNhat: new Date(),
    theoBang: theoBang,
    trungLapKetQuaQuet: trungLapKetQuaQuet,
    cauTrucKetQuaQuet: cauTruc
  };
}

/**
 * Đánh dấu "đã quét" cho một bảng link đã đăng ký.
 */
function danhDauLinkDaQuetChoBang_(ss, dangKy, tapDaQuetCache, cauTruc) {
  const thongKe = {
    sheetName: dangKy.sheetName,
    tonTai: false,
    tongLink: 0,
    daQuet: 0,
    choXuLy: 0
  };

  const sheet = ss.getSheetByName(dangKy.sheetName);
  if (!sheet) return thongKe;
  thongKe.tonTai = true;

  const lastRow = sheet.getLastRow();
  const lastCol = sheet.getLastColumn();
  if (lastRow < 2 || lastCol < 1) return thongKe;

  const tapDaQuet = layTapDaQuetCoCache_(ss, dangKy, tapDaQuetCache, cauTruc);

  const numRows = lastRow - 1;
  const range = sheet.getRange(2, 1, numRows, lastCol);
  const values = range.getValues();
  const backgrounds = range.getBackgrounds();
  const fontColors = range.getFontColors();
  const fontWeights = range.getFontWeights();

  for (let r = 0; r < numRows; r++) {
    for (let c = 0; c < lastCol; c++) {
      const raw = values[r][c];
      if (raw === '' || raw === null || raw === undefined) continue;

      const khoa = layKhoaSoSanh_(raw, dangKy.khoaSoSanh);
      if (!khoa) continue; // không phải link/khoá hợp lệ -> bỏ qua, giữ nguyên định dạng

      thongKe.tongLink++;
      if (tapDaQuet.has(khoa)) {
        thongKe.daQuet++;
        backgrounds[r][c] = MAU_SAC.DA_QUET_NEN;
        fontColors[r][c] = MAU_SAC.DA_QUET_CHU;
        fontWeights[r][c] = 'bold';
      } else {
        thongKe.choXuLy++;
        backgrounds[r][c] = MAU_SAC.MAC_DINH_NEN;
        fontColors[r][c] = MAU_SAC.MAC_DINH_CHU;
        fontWeights[r][c] = 'normal';
      }
    }
  }

  range.setBackgrounds(backgrounds);
  range.setFontColors(fontColors);
  range.setFontWeights(fontWeights);

  return thongKe;
}

/**
 * Lấy "tập đã quét" cho một khai báo đăng ký, có cache trong phạm vi một
 * lượt chạy — nếu 2 bảng dùng chung (ketQuaHeader, khoaSoSanh) thì chỉ cần
 * đọc KetQuaQuet một lần.
 */
function layTapDaQuetCoCache_(ss, dangKy, cache, cauTruc) {
  const cacheKey = dangKy.ketQuaHeader + '|' + dangKy.khoaSoSanh;
  if (cache[cacheKey]) return cache[cacheKey];
  const set = xayDungTapKhoaTuKetQuaQuet_(ss, dangKy.ketQuaHeader, dangKy.khoaSoSanh, cauTruc);
  cache[cacheKey] = set;
  return set;
}

function xayDungTapKhoaTuKetQuaQuet_(ss, tenTieuDe, loaiKhoa, cauTruc) {
  const set = new Set();
  const ct = cauTruc || layCauTrucKetQuaQuet_(ss);
  if (!ct.tonTai) return set;

  const sheet = ct.sheet;
  const lastRow = sheet.getLastRow();
  if (lastRow < ct.hangDauDuLieu || ct.soCot < 1) return set;

  const colIndex = ct.columnMap[chuanHoaTieuDe_(tenTieuDe)];
  if (colIndex === undefined) return set;
  if (colIndex + 1 > ct.soCot) return set; // cột nằm ngoài vùng đang có dữ liệu

  const numRows = lastRow - ct.hangDauDuLieu + 1;
  const values = sheet
    .getRange(ct.hangDauDuLieu, colIndex + 1, numRows, 1)
    .getValues();

  values.forEach(function (row) {
    const khoa = layKhoaSoSanh_(row[0], loaiKhoa);
    if (khoa) set.add(khoa);
  });

  return set;
}

/**
 * Phát hiện & tô cảnh báo (cam) cho các dòng trong KetQuaQuet có
 * "Link video vi phạm" bị lặp lại hơn 1 lần — dấu hiệu một video có thể đã
 * bị quét/nhập trùng, giúp bạn dễ rà soát khi dữ liệu ngày càng nhiều.
 */
function danhDauTrungLapTrongKetQuaQuet_(ss, cauTruc) {
  const thongKe = { tongDongTrungLap: 0, soKhoaTrungLap: 0 };
  const ct = cauTruc || layCauTrucKetQuaQuet_(ss);
  if (!ct.tonTai) return thongKe;

  const sheet = ct.sheet;
  const lastRow = sheet.getLastRow();
  if (lastRow < ct.hangDauDuLieu || ct.soCot < 1) return thongKe;

  const colIndex = ct.columnMap[chuanHoaTieuDe_(KET_QUA_JSON_FIELDS.INFRINGING_URL)];
  if (colIndex === undefined) return thongKe;
  if (colIndex + 1 > ct.soCot) return thongKe;

  const numRows = lastRow - ct.hangDauDuLieu + 1;
  const colRange = sheet.getRange(ct.hangDauDuLieu, colIndex + 1, numRows, 1);
  const values = colRange.getValues();
  const backgrounds = colRange.getBackgrounds();
  const fontColors = colRange.getFontColors();
  const fontWeights = colRange.getFontWeights();

  const tanSuat = new Map();
  const khoaTheoDong = values.map(function (row) {
    return layYoutubeVideoId_(row[0]);
  });
  khoaTheoDong.forEach(function (khoa) {
    if (khoa) tanSuat.set(khoa, (tanSuat.get(khoa) || 0) + 1);
  });

  let tongDongTrungLap = 0;
  const khoaTrungLap = new Set();

  for (let r = 0; r < numRows; r++) {
    const khoa = khoaTheoDong[r];
    const biTrung = khoa && tanSuat.get(khoa) > 1;
    if (biTrung) {
      tongDongTrungLap++;
      khoaTrungLap.add(khoa);
      backgrounds[r][0] = MAU_SAC.TRUNG_LAP_NEN;
      fontColors[r][0] = MAU_SAC.TRUNG_LAP_CHU;
      fontWeights[r][0] = 'bold';
    } else {
      backgrounds[r][0] = MAU_SAC.MAC_DINH_NEN;
      fontColors[r][0] = MAU_SAC.MAC_DINH_CHU;
      fontWeights[r][0] = 'normal';
    }
  }

  colRange.setBackgrounds(backgrounds);
  colRange.setFontColors(fontColors);
  colRange.setFontWeights(fontWeights);

  thongKe.tongDongTrungLap = tongDongTrungLap;
  thongKe.soKhoaTrungLap = khoaTrungLap.size;
  return thongKe;
}

/**
 * Dọn dẹp các rule Conditional Formatting "kiểu cũ" (dùng công thức
 * COUNTIF/INDIRECT tham chiếu KetQuaQuet) trên một sheet — tránh nhầm lẫn/
 * xung đột với cách tô màu trực tiếp bằng script ở trên. Rule nào KHÔNG
 * liên quan (không tham chiếu KetQuaQuet) được giữ nguyên, không đụng tới.
 */
function xoaQuyTacDinhDangCuLienQuanKetQuaQuet_(sheet) {
  const rules = sheet.getConditionalFormatRules();
  const rulesGiuLai = rules.filter(function (rule) {
    const condition = rule.getBooleanCondition();
    if (!condition) return true; // không phải rule dạng công thức (vd gradient) -> giữ nguyên
    const values = condition.getCriteriaValues() || [];
    const formula = String(values[0] || '');
    return formula.indexOf('KetQuaQuet') === -1;
  });
  if (rulesGiuLai.length !== rules.length) {
    sheet.setConditionalFormatRules(rulesGiuLai);
  }
  return rules.length - rulesGiuLai.length;
}
