/* SABER ACTROS DZ: home-screen installation with clear device guidance. */
(() => {
  "use strict";
  let deferredInstall = null;
  const isInstalled = () =>
    window.matchMedia("(display-mode: standalone)").matches ||
    window.navigator.standalone === true;

  function markInstalled() {
    if (isInstalled()) document.documentElement.classList.add("store-installed");
  }
  function guidance(button, message) {
    let hint = button.nextElementSibling;
    if (!hint || !hint.classList.contains("install-help")) {
      hint = document.createElement("div");
      hint.className = "install-help";
      hint.setAttribute("role", "status");
      button.insertAdjacentElement("afterend", hint);
    }
    hint.textContent = message;
  }

  window.addEventListener("beforeinstallprompt", event => {
    event.preventDefault();
    deferredInstall = event;
  });
  window.addEventListener("appinstalled", () => {
    deferredInstall = null;
    document.documentElement.classList.add("store-installed");
  });
  window.installStoreApp = async button => {
    if (isInstalled()) {
      guidance(button, "المتجر مُثبّت بالفعل ويمكنك فتحه من شاشة هاتفك الرئيسية.");
      return;
    }
    if (deferredInstall) {
      const prompt = deferredInstall;
      deferredInstall = null;
      try {
        await prompt.prompt();
        const choice = await prompt.userChoice;
        if (choice && choice.outcome === "accepted") {
          document.documentElement.classList.add("store-installed");
          return;
        }
      } catch (error) {
        // Continue with manual browser instructions below.
      }
    }
    const agent = navigator.userAgent || "";
    const isiOS = /iPhone|iPad|iPod/i.test(agent) ||
      (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
    const instructions = isiOS
      ? "على الآيفون: افتح الموقع في Safari، ثم اضغط مشاركة واختر «إضافة إلى الشاشة الرئيسية»، ثم «إضافة»."
      : /Android/i.test(agent)
        ? "على أندرويد: افتح الموقع في Chrome، ثم اضغط القائمة ⋮ واختر «تثبيت التطبيق» أو «إضافة إلى الشاشة الرئيسية»."
        : "على الكمبيوتر: افتح الموقع في Chrome أو Edge، ثم اختر «تثبيت التطبيق» من قائمة المتصفح.";
    guidance(button, instructions);
  };

  if (navigator.serviceWorker && window.isSecureContext) {
    window.addEventListener("load", () => {
      navigator.serviceWorker.register("/service-worker.js", {scope:"/"})
        .catch(() => { /* Website remains usable without a service worker. */ });
    });
  }
  markInstalled();
})();