/**
 * ############################################################################
 * TOÀN BỘ APPS SCRIPT CHO GOOGLE SHEET "TOOL QUÉT" — MỘT FILE DUY NHẤT
 * ############################################################################
 *
 * CÁCH DÙNG (làm một lần, ~2 phút):
 *
 *   1. Mở Google Sheet → menu «Tiện ích mở rộng» → «Apps Script».
 *   2. XOÁ HẾT các tệp .gs cũ trong dự án (Code.gs, File 01…07, v.v.) — nếu
 *      để lẫn bản cũ, Apps Script sẽ báo lỗi "đã khai báo trùng tên" vì cả
 *      dự án dùng CHUNG một phạm vi biến toàn cục.
 *   3. Tạo một tệp duy nhất (đặt tên gì cũng được, ví dụ «Code.gs»), dán
 *      TOÀN BỘ nội dung file này vào, bấm 💾 Lưu.
 *   4. Quay lại Google Sheet, TẢI LẠI TRANG (F5). Menu «CHUYỂN ĐỔI DỮ LIỆU»
 *      sẽ hiện ra trên thanh menu.
 *   5. Chạy menu «🩹 Khôi phục hàng tiêu đề cho KetQuaQuet» MỘT LẦN.
 *   6. Chạy menu «⚙️ Cài đặt tự động hoá» MỘT LẦN (Google sẽ hỏi cấp quyền —
 *      đây là bước bình thường, bấm cho phép).
 *
 * ----------------------------------------------------------------------------
 * BẢN NÀY SỬA GÌ SO VỚI BẢN CŨ
 * ----------------------------------------------------------------------------
 *
 * ❶ LỖI «Không tìm thấy các cột bắt buộc: Thời gian quét, Link kênh vi phạm…»
 *
 *   Nguyên nhân: sheet KetQuaQuet đã MẤT HÀNG TIÊU ĐỀ — hàng 1 hiện là dữ
 *   liệu thật. Bản cũ luôn coi hàng 1 là tiêu đề nên nó đi tìm tên cột
 *   trong một hàng dữ liệu và tất nhiên không thấy cột nào.
 *
 * ❷ HAI TÍNH NĂNG KHÁC CŨNG ĐANG HỎNG VÌ CÙNG NGUYÊN NHÂN — nhưng hỏng ÂM
 *   THẦM, không báo gì cả:
 *     • Đánh dấu link "đã quét": trả về danh sách rỗng → TOÀN BỘ link bên
 *       «Link SML» / «Link Cory» bị tô về trắng như chưa từng được quét.
 *     • Dò link bị quét trùng: ngừng hoạt động hoàn toàn.
 *
 *   Nay mọi nơi đọc KetQuaQuet đều đi qua layCauTrucKetQuaQuet_(): tự nhận
 *   ra hàng 1 là tiêu đề hay dữ liệu, và nếu là dữ liệu thì đọc theo thứ tự
 *   cột gốc của công cụ + coi hàng 1 là dòng dữ liệu đầu tiên (bản cũ luôn
 *   bắt đầu từ hàng 2 nên còn bỏ sót mất dòng đầu).
 *
 * ❸ BẢN MẪU XUẤT MỚI: mỗi tiêu đề mục có một dòng trống ngay sau nó; đoạn
 *   vi phạm tách thành mục riêng; danh sách video gốc lùi xuống mục kế tiếp.
 *   Số mục được đánh ĐỘNG nên đoạn văn bản không bao giờ nhảy số.
 *
 *   Hai dòng «Thời gian quét» và «Tổng số đoạn video gốc phát hiện» mặc định
 *   KHÔNG in ra. Muốn lấy lại: tìm khối MAU_XUAT ở phần A3 bên dưới và đổi
 *   false thành true — phần đánh số mục tự điều chỉnh theo.
 *
 * ❹ THÊM MENU «🩹 Khôi phục hàng tiêu đề cho KetQuaQuet» để chèn lại hàng
 *   tiêu đề vĩnh viễn. Chỉ chèn thêm MỘT hàng, không xoá/sửa dữ liệu nào.
 *
 * ----------------------------------------------------------------------------
 * MỤC LỤC (dùng Ctrl+F để nhảy tới)
 * ----------------------------------------------------------------------------
 *   PHẦN 01 — Cấu hình chung & tiện ích dùng chung
 *   PHẦN 02 — Menu
 *   PHẦN 03 — Xuất hàng đang chọn thành đoạn văn bản
 *   PHẦN 04 — Tự động đánh dấu link "đã quét"
 *   PHẦN 05 — Tự động căn chỉnh chiều cao hàng
 *   PHẦN 06 — Cài đặt / quản lý tự động hoá (trigger)
 *   PHẦN 07 — Bảng Tổng quan & tiện ích bổ sung
 *
 * ⚠️ THỨ TỰ CÁC PHẦN TRONG FILE NÀY CÓ Ý NGHĨA: các hằng số khai báo bằng
 * "const" ở cấp cao nhất được nạp theo đúng thứ tự từ trên xuống. Đừng đảo
 * PHẦN 01 xuống dưới — mọi phần khác đều phụ thuộc vào hằng số của nó.
 * (Riêng các hàm thì gọi lẫn nhau được bất kể thứ tự.)
 */

// ==========================================================================
// PHẦN 01  (nguồn: File01_CauHinh_TienIch.gs)
// ==========================================================================

/**
 * ============================================================================
 * PHẦN 01 — CẤU HÌNH CHUNG & TIỆN ÍCH DÙNG CHUNG
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

// ==========================================================================
// PHẦN 02  (nguồn: File02_Menu.gs)
// ==========================================================================

/**
 * ============================================================================
 * PHẦN 02 — MENU
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

// ==========================================================================
// PHẦN 03  (nguồn: File03_XuatHangDaChon.gs)
// ==========================================================================

/**
 * ============================================================================
 * PHẦN 03 — XUẤT HÀNG ĐANG CHỌN THÀNH ĐOẠN VĂN BẢN CÓ CẤU TRÚC
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

// ==========================================================================
// PHẦN 04  (nguồn: File04_DanhDauLinkDaQuet.gs)
// ==========================================================================

/**
 * ============================================================================
 * PHẦN 04 — TÍNH NĂNG 1: TỰ ĐỘNG ĐÁNH DẤU LINK "ĐÃ QUÉT"
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

// ==========================================================================
// PHẦN 05  (nguồn: File05_CanChieuCaoHang.gs)
// ==========================================================================

/**
 * ============================================================================
 * PHẦN 05 — TÍNH NĂNG 2: TỰ ĐỘNG CĂN CHỈNH CHIỀU CAO HÀNG
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

// ==========================================================================
// PHẦN 06  (nguồn: File06_TuDongHoa.gs)
// ==========================================================================

/**
 * ============================================================================
 * PHẦN 06 — CÀI ĐẶT / QUẢN LÝ TỰ ĐỘNG HOÁ (TRIGGER)
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

// ==========================================================================
// PHẦN 07  (nguồn: File07_TongQuan_TienIchBoSung.gs)
// ==========================================================================

/**
 * ============================================================================
 * PHẦN 07 — BẢNG TỔNG QUAN & TIỆN ÍCH BỔ SUNG
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
