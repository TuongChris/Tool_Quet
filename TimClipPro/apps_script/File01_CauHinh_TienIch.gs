/**
 * ============================================================================
 * FILE 01 — CẤU HÌNH CHUNG & TIỆN ÍCH DÙNG CHUNG
 * ============================================================================
 * File này khai báo các hằng số cấu hình và các hàm tiện ích được nhiều
 * tính năng khác trong dự án dùng lại: đọc cột theo TÊN TIÊU ĐỀ (không phụ
 * thuộc thứ tự cột A,B,C...), trích video ID YouTube, định dạng ngày giờ /
 * thời lượng, và khoá (lock) chống chạy chồng chéo.
 *
 * ⚠️ LƯU Ý VỀ THỨ TỰ NẠP FILE:
 * Trong Apps Script, các HÀM (function) có thể gọi lẫn nhau bất kể được
 * viết ở file nào (toàn bộ dự án dùng chung 1 phạm vi biến toàn cục), nên
 * bạn có thể sắp xếp lại thứ tự file tuỳ ý mà không lo lỗi.
 * Riêng các hằng số khai báo bằng "const" ở cấp cao nhất (ví dụ
 * DANG_KY_BANG_LIEN_KET bên dưới) được nạp THEO ĐÚNG THỨ TỰ TỪ TRÊN XUỐNG
 * TRONG FILE NÀY, nên nếu bạn thêm hằng số mới có tham chiếu tới hằng số
 * khác, hãy khai báo nó ở SAU hằng số mà nó phụ thuộc vào — giống như cách
 * KET_QUA_JSON_FIELDS được khai báo trước DANG_KY_BANG_LIEN_KET dưới đây.
 */

// ---------------------------------------------------------------------------
// A. CẤU HÌNH SHEET "KẾT QUẢ QUÉT" (nguồn dữ liệu chính của cả dự án)
// ---------------------------------------------------------------------------
const KET_QUA_JSON_CONFIG = Object.freeze({
  SOURCE_SHEET_NAME: 'KetQuaQuet',
  OUTPUT_SHEET_NAME: 'Ket_Qua_Json',
  HEADER_ROW: 1,
  FIRST_DATA_ROW: 2,
  EMPTY_VALUE_TEXT: '(trống)',
  OUTPUT_HEADERS: [
    'STT',
    'Sheet nguồn',
    'Hàng nguồn',
    'Thời gian xuất',
    'Nội dung chuyển đổi'
  ]
});

const KET_QUA_JSON_FIELDS = Object.freeze({
  SCAN_TIME: 'Thời gian quét',
  CHANNEL_URL: 'Link kênh vi phạm',
  CHANNEL_NAME: 'Tên kênh vi phạm',
  CHANNEL_ID: 'Id kênh vi phạm',
  INFRINGING_URL: 'Link video vi phạm',
  INFRINGING_TITLE: 'Tên video vi phạm',
  INFRINGING_DURATION: 'Thời lượng video vi phạm',
  INFRINGING_DATE: 'Ngày đăng video vi phạm',
  TOTAL_MATCHES: 'Tổng số đoạn phát hiện',
  STATUS: 'Trạng thái'
});

