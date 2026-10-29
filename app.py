import os, re, secrets, hashlib
from datetime import datetime, timezone
from functools import wraps
from flask import Flask, request, session, redirect, abort, render_template_string, flash, g
from sqlalchemy import create_engine, Column, Integer, String, Text, Boolean, DateTime, ForeignKey, select, func, UniqueConstraint
from sqlalchemy.orm import declarative_base, scoped_session, sessionmaker
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.middleware.proxy_fix import ProxyFix

app=Flask(__name__)
secret=os.getenv("SECRET_KEY")
if not secret:
    if os.getenv("RENDER") or os.getenv("FLASK_ENV")=="production": raise RuntimeError("SECRET_KEY missing")
    secret=secrets.token_urlsafe(40)
app.secret_key=secret
app.config.update(SESSION_COOKIE_HTTPONLY=True,SESSION_COOKIE_SAMESITE="Lax",SESSION_COOKIE_SECURE=os.getenv("COOKIE_SECURE")=="1")
app.wsgi_app=ProxyFix(app.wsgi_app,x_for=1,x_proto=1)
url=os.getenv("DATABASE_URL","sqlite:///store.db")
url=url.replace("postgres://","postgresql+psycopg://",1).replace("postgresql://","postgresql+psycopg://",1)
engine=create_engine(url,pool_pre_ping=True,connect_args={"check_same_thread":False} if url.startswith("sqlite") else {})
DB=scoped_session(sessionmaker(bind=engine))
Base=declarative_base()
from photos import register_photo_model, setup_photo_routes
from catalog import register_catalog_models, setup_catalog_routes
from videos import register_video_model, setup_video_routes
from workshops import register_workshop_model, setup_workshops_routes
Photo=register_photo_model(Base)
CatalogMeta, CatalogDocument=register_catalog_models(Base)
TutorialVideo=register_video_model(Base)
Workshop=register_workshop_model(Base)
class User(Base):
    __tablename__="users"
    id=Column(Integer,primary_key=True)
    name=Column(String(120),nullable=False)
    email=Column(String(254),unique=True,nullable=False)
    password_hash=Column(String(255),nullable=False)
    admin=Column(Boolean,default=False)
class Product(Base):
    __tablename__="products"
    id=Column(Integer,primary_key=True)
    slug=Column(String(100),unique=True,nullable=False)
    title=Column(String(150),nullable=False)
    brand=Column(String(80),nullable=False)
    description=Column(Text,nullable=False)
    visible=Column(Boolean,default=True)
class Order(Base):
    __tablename__="orders"
    id=Column(Integer,primary_key=True)
    reference=Column(String(30),unique=True,nullable=False)
    product_id=Column(Integer,ForeignKey("products.id"),nullable=False)
    user_id=Column(Integer,ForeignKey("users.id"),nullable=True)
    name=Column(String(120),nullable=False)
    email=Column(String(254),nullable=False)
    contact=Column(String(180),default="")
    notes=Column(Text,default="")
    status=Column(String(50),default="awaiting_contact")
    created_at=Column(DateTime,default=lambda:datetime.now(timezone.utc))
class Inquiry(Base):
    __tablename__="inquiries"
    id=Column(Integer,primary_key=True)
    name=Column(String(120))
    email=Column(String(254),nullable=False)
    message=Column(Text)
class Visit(Base):
    __tablename__="visits"
    id=Column(Integer,primary_key=True)
    day=Column(String(10))
    digest=Column(String(64))
    views=Column(Integer,default=1)
    __table_args__=(UniqueConstraint("day","digest"),)
