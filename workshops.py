"""Admin-managed workshop directory with opt-in visitor proximity search."""
import re
from datetime import datetime, timezone
from math import isfinite

from flask import Response, abort, flash, redirect, request
from sqlalchemy import Boolean, Column, DateTime, Float, Integer, LargeBinary, String, Text, func, select

from photos import transform_image


KINDS = (
    ("truck", "شاحنات"),
    ("heavy", "معدات ثقيلة"),
    ("mixed", "شاحنات ومعدات ثقيلة"),
    ("car", "سيارات ومركبات"),
)
KIND_LABELS = dict(KINDS)
MAX_WORKSHOPS = 200


def register_workshop_model(Base):
    class Workshop(Base):
        __tablename__ = "workshop_directory"
        id = Column(Integer, primary_key=True)
        name = Column(String(160), nullable=False)
        category = Column(String(20), nullable=False, default="truck")
        address = Column(String(300), nullable=False)
        description = Column(Text, nullable=False, default="")
        phone = Column(String(40), nullable=False)
        latitude = Column(Float, nullable=False)
        longitude = Column(Float, nullable=False)
        image_data = Column(LargeBinary, nullable=False)
        visible = Column(Boolean, nullable=False, default=True)
        created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    return Workshop


PUBLIC_PAGE = """<div class="container">
<section class="catalog-intro workshop-intro">
  <h1>📍 أقرب ورشة إليك</h1>
  <p class="muted">تصفّح الورش التي أضافتها إدارة SABER ACTROS DZ، مع صورة لكل ورشة ورقم التواصل وموقعها على الخريطة.</p>
  <p class="muted">يمكنك تحديد موقعك باختيارك لترتيب الورش من الأقرب إلى الأبعد؛ أو الضغط على أي نقطة على الخريطة دون مشاركة موقع هاتفك.</p>
</section>
<section class="card" aria-label="خريطة دليل الورش">
  <div class="workshop-toolbar">
    <button id="workshop-locate" type="button" class="button">📍 أقرب ورشة إلى موقعي</button>
    <button id="workshop-reset" type="button" class="button workshop-reset">عرض جميع الورش</button>
    <label class="workshop-field">نوع الورشة
      <select id="workshop-type">
        <option value="all">جميع الورش</option>
        <option value="truck">شاحنات ومعدات ثقيلة</option>
        <option value="car">سيارات ومركبات</option>
      </select>
    </label>
    <label class="workshop-field">الاسم أو المدينة
      <input id="workshop-query" type="search" placeholder="ابحث في الورش المسجلة">
    </label>
  </div>
  <p class="workshop-note">هذه الصفحة تعرض <strong>الورش التي سجّلها مدير المتجر فقط</strong>، ولا تجلب ورشًا تلقائيًا من الإنترنت. تحديد موقعك اختياري؛ تتم مقارنة المسافة على جهازك ولا يتم حفظ إحداثياتك في قاعدة بيانات المتجر. المسافة بخط مستقيم وليست مسافة القيادة.</p>
  <p id="workshop-status" class="workshop-status" role="status" aria-live="polite">تعرض الخريطة جميع الورش المسجلة. اضغط «أقرب ورشة إلى موقعي» لترتيبها حسب قربها منك.</p>
  <div class="workshop-layout">
    <div id="workshop-map" role="region" aria-label="خريطة الورش التي أضافها مدير المتجر"></div>
    <aside class="workshop-results" aria-label="قائمة الورش المسجلة">
      <h2>الورش المسجلة <small id="workshop-count"></small></h2>
      <div id="workshop-list"><p class="muted">يتم تحميل قائمة الورش...</p></div>
    </aside>
  </div>
  <p class="workshop-attribution">خريطة: <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener noreferrer">© OpenStreetMap</a>. اضغط «الاتجاهات» لفتح مسار الورشة في خرائط Google.</p>
</section></div>
<script id="workshop-data" type="application/json">{{workshop_data|tojson}}</script>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js" defer></script>
<script src="/static/workshops.js?v=2" defer></script>
<style>
.workshop-intro{margin-top:22px}
.workshop-toolbar{display:flex;gap:12px;flex-wrap:wrap;align-items:end;margin-bottom:12px}
.workshop-toolbar>.button{min-height:44px}
.workshop-reset{background:#27445f!important;color:#e8f3fe!important}
.workshop-field{display:flex;flex-direction:column;min-width:155px;flex:1;gap:4px;font-size:.92rem}
.workshop-field select,.workshop-field input{margin:0;min-height:44px;max-width:100%}
.workshop-note,.workshop-attribution{font-size:.85rem;color:#b8cce0;line-height:1.8}
.workshop-status{font-size:.92rem;color:#cee7f5;margin:12px 0;min-height:24px}
.workshop-status.error{color:#ffb6b6}
.workshop-layout{display:grid;grid-template-columns:minmax(0,1fr) 350px;gap:15px;align-items:start}
#workshop-map{height:540px;min-height:360px;border:1px solid #3b566e;border-radius:13px;overflow:hidden;background:#22364b;z-index:0}
#workshop-map .leaflet-container{font-family:system-ui,Arial}
#workshop-map .leaflet-popup-content{color:#172436;line-height:1.55}
.workshop-results{border:1px solid #395069;border-radius:13px;background:#101d2e;padding:16px;min-height:250px;max-height:540px;overflow-y:auto}
.workshop-results h2{font-size:1.2rem;margin:0 0 12px}
.workshop-result{border:1px solid #314b65;border-radius:11px;padding:12px;margin-bottom:12px;background:#182c40}
.workshop-result.nearest{border-color:#e6c26d}
.workshop-result-image{width:100%;height:160px;object-fit:cover;border-radius:9px;margin-bottom:9px}
.workshop-result strong{display:block;color:#ffcf70;overflow-wrap:anywhere;font-size:1rem}
.workshop-result small{display:block;color:#bbd0df;margin:5px 0}
.workshop-result .workshop-actions{display:flex;gap:9px;flex-wrap:wrap;margin-top:12px;align-items:center}
.workshop-result .workshop-actions a,.workshop-result .workshop-actions button{padding:7px 11px;background:#224e67;border:1px solid #3c6a84;color:#eaf8ff;text-decoration:none;border-radius:8px;font:inherit;font-size:.9rem;cursor:pointer}
.workshop-result .workshop-actions a:hover,.workshop-result .workshop-actions button:hover{background:#2e667f}
.workshop-result p{margin:6px 0;white-space:pre-wrap;overflow-wrap:anywhere}
.workshop-result-phone{direction:ltr;unicode-bidi:isolate;display:inline-block}
@media(max-width:900px){.workshop-layout{grid-template-columns:1fr}#workshop-map{height:410px}.workshop-results{max-height:none}}
@media(max-width:550px){.workshop-toolbar>.button{flex:1 1 auto}.workshop-field{min-width:125px}#workshop-map{height:350px}}
</style>"""