// ---------------------------------------------------------------------------
// A2. THỨ TỰ CỘT GỐC MÀ CÔNG CỤ TimClipPro GHI RA (bản "Ngang", 34 cột)
// ---------------------------------------------------------------------------
// 🔧 ĐÂY LÀ PHẦN SỬA LỖI "Không tìm thấy các cột bắt buộc".
//
// NGUYÊN NHÂN GỐC: sheet KetQuaQuet của bạn hiện KHÔNG CÒN HÀNG TIÊU ĐỀ —
// hàng 1 đang là DỮ LIỆU THẬT (đã kiểm: 1465 dòng dữ liệu, không dòng nào
// chứa chữ "Thời gian quét"). Script cũ luôn coi hàng 1 là tiêu đề, nên nó
// đi tìm tên cột trong một hàng dữ liệu và tất nhiên không thấy cột nào.
//
// Hàng tiêu đề chỉ được công cụ ghi MỘT LẦN, lúc trang tính còn trống. Nếu
// hàng đó bị xoá (hoặc bị sắp xếp mất) thì công cụ sẽ không ghi lại nữa —
// vì nó thấy ô A1 đã có dữ liệu nên tưởng tiêu đề vẫn còn.
//
// CÁCH XỬ LÝ Ở ĐÂY (hai lớp, không cần bạn làm gì trước):
//   1) Script tự nhận ra hàng 1 là tiêu đề hay là dữ liệu.
//   2) Nếu là dữ liệu → dùng THỨ TỰ CỘT CỐ ĐỊNH bên dưới để đọc, nên mọi
//      tính năng chạy được ngay lập tức.
//   3) Bạn có thể khôi phục hàng tiêu đề vĩnh viễn bằng menu
//      "🩹 Khôi phục hàng tiêu đề cho KetQuaQuet".
//
// ⚠️ Danh sách này phải khớp ĐÚNG THỨ TỰ với `bang_ngang.HEADER_NGANG`
// trong công cụ TimClipPro. Nếu sau này công cụ đổi cột, sửa cả hai nơi.
const KETQUAQUET_COT_MAC_DINH = Object.freeze([
  'Thời gian quét',                      // A
  'Link kênh vi phạm',                   // B
  'Tên kênh vi phạm',                    // C
  'Id kênh vi phạm',                     // D
  'Link video vi phạm',                  // E
  'Tên video vi phạm',                   // F
  'Thời lượng video vi phạm',            // G
  'Ngày đăng video vi phạm',             // H
  'Đoạn vi phạm 1 trong video vi phạm',  // I
  'Đoạn vi phạm 2 trong video vi phạm',  // J
  'Đoạn vi phạm 3 trong video vi phạm',  // K
  'Đoạn vi phạm 4 trong video vi phạm',  // L
  'Đoạn vi phạm 5 trong video vi phạm',  // M
  'Link video gốc 1',                    // N
  'Tên video gốc 1',                     // O
  'Ngày đăng video gốc 1',               // P
  'Thời lượng video gốc 1',              // Q
  'Link video gốc 2',                    // R
  'Tên video gốc 2',                     // S
  'Ngày đăng video gốc 2',               // T
  'Thời lượng video gốc 2',              // U
  'Link video gốc 3',                    // V
  'Tên video gốc 3',                     // W
  'Ngày đăng video gốc 3',               // X
  'Thời lượng video gốc 3',              // Y
  'Link video gốc 4',                    // Z
  'Tên video gốc 4',                     // AA
  'Ngày đăng video gốc 4',               // AB
  'Thời lượng video gốc 4',              // AC
  'Link video gốc 5',                    // AD
  'Tên video gốc 5',                     // AE
  'Ngày đăng video gốc 5',               // AF
  'Thời lượng video gốc 5',              // AG
  'Tổng số đoạn phát hiện'               // AH
]);

// Số tên cột tối thiểu phải nhận ra được thì mới coi hàng 1 là HÀNG TIÊU ĐỀ.
// Đặt 3 để: một hàng dữ liệu thật (toàn link/tên video) gần như không thể
// đạt tới, còn một hàng tiêu đề dù bạn có đổi tên vài cột vẫn vượt qua —
// nhờ vậy lỗi "đổi tên cột" vẫn được báo đúng thay vì âm thầm đọc sai cột.
const SO_COT_TOI_THIEU_DE_COI_LA_TIEU_DE = 3;

// ---------------------------------------------------------------------------
// A3. TUỲ CHỌN NỘI DUNG XUẤT (menu "📄 Xuất hàng đang chọn")
// ---------------------------------------------------------------------------
// 👉 Hai dòng dưới đây điều khiển hai dòng thông tin mà bản mẫu mới KHÔNG
// còn in ra. Muốn lấy lại dòng nào, đổi false thành true rồi lưu — không
// cần sửa gì thêm, phần đánh số mục (1., 2., 3., 4.) tự điều chỉnh theo.
const MAU_XUAT = Object.freeze({
  HIEN_THOI_GIAN_QUET: false,  // dòng "Thời gian quét : ..." ở đầu đoạn
  HIEN_TONG_SO_DOAN: false     // dòng "Tổng số đoạn video gốc phát hiện : ..." ở cuối
});

