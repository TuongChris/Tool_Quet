# -*- coding: utf-8 -*-
"""Test logic thuần cho watchlist và URL YouTube."""

import json
from types import SimpleNamespace

import pytest

from engine import ScanResult
from luu_tru import LoiDuLieu
from watch import (
    BaoCao,
    MucTheoDoi,
    UngVien,
    WatchList,
    chay_giam_sat,
    doc_watchlist,
    ghi_watchlist,
    id_da_quet,
    lay_ung_vien,
    lay_id_youtube,
    loc_can_quet,
)


class _EngineGia:
    def __init__(self, jobs):
        self.jobs = jobs
        self.limit = None

    def list_jobs(self, limit=200):
        self.limit = limit
        return self.jobs


class _EngineIdsGia:
    def __init__(self):
        self.chi_thanh_cong = None

    def ids_da_quet(self, chi_thanh_cong=True):
        self.chi_thanh_cong = chi_thanh_cong
        return {"truy-van-sql"}


@pytest.mark.parametrize("url", [
    "https://youtu.be/dQw4w9WgXcQ",
    "https://youtu.be/dQw4w9WgXcQ?t=90",
    "https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=X",
    "https://www.youtube.com/shorts/dQw4w9WgXcQ?feature=share",
])
def test_tach_id_cac_dang_url(url):
    assert lay_id_youtube(url) == "dQw4w9WgXcQ"


@pytest.mark.parametrize("url", [
    "https://example.com/abc",
    "https://www.youtube.com/channel/UC123456",
    "https://youtu.be/abc",
    "khong-phai-url",
])
def test_tach_id_url_khong_hop_le(url):
    assert lay_id_youtube(url) == ""


def test_doc_file_khong_ton_tai(tmp_path):
    path = tmp_path / "chua_co.json"

    assert doc_watchlist(str(path)).muc == []
    assert not path.exists()


@pytest.mark.parametrize("noi_dung", ["", "{json hong"])
def test_doc_json_rong_hoac_hong_khong_bi_nuot_loi(tmp_path, noi_dung):
    path = tmp_path / "watchlist.json"
    path.write_text(noi_dung, encoding="utf-8")

    with pytest.raises(LoiDuLieu):
        doc_watchlist(str(path))

    assert len(list(tmp_path.glob("watchlist.json.hong.*"))) == 1


def test_doc_json_co_muc_khong_phai_danh_sach(tmp_path):
    path = tmp_path / "watchlist.json"
    path.write_text('{"muc": null}', encoding="utf-8")

    assert doc_watchlist(str(path)) == WatchList()


def test_doc_bo_qua_muc_thieu_url_va_loai_sai(tmp_path):
    path = tmp_path / "watchlist.json"
    path.write_text(json.dumps({
        "muc": [
            {"loai": "kenh", "url": "https://youtube.com/@kenh"},
            {"loai": "link"},
            {"loai": "sai", "url": "https://youtu.be/dQw4w9WgXcQ"},
        ],
        "kho": "Kho chính",
        "gioi_han_moi_lan": 12,
    }), encoding="utf-8")

    wl = doc_watchlist(str(path))

    assert wl.muc == [MucTheoDoi(
        loai="kenh",
        url="https://youtube.com/@kenh",
    )]
    assert wl.kho == "Kho chính"
    assert wl.gioi_han_moi_lan == 12


def test_ghi_doc_watchlist_giu_nguyen_tieng_viet(tmp_path):
    path = tmp_path / "watchlist.json"
    wl = WatchList(
        muc=[
            MucTheoDoi(
                loai="link",
                url="https://youtu.be/dQw4w9WgXcQ",
                ghi_chu="Khiếu nại bản quyền",
                bat=False,
            ),
        ],
        kho="Kho tiếng Việt",
        gioi_han_moi_lan=7,
    )

    ghi_watchlist(wl, str(path))
    noi_dung = path.read_text(encoding="utf-8")
    doc_lai = doc_watchlist(str(path))

    assert "Khiếu nại bản quyền" in noi_dung
    assert "\\u" not in noi_dung
    assert doc_lai == wl


