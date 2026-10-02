# -*- coding: utf-8 -*-
"""Quét tăng dần: quét từng đoạn từ đầu, thấy bằng chứng thì dừng.

Đo thật 19/08/2026 trên video 35 tiếng (quét trọn hết 40 phút):
  * 180 đoạn khớp rải ĐỀU — 25-27 đoạn mỗi khối 5 tiếng, suốt cả 35 tiếng.
  * Khoảng cách giữa hai đoạn liên tiếp: trung vị 12 phút, LỚN NHẤT 19 phút.
  * Cả 64 vị trí đặt cửa sổ 3 tiếng đều bắt được video — không có điểm mù.
  * Với `top_n=1`: bằng chứng chọn từ 1 giờ đầu có 43.815 hash, quét trọn 35 tiếng
    được 47.432 hash — tức 92% sức mạnh từ 1/35 khối lượng.

RÀNG BUỘC KHÔNG ĐƯỢC PHÁ: dừng sớm chỉ đổi THỨ TỰ làm việc, KHÔNG đổi độ phủ.
Không tìm thấy gì thì phải quét hết video, đúng như trước.
"""

import pytest
from engine import Config, Engine, Match


def _eng(tmp_path, **cfg):
    e = Engine(root=str(tmp_path), data_dir=str(tmp_path / "d"),
               out_dir=str(tmp_path / "r"))
    e.config = Config(**cfg)
    return e


# ---------------------------------------------------------------- chia đoạn

def test_video_ngan_van_quet_tron_mot_luot(tmp_path):
    """Chia nhỏ video ngắn chỉ tốn thêm chi phí nạp kho vân tay mỗi đoạn."""
    e = _eng(tmp_path, quet_tang_dan=True, quet_tang_dan_tu_gio=10.0)
    assert e._doan_quet_tang_dan(3 * 3600) == [(0.0, 3 * 3600)]


def test_video_dai_bi_chia_theo_buoc(tmp_path):
    e = _eng(tmp_path, quet_tang_dan=True, quet_tang_dan_tu_gio=10.0,
             quet_tang_dan_buoc_gio=3.0)
    doan = e._doan_quet_tang_dan(11 * 3600)
    assert doan[0] == (0.0, 3 * 3600)
    assert len(doan) == 4
    assert doan[-1][1] == 11 * 3600, "đoạn cuối phải chạm đúng cuối video"


def test_cac_doan_phu_kin_khong_ho(tmp_path):
    """Hở một khoảng là mất bằng chứng ở đó mà không ai biết."""
    e = _eng(tmp_path, quet_tang_dan=True, quet_tang_dan_tu_gio=1.0,
             quet_tang_dan_buoc_gio=2.0)
    doan = e._doan_quet_tang_dan(35 * 3600)
    assert doan[0][0] == 0.0
    for truoc, sau in zip(doan, doan[1:]):
        assert truoc[1] == sau[0], f"hở giữa {truoc} và {sau}"
    assert doan[-1][1] == 35 * 3600


@pytest.mark.parametrize("cfg", [
    {"quet_tang_dan": False},
    {"quet_tang_dan": True, "quet_tang_dan_buoc_gio": 0.0},
])
def test_tat_tinh_nang_thi_ve_hanh_vi_cu(tmp_path, cfg):
    e = _eng(tmp_path, quet_tang_dan_tu_gio=1.0, **cfg)
    assert e._doan_quet_tang_dan(35 * 3600) == [(0.0, 35 * 3600)]


# ---------------------------------------------------------------- cắt theo khoảng

def test_cut_chunks_giu_nguyen_luoi_moc_khi_cat_tung_doan(tmp_path, monkeypatch):
    """Mốc từng khúc phải y hệt khi quét trọn, nếu không hai đường cho kết quả khác
    nhau và các đoạn nối nhau sẽ cắt trùng."""
    e = _eng(tmp_path, chunk_s=3600, overlap_max_s=180)
    monkeypatch.setattr(e, "duration_of", lambda p: 20000.0)
    monkeypatch.setattr(e, "_overlap_thuc_te", lambda *a, **k: 200)
    goi = []

    def ffmpeg_gia(cmd, **kw):
        goi.append(float(cmd[cmd.index("-ss") + 1]))
        with open(cmd[-1], "wb") as f:
            f.write(b"x" * 2048)

        class R:
            returncode = 0
            cancelled = False
            timed_out = False
            stdout = stderr = ly_do = ""
        return R()

    import engine as engine_module

    # Mọi lời gọi FFmpeg của engine đi qua `chay_lenh_media` (có huỷ + hạn im lặng).
    monkeypatch.setattr(engine_module, "chay_lenh_media", ffmpeg_gia)
    tron, _ = e._cut_chunks("phim.mp4", workspace=str(tmp_path))
    moc_tron = list(goi)

    goi.clear()
    a, _ = e._cut_chunks("phim.mp4", workspace=str(tmp_path), tu_giay=0, den_giay=7000)
    b, _ = e._cut_chunks("phim.mp4", workspace=str(tmp_path), tu_giay=7000, den_giay=20000)
    assert goi == moc_tron, "ghép các đoạn phải ra đúng lưới mốc của lượt quét trọn"
    assert len(a) + len(b) == len(tron)


