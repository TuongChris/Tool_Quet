# -*- coding: utf-8 -*-
"""Adapter quan sát audfprint mà không sửa source vendored.

Wrapper chỉ thêm JSON event trước/sau ``wavfile2hashes``. Thuật toán Analyzer,
HashTable, tham số CLI và format ``.pklz`` vẫn do audfprint vendored thực hiện.
"""

from __future__ import annotations

import gzip
import json
import os
import pickle
import shutil
import sys
import tempfile
import time


PREFIX = "TIMCLIP_FINGERPRINT_EVENT "

# Mỗi worker chờ tối đa bấy nhiêu giây sau khi tất cả worker đã báo xong. Chỉ là
# lưới an toàn cuối cùng để job không treo vĩnh viễn; đường chạy bình thường không
# bao giờ chạm tới.
CHO_WORKER_S = 1800.0


def _emit(event: str, **payload) -> None:
    """Ghi một dòng event bằng ĐÚNG MỘT syscall.

    Tới 8 tiến trình con cùng ghi vào một pipe stdout. ``print()`` có thể tách
    thành nhiều lần ghi, hai dòng lồng vào nhau và engine mất event (đã quan sát:
    7/8 event thay vì 8/8). Một ``os.write`` cho dòng dưới 4 KB là nguyên tử trên
    cả Windows lẫn POSIX.
    """
    dong = PREFIX + json.dumps({"event": event, **payload}, ensure_ascii=False) + "\n"
    du_lieu = dong.encode("utf-8", errors="replace")
    try:
        sys.stdout.flush()          # giữ đúng thứ tự với output của audfprint
        os.write(sys.stdout.fileno(), du_lieu)
    except (OSError, ValueError):
        # stdout đã đóng (job bị hủy) — mất một dòng log không được làm chết worker.
        pass


def instrumented_make_ht_from_list(
    analyzer,
    filelist,
    hashbits,
    depth,
    maxtime,
    pipe=None,
):
    """Bản bọc tương đương ``make_ht_from_list`` với event per-file."""
    import hash_table

    ht = hash_table.HashTable(hashbits=hashbits, depth=depth, maxtime=maxtime)
    for filename in filelist:
        started = time.monotonic()
        _emit(
            "clip_started",
            file=filename,
            phase="fingerprinting",
            process_pid=os.getpid(),
        )
        try:
            hashes = analyzer.wavfile2hashes(filename)
            ht.store(filename, hashes)
        except BaseException as exc:
            _emit(
                "clip_finished",
                file=filename,
                status="failed",
                category=type(exc).__name__,
                message=str(exc)[:500],
                elapsed_seconds=time.monotonic() - started,
                process_pid=os.getpid(),
            )
            raise
        _emit(
            "clip_finished",
            file=filename,
            status="success" if len(hashes) else "failed",
            category="" if len(hashes) else "zero_hashes",
            message="" if len(hashes) else "Không tạo được hash từ audio.",
            hash_count=len(hashes),
            elapsed_seconds=time.monotonic() - started,
            process_pid=os.getpid(),
        )
    if pipe:
        pipe.send(ht)
    else:
        return ht


_DA_CAI_THEO_DOI_GIAI_MA = False


def cai_dat_theo_doi_giai_ma() -> None:
    """Phát phase ``decoding`` từ đúng nơi FFmpeg thực sự được gọi.

    Trước đây phase này chỉ được suy ra bằng cách *bắt gặp* tiến trình ffmpeg lúc
    lấy mẫu cây process. Với clip ngắn, ffmpeg chỉ sống vài chục mili giây nên bắt
    được hay không là may rủi — giao diện lúc hiện lúc không, và test thì flaky.

    ``audfprint_analyze.wavfile2peaks`` gọi ``audio_read.audio_read()``; bọc đúng
    hàm đó cho tín hiệu tất định. Không sửa code vendored, chỉ thay tham chiếu.

    Phải gọi trong **mỗi** tiến trình con vì Windows dùng spawn: bản vá ở tiến trình
    cha không đi theo sang con.
    """
    global _DA_CAI_THEO_DOI_GIAI_MA
    if _DA_CAI_THEO_DOI_GIAI_MA:
        return
    try:
        import audio_read
    except ImportError:
        return          # không có module thì giữ nguyên hành vi cũ, không làm chết job
    goc = audio_read.audio_read

    def audio_read_co_su_kien(*args, **kwargs):
        ten = str(args[0] if args else kwargs.get("filename") or "")
        _emit("clip_phase", file=ten, phase="decoding", process_pid=os.getpid())
        try:
            return goc(*args, **kwargs)
        finally:
            _emit("clip_phase", file=ten, phase="fingerprinting", process_pid=os.getpid())

    audio_read.audio_read = audio_read_co_su_kien
    _DA_CAI_THEO_DOI_GIAI_MA = True


