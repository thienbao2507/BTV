# core/views_bgd.py
from io import BytesIO
import zipfile
import json

from django.http import HttpResponse, Http404, JsonResponse, HttpResponseBadRequest
from django.shortcuts import render, redirect
from django.urls import reverse
from django.conf import settings
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.db.models import Sum, Q, Avg, Count

from .models import BanGiamDoc, CuocThi, GiamKhao, ThiSinh, BGDScore, VongThi, PhieuChamDiem, BaiThi
from .views_score import score_view  # tái dùng view chấm hiện có


def _auto_login_bgd_as_judge(request, bgd):
    """
    Dựa vào mã & tên BGD để tìm bản ghi GiamKhao tương ứng,
    rồi ghi thẳng thông tin đăng nhập vào session giống login_view.
    Điều kiện khớp:
      - ưu tiên: maNV == maBGD và hoTen (không phân biệt hoa/thường) == ten
      - nếu không khớp tên, fallback: chỉ cần maNV == maBGD
    """
    # Xoá thông tin login cũ (nếu có)
    request.session.pop("judge_pk", None)
    request.session.pop("judge_email", None)

    # Ưu tiên khớp cả mã + tên
    judge = GiamKhao.objects.filter(
        maNV=bgd.maBGD,
        hoTen__iexact=bgd.ten,
    ).first()

    # fallback: chỉ cần đúng mã
    if not judge:
        judge = GiamKhao.objects.filter(maNV=bgd.maBGD).first()

    if not judge:
        # Không tìm thấy giám khảo tương ứng
        raise Http404(
            "BGD này chưa được khai báo trong danh sách Giám khảo "
            "(không tìm thấy GiamKhao trùng mã/tên)."
        )

    # Ghi session giống login_view
    request.session["judge_pk"] = judge.pk
    request.session["judge_email"] = judge.email or ""
    request.session.modified = True

    return judge




# ===== Helper: tạo QR đơn (chấm điểm / đối kháng) =====
def _make_bgd_single_qr_image(bgd, request, kind: str, ct=None, vt=None):
    """
    Tạo ảnh QR + chữ bên dưới cho 1 BGD.
    kind: "score" (chấm điểm) hoặc "battle" (đối kháng).
    """
    import qrcode
    from PIL import Image, ImageDraw, ImageFont

    if kind == "battle":
        target_url = request.build_absolute_uri(
            reverse("bgd-battle-go", args=[bgd.token])
        )
        suffix = "Battle"
    else:
        # QR chấm điểm: cần kèm id cuộc thi & id vòng thi
        if ct is None or vt is None:
            raise ValueError("Thiếu cuộc thi (ct) hoặc vòng thi (vt) khi tạo QR chấm điểm.")
        target_url = request.build_absolute_uri(
            reverse("bgd-go", args=[ct.id, vt.id, bgd.token])
        )
        suffix = "Score"


    # --- Tạo ảnh QR ---
    qr = qrcode.QRCode(box_size=10, border=4)
    qr.add_data(target_url)
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color="black", back_color="white").convert("RGB")

    W, H = qr_img.size
    padding_y = int(H * 0.25)  # khoảng dành cho chữ phía dưới

    canvas = Image.new("RGB", (W, H + padding_y), "white")
    canvas.paste(qr_img, (0, 0))

    draw = ImageDraw.Draw(canvas)
    label = f"{bgd.maBGD} — {suffix}"

    try:
        font_path = getattr(settings, "BGD_QR_FONT_PATH", None)
        if font_path:
            font = ImageFont.truetype(font_path, size=int(H * 0.12))
        else:
            font = ImageFont.load_default()
    except Exception:
        font = ImageFont.load_default()

    bbox = draw.textbbox((0, 0), label, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]

    text_x = (W - text_w) // 2
    text_y = H + (padding_y - text_h) // 2


    draw.text((text_x, text_y), label, font=font, fill="black")

    return canvas

