/* SABER ACTROS DZ nearby workshops. Browser permission only, location is not stored. */
(() => {
  "use strict";
  const $=id=>document.getElementById(id);
  const status=$("workshop-status"),locate=$("workshop-locate"),search=$("workshop-search");
  const radius=$("workshop-radius"),type=$("workshop-type"),list=$("workshop-list");
  const count=$("workshop-count"),google=$("workshop-google"),mapElement=$("workshop-map");
  if(!status||!locate||!search||!list)return;
  let map,userPin,markers,selected,busy=false;
  const providers=["https://overpass.private.coffee/api/interpreter","https://overpass-api.de/api/interpreter"];
  const valid=(lat,lon)=>Number.isFinite(lat)&&Number.isFinite(lon)&&Math.abs(lat)<=90&&Math.abs(lon)<=180;
  const inform=(msg,error=false)=>{status.textContent=msg;status.classList.toggle("error",error)};
  const distance=(a,b,c,d)=>{
    const rad=Math.PI/180;
    const x=Math.sin((c-a)*rad/2)**2+Math.cos(a*rad)*Math.cos(c*rad)*Math.sin((d-b)*rad/2)**2;
    return 6371*2*Math.asin(Math.min(1,Math.sqrt(Math.max(0,x))));
  };
  const kmLabel=km=>km<1?Math.round(km*1000)+" متر تقريبًا":km.toFixed(1)+" كم تقريبًا";
  const directions=(lat,lon)=>"https://www.google.com/maps/dir/?api=1&destination="+encodeURIComponent(lat+","+lon);
  const googleLink=()=>{
    const term=type.value==="trucks"?"truck repair":"vehicle repair workshop";
    const query=selected?term+" near "+selected.lat.toFixed(5)+","+selected.lon.toFixed(5):term;
    return "https://www.google.com/maps/search/?api=1&query="+encodeURIComponent(query);
  };
  const updateGoogle=()=>{google.href=googleLink()};
  const clear=()=>{list.replaceChildren();count.textContent="";if(markers)markers.clearLayers()};
  const select=(lat,lon,zoom=12)=>{
    if(!valid(lat,lon))return;
    selected={lat,lon};
    if(map){
      if(!userPin)userPin=L.circleMarker([lat,lon],{radius:10,color:"#124687",weight:3,fillColor:"#51c2ef",fillOpacity:1}).addTo(map);
      else userPin.setLatLng([lat,lon]);
      map.setView([lat,lon],zoom);
    }
    search.disabled=false;clear();updateGoogle();
    inform("تم تحديد نقطة البحث. اضغط «بحث حول النقطة المحددة» لإظهار الورش.");
  };
  const isTruck=tags=>{
    const text=[tags.name,tags["name:ar"],tags.description,tags["service"],tags.operator].filter(Boolean).join(" ");
    return tags.shop==="truck_repair"||tags["service:vehicle:truck"]==="yes"||tags["truck:repair"]==="yes"||
      /شاحنات|شاحنة|معدات ثقيلة|ديزل|truck|lorry|diesel|heavy vehicles|camion|poids lourds/i.test(text);
  };
  const parse=(raw,point)=>{
    const lat=Number(raw.lat??raw.center?.lat),lon=Number(raw.lon??raw.center?.lon);
    if(!valid(lat,lon)||!raw.tags)return null;
    const t=raw.tags;
    return {
      id:raw.type+"/"+raw.id,lat,lon,
      name:String(t["name:ar"]||t.name||t["name:en"]||"ورشة صيانة (اسم غير متوفر)").slice(0,120),
      km:distance(point.lat,point.lon,lat,lon),
      truck:isTruck(t),category:t.shop==="truck_repair"?"ورشة شاحنات":"ورشة صيانة مركبات",
      address:[t["addr:street"],t["addr:city"]].filter(Boolean).join("، ").slice(0,120)
    };
  };
  const addText=(tag,text,className,parent)=>{
    const el=document.createElement(tag);el.textContent=text;
    if(className)el.className=className;
    parent.appendChild(el);return el;
  };
  const showResults=all=>{
    clear();
    const found=all.filter(x=>type.value!=="trucks"||x.truck).sort((a,b)=>a.km-b.km).slice(0,35);
    count.textContent="("+found.length+")";
    if(!found.length){
      addText("p",type.value==="trucks"?
        "لا توجد ورش شاحنات مصنّفة في هذه المنطقة ضمن قاعدة البيانات. جرّب جميع الورش أو خرائط Google.":
        "لم تُسجّل ورش مطابقة ضمن المسافة المحددة. جرّب نطاقًا أوسع أو خرائط Google.","muted",list);
      inform("اكتمل البحث، ولا توجد نتائج مطابقة في البيانات المتاحة.");return;
    }
    found.forEach((workshop,i)=>{
      const card=document.createElement("div");
      card.className="workshop-result"+(i===0?" nearest":"");
      addText("strong",workshop.name,"",card);
      addText("small",(i===0?"الأقرب · ":"")+workshop.category+" · "+kmLabel(workshop.km),"",card);
      if(workshop.address)addText("small",workshop.address,"",card);
      const dir=document.createElement("a");
      dir.href=directions(workshop.lat,workshop.lon);dir.target="_blank";dir.rel="noopener noreferrer";dir.textContent="الاتجاهات";
      card.appendChild(dir);
      const focus=document.createElement("button");
      focus.type="button";focus.className="copy-link";focus.textContent="على الخريطة";
      focus.addEventListener("click",()=>{
        if(map)map.setView([workshop.lat,workshop.lon],15);
        const marker=markers&&markers.getLayers().find(m=>m.options.workshopId===workshop.id);
        if(marker)marker.openPopup();
      });
      card.appendChild(focus);list.appendChild(card);
      if(map&&markers){
        const pin=L.marker([workshop.lat,workshop.lon],{workshopId:workshop.id});
        const popup=document.createElement("div");
        addText("strong",workshop.name,"",popup);
        addText("p",kmLabel(workshop.km),"",popup);
        const link=document.createElement("a");link.href=dir.href;link.target="_blank";link.rel="noopener noreferrer";link.textContent="الاتجاهات";
        popup.appendChild(link);pin.bindPopup(popup);pin.addTo(markers);
      }
    });
    inform("تم العثور على "+found.length+" ورشة مرتبة حسب المسافة بخط مستقيم.");
  };
  const query=(pt,meters)=>{
    const near="around:"+meters+","+pt.lat.toFixed(6)+","+pt.lon.toFixed(6);
    return "[out:json][timeout:22];(nwr("+near+")[\"shop\"=\"car_repair\"];nwr("+near+")[\"shop\"=\"truck_repair\"];nwr("+near+")[\"craft\"=\"car_repair\"];nwr("+near+")[\"service:vehicle:truck\"=\"yes\"];);out center 120;";
  };
  const fetchTimeout=async url=>{
    const controller=new AbortController();
    const timer=setTimeout(()=>controller.abort(),14000);
    try{
      const res=await fetch(url,{mode:"cors",credentials:"omit",signal:controller.signal,headers:{"Accept":"application/json"}});
      if(!res.ok)throw Error("HTTP "+res.status);
      const data=await res.json();
      if(!data||!Array.isArray(data.elements))throw Error("Unexpected data");
      return data.elements;
    }finally{clearTimeout(timer)}
  };
  const findNearby=async()=>{
    if(!selected||busy)return;
    busy=true;search.disabled=true;locate.disabled=true;clear();
    inform("جارٍ البحث عن الورش المسجلة في المنطقة...");
    const pt={...selected},data=query(pt,Number(radius.value));
    let rows=null;
    for(const provider of providers){
      try{
        const entries=await fetchTimeout(provider+"?data="+encodeURIComponent(data));
        const unique=new Map();
        for(const entry of entries){
          const w=parse(entry,pt);
          if(w&&w.km<=Number(radius.value)/1000&&!unique.has(w.id))unique.set(w.id,w);
        }
        rows=[...unique.values()];break;
      }catch(err){/* Try the next provider; external service can be temporarily unavailable. */}
    }
    if(rows)showResults(rows);
    else{
      addText("p","خدمة بيانات الورش لا تستجيب حاليًا. يمكنك فتح البحث البديل في خرائط Google.","muted",list);
      inform("تعذّر الاتصال ببيانات الورش. أعد المحاولة أو استخدم خرائط Google.",true);
    }
    busy=false;search.disabled=false;locate.disabled=false;
  };
  if(window.L){
    map=L.map(mapElement,{scrollWheelZoom:false}).setView([24.7,46.7],5);
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",{
      maxZoom:18,attribution:'© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
    }).addTo(map);
    markers=L.layerGroup().addTo(map);
    map.on("click",event=>select(event.latlng.lat,event.latlng.lng,12));
  }else{
    mapElement.textContent="تعذّر تحميل الخريطة. استخدم رابط خرائط Google أدناه للبحث.";
    inform("تعذّر تحميل الخريطة؛ تأكد من الإنترنت ثم أعد فتح الصفحة.",true);
  }
  updateGoogle();
  search.addEventListener("click",findNearby);
  type.addEventListener("change",()=>{updateGoogle();if(selected)findNearby()});
  radius.addEventListener("change",()=>{if(selected)findNearby()});
  locate.addEventListener("click",()=>{
    if(!window.isSecureContext||!navigator.geolocation){
      inform("تحديد الموقع غير متاح. افتح المتجر عبر HTTPS أو اختر نقطة على الخريطة.",true);return;
    }
    locate.disabled=true;inform("سيطلب المتصفح إذن مشاركة موقعك لهذا البحث...");
    navigator.geolocation.getCurrentPosition(
      pos=>{locate.disabled=false;select(pos.coords.latitude,pos.coords.longitude,13);findNearby()},
      err=>{locate.disabled=false;inform(err.code===1?
        "تم رفض مشاركة الموقع. يمكنك اختيار نقطة على الخريطة بدلًا منها.":
        "تعذّر تحديد موقعك. اختر نقطة على الخريطة للبحث.",true)},
      {enableHighAccuracy:false,timeout:12000,maximumAge:0}
    );
  });
})();