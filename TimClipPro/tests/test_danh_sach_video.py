# -*- coding: utf-8 -*-
"""Khoá lại ba lời hứa của tab «Danh sách video trong kho»:

tên video lấy từ metadata chứ KHÔNG từ tên file, chạy hoàn toàn offline, và
không ghi một byte nào xuống thư mục kho.
"""

from __future__ import annotations

import json
import os
import socket
import urllib.request

import pytest

import danh_sach_video as dsv
from danh_sach_video import (
    GHI_CHU_KHONG_XAC_DINH,
    GHI_CHU_SUY_TU_TEN_FILE,
    KetQuaKho,
    LoiKho,
    hang_bang_tinh,
    liet_ke_kho,
    liet_ke_theo_ten_kho,
    ten_trang_tinh,
)

# Ca thật của người dùng: tên file có dấu GẠCH DƯỚI, tên YouTube có dấu HAI CHẤM.
FILE_WORLDCUP = "20250115 - SML Movie_ The World Cup! [gRZah-YY0FM].opus"
TITLE_WORLDCUP = "SML Movie: The World Cup!"


def _meta(video_id: str, title: str, **them) -> dict:
    muc = {
        "id": video_id,
        "title": title,
        "url": f"https://youtu.be/{video_id}",
        "upload_date": "20250115",
        "duration": 1358,
    }
    muc.update(them)
    return muc


def _kho(tmp_path, ten_file: list[str], meta: dict | None = None,
         meta_text: str | None = None) -> str:
    """Dựng một thư mục kho giả. Trả về đường dẫn.

    ``meta_text`` khác None thì ghi NGUYÊN VĂN chuỗi đó (cần cho ca khoá trùng và
    JSON hỏng — ``json.dump`` không tạo được khoá trùng).
    """
    thu_muc = tmp_path / "kho"
    thu_muc.mkdir(exist_ok=True)
    for ten in ten_file:
        (thu_muc / ten).write_bytes(b"")
    if meta_text is not None:
        (thu_muc / "clips_meta.json").write_text(meta_text, encoding="utf-8")
    elif meta is not None:
        (thu_muc / "clips_meta.json").write_text(
            json.dumps(meta, ensure_ascii=False), encoding="utf-8")
    return str(thu_muc)


def _anh_chup(thu_muc: str) -> dict:
    """{tên: (kích thước, mtime)} của MỌI mục — để chứng minh không ghi gì."""
    return {
        ten: (os.stat(os.path.join(thu_muc, ten)).st_size,
              os.stat(os.path.join(thu_muc, ten)).st_mtime_ns)
        for ten in sorted(os.listdir(thu_muc))
    }


class _ExporterGia:
    def __init__(self, link: str = "", worksheet: str = ""):
        self.link = link
        self.worksheet = worksheet
        self.da_ghi: list[tuple[list, list]] = []

    def san_sang(self) -> bool:
        return True

    def thieu_gi(self) -> str:
        return ""

    def email_service_account(self) -> str:
        return "bot@duan.iam.gserviceaccount.com"

    def ghi_de(self, header, rows, **kwargs):
        self.da_ghi.append((header, rows))
        return len(rows)


@pytest.fixture
def khong_mang(monkeypatch):
    """Làm test thất bại ngay nếu module âm thầm gọi mạng."""

    def chan(*args, **kwargs):
        del args, kwargs
        raise AssertionError("Tab danh sách video không được gọi mạng")

    monkeypatch.setattr(socket, "create_connection", chan)
    monkeypatch.setattr(urllib.request, "urlopen", chan)

    import requests
    import yt_dlp

    monkeypatch.setattr(requests.sessions.Session, "request", chan)
    monkeypatch.setattr(yt_dlp, "YoutubeDL", chan)
    return chan


# ---------------------------------------------------------------------------
# Lấy đúng tên video — lý do tồn tại của cả tính năng
# ---------------------------------------------------------------------------

def test_lay_dung_ten_youtube_chu_khong_phai_ten_file(tmp_path):
    thu_muc = _kho(tmp_path, [FILE_WORLDCUP],
                   {FILE_WORLDCUP: _meta("gRZah-YY0FM", TITLE_WORLDCUP)})
    kq = liet_ke_kho("SML", thu_muc)
    assert kq.so_video == 1
    assert kq.dong[0].ten_video == TITLE_WORLDCUP      # dấu HAI CHẤM, không phải "_"
    assert kq.dong[0].chinh_xac is True
    assert kq.dong[0].ghi_chu == ""