def _make_bgd_single_qr_image(bgd, request, ct, vt):
    """
    Sinh 1 ảnh PNG nền trắng, ở giữa là 1 QR của vòng thi BGD
    và bên dưới có text tên vòng thi.
    """
    import qrcode
    from qrcode.constants import ERROR_CORRECT_H
    from PIL import Image, ImageDraw, ImageFont

    # URL chấm điểm của BGD cho vòng thi này
    target_url = request.build_absolute_uri(
        reverse("bgd-go", args=[ct.id, vt.id, bgd.token])
    )

    qr = qrcode.QRCode(
        version=None,
        error_correction=ERROR_CORRECT_H,
        box_size=10,
        border=4,
    )
    qr.add_data(target_url)
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color="black", back_color="white").convert("RGB")

    # Chuẩn bị "card" trắng chứa QR + label
    padding = 40
    label_height = 80  # đủ chỗ cho 2 dòng chữ
    qr_w, qr_h = qr_img.size
    card_w = qr_w + padding * 2
    card_h = qr_h + padding * 2 + label_height

    card = Image.new("RGB", (card_w, card_h), "white")
    qr_x = (card_w - qr_w) // 2
    qr_y = padding
    card.paste(qr_img, (qr_x, qr_y))

    draw = ImageDraw.Draw(card)
    try:
        font = ImageFont.truetype("arial.ttf", 24)
    except Exception:
        font = ImageFont.load_default()

    # helper đo text, tương thích nhiều version Pillow
    def measure(text: str):
        # Pillow mới: dùng textbbox
        if hasattr(draw, "textbbox"):
            bbox = draw.textbbox((0, 0), text, font=font)
            return bbox[2] - bbox[0], bbox[3] - bbox[1]
        # fallback: dùng font.getbbox / getsize
        if hasattr(font, "getbbox"):
            bbox = font.getbbox(text)
            return bbox[2] - bbox[0], bbox[3] - bbox[1]
        return font.getsize(text)

    return card

# def _make_bgd_dual_qr_image(bgd, request, ct, vt):
#     """
#     Tạo 1 ảnh chứa 2 QR:
#       - trái: chấm điểm
#       - phải: đối kháng
#     Mỗi QR có label tương ứng phía dưới.
#     """
#     from PIL import Image

#     left = _make_bgd_single_qr_image(bgd, request, "score", ct, vt)
#     right = _make_bgd_single_qr_image(bgd, request, "battle")



#     W, H = left.size  # giả định 2 ảnh cùng size
#     gap = int(W * 0.10)  # khoảng cách giữa 2 QR

#     new_w = W * 2 + gap
#     new_h = H

#     canvas = Image.new("RGB", (new_w, new_h), "white")
#     canvas.paste(left, (0, 0))
#     canvas.paste(right, (W + gap, 0))

#     return canvas


def bgd_list(request):
    out = []
    for b in BanGiamDoc.objects.order_by("maBGD"):
        has = GiamKhao.objects.filter(
            maNV=b.maBGD,
            hoTen__iexact=b.ten,   # so sánh cả mã & họ tên (không phân biệt hoa/thường)
        ).exists()
        out.append({
            "maBGD": b.maBGD,
            "ten": b.ten,
            "token": b.token,
            "has_judge": has,
        })
    return render(request, "bgd/list.html", {"bgds": out})


