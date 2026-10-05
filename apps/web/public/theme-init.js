try {
  const t = localStorage.getItem("cosoup.theme");
  document.documentElement.dataset.theme =
    t === "light" || t === "dark"
      ? t
      : matchMedia("(prefers-color-scheme:dark)").matches
        ? "dark"
        : "light";
  document.documentElement.dataset.motion =
    localStorage.getItem("cosoup.motion") === "paused" ||
    matchMedia("(prefers-reduced-motion:reduce)").matches
      ? "off"
      : "on";
} catch {}