def test_title_dai_hon_80_ky_tu_khong_bi_cat_theo_ten_file(tmp_path):
    """Ca thật kho Cory: `lam_sach_ten` cắt tên file ở 80 ký tự, metadata thì không."""
    day_du = ("BOWLER BALL IS BACK BUT I BROUGHT BACKUP THIS TIME | "
              "Little Nightmares (The Hideaway) NEW DLC")
    ten_file = ("20250115 - BOWLER BALL IS BACK BUT I BROUGHT BACKUP THIS TIME _ "
                "Little Nightmares (The Hide [Ql1jVlSshCQ].opus")
    thu_muc = _kho(tmp_path, [ten_file], {ten_file: _meta("Ql1jVlSshCQ", day_du)})
    kq = liet_ke_kho("Cory", thu_muc)
    assert kq.dong[0].ten_video == day_du
    assert kq.dong[0].chinh_xac is True


def test_thieu_upload_date_nhung_title_that_van_duoc_coi_la_chinh_xac(tmp_path):
    """Chứng minh vì sao KHÔNG được dùng ``resolution_method`` làm tiêu chí.

    ``_resolved_from_entry`` ép ``effective_method="filename_fallback"`` khi bất kỳ
    trường nào rỗng mà tên file suy ra được — kể cả khi title chuẩn 100%.
    """
    from clip_metadata import ClipMetadataResolver

    muc = _meta("gRZah-YY0FM", TITLE_WORLDCUP)
    muc["upload_date"] = ""            # tên file có ngày THẬT 20250115 -> enrich
    thu_muc = _kho(tmp_path, [FILE_WORLDCUP], {FILE_WORLDCUP: muc})

    res = ClipMetadataResolver.from_mapping({FILE_WORLDCUP: muc})
    assert res.resolve(FILE_WORLDCUP).resolution_method == "filename_fallback"

    kq = liet_ke_kho("SML", thu_muc)
    assert kq.dong[0].chinh_xac is True
    assert kq.dong[0].ten_video == TITLE_WORLDCUP


def test_status_partial_van_lay_duoc_ten_dung(tmp_path):
    """Tái hiện kho msa: 100/100 mục ``status="partial"`` mà title hoàn toàn đúng."""
    ten_file = "00000000 - 10 Rules To Get A Guy [aBcDeFgHiJk].opus"
    muc = _meta("aBcDeFgHiJk", "10 Rules To Get A Guy")
    muc["upload_date"] = ""
    thu_muc = _kho(tmp_path, [ten_file], {ten_file: muc})
    kq = liet_ke_kho("msa", thu_muc)
    assert kq.so_chinh_xac == kq.so_video == 1
    assert kq.dong[0].ten_video == "10 Rules To Get A Guy"


def test_title_rong_trong_meta_thi_khong_duoc_coi_la_chinh_xac(tmp_path):
    thu_muc = _kho(tmp_path, [FILE_WORLDCUP],
                   {FILE_WORLDCUP: _meta("gRZah-YY0FM", "")})
    kq = liet_ke_kho("SML", thu_muc)
    assert kq.dong[0].chinh_xac is False
    # Lý do phải chỉ ĐÚNG chỗ cần sửa: mục đã có, chỉ thiếu title. Nói «chưa có
    # trong clips_meta.json» sẽ đẩy người dùng đi chạy «Vá metadata thiếu» — mà
    # bước đó bỏ qua vì entry đã tồn tại, nên tên mãi không đúng.
    assert kq.dong[0].ghi_chu == dsv.GHI_CHU_TITLE_RONG


def test_tra_title_theo_khoa_metadata_chu_khong_theo_ten_file(tmp_path):
    """Khoá trong clips_meta.json KHÁC tên file trên đĩa (kho đồng bộ lại đổi ngày).

    Resolver khớp qua mã video 11 ký tự. Nếu ai đó đổi sang tra thẳng bằng tên file
    thì tra trượt và cả kho tụt về tên đã làm sạch — test này khoá đúng điều đó.
    """
    khoa_cu = "20240101 - Ten cu [gRZah-YY0FM].opus"
    thu_muc = _kho(tmp_path, [FILE_WORLDCUP],
                   {khoa_cu: _meta("gRZah-YY0FM", TITLE_WORLDCUP)})
    kq = liet_ke_kho("SML", thu_muc)
    assert kq.dong[0].ten_file == FILE_WORLDCUP
    assert kq.dong[0].ten_video == TITLE_WORLDCUP
    assert kq.dong[0].chinh_xac is True


