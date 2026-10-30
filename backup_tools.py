"""Administrator-only backup, restore and storage diagnostics for SABER ACTROS DZ.

Backups are intentionally portable between SQLite and PostgreSQL. They contain
sensitive account/order data and must be stored privately by the administrator.
"""
import base64
import binascii
import io
import json
import os
import zipfile
from datetime import datetime, timezone

from flask import Response, flash, redirect, request, session, abort
from sqlalchemy import DateTime, LargeBinary, select, text, func

FORMAT_NAME = "SABER-ACTROS-DZ-DB-BACKUP"
FORMAT_VERSION = 1
MAX_UPLOAD = 64 * 1024 * 1024
MAX_JSON = 160 * 1024 * 1024


def encode_value(value):
    if isinstance(value, (bytes, bytearray, memoryview)):
        return {"binary_base64": base64.b64encode(bytes(value)).decode("ascii")}
    if isinstance(value, datetime):
        return {"datetime_iso": value.isoformat()}
    return value


def decode_value(column, value):
    if isinstance(column.type, LargeBinary):
        if not isinstance(value, dict) or set(value) != {"binary_base64"}:
            raise ValueError("Invalid binary value")
        try:
            return base64.b64decode(value["binary_base64"], validate=True)
        except (ValueError, binascii.Error):
            raise ValueError("Invalid binary encoding") from None
    if isinstance(column.type, DateTime):
        if value is None:
            return None
        if not isinstance(value, dict) or set(value) != {"datetime_iso"}:
            raise ValueError("Invalid datetime value")
        return datetime.fromisoformat(value["datetime_iso"])
    if isinstance(value, (dict, list)):
        raise ValueError("Unexpected complex value")
    return value


def create_payload(db, metadata):
    tables = {}
    for table in metadata.sorted_tables:
        records = db.execute(select(table)).mappings().all()
        tables[table.name] = [
            {column.name: encode_value(row[column.name]) for column in table.columns}
            for row in records
        ]
    return {
        "type": FORMAT_NAME,
        "version": FORMAT_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "tables": tables,
    }


def validate_payload(data, metadata):
    if not isinstance(data, dict) or data.get("type") != FORMAT_NAME or data.get("version") != FORMAT_VERSION:
        raise ValueError("صيغة النسخة الاحتياطية غير معروفة.")
    tables = data.get("tables")
    required = {t.name: t for t in metadata.sorted_tables}
    if not isinstance(tables, dict) or set(tables) != set(required):
        raise ValueError("النسخة الاحتياطية لا تطابق جداول المتجر.")
    clean = {}
    for name, table in required.items():
        records = tables[name]
        if not isinstance(records, list) or len(records) > 100_000:
            raise ValueError("عدد السجلات غير صالح.")
        columns = {c.name: c for c in table.columns}
        rows = []
        ids = set()
        for record in records:
            if not isinstance(record, dict) or set(record) != set(columns):
                raise ValueError("حقول السجلات غير صالحة.")
            row = {key: decode_value(columns[key], value) for key, value in record.items()}
            if "id" in row:
                if not isinstance(row["id"], int) or row["id"] < 1 or row["id"] in ids:
                    raise ValueError("معرّفات السجلات غير صالحة.")
                ids.add(row["id"])
            rows.append(row)
        clean[name] = rows
    return clean


