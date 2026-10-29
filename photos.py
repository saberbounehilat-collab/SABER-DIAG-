"""Secure image upload and moderated photo gallery for SABER ACTROS DZ."""
from datetime import datetime, timedelta, timezone
from functools import wraps
from io import BytesIO

from flask import abort, flash, redirect, request, Response
from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy import Column, Integer, String, DateTime, LargeBinary, ForeignKey, select, func

MAX_FILE_BYTES = 4 * 1024 * 1024
MAX_OUTPUT_BYTES = 1400 * 1024
IMAGE_LIMIT = 12_000_000
Image.MAX_IMAGE_PIXELS = IMAGE_LIMIT


def register_photo_model(Base):
    class Photo(Base):
        __tablename__ = "photos"
        id = Column(Integer, primary_key=True)
        user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
        product_id = Column(Integer, ForeignKey("products.id"), nullable=True)
        kind = Column(String(20), nullable=False, default="gallery")
        status = Column(String(24), nullable=False, default="pending")
        title = Column(String(140), nullable=False, default="")
        description = Column(String(1000), nullable=False, default="")
        image_data = Column(LargeBinary, nullable=False)
        content_type = Column(String(50), nullable=False, default="image/webp")
        created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    return Photo


def transform_image(file):
    if not file or not file.filename:
        raise ValueError("اختر صورة أولاً.")
    raw = file.stream.read(MAX_FILE_BYTES + 1)
    if not raw or len(raw) > MAX_FILE_BYTES:
        raise ValueError("حجم الصورة يجب ألا يتجاوز 4 ميغابايت.")
    try:
        with Image.open(BytesIO(raw)) as uploaded:
            if uploaded.format not in ("JPEG", "PNG", "WEBP"):
                raise ValueError("المسموح صور JPG أو PNG أو WebP فقط.")
            if uploaded.width * uploaded.height > IMAGE_LIMIT:
                raise ValueError("أبعاد الصورة كبيرة جداً.")
            uploaded.load()
            normalized = ImageOps.exif_transpose(uploaded).convert("RGB")
            normalized.thumbnail((1600, 1600), Image.Resampling.LANCZOS)
            out = BytesIO()
            normalized.save(out, format="WEBP", quality=78, method=5)
            result = out.getvalue()
            if len(result) > MAX_OUTPUT_BYTES:
                raise ValueError("الصورة كبيرة بعد المعالجة، جرّب صورة أصغر.")
            return result
    except (UnidentifiedImageError, OSError, ValueError) as err:
        if isinstance(err, ValueError):
            raise
        raise ValueError("لم يمكن قراءة الصورة. اختر صورة JPG أو PNG أو WebP سليمة.") from err