Base.metadata.create_all(engine)
seed=[
("man-cats","MAN CATS","MAN","خدمات تشخيص وإعداد أجهزة فحص شاحنات MAN والتراخيص الرسمية حسب التوفر"),
("xentry","Mercedes-Benz Xentry","Mercedes-Benz","دعم الفحص والتشخيص لشاحنات مرسيدس بنز"),
("iveco-easy","IVECO EASY","IVECO","حلول تشخيص وإعداد الأجهزة والتراخيص المعتمدة"),
("tech-tool","Volvo Premium Tech Tool","Volvo / Renault","خدمات دعم وتشخيص وبرمجة مصرح بها"),
("jaltest","Jaltest CV","Multi-brand","دعم أدوات الفحص متعددة العلامات"),
("ecu-tcu","ECU / TCU Repair","ECU","فحص وإصلاح وحدات التحكم الإلكترونية"),
("remote-support","الدعم الفني عن بعد","Support","استشارة تقنية ومساعدة تشخيص عن بُعد"),
("training","تدريب فحص الشاحنات","Academy","دورات تدريبية للتشخيص وقراءة المخططات")
]
with DB() as d:
    if not d.scalar(select(func.count()).select_from(Product)):
        d.add_all([Product(slug=a,title=b,brand=c,description=e) for a,b,c,e in seed])
    email=os.getenv("ADMIN_EMAIL","").strip().lower()
    pw=os.getenv("ADMIN_PASSWORD","")
    existing=d.scalar(select(User).where(User.email==email)) if email else None
    if existing and not existing.admin: raise RuntimeError("Admin email already registered as customer")
    if email and pw:
        if len(pw)<8: raise RuntimeError("Admin password too short")
        if existing:
            # Keep the admin login synchronized with the secret stored in Render.
            # Changing ADMIN_PASSWORD only updates the intended admin account.
            if not check_password_hash(existing.password_hash,pw):
                existing.password_hash=generate_password_hash(pw)
        else:
            d.add(User(name="SABER ACTROS DZ",email=email,password_hash=generate_password_hash(pw),admin=True))
    d.commit()
@app.teardown_appcontext
def close(error=None):
    DB.remove()
def user():
    return DB().get(User,session["uid"]) if session.get("uid") else None
def token():
    if "csrf" not in session:session["csrf"]=secrets.token_urlsafe(32)
    return session["csrf"]
def field(name,maxlen=500):
    return request.form.get(name,"").strip()[:maxlen]
