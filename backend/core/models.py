from django.db import models
import re
from urllib.parse import urlparse, parse_qs

# Create your models here.
from django.db import models
from django.utils import timezone
from django.db.models import Max, SET_NULL
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db.models import Avg, Count, Min
import secrets
import string

def _gen_token_20():
    # 20 ký tự [A-Za-z0-9] an toàn
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(20))

def normalize_drive_url(url: str) -> str:
    """
    Helper chung để convert link Google Drive thành link ảnh trực tiếp.
    Dùng chung cho ThiSinh (và các chỗ khác nếu cần sau này).
    """
    if not url:
        return ""

    if "drive.google.com" not in url:
        return url

    file_id = None

    # /file/d/<id>/
    m = re.search(r"/file/d/([^/]+)", url)
    if m:
        file_id = m.group(1)
    else:
        # ?id=<id>
        parsed = urlparse(url)
        qs = parse_qs(parsed.query)
        if "id" in qs and qs["id"]:
            file_id = qs["id"][0]

    # Nếu vẫn không lấy được id (ví dụ link folders/...), trả lại url gốc
    if not file_id:
        return url

    return f"https://drive.google.com/uc?export=view&id={file_id}"

class BanGiamDoc(models.Model):
    maBGD = models.CharField(primary_key=True, max_length=20)  # "BGD001",...
    ten = models.CharField(max_length=255)
    token = models.CharField(max_length=32, unique=True, editable=False)

    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self.token:
            # phát sinh token 20 ký tự
            self.token = _gen_token_20()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.maBGD} — {self.ten}"
# Helper để sinh mã tự động CTxxx, VTxxx, BTxxx
def generate_code(model, prefix):
    last_code = model.objects.aggregate(max_code=Max("ma"))["max_code"]
    if not last_code:
        return f"{prefix}001"
    num = int(last_code[len(prefix):]) + 1
    return f"{prefix}{num:03d}"


class ThiSinh(models.Model):
    maNV = models.CharField(max_length=20, primary_key=True)
    hoTen = models.CharField(max_length=100)
    chiNhanh = models.CharField(max_length=100, null=True)
    vung = models.CharField(max_length=100, blank=True, null=True)
    donVi = models.CharField(max_length=100, blank=True, null=True)
    email = models.EmailField(unique=True, null=True)
    nhom = models.CharField(max_length=50, null=True)
    cuocThi = models.ManyToManyField(
        'CuocThi',
        through='ThiSinhCuocThi',
        related_name='thiSinhs',
        blank=True
    )
    image_url = models.URLField(
        max_length=500,
        null=True,
        blank=True,
        help_text="URL ảnh (trên Drive) của thí sinh"
    )
    @property
    def display_image_url(self) -> str:
        """
        URL cuối cùng dùng cho <img>.
        Sau này nếu có trường khác (ví dụ hinhAnh) vẫn có thể ưu tiên thêm.
        Hiện tại dùng image_url và convert link Drive nếu cần.
        """
        raw = self.image_url or ""
        return normalize_drive_url(raw)

    def __str__(self):
        return f"{self.maNV} - {self.hoTen}"
class ThiSinhCuocThi(models.Model):
    thiSinh = models.ForeignKey('ThiSinh', on_delete=models.CASCADE, related_name='tham_gia')
    cuocThi = models.ForeignKey('CuocThi', on_delete=models.CASCADE, related_name='thi_sinh_tham_gia')

    class Meta:
        unique_together = ('thiSinh', 'cuocThi')

    def __str__(self):
        try:
            ts = getattr(self.thiSinh, 'maNV', self.thiSinh_id)
            ct = getattr(self.cuocThi, 'ma', self.cuocThi_id)
        except Exception:
            ts, ct = self.thiSinh_id, self.cuocThi_id
        return f"{ts} ↔ {ct}"