def test_cut_chunks_khoang_rong_tra_ve_rong(tmp_path, monkeypatch):
    e = _eng(tmp_path)
    monkeypatch.setattr(e, "duration_of", lambda p: 1000.0)
    monkeypatch.setattr(e, "_overlap_thuc_te", lambda *a, **k: 60)
    ds, tong = e._cut_chunks("phim.mp4", workspace=str(tmp_path),
                             tu_giay=5000, den_giay=6000)
    assert ds == [] and tong == 1000.0, "thời lượng trả về luôn là của CẢ file"


# ---------------------------------------------------------------- dừng sớm

def _dung_scan(e, monkeypatch, tong, co_ket_qua_tu_giay):
    """Giả lập: chỉ các khúc bắt đầu từ `co_ket_qua_tu_giay` mới có kết quả."""
    monkeypatch.setattr(e, "require", lambda **k: None)
    monkeypatch.setattr(e, "duration_of", lambda p: tong)
    da_cat = []

    def cut(path, progress=None, pct0=0, pct1=0, workspace=None,
            tu_giay=0.0, den_giay=None):
        het = tong if den_giay is None else min(den_giay, tong)
        moc = [m for m in range(0, int(tong), 3600) if tu_giay <= m < het]
        da_cat.extend(moc)
        return [f"chunk_{m}.wav" for m in moc], tong

    monkeypatch.setattr(e, "_cut_chunks", cut)
    monkeypatch.setattr(e, "_quet_tho", lambda chunks, *a, **k: [
        c for c in chunks if int(c.split("_")[1].split(".")[0]) >= co_ket_qua_tu_giay])
    monkeypatch.setattr(e, "_merge", lambda tho: [
        Match(clip="x.opus", start_s=0, end_s=1, matched_s=1, clip_offset_s=0,
              hashes=9999, confidence="chac") for _ in tho[:1]])
    monkeypatch.setattr(e, "_gan_chi_so", lambda ds, d: None)
    monkeypatch.setattr(e, "_chon_loc", lambda ds, d: (ds, []))
    return da_cat


def test_thay_bang_chung_som_thi_dung_khong_quet_tiep(tmp_path, monkeypatch):
    """`top_n=1` là chiều ẩn của phép đo gốc, nay phải viết ra.

    Bản đo trong CLAUDE.md mục 12 chạy ở `top_n=1`, nhưng `Config.top_n` mặc định là
    5 — nên test này (dùng mặc định) từng khoá nhầm hành vi "một ứng viên là dừng"
    cho MỌI `top_n`. Xem `test_top_n_5_ma_moi_co_1_ung_vien_thi_PHAI_quet_tiep`.
    """
    e = _eng(tmp_path, quet_tang_dan=True, quet_tang_dan_tu_gio=1.0,
             quet_tang_dan_buoc_gio=3.0, quet_da_toc_do=False, top_n=1)
    da_cat = _dung_scan(e, monkeypatch, 35 * 3600, co_ket_qua_tu_giay=0)
    p = tmp_path / "phim.mp4"
    p.write_bytes(b"x")
    kq = e.scan_media(str(p), luu_lich_su=False)
    assert kq.status == "ok"
    assert max(da_cat) < 3 * 3600, "chỉ được cắt đoạn đầu"
    assert kq.pham_vi_quet_s == 3 * 3600
    assert kq.duration_s == 35 * 3600, "thời lượng VIDEO vẫn phải là 35 giờ"
    assert kq.quet_mot_phan is True
    assert "dừng sớm" in kq.note.lower()


