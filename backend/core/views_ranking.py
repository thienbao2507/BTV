from django.shortcuts import render
from django.db.models import Avg
from .models import CuocThi, VongThi, BaiThi, ThiSinh, PhieuChamDiem
from django.db.models import Q
from django.core.cache import cache
def _score_type(bt) -> str:
    v = getattr(bt, "phuongThucCham", None)
    if v is None:
        return "POINTS"
    s = str(v).strip().upper()
    if s in {"TIME", "2"}:
        return "TIME"
    return "POINTS"

def ranking_view(request):
    # Fallback server-side: nếu tắt, render trang thông báo
    if not cache.get("ranking_enabled", True):
        return render(request, "ranking/disabled.html", {
            "title": "Xếp hạng — đang tắt",
        })

    ct_id = request.GET.get("ct")
    # ===== Lọc theo tên & đơn vị (dùng nút trượt) =====
    ten = (request.GET.get("ten") or "").strip()
    don_vi = (request.GET.get("don_vi") or "").strip()
    use_filter = request.GET.get("use_filter") == "1"
    # ten / don_vi luôn giữ để hiển thị lại trong ô input
    # chỉ khi use_filter = True mới áp vào query
    # ================================================

    # ================================

    cuoc_this = CuocThi.objects.filter(trangThai=True).order_by("-id")

    if not cuoc_this.exists():
        return render(request, "ranking/index.html", {
            "cuoc_this": cuoc_this, "selected_ct": None,
            "groups": [], "rows": [], "total_max": 0,
            "title": "Xếp hạng theo Cuộc thi",
            "filter_name": ten,
            "filter_unit": don_vi,
            "is_filtered": False,
        })


    selected_ct = cuoc_this.filter(id=ct_id).first() if ct_id else None
    if selected_ct is None:
        selected_ct = cuoc_this.first()

    # 2) Lấy vòng + bài
    vongs = list(VongThi.objects.filter(cuocThi=selected_ct).order_by("id"))
    bai_list = (
        BaiThi.objects.filter(vongThi__in=vongs)
        .select_related("vongThi").prefetch_related("time_rules")
        .order_by("vongThi_id", "id")
    )

    # Gom theo vòng
    groups = []
    group_index_by_vong = {}
    running_test_index = 0
    total_max = 0

    for vt in vongs:
        tests = []
        g_max = 0
        for b in [x for x in bai_list if x.vongThi_id == vt.id]:
            if _score_type(b) == "TIME":
                rules = list(getattr(b, "time_rules", []).all()) if hasattr(b, "time_rules") else []
                b_max = max([r.score for r in rules], default=0)
            else:
                b_max = b.cachChamDiem
            tests.append({
                "id": b.id,
                "code": b.ma,
                "title": b.tenBaiThi,
                "max": b_max,
                "col_index": running_test_index,
            })
            running_test_index += 1
            g_max += (b_max or 0)

        if tests:
            group_index_by_vong[vt.id] = len(groups)
            groups.append({
                "vong_id": vt.id,
                "vong_name": vt.tenVongThi,
                "tests": tests,
                "max": g_max,
            })
            total_max += g_max

    # === (MỚI) Tính tổng thời gian SAU khi đã có toàn bộ groups/bai_list ===
    time_test_ids = [b.id for b in bai_list if _score_type(b) == "TIME"]

    time_sum_map = {}
    if time_test_ids:
        time_qs = (
            PhieuChamDiem.objects
            .filter(cuocThi=selected_ct, baiThi_id__in=time_test_ids)
            .values("thiSinh__maNV", "baiThi_id")
            .annotate(t_avg=Avg("thoiGian"))   # đổi tên field nếu DB bạn khác
        )
        for r in time_qs:
            if r["t_avg"] is None:
                continue
            key = r["thiSinh__maNV"]
            time_sum_map[key] = time_sum_map.get(key, 0.0) + float(r["t_avg"])

    # 3) Map điểm
    all_test_ids = [t["id"] for g in groups for t in g["tests"]]
    score_qs = list(
        PhieuChamDiem.objects
        .filter(cuocThi=selected_ct, baiThi_id__in=all_test_ids)
        .values("thiSinh__maNV", "baiThi_id")
        .annotate(avg=Avg("diem"))
    )
    score_map = {(r["thiSinh__maNV"], r["baiThi_id"]): float(r["avg"]) for r in score_qs}

    # Đếm số bài thi đã được chấm của từng thí sinh
    # (mỗi cặp thí sinh–bài thi tính 1 lần)
    done_count_map = {}
    for r in score_qs:
        key = r["thiSinh__maNV"]
        done_count_map[key] = done_count_map.get(key, 0) + 1

    total_tests = len(all_test_ids)

    # 4) Thí sinh
    ts_m2m = ThiSinh.objects.filter(cuocThi=selected_ct)
    ts_scored = ThiSinh.objects.filter(phieuchamdiem__cuocThi=selected_ct)
    ts_qs_base = (
        ThiSinh.objects
        .filter(Q(pk__in=ts_m2m.values("pk")) | Q(pk__in=ts_scored.values("pk")))
        .distinct().order_by("maNV")
    )

    # 4.1. Tạo LIST đầy đủ cho tất cả thí sinh (không lọc)
    rows_all = []
    for ts in ts_qs_base:
        groups_view = []
        total_sum = 0.0
        for g in groups:
            g_scores = []
            g_sum = 0.0
            for t in g["tests"]:
                val = score_map.get((ts.maNV, t["id"]), 0.0)
                g_scores.append(val)
                g_sum += val
            groups_view.append({"scores": g_scores, "total": g_sum})
            total_sum += g_sum

        done = done_count_map.get(ts.maNV, 0)

        rows_all.append({
            "maNV": ts.maNV,
            "hoTen": ts.hoTen,
            "donVi": ts.donVi or "",
            "groups_view": groups_view,
            "total": total_sum,
            "total_time": time_sum_map.get(ts.maNV),  # None nếu không có TIME
            "done": done,
            "total_tests": total_tests,
        })

    # Sort: điểm ↓, tổng thời gian ↑ (nếu có), mã NV ↑
    def _row_sort_key(r):
        total = r["total"]
        t = r.get("total_time")
        t_key = t if t is not None else float("inf")
        return (-total, t_key, r["maNV"])

    rows_all.sort(key=_row_sort_key)

    # 4.2. Gán RANK GLOBAL cho toàn bộ list
    for idx, r in enumerate(rows_all, start=1):
        r["rank"] = idx

    # 4.3. Áp điều kiện lọc TRÊN LIST (không thay đổi rank)
    ten_filter = ten if use_filter else ""
    don_vi_filter = don_vi if use_filter else ""

    if use_filter and (ten_filter or don_vi_filter):
        lf = ten_filter.lower()
        lu = don_vi_filter.lower()

        def _match(row):
            ok = True
            if lf:
                ok = ok and (lf in (row["hoTen"] or "").lower())
            if lu:
                ok = ok and (lu in (row["donVi"] or "").lower())
            return ok

        rows = [r for r in rows_all if _match(r)]
        is_filtered = True
    else:
        rows = rows_all
        is_filtered = False

    return render(request, "ranking/index.html", {
        "cuoc_this": cuoc_this,
        "selected_ct": selected_ct,
        "groups": groups,
        "rows": rows,
        "total_max": total_max,
        "title": f"Xếp hạng — {selected_ct.ma} · {selected_ct.tenCuocThi}",
        "filter_name": ten,
        "filter_unit": don_vi,
        "is_filtered": is_filtered,
    })