def test_id_da_quet_khi_lich_su_rong():
    engine = _EngineGia([])

    assert id_da_quet(engine) == set()
    assert engine.limit == 100000


def test_id_da_quet_chi_lay_job_thanh_cong_va_id_khong_rong():
    engine = _EngineGia([
        {"source_id": "ok-1", "status": "ok"},
        {"source_id": "loi-1", "status": "error"},
        {"source_id": "", "status": "ok"},
        {"source_id": None, "status": "ok"},
    ])

    assert id_da_quet(engine) == {"ok-1"}


def test_id_da_quet_co_the_tinh_ca_job_loi():
    engine = _EngineGia([
        {"source_id": "ok-1", "status": "ok"},
        {"source_id": "loi-1", "status": "error"},
    ])

    assert id_da_quet(engine, chi_thanh_cong=False) == {"ok-1", "loi-1"}


def test_id_da_quet_uu_tien_truy_van_sql():
    engine = _EngineIdsGia()

    assert id_da_quet(engine, chi_thanh_cong=False) == {"truy-van-sql"}
    assert engine.chi_thanh_cong is False


def test_khu_trung_lap_trong_ung_vien():
    uv = [UngVien("a", "u1"), UngVien("a", "u1"), UngVien("b", "u2")]

    assert [x.video_id for x in loc_can_quet(uv, set())] == ["a", "b"]


def test_bo_qua_id_da_quet():
    uv = [UngVien("a", "u1"), UngVien("b", "u2")]

    assert [x.video_id for x in loc_can_quet(uv, {"a"})] == ["b"]


def test_loc_can_quet_bo_id_rong_va_giu_nguyen_thu_tu():
    uv = [
        UngVien("", "rong"),
        UngVien("c", "u3"),
        UngVien("a", "u1"),
        UngVien("b", "u2"),
    ]

    assert [x.video_id for x in loc_can_quet(uv, set())] == ["c", "a", "b"]


def test_loc_can_quet_cat_theo_gioi_han():
    uv = [UngVien("a", "u1"), UngVien("b", "u2"), UngVien("c", "u3")]

    assert [x.video_id for x in loc_can_quet(uv, set(), gioi_han=2)] == ["a", "b"]


@pytest.mark.parametrize("gioi_han", [0, -1, 10])
def test_loc_can_quet_khong_cat_khi_gioi_han_khong_ap_dung(gioi_han):
    uv = [UngVien("a", "u1"), UngVien("b", "u2")]

    assert loc_can_quet(uv, set(), gioi_han=gioi_han) == uv


def test_loc_can_quet_danh_sach_rong():
    assert loc_can_quet([], {"a"}, gioi_han=3) == []


def test_lay_ung_vien_watchlist_rong():
    assert lay_ung_vien(WatchList(), lister=lambda url, limit: []) == ([], [])


def test_lay_ung_vien_bo_qua_muc_dang_tat():
    wl = WatchList(muc=[
        MucTheoDoi("link", "https://youtu.be/dQw4w9WgXcQ", bat=False),
        MucTheoDoi("kenh", "https://youtube.com/@tat", bat=False),
    ])

    assert lay_ung_vien(wl, lister=lambda url, limit: []) == ([], [])


def test_lay_ung_vien_link_don_va_bao_link_khong_hop_le():
    wl = WatchList(muc=[
        MucTheoDoi("link", "https://youtu.be/dQw4w9WgXcQ"),
        MucTheoDoi("link", "https://example.com/khong-phai-youtube"),
    ])

    ung_vien, loi = lay_ung_vien(wl, lister=lambda url, limit: [])

    assert ung_vien == [UngVien(
        video_id="dQw4w9WgXcQ",
        url="https://youtu.be/dQw4w9WgXcQ",
        nguon="https://youtu.be/dQw4w9WgXcQ",
    )]
    assert len(loi) == 1
    assert "https://example.com/khong-phai-youtube" in loi[0]