// ---------------------------------------------------------------------------
// B. MÀU SẮC DÙNG CHUNG
// ---------------------------------------------------------------------------
// Giữ đúng 2 màu "đã quét" / "cảnh báo" bạn đã dùng từ trước để không thay
// đổi cảm giác trực quan đã quen mắt; thêm màu "trùng lặp" cho tính năng
// mới (phát hiện link bị quét/nhập trùng trong KetQuaQuet).
const MAU_SAC = Object.freeze({
  DA_QUET_NEN: '#d9ead3',
  DA_QUET_CHU: '#137333',
  CANH_BAO_NEN: '#fce8e6',
  CANH_BAO_CHU: '#c5221f',
  TRUNG_LAP_NEN: '#fce5cd',
  TRUNG_LAP_CHU: '#b45f06',
  MAC_DINH_NEN: '#ffffff',
  MAC_DINH_CHU: '#000000'
});

// ---------------------------------------------------------------------------
// C. LOẠI "KHOÁ SO SÁNH" (dùng để nhận biết 1 ô có phải là "đã quét" không)
// ---------------------------------------------------------------------------
const LOAI_KHOA = Object.freeze({
  YOUTUBE_VIDEO_ID: 'youtube_video_id', // trích 11 ký tự video ID từ link YouTube
  TEXT: 'text'                          // so khớp chuỗi văn bản đã chuẩn hoá
});

// ---------------------------------------------------------------------------
// D. ĐĂNG KÝ CÁC BẢNG "LINK ỨNG VIÊN" CẦN ĐÁNH DẤU "ĐÃ QUÉT"
// ---------------------------------------------------------------------------
// 👉 ĐÂY LÀ NƠI DUY NHẤT BẠN CẦN SỬA KHI MUỐN THÊM MỘT BẢNG LINK MỚI SAU NÀY.
// Không cần sửa logic ở bất kỳ file nào khác. Mỗi mục gồm:
//
//   sheetName    tên sheet chứa danh sách link ứng viên (Link SML, Link Cory...)
//
//   khoaSoSanh   kiểu khoá dùng để so khớp:
//                 - LOAI_KHOA.YOUTUBE_VIDEO_ID (mặc định): trích video ID
//                   11 ký tự từ link YouTube — không quan trọng http/https,
//                   có/không www, khoảng trắng thừa, hay tham số phía sau.
//                 - LOAI_KHOA.TEXT: so khớp chuỗi văn bản (dùng cho các
//                   "khoá khác" sau này, ví dụ Id kênh thay vì link video).
//
//   ketQuaHeader TÊN TIÊU ĐỀ cột bên sheet KetQuaQuet dùng làm "danh sách đã
//                quét" để đối chiếu — dùng tên tiêu đề (không phải chữ cái
//                cột) để không bị vỡ khi bạn chèn/xoá cột trong KetQuaQuet.
//
// Ví dụ thêm một bảng mới trong tương lai với MỘT KHOÁ KHÁC (chẳng hạn so
// khớp theo Id kênh thay vì theo video): chỉ cần thêm một mục như sau vào
// mảng bên dưới — không cần sửa gì thêm ở các file khác:
//   {
//     sheetName: 'Danh sách kênh cần theo dõi',
//     khoaSoSanh: LOAI_KHOA.TEXT,
//     ketQuaHeader: KET_QUA_JSON_FIELDS.CHANNEL_ID
//   }
const DANG_KY_BANG_LIEN_KET = [
  {
    sheetName: 'Link SML',
    khoaSoSanh: LOAI_KHOA.YOUTUBE_VIDEO_ID,
    ketQuaHeader: KET_QUA_JSON_FIELDS.INFRINGING_URL
  },
  {
    sheetName: 'Link Cory',
    khoaSoSanh: LOAI_KHOA.YOUTUBE_VIDEO_ID,
    ketQuaHeader: KET_QUA_JSON_FIELDS.INFRINGING_URL
  }
  // Thêm bảng mới tại đây (nhớ thêm dấu phẩy "," ở mục phía trên nếu bỏ
  // dấu // để kích hoạt dòng ví dụ dưới đây):
  // ,{
  //   sheetName: 'Link ABC',
  //   khoaSoSanh: LOAI_KHOA.YOUTUBE_VIDEO_ID,
  //   ketQuaHeader: KET_QUA_JSON_FIELDS.INFRINGING_URL
  // }
];