def test_tieu_de_chua_ngoac_vuong_11_ky_tu_van_lay_duoc_ten_tu_metadata(tmp_path):
    """«[Compilation]», «[Official_MV]», «[4K-REMASTER]»… đều dài đúng 11 ký tự.

    Trước audit TCP-12, ``clip_metadata._ids_from_value`` quét toàn chuỗi nên mục
    metadata trông như có hai mã video; Mức 2 cứu được tên nhưng vẫn phải gắn cảnh báo
    mâu thuẫn danh tính GIẢ (bản trước của test này khoá đúng cảnh báo đó). Nay mã
    video chỉ đọc ở hậu tố ``[ID].đuôi`` nên đây là khớp chính xác, không cảnh báo.
    """
    title = "SML Movie: Jeffy [Compilation] Best Of"
    ten_file = "20240101 - SML Movie_ Jeffy [Compilation] Best Of [gRZah-YY0FM].opus"
    thu_muc = _kho(tmp_path, [ten_file], {ten_file: _meta("gRZah-YY0FM", title)})
    kq = liet_ke_kho("SML", thu_muc)
    assert kq.dong[0].ten_video == title          # còn nguyên dấu HAI CHẤM
    assert kq.dong[0].chinh_xac is True
    assert kq.dong[0].ghi_chu == ""


def test_mau_thuan_ma_video_that_van_lay_ten_nhung_nhac_doi_chieu(tmp_path):
    """Mức 2 vẫn cần cho mâu thuẫn THẬT: metadata ghi mã khác hậu tố tên file."""
    title = "SML Movie: Jeffy Best Of"
    ten_file = "20240101 - SML Movie_ Jeffy Best Of [gRZah-YY0FM].opus"
    thu_muc = _kho(tmp_path, [ten_file], {ten_file: _meta("BBBBBBBBBBB", title)})
    kq = liet_ke_kho("SML", thu_muc)
    assert kq.dong[0].ten_video == title
    assert kq.dong[0].chinh_xac is False
    assert kq.dong[0].ghi_chu == dsv.GHI_CHU_MAU_THUAN_DANH_TINH
    # Và KHÔNG được vu cho dữ liệu lành lặn là sai kiểu / bị bỏ qua.
    assert not any("sai kiểu" in cb for cb in kq.canh_bao)


def test_thu_muc_kho_chua_ngoac_vuong_11_ky_tu_khong_lam_ca_kho_mat_ten(tmp_path):
    """Kho đặt ở «D:\\Kho\\[SML-Channel]\\audio» từng làm 100% số dòng mất tên thật."""
    cha = tmp_path / "[SML-Channel]"
    cha.mkdir()
    thu_muc = _kho(cha, [FILE_WORLDCUP],
                   {FILE_WORLDCUP: _meta("gRZah-YY0FM", TITLE_WORLDCUP)})
    kq = liet_ke_kho("SML", thu_muc)
    assert kq.dong[0].ten_video == TITLE_WORLDCUP
    assert kq.dong[0].chinh_xac is True


def test_ten_file_co_khoang_trang_dau_khong_hien_duoi_opus(tmp_path):
    """``basename_compatible`` có strip nên chốt so chuỗi thô để lọt ca này."""
    thu_muc = _kho(tmp_path, [" test.opus"], {})
    kq = liet_ke_kho("X", thu_muc)
    assert not kq.dong[0].ten_video.lower().endswith(".opus")
    assert kq.dong[0].ten_video == "test"


def test_kho_chua_he_co_clips_meta_json_thi_canh_bao_ro(tmp_path):
    """Ca thật phổ biến nhất: chép tay 500 file vào kho, chưa từng đồng bộ kênh."""
    thu_muc = _kho(tmp_path, [FILE_WORLDCUP])      # KHÔNG tạo clips_meta.json
    kq = liet_ke_kho("SML", thu_muc)
    assert kq.so_video == 1
    assert kq.so_chinh_xac == 0
    assert any("chưa có file clips_meta.json" in cb for cb in kq.canh_bao)
    assert any("chưa lấy được tên chính xác" in cb for cb in kq.canh_bao)


def test_thieu_entry_thi_suy_tu_ten_file_va_bi_danh_dau(tmp_path):
    thu_muc = _kho(tmp_path, [FILE_WORLDCUP], {})
    kq = liet_ke_kho("SML", thu_muc)
    dong = kq.dong[0]
    assert kq.so_video == 1                       # không âm thầm bỏ file của người dùng
    assert dong.chinh_xac is False
    assert dong.ghi_chu == GHI_CHU_SUY_TU_TEN_FILE
    assert ".opus" not in dong.ten_video
    assert not dong.ten_video.startswith("20250115")
    assert kq.canh_bao


def test_entry_ambiguous_khong_lam_ten_video_thanh_ca_ten_file(tmp_path):
    """ID trong meta khác ID trong tên file -> ``r.title`` là NGUYÊN tên file."""
    thu_muc = _kho(tmp_path, [FILE_WORLDCUP],
                   {FILE_WORLDCUP: _meta("KHACKHACKHA", TITLE_WORLDCUP)})
    kq = liet_ke_kho("SML", thu_muc)
    dong = kq.dong[0]
    assert dong.chinh_xac is False
    assert ".opus" not in dong.ten_video
    assert not dong.ten_video.startswith("20250115")