def test_kenh_loi_khong_lam_dut_cac_muc_con_lai():
    def lister_gia(url, limit=None):
        if "hong" in url:
            raise RuntimeError("không kết nối được")
        return [SimpleNamespace(id="x1", title="T", url="u")]

    wl = WatchList(muc=[
        MucTheoDoi("kenh", "https://youtube.com/@hong"),
        MucTheoDoi("kenh", "https://youtube.com/@tot"),
    ])

    ung_vien, loi = lay_ung_vien(wl, lister=lister_gia)

    assert len(ung_vien) == 1
    assert ung_vien[0].video_id == "x1"
    assert len(loi) == 1
    assert "https://youtube.com/@hong" in loi[0]
    assert "không kết nối được" in loi[0]


def test_lay_ung_vien_kenh_rong_khong_bao_loi():
    wl = WatchList(muc=[MucTheoDoi("kenh", "https://youtube.com/@rong")])

    assert lay_ung_vien(wl, lister=lambda url, limit: []) == ([], [])


def test_lay_ung_vien_video_thieu_title_dung_chuoi_rong():
    wl = WatchList(muc=[MucTheoDoi("kenh", "https://youtube.com/@kenh")])
    video_thieu_title = SimpleNamespace(id="x1", url="https://youtu.be/x12345")

    ung_vien, loi = lay_ung_vien(
        wl,
        lister=lambda url, limit: [video_thieu_title],
    )

    assert loi == []
    assert ung_vien[0].tieu_de == ""


def test_lay_ung_vien_dung_lister_mac_dinh_va_truyen_gioi_han(monkeypatch):
    loi_goi = []

    def lister_gia(url, limit=None):
        loi_goi.append((url, limit))
        return [SimpleNamespace(id="x1", title="Tiêu đề", url="u1")]

    monkeypatch.setattr("watch.ChannelSync.list_channel", lister_gia)
    wl = WatchList(muc=[MucTheoDoi("kenh", "https://youtube.com/@kenh")])

    ung_vien, loi = lay_ung_vien(wl, gioi_han_kenh=7)

    assert loi_goi == [("https://youtube.com/@kenh", 7)]
    assert ung_vien == [UngVien("x1", "u1", "Tiêu đề", wl.muc[0].url)]
    assert loi == []


def test_bao_cao_tom_tat_bang_tieng_viet_va_nhieu_dong():
    bao_cao = BaoCao(
        tong_ung_vien=3,
        quet_moi=2,
        loi=["Nguồn hỏng"],
    )

    tom_tat = bao_cao.tom_tat()

    assert "Tổng ứng viên: 3" in tom_tat
    assert "Quét mới: 2" in tom_tat
    assert "Nguồn hỏng" in tom_tat
    assert "\n" in tom_tat


def test_bao_cao_tom_tat_khong_rong_khi_moi_so_dem_bang_khong():
    tom_tat = BaoCao().tom_tat()

    assert tom_tat
    assert "Tổng ứng viên: 0" in tom_tat
    assert "Quét mới: 0" in tom_tat
    assert "Google Sheets: Không sử dụng" in tom_tat


def test_khong_co_ung_vien_thi_khong_tao_csv(engine, monkeypatch):
    monkeypatch.setattr(
        engine,
        "export_csv_ngang",
        lambda ket: pytest.fail("Không được tạo CSV"),
    )

    bao_cao = chay_giam_sat(engine, WatchList(), lister=lambda url, limit: [])

    assert bao_cao.quet_moi == 0
    assert bao_cao.csv_path == ""


def test_tat_ca_da_quet_thi_khong_quet_va_khong_tao_csv(engine, monkeypatch):
    video = SimpleNamespace(id="x1", title="T", url="u1")
    wl = WatchList(muc=[MucTheoDoi("kenh", "kenh-1")])
    monkeypatch.setattr(
        engine,
        "ids_da_quet",
        lambda chi_thanh_cong=True: {"x1"},
    )
    monkeypatch.setattr(
        engine,
        "scan_youtube",
        lambda url, progress=None: pytest.fail("Không được quét lại"),
    )
    monkeypatch.setattr(
        engine,
        "export_csv_ngang",
        lambda ket: pytest.fail("Không được tạo CSV"),
    )

    bao_cao = chay_giam_sat(
        engine,
        wl,
        lister=lambda url, limit: [video],
    )

    assert bao_cao.da_quet_truoc == 1
    assert bao_cao.quet_moi == 0
    assert bao_cao.csv_path == ""