ADMIN_PAGE = """<div class="container">
<h1>إدارة دليل الورش</h1>
<p class="muted">أنت وحدك تضيف الورش وتتحكم فيما يظهر للزوار. لكل ورشة: الاسم، الصورة، رقم التواصل، العنوان، والموقع على الخريطة.</p>
<p><a href="/admin">لوحة الإدارة</a> · <a href="/workshops">مشاهدة دليل الورش</a></p>
<section class="card">
<h2>{{"تعديل بيانات ورشة" if editing else "إضافة ورشة جديدة"}}</h2>
{% if editing %}<p>تعديل: <strong>{{editing.name}}</strong> · <a href="/admin/workshops">إلغاء التعديل</a></p>{% endif %}
<form method="post" enctype="multipart/form-data" action="{{'/admin/workshops/' ~ editing.id ~ '/update' if editing else '/admin/workshops/new'}}">
<input type="hidden" name="csrf" value="{{csrf}}">
<label>اسم الورشة <input name="name" maxlength="160" required value="{{editing.name if editing else ''}}" placeholder="مثال: ورشة صيانة شاحنات MAN"></label>
<label>نوع الورشة
<select name="category" required>
{% for value,label in kinds %}<option value="{{value}}" {% if (editing.category if editing else 'truck')==value %}selected{% endif %}>{{label}}</option>{% endfor %}
</select></label>
<label>رقم التواصل <input type="tel" name="phone" maxlength="40" required inputmode="tel" dir="ltr" value="{{editing.phone if editing else ''}}" placeholder="+9665... أو 00213..."></label>
<label>العنوان والمدينة <input name="address" maxlength="300" required value="{{editing.address if editing else ''}}" placeholder="المدينة، الحي، الطريق"></label>
<label>الخدمات والتخصصات (اختياري) <textarea name="description" maxlength="1200" rows="3">{{editing.description if editing else ''}}</textarea></label>
<label>صورة الورشة {{'(اختيارية لاستبدال الصورة)' if editing else '(مطلوبة)'}}
<input name="photo" type="file" accept="image/jpeg,image/png,image/webp" {% if not editing %}required{% endif %}></label>
{% if editing %}<p><img src="/admin/workshops/{{editing.id}}/photo" loading="lazy" alt="صورة الورشة الحالية" class="admin-workshop-thumbnail"></p>{% endif %}
<p class="muted">صور JPG أو PNG أو WebP، بحجم أقصى 4 ميغابايت. تتم إزالة بيانات الصورة الوصفية أثناء المعالجة.</p>
<p><b>حدد موقع الورشة:</b> اضغط على الخريطة أدناه، أو أدخل خط العرض وخط الطول يدويًا من خرائط Google.</p>
<div class="admin-map-actions">
<button type="button" class="button" data-place="sa">🇸🇦 عرض السعودية</button>
<button type="button" class="button" data-place="dz">🇩🇿 عرض الجزائر</button>
</div>
<div id="workshop-admin-map" aria-label="اختيار موقع الورشة على الخريطة"></div>
<div class="admin-coordinates">
<label>خط العرض (Latitude) <input id="workshop-latitude" name="latitude" required type="number" step="any" min="-90" max="90" inputmode="decimal" dir="ltr" value="{{editing.latitude if editing else ''}}" placeholder="24.7136"></label>
<label>خط الطول (Longitude) <input id="workshop-longitude" name="longitude" required type="number" step="any" min="-180" max="180" inputmode="decimal" dir="ltr" value="{{editing.longitude if editing else ''}}" placeholder="46.6753"></label>
</div>
<label class="admin-workshop-check"><input name="visible" type="checkbox" value="yes" {% if not editing or editing.visible %}checked{% endif %}> عرض الورشة للزوار على الخريطة</label>
<label class="admin-workshop-check"><input name="permission" type="checkbox" value="yes" required> أؤكد أن لدي إذن نشر الصورة واسم الورشة ورقم التواصل والعنوان.</label>
<button type="submit">{{"حفظ التعديلات" if editing else "إضافة الورشة"}}</button>
</form></section>
<section>
<h2>الورش المضافة ({{shops|length}})</h2>
<div class="grid">
{% for w in shops %}
<div class="card">
<img src="/admin/workshops/{{w.id}}/photo" class="admin-workshop-thumbnail" loading="lazy" alt="{{w.name}}">
<h3>{{w.name}}</h3><p>{{w.address}}</p>
<p><bdi dir="ltr">{{w.phone}}</bdi> · {{kind_labels.get(w.category,'ورشة')}}</p>
<p class="muted">{{'منشورة' if w.visible else 'مخفية'}}</p>
<a class="button" href="/admin/workshops/{{w.id}}/edit">تعديل</a>
<form method="post" action="/admin/workshops/{{w.id}}/toggle" style="display:inline">
<input type="hidden" name="csrf" value="{{csrf}}">
<button type="submit">{{'إخفاء' if w.visible else 'نشر'}}</button></form>
<form method="post" action="/admin/workshops/{{w.id}}/delete" style="display:inline" onsubmit="return confirm('هل أنت متأكد من حذف بيانات هذه الورشة وصورتها؟')">
<input type="hidden" name="csrf" value="{{csrf}}"><button type="submit">حذف</button></form>
</div>
{% else %}<div class="card">لم تضف أي ورشة بعد. ابدأ بإضافة الأولى من النموذج أعلاه.</div>{% endfor %}
</div></section>
</div>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js" defer></script>
<script src="/static/admin-workshops.js?v=1" defer></script>
<style>
#workshop-admin-map{height:340px;background:#20344b;border-radius:12px;overflow:hidden;border:1px solid #43657b;z-index:0;margin:10px 0}
.admin-map-actions{display:flex;gap:10px;flex-wrap:wrap;margin:12px 0}
.admin-map-actions .button{padding:8px 14px}
.admin-coordinates{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.admin-workshop-thumbnail{width:100%;height:180px;max-width:350px;object-fit:cover;border-radius:10px}
.admin-workshop-check{display:flex;gap:9px;align-items:center;margin:10px 0}
.admin-workshop-check input{width:auto}
@media(max-width:560px){.admin-coordinates{grid-template-columns:1fr}}
</style>"""