def test_khong_thay_gi_thi_QUET_HET_khong_mat_do_phu(tmp_path, monkeypatch):
    """Ràng buộc quan trọng nhất: dừng-khi-thấy chỉ đổi thứ tự, không đổi độ phủ."""
    e = _eng(tmp_path, quet_tang_dan=True, quet_tang_dan_tu_gio=1.0,
             quet_tang_dan_buoc_gio=3.0, quet_da_toc_do=False)
    # Bằng chứng nằm tận giờ thứ 30 — đúng ca mà quét-3h-cứng sẽ bỏ sót.
    da_cat = _dung_scan(e, monkeypatch, 35 * 3600, co_ket_qua_tu_giay=30 * 3600)
    p = tmp_path / "phim.mp4"
    p.write_bytes(b"x")
    kq = e.scan_media(str(p), luu_lich_su=False)
    assert max(da_cat) >= 30 * 3600, "phải quét tới chỗ có bằng chứng"
    assert kq.matches, "vẫn phải tìm ra"
    assert kq.pham_vi_quet_s >= 30 * 3600


def test_video_sach_thi_quet_tron_ven(tmp_path, monkeypatch):
    e = _eng(tmp_path, quet_tang_dan=True, quet_tang_dan_tu_gio=1.0,
             quet_tang_dan_buoc_gio=3.0, quet_da_toc_do=False)
    da_cat = _dung_scan(e, monkeypatch, 12 * 3600, co_ket_qua_tu_giay=10**9)
    p = tmp_path / "phim.mp4"
    p.write_bytes(b"x")
    kq = e.scan_media(str(p), luu_lich_su=False)
    assert max(da_cat) >= 11 * 3600, "video sạch phải được quét hết mới kết luận"
    assert kq.pham_vi_quet_s == 12 * 3600
    assert kq.quet_mot_phan is False, "quét trọn thì không được gắn nhãn quét một phần"


def test_bao_cao_khong_bao_gio_nham_quet_mot_phan_thanh_quet_tron(tmp_path):
    """Nếu nhãn này sai, sau này nhìn lại sẽ tưởng đã quét cả video."""
    from engine import ScanResult
    assert ScanResult(source_name="x", duration_s=3600, pham_vi_quet_s=3600).quet_mot_phan is False
    assert ScanResult(source_name="x", duration_s=3600, pham_vi_quet_s=600).quet_mot_phan is True
    assert ScanResult(source_name="x").quet_mot_phan is False, "chưa quét thì không kết luận"


# ---------------------------------------------------------------- tải một phần

def test_gioi_han_tai_chi_ap_dung_cho_video_dai(tmp_path):
    e = _eng(tmp_path, tai_mot_phan=True, quet_tang_dan_tu_gio=10.0,
             quet_tang_dan_buoc_gio=3.0)
    assert e._gioi_han_tai(3 * 3600) is None, "video ngắn thì tải trọn như cũ"
    assert e._gioi_han_tai(66 * 3600) == 3 * 3600
    assert e._gioi_han_tai(0) is None, "chưa biết thời lượng thì đừng cắt bừa"


def test_tat_tai_mot_phan_thi_ve_hanh_vi_cu(tmp_path):
    e = _eng(tmp_path, tai_mot_phan=False, quet_tang_dan_tu_gio=1.0,
             quet_tang_dan_buoc_gio=3.0)
    assert e._gioi_han_tai(66 * 3600) is None


def test_ten_file_mot_phan_khong_bi_nham_la_ban_day_du(tmp_path):
    """Nếu nhận nhầm, lượt quét sau sẽ lặng lẽ chỉ quét 3 tiếng rồi báo "không tìm
    thấy" cho cả video 66 tiếng — sai mà không có dấu hiệu nào."""
    import glob
    import os

    e = _eng(tmp_path)
    vid = "SfVmNaVsQv0"
    ten = e._ten_phan_dau(vid, 10800)
    os.makedirs(e.dl_dir, exist_ok=True)
    for t in (ten + ".webm",):
        open(os.path.join(e.dl_dir, t), "wb").write(b"x")
    day_du = glob.glob(os.path.join(e.dl_dir, vid + ".*"))
    assert day_du == [], "glob tìm bản đầy đủ KHÔNG được khớp phải bản một phần"
    assert glob.glob(os.path.join(e.dl_dir, ten + ".*")), "bản một phần vẫn tìm lại được"