def test_mot_video_loi_khong_lam_dut_luot_quet(engine, monkeypatch, tmp_path):
    videos = [
        SimpleNamespace(id=f"x{i}", title=f"Video {i}", url=f"u{i}")
        for i in range(1, 4)
    ]
    da_goi = []

    def scan_gia(url, progress=None):
        da_goi.append(url)
        if url == "u2":
            raise RuntimeError("mất kết nối")
        return ScanResult(source_name=url, source_ref=url)

    monkeypatch.setattr(engine, "list_jobs", lambda limit: [])
    monkeypatch.setattr(engine, "scan_youtube", scan_gia)
    monkeypatch.setattr(
        engine,
        "export_csv_ngang",
        lambda ket: str(tmp_path / "ket-qua.csv"),
    )
    wl = WatchList(muc=[MucTheoDoi("kenh", "kenh-1")])

    bao_cao = chay_giam_sat(
        engine,
        wl,
        lister=lambda url, limit: videos,
    )

    assert da_goi == ["u1", "u2", "u3"]
    assert bao_cao.quet_moi == 3
    assert len(bao_cao.loi) >= 1
    assert "mất kết nối" in bao_cao.loi[0]


def test_chay_giam_sat_dem_bang_chung_va_bao_scanresult_loi(
    engine,
    monkeypatch,
    tmp_path,
):
    videos = [
        SimpleNamespace(id="x1", title="Một", url="u1"),
        SimpleNamespace(id="x2", title="Hai", url="u2"),
    ]
    ket_qua = [
        ScanResult(source_name="Một", matches=[object(), object()]),
        ScanResult(source_name="Hai", status="error", note="video hỏng"),
    ]

    monkeypatch.setattr(engine, "list_jobs", lambda limit: [])
    monkeypatch.setattr(
        engine,
        "scan_youtube",
        lambda url, progress=None: ket_qua.pop(0),
    )
    monkeypatch.setattr(
        engine,
        "export_csv_ngang",
        lambda ket: str(tmp_path / "ket-qua.csv"),
    )
    wl = WatchList(muc=[MucTheoDoi("kenh", "kenh-1")])

    bao_cao = chay_giam_sat(
        engine,
        wl,
        lister=lambda url, limit: videos,
    )

    assert bao_cao.nguon_co_vi_pham == 1
    assert bao_cao.tong_bang_chung == 2
    assert bao_cao.csv_path == str(tmp_path / "ket-qua.csv")
    assert any("Hai: video hỏng" in dong for dong in bao_cao.loi)


def test_chay_giam_sat_quy_doi_tien_do_tong(engine, monkeypatch, tmp_path):
    videos = [
        SimpleNamespace(id="x1", title="Một", url="u1"),
        SimpleNamespace(id="x2", title="Hai", url="u2"),
    ]
    tien_do = []

    def scan_gia(url, progress=None):
        progress(0.5, "Đang quét")
        return ScanResult(source_name=url)

    monkeypatch.setattr(engine, "list_jobs", lambda limit: [])
    monkeypatch.setattr(engine, "scan_youtube", scan_gia)
    monkeypatch.setattr(
        engine,
        "export_csv_ngang",
        lambda ket: str(tmp_path / "ket-qua.csv"),
    )
    wl = WatchList(muc=[MucTheoDoi("kenh", "kenh-1")])

    chay_giam_sat(
        engine,
        wl,
        progress=lambda pct, msg: tien_do.append((pct, msg)),
        lister=lambda url, limit: videos,
    )

    assert tien_do == [
        (0.25, "[1/2] Đang quét"),
        (0.75, "[2/2] Đang quét"),
    ]