def _worker_ghi_hash_table(
    analyzer,
    filelist,
    hashbits,
    depth,
    maxtime,
    pipe,
    duong_dan,
) -> None:
    """Chạy trong tiến trình con: tính hash table rồi GHI RA FILE, không gửi qua pipe.

    Pipe chỉ mang một dict trạng thái vài chục byte.
    """
    cai_dat_theo_doi_giai_ma()      # spawn: bản vá của cha không đi theo sang con
    try:
        ht = instrumented_make_ht_from_list(
            analyzer, filelist, hashbits, depth, maxtime
        )
        with gzip.open(duong_dan, "wb", compresslevel=1) as fh:
            pickle.dump(ht, fh, protocol=pickle.HIGHEST_PROTOCOL)
        pipe.send({"ok": True, "so_file": len(filelist)})
    except BaseException as exc:  # noqa: BLE001 - phải báo về cha rồi mới chết
        try:
            pipe.send({
                "ok": False,
                "loi": f"{type(exc).__name__}: {str(exc)[:500]}",
            })
        except (BrokenPipeError, OSError):
            pass
        raise
    finally:
        try:
            pipe.close()
        except OSError:
            pass


def instrumented_multiproc_add(analyzer, hash_tab, filename_iter, report, ncores):
    """Bản thay thế ``multiproc_add`` — cùng thuật toán, không kẹt vĩnh viễn.

    Bản vendored (``audfprint.py:199``) có ba khiếm khuyết cộng lại thành treo cứng:

    1. Mỗi worker gửi trả nguyên một ``HashTable`` qua ``multiprocessing.Pipe``.
       Bảng luôn được cấp phát đủ ``2**hashbits x depth`` ô ``uint32`` bất kể xử lý
       bao nhiêu file — với tham số mặc định là **419 MB mỗi worker**, tức khoảng
       3,3 GB đi qua named pipe khi ``--ncores 8``. Đây là phần không ổn định.
    2. Tiến trình cha **giữ nguyên mọi đầu ghi** ``tx[ix]``. Worker chết không tạo
       EOF nên ``recv()`` chờ mãi mãi.
    3. Không có timeout ở bất kỳ đâu.

    Đã tái hiện treo trên chính audfprint gốc (không qua wrapper), 3/6 lần chạy.

    Bản này giữ nguyên cách chia file, tham số HashTable và ``merge()``; chỉ đổi
    đường vận chuyển: worker ghi bảng ra file tạm (gzip — bảng gần như toàn số 0 nên
    nén cực tốt), pipe chỉ mang dict trạng thái nhỏ.
    """
    import multiprocessing

    filelists = [[] for _ in range(ncores)]
    for ix, filename in enumerate(filename_iter):
        filelists[ix % ncores].append(filename)

    thu_muc = tempfile.mkdtemp(prefix="timclip_ht_")
    rx: list = []
    pr: list = []
    duong_dan: list = []
    try:
        for ix in range(ncores):
            doc, ghi = multiprocessing.Pipe(False)
            path = os.path.join(thu_muc, f"hash_table_{ix}.pklz")
            process = multiprocessing.Process(
                target=_worker_ghi_hash_table,
                args=(
                    analyzer,
                    filelists[ix],
                    hash_tab.hashbits,
                    hash_tab.depth,
                    (1 << hash_tab.maxtimebits),
                    ghi,
                    path,
                ),
            )
            process.start()
            # Cha không được giữ đầu ghi: worker chết phải thành EOF, không phải treo.
            ghi.close()
            rx.append(doc)
            pr.append(process)
            duong_dan.append(path)

        for core in range(ncores):
            try:
                if not rx[core].poll(CHO_WORKER_S):
                    raise RuntimeError(
                        f"Worker vân tay {core} không phản hồi sau "
                        f"{CHO_WORKER_S:.0f} giây."
                    )
                ket_qua = rx[core].recv()
            except EOFError as exc:
                pr[core].join(timeout=30)
                raise RuntimeError(
                    f"Worker vân tay {core} kết thúc bất thường "
                    f"(exit code {pr[core].exitcode}) mà không trả kết quả."
                ) from exc
            finally:
                rx[core].close()

            if not ket_qua.get("ok"):
                raise RuntimeError(
                    f"Worker vân tay {core} lỗi: {ket_qua.get('loi') or 'không rõ'}"
                )

            with gzip.open(duong_dan[core], "rb") as fh:
                hash_tabx = pickle.load(fh)
            # Giải phóng sớm để đỉnh dung lượng đĩa không cộng dồn cả 8 worker.
            try:
                os.remove(duong_dan[core])
            except OSError:
                pass

            report([
                "hash_table " + str(core) + " has "
                + str(len(hash_tabx.names))
                + " files " + str(sum(hash_tabx.counts)) + " hashes"
            ])
            hash_tab.merge(hash_tabx)
            del hash_tabx
            pr[core].join(timeout=60)
    finally:
        for process in pr:
            if process.is_alive():
                process.terminate()
        shutil.rmtree(thu_muc, ignore_errors=True)


