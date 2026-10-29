"""Educational videos library with safe YouTube links and admin review."""
import re
from datetime import datetime, timezone
from urllib.parse import urlparse, parse_qs

from flask import request, redirect, flash, abort
from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, select


def register_video_model(Base):
    class TutorialVideo(Base):
        __tablename__ = "tutorial_videos"
        id = Column(Integer, primary_key=True)
        title = Column(String(160), nullable=False)
        description = Column(Text, default="")
        youtube_id = Column(String(11), nullable=False)
        visible = Column(Boolean, default=True)
        created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    return TutorialVideo



def register_direct_video_model(Base):
    class DirectVideo(Base):
        __tablename__ = "direct_videos"
        id = Column(Integer, primary_key=True)
        title = Column(String(160), nullable=False)
        description = Column(Text, default="")
        url = Column(Text, nullable=False)
        visible = Column(Boolean, default=True)
        created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    return DirectVideo


def direct_video_url(raw):
    """Only accept publicly accessible HTTPS video file URLs; never embed HTML pages."""
    raw = (raw or "").strip()
    if not raw or len(raw) > 1500:
        return None
    try:
        p = urlparse(raw)
        if p.scheme != "https" or not p.hostname or p.username or p.password or p.port not in (None, 443):
            return None
        if not p.path.lower().endswith((".mp4", ".webm", ".ogg", ".ogv")):
            return None
        return raw
    except (ValueError, AttributeError):
        return None


def video_id_from_link(raw):
    """Accept only HTTPS YouTube URLs and validated 11-character video IDs."""
    try:
        parsed = urlparse(raw.strip())
        if parsed.scheme != "https" or parsed.port not in (None, 443):
            return None
        host = (parsed.hostname or "").lower()
        path = parsed.path.strip("/")
        candidate = None
        if host == "youtu.be":
            candidate = path.split("/")[0]
        elif host in ("youtube.com", "www.youtube.com", "m.youtube.com",
                      "youtube-nocookie.com", "www.youtube-nocookie.com"):
            if path == "watch":
                candidate = parse_qs(parsed.query).get("v", [None])[0]
            elif path.startswith(("shorts/", "embed/", "live/")):
                candidate = path.split("/")[1]
        if candidate and re.fullmatch(r"[A-Za-z0-9_-]{11}", candidate):
            return candidate
    except (ValueError, AttributeError, IndexError):
        pass
    return None


