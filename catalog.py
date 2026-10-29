"""Catalog pages and administration for the SABER ACTROS DZ storefront.

Products reuse the shop's existing database, images and manual-payment orders.
Extra specifications and PDF catalog files live in separate tables, so existing
product/order records need no schema migration.
"""
from datetime import datetime, timezone
from io import BytesIO
import fitz
from sqlalchemy import Column, Integer, String, Text, LargeBinary, DateTime, Boolean, ForeignKey, select, func
from flask import abort, flash, redirect, request, Response

CATEGORIES = (
    ("diagnostic", "برامج وأجهزة التشخيص"),
    ("programming", "البرمجة والتراخيص"),
    ("parts", "كتالوجات قطع الغيار"),
    ("technical", "المخططات والمراجع الفنية"),
    ("service", "الخدمات والإصلاح"),
    ("training", "الدورات والتدريب"),
)
CATEGORY_LABELS = dict(CATEGORIES)
MAX_PDF_BYTES = 4 * 1024 * 1024


def register_catalog_models(Base):
    class CatalogMeta(Base):
        __tablename__ = "catalog_product_meta"
        id = Column(Integer, primary_key=True)
        product_id = Column(Integer, ForeignKey("products.id"), nullable=False, unique=True)
        category = Column(String(30), nullable=False, default="diagnostic")
        specifications = Column(Text, default="", nullable=False)

    class CatalogDocument(Base):
        __tablename__ = "catalog_documents"
        id = Column(Integer, primary_key=True)
        title = Column(String(160), nullable=False)
        brand = Column(String(80), nullable=False, default="")
        category = Column(String(30), nullable=False, default="parts")
        description = Column(Text, default="", nullable=False)
        pdf_data = Column(LargeBinary, nullable=False)
        uploaded_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
        visible = Column(Boolean, nullable=False, default=True)

    return CatalogMeta, CatalogDocument


def default_category(p):
    slug = (p.slug or "").casefold()
    brand = (p.brand or "").casefold()
    if "training" in slug or "academy" in brand:
        return "training"
    if "repair" in slug or "support" in slug:
        return "service"
    if "parts" in slug or "catalog" in slug:
        return "parts"
    if "xentry" in slug or "tech-tool" in slug or "man-cats" in slug:
        return "diagnostic"
    if "iveco-easy" in slug or "jaltest" in slug:
        return "diagnostic"
    return "diagnostic"


