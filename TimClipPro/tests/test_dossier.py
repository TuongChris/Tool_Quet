# -*- coding: utf-8 -*-
"""Test logic thuần dựng hồ sơ vi phạm."""

from conftest import M

from clip_metadata import ClipMetadataResolver
from dossier import dung_ho_so, render_markdown
from engine import ScanResult


def test_ho_so_rong_khi_khong_co_ket_qua():
    h = dung_ho_so(ScanResult(source_name="v", duration_s=3600))
    assert h.muc == []
    assert h.tong_giay_vi_pham == 0
    assert h.ty_le_video == 0.0


def test_khong_chia_cho_khong():
    h = dung_ho_so(ScanResult(source_name="v", duration_s=0))
    assert h.ty_le_video == 0.0


def test_ba_doan_60_giay_co_tong_180_va_ty_le_5_phan_tram():
    kq = ScanResult(
        source_name="Video X",
        duration_s=3600,
        matches=[
            M("clip-1.mp4", start=0, matched=60),
            M("clip-2.mp4", start=120, matched=60),
            M("clip-3.mp4", start=240, matched=60),
        ],
    )

    h = dung_ho_so(kq)

    assert h.tong_giay_vi_pham == 180
    assert h.ty_le_video == 5.0


def test_dung_day_du_ho_so_va_meta():
    match = M("clip.mp4", start=65.2, hashes=321, matched=10.6)
    match.ty_le = 87.5
    kq = ScanResult(
        source_name="Video vi phạm",
        source_ref="https://www.youtube.com/watch?v=abc",
        source_id="abc",
        duration_s=100,
        matches=[match],
    )

    h = dung_ho_so(kq, {
        "clip.mp4": {
            "id": "goc12345678",
            "title": "Video gốc",
            "url": "https://youtu.be/goc12345678",
        },
    })

    assert h.tieu_de_vi_pham == "Video vi phạm"
    assert h.link_vi_pham == kq.source_ref
    assert h.thoi_luong_hhmmss == "00:01:40"
    assert h.tong_giay_vi_pham == 11
    assert h.ty_le_video == 11.0
    assert len(h.muc) == 1
    assert h.muc[0].tieu_de_goc == "Video gốc"
    assert h.muc[0].link_goc == "https://youtu.be/goc12345678"
    # Mốc media được CẮT phần lẻ, không làm tròn: đoạn kết thúc ở giây 75,8 thì
    # trình phát hiển thị 01:15. Nhờ vậy mốc hiển thị khớp đúng link ?t= bên dưới,
    # vốn đã luôn dùng int(). Xem docs/DURATION_ARCHITECTURE.md.
    assert h.muc[0].tu_hhmmss == "00:01:05"          # start_s = 65,2
    assert h.muc[0].den_hhmmss == "00:01:15"         # end_s   = 75,8
    assert h.muc[0].link_moc == "https://youtu.be/abc?t=65"
    assert h.muc[0].do_dai_giay == 11
    assert h.muc[0].ty_le == 87.5
    assert h.muc[0].hashes == 321


def test_status_loi_luon_tra_ho_so_rong():
    kq = ScanResult(
        source_name="v",
        duration_s=100,
        matches=[M(matched=25)],
        status="error",
        note="Nguồn hỏng",
    )

    h = dung_ho_so(kq)

    assert h.muc == []
    assert h.tong_giay_vi_pham == 0
    assert h.ty_le_video == 0.0


def test_meta_thieu_clip_dung_basename_de_khong_bien_mat():
    h = dung_ho_so(ScanResult(
        source_name="v",
        duration_s=100,
        matches=[M("khong-co-meta.mp4")],
    ))

    assert h.muc[0].tieu_de_goc == "khong-co-meta.mp4"
    assert h.muc[0].link_goc == ""


def test_render_ho_so_rong_van_hop_le():
    s = render_markdown(dung_ho_so(
        ScanResult(source_name="Video X", duration_s=3600),
    ))

    assert isinstance(s, str)
    assert "Hồ sơ khiếu nại" in s
    assert "Video X" in s
    assert "01:00:00" in s
    assert "Không phát hiện" in s


