(() => {
  "use strict";

  if (document.querySelector(".site-hero")) {
    document.body.classList.add("landing-page");
  }

  const match = window.location.pathname.match(/\/(en|ja)\/(.*)$/);
  if (!match) {
    return;
  }

  const currentLanguage = match[1];
  const pagePath = match[2] || "index.html";
  const basePath = window.location.pathname.slice(0, match.index + 1);
  const labels = { en: "EN", ja: "日本語" };
  const names = { en: "View this page in English", ja: "このページを日本語で表示" };
  const switcher = document.createElement("nav");
  switcher.className = "language-switcher";
  switcher.setAttribute("aria-label", "Language / 言語");

  for (const language of ["en", "ja"]) {
    const link = document.createElement("a");
    link.href = `${basePath}${language}/${pagePath}`;
    link.lang = language;
    link.textContent = labels[language];
    link.setAttribute("aria-label", names[language]);
    if (language === currentLanguage) {
      link.setAttribute("aria-current", "page");
    }
    link.addEventListener("click", () => window.localStorage.setItem("emi-guardian-language", language));
    switcher.append(link);
  }

  document.documentElement.lang = currentLanguage;
  document.body.append(switcher);
})();