def bgd_qr_index(request, token=None):
    items = list(
        BanGiamDoc.objects
        .order_by("maBGD")
        .values("maBGD", "ten", "token")
    )

    # Xác định cuộc thi đang chọn (ct):
    # 1) ?ct=... trên URL
    # 2) nếu không có thì lấy cuộc thi đang bật (trangThai=True) mới nhất
    # 3) nếu vẫn không có thì lấy cuộc thi mới nhất
    ct = None
    ct_param = request.GET.get("ct")
    if ct_param:
        ct = CuocThi.objects.filter(id=ct_param).first()
    if not ct:
        ct = CuocThi.objects.filter(trangThai=True).order_by("-id").first()
    if not ct:
        ct = CuocThi.objects.order_by("-id").first()

    # Xác định vòng thi BGD (vt) trong cuộc thi đã chọn:
    # ưu tiên ?vt=...; nếu không có thì lấy vòng BGD mới nhất
    vt = None
    if ct:
        vt_param = request.GET.get("vt")
        if vt_param:
            vt = (
                VongThi.objects
                .filter(id=vt_param, cuocThi=ct, is_bgd_round=True)
                .first()
            )
        if not vt:
            vt = (
                VongThi.objects
                .filter(cuocThi=ct, is_bgd_round=True)
                .order_by("-id")
                .first()
            )

    # build URL đích khi BGD quét QR
    def _go_url(tok):
        if not ct or not vt:
            return "#"
        return request.build_absolute_uri(
            reverse("bgd-go", args=[ct.id, vt.id, tok])
        )

    for it in items:
        it["url"] = _go_url(it["token"])

    # Ưu tiên focus:
    # 1) token trong path (/bgd/qr/<token>/)
    # 2) focus trong query string (?focus=<token>)
    focus_token = token or request.GET.get("focus")
    if focus_token and items:
        try:
            idx = next(i for i, it in enumerate(items) if it["token"] == focus_token)
            if idx != 0:
                items = items[idx:] + items[:idx]
        except StopIteration:
            pass

    # Danh sách cuộc thi cho dropdown: chỉ lấy cuộc thi đang bật
    competitions = list(
        CuocThi.objects
        .filter(trangThai=True)
        .order_by("-id")
        .values("id", "tenCuocThi")
    )

    # Danh sách vòng thi BGD của cuộc thi đang chọn
    rounds = []
    if ct:
        rounds = list(
            VongThi.objects
            .filter(cuocThi=ct, is_bgd_round=True)
            .order_by("-id")
            .values("id", "tenVongThi", "bgd_top_limit")
        )

    return render(
        request,
        "bgd/qr.html",
        {
            "items": items,
            "current_ct": ct,
            "current_vt": vt,
            "competitions": competitions,
            "rounds": rounds,
        },
    )



def bgd_qr_png(request, ct_id: int, vt_id: int, token: str):
    # Đảm bảo Pillow đã cài
    try:
        from PIL import Image  # noqa: F401
    except Exception:
        raise Http404("Thiếu thư viện pillow. Hãy cài: pip install pillow")

    ct = CuocThi.objects.filter(id=ct_id).only("id", "tenCuocThi").first()
    if not ct:
        raise Http404("Không tìm thấy cuộc thi tương ứng với mã QR này.")

    vt = VongThi.objects.filter(id=vt_id, cuocThi=ct, is_bgd_round=True).only("id", "tenVongThi").first()
    if not vt:
        raise Http404("Không tìm thấy vòng thi BGD tương ứng với mã QR này.")

    bgd = (
        BanGiamDoc.objects
        .filter(token=token)
        .only("token", "maBGD", "ten")
        .first()
    )
    if not bgd:
        raise Http404("Không tìm thấy Ban Giám Đốc tương ứng với mã QR này.")

    # Ảnh PNG chứa 2 QR (chấm điểm + đối kháng)
    img = _make_bgd_single_qr_image(bgd, request, ct, vt)


    buf = BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return HttpResponse(buf.getvalue(), content_type="image/png")