// ---------------------------------------------------------------------------
// E. SHEET CẦN TỰ ĐỘNG CĂN CHỈNH CHIỀU CAO HÀNG
// ---------------------------------------------------------------------------
// 👉 Thêm tên sheet vào đây nếu muốn sheet đó cũng được tự động auto-fit
// chiều cao hàng mỗi khi có dữ liệu mới — ví dụ nếu sau này có thêm một
// sheet log khác cũng được công cụ ngoài đẩy dữ liệu vào.
const SHEETS_TU_DONG_CAN_CHIEU_CAO = ['KetQuaQuet'];

// ---------------------------------------------------------------------------
// F. CÀI ĐẶT TỰ ĐỘNG HOÁ (trigger)
// ---------------------------------------------------------------------------
const CAI_DAT_TU_DONG = Object.freeze({
  SO_PHUT_LAP_LAI: 10, // ⚠️ Apps Script chỉ cho phép: 1, 5, 10, 15 hoặc 30
  KHOANG_DEM_CHIEU_CAO_PX: 4,
  TEN_HAM_TRIGGER_LICH: 'capNhatTuDongTheoLich',
  TEN_HAM_TRIGGER_ON_EDIT: 'xuLyKhiChinhSuaTucThoi',
  KHOA_THUOC_TINH_DA_XU_LY: 'LAN_CUOI_DA_FIT_' // + tên sheet = key lưu trong PropertiesService
});

// =============================================================================
// TIỆN ÍCH: ĐỌC CỘT THEO TÊN TIÊU ĐỀ (không phụ thuộc thứ tự cột A,B,C...)
// =============================================================================

/**
 * Tạo bản đồ: tên tiêu đề đã chuẩn hoá -> vị trí cột (0-based).
 */
function taoBanDoCotTheoTieuDe_(headers) {
  const columnMap = Object.create(null);
  headers.forEach(function (header, index) {
    const normalizedHeader = chuanHoaTieuDe_(header);
    if (normalizedHeader && columnMap[normalizedHeader] === undefined) {
      columnMap[normalizedHeader] = index;
    }
  });
  return columnMap;
}

/**
 * Kiểm tra các cột bắt buộc để báo lỗi rõ ràng nếu tên tiêu đề bị sửa/xoá.
 * @param {Object} columnMap kết quả của taoBanDoCotTheoTieuDe_()
 * @param {string[]} requiredHeaders danh sách tên tiêu đề bắt buộc phải có
 */
function kiemTraCotBatBuoc_(columnMap, requiredHeaders) {
  const missingHeaders = requiredHeaders.filter(function (header) {
    return columnMap[chuanHoaTieuDe_(header)] === undefined;
  });
  if (missingHeaders.length > 0) {
    throw new Error(
      'Không tìm thấy các cột bắt buộc: ' + missingHeaders.join(', ') + '.'
    );
  }
}

function layRaw_(columnMap, rawRow, header) {
  const columnIndex = columnMap[chuanHoaTieuDe_(header)];
  return columnIndex === undefined ? '' : rawRow[columnIndex];
}

function layDisplay_(columnMap, displayRow, header) {
  const columnIndex = columnMap[chuanHoaTieuDe_(header)];
  return columnIndex === undefined ? '' : displayRow[columnIndex];
}

function chuanHoaTieuDe_(value) {
  return String(value || '')
    .replace(/\s+/g, ' ')
    .trim()
    .toLocaleLowerCase('vi-VN');
}

// =============================================================================
// TIỆN ÍCH LÕI: NHẬN DIỆN CẤU TRÚC SHEET KetQuaQuet
// =============================================================================