def test_kho_khong_ton_tai_van_tiep_tuc_quet(engine, monkeypatch, tmp_path):
    video = SimpleNamespace(id="x1", title="Một", url="u1")
    monkeypatch.setattr(
        engine,
        "use_kho",
        lambda ten: (_ for _ in ()).throw(RuntimeError("không tồn tại")),
    )
    monkeypatch.setattr(engine, "list_jobs", lambda limit: [])
    monkeypatch.setattr(
        engine,
        "scan_youtube",
        lambda url, progress=None: ScanResult(source_name=url),
    )
    monkeypatch.setattr(
        engine,
        "export_csv_ngang",
        lambda ket: str(tmp_path / "ket-qua.csv"),
    )
    wl = WatchList(
        muc=[MucTheoDoi("kenh", "kenh-1")],
        kho="Kho sai",
    )

    bao_cao = chay_giam_sat(
        engine,
        wl,
        lister=lambda url, limit: [video],
    )

    assert bao_cao.quet_moi == 1
    assert any("Kho sai" in dong and "không tồn tại" in dong for dong in bao_cao.loi)


def test_sheets_chua_san_sang_tra_ghi_chu(engine, monkeypatch):
    class SheetsChuaSanSang:
        def __init__(self, sheet=""):
            self.sheet = sheet

        def san_sang(self):
            return False

        def thieu_gi(self):
            return "Chưa có khóa Google"

    monkeypatch.setattr("watch.SheetsExporter", SheetsChuaSanSang)

    bao_cao = chay_giam_sat(
        engine,
        WatchList(),
        lister=lambda url, limit: [],
        sheet_link="sheet-id",
    )

    assert bao_cao.sheets_ok is False
    assert bao_cao.sheets_note == "Chưa có khóa Google"


def test_sheets_khong_co_du_lieu_thi_khong_bao_da_ghi(engine, monkeypatch):
    class SheetsRong:
        def __init__(self, sheet=""):
            self.sheet = sheet

        def san_sang(self):
            return True

        def append(self, header, rows):
            assert rows == []
            return 0

    monkeypatch.setattr("watch.SheetsExporter", SheetsRong)

    bao_cao = chay_giam_sat(
        engine,
        WatchList(),
        lister=lambda url, limit: [],
        sheet_link="sheet-id",
    )
    tom_tat = bao_cao.tom_tat()

    assert bao_cao.sheets_so_dong == 0
    assert "Đã ghi" not in tom_tat
    assert "File CSV: Không có dữ liệu để ghi" in tom_tat
    assert "Google Sheets: Không có dữ liệu để ghi" in tom_tat


def test_sheets_loi_thi_csv_van_duoc_tao(engine, monkeypatch, tmp_path):
    class SheetsBiLoi:
        def __init__(self, sheet=""):
            self.sheet = sheet

        def san_sang(self):
            return True

        def append(self, header, rows):
            raise RuntimeError("Sheets tạm lỗi")

    video = SimpleNamespace(id="x1", title="Một", url="u1")
    csv_path = str(tmp_path / "ket-qua.csv")
    monkeypatch.setattr("watch.SheetsExporter", SheetsBiLoi)
    monkeypatch.setattr(engine, "list_jobs", lambda limit: [])
    monkeypatch.setattr(
        engine,
        "scan_youtube",
        lambda url, progress=None: ScanResult(source_name=url),
    )
    monkeypatch.setattr(engine, "export_csv_ngang", lambda ket: csv_path)
    monkeypatch.setattr(engine, "to_rows_ngang", lambda ket: [["dong"]])
    wl = WatchList(muc=[MucTheoDoi("kenh", "kenh-1")])

    bao_cao = chay_giam_sat(
        engine,
        wl,
        lister=lambda url, limit: [video],
        sheet_link="sheet-id",
    )

    assert bao_cao.csv_path == csv_path
    assert bao_cao.sheets_ok is False
    assert "Sheets tạm lỗi" in bao_cao.sheets_note