def setup_video_routes(app, Video, DB, page, admin_only, DirectVideo=None):
    @app.get("/videos")
    def videos():
        # A YouTube player always contains links managed by YouTube. Use a native
        # HTML5 video player instead, so visitors stay on the store video page.
        clips = DB().scalars(select(DirectVideo).where(DirectVideo.visible == True).order_by(DirectVideo.id.desc()).limit(100)).all() if DirectVideo is not None else []
        return page("""<div class="container videos-page">
<section class="catalog-intro">
<h1>🎬 فيديوهات تعليمية</h1>
<p class="muted">دروس الشاحنات والبرمجة داخل متجر SABER ACTROS DZ، بدون تحويل إلى صفحة YouTube.</p>
</section>
<div class="grid">
{% for v in clips %}
<article class="card tutorial-card">
<div class="tutorial-player">
<video controls preload="metadata" playsinline controlslist="nodownload" aria-label="تشغيل {{v.title}}">
<source src="{{v.url}}">
متصفحك لا يدعم تشغيل هذا الفيديو.
</video>
</div>
<h2>{{v.title}}</h2>
{% if v.description %}<p>{{v.description}}</p>{% endif %}
</article>
{% else %}
<div class="card"><h2>مكتبة الفيديوهات قيد الإعداد</h2>
<p>أضف فيديوهات MP4 أو WebM من لوحة الإدارة كي تعمل مباشرة هنا بدون مشغّل أو روابط YouTube.</p></div>
{% endfor %}
</div></div>
<style>
.videos-page{padding:10px 0 35px}
.tutorial-card h2{font-size:1.13rem}
.tutorial-player{aspect-ratio:16/9;background:linear-gradient(145deg,#193951,#091a2d);border:1px solid #375c75;display:flex;align-items:center;justify-content:center;border-radius:11px;overflow:hidden;margin-bottom:12px}
.tutorial-player video{display:block;width:100%;height:100%;background:#000}
.tutorial-card p{white-space:pre-line;overflow-wrap:anywhere}
</style>""", title="فيديوهات تعليمية | SABER ACTROS DZ", clips=clips)

    @app.get("/admin/videos")
    @admin_only
    def admin_videos():
        clips = DB().scalars(select(Video).order_by(Video.id.desc()).limit(150)).all()
        direct = DB().scalars(select(DirectVideo).order_by(DirectVideo.id.desc()).limit(150)).all() if DirectVideo is not None else []
        return page("""<div class="container">
<h1>إدارة الفيديوهات التعليمية</h1>
<p><a href="/admin">لوحة الإدارة</a> · <a href="/videos">عرض الفيديوهات للعامة</a></p>
<section class="card"><h2>إضافة فيديو يعمل داخل المتجر فقط</h2>
<p class="muted">ضع رابط HTTPS مباشر لملف MP4 أو WebM أو OGG تملك حق عرضه. رابط صفحة YouTube لا يصلح هنا. ينبغي أن يكون الفيديو محفوظًا لدى استضافة تدعم عرضه عبر الإنترنت.</p>
<form method="post" action="/admin/videos/direct/new">
<input name="csrf" type="hidden" value="{{csrf}}">
<label>عنوان الدرس<input name="title" maxlength="160" required placeholder="مثال: تشخيص MAN TGS"></label>
<label>الرابط المباشر للفيديو<input name="url" type="url" maxlength="1500" required placeholder="https://your-storage.example/video.mp4"></label>
<label>وصف مختصر<textarea name="description" maxlength="1500"></textarea></label>
<button type="submit">إضافة الفيديو المباشر</button>
</form></section>
<section><h2>الفيديوهات المباشرة المعروضة للزوار</h2><div class="grid">
{% for v in direct %}
<article class="card"><h3>{{v.title}}</h3><p>{{v.description}}</p>
<p class="muted">{{"منشور" if v.visible else "مخفي"}}</p>
<form action="/admin/videos/direct/{{v.id}}/toggle" method="post" style="display:inline">
<input type="hidden" name="csrf" value="{{csrf}}"><button type="submit">{{"إخفاء" if v.visible else "نشر"}}</button></form>
<form action="/admin/videos/direct/{{v.id}}/delete" method="post" style="display:inline" onsubmit="return confirm('حذف هذا الفيديو من قائمة المتجر؟')">
<input type="hidden" name="csrf" value="{{csrf}}"><button type="submit">حذف</button></form>
</article>
{% else %}<p class="card">لم تضف بعد فيديوهات مباشرة.</p>{% endfor %}
</div></section>
<section><h2>فيديوهات YouTube القديمة (أرشيف الإدارة)</h2>
<p class="muted">احتفظنا بهذه البيانات دون حذفها. لا تظهر هذه المقاطع للزوار الآن لأن مشغّل YouTube يحتوي على روابط خارجية لا يسمح YouTube بتعطيلها.</p>
<div class="grid">{% for v in clips %}
<article class="card"><h3>{{v.title}}</h3><p>{{v.description}}</p>
<form action="/admin/videos/{{v.id}}/delete" method="post" style="display:inline" onsubmit="return confirm('حذف السجل القديم؟')">
<input type="hidden" name="csrf" value="{{csrf}}"><button type="submit">حذف السجل</button></form>
</article>
{% else %}<p class="card">لا توجد فيديوهات قديمة.</p>{% endfor %}
</div></section></div>""", title="إدارة الفيديوهات | SABER ACTROS DZ", clips=clips, direct=direct)

    @app.post("/admin/videos/new")
    @admin_only
    def add_video():
        flash("إضافة روابط YouTube موقوفة. استخدم رابط فيديو مباشر لتجنب فتح YouTube.")
        return redirect("/admin/videos")

    @app.post("/admin/videos/<int:video_id>/toggle")
    @admin_only
    def toggle_video(video_id):
        d = DB()
        v = d.get(Video, video_id)
        if v is None:
            abort(404)
        v.visible = not v.visible
        d.commit()
        flash("تم تحديث حالة الفيديو.")
        return redirect("/admin/videos")

    @app.post("/admin/videos/<int:video_id>/delete")
    @admin_only
    def delete_video(video_id):
        d = DB()
        v = d.get(Video, video_id)
        if v is None:
            abort(404)
        d.delete(v)
        d.commit()
        flash("تم حذف الفيديو.")
        return redirect("/admin/videos")

    @app.post("/admin/videos/direct/new")
    @admin_only
    def add_direct_video():
        if DirectVideo is None:
            abort(503)
        title = request.form.get("title", "").strip()[:160]
        desc = request.form.get("description", "").strip()[:1500]
        url = direct_video_url(request.form.get("url", ""))
        if not title or not url:
            flash("أدخل عنوانًا ورابط HTTPS مباشر ينتهي بـ MP4 أو WebM أو OGG.")
            return redirect("/admin/videos")
        d = DB()
        d.add(DirectVideo(title=title, description=desc, url=url, visible=True))
        d.commit()
        flash("أضيف الفيديو المباشر بنجاح.")
        return redirect("/admin/videos")

    @app.post("/admin/videos/direct/<int:video_id>/toggle")
    @admin_only
    def toggle_direct_video(video_id):
        if DirectVideo is None:
            abort(503)
        d = DB()
        video = d.get(DirectVideo, video_id)
        if video is None:
            abort(404)
        video.visible = not video.visible
        d.commit()
        flash("تم تحديث نشر الفيديو.")
        return redirect("/admin/videos")

    @app.post("/admin/videos/direct/<int:video_id>/delete")
    @admin_only
    def delete_direct_video(video_id):
        if DirectVideo is None:
            abort(503)
        d = DB()
        video = d.get(DirectVideo, video_id)
        if video is None:
            abort(404)
        d.delete(video)
        d.commit()
        flash("حُذف الفيديو من قائمة المتجر.")
        return redirect("/admin/videos")