def test_ten_khong_doan_duoc_thi_khong_hien_duoi_opus(tmp_path):
    thu_muc = _kho(tmp_path, ["abc.opus"], {})
    kq = liet_ke_kho("X", thu_muc)
    assert kq.dong[0].ten_video == "abc"
    assert kq.dong[0].ghi_chu == GHI_CHU_KHONG_XAC_DINH


def test_unicode_va_emoji_trong_title_giu_nguyen(tmp_path):
    title = "🔥 テスト 한국어 cà phê e\u0301 | Tập 1"
    thu_muc = _kho(tmp_path, [FILE_WORLDCUP],
                   {FILE_WORLDCUP: _meta("gRZah-YY0FM", title)})
    kq = liet_ke_kho("SML", thu_muc)
    assert kq.dong[0].ten_video == title


# ---------------------------------------------------------------------------
# Metadata hỏng / thiếu — phải cảnh báo, không được im lặng và không được ném lỗi
# ---------------------------------------------------------------------------

def test_clips_meta_trung_khoa_thi_canh_bao_ro_chu_khong_im_lang(tmp_path):
    """``load_metadata_strict`` TỪ CHỐI TOÀN BỘ file khi có khoá trùng."""
    muc = json.dumps(_meta("gRZah-YY0FM", TITLE_WORLDCUP), ensure_ascii=False)
    text = '{"%s": %s, "%s": %s}' % (FILE_WORLDCUP, muc, FILE_WORLDCUP, muc)
    thu_muc = _kho(tmp_path, [FILE_WORLDCUP], meta_text=text)
    kq = liet_ke_kho("SML", thu_muc)
    assert kq.canh_bao
    assert any("clips_meta.json" in cb and "TỪ CHỐI TOÀN BỘ" in cb
               for cb in kq.canh_bao)
    assert all(not d.chinh_xac for d in kq.dong)


def test_clips_meta_hong_khong_bi_doi_ten_va_van_hien_duoc_danh_sach(tmp_path):
    thu_muc = _kho(tmp_path, [FILE_WORLDCUP], meta_text="{ khong phai json ")
    truoc = _anh_chup(thu_muc)
    kq = liet_ke_kho("SML", thu_muc)
    assert kq.so_video == 1
    assert any("clips_meta.json" in cb for cb in kq.canh_bao)
    # KHÔNG đổi tên thành `.hong.*`, không sinh `.bak`, không sửa nội dung.
    assert _anh_chup(thu_muc) == truoc


def test_clips_meta_rong_thi_van_canh_bao(tmp_path):
    thu_muc = _kho(tmp_path, [FILE_WORLDCUP], meta_text="{}")
    kq = liet_ke_kho("SML", thu_muc)
    assert any("RỖNG" in cb for cb in kq.canh_bao)


def test_khong_ghi_gi_vao_thu_muc_kho(tmp_path):
    thu_muc = _kho(tmp_path, [FILE_WORLDCUP, "abc.opus"],
                   {FILE_WORLDCUP: _meta("gRZah-YY0FM", TITLE_WORLDCUP)})
    truoc = _anh_chup(thu_muc)
    liet_ke_kho("SML", thu_muc)
    assert _anh_chup(thu_muc) == truoc


def test_liet_ke_khong_bao_gio_goi_mang(tmp_path, khong_mang):
    thu_muc = _kho(tmp_path, [FILE_WORLDCUP],
                   {FILE_WORLDCUP: _meta("gRZah-YY0FM", TITLE_WORLDCUP)})
    kq = liet_ke_kho("SML", thu_muc)
    hang_bang_tinh(kq)
    assert kq.so_video == 1


# ---------------------------------------------------------------------------
# Duyệt thư mục
# ---------------------------------------------------------------------------

def test_bo_qua_thu_muc_con_va_file_khong_phai_audio(tmp_path):
    thu_muc = _kho(tmp_path, ["that.opus", "HOA.OPUS", "ghi_chu.txt"], {})
    os.mkdir(os.path.join(thu_muc, "gia.opus"))     # THƯ MỤC CON đuôi .opus
    kq = liet_ke_kho("X", thu_muc)
    assert kq.so_video == 2
    assert {d.ten_file for d in kq.dong} == {"that.opus", "HOA.OPUS"}


def test_kho_khong_co_file_opus_tra_danh_sach_rong_va_canh_bao(tmp_path):
    thu_muc = _kho(tmp_path, ["ghi_chu.txt"], {})
    kq = liet_ke_kho("X", thu_muc)
    assert kq.dong == ()
    assert kq.canh_bao
    assert "chưa có file audio" in kq.tom_tat()


