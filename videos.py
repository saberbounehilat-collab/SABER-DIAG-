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


def setup_video_routes(app, Video, DB, page, admin_only):
    @app.get("/videos")
    def videos():
        clips = DB().scalars(select(Video).where(Video.visible == True).order_by(Video.id.desc()).limit(100)).all()
        return page("""<div class="container videos-page">
<section class="catalog-intro">
<h1>🎬 فيديوهات تعليمية</h1>
<p class="muted">دروس تقنية في تشخيص الشاحنات وبرمجة وحدات التحكم والصيانة. اضغط على فيديو لتشغيله.</p>
</section>
<div class="grid">
{% for v in clips %}
<article class="card tutorial-card">
<div class="tutorial-player" id="tutorial-player-{{v.id}}">
<button class="tutorial-play" type="button" data-video="{{v.youtube_id}}" onclick="playTutorialVideo(this)" aria-label="تشغيل فيديو {{v.title}}">
<svg viewBox="0 0 24 24" width="48" height="48" aria-hidden="true"><circle cx="12" cy="12" r="11" fill="#b8312b"/><path d="M9 6.5 18 12 9 17.5Z" fill="white"/></svg>
<span>▶ تشغيل الدرس</span></button></div>
<h2>{{v.title}}</h2>
{% if v.description %}<p>{{v.description}}</p>{% endif %}
</article>
{% else %}
<div class="card"><h2>المكتبة قيد الإعداد</h2><p>لم تُنشر فيديوهات تعليمية بعد. ستظهر هنا الفيديوهات التي تضيفها إدارة المتجر.</p></div>
{% endfor %}
</div></div>
<style>
.videos-page{padding:10px 0 35px}.tutorial-card h2{font-size:1.13rem}
.tutorial-player{aspect-ratio:16/9;background:linear-gradient(145deg,#193951,#091a2d);border:1px solid #375c75;display:flex;align-items:center;justify-content:center;border-radius:11px;overflow:hidden;margin-bottom:12px}
.tutorial-play{background:transparent;border:0;color:white;cursor:pointer;display:flex;align-items:center;justify-content:center;flex-direction:column;gap:10px;font:inherit;font-weight:700;width:100%;height:100%}
.tutorial-play:hover{background:#2250715c}.tutorial-player iframe{display:block;width:100%;height:100%;border:0}
.tutorial-card p{white-space:pre-line;overflow-wrap:anywhere}
</style>
<script>
function playTutorialVideo(button){
  const id=button.dataset.video;
  if(!/^[A-Za-z0-9_-]{11}$/.test(id))return;
  const frame=document.createElement("iframe");
  frame.src="https://www.youtube-nocookie.com/embed/"+id+"?autoplay=1&rel=0";
  frame.title="فيديو تعليمي";frame.loading="lazy";frame.referrerPolicy="strict-origin-when-cross-origin";
  frame.allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share";
  frame.allowFullscreen=true;
  button.parentElement.replaceChildren(frame);
}
</script>""", title="فيديوهات تعليمية | SABER ACTROS DZ", clips=clips)

    @app.get("/admin/videos")
    @admin_only
    def admin_videos():
        clips = DB().scalars(select(Video).order_by(Video.id.desc()).limit(150)).all()
        return page("""<div class="container">
<h1>إدارة الفيديوهات التعليمية</h1>
<p><a href="/admin">لوحة الإدارة</a> · <a href="/videos">عرض الفيديوهات للعامة</a></p>
<section class="card"><h2>إضافة درس فيديو</h2>
<p class="muted">أدخل رابط فيديو من يوتيوب (YouTube) أو Shorts. يُعرض بعد الإضافة ويمكنك إخفاؤه في أي وقت.</p>
<form method="post" action="/admin/videos/new">
<input name="csrf" type="hidden" value="{{csrf}}">
<label>عنوان الدرس<input name="title" maxlength="160" required placeholder="مثال: تشخيص MAN TGS"></label>
<label>رابط الفيديو على يوتيوب<input name="url" type="url" maxlength="300" required placeholder="https://www.youtube.com/watch?v=..."></label>
<label>وصف مختصر<textarea name="description" maxlength="1500"></textarea></label>
<button type="submit">إضافة الفيديو</button>
</form></section>
<section><h2>الفيديوهات المضافة</h2>
<div class="grid">
{% for v in clips %}
<article class="card"><h3>{{v.title}}</h3><p>{{v.description}}</p>
<p class="muted">{{"منشور" if v.visible else "مخفي"}} · <a href="https://www.youtube.com/watch?v={{v.youtube_id}}" target="_blank" rel="noopener">فتح المصدر</a></p>
<form action="/admin/videos/{{v.id}}/toggle" method="post" style="display:inline">
<input type="hidden" name="csrf" value="{{csrf}}">
<button type="submit">{{"إخفاء" if v.visible else "نشر"}}</button></form>
<form action="/admin/videos/{{v.id}}/delete" method="post" style="display:inline" onsubmit="return confirm('هل تريد حذف هذا الفيديو من المتجر؟')">
<input type="hidden" name="csrf" value="{{csrf}}"><button type="submit">حذف</button></form>
</article>
{% else %}<p class="card">لم تضف فيديوهات بعد.</p>{% endfor %}
</div></section></div>""", title="إدارة الفيديوهات | SABER ACTROS DZ", clips=clips)

    @app.post("/admin/videos/new")
    @admin_only
    def add_video():
        title = request.form.get("title", "").strip()[:160]
        desc = request.form.get("description", "").strip()[:1500]
        video_id = video_id_from_link(request.form.get("url", "")[:300])
        if not title or not video_id:
            flash("الرجاء إدخال عنوان ورابط يوتيوب صالح.")
            return redirect("/admin/videos")
        d = DB()
        if d.scalar(select(Video.id).where(Video.youtube_id == video_id)):
            flash("هذا الفيديو موجود بالفعل.")
            return redirect("/admin/videos")
        d.add(Video(title=title, description=desc, youtube_id=video_id, visible=True))
        d.commit()
        flash("تمت إضافة الفيديو.")
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