class GiamKhao(models.Model):
    maNV = models.CharField(max_length=20, primary_key=True)
    hoTen = models.CharField(max_length=100)
    email = models.EmailField(unique=True)

    ROLE_CHOICES = (
        ("ADMIN", "Admin"),
        ("JUDGE", "Giám khảo"),
    )
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default="JUDGE", db_index=True, null=True)

    contestants_voted = models.ManyToManyField(
        'ThiSinhCapThiDau',
        through='BattleVote',
        related_name='judges',
        blank=True
    )

    def __str__(self):
        return f"{self.maNV} - {self.hoTen}"


class CuocThi(models.Model):
    ma = models.CharField(max_length=10, unique=True, editable=False)
    tenCuocThi = models.CharField(max_length=200)
    trangThai = models.BooleanField(default=False)

    def save(self, *args, **kwargs):
        if not self.ma:
            self.ma = generate_code(CuocThi, "CT")
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.ma} - {self.tenCuocThi}"


class VongThi(models.Model):
    ma = models.CharField(max_length=10, editable=False)
    tenVongThi = models.CharField(max_length=200)
    cuocThi = models.ForeignKey(CuocThi, on_delete=models.CASCADE, related_name="vong_thi")
    is_special_bonus_round = models.BooleanField(default=False)
    special_bonus_score = models.PositiveIntegerField(
        default=100,
        help_text="Điểm cộng cho người thắng trong vòng đặc biệt (thua = 0)."
    )

    # Vòng dành cho Ban Giám Đốc chấm Top X
    is_bgd_round = models.BooleanField(
        default=False,
        help_text="Nếu bật, vòng này dùng để chọn Top X thí sinh đưa sang trang BGD GO."
    )
    
    bgd_top_limit = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Số lượng Top X sẽ lấy từ vòng trước (ví dụ 10, 5...)."
    )

    def save(self, *args, **kwargs):
        if not self.ma:
            self.ma = generate_code(VongThi, "VT")
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.ma} - {self.tenVongThi}"


class BaiThi(models.Model):
    ma = models.CharField(max_length=10, editable=False)
    tenBaiThi = models.CharField(max_length=200)
    cachChamDiem = models.IntegerField()
    vongThi = models.ForeignKey(VongThi, on_delete=models.CASCADE, related_name="bai_thi")
    PHUONG_THUC_CHOICES = (
        ("TIME", "Chấm theo thời gian"),
        ("TEMPLATE", "Chấm theo mẫu"),
        ("POINTS", "Chấm theo thang điểm"),
    )
    phuongThucCham = models.CharField(max_length=20, choices=PHUONG_THUC_CHOICES, default="POINTS")
    def save(self, *args, **kwargs):
        if not self.ma:
            self.ma = generate_code(BaiThi, "BT")
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.ma} - {self.tenBaiThi}"
    
class GiamKhaoBaiThi(models.Model):  
    giamKhao = models.ForeignKey('GiamKhao', on_delete=models.CASCADE, related_name='phan_cong_bai_thi') 
    baiThi = models.ForeignKey('BaiThi', on_delete=models.CASCADE, related_name='giam_khao_duoc_chi_dinh') 
    assigned_at = models.DateTimeField(auto_now_add=True) 

    class Meta:  
        unique_together = ('giamKhao', 'baiThi') 
        indexes = [models.Index(fields=['giamKhao', 'baiThi'])]

    def __str__(self): 
        return f"{self.giamKhao.maNV} → {self.baiThi.ma}"

class BaiThiTimeRule(models.Model):
    baiThi = models.ForeignKey(BaiThi, on_delete=models.CASCADE, related_name="time_rules")
    start_seconds = models.IntegerField()  # inclusive
    end_seconds = models.IntegerField()    # inclusive
    score = models.IntegerField()

    class Meta:
        ordering = ["start_seconds", "end_seconds", "score"]


