from django.contrib import admin
from django.utils.html import mark_safe
from .models import (
    CuocThi,
    VongThi,
    BaiThi,
    BaiThiTemplateSection,
    BaiThiTemplateItem,
    ThiSinh,
    GiamKhao,
    GiamKhaoBaiThi,
    BanGiamDoc,
    PhieuChamDiem,
    CapThiDau,
    ThiSinhCapThiDau,
    SpecialRoundPair,
    SpecialRoundPairMember,
    BattleVote,
    SpecialRoundScoreLog,
    BGDScore,
)

admin.site.register(SpecialRoundPair)
@admin.register(SpecialRoundPairMember)
class SpecialRoundPairMemberAdmin(admin.ModelAdmin):
    list_display = ("thi_sinh_info", "pair_info", "side", "slot")
    list_filter = ("pair__cuocThi", "pair__vongThi", "side")
    search_fields = ("thiSinh__maNV", "thiSinh__hoTen", "pair__id")

    def thi_sinh_info(self, obj):
        try:
            return f"{obj.thiSinh.maNV} - {obj.thiSinh.hoTen}"
        except Exception:
            return str(obj)
    thi_sinh_info.short_description = "Thí sinh"

    def pair_info(self, obj):
        try:
            return f"Cặp {obj.pair.id}"
        except Exception:
            return ""
    pair_info.short_description = "Cặp"


@admin.register(ThiSinh)
class ThiSinhAdmin(admin.ModelAdmin):
    list_display = ("maNV", "hoTen", "chiNhanh", "vung", "donVi", "nhom", "image_url", "ds_cuoc_thi")
    list_filter = ("cuocThi",)   # đúng tên field M2M
    search_fields = ("maNV", "hoTen", "email", "vung", "donVi")

    def ds_cuoc_thi(self, obj):
        try:
            return ", ".join(ct.ma for ct in obj.cuocThi.all())
        except Exception:
            return ""
    ds_cuoc_thi.short_description = "Cuộc thi"



@admin.register(GiamKhao)
class GiamKhaoAdmin(admin.ModelAdmin):
    list_display = ("maNV", "hoTen", "email", "role", "bai_thi")
    search_fields = ("maNV", "hoTen")

    def bai_thi(self, obj):
        try:
            # obj.phan_cong_bai_thi yields GiamKhaoBaiThi instances (assignment objects)
            # access the related BaiThi via .baiThi
            return ", ".join([assign.baiThi.tenBaiThi for assign in obj.phan_cong_bai_thi.all()])
        except Exception:
            return ""
    bai_thi.short_description = "Bài thi"
    
@admin.register(CuocThi)
class CuocThiAdmin(admin.ModelAdmin):
    list_display = ("ma", "tenCuocThi", "trangThai")
    search_fields = ("ma", "tenCuocThi")
    list_filter = ("trangThai",)


@admin.register(VongThi)
class VongThiAdmin(admin.ModelAdmin):
    list_display = ("ma", "tenVongThi", "cuocThi")
    search_fields = ("ma", "tenVongThi")  
    list_filter = ("cuocThi",)

@admin.register(BaiThi)
class BaiThiAdmin(admin.ModelAdmin):
    list_display = ("ma", "tenBaiThi", "cachChamDiem", "vongThi", "giam_khao")
    search_fields = ("ma", "tenBaiThi")
    list_filter = ("vongThi",)

    def giam_khao(self, obj):
        return ", ".join([gk.giamKhao.hoTen for gk in obj.giam_khao_duoc_chi_dinh.all()])

@admin.register(PhieuChamDiem)
class PhieuChamDiemAdmin(admin.ModelAdmin):
    list_display = ("maPhieu", "thiSinh", "giamKhao", "baiThi", "diem", "maCuocThi", "thoiGian", "updated_at")
    search_fields = ("thiSinh__maNV", "giamKhao__maNV", "baiThi__ma", "maCuocThi")
    list_filter = ("maCuocThi", "baiThi")
    
@admin.register(BaiThiTemplateSection)
class BaiThiTemplateSectionAdmin(admin.ModelAdmin):
    list_display = ("id", "baiThi", "stt", "title")
    list_filter = ("baiThi",)
    search_fields = ("title", "baiThi__ma")