def test_moi_gioi_han_co_ten_rieng(tmp_path):
    e = _eng(tmp_path)
    assert e._ten_phan_dau("abc", 10800) != e._ten_phan_dau("abc", 21600)


def test_tai_mot_phan_van_phai_ghi_chu_len_bao_cao(tmp_path, monkeypatch):
    """Lỗi thật 19/08: tải 3h của video 66h thì `scan_media` chỉ thấy file 3 tiếng nên
    tưởng đã quét trọn và KHÔNG ghi chú gì. `scan_youtube` sửa lại thời lượng sau đó,
    nhưng quên ghi chú — báo cáo và lịch sử im lặng như thể đã quét cả 66 tiếng."""
    from engine import Match, ScanResult

    # `top_n=1`: một đoạn là đủ nên không phải tải nốt. Với `top_n` mặc định (5) thì
    # một đoạn KHÔNG đủ — ca đó có test riêng bên dưới.
    e = _eng(tmp_path, tai_mot_phan=True, quet_tang_dan_tu_gio=10.0,
             quet_tang_dan_buoc_gio=3.0, top_n=1)
    monkeypatch.setattr(e, "require", lambda **k: None)
    monkeypatch.setattr(e, "youtube_info", lambda url: {
        "id": "abc", "title": "video 66h", "duration": 66 * 3600, "channel": "",
        "channel_id": "", "channel_url": "", "upload_date": ""})
    gan = {}

    def tai(url, vid, progress=None, gioi_han_giay=None):
        gan["gioi_han"] = gioi_han_giay
        return str(tmp_path / "part.mp4")

    monkeypatch.setattr(e, "download_audio", tai)

    def quet(path, **k):
        r = ScanResult(source_name="video 66h", duration_s=3 * 3600,
                       pham_vi_quet_s=3 * 3600)
        r.matches = [Match(clip="x.opus", start_s=100, end_s=200, matched_s=100,
                           clip_offset_s=0, hashes=9999, confidence="chac")]
        return r

    monkeypatch.setattr(e, "scan_media", quet)
    kq = e.scan_youtube("https://youtu.be/abc", luu_lich_su=False)

    assert gan["gioi_han"] == 3 * 3600, "phải yêu cầu tải đúng 3 tiếng đầu"
    assert kq.duration_s == 66 * 3600, "thời lượng phải là của VIDEO THẬT"
    assert kq.pham_vi_quet_s == 3 * 3600
    assert kq.quet_mot_phan is True
    assert kq.note, "PHẢI ghi chú, nếu không báo cáo im lặng như đã quét trọn"
    assert "66:00:00" in kq.note and "03:00:00" in kq.note


def test_khong_thay_gi_thi_tai_tron_va_khong_ghi_chu_nham(tmp_path, monkeypatch):
    from engine import ScanResult

    e = _eng(tmp_path, tai_mot_phan=True, quet_tang_dan_tu_gio=10.0,
             quet_tang_dan_buoc_gio=3.0)
    monkeypatch.setattr(e, "require", lambda **k: None)
    monkeypatch.setattr(e, "youtube_info", lambda url: {
        "id": "abc", "title": "v", "duration": 66 * 3600, "channel": "",
        "channel_id": "", "channel_url": "", "upload_date": ""})
    lan_tai = []

    def tai(url, vid, progress=None, gioi_han_giay=None):
        lan_tai.append(gioi_han_giay)
        return str(tmp_path / "f.mp4")

    monkeypatch.setattr(e, "download_audio", tai)
    monkeypatch.setattr(e, "scan_media", lambda path, **k: ScanResult(
        source_name="v", duration_s=66 * 3600, pham_vi_quet_s=66 * 3600))
    kq = e.scan_youtube("https://youtu.be/abc", luu_lich_su=False)

    assert lan_tai == [3 * 3600, None], "sạch ở phần đầu thì phải tải trọn rồi quét lại"
    assert kq.quet_mot_phan is False
    assert "chỉ tải" not in (kq.note or "").lower()


# =====================================================================
#  top_n > 1: dừng sớm phải xét CHÍNH SÁCH CHỌN LỌC, không phải "có một cái nào chưa"
#
#  `Config.top_n` mặc định là 5, nên đây là hành vi MẶC ĐỊNH chứ không phải ca hiếm.
#  Người dùng đặt top_n=5 để lấy 5 bằng chứng rải đều cho hồ sơ khiếu nại; đoạn đầu
#  tìm được 1 ứng viên mà dừng luôn là mất trắng 4 suất, im lặng.
# =====================================================================