def _validate_input():
    name = request.form.get("name", "").strip()[:160]
    category = request.form.get("category", "")
    phone = request.form.get("phone", "").strip()[:40]
    address = request.form.get("address", "").strip()[:300]
    description = request.form.get("description", "").strip()[:1200]
    if not name or not address or category not in KIND_LABELS:
        raise ValueError("الرجاء كتابة اسم الورشة وعنوانها واختيار نوعها.")
    # Accept international and national phone numbers, without forcing one country.
    sanitized = re.sub(r"[\s().+\-]", "", phone)
    if not sanitized.isascii() or not re.fullmatch(r"[0-9]{7,18}", sanitized):
        raise ValueError("رقم التواصل غير صالح. اكتب رقمًا مع رمز الدولة إن كان دوليًا.")
    try:
        latitude = float(request.form.get("latitude", ""))
        longitude = float(request.form.get("longitude", ""))
    except ValueError as exc:
        raise ValueError("يجب تحديد مكان الورشة على الخريطة.") from exc
    if not (isfinite(latitude) and isfinite(longitude) and -90 <= latitude <= 90 and -180 <= longitude <= 180):
        raise ValueError("إحداثيات الورشة غير صحيحة.")
    if request.form.get("permission") != "yes":
        raise ValueError("يلزم تأكيد حق نشر صورة الورشة ومعلومات التواصل.")
    return {
        "name": name, "category": category, "phone": phone, "address": address,
        "description": description, "latitude": latitude, "longitude": longitude,
        "visible": request.form.get("visible") == "yes",
    }