/**
 * Trả về cấu trúc thật của sheet KetQuaQuet, tự xử lý trường hợp sheet bị
 * MẤT HÀNG TIÊU ĐỀ. MỌI tính năng đọc KetQuaQuet đều phải đi qua hàm này —
 * nếu không, mỗi nơi sẽ tự đoán một kiểu và hỏng theo một kiểu khác nhau
 * (đúng thứ đã xảy ra: xuất hàng thì báo lỗi đỏ, còn đánh dấu "đã quét" và
 * dò trùng lặp thì hỏng ÂM THẦM — coi như không có link nào từng được quét).
 *
 * @return {{
 *   tonTai: boolean,        sheet có tồn tại không
 *   sheet: Sheet|null,
 *   columnMap: Object,      tên tiêu đề đã chuẩn hoá -> chỉ số cột (0-based)
 *   hangDauDuLieu: number,  hàng đầu tiên chứa DỮ LIỆU (1 nếu mất tiêu đề)
 *   dungDuPhong: boolean,   true = đang đọc theo thứ tự cột cố định
 *   soCot: number,
 *   soCotNhanRa: number     số tên cột nhận ra được ở hàng 1
 * }}
 */
function layCauTrucKetQuaQuet_(ss) {
  const ketQua = {
    tonTai: false,
    sheet: null,
    columnMap: Object.create(null),
    hangDauDuLieu: KET_QUA_JSON_CONFIG.FIRST_DATA_ROW,
    dungDuPhong: false,
    soCot: 0,
    soCotNhanRa: 0
  };

  const sheet = (ss || SpreadsheetApp.getActiveSpreadsheet())
    .getSheetByName(KET_QUA_JSON_CONFIG.SOURCE_SHEET_NAME);
  if (!sheet) return ketQua;

  ketQua.tonTai = true;
  ketQua.sheet = sheet;

  const soCot = sheet.getLastColumn();
  ketQua.soCot = soCot;
  if (soCot < 1) return ketQua;

  const hangMot = sheet
    .getRange(KET_QUA_JSON_CONFIG.HEADER_ROW, 1, 1, soCot)
    .getDisplayValues()[0];
  const banDoHangMot = taoBanDoCotTheoTieuDe_(hangMot);

  const soNhanRa = KETQUAQUET_COT_MAC_DINH.filter(function (ten) {
    return banDoHangMot[chuanHoaTieuDe_(ten)] !== undefined;
  }).length;
  ketQua.soCotNhanRa = soNhanRa;

  if (soNhanRa >= SO_COT_TOI_THIEU_DE_COI_LA_TIEU_DE) {
    // Hàng 1 đúng là hàng tiêu đề (kể cả khi bạn đã đổi tên/thêm cột riêng
    // như "Trạng thái"). Dùng nguyên bản đồ đọc được — nhờ vậy việc chèn/
    // xoá/di chuyển cột vẫn không làm hỏng gì.
    ketQua.columnMap = banDoHangMot;
    ketQua.hangDauDuLieu = KET_QUA_JSON_CONFIG.FIRST_DATA_ROW;
    return ketQua;
  }

  // Hàng 1 là DỮ LIỆU → sheet đã mất hàng tiêu đề. Đọc theo thứ tự cột cố
  // định mà công cụ TimClipPro ghi ra, và coi hàng 1 là dòng dữ liệu đầu.
  const banDoDuPhong = Object.create(null);
  KETQUAQUET_COT_MAC_DINH.forEach(function (ten, viTri) {
    banDoDuPhong[chuanHoaTieuDe_(ten)] = viTri;
  });
  ketQua.columnMap = banDoDuPhong;
  ketQua.hangDauDuLieu = 1;
  ketQua.dungDuPhong = true;
  return ketQua;
}

/**
 * Câu nhắc hiển thị khi đang phải đọc theo thứ tự cột cố định. Tách riêng
 * để mọi nơi nhắc cùng một câu, và chỉ cần sửa một chỗ.
 */
function nhacMatHangTieuDe_() {
  return (
    'Sheet "' + KET_QUA_JSON_CONFIG.SOURCE_SHEET_NAME + '" đang KHÔNG có hàng ' +
    'tiêu đề (hàng 1 là dữ liệu). Script đang tạm đọc theo thứ tự cột gốc của ' +
    'công cụ nên vẫn chạy đúng.\n\n' +
    'Nên khôi phục hàng tiêu đề bằng menu "CHUYỂN ĐỔI DỮ LIỆU" > ' +
    '"🩹 Khôi phục hàng tiêu đề cho KetQuaQuet" — sau đó bạn có thể chèn/xoá/' +
    'di chuyển cột tuỳ ý mà script vẫn đọc đúng.'
  );
}