def _dung_scan_nhieu(e, monkeypatch, tong, so_ung_vien_moi_khuc, clip_theo_khuc=True):
    """Như `_dung_scan` nhưng mỗi khúc sinh ra N ứng viên; tên clip theo mốc khúc."""
    monkeypatch.setattr(e, "require", lambda **k: None)
    monkeypatch.setattr(e, "duration_of", lambda p: tong)
    da_cat = []

    def cut(path, progress=None, pct0=0, pct1=0, workspace=None,
            tu_giay=0.0, den_giay=None):
        het = tong if den_giay is None else min(den_giay, tong)
        moc = [m for m in range(0, int(tong), 3600) if tu_giay <= m < het]
        da_cat.extend(moc)
        return [f"chunk_{m}.wav" for m in moc], tong

    monkeypatch.setattr(e, "_cut_chunks", cut)
    monkeypatch.setattr(e, "_quet_tho", lambda chunks, *a, **k: list(chunks))

    def merge(tho):
        ra = []
        for khuc in tho:
            moc = int(khuc.split("_")[1].split(".")[0])
            for i in range(so_ung_vien_moi_khuc):
                ten = f"clip_{moc}_{i}.opus" if clip_theo_khuc else "chung.opus"
                ra.append(Match(clip=ten, start_s=moc, end_s=moc + 1, matched_s=1,
                                clip_offset_s=0, hashes=9999, confidence="chac"))
        return ra

    monkeypatch.setattr(e, "_merge", merge)
    monkeypatch.setattr(e, "_gan_chi_so", lambda ds, d: None)
    monkeypatch.setattr(e, "_chon_loc", lambda ds, d: (ds[:max(1, e.config.top_n)], []))
    return da_cat


def test_top_n_5_ma_moi_co_1_ung_vien_thi_PHAI_quet_tiep(tmp_path, monkeypatch):
    """Lỗi gốc: `_co_ung_vien_dat` trả True ngay ở ứng viên đầu tiên."""
    e = _eng(tmp_path, quet_tang_dan=True, quet_tang_dan_tu_gio=1.0,
             quet_tang_dan_buoc_gio=3.0, quet_da_toc_do=False, top_n=5)
    da_cat = _dung_scan_nhieu(e, monkeypatch, 12 * 3600, so_ung_vien_moi_khuc=1)
    p = tmp_path / "phim.mp4"
    p.write_bytes(b"x")
    kq = e.scan_media(str(p), luu_lich_su=False)
    # 3 khúc mỗi đoạn -> hết đoạn 1 mới có 3 clip khác nhau, chưa đủ 5 nên phải
    # sang đoạn 2 (mốc khúc 10800/14400/18000) rồi mới đủ 6 clip và dừng.
    assert max(da_cat) >= 3 * 3600, "chưa đủ 5 suất thì không được dừng ở đoạn 1"
    assert kq.status == "ok"


def test_top_n_5_du_5_clip_khac_nhau_thi_duoc_dung(tmp_path, monkeypatch):
    """Đủ rồi thì vẫn phải dừng — không được vứt bỏ khoản tiết kiệm đã đo."""
    e = _eng(tmp_path, quet_tang_dan=True, quet_tang_dan_tu_gio=1.0,
             quet_tang_dan_buoc_gio=3.0, quet_da_toc_do=False, top_n=5)
    da_cat = _dung_scan_nhieu(e, monkeypatch, 35 * 3600, so_ung_vien_moi_khuc=2)
    p = tmp_path / "phim.mp4"
    p.write_bytes(b"x")
    e.scan_media(str(p), luu_lich_su=False)
    assert max(da_cat) < 3 * 3600, "3 khúc × 2 clip = 6 ≥ 5 nên phải dừng ngay đoạn đầu"


def test_nam_doan_cua_CUNG_MOT_clip_khong_lap_day_duoc_5_suat(tmp_path, monkeypatch):
    """Chốt chặn tinh tế: `uu_tien_clip_khac_nhau` nên phải đếm CLIP, không đếm đoạn.

    Đếm gộp thì 6 đoạn của cùng một clip trông như đã đủ 5 suất, trong khi
    `_chon_loc` chỉ điền được đúng một suất từ chúng.
    """
    e = _eng(tmp_path, quet_tang_dan=True, quet_tang_dan_tu_gio=1.0,
             quet_tang_dan_buoc_gio=3.0, quet_da_toc_do=False, top_n=5,
             uu_tien_clip_khac_nhau=True)
    da_cat = _dung_scan_nhieu(e, monkeypatch, 12 * 3600, so_ung_vien_moi_khuc=3,
                              clip_theo_khuc=False)
    p = tmp_path / "phim.mp4"
    p.write_bytes(b"x")
    e.scan_media(str(p), luu_lich_su=False)
    assert max(da_cat) >= 6 * 3600, "toàn một clip thì không bao giờ đủ 5 clip khác nhau"