def valid_email(e):
    return len(e)<=254 and bool(re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+",e))
@app.before_request
def before():
    if request.method=="POST" and not secrets.compare_digest(str(session.get("csrf","")),str(request.form.get("csrf",""))):abort(400)
    if request.method!="GET" or request.path.startswith(("/admin","/health","/static","/photos/")):return
    key=session.setdefault("visitor",secrets.token_urlsafe(20))
    day=datetime.now(timezone.utc).date().isoformat()
    digest=hashlib.sha256((app.secret_key+key).encode()).hexdigest()
    d=DB()
    v=d.scalar(select(Visit).where(Visit.day==day,Visit.digest==digest))
    if v:v.views+=1
    else:d.add(Visit(day=day,digest=digest))
    try:d.commit()
    except Exception:d.rollback()
def admin_only(fn):
    @wraps(fn)
    def wrapped(*args,**kwargs):
        u=user()
        if not u:return redirect("/login")
        if not u.admin:abort(403)
        return fn(*args,**kwargs)
    return wrapped
CSS="""<style>
:root{color-scheme:dark}*{box-sizing:border-box}body{margin:0;background:linear-gradient(rgba(8,16,29,.94),rgba(8,16,29,.97)),url('/static/hero.webp') center top/cover fixed no-repeat;background-color:#0b1220;color:#edf4ff;font:16px system-ui,Arial;line-height:1.8}
a{color:#6bdbf0;text-decoration:none}nav{display:flex;gap:16px;flex-wrap:wrap;align-items:center;justify-content:space-between;padding:17px max(20px,5%);background:#121f32;border-bottom:1px solid #29405a}
nav strong{color:#ffcb55;font-size:21px}.brand-lockup{display:flex;flex-direction:column;align-items:flex-start;gap:0;line-height:1.5}.brand-title-line{display:flex;align-items:center;gap:9px;flex-wrap:wrap}.wa-inquiry{display:inline-flex;align-items:center;gap:7px;background:#16854f;border:1px solid #51cb83;color:#fff!important;text-decoration:none!important;border-radius:10px;padding:5px 9px;line-height:1.15;font-size:12px;font-weight:700;white-space:nowrap;box-shadow:0 2px 8px #0003}.wa-inquiry:hover,.wa-inquiry:focus-visible{background:#20a562;color:#fff!important}.wa-inquiry svg{width:25px;height:25px;flex-shrink:0;display:block}.wa-inquiry-text{display:flex;flex-direction:column;gap:1px;text-align:center}.wa-inquiry-hours{font-size:11px;font-weight:800;direction:ltr;unicode-bidi:isolate}.algeria-flag{width:32px;height:auto;aspect-ratio:3/2;object-fit:cover;display:block;border-radius:2px;box-shadow:0 0 0 1px #ffffff55}.brand-caption{font-size:13px;color:#e4ebf3;font-weight:500;white-space:nowrap}.brand-caption bdi{direction:ltr;unicode-bidi:isolate}.links{display:flex;gap:16px;flex-wrap:wrap}.container{width:min(1100px,94%);margin:auto}
.hero{padding:90px 0 78px;text-align:center;background:linear-gradient(90deg,rgba(2,12,24,.83),rgba(2,12,24,.4),rgba(2,12,24,.83)),url('/static/hero.webp') center 52%/cover no-repeat;min-height:440px;display:flex;align-items:center;justify-content:center}.hero .container{position:relative;text-shadow:0 2px 15px #000b}.hero .button{text-shadow:none}h1{font-size:clamp(30px,5vw,52px);margin:8px}h2{color:#f8c75b}.muted{color:#a7bacd}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:18px;margin:24px 0}
.card{padding:22px;background:#142237;border:1px solid #2b445e;border-radius:16px;box-shadow:0 4px 18px #0002}
.button,button{display:inline-block;padding:10px 19px;background:#e6b44a;color:#121a28;font-weight:bold;border:0;border-radius:9px;cursor:pointer}
input,textarea,select{width:100%;padding:12px;margin:8px 0 16px;color:#eff7fd;background:#0b1929;border:1px solid #47647a;border-radius:9px}
label{display:block}input[type=checkbox]{width:auto;margin-left:8px}section{margin:40px 0}
small{color:#a7bacd}footer{text-align:center;padding:25px;margin-top:60px;background:#121f32}table{width:100%;border-collapse:collapse;min-width:650px}td,th{padding:9px;border-bottom:1px solid #355068;text-align:right}.scroll{overflow-x:auto}
.hero-actions{display:flex;flex-wrap:wrap;justify-content:center;align-items:center;gap:12px;margin:20px auto 0}.hero-actions .button{font:inherit;font-weight:700;min-width:155px;padding:10px 19px;text-shadow:none}
.catalog-intro{background:#15273d;border:1px solid #304967;border-radius:16px;padding:24px;margin-top:35px}
.catalog-filters{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:14px;align-items:end}
.catalog-filters input,.catalog-filters select{margin:6px 0 0}
.catalog-reset{padding:9px 0;color:#8addec}
.catalog-card h3 a{color:#fff}
.catalog-card h3 a:hover{color:#e7bf65}
.catalog-actions{display:flex;align-items:center;flex-wrap:wrap;gap:9px;margin-top:14px}
.catalog-actions .button{font-size:.88rem;padding:8px 12px}
.catalog-actions .copy-link{margin:0}
.catalog-no-photo{height:170px;display:flex;align-items:center;justify-content:center;background:linear-gradient(145deg,#263d57,#10283f);font-weight:800;letter-spacing:.06em;border-radius:12px;margin-bottom:10px;color:#e9ba58}
.catalog-detail{max-width:850px;margin:32px auto}
.catalog-detail-image{display:block;width:100%;max-height:370px;object-fit:contain;background:#0d1725;border-radius:11px;margin:14px auto}
.catalog-specs{white-space:pre-wrap}
.product-image{width:100%;height:180px;object-fit:cover;border-radius:12px;margin-bottom:10px}.gallery-image{width:100%;height:220px;object-fit:cover;border-radius:12px}.photo-actions{display:flex;gap:10px;flex-wrap:wrap}
.copy-link{background:#24394e;color:#eaf3fa;border:1px solid #4b6279;font-size:.86rem;padding:7px 12px;margin-inline-start:8px;font-weight:500}
.copy-link:hover{background:#314e6b}
.share-link{display:inline-flex;align-items:center;justify-content:center;vertical-align:middle;width:38px;height:38px;padding:7px!important;cursor:pointer;border-radius:10px;margin-inline-start:7px}
.share-link svg{display:block;flex:none}
.share-link:hover,.share-link:focus-visible{background:#2f5477;color:#fff}

.install-app-button{background:#168252!important;color:#fff!important;border:1px solid #62cd91!important}
.install-app-button:hover,.install-app-button:focus-visible{background:#1ba462!important}
.header-install-button{display:inline-flex!important;align-items:center;justify-content:center;gap:6px;padding:6px 10px!important;border-radius:10px;min-height:36px;font-size:12px;line-height:1.25;white-space:nowrap;box-shadow:0 2px 8px #0003}
.header-install-button svg{display:block;flex-shrink:0}
.install-help{font-size:.87rem;line-height:1.65;color:#d8e7f3;background:#1a3447;border:1px solid #43627b;border-radius:10px;padding:10px 12px;max-width:400px;margin:9px auto;text-align:right}
.admin-photo-link,.admin-video-link{display:inline-flex;align-items:center;gap:6px;color:#f2cb71!important;font-weight:700}
.admin-photo-link svg,.admin-video-link svg{display:block;flex-shrink:0}
.admin-photo-link:hover,.admin-photo-link:focus-visible,.admin-video-link:hover,.admin-video-link:focus-visible{color:#fff0b5!important;text-decoration:underline}
html.store-installed .install-app-button{display:none!important}
@media(max-width:620px){.hero-actions{gap:9px}.header-install-button{padding:6px 8px!important}}
</style>"""
def page(body,title="SABER ACTROS DZ",**context):
    template="""<!doctype html><html lang="ar" dir="rtl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{{title}}</title>
<link rel="manifest" href="/manifest.webmanifest">
<link rel="icon" type="image/png" sizes="192x192" href="/static/icons/icon-192.png">
<link rel="apple-touch-icon" sizes="180x180" href="/static/icons/icon-180.png">
<meta name="theme-color" content="#121f32">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-title" content="SABER ACTROS DZ">
<meta name="apple-mobile-web-app-status-bar-style" content="default">
"""+CSS+"""</head><body>
<nav><div class="brand-lockup"><div class="brand-title-line"><img class="algeria-flag" src="/static/flag-dz.svg" width="32" height="21" alt="علم الجزائر"><strong>SABER ACTROS DZ</strong><a class="wa-inquiry" href="https://wa.me/{{whatsapp}}" target="_blank" rel="noopener noreferrer" aria-label="واتساب للاستفسار 24/24">
<svg viewBox="0 0 32 32" aria-hidden="true" focusable="false"><path d="M26.4 15.1a10.7 10.7 0 0 1-15.9 9.3L5.1 26l1.5-5.2A10.7 10.7 0 1 1 26.4 15.1Z" fill="none" stroke="white" stroke-width="2.1" stroke-linecap="round" stroke-linejoin="round"/><path d="M12 10.4c-.6-.3-1.5.5-1.7 1.5-.5 2.2 1.5 5 3.9 7 2.4 2 5.1 3 6.5 2.3.8-.4 1.7-1.4 1.6-2.2 0-.5-2.4-1.5-2.8-1.3l-1.2 1.4c-1.3.6-4.6-2.3-4.8-3.8l1.1-1.3c.2-.4-.9-2.9-1.7-3.2Z" fill="white"/></svg>
<span class="wa-inquiry-text"><span>واتساب للاستفسار</span><span class="wa-inquiry-hours">24/24</span></span></a><button type="button" class="install-app-button header-install-button" title="تثبيت المتجر على الهاتف" aria-label="تثبيت المتجر على الهاتف" onclick="installStoreApp(this)"><svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="6" y="2" width="12" height="20" rx="2"/><path d="M12 7v9m-3-3 3 3 3-3"/></svg><span>تثبيت المتجر</span></button></div><span class="brand-caption">أبو يزن · <bdi dir="ltr">00966564404359</bdi></span></div><div class="links"><a href="/">الرئيسية</a><a href="/#products">البرامج والخدمات</a><a href="/catalog">كتالوج</a><a href="/catalog/pdfs">كتالوجات PDF</a><a href="/workshops">أقرب ورشة</a><a href="/videos">فيديوهات تعليمية</a>{% if me and me.admin %}<a class="admin-photo-link" href="/admin/photos" title="إدارة الصور" aria-label="إدارة الصور"><svg viewBox="0 0 24 24" width="19" height="19" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><path d="m3 17 5-5 4 4 3-3 6 6"/></svg><span>إدارة الصور</span></a>{% endif %}
{% if me %}<a href="/my-orders">طلباتي</a>{% if me.admin %}<a href="/admin">الإدارة</a><a href="/admin/catalog">إدارة الكتالوج</a><a href="/admin/workshops">لوحة إدارة الورش</a><a class="admin-video-link" href="/admin/videos" title="إضافة فيديوهات تعليمية" aria-label="إضافة فيديوهات تعليمية"><svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="2" y="5" width="15" height="14" rx="2"/><path d="m17 9 5-3v12l-5-3"/><path d="M9.5 8.5v7m-3.5-3.5h7"/></svg><span>إضافة فيديوهات تعليمية</span></a>{% endif %}<form action="/logout" method="post" style="display:inline"><input type="hidden" name="csrf" value="{{csrf}}"><button>خروج</button></form>{% else %}<a href="/login">دخول</a>{% endif %}</div></nav>
{% with messages=get_flashed_messages() %}{% if messages %}<div class="container"><p>{{messages|join(' • ')}}</p></div>{% endif %}{% endwith %}
"""+body+"""<footer>© SABER ACTROS DZ · <a href="/#contact">تواصل معنا</a> · <a href="/privacy">سياسة الخصوصية</a> · <a href="mailto:{{contact_email}}">{{contact_email}}</a> · <button type="button" class="copy-link share-link" data-path="/" data-title="SABER ACTROS DZ" title="مشاركة الرابط" aria-label="مشاركة الرابط" onclick="shareStoreLink(this)"><svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/><path d="M8.6 13.5l6.8 4M15.4 6.5l-6.8 4"/></svg></button></footer><script>
async function copyStoreLink(el){
  const url = new URL(el.dataset.path || "/", window.location.origin).href;
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(url);
    } else {
      const temp = document.createElement("textarea");
      temp.value=url;temp.style.position="fixed";temp.style.opacity="0";
      document.body.appendChild(temp);temp.select();
      const success=document.execCommand("copy");temp.remove();
      if(!success)throw Error("copy failed");
    }
    const oldHTML=el.innerHTML;
    el.textContent="✓";
    el.setAttribute("aria-label","تم نسخ الرابط");
    setTimeout(()=>{el.innerHTML=oldHTML;el.setAttribute("aria-label","مشاركة الرابط");},1900);
  } catch(e) {
    window.prompt("انسخ الرابط:",url);
  }
}

async function shareStoreLink(el) {
  const url=new URL(el.dataset.path||"/",window.location.origin).href;
  const title=el.dataset.title||"SABER ACTROS DZ";
  if(navigator.share){
    try { await navigator.share({title,url}); return; }
    catch(e){ if(e.name==="AbortError") return; }
  }
  await copyStoreLink(el);
}
</script><script src="/static/install.js" defer></script></body></html>"""
    return render_template_string(template,title=title,me=user(),csrf=token(),contact_email=os.getenv("PUBLIC_CONTACT_EMAIL","saberbounehilat@gmail.com"),whatsapp=os.getenv("PUBLIC_WHATSAPP","966564404359"),**context)
@app.get("/")
def home():
    products=DB().scalars(select(Product).where(Product.visible==True)).all()
    photo_ids={p.product_id:p.id for p in DB().scalars(select(Photo).where(Photo.kind=="product",Photo.status=="approved").order_by(Photo.id.asc())).all()}
    hero_id=DB().scalar(select(Photo.id).where(Photo.kind=="hero",Photo.status=="approved").order_by(Photo.id.desc()))
    return page("""<header class="hero"{% if hero_id %} style="background-image:linear-gradient(180deg,rgba(3,12,25,.30),rgba(3,12,25,.76)),url('/photos/file/{{hero_id}}')"{% endif %}><div class="container"><h1>برامج فحص الشاحنات وخدمات البرمجة</h1><p>MAN · Mercedes-Benz · IVECO · Volvo · Renault · Scania</p><p class="muted">أجهزة التشخيص والتراخيص والدعم الفني بإشراف SABER ACTROS DZ</p><div class="hero-actions"><a class="button" href="#products">الأجهزة والبرامج</a><a class="button" href="/catalog">كتالوج</a><a class="button" href="/videos">🎬 فيديوهات تعليمية</a><a class="button" href="/workshops">📍 أقرب ورشة</a></div></div></header>
<div class="container"><section id="products"><h2>البرامج والخدمات</h2><div class="grid">{% for p in products %}
<div class="card">{% if photo_ids.get(p.id) %}<a href="/order/{{p.slug}}"><img class="product-image" src="/photos/file/{{photo_ids[p.id]}}" alt="صورة {{p.title}}" loading="lazy"></a>{% endif %}<small>{{p.brand}}</small><h3>{{p.title}}</h3><p>{{p.description}}</p><a class="button" href="/order/{{p.slug}}">اطلب الآن</a><button type="button" class="copy-link share-link" data-path="/order/{{p.slug}}" data-title="{{p.title}} | SABER ACTROS DZ" title="مشاركة الرابط" aria-label="مشاركة الرابط" onclick="shareStoreLink(this)"><svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/><path d="M8.6 13.5l6.8 4M15.4 6.5l-6.8 4"/></svg></button></div>
{% endfor %}</div></section>
<section class="card" id="contact"><h2>تواصل قبل الدفع</h2><p>لا يوجد دفع تلقائي. سيتم التواصل معك لتوضيح السعر وطريقة الدفع، ولن يُؤكد الطلب إلا بواسطة المدير.</p>
<a class="button" href="https://wa.me/{{whatsapp}}" target="_blank" rel="noopener">واتساب <bdi dir="ltr">00966564404359</bdi></a><p>البريد: <a href="mailto:{{contact_email}}">{{contact_email}}</a></p>
<h3>أرسل استفسارك</h3><form method="post" action="/contact"><input type="hidden" name="csrf" value="{{csrf}}">
<label>الاسم<input name="name" maxlength="120" required></label><label>البريد الإلكتروني<input name="email" type="email" required></label><label>الرسالة<textarea name="message" maxlength="2000" required></textarea></label>
<label><input type="checkbox" name="consent" required>أوافق على إرسال بريدي وبياناتي لغرض الرد، وفق <a href="/privacy">سياسة الخصوصية</a>.</label><button>إرسال</button></form></section></div>""",products=products,photo_ids=photo_ids,hero_id=hero_id)
@app.post("/contact")
def contact():
    e=field("email",254).lower()
    if not valid_email(e) or not field("consent"):abort(400)
    if session.get("sent",0)>=5:abort(429)
    d=DB();d.add(Inquiry(name=field("name",120),email=e,message=field("message",2000)));d.commit()
    session["sent"]=session.get("sent",0)+1
    flash("تم استلام استفسارك");return redirect("/#contact")
@app.route("/login",methods=["GET","POST"])
def login():
    if request.method=="POST":
        e=field("email",254).lower();d=DB();u=d.scalar(select(User).where(User.email==e))
        if u and check_password_hash(u.password_hash,request.form.get("password","")):
            session.clear();session["uid"]=u.id;return redirect("/admin" if u.admin else "/my-orders")
        flash("معلومات الدخول غير صحيحة")
    return auth("تسجيل الدخول")
def auth(title):
    return page("""<div class="container"><section class="card" style="max-width:540px;margin:45px auto"><h2>{{heading}}</h2><form method="post">
<input type="hidden" name="csrf" value="{{csrf}}">
<label>البريد<input name="email" type="email" required></label>
<label>كلمة المرور<input name="password" type="password" required></label>
<button>{{heading}}</button></form></section></div>""",heading=title)
@app.post("/logout")
def logout():
    session.clear();return redirect("/")
@app.route("/order/<slug>",methods=["GET","POST"])
def order(slug):
    d=DB();p=d.scalar(select(Product).where(Product.slug==slug,Product.visible==True))
    if not p:abort(404)
    if request.method=="POST":
        email=field("email",254).lower();name=field("name",120)
        if not name or not valid_email(email) or not field("consent"):abort(400)
        ref="SADZ-"+secrets.token_hex(5).upper()
        u=user()
        d.add(Order(reference=ref,product_id=p.id,user_id=u.id if u else None,name=name,email=email,contact=field("contact",180),notes=field("notes",2000)))
        d.commit()
        return page("""<div class="container"><section class="card"><h2>تم إرسال طلبك</h2><p>رقم الطلب: <strong>{{ref}}</strong></p><p>الحالة: بانتظار التواصل لتزويدك بمعلومات الدفع.</p><a class="button" href="https://wa.me/{{whatsapp}}?text={{('طلب رقم '+ref)|urlencode}}" target="_blank">التواصل واتساب</a></section></div>""",ref=ref)
    return page("""<div class="container"><section class="card" style="max-width:700px;margin:45px auto"><h2>طلب {{p.title}}</h2><p>{{p.description}}</p><p class="muted">السعر وطريقة الدفع بعد التواصل. التأكيد يدوي فقط.</p>
<form method="post"><input type="hidden" name="csrf" value="{{csrf}}">
<label>الاسم<input name="name" value="{{me.name if me else ''}}" required></label><label>البريد<input type="email" name="email" value="{{me.email if me else ''}}" required></label>
<label>رقم التواصل<input name="contact"></label><label>تفاصيل الطلب<textarea name="notes"></textarea></label>
<label><input type="checkbox" name="consent" required>أوافق على مشاركة بياناتي لغرض تنفيذ الطلب.</label><button>إرسال الطلب</button></form></section></div>""",p=p)
@app.get("/my-orders")
def myorders():
    u=user()
    if not u:return redirect("/login")
    orders=DB().execute(select(Order,Product).join(Product,Order.product_id==Product.id).where(Order.user_id==u.id).order_by(Order.id.desc())).all()
    return page("""<div class="container"><h2>طلباتي</h2><div class="grid">{% for o,p in orders %}<div class="card"><b>{{o.reference}}</b><p>{{p.title}}</p><p>الحالة: {{o.status}}</p></div>{% else %}<p>لا توجد طلبات بعد.</p>{% endfor %}</div></div>""",orders=orders)
@app.get("/admin")
@admin_only
def admin():
    d=DB()
    views=d.scalar(select(func.coalesce(func.sum(Visit.views),0)))
    uniques=d.scalar(select(func.count()).select_from(Visit))
    orders=d.execute(select(Order,Product).join(Product,Order.product_id==Product.id).order_by(Order.id.desc()).limit(200)).all()
    inquiries=d.scalars(select(Inquiry).order_by(Inquiry.id.desc()).limit(200)).all()
    products=d.scalars(select(Product)).all()
    customers=d.scalars(select(User).where(User.admin==False).limit(200)).all()
    return page("""<div class="container"><h1>لوحة الإدارة</h1><div class="grid"><div class="card"><h2>{{views}}</h2>مشاهدات الصفحات</div><div class="card"><h2>{{uniques}}</h2>زوار فريدون تقريبياً حسب اليوم</div><div class="card"><h2>{{orders|length}}</h2>طلبات معروضة</div></div>
<section><h2>الطلبات</h2><div class="scroll"><table><tr><th>الرقم</th><th>العميل</th><th>البريد</th><th>البرنامج</th><th>التفاصيل</th><th>الحالة</th></tr>{% for o,p in orders %}
<tr><td>{{o.reference}}</td><td>{{o.name}}</td><td>{{o.email}}</td><td>{{p.title}}</td><td>{{o.contact}} {{o.notes}}</td><td><form method="post" action="/admin/order/{{o.id}}"><input type="hidden" name="csrf" value="{{csrf}}"><select name="status">{% for s in statuses %}<option value="{{s}}" {% if o.status==s %}selected{% endif %}>{{s}}</option>{% endfor %}</select><button>حفظ</button></form></td></tr>{% endfor %}</table></div></section>
<section><h2>رسائل العملاء (بموافقتهم)</h2><div class="grid">{% for i in inquiries %}<div class="card"><b>{{i.name}}</b> · {{i.email}}<p>{{i.message}}</p></div>{% endfor %}</div></section>
<section><h2>العملاء المسجلون</h2><div class="grid">{% for c in customers %}<div class="card">{{c.name}} · {{c.email}}</div>{% endfor %}</div></section>
<section><h2>دليل الورش</h2><p class="muted">أضف صور الورش وأرقام التواصل وعناوينها وحدد مواقعها على الخريطة.</p><a class="button" href="/admin/workshops">إدارة الورش ومواقعها</a></section><section><h2>الفيديوهات التعليمية</h2><p class="muted">أضف فيديوهات دروسك التعليمية من يوتيوب لتظهر للزوار.</p><a class="button" href="/admin/videos">إدارة الفيديوهات</a></section>
<section><h2>إدارة الكتالوج</h2><p class="muted">برامج الفحص والبرمجة منفصلة عن كتالوجات PDF وقطع الغيار.</p><p><a class="button" href="/admin/catalog">فتح لوحة إدارة الكتالوج</a> <a href="/catalog">كتالوج</a> · <a href="/catalog/pdfs">كتالوجات PDF</a></p></section><section><h2>إضافة منتج أو خدمة</h2><form method="post" action="/admin/product" class="card"><input type="hidden" name="csrf" value="{{csrf}}"><label>الاسم<input name="title" required></label><label>العلامة<input name="brand" required></label><label>الوصف<textarea name="description" required></textarea></label><button>إضافة</button></form>
{% for p in products %}<div class="card">{{p.title}} · {{'معروض' if p.visible else 'مخفي'}}<form method="post" action="/admin/product/{{p.id}}/toggle"><input type="hidden" name="csrf" value="{{csrf}}"><button>إظهار/إخفاء</button></form></div>{% endfor %}</section></div>""",views=views,uniques=uniques,orders=orders,inquiries=inquiries,customers=customers,products=products,statuses=["awaiting_contact","awaiting_payment","paid","delivered","rejected"])
@app.post("/admin/order/<int:id>")
@admin_only
def update_order(id):
    o=DB().get(Order,id)
    if not o:abort(404)
    status=field("status",50)
    if status not in ["awaiting_contact","awaiting_payment","paid","delivered","rejected"]:abort(400)
    o.status=status;DB().commit();return redirect("/admin")
@app.post("/admin/product")
@admin_only
def add_product():
    title=field("title",150);brand=field("brand",80);description=field("description",2000)
    if not all([title,brand,description]):abort(400)
    DB().add(Product(slug="item-"+secrets.token_hex(5),title=title,brand=brand,description=description));DB().commit();return redirect("/admin")
@app.post("/admin/product/<int:id>/toggle")
@admin_only
def toggle(id):
    p=DB().get(Product,id)
    if not p:abort(404)
    p.visible=not p.visible;DB().commit();return redirect("/admin")
@app.get("/privacy")
def privacy():
    return page("""<div class="container"><section class="card"><h1>سياسة الخصوصية</h1><p>نستخدم ملف تعريف جلسة آمن لعدّ الزيارات بصورة تقريبية دون معرفة البريد الإلكتروني للزائر تلقائياً.</p><p>نجمع الاسم والبريد الإلكتروني اللذين يقدمهما العميل بموافقته عند الطلب أو التواصل، ونستخدمهما لخدمة العميل وإدارة طلباته.</p><p>يمكنك مراسلتنا لطلب تصحيح أو حذف بياناتك عبر {{contact_email}}. لا تُعرض معلوماتك لزوار الموقع. صور الأعضاء لا تظهر للعامة إلا بعد موافقتهم على النشر ومراجعة الإدارة، وتُزال منها بيانات الصور الوصفية أثناء المعالجة.</p></section></div>""")
@app.get("/health")
def health():return "ok",200
@app.get("/manifest.webmanifest")
def store_manifest():
    response=app.send_static_file("manifest.webmanifest")
    response.mimetype="application/manifest+json"
    response.headers["Cache-Control"]="public, max-age=3600"
    return response

@app.get("/service-worker.js")
def store_service_worker():
    response=app.send_static_file("sw.js")
    response.mimetype="application/javascript"
    response.headers["Service-Worker-Allowed"]="/"
    response.headers["Cache-Control"]="no-cache, no-store, must-revalidate"
    return response

@app.get("/robots.txt")
def robots():return "User-agent: *\nDisallow: /admin\nDisallow: /my-orders\nDisallow: /login\n",200,{"Content-Type":"text/plain"}
setup_photo_routes(app, Photo, DB, user, page, field, admin_only, Product, User)
setup_catalog_routes(app, CatalogMeta, CatalogDocument, DB, Product, Photo, user, page, field, admin_only)
setup_workshops_routes(app, Workshop, DB, page, admin_only)
setup_video_routes(app, TutorialVideo, DB, page, admin_only)
if __name__=="__main__":app.run(port=int(os.getenv("PORT","5000")))
