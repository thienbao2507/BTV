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

from .models import BanGiamDoc, CuocThi, GiamKhao, ThiSinh, BGDScore
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
def _make_bgd_single_qr_image(bgd, request, kind: str):
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
        target_url = request.build_absolute_uri(
            reverse("bgd-go", args=[bgd.token])
        )
        suffix = "Score"

    # Tạo QR cho URL tương ứng
    qr = qrcode.QRCode(box_size=10, border=2)
    qr.add_data(target_url)
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color="black", back_color="white").convert("RGB")

    W, H = qr_img.size

    # Text dưới QR: "maBGD - tên - Chấm điểm/Đối kháng"
    label = f"{bgd.maBGD} - {bgd.ten} - {suffix}".strip(" -")

    # Chọn font truetype để chỉnh size
    try:
        font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
        font_size = max(int(W * 0.18), 32)  # chỉnh hệ số nếu muốn to/nhỏ hơn
        font = ImageFont.truetype(font_path, font_size)
    except Exception:
        from PIL import ImageFont as _IF
        font = _IF.load_default()

    # Tính kích thước text
    try:
        bbox = font.getbbox(label)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]
    except AttributeError:
        text_w, text_h = font.getsize(label)

    padding = int(H * 0.08)
    new_h = H + text_h + 2 * padding

    canvas = Image.new("RGB", (W, new_h), "white")
    draw = ImageDraw.Draw(canvas)

    # Dán QR lên trên
    canvas.paste(qr_img, (0, 0))

    # Vẽ text ở giữa phía dưới
    text_x = (W - text_w) // 2
    text_y = H + padding
    draw.text((text_x, text_y), label, fill="black", font=font)

    return canvas


def _make_bgd_dual_qr_image(bgd, request):
    """
    Tạo 1 ảnh chứa 2 QR:
      - trái: chấm điểm
      - phải: đối kháng
    Mỗi QR có label tương ứng phía dưới.
    """
    from PIL import Image

    left = _make_bgd_single_qr_image(bgd, request, "score")
    right = _make_bgd_single_qr_image(bgd, request, "battle")

    W, H = left.size  # giả định 2 ảnh cùng size
    gap = int(W * 0.10)  # khoảng cách giữa 2 QR

    new_w = W * 2 + gap
    new_h = H

    canvas = Image.new("RGB", (new_w, new_h), "white")
    canvas.paste(left, (0, 0))
    canvas.paste(right, (W + gap, 0))

    return canvas


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

    # build URL đích khi quét (QR chấm điểm)
    def _go_url(tok):
        return request.build_absolute_uri(reverse("bgd-go", args=[tok]))

    for it in items:
        it["url"] = _go_url(it["token"])

    # Ưu tiên:
    # 1) token trong path (/bgd/qr/<token>/)
    # 2) focus trong query string (?focus=<token>)
    focus_token = token or request.GET.get("focus")

    # Nếu có focus_token => xoay list để BGD đó nằm đầu (hiện ra trước)
    if focus_token and items:
        try:
            idx = next(i for i, it in enumerate(items) if it["token"] == focus_token)
            if idx != 0:
                items = items[idx:] + items[:idx]
        except StopIteration:
            # token không tồn tại thì giữ nguyên list
            pass

    return render(request, "bgd/qr.html", {"items": items})



def bgd_qr_png(request, token: str):
    # Đảm bảo Pillow đã cài
    try:
        from PIL import Image  # noqa: F401
    except Exception:
        raise Http404("Thiếu thư viện pillow. Hãy cài: pip install pillow")

    bgd = (
        BanGiamDoc.objects
        .filter(token=token)
        .only("token", "maBGD", "ten")
        .first()
    )
    if not bgd:
        raise Http404("Không tìm thấy Ban Giám Đốc tương ứng với mã QR này.")

    # === Ảnh PNG trả về: 2 QR (chấm điểm + đối kháng) trên cùng 1 hình ===
    img = _make_bgd_dual_qr_image(bgd, request)

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

    zip_buf = BytesIO()
    with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for bgd in bgds:
            # Mỗi file PNG trong zip cũng chứa 2 QR giống như trên trang
            img = _make_bgd_dual_qr_image(bgd, request)
            img_bytes = BytesIO()
            img.save(img_bytes, format="PNG")
            img_bytes.seek(0)

            filename = f"QR_{bgd.maBGD}.png"
            zf.writestr(filename, img_bytes.getvalue())

    zip_buf.seek(0)
    resp = HttpResponse(zip_buf.getvalue(), content_type="application/zip")
    resp["Content-Disposition"] = 'attachment; filename="bgd_qr_all.zip"'
    return resp


def bgd_go(request, token: str):
    bgd = BanGiamDoc.objects.filter(token=token).first()
    if not bgd:
        raise Http404("Token không hợp lệ")

    judge = _auto_login_bgd_as_judge(request, bgd)

    ct = CuocThi.objects.filter(tenCuocThi__iexact="Chung Kết").order_by("-id").first()
    if not ct:
        ct = CuocThi.objects.filter(tenCuocThi__iexact="Chung ket").order_by("-id").first()
    if not ct:
        ct = CuocThi.objects.filter(trangThai=True).order_by("-id").first()

    if ct:
        request.session["bgd_mode"] = "score"
        request.session["bgd_ct_id"] = ct.id
        request.session["bgd_ct_name"] = ct.tenCuocThi
    else:
        request.session.pop("bgd_mode", None)
        request.session.pop("bgd_ct_id", None)
        request.session.pop("bgd_ct_name", None)

    request.session["bgd_token"] = token
    request.session.modified = True

    contestants = []
    if ct:
        contestants = (
            ThiSinh.objects.filter(tham_gia__cuocThi=ct)
            .order_by("maNV")
            .distinct()[:5]
        )

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
    """
    API lưu điểm (0–10) cho BGD vào bảng BGDScore.
    - Input JSON: { "thiSinh_id": <id>, "score": <số> }
    - BGD lấy từ session["bgd_token"]
    - Cuộc thi ưu tiên lấy từ session["bgd_ct_id"], fallback "Chung Kết"
    """
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

    # Lấy BGD theo token đã lưu khi vào /bgd/go/<token>/
    bgd_token = request.session.get("bgd_token")
    bgd = BanGiamDoc.objects.filter(token=bgd_token).first()
    if not bgd:
        return JsonResponse(
            {"ok": False, "message": "BGD chưa được xác định trong phiên làm việc."},
            status=401,
        )

    # Lấy cuộc thi: ưu tiên từ session, fallback "Chung Kết"
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

    obj, created = BGDScore.objects.update_or_create(
        bgd=bgd,
        cuocThi=ct,
        thiSinh=thi_sinh,
        defaults={"diem": diem_int},
    )

    return JsonResponse(
        {"ok": True, "created": bool(created), "message": "Đã lưu điểm."}
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