// =============================================================================
// TIỆN ÍCH: TRÍCH "KHOÁ SO SÁNH" TỪ MỘT Ô (video ID YouTube hoặc văn bản)
// =============================================================================

/**
 * Trích video ID YouTube (11 ký tự) từ một chuỗi bất kỳ chứa link dạng
 * .../watch?v=XXXXXXXXXXX hoặc youtu.be/XXXXXXXXXXX. Không phân biệt
 * http/https, có/không có www, khoảng trắng thừa ở đầu/cuối, hay các tham
 * số phía sau (&t=, ?si=...). Trả về '' nếu không nhận diện được — nghĩa là
 * ô đó KHÔNG được coi là một "link video" hợp lệ.
 */
function layYoutubeVideoId_(value) {
  const text = String(value || '').trim();
  if (!text) return '';
  const match = text.match(/(?:[?&]v=|youtu\.be\/)([A-Za-z0-9_-]{11})/);
  return match ? match[1] : '';
}

/**
 * Chuẩn hoá một chuỗi văn bản bất kỳ để so khớp dạng LOAI_KHOA.TEXT (dùng
 * cho các khoá không phải link YouTube, ví dụ Id kênh). Rút gọn khoảng
 * trắng thừa, cắt khoảng trắng đầu/cuối, hạ chữ thường theo chuẩn tiếng Việt.
 */
function chuanHoaKhoaVanBan_(value) {
  return String(value || '')
    .replace(/\s+/g, ' ')
    .trim()
    .toLocaleLowerCase('vi-VN');
}

/**
 * Trích "khoá so sánh" từ một ô theo kiểu khoá được khai báo trong
 * DANG_KY_BANG_LIEN_KET. Trả về '' nếu ô không chứa khoá hợp lệ — ô đó sẽ
 * được BỎ QUA (không tô màu, giữ nguyên định dạng) vì không chắc chắn đó là
 * một "link"/khoá thật sự.
 */
function layKhoaSoSanh_(rawValue, loaiKhoa) {
  if (loaiKhoa === LOAI_KHOA.TEXT) {
    return chuanHoaKhoaVanBan_(rawValue);
  }
  return layYoutubeVideoId_(rawValue);
}

// =============================================================================
// TIỆN ÍCH: DỮ LIỆU CÓ HAY KHÔNG / GIÁ TRỊ HOẶC "(trống)"
// =============================================================================

function coDuLieu_(value) {
  if (value instanceof Date) return !isNaN(value.getTime());
  if (typeof value === 'number') return isFinite(value);
  return value !== null && value !== undefined && String(value).trim() !== '';
}

function giaTriHoacTrong_(value) {
  return coDuLieu_(value)
    ? String(value).trim()
    : KET_QUA_JSON_CONFIG.EMPTY_VALUE_TEXT;
}

// =============================================================================
// TIỆN ÍCH: ĐỊNH DẠNG NGÀY GIỜ / THỜI LƯỢNG (dùng cho tính năng xuất JSON)
// =============================================================================

/**
 * Chuẩn hoá thời gian quét thành yyyy-MM-dd HH:mm:ss.
 */
function dinhDangNgayGio_(rawValue, displayValue, timeZone) {
  if (rawValue instanceof Date && !isNaN(rawValue.getTime())) {
    return Utilities.formatDate(rawValue, timeZone, 'yyyy-MM-dd HH:mm:ss');
  }
  const text = String(displayValue || rawValue || '').trim();
  if (!text) return '';
  const normalized = chuanHoaChuoiNgayGio_(text, false, true);
  return normalized || text;
}

/**
 * Chuẩn hoá ngày đăng thành dd/MM/yyyy.
 */
function dinhDangNgay_(rawValue, displayValue, timeZone) {
  if (rawValue instanceof Date && !isNaN(rawValue.getTime())) {
    return Utilities.formatDate(rawValue, timeZone, 'dd/MM/yyyy');
  }
  const text = String(displayValue || rawValue || '').trim();
  if (!text) return '';
  const normalized = chuanHoaChuoiNgayGio_(text, true, false);
  return normalized || text;
}

