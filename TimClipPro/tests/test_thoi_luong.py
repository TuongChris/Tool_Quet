# -*- coding: utf-8 -*-
"""Test chính sách thời lượng media.

Số liệu trong file này đo trực tiếp trên YouTube (đọc `.ytp-time-duration` và
`video.duration` ngay trong trang) và bằng ffprobe trên file đã tải — không phải
giá trị bịa để test xanh. Xem docs/DURATION_DRIFT_AUDIT.md.
"""

import json

import pytest
from clip_metadata import (
    ClipMetadataResolver,
    ResolvedClipMetadata,
    load_metadata_strict,
)
from conftest import M
from engine import Engine, Match, ScanResult, hhmmss

# (video, độ dài media thật, lengthSeconds của YouTube, UI YouTube hiển thị)
DO_THAT = [
    ("D-sVTRR5jm0", 21219.981, 21220, "05:53:39"),
    ("3ixKzIN0et0", 675.861, 676, "00:11:15"),
]


# =====================================================================
#  Formatter: cắt phần lẻ, không làm tròn
# =====================================================================

@pytest.mark.parametrize("vid,media,length_seconds,ui", DO_THAT)
def test_khop_dung_giao_dien_youtube(vid, media, length_seconds, ui):
    """Định dạng độ dài media phải ra ĐÚNG con số YouTube hiển thị."""
    assert hhmmss(media) == ui, f"{vid}: lệch so với UI YouTube"


@pytest.mark.parametrize("vid,media,length_seconds,ui", DO_THAT)
def test_lengthseconds_cua_youtube_khong_dung_de_hien_thi(vid, media,
                                                          length_seconds, ui):
    """`duration` của yt-dlp là lengthSeconds — đã làm tròn, hiển thị ra sai.

    Đây là lý do KHÔNG lấy metadata yt-dlp làm nguồn hiển thị dù nó "chính thống".
    """
    assert hhmmss(length_seconds) != ui
    assert length_seconds == round(media)


@pytest.mark.parametrize("giay,mong_doi", [
    (0, "00:00:00"),
    (59.0, "00:00:59"), (59.1, "00:00:59"), (59.49, "00:00:59"),
    (59.5, "00:00:59"), (59.9, "00:00:59"), (59.999, "00:00:59"),
    (60.0, "00:01:00"), (60.1, "00:01:00"),
    (3599.9, "00:59:59"), (3600.0, "01:00:00"), (3600.9, "01:00:00"),
])
def test_bien_giay_va_gio(giay, mong_doi):
    """Không bao giờ được sinh ra 00:60:00 hay nhảy giờ sớm một giây."""
    assert hhmmss(giay) == mong_doi


def test_hon_24_gio_khong_bi_cuon_vong():
    """TimClipPro quét compilation rất dài; 27 tiếng phải ra 27 tiếng."""
    assert hhmmss(27 * 3600 + 10 * 60 + 5) == "27:10:05"


@pytest.mark.parametrize("giay", [-5, -0.4])
def test_am_thi_ve_khong(giay):
    assert hhmmss(giay) == "00:00:00"


def test_khong_lam_tron_kieu_ngan_hang():
    """`round()` dùng làm tròn về số chẵn nên 4108,5→4108 mà 4109,5→4110.

    Hành vi khó đoán đó chính là một lý do bỏ `round()`.
    """
    assert hhmmss(4108.5) == "01:08:28"
    assert hhmmss(4109.5) == "01:08:29"


def test_moc_hien_thi_khop_link_nhay_moc():
    """Trước đây hiển thị dùng round còn link dùng int → lệch nhau một giây."""
    m = M("a.opus", start=1441.8, hashes=5000)
    link = Engine.link_moc("abc", "", m.start_s)
    assert m.start_hhmmss == "00:24:01"
    assert link.endswith("?t=1441")


# =====================================================================
#  Clip gốc: metadata ưu tiên độ dài media thật
# =====================================================================

def _resolver(tmp_path, entry: dict):
    p = tmp_path / "clips_meta.json"
    p.write_text(json.dumps({"clip.opus": entry}, ensure_ascii=False),
                 encoding="utf-8")
    return ClipMetadataResolver(
        [load_metadata_strict(str(p), kind="live", priority=0)])


def _entry(**kw):
    goc = {"id": "3ixKzIN0et0", "title": "Clip gốc",
           "url": "https://youtu.be/3ixKzIN0et0", "upload_date": "20260101"}
    goc.update(kw)
    return goc