def setup_catalog_routes(app, Meta, Document, DB, Product, Photo, user, page, field, admin_only):
    def current_meta_map(d):
        return {m.product_id: m for m in d.scalars(select(Meta)).all()}

    def current_photo_map(d):
        images = d.scalars(select(Photo).where(
            Photo.kind == "product", Photo.status == "approved"
        ).order_by(Photo.id.asc())).all()
        return {photo.product_id: photo.id for photo in images}

    def category_for(product, meta_map):
        meta = meta_map.get(product.id)
        return meta.category if meta else default_category(product)

    def found(*values, q):
        return not q or any(q in str(v or "").casefold() for v in values)

    @app.get("/catalog")
    def catalog():
        d = DB()
        q = request.args.get("q", "").strip()[:80]
        brand = request.args.get("brand", "").strip()[:80]
        category = request.args.get("category", "").strip()[:30]
        if category not in CATEGORY_LABELS:
            category = ""
        q_lower = q.casefold()

        all_products = d.scalars(select(Product).where(Product.visible == True).order_by(Product.id.desc()).limit(300)).all()
        meta_map = current_meta_map(d)
        photo_map = current_photo_map(d)
        brands = sorted(set(p.brand for p in all_products if p.brand), key=str.casefold)
        filtered_products = []
        for product in all_products:
            cat = category_for(product, meta_map)
            meta = meta_map.get(product.id)
            if brand and product.brand != brand:
                continue
            if category and cat != category:
                continue
            if not found(product.title, product.brand, product.description,
                         meta.specifications if meta else "", q=q_lower):
                continue
            filtered_products.append({
                "p": product, "category": CATEGORY_LABELS.get(cat, "برامج وخدمات"),
                "photo_id": photo_map.get(product.id)
            })
        preview_docs = d.scalars(select(Document).where(
            Document.visible == True
        ).order_by(Document.id.desc()).limit(40)).all()
        return page("""<div class="container catalog-page">
<section class="catalog-intro">
<h1>كتالوج</h1>
<p class="muted">برامج فحص وبرمجة الشاحنات والخدمات التقنية حسب العلامة والشركة.</p>
<p><strong>معاينة مجانية:</strong> يستطيع كل زائر رؤية أول صورتين (أول صفحتين) من كل كتالوج PDF دون دفع أو تسجيل دخول. بقية الصفحات لا تُعرض إلا بعد التواصل وتأكيد الدفع من الإدارة.</p>
<p><a class="button" href="/catalog/pdfs">عرض جميع كتالوجات PDF وقطع الغيار</a></p>
<form method="get" action="/catalog" class="catalog-filters">
<label>ابحث عن برنامج أو شركة أو خدمة
<input type="search" name="q" value="{{q}}" maxlength="80" placeholder="مثال: MAN، IVECO، Xentry"></label>
<label>الشركة أو العلامة
<select name="brand"><option value="">جميع العلامات</option>
{% for b in brands %}<option value="{{b}}" {% if selected_brand==b %}selected{% endif %}>{{b}}</option>{% endfor %}
</select></label>
<label>نوع الكتالوج
<select name="category"><option value="">جميع الأقسام</option>
{% for code,label in categories %}<option value="{{code}}" {% if selected_category==code %}selected{% endif %}>{{label}}</option>{% endfor %}
</select></label>
<button type="submit">بحث وتصفية</button><a href="/catalog" class="catalog-reset">عرض الكل</a>
</form></section>
<section id="pdf-catalogs"><h2>معاينة كتالوجات PDF مجانًا <small>({{preview_docs|length}})</small></h2>
<p class="muted">تظهر هنا أول صورتين من كل ملف فقط؛ باقي الملف محمي حتى تأكيد الدفع يدويًا.</p>
<div class="grid">
{% for doc in preview_docs %}
<article class="card catalog-card">
<small>{{doc.brand}}</small><h3>{{doc.title}}</h3><p>{{doc.description}}</p>
<a href="/catalog/pdf/{{doc.id}}/preview" aria-label="معاينة أول صفحتين من {{doc.title}}">
<div style="display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px">
<img src="/catalog/pdf/{{doc.id}}/preview/0" loading="lazy" alt="الصفحة الأولى من {{doc.title}}" style="width:100%;aspect-ratio:3/4;object-fit:contain;background:#0c1a2e;border-radius:9px">
<img src="/catalog/pdf/{{doc.id}}/preview/1" loading="lazy" onerror="this.style.display='none'" alt="الصفحة الثانية من {{doc.title}}" style="width:100%;aspect-ratio:3/4;object-fit:contain;background:#0c1a2e;border-radius:9px">
</div></a>
<p class="muted">صورتان مجانًا · باقي الصفحات بعد الدفع</p>
<a class="button" href="/catalog/pdf/{{doc.id}}/preview">معاينة مجانية</a>
</article>
{% else %}<p class="card">لا توجد كتالوجات PDF منشورة بعد. يمكن للإدارة إضافتها من لوحة إدارة الكتالوج.</p>{% endfor %}
</div></section>
<section><h2>البرامج والخدمات <small>({{items|length}})</small></h2>
<div class="grid">
{% for item in items %}
{% set p=item.p %}
<article class="card catalog-card">
{% if item.photo_id %}<a href="/catalog/product/{{p.slug}}"><img class="product-image" src="/photos/file/{{item.photo_id}}" loading="lazy" alt="صورة {{p.title}}"></a>{% else %}
<a class="catalog-no-photo" href="/catalog/product/{{p.slug}}">SABER ACTROS DZ</a>{% endif %}
<small>{{item.category}} · {{p.brand}}</small>
<h3><a href="/catalog/product/{{p.slug}}">{{p.title}}</a></h3>
<p>{{p.description}}</p>
<div class="catalog-actions">
<a class="button" href="/catalog/product/{{p.slug}}">تفاصيل الكتالوج</a>
<a class="button" href="/order/{{p.slug}}">اطلب الآن</a>
<button type="button" class="copy-link share-link" data-path="/catalog/product/{{p.slug}}" data-title="{{p.title}} | SABER ACTROS DZ" title="مشاركة الرابط" aria-label="مشاركة الرابط" onclick="shareStoreLink(this)"><svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/><path d="M8.6 13.5l6.8 4M15.4 6.5l-6.8 4"/></svg></button>
</div></article>
{% else %}<p class="card">لا توجد برامج مطابقة للبحث.</p>{% endfor %}
</div></section>
</div>""", title="كتالوج | SABER ACTROS DZ",
            items=filtered_products, preview_docs=preview_docs, brands=brands,
            categories=CATEGORIES, labels=CATEGORY_LABELS, q=q,
            selected_brand=brand, selected_category=category)

    @app.get("/catalog/pdfs")
    def catalog_pdfs():
        """Separate PDF/parts catalog, preserving old download links."""
        d=DB()
        q=request.args.get("q","").strip()[:80]
        brand=request.args.get("brand","").strip()[:80]
        category=request.args.get("category","").strip()[:30]
        if category not in CATEGORY_LABELS:
            category=""
        all_docs=d.scalars(select(Document).where(Document.visible==True).order_by(Document.id.desc()).limit(100)).all()
        brands=sorted(set(x.brand for x in all_docs if x.brand),key=str.casefold)
        result=[
            doc for doc in all_docs
            if (not brand or doc.brand==brand)
            and (not category or doc.category==category)
            and found(doc.title, doc.brand, doc.description, q=q.casefold())
        ]
        return page("""<div class="container catalog-page">
<section class="catalog-intro">
<h1>كتالوجات PDF وقطع الغيار</h1>
<p class="muted">الكتالوجات والمراجع الفنية المرفوعة من إدارة المتجر، مستقلة عن كتالوج.</p>
<p><a href="/catalog">العودة إلى كتالوج</a></p>
<form method="get" action="/catalog/pdfs" class="catalog-filters">
<label>ابحث عن كتالوج أو قطعة غيار
<input name="q" type="search" value="{{q}}" maxlength="80" placeholder="مثال: MAN، IVECO"></label>
<label>العلامة أو الشركة
<select name="brand"><option value="">جميع العلامات</option>
{% for b in brands %}<option value="{{b}}" {% if b==selected_brand %}selected{% endif %}>{{b}}</option>{% endfor %}
</select></label>
<label>نوع الملف
<select name="category"><option value="">جميع الأقسام</option>
{% for code,label in categories %}<option value="{{code}}" {% if code==selected_category %}selected{% endif %}>{{label}}</option>{% endfor %}
</select></label>
<button type="submit">بحث وتصفية</button><a class="catalog-reset" href="/catalog/pdfs">عرض الكل</a>
</form></section>
<section><h2>ملفات PDF <small>({{docs|length}})</small></h2>
<div class="grid">
{% for doc in docs %}<article class="card catalog-card">
<small>{{labels.get(doc.category,"كتالوج")}} · {{doc.brand}}</small>
<h3>{{doc.title}}</h3><p>{{doc.description}}</p>
<a href="/catalog/pdf/{{doc.id}}/preview" aria-label="معاينة مجانية للكتالوج">
<div style="display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px">
<img src="/catalog/pdf/{{doc.id}}/preview/0" loading="lazy" alt="صورة الصفحة الأولى" style="width:100%;aspect-ratio:3/4;object-fit:contain;background:#0c1a2e;border-radius:9px">
<img src="/catalog/pdf/{{doc.id}}/preview/1" loading="lazy" onerror="this.style.display='none'" alt="صورة الصفحة الثانية" style="width:100%;aspect-ratio:3/4;object-fit:contain;background:#0c1a2e;border-radius:9px">
</div></a>
<p class="muted">🔒 صفحتان مجانًا، وبقية الملف بعد التواصل وتأكيد الدفع يدويًا.</p>
<div class="catalog-actions">
<a class="button" href="/catalog/pdf/{{doc.id}}/preview">عرض أول صورتين مجانًا</a>
<button type="button" class="copy-link share-link" data-path="/catalog/pdf/{{doc.id}}" data-title="{{doc.title}} | SABER ACTROS DZ" title="مشاركة الرابط" aria-label="مشاركة الرابط" onclick="shareStoreLink(this)"><svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/><path d="M8.6 13.5l6.8 4M15.4 6.5l-6.8 4"/></svg></button>
</div></article>
{% else %}<p class="card">لا توجد كتالوجات PDF منشورة حاليًا.</p>{% endfor %}
</div></section></div>""",title="كتالوجات PDF وقطع الغيار | SABER ACTROS DZ",
            docs=result,labels=CATEGORY_LABELS,categories=CATEGORIES,
            brands=brands,q=q,selected_brand=brand,selected_category=category)

    @app.get("/catalog/product/<slug>")
    def catalog_product(slug):
        d=DB()
        p=d.scalar(select(Product).where(Product.slug==slug, Product.visible==True))
        if not p:
            abort(404)
        meta=d.scalar(select(Meta).where(Meta.product_id==p.id))
        photo_ids=d.scalars(select(Photo.id).where(
            Photo.kind=="product",Photo.product_id==p.id,Photo.status=="approved"
        ).order_by(Photo.id.desc()).limit(2)).all()
        cat=meta.category if meta else default_category(p)
        return page("""<div class="container">
<section class="card catalog-detail">
<p><a href="/catalog">كتالوج</a> / {{p.title}}</p>
{% if photo_ids %}<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px">
{% for photo_id in photo_ids %}<img class="catalog-detail-image" src="/photos/file/{{photo_id}}" alt="صورة معاينة مجانية من {{p.title}}" loading="lazy">{% endfor %}
</div><p class="muted">معاينة أول صورتين مجانًا. للحصول على المحتوى الكامل تواصل مع الإدارة لتأكيد الدفع.</p>{% endif %}
<small>{{category_name}} · {{p.brand}}</small><h1>{{p.title}}</h1><p>{{p.description}}</p>
{% if specs %}<h2>المواصفات والتفاصيل</h2><p class="catalog-specs">{{specs}}</p>{% endif %}
<p class="muted">للحصول على السعر ومعلومات الدفع، أرسل الطلب أولًا. تأكيد الدفع من المدير فقط.</p>
<div class="catalog-actions"><a class="button" href="/order/{{p.slug}}">طلب البرنامج أو الخدمة</a>
<button type="button" class="copy-link share-link" data-path="/catalog/product/{{p.slug}}" data-title="{{p.title}} | SABER ACTROS DZ" title="مشاركة الرابط" aria-label="مشاركة الرابط" onclick="shareStoreLink(this)"><svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/><path d="M8.6 13.5l6.8 4M15.4 6.5l-6.8 4"/></svg></button></div>
</section></div>""",title=p.title+" | كتالوج SABER ACTROS DZ",
           p=p,photo_ids=photo_ids,category_name=CATEGORY_LABELS.get(cat,cat),
           specs=meta.specifications if meta else "")

    @app.get("/catalog/pdf/<int:doc_id>/preview")
    def preview_catalog_pdf(doc_id):
        doc=DB().get(Document,doc_id)
        if not doc or not doc.visible:
            abort(404)
        try:
            with fitz.open(stream=bytes(doc.pdf_data), filetype="pdf") as pdf:
                preview_count = min(2, len(pdf))
        except (ValueError, RuntimeError, fitz.FileDataError):
            abort(404)
        return page("""<div class="container"><section class="card catalog-detail">
<h1>{{doc.title}}</h1><p>{{doc.description}}</p>
<p>معاينة مجانية لأول صورتين فقط من الكتالوج دون دفع أو تسجيل دخول.</p>
{% for i in range(preview_count) %}
<img src="/catalog/pdf/{{doc.id}}/preview/{{i}}" alt="معاينة الصفحة {{i+1}}" style="width:100%;height:auto;margin:12px 0" loading="lazy">
{% endfor %}
<p>🔒 بقية الصفحات محمية، ويُسلَّم الكتالوج الكامل بعد التواصل والدفع وموافقة الإدارة يدويًا.</p>
<a class="button" href="https://wa.me/{{whatsapp}}?text={{('أريد شراء الكتالوج '+doc.title+' رقم '+doc.id|string)|urlencode}}" target="_blank" rel="noopener">اطلب الكتالوج الكامل</a>
</section></div>""",doc=doc,preview_count=preview_count)

    @app.get("/catalog/pdf/<int:doc_id>/preview/<int:page_number>")
    def preview_catalog_page(doc_id,page_number):
        if page_number not in (0,1):
            abort(404)
        doc=DB().get(Document,doc_id)
        if not doc or not doc.visible:
            abort(404)
        try:
            with fitz.open(stream=bytes(doc.pdf_data),filetype="pdf") as pdf:
                if page_number>=len(pdf):
                    abort(404)
                image=pdf[page_number].get_pixmap(matrix=fitz.Matrix(1.3,1.3),alpha=False)
                from PIL import Image
                img=Image.frombytes("RGB",[image.width,image.height],image.samples)
                img.thumbnail((1200,1600))
                output=BytesIO()
                img.save(output,format="WEBP",quality=72)
                data=output.getvalue()
        except (ValueError,RuntimeError):
            abort(404)
        return Response(data,mimetype="image/webp",headers={"Cache-Control":"public, max-age=300","X-Content-Type-Options":"nosniff"})

    @app.get("/catalog/pdf/<int:doc_id>")
    def download_catalog_pdf(doc_id):
        current=user()
        if not current or not current.admin:
            abort(403,description="الكتالوج الكامل محمي. تواصل مع الإدارة لشرائه.")
        doc=DB().get(Document,doc_id)
        if not doc:
            abort(404)
        return Response(bytes(doc.pdf_data),mimetype="application/pdf",headers={
            "Content-Disposition":f'attachment; filename="SABER-CATALOG-{doc.id}.pdf"',
            "Cache-Control":"private, no-store","X-Content-Type-Options":"nosniff"})

    @app.get("/admin/catalog")
    @admin_only
    def catalog_admin():
        d=DB()
        products=d.scalars(select(Product).order_by(Product.id.desc()).limit(300)).all()
        meta_map=current_meta_map(d)
        photo_map=current_photo_map(d)
        docs=d.scalars(select(Document).order_by(Document.id.desc()).limit(100)).all()
        rows=[{
            "p":p, "category":category_for(p, meta_map),
            "specs":meta_map[p.id].specifications if p.id in meta_map else "",
            "photo_id":photo_map.get(p.id)
        } for p in products]
        return page("""<div class="container">
<h1>إدارة الكتالوج</h1>
<p><a href="/admin">لوحة الإدارة</a> · <a href="/catalog">كتالوج</a> · <a href="/catalog/pdfs">كتالوجات PDF</a></p>
<section class="card"><h2>إضافة برنامج أو خدمة إلى الكتالوج</h2>
<p class="muted">البرامج التي تضيفها هنا تظهر أيضًا في المتجر.</p>
<form method="post" action="/admin/catalog/new">
<input type="hidden" name="csrf" value="{{csrf}}">
<label>اسم البرنامج أو الخدمة<input name="title" required maxlength="150"></label>
<label>العلامة أو الشركة<input name="brand" required maxlength="80"></label>
<label>القسم<select name="category">{% for code,label in categories %}
<option value="{{code}}">{{label}}</option>{% endfor %}</select></label>
<label>وصف مختصر<textarea name="description" maxlength="2000" required></textarea></label>
<label>مواصفات أو ملاحظات إضافية<textarea name="specifications" maxlength="3000"></textarea></label>
<button type="submit">إضافة إلى الكتالوج والمتجر</button>
</form></section>
<section><h2>تعديل المنتجات وتصنيفها</h2><div class="grid">
{% for item in items %}{% set p=item.p %}
<div class="card">
{% if item.photo_id %}<img class="product-image" src="/photos/file/{{item.photo_id}}" loading="lazy" alt="{{p.title}}">{% endif %}
<form method="post" action="/admin/catalog/product/{{p.id}}">
<input type="hidden" name="csrf" value="{{csrf}}">
<label>اسم البرنامج<input name="title" value="{{p.title}}" required maxlength="150"></label>
<label>الشركة<input name="brand" value="{{p.brand}}" required maxlength="80"></label>
<label>القسم<select name="category">{% for code,label in categories %}
<option value="{{code}}" {% if code==item.category %}selected{% endif %}>{{label}}</option>
{% endfor %}</select></label>
<label>الوصف<textarea name="description" required maxlength="2000">{{p.description}}</textarea></label>
<label>المواصفات<textarea name="specifications" maxlength="3000">{{item.specs}}</textarea></label>
<label><input type="checkbox" name="visible" value="yes" {% if p.visible %}checked{% endif %}> ظاهر في المتجر والكتالوج</label>
<button type="submit">حفظ التعديلات</button>
</form>
<p><a href="/catalog/product/{{p.slug}}">عرض المنتج</a> ·
<a href="/admin/photos">إدارة صور المنتجات</a></p>
</div>{% endfor %}</div></section>
<section class="card"><h2>رفع كتالوج PDF</h2>
<p class="muted">ملفات PDF بحجم 4 ميغابايت كحد أقصى. تظهر أول صورتين من كل PDF على صفحة الكتالوج الرئيسية مجانًا. بقية الصفحات محمية ولا يُسلَّم الملف الكامل إلا بعد تأكيدك الدفع يدويًا.</p>
<form method="post" action="/admin/catalog/pdf" enctype="multipart/form-data">
<input type="hidden" name="csrf" value="{{csrf}}">
<label>اسم الكتالوج<input name="title" maxlength="160" required></label>
<label>العلامة أو الشركة<input name="brand" maxlength="80" required></label>
<label>القسم<select name="category">{% for code,label in categories %}
<option value="{{code}}" {% if code=="parts" %}selected{% endif %}>{{label}}</option>{% endfor %}</select></label>
<label>الوصف<textarea name="description" maxlength="1000"></textarea></label>
<label>ملف PDF<input type="file" name="catalog_file" accept="application/pdf,.pdf" required></label>
<button type="submit">رفع ملف الكتالوج</button>
</form></section>
<section><h2>ملفات PDF المنشورة</h2><div class="grid">
{% for doc in docs %}<div class="card">
<h3>{{doc.title}}</h3><p>{{doc.brand}} · {{'ظاهر' if doc.visible else 'مخفي'}}</p>
<a href="/catalog/pdf/{{doc.id}}">تنزيل / فحص الملف</a>
<form method="post" action="/admin/catalog/pdf/{{doc.id}}/toggle">
<input type="hidden" name="csrf" value="{{csrf}}"><button>إظهار / إخفاء</button></form>
<form method="post" action="/admin/catalog/pdf/{{doc.id}}/delete" onsubmit="return confirm('حذف ملف الكتالوج نهائيًا؟')">
<input type="hidden" name="csrf" value="{{csrf}}"><button>حذف الملف</button></form>
</div>{% else %}<p>لا توجد ملفات بعد.</p>{% endfor %}</div></section>
</div>""",title="إدارة الكتالوج | SABER ACTROS DZ",
            categories=CATEGORIES,items=rows,docs=docs)

    @app.post("/admin/catalog/new")
    @admin_only
    def catalog_add_product():
        title=field("title",150)
        brand=field("brand",80)
        description=field("description",2000)
        cat=field("category",30)
        if not title or not brand or not description or cat not in CATEGORY_LABELS:
            abort(400)
        d=DB()
        import secrets
        product=Product(slug="catalog-"+secrets.token_hex(6),title=title,
                        brand=brand,description=description,visible=True)
        d.add(product)
        d.flush()
        d.add(Meta(product_id=product.id,category=cat,
                   specifications=field("specifications",3000)))
        d.commit()
        flash("تمت إضافة البرنامج إلى المتجر والكتالوج.")
        return redirect("/admin/catalog")

    @app.post("/admin/catalog/product/<int:product_id>")
    @admin_only
    def catalog_edit_product(product_id):
        d=DB()
        p=d.get(Product,product_id)
        if not p:
            abort(404)
        cat=field("category",30)
        title=field("title",150)
        brand=field("brand",80)
        description=field("description",2000)
        if cat not in CATEGORY_LABELS or not title or not brand or not description:
            abort(400)
        p.title=title
        p.brand=brand
        p.description=description
        p.visible=field("visible",8)=="yes"
        meta=d.scalar(select(Meta).where(Meta.product_id==p.id))
        if not meta:
            meta=Meta(product_id=p.id)
            d.add(meta)
        meta.category=cat
        meta.specifications=field("specifications",3000)
        d.commit()
        flash("تم تحديث بيانات الكتالوج.")
        return redirect("/admin/catalog")

    @app.post("/admin/catalog/pdf")
    @admin_only
    def catalog_pdf_upload():
        title=field("title",160)
        brand=field("brand",80)
        category=field("category",30)
        if not title or not brand or category not in CATEGORY_LABELS:
            abort(400)
        uploaded=request.files.get("catalog_file")
        if not uploaded or not uploaded.filename:
            flash("اختر ملف PDF أولًا.")
            return redirect("/admin/catalog")
        contents=uploaded.stream.read(MAX_PDF_BYTES+1)
        if not contents or len(contents)>MAX_PDF_BYTES:
            flash("حجم ملف PDF يجب ألا يتجاوز 4 ميغابايت.")
            return redirect("/admin/catalog")
        if not contents.startswith(b"%PDF-") or b"%%EOF" not in contents[-2048:]:
            flash("الملف غير صالح. اختر كتالوج PDF صحيحًا.")
            return redirect("/admin/catalog")
        d=DB()
        if d.scalar(select(func.count()).select_from(Document))>=60:
            flash("وصلت إلى الحد الأقصى من ملفات PDF.")
            return redirect("/admin/catalog")
        d.add(Document(title=title,brand=brand,category=category,
                       description=field("description",1000),pdf_data=contents,
                       visible=True))
        d.commit()
        flash("تم نشر الكتالوج PDF بنجاح.")
        return redirect("/admin/catalog")

    @app.post("/admin/catalog/pdf/<int:doc_id>/toggle")
    @admin_only
    def catalog_toggle_doc(doc_id):
        d=DB()
        doc=d.get(Document,doc_id)
        if not doc:
            abort(404)
        doc.visible=not doc.visible
        d.commit()
        flash("تم تغيير ظهور الملف.")
        return redirect("/admin/catalog")

    @app.post("/admin/catalog/pdf/<int:doc_id>/delete")
    @admin_only
    def catalog_delete_doc(doc_id):
        d=DB()
        doc=d.get(Document,doc_id)
        if not doc:
            abort(404)
        d.delete(doc)
        d.commit()
        flash("تم حذف الملف.")
        return redirect("/admin/catalog")
