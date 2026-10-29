/* Admin map picker: click a point to fill coordinates for a workshop. */
(() => {
  "use strict";
  const div=document.getElementById("workshop-admin-map");
  const lat=document.getElementById("workshop-latitude");
  const lon=document.getElementById("workshop-longitude");
  if(!div||!lat||!lon)return;
  if(!window.L){
    div.textContent="تعذّر تحميل الخريطة. أدخل الإحداثيات يدويًا من خرائط Google.";
    return;
  }
  const map=L.map(div,{scrollWheelZoom:false}).setView([29,34],3);
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",{
    maxZoom:19,attribution:'© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
  }).addTo(map);
  let pin;
  const marker=(latitude,longitude,zoom)=>{
    if(!Number.isFinite(latitude)||!Number.isFinite(longitude)||
       latitude>90||latitude< -90||longitude>180||longitude< -180)return;
    if(!pin){
      pin=L.marker([latitude,longitude],{draggable:true}).addTo(map);
      pin.on("dragend",()=>{
        const c=pin.getLatLng();
        lat.value=c.lat.toFixed(6);
        lon.value=c.lng.toFixed(6);
      });
    }else pin.setLatLng([latitude,longitude]);
    map.setView([latitude,longitude],zoom||map.getZoom());
  };
  const set=(latitude,longitude)=>{
    lat.value=latitude.toFixed(6);
    lon.value=longitude.toFixed(6);
    marker(latitude,longitude,Math.max(map.getZoom(),10));
  };
  map.on("click",event=>set(event.latlng.lat,event.latlng.lng));
  function updateFromFields(){
    if(lat.value.trim()===""||lon.value.trim()==="")return;
    const latitude=Number(lat.value),longitude=Number(lon.value);
    marker(latitude,longitude);
  }
  lat.addEventListener("change",updateFromFields);
  lon.addEventListener("change",updateFromFields);
  document.querySelectorAll("[data-place]").forEach(button=>{
    button.addEventListener("click",()=>{
      const preset=button.dataset.place==="dz"?[36.70,3.06]:[24.71,46.67];
      map.setView(preset,6);
    });
  });
  updateFromFields();
  if(pin)map.setZoom(14);
})();