/* SABER ACTROS DZ: only administrator-published workshops; visitor location remains client-side. */
(() => {
  "use strict";
  const get=id=>document.getElementById(id);
  const list=get("workshop-list"),dataNode=get("workshop-data");
  if(!list||!dataNode)return;
  let workshops=[];
  try{
    workshops=JSON.parse(dataNode.textContent).filter(w=>
      Number.isInteger(w.id)&&Number.isFinite(w.latitude)&&Number.isFinite(w.longitude)&&
      Math.abs(w.latitude)<=90&&Math.abs(w.longitude)<=180
    );
  }catch(err){workshops=[]}
  const count=get("workshop-count"),status=get("workshop-status");
  const locate=get("workshop-locate"),reset=get("workshop-reset");
  const query=get("workshop-query"),type=get("workshop-type");
  const mapElement=get("workshop-map");
  let map,pins,userPin,origin=null;
  const category={truck:"ورشة شاحنات",heavy:"معدات ثقيلة",mixed:"شاحنات ومعدات ثقيلة",car:"ورشة سيارات"};
  const info=(text,error=false)=>{status.textContent=text;status.classList.toggle("error",error)};
  const distance=(lat1,lon1,lat2,lon2)=>{
    const rad=Math.PI/180;
    const a=Math.sin((lat2-lat1)*rad/2)**2+
      Math.cos(lat1*rad)*Math.cos(lat2*rad)*Math.sin((lon2-lon1)*rad/2)**2;
    return 6371*2*Math.atan2(Math.sqrt(Math.max(0,a)),Math.sqrt(Math.max(0,1-a)));
  };
  const distanceLabel=km=>km<1?Math.round(km*1000)+" متر تقريبًا":km.toFixed(1)+" كم تقريبًا";
  const mapsURL=w=>"https://www.google.com/maps/dir/?api=1&destination="+
    encodeURIComponent(w.latitude+","+w.longitude);
  const telURL=raw=>{
    const digits=String(raw||"").replace(/\D/g,"");
    if(!digits)return "#";
    return "tel:"+(digits.startsWith("00")?"+"+digits.slice(2):String(raw).trim().startsWith("+")?"+"+digits:digits);
  };
  const element=(tag,text,cls,parent)=>{
    const node=document.createElement(tag);node.textContent=text;
    if(cls)node.className=cls;
    if(parent)parent.appendChild(node);
    return node;
  };
  const link=(text,url,parent)=>{
    const a=element("a",text,"",parent);
    a.href=url;
    if(/^https:/.test(url)){a.target="_blank";a.rel="noopener noreferrer"}
    return a;
  };
  const entries=()=> {
    const q=query.value.trim().toLocaleLowerCase("ar");
    let data=workshops.filter(w=>{
      if(type.value==="truck"&&w.category==="car")return false;
      if(type.value==="car"&&w.category!=="car")return false;
      if(q&&!([w.name,w.address,w.description].join(" ").toLocaleLowerCase("ar").includes(q)))return false;
      return true;
    }).map(w=>({...w,km:origin?distance(origin.lat,origin.lon,w.latitude,w.longitude):null}));
    if(origin)data.sort((a,b)=>a.km-b.km);
    else data.sort((a,b)=>a.name.localeCompare(b.name,"ar"));
    return data;
  };
  const popupFor=w=>{
    const div=document.createElement("div");
    element("strong",w.name,"",div);
    element("p",(w.address||"")+(origin?" · "+distanceLabel(distance(origin.lat,origin.lon,w.latitude,w.longitude)):""),"",div);
    link("الاتجاهات",mapsURL(w),div);
    return div;
  };
  const showOnMap=w=>{
    if(!map||!pins)return;
    map.setView([w.latitude,w.longitude],15);
    const marker=pins.get(w.id);
    if(marker)marker.openPopup();
  };
  const card=w=>{
    const article=element("article","","workshop-result"+(origin&&w===undefined?"":""));
    if(origin&&w.km===Math.min(...entries().map(x=>x.km)))article.classList.add("nearest");
    const image=document.createElement("img");
    image.className="workshop-result-image";image.alt="صورة "+w.name;
    image.loading="lazy";image.src="/workshops/"+w.id+"/photo";
    article.appendChild(image);
    element("strong",w.name,"",article);
    const summary=(category[w.category]||"ورشة")+(origin?" · "+distanceLabel(w.km):"");
    element("small",summary,"",article);
    element("small","📍 "+w.address,"",article);
    if(w.description)element("p",w.description,"",article);
    const phone=element("small","☎ ", "",article);
    const number=link(w.phone,telURL(w.phone),phone);
    number.className="workshop-result-phone";
    const actions=element("div","","workshop-actions",article);
    link("📞 اتصال",telURL(w.phone),actions);
    link("🧭 الاتجاهات",mapsURL(w),actions);
    const focus=element("button","على الخريطة","",actions);
    focus.type="button";
    focus.addEventListener("click",()=>showOnMap(w));
    return article;
  };
  const refresh=()=>{
    const data=entries();
    list.replaceChildren();
    count.textContent="("+data.length+")";
    if(!workshops.length){
      element("p","لا توجد ورش منشورة حتى الآن. ستظهر هنا الورش بعد إضافتها من إدارة المتجر.","muted",list);
      info("الدليل قيد الإعداد: لم تُضف الإدارة ورشًا منشورة بعد.");
      return;
    }
    if(!data.length){
      element("p","لا توجد ورش مطابقة للبحث أو النوع المختار. جرّب تعديل خيارات البحث.","muted",list);
      info("لا توجد نتائج مطابقة ضمن الورش المسجلة.");
      return;
    }
    data.forEach((w,i)=>{
      const row=card(w);
      if(i===0&&origin)row.classList.add("nearest");
      list.appendChild(row);
    });
    if(origin)info("أقرب ورشة مدرجة: "+data[0].name+" ("+distanceLabel(data[0].km)+"). المسافة بخط مستقيم.");
    else info("يتم عرض "+data.length+" ورشة مسجلة. اسمح بتحديد موقعك لترتيبها حسب المسافة.");
  };
  const renderMap=()=>{
    if(!window.L){
      mapElement.textContent="تعذّر تحميل الخريطة. تظهر قائمة الورش وأرقام التواصل أدناه.";
      return;
    }
    map=L.map(mapElement,{scrollWheelZoom:false}).setView([29,34],4);
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",{
      maxZoom:19,attribution:'© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
    }).addTo(map);
    pins=new Map();
    const bounds=[];
    workshops.forEach(w=>{
      const marker=L.marker([w.latitude,w.longitude]).addTo(map);
      marker.bindPopup(()=>popupFor(w));
      marker.on("click",ev=>{
        if(ev.originalEvent)L.DomEvent.stopPropagation(ev.originalEvent);
      });
      pins.set(w.id,marker);
      bounds.push([w.latitude,w.longitude]);
    });
    if(bounds.length===1)map.setView(bounds[0],12);
    else if(bounds.length>1)map.fitBounds(bounds,{padding:[30,30],maxZoom:11});
    map.on("click",event=>{
      setOrigin(event.latlng.lat,event.latlng.lng);
      info("اخترت نقطة على الخريطة. تم ترتيب الورش حسب قربها من تلك النقطة.");
    });
  };
  const setOrigin=(lat,lon)=>{
    if(!Number.isFinite(lat)||!Number.isFinite(lon))return;
    origin={lat,lon};
    if(map){
      if(!userPin)userPin=L.circleMarker([lat,lon],{radius:10,color:"#102f65",weight:3,
        fillColor:"#5ac7f3",fillOpacity:1}).addTo(map);
      else userPin.setLatLng([lat,lon]);
      map.setView([lat,lon],12);
    }
    refresh();
  };
  locate.addEventListener("click",()=>{
    if(!navigator.geolocation||!window.isSecureContext){
      info("لا يمكن تحديد موقعك في هذا المتصفح. اضغط نقطة على الخريطة لترتيب الورش دون مشاركة موقع الهاتف.",true);
      return;
    }
    locate.disabled=true;
    info("سيطلب هاتفك إذن مشاركة الموقع. يمكنك رفضه واختيار نقطة على الخريطة.");
    navigator.geolocation.getCurrentPosition(
      pos=>{
        locate.disabled=false;
        setOrigin(pos.coords.latitude,pos.coords.longitude);
      },
      err=>{
        locate.disabled=false;
        info(err.code===1?"لم تمنح إذن الموقع. يمكنك الاختيار بالنقر على الخريطة.":
          "تعذّر تحديد الموقع. اختر نقطة على الخريطة بدلًا من ذلك.",true);
      },
      {enableHighAccuracy:false,timeout:12000,maximumAge:0}
    );
  });
  reset.addEventListener("click",()=>{
    origin=null;query.value="";type.value="all";
    if(userPin&&map){map.removeLayer(userPin);userPin=null}
    refresh();
    if(map&&pins.size>0){
      const bounds=workshops.map(w=>[w.latitude,w.longitude]);
      bounds.length===1?map.setView(bounds[0],12):map.fitBounds(bounds,{padding:[30,30],maxZoom:11});
    }
  });
  query.addEventListener("input",refresh);
  type.addEventListener("change",refresh);
  renderMap();
  refresh();
})();