def setup_workshops_routes(app, Workshop, DB, page, admin_only):
    @app.get("/workshops")
    def workshops():
        d = DB()
        values = d.execute(
            select(Workshop.id, Workshop.name, Workshop.category, Workshop.address,
                   Workshop.description, Workshop.phone, Workshop.latitude,
                   Workshop.longitude)
            .where(Workshop.visible == True).order_by(Workshop.id.desc()).limit(MAX_WORKSHOPS)
        ).all()
        entries = [
            {
                "id": w.id, "name": w.name, "category": w.category,
                "address": w.address, "description": w.description, "phone": w.phone,
                "latitude": w.latitude, "longitude": w.longitude,
            }
            for w in values
        ]
        return page(PUBLIC_PAGE, title="أقرب ورشة | SABER ACTROS DZ", workshop_data=entries)

    @app.get("/workshops/<int:workshop_id>/photo")
    def public_workshop_photo(workshop_id):
        d = DB()
        photo = d.execute(
            select(Workshop.image_data).where(
                Workshop.id == workshop_id, Workshop.visible == True
            )
        ).scalar_one_or_none()
        if not photo:
            abort(404)
        return Response(photo, mimetype="image/webp", headers={
            "Cache-Control": "public, max-age=300", "X-Content-Type-Options": "nosniff"
        })

    @app.get("/admin/workshops/<int:workshop_id>/photo")
    @admin_only
    def admin_workshop_photo(workshop_id):
        d = DB()
        photo = d.execute(
            select(Workshop.image_data).where(Workshop.id == workshop_id)
        ).scalar_one_or_none()
        if not photo:
            abort(404)
        return Response(photo, mimetype="image/webp", headers={
            "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"
        })

    def admin_page(editing=None):
        all_shops = DB().execute(
            select(Workshop.id, Workshop.name, Workshop.category, Workshop.address,
                   Workshop.phone, Workshop.visible)
            .order_by(Workshop.id.desc()).limit(MAX_WORKSHOPS)
        ).all()
        return page(
            ADMIN_PAGE, title="إدارة الورش | SABER ACTROS DZ",
            shops=all_shops, editing=editing, kinds=KINDS, kind_labels=KIND_LABELS
        )

    @app.get("/admin/workshops")
    @admin_only
    def admin_workshops():
        return admin_page()

    @app.get("/admin/workshops/<int:workshop_id>/edit")
    @admin_only
    def edit_workshop(workshop_id):
        current = DB().get(Workshop, workshop_id)
        if current is None:
            abort(404)
        return admin_page(current)

    @app.post("/admin/workshops/new")
    @admin_only
    def create_workshop():
        d = DB()
        if d.scalar(select(func.count()).select_from(Workshop)) >= MAX_WORKSHOPS:
            flash("تم بلوغ الحد الأقصى للورش. احذف ورشة قديمة أولًا.")
            return redirect("/admin/workshops")
        try:
            values = _validate_input()
            photo = transform_image(request.files.get("photo"))
        except ValueError as err:
            flash(str(err))
            return redirect("/admin/workshops")
        d.add(Workshop(**values, image_data=photo))
        d.commit()
        flash("تم حفظ الورشة وصورتها وإضافتها إلى الدليل.")
        return redirect("/admin/workshops")

    @app.post("/admin/workshops/<int:workshop_id>/update")
    @admin_only
    def update_workshop(workshop_id):
        d = DB()
        w = d.get(Workshop, workshop_id)
        if w is None:
            abort(404)
        try:
            values = _validate_input()
            new_file = request.files.get("photo")
            image = transform_image(new_file) if new_file and new_file.filename else None
        except ValueError as err:
            flash(str(err))
            return redirect("/admin/workshops/" + str(workshop_id) + "/edit")
        for key, value in values.items():
            setattr(w, key, value)
        if image is not None:
            w.image_data = image
        d.commit()
        flash("تم حفظ تعديلات الورشة.")
        return redirect("/admin/workshops")

    @app.post("/admin/workshops/<int:workshop_id>/toggle")
    @admin_only
    def toggle_workshop(workshop_id):
        d = DB()
        w = d.get(Workshop, workshop_id)
        if w is None:
            abort(404)
        w.visible = not w.visible
        d.commit()
        flash("تم تحديث ظهور الورشة.")
        return redirect("/admin/workshops")

    @app.post("/admin/workshops/<int:workshop_id>/delete")
    @admin_only
    def delete_workshop(workshop_id):
        d = DB()
        w = d.get(Workshop, workshop_id)
        if w is None:
            abort(404)
        d.delete(w)
        d.commit()
        flash("تم حذف الورشة وصورتها من الدليل.")
        return redirect("/admin/workshops")
