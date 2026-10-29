"""Workshop finder page, using location only with explicit browser consent."""
from flask import render_template_string


def setup_workshops_routes(app, page):
    @app.get("/workshops")
    def workshops():
        body = """<div class="container">
<section class="catalog-intro workshop-intro">
  <h1>🔧 ابحث عن أقرب ورشة إليك</h1>
  <p class="muted">اعثر على ورش صيانة الشاحنات والمركبات القريبة من موقعك، وتعرّف على المسافة التقريبية وافتح الاتجاهات في الخريطة.</p>
  <p class="muted">اضغط <b>«تحديد موقعي»</b> للسماح بذلك، أو اختر مكانًا بنفسك بالضغط على الخريطة. لا يطلب الموقع موقعك تلقائيًا.</p>
</section>

<section class="card" aria-label="البحث عن الورش القريبة">
  <div class="workshop-toolbar">
    <button id="workshop-locate" type="button" class="button">📍 تحديد موقعي والبحث</button>
    <button id="workshop-search" type="button" class="button" disabled>🔎 بحث حول النقطة المحددة</button>
    <label class="workshop-field">نوع الورشة
      <select id="workshop-type">
        <option value="all">جميع ورش الإصلاح</option>
        <option value="trucks">ورش الشاحنات والمعدات الثقيلة</option>
      </select>
    </label>
    <label class="workshop-field">نطاق البحث
      <select id="workshop-radius">
        <option value="5000">5 كم</option>
        <option value="10000" selected>10 كم</option>
        <option value="20000">20 كم</option>
        <option value="40000">40 كم</option>
      </select>
    </label>
  </div>
  <p class="workshop-note">تُستخدم إحداثيات الموقع للبحث عبر خدمات OpenStreetMap الخارجية فقط عند طلبك؛ لا يرسلها هذا البحث إلى خادم المتجر لتخزينها. المسافة المعروضة <b>خط مستقيم</b> وليست مسافة الطريق. النتائج بحسب البيانات المتاحة وقد لا تشمل جميع الورش.</p>
  <p id="workshop-status" class="workshop-status" role="status" aria-live="polite">للبدء: حدد موقعك أو اضغط موقعًا على الخريطة.</p>

  <div class="workshop-layout">
    <div id="workshop-map" role="region" aria-label="خريطة الورش القريبة"></div>
    <aside class="workshop-results" aria-label="نتائج البحث">
      <h2>الورش القريبة <small id="workshop-count"></small></h2>
      <div id="workshop-list"><p class="muted">ستظهر أقرب الورش هنا بعد البحث.</p></div>
      <a id="workshop-google" class="button workshop-google" href="https://www.google.com/maps/search/?api=1&amp;query=truck%20repair" rel="noopener noreferrer" target="_blank">البحث أيضًا في خرائط Google</a>
    </aside>
  </div>
  <p class="workshop-attribution">بيانات الخريطة ونتائج الورش: <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener noreferrer">© مساهمو OpenStreetMap</a>. تعتمد النتائج على توفر البيانات واتصال الإنترنت.</p>
</section>
</div>
<style>
.workshop-intro{margin-top:24px}
.workshop-toolbar{display:flex;gap:10px;flex-wrap:wrap;align-items:end;margin-bottom:15px}
.workshop-toolbar>.button{min-height:45px}
.workshop-toolbar>.button:disabled{opacity:.5;cursor:not-allowed}
.workshop-field{display:flex;flex-direction:column;gap:4px;min-width:155px;flex:1;font-size:.92rem}
.workshop-field select{margin:0;min-height:45px}
.workshop-note{font-size:.83rem;color:#b9d0df;line-height:1.75;margin:12px 0}
.workshop-status{font-size:.95rem;color:#cdeaf4;margin:12px 0;min-height:24px}
.workshop-status.error{color:#ffb4a9}
.workshop-layout{display:grid;grid-template-columns:minmax(0,1fr) 330px;gap:15px;align-items:start}
#workshop-map{height:530px;min-height:350px;border:1px solid #3b566e;border-radius:13px;overflow:hidden;background:#23384d;z-index:0}
#workshop-map .leaflet-container{font-family:system-ui,Arial}
#workshop-map .leaflet-popup-content{color:#172436;line-height:1.55}
.workshop-results{border:1px solid #395069;border-radius:13px;background:#101d2e;padding:16px;min-height:250px;max-height:530px;overflow:auto}
.workshop-results h2{font-size:1.2rem;margin:0 0 12px}
.workshop-result{border:1px solid #314b65;border-radius:11px;padding:11px;margin:0 0 10px;background:#182c40}
.workshop-result strong{display:block;color:#ffcf70;overflow-wrap:anywhere}
.workshop-result small{display:block;color:#b6cde0;margin-bottom:8px}
.workshop-result a{display:inline-flex;align-items:center;padding:6px 11px;background:#224e67;color:#e8f9ff;border-radius:8px;margin-top:4px}
.workshop-result button{margin-inline-start:8px;padding:6px 11px;font-size:.9rem}
.workshop-result.nearest{border-color:#e7c36e}
.workshop-google{display:block;text-align:center;margin-top:12px}
.workshop-attribution{font-size:.82rem;color:#b9c5d0;margin-top:12px}
@media(max-width:850px){.workshop-layout{grid-template-columns:1fr}#workshop-map{height:390px}.workshop-results{max-height:none}}
@media(max-width:500px){.workshop-field{min-width:130px}.workshop-toolbar>.button{flex:1 1 100%}#workshop-map{height:365px}}
</style>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js" defer></script>
<script src="/static/workshops.js?v=1" defer></script>"""
        return page(body, title="أقرب ورشة | SABER ACTROS DZ")