def test_giu_ca_hai_video_trung_tieu_de_va_stt_lien_tuc(tmp_path):
    f1 = "20250115 - Trung ten [aaaaaaaaaaa].opus"
    f2 = "20250116 - Trung ten [bbbbbbbbbbb].opus"
    thu_muc = _kho(tmp_path, [f1, f2], {
        f1: _meta("aaaaaaaaaaa", "Trùng tên"),
        f2: _meta("bbbbbbbbbbb", "Trùng tên"),
    })
    kq = liet_ke_kho("X", thu_muc)
    assert kq.so_video == 2
    assert [d.stt for d in kq.dong] == [1, 2]
    assert {d.ten_video for d in kq.dong} == {"Trùng tên"}


def test_bat_bien_so_chinh_xac_cong_so_can_kiem_tra_bang_so_video(tmp_path):
    f_ok = "20250115 - Tot [aaaaaaaaaaa].opus"
    f_thieu = "20250115 - Thieu entry [bbbbbbbbbbb].opus"
    f_rong = "20250115 - Title rong [ccccccccccc].opus"
    f_mau_thuan = "20250115 - Mau thuan [ddddddddddd].opus"
    thu_muc = _kho(tmp_path, [f_ok, f_thieu, f_rong, f_mau_thuan], {
        f_ok: _meta("aaaaaaaaaaa", "Tốt"),
        f_rong: _meta("ccccccccccc", ""),
        f_mau_thuan: _meta("eeeeeeeeeee", "Mâu thuẫn"),
    })
    kq = liet_ke_kho("X", thu_muc)
    assert kq.so_video == len(kq.dong) == 4
    assert kq.so_chinh_xac + kq.so_can_kiem_tra == kq.so_video
    assert kq.dong_can_kiem_tra() == tuple(d for d in kq.dong if not d.chinh_xac)
    assert kq.so_chinh_xac == 1


@pytest.mark.parametrize("thu_muc", ["", "  ", r"D:\khong_ton_tai_bao_gio_12345"])
def test_thu_muc_rong_hoac_khong_ton_tai_bao_loi_tieng_viet(thu_muc):
    with pytest.raises(LoiKho) as e:
        liet_ke_kho("SML", thu_muc)
    assert "«SML»" in str(e.value)
    assert "thư mục" in str(e.value)


def test_progress_duoc_goi_va_ket_thuc_o_100(tmp_path):
    thu_muc = _kho(tmp_path, [FILE_WORLDCUP],
                   {FILE_WORLDCUP: _meta("gRZah-YY0FM", TITLE_WORLDCUP)})
    moc: list[tuple[float, str]] = []
    liet_ke_kho("SML", thu_muc, progress=lambda p, m: moc.append((p, m)))
    assert moc
    assert moc[-1][0] == 1.0
    assert [p for p, _ in moc] == sorted(p for p, _ in moc)
    assert all(isinstance(m, str) and m for _, m in moc)
    liet_ke_kho("SML", thu_muc)                 # không truyền progress vẫn chạy


def test_liet_ke_theo_ten_kho_khong_thay_thi_bao_ro_cac_kho_hien_co(tmp_path):
    khos = [{"ten": "A", "thu_muc": str(tmp_path)}]
    with pytest.raises(LoiKho) as e:
        liet_ke_theo_ten_kho(khos, "SLM")
    assert "Không còn kho tên" in str(e.value)
    assert "A" in str(e.value)

    with pytest.raises(LoiKho) as e2:
        liet_ke_theo_ten_kho([], "X")
    assert "Chưa có kho nào" in str(e2.value)


def test_liet_ke_theo_ten_kho_chap_nhan_kho_chua_gan_thu_muc():
    """``add_kho(ten)`` mặc định ``thu_muc=""`` — không được ném KeyError."""
    with pytest.raises(LoiKho) as e:
        liet_ke_theo_ten_kho([{"ten": "A", "db": "kho_a.pklz"}], "A")
    assert "chưa gán thư mục" in str(e.value)


# ---------------------------------------------------------------------------
# Tên trang tính
# ---------------------------------------------------------------------------

def test_ten_trang_tinh_giu_nguyen_ten_kho_an_toan():
    assert ten_trang_tinh("SML") == "DanhSachVideo_SML"
    assert ten_trang_tinh("Ẩm thực") == "DanhSachVideo_Ẩm thực"


@pytest.mark.parametrize("ten", ["Kho: A/B", "A[1]", "Kho's", "X" * 200, "", "   "])
def test_ten_trang_tinh_lam_sach_ky_tu_cam_va_khong_qua_100(ten):
    r = ten_trang_tinh(ten)
    assert r.startswith("DanhSachVideo_")
    assert len(r) <= 100
    assert not any(c in r for c in "[]:\\/?*'")