# NEW: Mẫu chấm theo "TEMPLATE" gắn với từng bài thi
class BaiThiTemplateSection(models.Model):
    baiThi = models.ForeignKey(BaiThi, on_delete=models.CASCADE, related_name="template_sections")
    stt = models.PositiveIntegerField(default=1)  # thứ tự mục lớn
    title = models.CharField(max_length=255)      # tên mục lớn (vd: Phần I: Kiến thức)
    note = models.CharField(max_length=255, blank=True, null=True)  # ghi chú (nếu có)

    class Meta:
        ordering = ["baiThi_id", "stt"]

    def __str__(self):
        return f"{self.baiThi.ma} - [{self.stt}] {self.title}"


class BaiThiTemplateItem(models.Model):
    section = models.ForeignKey(BaiThiTemplateSection, on_delete=models.CASCADE, related_name="items")
    stt = models.PositiveIntegerField(default=1)     # thứ tự mục con trong section
    content = models.CharField(max_length=500)       # nội dung tiêu chí/câu hỏi
    max_score = models.IntegerField(default=0)       # điểm tối đa cho mục con
    note = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        ordering = ["section_id", "stt"]

    def __str__(self):
        return f"{self.section.baiThi.ma} - {self.section.title} - [{self.stt}] {self.content}"

class PhieuChamDiem(models.Model):
    maPhieu = models.AutoField(primary_key=True)
    thiSinh = models.ForeignKey(ThiSinh, on_delete=models.CASCADE)
    giamKhao = models.ForeignKey(GiamKhao, on_delete=models.CASCADE)
    cuocThi = models.ForeignKey(CuocThi, on_delete=models.CASCADE)
    maCuocThi = models.CharField(max_length=10, db_index=True, editable=False)  # NEW
    vongThi = models.ForeignKey(VongThi, on_delete=models.CASCADE)
    baiThi = models.ForeignKey(BaiThi, on_delete=models.CASCADE)
    diem = models.IntegerField(validators=[MinValueValidator(0)])
    thoiGian = models.PositiveIntegerField(default = 0, help_text="Thời gian (giây)")
    updated_at = models.DateTimeField(default=timezone.now)

    class Meta:
        unique_together = ("thiSinh", "giamKhao", "baiThi")

    def save(self, *args, **kwargs):
        # đồng bộ mã cuộc thi từ FK (lưu CTxxx để báo cáo/search nhanh)
        self.maCuocThi = self.cuocThi.ma

        # kiểm tra điểm hợp lệ theo phương thức chấm
        method = getattr(self.baiThi, "phuongThucCham", "POINTS")
        if self.diem is None or self.diem < 0:
            raise ValueError("Điểm không hợp lệ!")

        if method == "POINTS":
            # chỉ áp trần khi là thang điểm
            if self.diem > self.baiThi.cachChamDiem:
                raise ValueError("Điểm vượt quá điểm tối đa của bài thi!")
            
        # BGD (maBGD trùng maNV, ten trùng hoTen) luôn được chấm tự do
        # cho cuộc thi "Chung Kết" (không cần phân công từng bài).
        is_bgd = False
        try:
            is_bgd = BanGiamDoc.objects.filter(
                maBGD=self.giamKhao.maNV,
                ten__iexact=self.giamKhao.hoTen,
            ).exists()
        except Exception:
            is_bgd = False

        is_chung_ket = False
        try:
            tn = (self.cuocThi.tenCuocThi or "").strip().lower()
            is_chung_ket = tn in ("chung kết", "chung ket")
        except Exception:
            is_chung_ket = False

        # Cho phép BGD chấm tự do ở vòng được bật chế độ BGD
        is_bgd_round = False
        try:
            is_bgd_round = bool(getattr(self.vongThi, "is_bgd_round", False))
        except Exception:
            is_bgd_round = False

        # BGD được bỏ qua phân công nếu:
        #   - là BGD, và
        #   - cuộc thi là "Chung Kết" hoặc vòng đó là vòng BGD
        allow_without_assign = is_bgd and (is_chung_ket or is_bgd_round)

        if getattr(self.giamKhao, "role", "JUDGE") != "ADMIN" and not allow_without_assign:
            from .models import GiamKhaoBaiThi
            allowed = GiamKhaoBaiThi.objects.filter(
                giamKhao=self.giamKhao,
                baiThi=self.baiThi
            ).exists()
            if not allowed:
                raise PermissionError("Giám khảo chưa được admin chỉ định cho bài thi này.")


        # (TIME/TEMPLATE sẽ được quy đổi/validate ở bước 3B)
        self.updated_at = timezone.now()
        super().save(*args, **kwargs)
        