def test_tat_uu_tien_clip_khac_nhau_thi_dem_theo_doan(tmp_path, monkeypatch):
    e = _eng(tmp_path, quet_tang_dan=True, quet_tang_dan_tu_gio=1.0,
             quet_tang_dan_buoc_gio=3.0, quet_da_toc_do=False, top_n=5,
             uu_tien_clip_khac_nhau=False)
    da_cat = _dung_scan_nhieu(e, monkeypatch, 12 * 3600, so_ung_vien_moi_khuc=3,
                              clip_theo_khuc=False)
    p = tmp_path / "phim.mp4"
    p.write_bytes(b"x")
    e.scan_media(str(p), luu_lich_su=False)
    assert max(da_cat) < 3 * 3600, "9 đoạn ≥ 5 suất nên dừng được"


def test_chua_du_top_n_thi_phai_TAI_NOT_phan_con_lai(tmp_path, monkeypatch):
    """Nửa còn lại của cùng một lỗi: không tải nốt thì có quét tiếp cũng vô nghĩa."""
    from engine import ScanResult

    e = _eng(tmp_path, tai_mot_phan=True, quet_tang_dan_tu_gio=10.0,
             quet_tang_dan_buoc_gio=3.0, top_n=5)
    monkeypatch.setattr(e, "require", lambda **k: None)
    monkeypatch.setattr(e, "youtube_info", lambda url: {
        "id": "abc", "title": "v", "duration": 66 * 3600, "channel": "",
        "channel_id": "", "channel_url": "", "upload_date": ""})
    lan_tai = []

    def tai(url, vid, progress=None, gioi_han_giay=None):
        lan_tai.append(gioi_han_giay)
        return str(tmp_path / "f.mp4")

    monkeypatch.setattr(e, "download_audio", tai)

    def quet(path, **k):
        r = ScanResult(source_name="v", duration_s=3 * 3600, pham_vi_quet_s=3 * 3600)
        r.matches = [Match(clip="x.opus", start_s=1, end_s=2, matched_s=1,
                           clip_offset_s=0, hashes=9999, confidence="chac")]
        return r

    monkeypatch.setattr(e, "scan_media", quet)
    e.scan_youtube("https://youtu.be/abc", luu_lich_su=False)
    assert lan_tai == [3 * 3600, None], "mới 1/5 đoạn thì phải tải nốt để tìm tiếp"


# =====================================================================
#  «Quét tăng dần» là CÔNG TẮC TỔNG của cả phần tải
# =====================================================================

def test_tat_quet_tang_dan_thi_TAI_TRON_dung_nhu_giao_dien_hua(tmp_path):
    """app.py bảo "muốn quét trọn thì tắt «Quét tăng dần»". Lời hứa đó phải đúng.

    Trước đây `_gioi_han_tai` chỉ đọc `tai_mot_phan`, mà trường này không có ô nào
    trên giao diện — nên bỏ tick vẫn chỉ tải 3 tiếng đầu của video 66 tiếng, và
    không có dấu hiệu nào cho thấy điều đó.
    """
    e = _eng(tmp_path, quet_tang_dan=False, tai_mot_phan=True,
             quet_tang_dan_tu_gio=10.0, quet_tang_dan_buoc_gio=3.0)
    assert e._gioi_han_tai(66 * 3600) is None


def test_quet_tang_dan_bat_ma_tat_tai_mot_phan_van_hop_le(tmp_path):
    """Chiều ngược lại phải giữ được: xử lý tăng dần nhưng tải trọn."""
    e = _eng(tmp_path, quet_tang_dan=True, tai_mot_phan=False,
             quet_tang_dan_tu_gio=10.0, quet_tang_dan_buoc_gio=3.0)
    assert e._gioi_han_tai(66 * 3600) is None
    assert len(e._doan_quet_tang_dan(66 * 3600)) > 1, "vẫn phải chia đoạn để quét"