@pytest.mark.parametrize("a, b", [
    ("A:B", "A/B"),
    ("X" * 200, "X" * 199 + "Y"),
    # Khoảng trắng BÊN TRONG là khác biệt thật: `Engine.add_kho` chỉ strip hai đầu
    # nên đây là hai kho riêng, mỗi kho một file vân tay. Trên dropdown Streamlit
    # chúng hiện ra y hệt nhau, người dùng không thể tự phát hiện đẩy nhầm.
    ("SML A", "SML  A"),
    ("Kho A", "Kho A"),        # U+00A0 rất hay dính khi copy-paste
    ("Am\tthuc", "Am thuc"),
    ("X Y", "X\nY"),
])
def test_hai_kho_khac_nhau_khong_bao_gio_cung_mot_trang_tinh(a, b):
    """Test này đỏ nghĩa là đẩy kho này sẽ XOÁ SẠCH danh sách của kho kia."""
    assert a.strip() != b.strip(), "hai tên phải thật sự là hai kho khác nhau"
    assert ten_trang_tinh(a) != ten_trang_tinh(b)


def test_ten_kho_trong_giong_da_bam_khong_dung_trang_tinh_voi_ten_bi_bam():
    """Hai không gian tên (có băm / giữ nguyên) phải RỜI NHAU.

    Băm md5 của ``"A:B"`` đúng bằng ``0a85c0``, nên nếu tên ``"A_B_0a85c0"`` được
    giữ nguyên thì hai kho hoàn toàn khác nhau sẽ ghi đè lên nhau.
    """
    bi_bam = ten_trang_tinh("A:B")
    assert bi_bam == "DanhSachVideo_A_B_0a85c0"
    assert ten_trang_tinh("A_B_0a85c0") != bi_bam


def test_khong_cap_ten_kho_thuc_te_nao_dung_trang_tinh():
    """Quét rộng: mọi tên kho khác nhau phải ra trang tính khác nhau.

    Khoá chuẩn là ``k.strip()`` — ĐÚNG danh tính mà ``Engine.add_kho`` lưu. Tuyệt
    đối không dùng ``" ".join(k.split())``: đó chính là phép chuẩn hoá bên trong
    hàm đang được kiểm, nên lấy nó làm khoá là tự định nghĩa va chạm khoảng trắng
    thành hợp lệ — test sẽ xanh trong khi bug đang sống.
    """
    import random
    import string

    random.seed(7)
    ky_tu = string.ascii_letters + "0123456789_:/?*[]' "
    ten_kho = {"SML", "Cory", "Ẩm thực", "A:B", "A/B", "A?B", "A_B_0a85c0",
               "A*B", "A[1]", "X" * 200, "X" * 199 + "Y", "Kho's",
               "SML A", "SML  A", "SML   A", "SML\tA", "SML\xa0A", "SML\nA"}
    ten_kho.update("".join(random.choice(ky_tu) for _ in range(random.randint(1, 12)))
                   for _ in range(2000))
    # ``add_kho`` từ chối tên rỗng, nên bỏ chúng khỏi corpus thay vì gộp làm một.
    ten_kho = {k for k in ten_kho if k.strip()}

    da_thay: dict[str, str] = {}
    for k in ten_kho:
        chuan = k.strip()
        t = ten_trang_tinh(k)
        assert da_thay.setdefault(t, chuan) == chuan, (
            f"va chạm «{t}»: {chuan!r} và {da_thay[t]!r}")


# ---------------------------------------------------------------------------
# Đổi sang hàng bảng tính và đẩy lên Sheets
# ---------------------------------------------------------------------------

def _ket_qua(dong: list[tuple[int, str]]) -> KetQuaKho:
    return KetQuaKho(
        ten_kho="SML", thu_muc="D:\\ClipGocSML",
        dong=tuple(dsv.DongVideo(stt=i, ten_video=t, ten_file=f"{i}.opus",
                                 chinh_xac=True) for i, t in dong),
    )


def test_hang_bang_tinh_dung_2_cot_stt_la_so_nguyen():
    header, rows = hang_bang_tinh(_ket_qua([(1, "Một"), (2, "Hai")]))
    assert header == ["STT", "Tên video"]
    assert all(len(r) == 2 for r in rows)
    assert isinstance(rows[0][0], int)          # chuỗi "9" sẽ sắp SAU "10" trên Sheets
    header.append("Thừa")
    assert dsv.HEADER == ["STT", "Tên video"]   # trả list MỚI mỗi lần gọi


def test_hang_bang_tinh_giu_nguyen_tieu_de_bat_dau_bang_dau_tru():
    """Đường Sheets ghi RAW nên bọc ``o_bang_tinh_an_toan`` chỉ làm tên video sai."""
    _, rows = hang_bang_tinh(_ket_qua([(1, "-- Best of --"), (2, "=SUM(A1)")]))
    assert rows[0][1] == "-- Best of --"
    assert rows[1][1] == "=SUM(A1)"