def bgd_qr_zip_all(request):
    bgds = list(
        BanGiamDoc.objects
        .order_by("maBGD")
        .only("token", "maBGD", "ten")
    )
    if not bgds:
        return HttpResponse(
            "Chưa có Ban Giám Đốc nào để xuất QR.",
            content_type="text/plain; charset=utf-8",
        )

    # Chọn cuộc thi dùng cho bộ QR này (giống logic bgd_qr_index)
    ct = CuocThi.objects.filter(trangThai=True).order_by("-id").first()
    if not ct:
        ct = CuocThi.objects.order_by("-id").first()
    if not ct:
        return HttpResponse(
            "Không tìm thấy cuộc thi phù hợp để sinh QR.",
            content_type="text/plain; charset=utf-8",
        )

    vt = (
        VongThi.objects
        .filter(cuocThi=ct, is_bgd_round=True)
        .order_by("-id")
        .first()
    )
    if not vt:
        return HttpResponse(
            "Không tìm thấy vòng thi BGD phù hợp để sinh QR.",
            content_type="text/plain; charset=utf-8",
        )

    zip_buf = BytesIO()
    with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for bgd in bgds:
            # Mỗi file PNG trong zip cũng chứa 2 QR giống như trên trang
            img = _make_bgd_single_qr_image(bgd, request, ct, vt)

            img_bytes = BytesIO()
            img.save(img_bytes, format="PNG")
            img_bytes.seek(0)

            filename = f"QR_{bgd.maBGD}.png"
            zf.writestr(filename, img_bytes.getvalue())


    zip_buf.seek(0)
    resp = HttpResponse(zip_buf.getvalue(), content_type="application/zip")
    resp["Content-Disposition"] = 'attachment; filename="bgd_qr_all.zip"'
    return resp


def bgd_go(request, ct_id: int, vt_id: int, token: str):
    bgd = BanGiamDoc.objects.filter(token=token).first()
    if not bgd:
        raise Http404("Token không hợp lệ")

    judge = _auto_login_bgd_as_judge(request, bgd)

    ct = CuocThi.objects.filter(id=ct_id).first()
    if not ct:
        raise Http404("Cuộc thi không tồn tại.")

    vt_bgd = (
        VongThi.objects
        .filter(id=vt_id, cuocThi=ct, is_bgd_round=True)
        .first()
    )
    if not vt_bgd:
        raise Http404("Vòng thi BGD không tồn tại hoặc không thuộc cuộc thi này.")

    # Lưu thông tin vào session để dùng cho save-score / score_bgd_view
    request.session["bgd_mode"] = "score"
    request.session["bgd_ct_id"] = ct.id
    request.session["bgd_ct_name"] = ct.tenCuocThi
    request.session["bgd_vt_id"] = vt_bgd.id
    request.session["bgd_vt_name"] = vt_bgd.tenVongThi
    request.session["bgd_token"] = token
    request.session.modified = True

    contestants = []

    print("[BGD DEBUG] Cuoc thi:", ct.id, ct.tenCuocThi)
    print("[BGD DEBUG] Vong BGD:", vt_bgd.id, vt_bgd.tenVongThi, "Top limit =", vt_bgd.bgd_top_limit)

    if ct and vt_bgd and vt_bgd.bgd_top_limit:
        # Lấy Top X theo "Tổng" điểm của toàn bộ các vòng (trừ vòng BGD),
        # nếu bằng điểm thì so tổng thời gian (ít hơn xếp trên)
        score_rows = (
            PhieuChamDiem.objects
            .filter(
                cuocThi=ct,
                vongThi__is_bgd_round=False,   # không tính vòng BGD
            )
            .values("thiSinh")
            .annotate(
                total_diem=Sum("diem"),
                total_time=Sum("thoiGian"),
            )
            .order_by("-total_diem", "total_time", "thiSinh")[:vt_bgd.bgd_top_limit]
        )

        ts_ids = [row["thiSinh"] for row in score_rows]
        print("[BGD DEBUG] Thi sinh duoc chon theo TONG:", ts_ids)

        contestants = list(ThiSinh.objects.filter(pk__in=ts_ids))
        order_map = {ts_id: idx for idx, ts_id in enumerate(ts_ids)}
        contestants.sort(key=lambda ts: order_map.get(ts.pk, 0))



    # Nếu chưa cấu hình vòng BGD hoặc chưa có dữ liệu -> fallback Top 5 toàn cuộc thi
    if ct and not contestants:
        contestants = (
            ThiSinh.objects.filter(tham_gia__cuocThi=ct)
            .annotate(
                total_diem=Sum(
                    "phieuchamdiem__diem",
                    filter=Q(phieuchamdiem__cuocThi=ct),
                )
            )
            .order_by("-total_diem", "maNV")
            .distinct()[:5]
        )

    # Lấy điểm BGD đã chấm (nếu có) và gán vào từng thí sinh
    if ct and contestants:
        scores_qs = BGDScore.objects.filter(
            bgd=bgd,
            cuocThi=ct,
            thiSinh__in=contestants,
        )

        scores_by_ts = {s.thiSinh_id: s.diem for s in scores_qs}

        for ts in contestants:
            ts.current_bgd_score = scores_by_ts.get(ts.pk)


    context = {
        "bgd": bgd,
        "judge": judge,
        "ct": ct,
        "contestants": contestants,
    }
    return render(request, "bgd/go.html", context)



