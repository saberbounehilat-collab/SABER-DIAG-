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
Photo=register_photo_model(Base)
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
nav strong{color:#ffcb55;font-size:21px}.links{display:flex;gap:16px;flex-wrap:wrap}.container{width:min(1100px,94%);margin:auto}
.hero{padding:90px 0 78px;text-align:center;background:linear-gradient(90deg,rgba(2,12,24,.83),rgba(2,12,24,.4),rgba(2,12,24,.83)),url('/static/hero.webp') center 52%/cover no-repeat;min-height:440px;display:flex;align-items:center;justify-content:center}.hero .container{position:relative;text-shadow:0 2px 15px #000b}.hero .button{text-shadow:none}h1{font-size:clamp(30px,5vw,52px);margin:8px}h2{color:#f8c75b}.muted{color:#a7bacd}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:18px;margin:24px 0}
.card{padding:22px;background:#142237;border:1px solid #2b445e;border-radius:16px;box-shadow:0 4px 18px #0002}
.button,button{display:inline-block;padding:10px 19px;background:#e6b44a;color:#121a28;font-weight:bold;border:0;border-radius:9px;cursor:pointer}
input,textarea,select{width:100%;padding:12px;margin:8px 0 16px;color:#eff7fd;background:#0b1929;border:1px solid #47647a;border-radius:9px}
label{display:block}input[type=checkbox]{width:auto;margin-left:8px}section{margin:40px 0}
small{color:#a7bacd}footer{text-align:center;padding:25px;margin-top:60px;background:#121f32}table{width:100%;border-collapse:collapse;min-width:650px}td,th{padding:9px;border-bottom:1px solid #355068;text-align:right}.scroll{overflow-x:auto}
.product-image{width:100%;height:180px;object-fit:cover;border-radius:12px;margin-bottom:10px}.gallery-image{width:100%;height:220px;object-fit:cover;border-radius:12px}.photo-actions{display:flex;gap:10px;flex-wrap:wrap}
.copy-link{background:#24394e;color:#eaf3fa;border:1px solid #4b6279;font-size:.86rem;padding:7px 12px;margin-inline-start:8px;font-weight:500}
.copy-link:hover{background:#314e6b}
</style>"""
def page(body,title="SABER ACTROS DZ",**context):
    template="""<!doctype html><html lang="ar" dir="rtl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{{title}}</title>"""+CSS+"""</head><body>
<nav><strong>SABER ACTROS DZ</strong><div class="links"><a href="/">الرئيسية</a><a href="/#products">البرامج والخدمات</a><a href="/gallery">معرض الصور</a><a href="/#contact">تواصل معنا</a>
{% if me %}<a href="/my-orders">طلباتي</a>{% if me.admin %}<a href="/admin">الإدارة</a><a href="/admin/photos">إدارة الصور</a>{% endif %}<form action="/logout" method="post" style="display:inline"><input type="hidden" name="csrf" value="{{csrf}}"><button>خروج</button></form>{% else %}<a href="/login">دخول</a><a href="/register">حساب جديد</a>{% endif %}</div></nav>
{% with messages=get_flashed_messages() %}{% if messages %}<div class="container"><p>{{messages|join(' • ')}}</p></div>{% endif %}{% endwith %}
"""+body+"""<footer>© SABER ACTROS DZ · <a href="/privacy">سياسة الخصوصية</a> · <a href="mailto:{{contact_email}}">{{contact_email}}</a> · <button type="button" class="copy-link" data-path="/" onclick="copyStoreLink(this)">نسخ رابط المتجر</button></footer><script>
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
    const oldText=el.textContent;
    el.textContent="✓ تم نسخ الرابط";
    setTimeout(()=>{el.textContent=oldText;},1900);
  } catch(e) {
    window.prompt("انسخ الرابط:",url);
  }
}
</script></body></html>"""
    return render_template_string(template,title=title,me=user(),csrf=token(),contact_email=os.getenv("PUBLIC_CONTACT_EMAIL","saberbounehilat@gmail.com"),whatsapp=os.getenv("PUBLIC_WHATSAPP","966564404359"),**context)
@app.get("/")
def home():
    products=DB().scalars(select(Product).where(Product.visible==True)).all()
    photo_ids={p.product_id:p.id for p in DB().scalars(select(Photo).where(Photo.kind=="product",Photo.status=="approved").order_by(Photo.id.asc())).all()}
    hero_id=DB().scalar(select(Photo.id).where(Photo.kind=="hero",Photo.status=="approved").order_by(Photo.id.desc()))
    return page("""<header class="hero"{% if hero_id %} style="background-image:linear-gradient(180deg,rgba(3,12,25,.30),rgba(3,12,25,.76)),url('/photos/file/{{hero_id}}')"{% endif %}><div class="container"><h1>برامج فحص الشاحنات وخدمات البرمجة</h1><p>MAN · Mercedes-Benz · IVECO · Volvo · Renault · Scania</p><p class="muted">أجهزة التشخيص والتراخيص والدعم الفني بإشراف SABER ACTROS DZ</p><a class="button" href="#products">استعرض البرامج</a></div></header>
<div class="container"><section id="products"><h2>البرامج والخدمات</h2><div class="grid">{% for p in products %}
<div class="card">{% if photo_ids.get(p.id) %}<a href="/order/{{p.slug}}"><img class="product-image" src="/photos/file/{{photo_ids[p.id]}}" alt="صورة {{p.title}}" loading="lazy"></a>{% endif %}<small>{{p.brand}}</small><h3>{{p.title}}</h3><p>{{p.description}}</p><a class="button" href="/order/{{p.slug}}">اطلب الآن</a><button type="button" class="copy-link" data-path="/order/{{p.slug}}" onclick="copyStoreLink(this)">نسخ الرابط</button></div>
{% endfor %}</div></section>
<section class="card" id="contact"><h2>تواصل قبل الدفع</h2><p>لا يوجد دفع تلقائي. سيتم التواصل معك لتوضيح السعر وطريقة الدفع، ولن يُؤكد الطلب إلا بواسطة المدير.</p>
<a class="button" href="https://wa.me/{{whatsapp}}" target="_blank" rel="noopener">واتساب +966 56 440 4359</a><p>البريد: <a href="mailto:{{contact_email}}">{{contact_email}}</a></p>
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
@app.route("/register",methods=["GET","POST"])
def register():
    if request.method=="POST":
        email=field("email",254).lower();pw=request.form.get("password","")
        if not valid_email(email) or len(pw)<10 or not field("consent") or not field("name",120):abort(400)
        d=DB()
        if d.scalar(select(User).where(User.email==email)):
            flash("البريد مستخدم سابقا");return redirect("/register")
        u=User(name=field("name",120),email=email,password_hash=generate_password_hash(pw))
        d.add(u);d.commit();session.clear();session["uid"]=u.id;return redirect("/my-orders")
    return auth("إنشاء حساب",True)
@app.route("/login",methods=["GET","POST"])
def login():
    if request.method=="POST":
        e=field("email",254).lower();d=DB();u=d.scalar(select(User).where(User.email==e))
        if u and check_password_hash(u.password_hash,request.form.get("password","")):
            session.clear();session["uid"]=u.id;return redirect("/admin" if u.admin else "/my-orders")
        flash("معلومات الدخول غير صحيحة")
    return auth("تسجيل الدخول",False)
def auth(title,register_mode):
    return page("""<div class="container"><section class="card" style="max-width:540px;margin:45px auto"><h2>{{heading}}</h2><form method="post">
<input type="hidden" name="csrf" value="{{csrf}}">
{% if registering %}<label>الاسم<input name="name" required maxlength="120"></label>{% endif %}
<label>البريد<input name="email" type="email" required></label><label>كلمة المرور<input name="password" type="password" minlength="{{10 if registering else 1}}" required></label>
{% if registering %}<label><input type="checkbox" name="consent" required>أوافق على <a href="/privacy">سياسة الخصوصية</a></label>{% endif %}
<button>{{heading}}</button></form></section></div>""",heading=title,registering=register_mode)
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
<section><h2>إضافة منتج أو خدمة</h2><form method="post" action="/admin/product" class="card"><input type="hidden" name="csrf" value="{{csrf}}"><label>الاسم<input name="title" required></label><label>العلامة<input name="brand" required></label><label>الوصف<textarea name="description" required></textarea></label><button>إضافة</button></form>
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
    return page("""<div class="container"><section class="card"><h1>سياسة الخصوصية</h1><p>نستخدم ملف تعريف جلسة آمن لعدّ الزيارات بصورة تقريبية دون معرفة البريد الإلكتروني للزائر تلقائياً.</p><p>نجمع الاسم والبريد الإلكتروني اللذين يقدمهما العميل بموافقته عند التسجيل أو الطلب أو التواصل، ونستخدمهما لخدمة العميل وإدارة طلباته.</p><p>يمكنك مراسلتنا لطلب تصحيح أو حذف بياناتك عبر {{contact_email}}. لا تُعرض معلوماتك لزوار الموقع. صور الأعضاء لا تظهر للعامة إلا بعد موافقتهم على النشر ومراجعة الإدارة، وتُزال منها بيانات الصور الوصفية أثناء المعالجة.</p></section></div>""")
@app.get("/health")
def health():return "ok",200
@app.get("/robots.txt")
def robots():return "User-agent: *\nDisallow: /admin\nDisallow: /my-orders\nDisallow: /login\n",200,{"Content-Type":"text/plain"}
setup_photo_routes(app, Photo, DB, user, page, field, admin_only, Product, User)
if __name__=="__main__":app.run(port=int(os.getenv("PORT","5000")))