def test_chay_lai_lan_hai_khong_quet_trung(engine, monkeypatch, tmp_path):
    video_id = "abc123XYZ"
    url = f"https://youtu.be/{video_id}"
    wl = WatchList(muc=[MucTheoDoi("link", url)])
    cac_lan_quet = []

    def scan_gia(url_quet, progress=None):
        cac_lan_quet.append(url_quet)
        ket_qua = ScanResult(
            source_name="Video theo dõi",
            source_ref=url_quet,
            source_id=video_id,
        )
        engine.save_job(ket_qua, "youtube")
        return ket_qua

    monkeypatch.setattr(engine, "scan_youtube", scan_gia)
    monkeypatch.setattr(
        engine,
        "export_csv_ngang",
        lambda ket: str(tmp_path / "ket-qua.csv"),
    )

    lan_dau = chay_giam_sat(engine, wl)
    lan_hai = chay_giam_sat(engine, wl)

    assert lan_dau.quet_moi == 1
    assert lan_hai.quet_moi == 0
    assert lan_hai.da_quet_truoc == 1
    assert cac_lan_quet == [url]


def test_chay_giam_sat_dang_doc_giu_cach_xuat_cu(
    engine,
    monkeypatch,
    tmp_path,
):
    video = SimpleNamespace(id="x1", title="Một", url="u1")
    csv_path = str(tmp_path / "ket-qua-doc.csv")
    monkeypatch.setattr(engine, "list_jobs", lambda limit: [])
    monkeypatch.setattr(
        engine,
        "scan_youtube",
        lambda url, progress=None: ScanResult(source_name=url, matches=[object()]),
    )
    monkeypatch.setattr(engine, "export_csv", lambda ket: csv_path)
    monkeypatch.setattr(
        engine,
        "export_csv_ngang",
        lambda ket: pytest.fail("Không được xuất dạng ngang"),
    )
    wl = WatchList(muc=[MucTheoDoi("kenh", "kenh-1")])

    bao_cao = chay_giam_sat(
        engine,
        wl,
        lister=lambda url, limit: [video],
        dang_ngang=False,
    )

    assert bao_cao.csv_path == csv_path


def test_chay_giam_sat_day_sheets_theo_header_ngang(
    engine,
    monkeypatch,
    tmp_path,
):
    from bang_ngang import HEADER_NGANG

    da_ghi = []

    class SheetsGia:
        def __init__(self, sheet=""):
            self.sheet = sheet

        def san_sang(self):
            return True

        def append(self, header, rows):
            da_ghi.append((header, rows))
            return len(rows)

    video = SimpleNamespace(id="x1", title="Một", url="u1")
    rows = [[""] * 34]
    monkeypatch.setattr("watch.SheetsExporter", SheetsGia)
    monkeypatch.setattr(engine, "list_jobs", lambda limit: [])
    monkeypatch.setattr(
        engine,
        "scan_youtube",
        lambda url, progress=None: ScanResult(source_name=url, matches=[object()]),
    )
    monkeypatch.setattr(
        engine,
        "export_csv_ngang",
        lambda ket: str(tmp_path / "ket-qua-ngang.csv"),
    )
    monkeypatch.setattr(engine, "to_rows_ngang", lambda ket: rows)
    wl = WatchList(muc=[MucTheoDoi("kenh", "kenh-1")])

    bao_cao = chay_giam_sat(
        engine,
        wl,
        lister=lambda url, limit: [video],
        sheet_link="sheet-id",
    )

    assert da_ghi == [(HEADER_NGANG, rows)]
    assert bao_cao.sheets_ok is True
    assert bao_cao.sheets_so_dong == 1
    assert "Google Sheets: Đã ghi 1 dòng" in bao_cao.tom_tat()


def test_ghi_tung_phan_khong_trung_dong(engine, monkeypatch, tmp_path):
    da_ghi = []

    class SheetsGia:
        def __init__(self, sheet=""):
            self.sheet = sheet

        def san_sang(self):
            return True

        def append(self, header, rows):
            da_ghi.extend(rows)
            return len(rows)

    videos = [
        SimpleNamespace(id=f"x{i}", title=f"Video {i}", url=f"u{i}")
        for i in range(1, 3)
    ]
    monkeypatch.setattr("watch.SheetsExporter", SheetsGia)
    monkeypatch.setattr(engine, "list_jobs", lambda limit: [])
    monkeypatch.setattr(
        engine,
        "scan_youtube",
        lambda url, progress=None: ScanResult(
            source_name=url,
            matches=[object()],
        ),
    )
    monkeypatch.setattr(
        engine,
        "to_rows_ngang",
        lambda ket: [[kq.source_name] for kq in ket],
    )
    monkeypatch.setattr(
        engine,
        "export_csv_ngang",
        lambda ket: str(tmp_path / "ket-qua.csv"),
    )

    bao_cao = chay_giam_sat(
        engine,
        WatchList(muc=[MucTheoDoi("kenh", "kenh-1")]),
        lister=lambda url, limit: videos,
        sheet_link="sheet-id",
    )

    assert da_ghi == [["u1"], ["u2"]]
    assert bao_cao.sheets_so_dong == 2