class SpecialRoundPair(models.Model):
    cuocThi = models.ForeignKey(CuocThi, on_delete=models.CASCADE)
    vongThi = models.ForeignKey(VongThi, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Cặp đặc biệt - {self.id}"
class SpecialRoundPairMember(models.Model):
    pair = models.ForeignKey(SpecialRoundPair, on_delete=models.CASCADE, related_name="members")
    thiSinh = models.ForeignKey(ThiSinh, on_delete=models.CASCADE)
    side = models.CharField(max_length=1)     # L hoặc R
    slot = models.PositiveSmallIntegerField() # 1 hoặc 2

    class Meta:
        unique_together = ("pair", "slot")

    def __str__(self):
        return f"{self.thiSinh} - {self.side}"
class BonusCompareLog(models.Model):
    special_pair = models.ForeignKey(SpecialRoundPair, on_delete=models.CASCADE, null=True, blank=True)
    cuocThi = models.ForeignKey(CuocThi, on_delete=models.CASCADE)
    vongThi = models.ForeignKey(VongThi, on_delete=models.CASCADE)
    baiThi = models.ForeignKey(BaiThi, on_delete=models.CASCADE)
    giamKhao = models.ForeignKey(GiamKhao, on_delete=models.CASCADE)
    thiSinh = models.ForeignKey(ThiSinh, on_delete=models.CASCADE)

    raw_score = models.FloatField(default=0)
    raw_time = models.PositiveIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("special_pair", "baiThi", "giamKhao", "thiSinh")
class SpecialRoundScoreLog(models.Model):
    """
    Log điểm raw cho vòng đặc biệt (trước khi đổi sang 100/0).
    Mỗi dòng = 1 thí sinh trong 1 cặp, 1 bài thi, 1 giám khảo.
    """
    cuocThi = models.ForeignKey(CuocThi, on_delete=models.CASCADE)
    vongThi = models.ForeignKey(VongThi, on_delete=models.CASCADE)
    baiThi = models.ForeignKey(BaiThi, on_delete=models.CASCADE)

    pair_member = models.ForeignKey(
        SpecialRoundPairMember,
        on_delete=models.CASCADE,
        related_name="score_logs",
    )

    giamKhao = models.ForeignKey(
        GiamKhao,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )

    raw_score = models.FloatField()
    raw_time = models.IntegerField(
        null=True,
        blank=True,
        help_text="Thời gian (giây) nếu có.",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Special round raw score log"
        verbose_name_plural = "Special round raw score logs"
        ordering = ["-created_at"]

    def __str__(self):
        ts = getattr(self.pair_member.thiSinh, "maNV", self.pair_member.thiSinh_id)
        pair_id = getattr(self.pair_member.pair, "id", None)
        return f"{ts} – {self.raw_score}đ (cặp {pair_id})"

def compute_special_round_pair_result(cuocThi, vongThi, baiThi, special_pair):
    """
    Tính kết quả 100/0 cho 1 cặp vòng đặc biệt, BỎ QUA giamKhao.
    - Gom tất cả SpecialRoundScoreLog của pair đó (mọi giám khảo).
    - Mỗi thí sinh: tính avg(raw_score), min(raw_time).
    - So sánh 2 bên → winner = 100, loser = 0.
    Trả về dict: {thiSinh_id: 100 hoặc 0}
    """
    from .models import SpecialRoundScoreLog, SpecialRoundPairMember  # tránh import vòng

    # 1) Lấy tất cả log thuộc đúng cuộc thi / vòng / bài / cặp
    logs = (
        SpecialRoundScoreLog.objects
        .filter(
            cuocThi=cuocThi,
            vongThi=vongThi,
            baiThi=baiThi,
            pair_member__pair=special_pair,
        )
    )

    # Nếu chưa đủ hai thí sinh có log thì chưa làm gì
    agg = (
        logs.values("pair_member_id")
        .annotate(
            avg_score=Avg("raw_score"),
            best_time=Min("raw_time"),
        )
    )

    data = list(agg)
    if len(data) < 2:
        # Mới có 1 bên được chấm → chưa kết luận
        return {}

    # Giả sử 1vs1: lấy 2 entry đầu
    m1, m2 = data[0], data[1]

    # Map pair_member_id -> thiSinh_id (để trả kết quả)
    member_qs = SpecialRoundPairMember.objects.filter(id__in=[m1["pair_member_id"], m2["pair_member_id"]])
    member_map = {m.id: m.thiSinh_id for m in member_qs}

    # Helper lấy số liệu
    def key(m):
        score = m["avg_score"] or 0.0
        time_ = m["best_time"]
        # Nếu không có thời gian → coi như rất lớn (bất lợi trong tie-break)
        if time_ is None:
            time_ = 10**9
        return score, -time_  # score ↑, time ↓ (dùng -time để sort desc theo score, asc theo time)

    s1, s2 = key(m1), key(m2)

    # Mặc định 0 điểm
    result = {
        member_map.get(m1["pair_member_id"]): 0,
        member_map.get(m2["pair_member_id"]): 0,
    }

    # So sánh:
    if s1 > s2:
        # m1 thắng
        result[member_map[m1["pair_member_id"]]] = 100
    elif s2 > s1:
        # m2 thắng
        result[member_map[m2["pair_member_id"]]] = 100
    else:
        # Hoà tuyệt đối: cả hai 0 (hoặc tuỳ bạn muốn chia 50/50 thì chỉnh ở đây)
        pass

    return result

class CapThiDau(models.Model):
    """
    Một cặp / một trận đối kháng.
    Hiện tại mỗi pair = 1 vs 1.
    Sau này vẫn dùng lại được cho 2 vs 2, N vs N (nhiều member mỗi bên).
    """
    cuocThi = models.ForeignKey(
        CuocThi,
        on_delete=models.CASCADE,
        related_name="battle_pairs"
    )
    vongThi = models.ForeignKey(
        VongThi,
        on_delete=models.CASCADE,
        related_name="battle_pairs",
        null=True,
        blank=True,
        help_text="Có thể gắn với vòng thi (VD: Chung kết, Bán kết...)"
    )

    maCapDau = models.CharField(
        max_length=20,
        unique=True,
        editable=False,
        db_index=True
    )
    tenCapDau = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        help_text="Tên hiển thị cặp đấu (nếu muốn đặt). VD: Bảng A - Trận 1"
    )
    thuTuThiDau = models.PositiveIntegerField(
        default=1,
        help_text="Thứ tự hiển thị cặp đấu"
    )
    active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        # Tự sinh mã BK001, BK002...
        if not self.maCapDau:
            from django.db.models import Max
            last_code = CapThiDau.objects.aggregate(max_code=Max("maCapDau"))["max_code"]
            if not last_code:
                self.maCapDau = "CK001"
            else:
                try:
                    num = int(last_code[2:]) + 1
                except ValueError:
                    num = 1
                self.maCapDau = f"CK{num:03d}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.maCapDau} - {self.cuocThi.tenCuocThi} (#{self.thuTuThiDau})"


class ThiSinhCapThiDau(models.Model):
    """
    Một thí sinh cụ thể nằm trong một cặp đấu (ở bên trái / phải).
    - 1 cặp 1vs1: mỗi bên (L/R) có 1 member (slot = 1).
    - 2vs2: mỗi bên có 2 member (slot = 1,2).
    - NvsN: cứ thế tăng slot.
    """
    SIDE_CHOICES = (
        ("L", "Bên trái"),
        ("R", "Bên phải"),
    )

    pair = models.ForeignKey(
        CapThiDau,
        on_delete=models.CASCADE,
        related_name="members"
    )
    thiSinh = models.ForeignKey(
        ThiSinh,
        on_delete=models.CASCADE,
        related_name="battle_entries"
    )
    side = models.CharField(
        max_length=1,
        choices=SIDE_CHOICES,
        help_text="L = đội/trận bên trái, R = đội bên phải"
    )
    slot = models.PositiveSmallIntegerField(
        default=1,
        help_text="Thứ tự trong đội (dùng cho 2vs2, NvsN)"
    )
    @property
    def display_image_url(self) -> str:
        """
        Lấy URL ảnh hiển thị từ ThiSinh.
        Nếu ThiSinh có display_image_url thì dùng lại luôn.
        """
        return getattr(self.thiSinh, "display_image_url", "")
    
    @property
    def total_votes(self) -> int:
        """
        Tổng số phiếu vote cho entry này.
        """
        return self.votes.count()

    @property
    def avg_stars(self):
        """
        Điểm sao trung bình (float) hoặc None nếu chưa có vote.
        """
        from django.db.models import Avg
        agg = self.votes.aggregate(avg=Avg("stars"))
        return agg.get("avg")
    class Meta:
        unique_together = ("pair", "side", "slot")
        indexes = [
            models.Index(fields=["pair", "side"]),
            models.Index(fields=["thiSinh"]),
        ]

    def __str__(self):
        return f"{self.pair.maCapDau} - {self.get_side_display()} - {self.thiSinh.maNV} (slot {self.slot})"
    
class BattleVote(models.Model):
    giamKhao = models.ForeignKey(
        GiamKhao,
        on_delete=models.CASCADE,
        related_name="battle_votes",
        null=True,
        blank=True,
        db_column="giam_khao_id",
    )
    entry = models.ForeignKey(
        ThiSinhCapThiDau,
        on_delete=models.CASCADE,
        related_name="votes"
    )
    stars = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        help_text="Số sao vote (1–5)"
    )
    note = models.TextField(
        null=True,
        blank=True,
        help_text="Nhận xét của BGD (tuỳ chọn)"
    )
    # NEW: tick “♥ Tim” (không bắt buộc)
    heart = models.BooleanField(
        default=False,
        db_index=True,
        help_text="Ưu tiên (♥) của giám khảo"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("giamKhao", "entry")
        indexes = [
            models.Index(fields=["giamKhao", "entry"]),
            models.Index(fields=["entry"]),
        ]

    def __str__(self):
        gk = self.giamKhao.maNV if self.giamKhao else "N/A"
        ts = getattr(self.entry.thiSinh, "maNV", self.entry.thiSinh_id)
        pair_code = getattr(self.entry.pair, "maCapDau", self.entry.pair_id)
        # thêm ký hiệu tim để dễ debug
        heart_flag = " ♥" if getattr(self, "heart", False) else ""
        return f"Vote {self.stars}★{heart_flag} - {gk} -> {ts} ({pair_code})"

class BGDScore(models.Model):
    bgd = models.ForeignKey(BanGiamDoc, on_delete=models.CASCADE, related_name="scores")
    cuocThi = models.ForeignKey(CuocThi, on_delete=models.CASCADE, related_name="bgd_scores")
    thiSinh = models.ForeignKey(ThiSinh, on_delete=models.CASCADE, related_name="bgd_scores")
    diem = models.IntegerField(validators=[MinValueValidator(0), MaxValueValidator(100)])
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("bgd", "cuocThi", "thiSinh")

    def __str__(self):
        return f"{self.bgd.maBGD} - {self.cuocThi.ma} - {self.thiSinh.maNV}: {self.diem}"