def test_day_len_sheet_dung_ten_trang_tinh_va_dung_du_lieu():
    ghi_nho = {}

    def tao(link, ten):
        ghi_nho["link"], ghi_nho["ten"] = link, ten
        return _ExporterGia(link, ten)

    ok, tb = dsv.day_len_sheet(_ket_qua([(1, "Một"), (2, "Hai")]), "link",
                               tao_exporter=tao)
    assert ok is True
    assert ghi_nho["ten"] == "DanhSachVideo_SML"
    assert "DanhSachVideo_SML" in tb and "2 video" in tb


def test_day_len_sheet_tu_choi_bang_rong_va_khong_mo_ket_noi():
    da_goi = []
    ok, tb = dsv.day_len_sheet(
        KetQuaKho(ten_kho="SML", thu_muc="d"), "link",
        tao_exporter=lambda link, ten: da_goi.append(1))
    assert ok is False
    assert "không ghi đè" in tb
    assert da_goi == []


@pytest.mark.parametrize("thieu_that, phai_co, khong_duoc_co", [
    # Nguyên văn của SheetsExporter.thieu_gi() -> câu người dùng làm theo được.
    ("Chưa cài thư viện — chạy: pip install gspread google-auth",
     "HUONG_DAN.md", "sheets.py"),
    ("Chưa có file google_key.json trong thư mục dự án "
     "(xem hướng dẫn ở đầu sheets.py)", "HUONG_DAN.md", "ở đầu sheets.py"),
    ("Chưa nhập link Google Sheet", "thanh bên", "sheets.py"),
])
def test_day_len_sheet_thieu_cau_hinh_tra_cau_lam_theo_duoc(
        thieu_that, phai_co, khong_duoc_co):
    """Không bao giờ bảo người làm nội dung đi mở mã nguồn."""

    class _Thieu(_ExporterGia):
        def san_sang(self):
            return False

        def thieu_gi(self):
            return thieu_that

    ok, tb = dsv.day_len_sheet(_ket_qua([(1, "Một")]), "",
                               tao_exporter=lambda link, ten: _Thieu())
    assert ok is False
    assert phai_co in tb
    assert khong_duoc_co not in tb


@pytest.mark.parametrize("loi, phai_co", [
    ("PERMISSION_DENIED: caller lacks permission", "Người chỉnh sửa"),
    ("404 not found", "link Google Sheet"),
    ("Connection reset by peer", "không tạo dòng trùng"),
])
def test_day_len_sheet_loi_thi_tra_cau_tieng_viet_co_goi_y(loi, phai_co):
    class _Loi(_ExporterGia):
        def ghi_de(self, header, rows, **kwargs):
            raise RuntimeError(loi)

    ok, tb = dsv.day_len_sheet(_ket_qua([(1, "Một")]), "link",
                               tao_exporter=lambda link, ten: _Loi())
    assert ok is False
    assert phai_co in tb


# ---------------------------------------------------------------------------
# Duyệt kho: thư mục con, và kho chép tay từ video gốc
# ---------------------------------------------------------------------------

def test_duyet_ca_thu_muc_con(tmp_path):
    """`engine.liet_ke_media` dùng os.walk nên vân tay có cả thư mục con.

    Chỉ duyệt một tầng thì bảng thiếu hẳn một phần kho mà không một dòng cảnh báo,
    người dùng tưởng chưa tải và đi tải lại.
    """
    f_ngoai = "20250115 - Ngoai [aaaaaaaaaaa].opus"
    f_trong = "20240101 - Trong [bbbbbbbbbbb].opus"
    thu_muc = _kho(tmp_path, [f_ngoai], {
        f_ngoai: _meta("aaaaaaaaaaa", "Video ngoài"),
        f_trong: _meta("bbbbbbbbbbb", "Video trong thư mục con"),
    })
    con = os.path.join(thu_muc, "nam2024")
    os.mkdir(con)
    open(os.path.join(con, f_trong), "wb").close()

    kq = liet_ke_kho("X", thu_muc)
    assert kq.so_video == 2
    assert {d.ten_video for d in kq.dong} == {"Video ngoài", "Video trong thư mục con"}
    assert kq.so_chinh_xac == 2      # tra metadata bằng basename, không bằng đường dẫn
    # Cột «Tên file» giữ đường dẫn tương đối để chỉ đúng chỗ.
    trong = next(d for d in kq.dong if d.ten_video == "Video trong thư mục con")
    assert trong.ten_file == os.path.join("nam2024", f_trong)