def bgd_battle_go(request, token: str):
    bgd = BanGiamDoc.objects.filter(token=token).first()
    if not bgd:
        raise Http404("Token không hợp lệ")

    # 1) Tự động login BGD như Giám khảo
    judge = _auto_login_bgd_as_judge(request, bgd)

    # 2) Ghi thêm flag vào session cho mode battle
    request.session["bgd_token"] = token
    request.session["bgd_mode"] = "battle"
    request.session.modified = True

    return redirect("battle")


@csrf_exempt
@require_http_methods(["POST"])
def bgd_save_score(request):
    try:
        payload = json.loads(request.body.decode("utf-8"))
    except Exception:
        return HttpResponseBadRequest("Invalid JSON")

    ts_id = payload.get("thiSinh_id")
    raw_score = payload.get("score")

    if not ts_id or raw_score is None:
        return JsonResponse(
            {"ok": False, "message": "Thiếu thông tin thí sinh hoặc điểm."},
            status=400,
        )

    try:
        score_val = float(raw_score)
    except (TypeError, ValueError):
        return JsonResponse(
            {"ok": False, "message": "Điểm không hợp lệ."},
            status=400,
        )

    if score_val < 0 or score_val > 100:
        return JsonResponse(
            {"ok": False, "message": "Điểm phải trong khoảng 0..100."},
            status=400,
        )

    thi_sinh = ThiSinh.objects.filter(pk=ts_id).first()
    if not thi_sinh:
        return JsonResponse(
            {"ok": False, "message": "Không tìm thấy thí sinh."},
            status=404,
        )

    # 1) Lấy BGD theo token đã lưu khi vào /bgd/go/<ct>/<vt>/<token>/
    bgd_token = request.session.get("bgd_token")
    bgd = BanGiamDoc.objects.filter(token=bgd_token).first()
    if not bgd:
        return JsonResponse(
            {"ok": False, "message": "BGD chưa được xác định trong phiên làm việc."},
            status=401,
        )

    # 2) Lấy cuộc thi: ưu tiên từ session, fallback "Chung Kết"
    ct = None
    ct_id = request.session.get("bgd_ct_id")
    if ct_id:
        ct = CuocThi.objects.filter(pk=ct_id).first()
    if not ct:
        ct = (
            CuocThi.objects.filter(tenCuocThi__iexact="Chung Kết").order_by("-id").first()
            or CuocThi.objects.filter(tenCuocThi__iexact="Chung ket").order_by("-id").first()
        )
    if not ct:
        return JsonResponse(
            {"ok": False, "message": "Không xác định được cuộc thi Chung Kết."},
            status=400,
        )

    diem_int = int(round(score_val))

    # 3) Lưu vào bảng BGDScore (mỗi BGD một dòng riêng)
    bgd_score, created = BGDScore.objects.update_or_create(
        bgd=bgd,
        cuocThi=ct,
        thiSinh=thi_sinh,
        defaults={"diem": diem_int},
    )

    # 4) Lấy vòng thi BGD: ưu tiên từ session (đã set khi vào bgd_go),
    #    fallback: vòng BGD mới nhất của cuộc thi này
    vt = None
    vt_id = request.session.get("bgd_vt_id")
    if vt_id:
        vt = VongThi.objects.filter(pk=vt_id, cuocThi=ct).first()
    if not vt:
        vt = (
            VongThi.objects
            .filter(cuocThi=ct, is_bgd_round=True)
            .order_by("-id")
            .first()
        )

    if not vt:
        return JsonResponse(
            {
                "ok": False,
                "created": bool(created),
                "message": "Đã lưu điểm BGD, nhưng không tìm thấy vòng thi BGD để gắn phiếu chấm.",
            },
            status=400,
        )

    # 5) Tạo / lấy bài thi dành riêng cho vòng BGD này
    bt_name = f"BGD - {vt.tenVongThi}"
    bai_bgd, _ = BaiThi.objects.get_or_create(
        vongThi=vt,
        tenBaiThi=bt_name,
        defaults={
            "cachChamDiem": 100,
            "phuongThucCham": "POINTS",
        },
    )

    # 6) Tính TRUNG BÌNH điểm tất cả BGD đã chấm cho thí sinh này trong cuộc thi này
    agg = BGDScore.objects.filter(cuocThi=ct, thiSinh=thi_sinh).aggregate(
        avg=Avg("diem"),
        cnt=Count("id"),
    )
    avg_score = int(round(agg.get("avg") or 0))
    bgd_count = int(agg.get("cnt") or 0)

    # 7) Chọn 1 giám khảo đại diện để đứng tên phiếu điểm tổng BGD
    #    Ưu tiên ADMIN, nếu không có thì dùng luôn judge đang login (nếu có).
    judge = None
    judge_pk = request.session.get("judge_pk")
    if judge_pk:
        judge = GiamKhao.objects.filter(pk=judge_pk).first()
    if not judge:
        judge = GiamKhao.objects.filter(role="ADMIN").order_by("maNV").first()
    if not judge:
        # fallback cuối cùng: map theo mã BGD
        judge = GiamKhao.objects.filter(maNV=bgd.maBGD).first()

    if not judge:
        return JsonResponse(
            {
                "ok": False,
                "created": bool(created),
                "message": "Không tìm thấy giám khảo đại diện để gắn phiếu chấm BGD.",
            },
            status=400,
        )

    # 8) Ghi 1 phiếu chấm duy nhất cho vòng BGD này:
    #    - Điểm = TRUNG BÌNH tất cả BGD
    #    - thoiGian tạm để 0 (nếu sau này cần lưu số BGD có thể encode chỗ khác)
    phieu, phieu_created = PhieuChamDiem.objects.update_or_create(
        thiSinh=thi_sinh,
        giamKhao=judge,
        cuocThi=ct,
        vongThi=vt,
        baiThi=bai_bgd,
        defaults={
            "maCuocThi": ct.ma,
            "diem": avg_score,
            "thoiGian": 0,
        },
    )

    return JsonResponse(
        {
            "ok": True,
            "created": bool(created),
            "synced": True,
            "message": "Đã lưu điểm BGD, cập nhật điểm trung bình cho phiếu chấm.",
            "debug": {
                "avg_score": avg_score,
                "bgd_count": bgd_count,
            },
        }
    )


# --- 4) View chấm cho BGD: khóa vào "Chung Kết", tái dùng score_view ---
def score_bgd_view(request):
    ct_id = request.session.get("bgd_ct_id")
    if not ct_id:
        # chưa đi qua QR -> quay về trang QR
        return redirect("bgd-qr")

    # ép querystring ct=<id> để score_view hiểu
    mutable_get = request.GET.copy()
    mutable_get["ct"] = str(ct_id)
    request.GET = mutable_get

    # gọi view gốc
    return score_view(request)