def test_render_co_du_so_muc():
    kq = ScanResult(
        source_name="Video X",
        source_id="abc",
        duration_s=100,
        matches=[
            M("clip-1.mp4", start=10, matched=20),
            M("clip-2.mp4", start=50, matched=25),
        ],
    )

    s = render_markdown(dung_ho_so(kq))

    assert "## Đoạn 1" in s
    assert "## Đoạn 2" in s
    assert "00:00:45" in s
    assert "Bằng chứng được sinh tự động" in s


def test_render_moi_truong_chuoi_rong_deu_hien_gach():
    kq = ScanResult(
        source_name="Video *X*_[1]",
        source_ref="D:/video.mp4",
        duration_s=100,
        matches=[M("   ", matched=10)],
    )

    ho_so = dung_ho_so(kq, meta={})
    ho_so.muc[0].tu_hhmmss = ""
    ho_so.muc[0].den_hhmmss = "   "
    s = render_markdown(ho_so)
    phan_doan = s.split("## Đoạn 1", maxsplit=1)[1]
    cac_dong_du_lieu = [
        dong for dong in phan_doan.splitlines() if dong.startswith("- **")
    ]

    assert "Video *X*_[1]" in s
    assert "**Khoảng thời gian:** — – —" in phan_doan
    assert "**Tên clip gốc:** —" in phan_doan
    assert "**Tiêu đề video gốc:** —" in phan_doan
    assert "**Link nhảy tới mốc:** —" in phan_doan
    assert "**Link video gốc:** —" in phan_doan
    assert all(
        not dong.replace("*", "").rstrip().endswith(":")
        for dong in cac_dong_du_lieu
    )


def test_export_ho_so_tao_dung_so_file(engine, tmp_path, monkeypatch):
    engine.out_dir = str(tmp_path)
    so_lan_doc_meta = 0

    def metadata_resolver():
        nonlocal so_lan_doc_meta
        so_lan_doc_meta += 1
        return ClipMetadataResolver.from_mapping({
            "clip.mp4": {
                "id": "goc12345678",
                "title": "Tiêu đề tiếng Việt",
                "url": "https://youtu.be/goc12345678",
            },
        })

    monkeypatch.setattr(engine, "clip_metadata_resolver", metadata_resolver)
    co_ket_qua = ScanResult(
        source_name='Video: vi phạm?',
        source_id="abc",
        duration_s=100,
        matches=[M("clip.mp4", matched=10)],
    )
    rong = ScanResult(source_name="Video rỗng", duration_s=100)

    cac_file = engine.export_ho_so([co_ket_qua, rong])

    assert so_lan_doc_meta == 1
    assert len(cac_file) == 1
    assert cac_file[0].endswith(".md")
    assert "Video_ vi phạm_" in cac_file[0]
    noi_dung = tmp_path.joinpath(cac_file[0]).read_text(encoding="utf-8")
    assert "Hồ sơ khiếu nại bản quyền" in noi_dung
    assert "Tiêu đề tiếng Việt" in noi_dung


def test_export_ho_so_rong_khong_tao_file(engine, tmp_path, monkeypatch):
    thu_muc_xuat = tmp_path / "out"
    engine.out_dir = str(thu_muc_xuat)
    monkeypatch.setattr(engine, "clip_meta", lambda: {})

    cac_file = engine.export_ho_so([
        ScanResult(source_name="Rỗng"),
        ScanResult(source_name="Lỗi", status="error", matches=[M()]),
    ])

    assert cac_file == []
    assert list(thu_muc_xuat.iterdir()) == []


def test_export_ho_so_danh_sach_rong(engine, tmp_path, monkeypatch):
    thu_muc_xuat = tmp_path / "out"
    engine.out_dir = str(thu_muc_xuat)
    monkeypatch.setattr(engine, "clip_meta", lambda: {})

    cac_file = engine.export_ho_so([])

    assert cac_file == []
    assert list(thu_muc_xuat.iterdir()) == []


def test_export_ho_so_trung_ten_them_hau_to(engine, tmp_path, monkeypatch):
    engine.out_dir = str(tmp_path)
    monkeypatch.setattr(engine, "clip_meta", lambda: {})
    kq = ScanResult(
        source_name="Video",
        duration_s=100,
        matches=[M(matched=10)],
    )
    ten_file = str(tmp_path / "hoso_tuy_chon.md")

    cac_file = engine.export_ho_so([kq, kq], ten_file=ten_file)

    assert cac_file == [
        str(tmp_path / "hoso_tuy_chon.md"),
        str(tmp_path / "hoso_tuy_chon_2.md"),
    ]