def test_kho_chep_tay_tu_video_goc_khong_bi_xui_dong_bo_lai_kenh(tmp_path):
    """Kho .mp4 CÓ vân tay hợp lệ (engine.MEDIA_EXTS nhận .mp4). Xui đồng bộ kênh
    là bắt tải lại hàng chục GB để chữa một thứ không hỏng."""
    thu_muc = tmp_path / "kho"
    thu_muc.mkdir()
    for ten in ("clip1.mp4", "clip2.mkv", "clip3.mp4"):
        (thu_muc / ten).write_bytes(b"")

    kq = liet_ke_kho("KhoChepTay", str(thu_muc))
    assert kq.so_video == 0
    assert kq.so_media_khac == 3
    canh = " ".join(kq.canh_bao)
    assert "3 file video/audio khác" in canh
    assert "ĐỪNG chạy đồng bộ kênh" in canh
    assert "file .opus" in kq.tom_tat()


def test_kho_rong_that_van_giu_cau_cu(tmp_path):
    thu_muc = _kho(tmp_path, ["ghi_chu.txt"], {})
    kq = liet_ke_kho("X", thu_muc)
    assert kq.so_media_khac == 0
    assert any("chưa có file .opus nào" in cb for cb in kq.canh_bao)
    assert not any("ĐỪNG chạy đồng bộ kênh" in cb for cb in kq.canh_bao)


# ---------------------------------------------------------------------------
# Cảnh báo phải nói đúng sự thật
# ---------------------------------------------------------------------------

def test_khong_xui_chay_va_metadata_thieu_vi_no_khong_ghi_title(tmp_path):
    """`ChannelSync.va_metadata` chỉ ghi upload_date/duration, KHÔNG BAO GIỜ ghi
    title. Chỉ đường tới nó là đẩy người dùng vào tác vụ mạng hàng giờ vô ích."""
    thu_muc = _kho(tmp_path, [FILE_WORLDCUP])      # không có clips_meta.json
    kq = liet_ke_kho("SML", thu_muc)
    canh = " ".join(kq.canh_bao)
    assert "Lấy lại tên video thật cho kho này" in canh
    assert "«Vá metadata thiếu»" not in canh


def test_muc_hong_dinh_dang_bao_bang_tieng_viet_va_ghi_chu_dung_cho(tmp_path):
    """Mã «entry_not_object:...» từng lọt nguyên tiếng Anh lên giao diện."""
    thu_muc = _kho(tmp_path, [FILE_WORLDCUP],
                   meta_text=json.dumps({FILE_WORLDCUP: "SML Movie"},
                                        ensure_ascii=False))
    kq = liet_ke_kho("SML", thu_muc)
    canh = " ".join(kq.canh_bao)
    assert "entry_not_object" not in canh
    assert "bị hỏng định dạng" in canh
    assert kq.dong[0].ghi_chu == dsv.GHI_CHU_MUC_HONG


@pytest.mark.parametrize("truong, gia_tri, ten_that", [
    ("publication_date", "2024-01-01", "publication_date"),
    ("duration_media", "675,858", "duration_media"),
    ("title", 12345, "title"),
])
def test_canh_bao_neu_dung_ten_truong_that_trong_file(tmp_path, truong, gia_tri, ten_that):
    """`clip_metadata` nối «invalid_field:» vào mã đã mang tiền tố «invalid_», nên
    phần đuôi KHÔNG phải tên trường — người dùng đi tìm sẽ không bao giờ thấy."""
    muc = _meta("gRZah-YY0FM", TITLE_WORLDCUP)
    muc[truong] = gia_tri
    thu_muc = _kho(tmp_path, [FILE_WORLDCUP], {FILE_WORLDCUP: muc})
    kq = liet_ke_kho("SML", thu_muc)
    canh = " ".join(kq.canh_bao)
    assert f"«{ten_that}»" in canh
    assert "invalid_" not in canh


def test_trung_ma_video_bao_dung_van_de_la_mot_video_thanh_hai_dong(tmp_path):
    """Hai file cùng mã video: `resolve` vẫn trả tên bình thường cho cả hai, nên
    nói «đều bị đánh dấu cần kiểm tra» là sai — người dùng tìm mãi không thấy."""
    f1 = "20250115 - Ban mot [gRZah-YY0FM].opus"
    f2 = "20250116 - Ban hai [gRZah-YY0FM].opus"
    thu_muc = _kho(tmp_path, [f1, f2], {
        f1: _meta("gRZah-YY0FM", "Bản một"),
        f2: _meta("gRZah-YY0FM", "Bản hai"),
    })
    kq = liet_ke_kho("X", thu_muc)
    canh = " ".join(kq.canh_bao)
    assert "dùng chung" in canh
    assert f1 in canh and f2 in canh
    assert "đánh dấu cần kiểm tra" not in canh