def _install_single_core_instrumentation(audfprint_analyze) -> None:
    original = audfprint_analyze.Analyzer.ingest

    def ingest(self, hashtable, filename):
        started = time.monotonic()
        _emit(
            "clip_started",
            file=filename,
            phase="fingerprinting",
            process_pid=os.getpid(),
        )
        try:
            duration, hash_count = original(self, hashtable, filename)
        except BaseException as exc:
            _emit(
                "clip_finished",
                file=filename,
                status="failed",
                category=type(exc).__name__,
                message=str(exc)[:500],
                elapsed_seconds=time.monotonic() - started,
                process_pid=os.getpid(),
            )
            raise
        _emit(
            "clip_finished",
            file=filename,
            status="success" if hash_count else "failed",
            category="" if hash_count else "zero_hashes",
            message="" if hash_count else "Không tạo được hash từ audio.",
            hash_count=hash_count,
            duration_seconds=duration,
            elapsed_seconds=time.monotonic() - started,
            process_pid=os.getpid(),
        )
        return duration, hash_count

    audfprint_analyze.Analyzer.ingest = ingest


def cai_dat_instrumentation(audfprint, audfprint_analyze) -> None:
    """Gắn toàn bộ bản vá vào audfprint vendored. Tách riêng để test được.

    Quên bất kỳ dòng nào ở đây đều làm mất một tính chất đã có regression test:
    thiếu ``make_ht_from_list`` là mất event khi ``ncores > 1``; thiếu
    ``multiproc_add`` là quay lại nguy cơ treo cứng; thiếu ``Analyzer.ingest``
    là mất event ở nhánh một nhân.
    """
    audfprint.make_ht_from_list = instrumented_make_ht_from_list
    audfprint.multiproc_add = instrumented_multiproc_add
    _install_single_core_instrumentation(audfprint_analyze)
    cai_dat_theo_doi_giai_ma()


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv if argv is None else argv)
    if len(argv) < 3:
        print("Dùng: audfprint_progress_runner.py <audfprint.py> <command> ...", file=sys.stderr)
        return 2
    vendor_script = os.path.abspath(argv[1])
    vendor_dir = os.path.dirname(vendor_script)
    if vendor_dir not in sys.path:
        sys.path.insert(0, vendor_dir)

    import audfprint
    import audfprint_analyze

    cai_dat_instrumentation(audfprint, audfprint_analyze)
    audfprint.main([vendor_script, *argv[2:]])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