def setup_photo_routes(app, Photo, DB, user, page, field, admin_only, Product, User):
    app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024

    @app.get("/gallery")
    def photo_gallery():
        d = DB()
        approved = d.scalars(
            select(Photo).where(Photo.kind == "gallery", Photo.status == "approved")
            .order_by(Photo.id.desc()).limit(60)
        ).all()
        current = user()
        mine = []
        if current and not current.admin:
            mine = d.scalars(
                select(Photo).where(Photo.kind == "gallery", Photo.user_id == current.id)
                .order_by(Photo.id.desc()).limit(30)
            ).all()
        return page("""<div class="container">
<h1>معرض صور SABER ACTROS DZ</h1>
<p class="muted">صور الأعمال الفنية والشاحنات والتشخيص. جميع الصور المنشورة من الأعضاء تتم مراجعتها قبل عرضها.</p>
<div class="grid">
{% for pic in approved %}
<div class="card"><img class="gallery-image" src="/photos/file/{{pic.id}}" loading="lazy" alt="{{pic.title}}">
<h3>{{pic.title}}</h3><p>{{pic.description}}</p></div>
{% else %}<div class="card">لا توجد صور منشورة حتى الآن.</div>{% endfor %}
</div><section class="card" style="max-width:650px">
<h2>نشر صورة جديدة</h2>
{% if me %}
<p class="muted">يمكنك إرسال صورتك، ولن تظهر للزوار قبل موافقة إدارة المتجر. الحد الأقصى 4MB وصيغ JPG أو PNG أو WebP.</p>
<form method="post" action="/gallery/upload" enctype="multipart/form-data">
<input type="hidden" name="csrf" value="{{csrf}}">
<label>عنوان الصورة <input name="title" maxlength="140" required></label>
<label>الوصف <textarea name="description" maxlength="1000" rows="3"></textarea></label>
<label>الصورة <input type="file" name="photo" accept="image/jpeg,image/png,image/webp" required></label>
<label><input type="checkbox" name="permission" value="yes" required>
أؤكد أن لدي حق نشر هذه الصورة وأوافق على عرضها للعامة بعد مراجعتها، دون معلومات شخصية للآخرين.</label>
<button type="submit">إرسال الصورة للمراجعة</button>
</form>
{% else %}
<p>سجّل الدخول أو أنشئ حسابًا لإرسال صورة.</p>
<a class="button" href="/login">تسجيل الدخول</a>
{% endif %}</section>
{% if mine %}<section><h2>صوري وحالة مراجعتها</h2><div class="grid">
{% for pic in mine %}<div class="card"><img class="gallery-image" src="/photos/file/{{pic.id}}" loading="lazy" alt="{{pic.title}}">
<h3>{{pic.title}}</h3><p>{{pic.status}}</p></div>{% endfor %}
</div></section>{% endif %}</div>""", approved=approved, mine=mine)

    @app.post("/gallery/upload")
    def photo_submit():
        current = user()
        if not current:
            return redirect("/login")
        title = field("title", 140)
        if not title or request.form.get("permission") != "yes":
            abort(400)
        d = DB()
        today = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=1)
        recent = d.scalar(select(func.count()).select_from(Photo).where(
            Photo.user_id == current.id, Photo.created_at >= today))
        if recent >= 5:
            flash("تم بلوغ الحد اليومي: خمس صور لكل حساب.")
            return redirect("/gallery")
        try:
            image_data = transform_image(request.files.get("photo"))
        except ValueError as e:
            flash(str(e))
            return redirect("/gallery")
        d.add(Photo(user_id=current.id, title=title, description=field("description", 1000),
                    kind="gallery", status="pending", image_data=image_data))
        d.commit()
        flash("تم استقبال الصورة للمراجعة. لن تظهر للعامة قبل الموافقة.")
        return redirect("/gallery")

    @app.get("/photos/file/<int:photo_id>")
    def photo_file(photo_id):
        item = DB().get(Photo, photo_id)
        if not item:
            abort(404)
        current = user()
        authorized = item.status == "approved" or (
            current and (current.admin or (item.user_id == current.id and item.kind == "gallery")))
        if not authorized:
            abort(404)
        data = bytes(item.image_data)
        headers = {"X-Content-Type-Options": "nosniff",
                   "Content-Security-Policy": "default-src 'none'; sandbox",
                   "Cache-Control": "private, no-store" if item.status != "approved" else "public, max-age=600"}
        return Response(data, mimetype="image/webp", headers=headers)

    @app.get("/admin/photos")
    @admin_only
    def photo_management():
        d = DB()
        pending = d.scalars(select(Photo).where(
            Photo.kind == "gallery", Photo.status == "pending").order_by(Photo.id.asc()).limit(100)).all()
        published = d.scalars(select(Photo).where(
            Photo.status == "approved").order_by(Photo.id.desc()).limit(100)).all()
        hero = d.scalar(select(Photo).where(Photo.kind == "hero", Photo.status == "approved").order_by(Photo.id.desc()))
        products = d.scalars(select(Product).order_by(Product.id)).all()
        return page("""<div class="container"><h1>إدارة الصور</h1>
<p><a href="/admin">العودة للوحة الإدارة</a></p>
<section class="card"><h2>خلفية الصفحة الرئيسية للمتجر</h2>
<p>اختر صورة بانورامية لشاحنات SABER ACTROS DZ والمعدات الثقيلة. تُنشر الخلفية مباشرة بعد الرفع وتظهر لزوار الصفحة الرئيسية.</p>
{% if hero %}<img class="gallery-image" src="/photos/file/{{hero.id}}" alt="الخلفية الحالية للمتجر" style="height:auto;aspect-ratio:21/9;object-fit:cover;max-height:420px">{% else %}<p class="muted">لم يتم تعيين خلفية بعد.</p>{% endif %}
<form method="post" action="/admin/photos/hero" enctype="multipart/form-data">
<input type="hidden" name="csrf" value="{{csrf}}">
<label>اختر صورة الخلفية (PNG أو JPG أو WebP، حتى 4MB)<input type="file" name="photo" accept="image/jpeg,image/png,image/webp" required></label>
<button type="submit">تعيين خلفية المتجر</button>
</form></section>
<section class="card"><h2>أضف صورة لبرنامج أو خدمة</h2><p>تُعرض الصورة مباشرة على بطاقة المنتج في المتجر.</p>
<form method="post" action="/admin/photos/product" enctype="multipart/form-data">
<input type="hidden" name="csrf" value="{{csrf}}">
<label>البرنامج أو الخدمة<select name="product_id" required>
{% for p in products %}<option value="{{p.id}}">{{p.title}}</option>{% endfor %}</select></label>
<label>الصورة (JPG / PNG / WebP، أقل من 4MB)<input type="file" name="photo" accept="image/jpeg,image/png,image/webp" required></label>
<button>نشر صورة المنتج</button>
</form></section>
<section><h2>صور الأعضاء بانتظار الموافقة ({{pending|length}})</h2><div class="grid">
{% for pic in pending %}<div class="card"><img class="gallery-image" src="/photos/file/{{pic.id}}" alt="{{pic.title}}">
<h3>{{pic.title}}</h3><p>{{pic.description}}</p><div class="photo-actions">
<form method="post" action="/admin/photos/{{pic.id}}/moderate"><input type="hidden" name="csrf" value="{{csrf}}">
<input type="hidden" name="action" value="approve"><button>الموافقة على النشر</button></form>
<form method="post" action="/admin/photos/{{pic.id}}/moderate"><input type="hidden" name="csrf" value="{{csrf}}">
<input type="hidden" name="action" value="reject"><button>رفض الصورة</button></form></div></div>
{% else %}<p>لا توجد صور بانتظار المراجعة.</p>{% endfor %}</div></section>
<section><h2>صور منشورة</h2><div class="grid">{% for pic in published %}
<div class="card"><img class="gallery-image" src="/photos/file/{{pic.id}}" alt="{{pic.title}}">
<h3>{{pic.title}}</h3><p>{{'خلفية المتجر' if pic.kind=='hero' else ('صورة منتج' if pic.kind=='product' else 'صورة عضو')}}</p>
<form method="post" action="/admin/photos/{{pic.id}}/moderate" onsubmit="return confirm('حذف الصورة المنشورة؟');">
<input type="hidden" name="csrf" value="{{csrf}}">
<input type="hidden" name="action" value="delete"><button>حذف الصورة</button>
</form></div>{% endfor %}</div></section></div>""", pending=pending, published=published, products=products, hero=hero)

    @app.post("/admin/photos/hero")
    @admin_only
    def photo_hero_upload():
        try:
            image_data = transform_image(request.files.get("photo"))
        except ValueError as e:
            flash(str(e))
            return redirect("/admin/photos")
        d = DB()
        for old in d.scalars(select(Photo).where(Photo.kind == "hero")).all():
            d.delete(old)
        d.add(Photo(user_id=user().id, kind="hero", status="approved",
                    title="SABER ACTROS DZ - Truck & Heavy Equipment Banner",
                    image_data=image_data))
        d.commit()
        flash("تم تعيين خلفية المتجر بنجاح.")
        return redirect("/admin/photos")

    @app.post("/admin/photos/product")
    @admin_only
    def photo_product_upload():
        try:
            product_id = int(field("product_id", 20))
        except (ValueError, TypeError):
            abort(400)
        d = DB()
        p = d.get(Product, product_id)
        if not p:
            abort(404)
        try:
            image_data = transform_image(request.files.get("photo"))
        except ValueError as e:
            flash(str(e))
            return redirect("/admin/photos")
        d.add(Photo(user_id=user().id, product_id=product_id, kind="product",
                    status="approved", title=p.title, image_data=image_data))
        d.commit()
        flash("تم نشر صورة المنتج.")
        return redirect("/admin/photos")

    @app.post("/admin/photos/<int:photo_id>/moderate")
    @admin_only
    def photo_moderate(photo_id):
        d = DB()
        photo = d.get(Photo, photo_id)
        if not photo:
            abort(404)
        action = field("action", 20)
        if action == "approve" and photo.kind == "gallery" and photo.status == "pending":
            photo.status = "approved"
        elif action == "reject" and photo.kind == "gallery" and photo.status == "pending":
            photo.status = "rejected"
        elif action == "delete":
            d.delete(photo)
        else:
            abort(400)
        d.commit()
        return redirect("/admin/photos")