def setup_backup_routes(app, Base, DB, engine, admin_only, page):
    # The per-image upload validator still limits individual images to 4MB.
    app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD + 1024 * 1024

    @app.get("/admin/storage")
    @admin_only
    def admin_storage():
        d = DB()
        status = "PostgreSQL" if engine.dialect.name == "postgresql" else "SQLite / " + engine.dialect.name
        temporary = bool(os.getenv("RENDER") and engine.dialect.name == "sqlite")
        counts = []
        for table in Base.metadata.sorted_tables:
            counts.append((table.name, d.scalar(select(func.count()).select_from(table))))
        return page("""<div class="container"><section class="card">
<h1>التخزين والنسخ الاحتياطي</h1><p>قاعدة البيانات المستخدمة: <strong>{{status}}</strong></p>
{% if temporary %}
<p style="color:#ffb4b4"><strong>تحذير: البيانات محفوظة داخل مساحة مؤقتة على Render وقد تختفي عند إعادة التشغيل أو النشر.</strong> احفظ نسخة الآن قبل أي تحديث.</p>
{% else %}<p>احفظ نسخة خارجية بشكل منتظم حتى مع وجود قاعدة بيانات مستقلة.</p>{% endif %}
<p><a class="button" href="/admin/backup">⬇ تنزيل نسخة احتياطية كاملة ZIP</a></p>
<p class="muted">النسخة تحتوي على بيانات العملاء وحساباتهم والمنتجات والصور والكتالوجات وملفات PDF وروابط الفيديوهات والورش. لا تشاركها علنًا.</p>
<h2>استعادة نسخة احتياطية</h2>
<p style="color:#ffb4b4">تنبيه: الاستعادة تستبدل <strong>جميع</strong> بيانات قاعدة البيانات الحالية. استخدمها فقط بعد تنزيل نسخة من البيانات الموجودة. تتم العملية في معاملة واحدة أو تُلغى دون استبدال البيانات.</p>
<form action="/admin/restore" method="post" enctype="multipart/form-data">
<input type="hidden" name="csrf" value="{{csrf}}">
<label>ملف النسخة الاحتياطية ZIP<input type="file" accept=".zip,application/zip" name="backup" required></label>
<label>اكتب RESTORE للموافقة على استبدال قاعدة البيانات<input name="confirmation" autocomplete="off" required></label>
<button type="submit" onclick="return confirm('هل أنت متأكد؟ ستُستبدل جميع البيانات الموجودة ببيانات النسخة الاحتياطية.')">استعادة قاعدة البيانات</button>
</form></section><section class="card"><h2>عدد السجلات لكل جدول</h2>
<div class="scroll"><table><tr><th>الجدول</th><th>عدد السجلات</th></tr>{% for name,n in counts %}<tr><td>{{name}}</td><td>{{n}}</td></tr>{% endfor %}</table></div>
</section></div>""", status=status, temporary=temporary, counts=counts,
                    title="التخزين والنسخ الاحتياطي | SABER ACTROS DZ")

    @app.get("/admin/backup")
    @admin_only
    def download_backup():
        data = create_payload(DB(), Base.metadata)
        content = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
            archive.writestr("store.json", content)
        filename = "SABER-ACTROS-DZ-" + datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S") + ".zip"
        return Response(buffer.getvalue(), mimetype="application/zip", headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff",
        })

    @app.post("/admin/restore")
    @admin_only
    def restore_backup():
        if request.form.get("confirmation") != "RESTORE":
            flash("لم يتم تأكيد الاستعادة؛ اكتب RESTORE حرفياً.")
            return redirect("/admin/storage")
        uploaded = request.files.get("backup")
        if not uploaded or not uploaded.filename.lower().endswith(".zip"):
            flash("اختر ملف ZIP صادر عن المتجر.")
            return redirect("/admin/storage")
        try:
            raw = uploaded.read(MAX_UPLOAD + 1)
            if len(raw) > MAX_UPLOAD:
                raise ValueError("حجم النسخة يتجاوز الحد 64MB.")
            with zipfile.ZipFile(io.BytesIO(raw), "r") as archive:
                if archive.namelist() != ["store.json"]:
                    raise ValueError("ملف النسخة غير صالح.")
                info = archive.getinfo("store.json")
                if info.file_size > MAX_JSON:
                    raise ValueError("النسخة كبيرة جداً للاستعادة المباشرة.")
                with archive.open(info) as source:
                    content = source.read(MAX_JSON + 1)
                if len(content) > MAX_JSON:
                    raise ValueError("النسخة كبيرة جداً للاستعادة المباشرة.")
            records = validate_payload(json.loads(content), Base.metadata)
        except (ValueError, UnicodeError, json.JSONDecodeError, zipfile.BadZipFile, OSError) as error:
            flash("تعذرت قراءة النسخة: " + str(error)[:140])
            return redirect("/admin/storage")
        d = DB()
        try:
            # Atomic transaction: all deletes and inserts are rolled back on failure.
            for table in reversed(Base.metadata.sorted_tables):
                d.execute(table.delete())
            for table in Base.metadata.sorted_tables:
                items = records[table.name]
                if items:
                    d.execute(table.insert(), items)
            if engine.dialect.name == "postgresql":
                for table in Base.metadata.sorted_tables:
                    if "id" not in table.columns:
                        continue
                    last = max((row["id"] for row in records[table.name]), default=0)
                    d.execute(text("SELECT setval(pg_get_serial_sequence(:table_name, 'id'), :value, :called)"),
                              {"table_name": table.name, "value": last if last else 1, "called": last > 0})
            d.commit()
        except Exception:
            d.rollback()
            app.logger.exception("Restore failed; database transaction rolled back")
            flash("فشلت الاستعادة؛ لم تُستبدل البيانات الحالية.")
            return redirect("/admin/storage")
        session.clear()
        flash("اكتملت الاستعادة. سجّل الدخول مجدداً.")
        return redirect("/login")