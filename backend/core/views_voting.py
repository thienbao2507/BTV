from django.shortcuts import render
from django.views.decorators.http import require_POST
from django.http import JsonResponse, HttpResponseBadRequest
from django.db import transaction
from django.db.models import Count, Q

from core.models import ThiSinh, CuocThi, ThiSinhVoting, VotingRecord

ALLOWED_VOTER_DOMAINS = {"fpt.com", "fpt.net", "vienthongtin.com"}


def _login_email(request) -> str:
    email = (
        request.session.get("judge_email")
        or request.session.get("auth_email")
        or ""
    ).strip().lower()
    return email


def _is_allowed_voter_email(email: str) -> bool:
    if "@" not in email:
        return False
    return email.split("@", 1)[1].lower() in ALLOWED_VOTER_DOMAINS


def voting_home_view(request):
    email = _login_email(request)

    # Chọn cuộc thi
    ct_id = request.GET.get("ct")
    if ct_id:
        try:
            ct = CuocThi.objects.get(pk=int(ct_id))
        except Exception:
            ct = None
    else:
        ct = CuocThi.objects.filter(trangThai=True).order_by("id").first()

    base_qs = ThiSinhVoting.objects.select_related("thiSinh", "cuocThi")

    if ct:
        candidates_qs = (
            base_qs
            .filter(cuocThi=ct)
            .annotate(
                total_votes=Count(
                    "thiSinh__votingrecord",
                    filter=Q(thiSinh__votingrecord__cuocThi=ct),
                )
            )
            .order_by("thiSinh__maNV")
        )
    else:
        candidates_qs = (
            base_qs
            .annotate(total_votes=Count("thiSinh__votingrecord"))
            .order_by("thiSinh__maNV")
        )

    existing = VotingRecord.objects.filter(voter_email=email).first() if email else None

    candidates = []
    for cv in candidates_qs:
        ts = cv.thiSinh
        votes = int(getattr(cv, "total_votes", 0) or 0)
        candidates.append({
            "maNV": ts.maNV,
            "hoTen": ts.hoTen,
            "donVi": ts.donVi or "",
            "image_url": ts.display_image_url,
            "ct_ma": cv.cuocThi.ma,
            "ct_id": cv.cuocThi.id,
            "total_votes": votes,   # vẫn giữ để tính %, nhưng template sẽ không hiển thị "x phiếu"
        })

    total_votes_all = sum(c["total_votes"] for c in candidates)
    for c in candidates:
        v = c["total_votes"]
        c["vote_percent"] = (v * 100.0 / total_votes_all) if total_votes_all > 0 else 0.0

    ctx = {
        "login_email": email or "",
        # dùng cùng logic với API submit để khỏi lệ thuộc session can_vote
        "can_vote": _is_allowed_voter_email(email) if email else False,
        "contest": ct,
        "candidates": candidates,
        "total_votes_all": total_votes_all,
        "already_voted": bool(existing),
        "voted_target": {
            "maNV": existing.thiSinh_ma,
            "hoTen": existing.thiSinh_ten
        } if existing else None,
    }
    return render(request, "voting/index.html", ctx)


@require_POST
def voting_submit_api(request):
    email = _login_email(request)
    if not email:
        return JsonResponse({"ok": False, "error": "NOT_LOGGED_IN"}, status=401)

    if not _is_allowed_voter_email(email):
        return JsonResponse({"ok": False, "error": "EMAIL_DOMAIN_NOT_ALLOWED"}, status=403)

    import json
    try:
        data = json.loads(request.body or "{}")
    except Exception:
        return HttpResponseBadRequest("BAD_JSON")

    maNV = (data.get("maNV") or "").strip()
    if not maNV:
        return HttpResponseBadRequest("MISSING_maNV")

    if VotingRecord.objects.filter(voter_email=email).exists():
        return JsonResponse({"ok": False, "error": "ALREADY_VOTED"}, status=409)

    ts = ThiSinh.objects.filter(pk=maNV).first()
    if not ts:
        return JsonResponse({"ok": False, "error": "INVALID_CANDIDATE"}, status=404)

    ct = None
    ct_id = data.get("ct_id")
    if ct_id:
        try:
            ct = CuocThi.objects.get(pk=int(ct_id))
        except Exception:
            ct = None

    if ct and not ThiSinhVoting.objects.filter(thiSinh=ts, cuocThi=ct).exists():
        return JsonResponse({"ok": False, "error": "CANDIDATE_NOT_IN_VOTING_LIST"}, status=400)

    with transaction.atomic():
        rec = VotingRecord.objects.create(
            voter_email=email,
            cuocThi=ct,
            thiSinh=ts,
            thiSinh_ma=ts.maNV,
            thiSinh_ten=ts.hoTen,
            count=1,
        )

    # Trả thêm tổng phiếu & phiếu của candidate để JS cập nhật %
    base = VotingRecord.objects.all()
    if ct:
        base = base.filter(cuocThi=ct)

    total_votes_all = base.count()
    candidate_votes = base.filter(thiSinh=ts).count()
    candidate_percent = (candidate_votes * 100.0 / total_votes_all) if total_votes_all > 0 else 0.0

    return JsonResponse({
        "ok": True,
        "maNV": rec.thiSinh_ma,
        "hoTen": rec.thiSinh_ten,
        "total_votes_all": total_votes_all,
        "candidate_votes": candidate_votes,
        "candidate_percent": candidate_percent,
    })


@require_POST
def voting_revoke_api(request):
    email = _login_email(request)
    if not email:
        return JsonResponse({"ok": False, "error": "NOT_LOGGED_IN"}, status=401)

    # Lưu lại target trước khi xoá để trả về cho JS
    rec = VotingRecord.objects.filter(voter_email=email).select_related("cuocThi", "thiSinh").first()
    revoked_ma = rec.thiSinh_ma if rec else None
    revoked_ct = rec.cuocThi if rec else None
    revoked_ts = rec.thiSinh if rec else None

    deleted_count, _ = VotingRecord.objects.filter(voter_email=email).delete()

    base = VotingRecord.objects.all()
    if revoked_ct:
        base = base.filter(cuocThi=revoked_ct)

    total_votes_all = base.count()
    candidate_votes = base.filter(thiSinh=revoked_ts).count() if revoked_ts else None
    candidate_percent = (candidate_votes * 100.0 / total_votes_all) if (candidate_votes is not None and total_votes_all > 0) else 0.0

    return JsonResponse({
        "ok": True,
        "deleted": deleted_count,
        "revoked_maNV": revoked_ma,
        "total_votes_all": total_votes_all,
        "candidate_votes": candidate_votes,
        "candidate_percent": candidate_percent,
    })