def test_uu_tien_do_dai_media_hon_lengthseconds(tmp_path):
    """676 là lengthSeconds (làm tròn); 675,861 mới là độ dài thật."""
    r = _resolver(tmp_path, _entry(duration=676, duration_media=675.861))
    assert r.resolve("clip.opus").duration == pytest.approx(675.861)
    assert hhmmss(r.resolve("clip.opus").duration) == "00:11:15"


def test_thieu_do_dai_media_thi_lui_ve_metadata_cu(tmp_path):
    """Kho cũ chưa có trường mới vẫn phải chạy, không được vỡ."""
    r = _resolver(tmp_path, _entry(duration=676))
    assert r.resolve("clip.opus").duration == 676


def test_do_dai_media_hong_thi_bo_qua_va_canh_bao(tmp_path):
    for xau in (-1, 0, "abc"):
        r = _resolver(tmp_path, _entry(duration=676, duration_media=xau))
        meta = r.resolve("clip.opus")
        assert meta.duration == 676, f"giá trị hỏng {xau!r} không được ghi đè"


def test_thieu_ca_hai_thi_khong_bia_so(tmp_path):
    r = _resolver(tmp_path, _entry())
    assert r.resolve("clip.opus").duration is None


# =====================================================================
#  Nhất quán giữa các exporter
# =====================================================================

def _ket_qua():
    m = Match(clip="clip.opus", start_s=1441.8, end_s=2078.8, matched_s=601.4,
              clip_offset_s=0.0, hashes=5000, confidence="x", ty_le=80.0)
    return ScanResult(source_name="video", source_ref="https://youtu.be/abc",
                      source_id="abc", duration_s=21219.981, matches=[m])


def test_moi_exporter_hien_cung_mot_thoi_luong(engine, monkeypatch, tmp_path):
    """UI, CSV ngang, CSV dọc và hồ sơ Markdown phải ra cùng một con số.

    Chú ý chữ ký ``dung_dong_ngang(kq, clips_meta=None, *, resolver=...)``: tham số
    thứ hai theo vị trí là `clips_meta`, không phải resolver. Truyền nhầm vị trí thì
    hàm lặng lẽ dựng resolver rỗng và rơi về đọc tên file — cột tên/ngày/thời lượng
    clip gốc vẫn có giá trị trông hợp lý nên rất dễ lọt.
    """
    import bang_ngang
    import dossier

    kq = _ket_qua()
    r = _resolver(tmp_path, _entry(duration=676, duration_media=675.858))
    monkeypatch.setattr(engine, "clip_metadata_resolver", lambda *a, **k: r)

    ngang = bang_ngang.dung_dong_ngang(kq, resolver=r)
    doc = engine.to_rows([kq])
    ho_so = dossier.dung_ho_so(kq, r.compatibility_mapping())

    # Thời lượng CLIP GỐC phải lấy từ `duration_media`, không phải lengthSeconds.
    i_goc = bang_ngang.HEADER_NGANG.index("Thời lượng video gốc 1")
    assert ngang[i_goc] == "00:11:15"
    assert bang_ngang.HEADER_NGANG.index("Tên video gốc 1") == i_goc - 2
    assert ngang[i_goc - 2] == "Clip gốc", "resolver phải được dùng thật"

    # Tổng thời lượng: chỉ CSV ngang và hồ sơ Markdown có trường này (CSV dọc
    # không có cột tổng thời lượng), cả hai phải ra cùng một con số.
    mong_doi = hhmmss(kq.duration_s)
    assert mong_doi == "05:53:39"
    assert ngang[bang_ngang.HEADER_NGANG.index("Thời lượng video vi phạm")] == mong_doi
    assert ho_so.thoi_luong_hhmmss == mong_doi

    # Mốc của đoạn khớp cũng phải nhất quán giữa các exporter và với hồ sơ.
    moc = hhmmss(kq.matches[0].start_s)
    assert moc == "00:24:01"
    assert doc[0][Engine.HEADER.index("Clip bắt đầu từ")] == moc
    assert ho_so.muc[0].tu_hhmmss == moc
    assert ngang[bang_ngang.HEADER_NGANG.index("Đoạn vi phạm 1 trong video vi phạm")].startswith(moc)


class _ResolverRong:
    """Resolver rỗng: test này chỉ quan tâm thời lượng video vi phạm."""

    def resolve(self, ten):
        return ResolvedClipMetadata(
            clip_name=str(ten), video_id="", title="", url="", upload_date="",
            duration=None, resolution_method="filename_fallback",
            status="unresolved", metadata_key="", source_file="",
            source_kind="", complete=False,
            missing_fields=("video_id", "url", "upload_date", "duration"),
            warnings=())


_RESOLVER_RONG = _ResolverRong()