@admin.register(BaiThiTemplateItem)
class BaiThiTemplateItemAdmin(admin.ModelAdmin):
    list_display = ("id", "section", "stt", "content", "max_score")
    list_filter = ("section__baiThi",)
    search_fields = ("content", "section__title", "section__baiThi__ma")

@admin.register(BanGiamDoc)
class BanGiamDocAdmin(admin.ModelAdmin):
    list_display = ("maBGD", "ten", "token", "created_at")
    search_fields = ("maBGD", "ten", "token")
class ThiSinhCapThiDauInline(admin.TabularInline):
    model = ThiSinhCapThiDau
    extra = 0
    fields = ("side", "slot", "thiSinh", "thiSinh_image")
    readonly_fields = ("thiSinh_image",)

    def thiSinh_image(self, obj):
        if not obj.pk or not getattr(obj.thiSinh, "display_image_url", None):
            return ""
        url = obj.thiSinh.display_image_url
        return mark_safe(f'<img src="{url}" style="height:50px;" />')
    thiSinh_image.short_description = "Ảnh thí sinh"

@admin.register(CapThiDau)
class CapThiDauAdmin(admin.ModelAdmin):
    list_display = ("maCapDau", "cuocThi", "vongThi", "thuTuThiDau", "active", "created_at")
    list_filter = ("cuocThi", "vongThi", "active")
    search_fields = ("maCapDau", "cuocThi__ma", "cuocThi__tenCuocThi")
    ordering = ("cuocThi", "thuTuThiDau")
    inlines = [ThiSinhCapThiDauInline]

class BattleVoteInline(admin.TabularInline):
    model = BattleVote
    extra = 0
    fields = ("giamKhao", "stars", "heart", "note", "created_at", "updated_at")  # + heart
    readonly_fields = ("created_at", "updated_at")


@admin.register(ThiSinhCapThiDau)
class ThiSinhCapThiDauAdmin(admin.ModelAdmin):
    list_display = ("pair", "side", "slot", "thiSinh", "thiSinh_image_url")
    list_filter = ("pair__cuocThi", "side")
    search_fields = ("thiSinh__maNV", "thiSinh__hoTen", "pair__maCapDau")
    inlines = [BattleVoteInline]

    def thiSinh_image_url(self, obj):
        """
        Hiển thị URL ảnh lấy từ ThiSinh.image_url (hoặc display_image_url).
        """
        if getattr(obj.thiSinh, "display_image_url", None):
            return obj.thiSinh.display_image_url
        return ""
    thiSinh_image_url.short_description = "Image URL"

@admin.register(BattleVote)
class BattleVoteAdmin(admin.ModelAdmin):
    list_display = ("id", "giamKhao", "entry", "stars", "heart", "short_note", "created_at", "updated_at")  # + heart
    list_filter = ("heart", "stars", "giamKhao", "entry__pair__cuocThi")  # + heart filter
    search_fields = (
        "giamKhao__maNV",
        "giamKhao__hoTen",
        "entry__thiSinh__maNV",
        "entry__thiSinh__hoTen",
        "entry__pair__maCapDau",
    )


    def short_note(self, obj):
        if not obj.note:
            return ""
        return (obj.note[:40] + "…") if len(obj.note) > 40 else obj.note
    short_note.short_description = "Ghi chú"
    
    
@admin.register(SpecialRoundScoreLog)
class SpecialRoundScoreLogAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "get_thi_sinh",
        "get_pair_label",
        "baiThi",
        "giamKhao",
        "raw_score",
        "raw_time",
        "created_at",
    )
    list_filter = (
        "baiThi",
        "giamKhao",
        "vongThi",
    )
    search_fields = (
        "pair_member__thiSinh__maNV",
        "pair_member__thiSinh__hoTen",
    )

    def get_thi_sinh(self, obj):
        return obj.pair_member.thiSinh
    get_thi_sinh.short_description = "Thí sinh"
    
    def get_pair_label(self, obj):
        return f"Cặp {obj.pair_member.pair_id}"
    get_pair_label.short_description = "Cặp"


@admin.register(BGDScore)
class BGDScoreAdmin(admin.ModelAdmin):
    list_display = ("bgd", "cuocThi", "vongThi", "thiSinh", "diem", "created_at", "updated_at")
    list_filter = ("cuocThi", "bgd")
    search_fields = ("bgd__maBGD", "cuocThi__ma", "thiSinh__maNV", "thiSinh__hoTen")