/**
 * Chuẩn hoá các chuỗi ngày giờ phổ biến (yyyy-MM-dd HH:mm:ss, dd/MM/yyyy,
 * M/d/yyyy h:mm:ss, dd-MM-yyyy...).
 * preferDayFirst = true: ưu tiên dd/MM/yyyy khi ngày và tháng đều <= 12.
 * includeTime = true: trả thêm HH:mm:ss.
 */
function chuanHoaChuoiNgayGio_(text, preferDayFirst, includeTime) {
  const cleanText = String(text || '').trim().replace(/\s+/g, ' ');
  const match = cleanText.match(
    /^(\d{1,4})[\/-](\d{1,2})[\/-](\d{1,4})(?:[ T](\d{1,2}):(\d{1,2})(?::(\d{1,2}))?)?$/
  );
  if (!match) return '';

  const first = Number(match[1]);
  const second = Number(match[2]);
  const third = Number(match[3]);
  const hour = Number(match[4] || 0);
  const minute = Number(match[5] || 0);
  const secondOfMinute = Number(match[6] || 0);

  let year, month, day;
  if (String(match[1]).length === 4) {
    year = first;
    month = second;
    day = third;
  } else {
    year = third;
    if (first > 12) {
      day = first;
      month = second;
    } else if (second > 12) {
      month = first;
      day = second;
    } else if (preferDayFirst) {
      day = first;
      month = second;
    } else {
      month = first;
      day = second;
    }
  }

  if (
    year < 1000 || month < 1 || month > 12 || day < 1 || day > 31 ||
    hour < 0 || hour > 23 || minute < 0 || minute > 59 ||
    secondOfMinute < 0 || secondOfMinute > 59
  ) {
    return '';
  }

  if (includeTime) {
    return (
      padSo_(year, 4) + '-' + padSo_(month, 2) + '-' + padSo_(day, 2) + ' ' +
      padSo_(hour, 2) + ':' + padSo_(minute, 2) + ':' + padSo_(secondOfMinute, 2)
    );
  }
  return padSo_(day, 2) + '/' + padSo_(month, 2) + '/' + padSo_(year, 4);
}

/**
 * Chuẩn hoá thời lượng thành H:mm:ss. Ví dụ: 04:51:33 -> 4:51:33.
 */
function dinhDangThoiLuong_(rawValue, displayValue) {
  const displayText = String(displayValue || '').trim();

  if (displayText) {
    const durationMatch = displayText.match(/^(\d+):(\d{1,2}):(\d{1,2})$/);
    if (durationMatch) {
      return (
        Number(durationMatch[1]) + ':' +
        padSo_(Number(durationMatch[2]), 2) + ':' +
        padSo_(Number(durationMatch[3]), 2)
      );
    }
    if (!/^\d+(?:[.,]\d+)?$/.test(displayText)) {
      return displayText;
    }
  }

  if (typeof rawValue === 'number' && isFinite(rawValue)) {
    const totalSeconds = Math.max(0, Math.round(rawValue * 24 * 60 * 60));
    const hours = Math.floor(totalSeconds / 3600);
    const minutes = Math.floor((totalSeconds % 3600) / 60);
    const seconds = totalSeconds % 60;
    return hours + ':' + padSo_(minutes, 2) + ':' + padSo_(seconds, 2);
  }

  return displayText;
}

function padSo_(number, length) {
  return String(Math.trunc(Number(number) || 0)).padStart(length, '0');
}

// =============================================================================
// TIỆN ÍCH: KHOÁ (LOCK) TRÁNH CHẠY CHỒNG CHÉO
// =============================================================================

/**
 * Lấy document lock với thời gian chờ ngắn. Trả về null nếu không lấy được
 * (đang có tiến trình khác chạy) thay vì treo quá lâu — các hàm gọi tiện
 * ích này cần tự xử lý trường hợp null (bỏ qua an toàn hoặc báo cho người
 * dùng thử lại).
 */
function layKhoaAnToan_(soMiliGiayChoToiDa) {
  const lock = LockService.getDocumentLock();
  try {
    const daKhoa = lock.tryLock(soMiliGiayChoToiDa);
    return daKhoa ? lock : null;
  } catch (err) {
    return null;
  }
}