def test_ghi_tung_phan_that_bai_van_tiep_tuc(engine, monkeypatch, tmp_path):
    so_lan_append = 0
    da_ghi = []
    da_quet = []

    class SheetsLoiLanDau:
        def __init__(self, sheet=""):
            self.sheet = sheet

        def san_sang(self):
            return True

        def append(self, header, rows):
            nonlocal so_lan_append
            so_lan_append += 1
            if so_lan_append == 1:
                raise RuntimeError("mạng tạm lỗi")
            da_ghi.extend(rows)
            return len(rows)

    videos = [
        SimpleNamespace(id=f"x{i}", title=f"Video {i}", url=f"u{i}")
        for i in range(1, 4)
    ]

    def scan_gia(url, progress=None):
        da_quet.append(url)
        return ScanResult(source_name=url, matches=[object()])

    monkeypatch.setattr("watch.SheetsExporter", SheetsLoiLanDau)
    monkeypatch.setattr(engine, "list_jobs", lambda limit: [])
    monkeypatch.setattr(engine, "scan_youtube", scan_gia)
    monkeypatch.setattr(
        engine,
        "to_rows_ngang",
        lambda ket: [[kq.source_name] for kq in ket],
    )
    monkeypatch.setattr(
        engine,
        "export_csv_ngang",
        lambda ket: str(tmp_path / "ket-qua.csv"),
    )

    bao_cao = chay_giam_sat(
        engine,
        WatchList(muc=[MucTheoDoi("kenh", "kenh-1")]),
        lister=lambda url, limit: videos,
        sheet_link="sheet-id",
    )

    assert da_quet == ["u1", "u2", "u3"]
    assert da_ghi == [["u2"], ["u3"], ["u1"]]
    assert bao_cao.sheets_so_dong == 3
    assert any(
        "Không ghi được kết quả từng phần" in dong
        and "mạng tạm lỗi" in dong
        for dong in bao_cao.loi
    )


def test_tat_ghi_tung_phan_giu_mot_batch_cuoi(engine, monkeypatch, tmp_path):
    cac_batch = []

    class SheetsGia:
        def __init__(self, sheet=""):
            self.sheet = sheet

        def san_sang(self):
            return True

        def append(self, header, rows):
            cac_batch.append(rows)
            return len(rows)

    videos = [
        SimpleNamespace(id=f"x{i}", title=f"Video {i}", url=f"u{i}")
        for i in range(1, 3)
    ]
    engine.config.ghi_tung_phan = False
    monkeypatch.setattr("watch.SheetsExporter", SheetsGia)
    monkeypatch.setattr(engine, "list_jobs", lambda limit: [])
    monkeypatch.setattr(
        engine,
        "scan_youtube",
        lambda url, progress=None: ScanResult(
            source_name=url,
            matches=[object()],
        ),
    )
    monkeypatch.setattr(
        engine,
        "to_rows_ngang",
        lambda ket: [[kq.source_name] for kq in ket],
    )
    monkeypatch.setattr(
        engine,
        "export_csv_ngang",
        lambda ket: str(tmp_path / "ket-qua.csv"),
    )

    chay_giam_sat(
        engine,
        WatchList(muc=[MucTheoDoi("kenh", "kenh-1")]),
        lister=lambda url, limit: videos,
        sheet_link="sheet-id",
    )

    assert cac_batch == [[["u1"], ["u2"]]]
