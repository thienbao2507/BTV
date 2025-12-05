from django.shortcuts import render
from django.db.models import Avg, Count, Q
from core.models import CuocThi, VongThi, BaiThi, ThiSinh, PhieuChamDiem
from core.decorators import judge_required
from core.views_ranking import _score_type
# --- thêm import ở đầu file
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.core.cache import cache
import json

RANKING_STATE_KEY = "ranking_enabled"  # True = mở, False = tắt

@require_http_methods(["GET", "POST"])
def ranking_state(request):
    """
    GET  -> {"enabled": true|false}
    POST -> body JSON {"enabled": true|false} -> lưu và trả lại trạng thái
    """
    if request.method == "GET":
        enabled = cache.get(RANKING_STATE_KEY, True)
        return JsonResponse({"enabled": bool(enabled)})

    try:
        data = json.loads(request.body or "{}")
    except Exception:
        data = {}
    enabled = bool(data.get("enabled", True))
    cache.set(RANKING_STATE_KEY, enabled, None)
    return JsonResponse({"enabled": enabled})

@judge_required
def management_view(request):
    # A — Lấy danh sách cuộc thi đang hoạt động
    ct_id = request.GET.get("ct")
    active_contests = CuocThi.objects.filter(trangThai=True).order_by("-id")

    if ct_id:
        ct = active_contests.filter(id=ct_id).first()
    else:
        ct = active_contests.first()


    if not ct:
        return render(request, "management/index.html", {"no_contest": True})

    # E — Tổng số thí sinh
    total_thi_sinh = ThiSinh.objects.filter(cuocThi=ct).count()

    # C — Xếp hạng (giống ranking_view)
    vt_ids = VongThi.objects.filter(cuocThi=ct).values_list("id", flat=True)
    bai_list = list(
        BaiThi.objects.filter(vongThi_id__in=vt_ids)
        .select_related("vongThi")
        .prefetch_related("time_rules")
        .order_by("vongThi_id", "id")
    )

    columns, total_max = [], 0
    for b in bai_list:
        if _score_type(b) == "TIME":
            rules = list(b.time_rules.all()) if hasattr(b, "time_rules") else []
            b_max = max((r.score for r in rules), default=0)
        else:
            b_max = b.cachChamDiem
        columns.append({"id": b.id, "code": b.ma, "title": f"{b.vongThi.tenVongThi} – {b.tenBaiThi}", "max": b_max})
        total_max += b_max

    scores_qs = (
        PhieuChamDiem.objects.filter(cuocThi=ct, baiThi_id__in=[b["id"] for b in columns])
        .values("thiSinh__maNV", "baiThi_id")
        .annotate(avg=Avg("diem"))
    )
    score_map = {(r["thiSinh__maNV"], r["baiThi_id"]): float(r["avg"]) for r in scores_qs}

    ts_qs = (
        ThiSinh.objects.filter(cuocThi=ct)
        .order_by("maNV")
        .distinct()
    )

    rows = []
    for ts in ts_qs:
        row_scores, total = [], 0.0
        for col in columns:
            val = score_map.get((ts.maNV, col["id"]), 0.0)
            row_scores.append(val)
            total += val
        rows.append({"maNV": ts.maNV, "hoTen": ts.hoTen, "donVi": ts.donVi or "", "scores": row_scores, "total": total})

    rows.sort(key=lambda r: (-r["total"], r["maNV"]))

    # G — Điểm trung bình (bỏ người không thi)
    valid_rows = [r for r in rows if r["total"] > 0]
    avg_score = sum(r["total"] for r in valid_rows) / len(valid_rows) if valid_rows else 0

    # B — Phân bố điểm
    score_ranges = {"100-90": 0, "89-60": 0, "59-0": 0}
    for r in valid_rows:
        avg = r["total"] / total_max * 100 if total_max > 0 else 0
        if avg >= 90:
            score_ranges["100-90"] += 1
        elif avg >= 60:
            score_ranges["89-60"] += 1
        else:
            score_ranges["59-0"] += 1

    range_total = sum(score_ranges.values()) or 1
    sr_pcts = {
        "high": round(score_ranges["100-90"] * 100 / range_total, 2),
        "mid":  round(score_ranges["89-60"] * 100 / range_total, 2),
        "low":  round(score_ranges["59-0"]  * 100 / range_total, 2),
    }
    sr_counts = {
        "high": score_ranges["100-90"],
        "mid":  score_ranges["89-60"],
        "low":  score_ranges["59-0"],
    }


    return render(request, "management/index.html", {
        "contest": ct,
        "columns": columns,
        "rows": rows,
        "total_max": total_max,
        "total_thi_sinh": total_thi_sinh,
        "avg_score": avg_score,
        "score_ranges": score_ranges,
        "sr_pcts": sr_pcts,
        "active_contests": active_contests,
    })

@judge_required
@require_http_methods(["GET", "POST"])
def ranking_state(request):
    """
    GET  -> {"enabled": true|false}
    POST -> body JSON {"enabled": true|false} -> lưu và trả lại trạng thái
    """
    if request.method == "GET":
        enabled = cache.get(RANKING_STATE_KEY, True)
        return JsonResponse({"enabled": bool(enabled)})

    try:
        data = json.loads(request.body or "{}")
    except Exception:
        data = {}
    enabled = bool(data.get("enabled", True))
    cache.set(RANKING_STATE_KEY, enabled, None)
    return JsonResponse({"enabled": enabled})
