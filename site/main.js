(function () {
  "use strict";

  var root = document.documentElement;
  root.dataset.js = "";

  function $(selector) {
    return document.querySelector(selector);
  }

  var reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
  var prefersDark = window.matchMedia("(prefers-color-scheme: dark)");

  /* ---------- theme ---------- */

  var themeButton = $("#theme-toggle");
  var themeColors = { light: "#D6E8F4", dark: "#07141D" };

  function currentTheme() {
    var set = root.dataset.theme;
    if (set === "light" || set === "dark") return set;
    return prefersDark.matches ? "dark" : "light";
  }

  function syncThemeButton() {
    themeButton.setAttribute("aria-pressed", String(currentTheme() === "dark"));
  }

  function setTheme(theme) {
    root.dataset.theme = theme;
    try {
      localStorage.setItem("theme", theme);
    } catch (e) {}
    var metas = document.querySelectorAll('meta[name="theme-color"]');
    for (var i = 0; i < metas.length; i++) metas[i].setAttribute("content", themeColors[theme]);
    syncThemeButton();
  }

  function toggleTheme() {
    setTheme(currentTheme() === "dark" ? "light" : "dark");
  }

  themeButton.addEventListener("click", toggleTheme);
  if (prefersDark.addEventListener) prefersDark.addEventListener("change", syncThemeButton);
  syncThemeButton();

  /* ---------- Baerum clock ---------- */

  var clock = $("#clock");
  var clockFormat = null;
  try {
    clockFormat = new Intl.DateTimeFormat("en-GB", {
      timeZone: "Europe/Oslo",
      hour: "2-digit",
      minute: "2-digit",
      hourCycle: "h23"
    });
  } catch (e) {}

  function tick() {
    var time = clockFormat.format(new Date());
    clock.textContent = time;
    clock.setAttribute("datetime", time);
  }

  if (clockFormat) {
    tick();
    window.setInterval(tick, 30000);
  } else {
    clock.parentNode.parentNode.hidden = true;
  }

  /* ---------- Haugesund weather (Open-Meteo) ---------- */

  var WEATHER_URL =
    "https://api.open-meteo.com/v1/forecast?latitude=59.4138&longitude=5.268" +
    "&current=temperature_2m,weather_code,wind_speed_10m,wind_direction_10m,is_day" +
    "&wind_speed_unit=ms&timezone=Europe%2FOslo";

  var COMPASS = ["north", "northeast", "east", "southeast", "south", "southwest", "west", "northwest"];

  function describe(code, isDay) {
    if (code === 0) return isDay ? "Sunny" : "Clear";
    if (code === 1) return isDay ? "Mostly sunny" : "Mostly clear";
    if (code === 2) return "Partly cloudy";
    if (code === 3) return "Overcast";
    if (code === 45 || code === 48) return "Fog";
    if (code >= 51 && code <= 55) return "Drizzle";
    if (code === 56 || code === 57) return "Freezing drizzle";
    if (code === 61) return "Light rain";
    if (code === 63) return "Rain";
    if (code === 65) return "Heavy rain";
    if (code === 66 || code === 67) return "Freezing rain";
    if (code === 71) return "Light snow";
    if (code === 73) return "Snow";
    if (code === 75) return "Heavy snow";
    if (code === 77) return "Snow grains";
    if (code >= 80 && code <= 82) return "Showers";
    if (code === 85 || code === 86) return "Snow showers";
    if (code === 95) return "Thunderstorm";
    if (code === 96 || code === 99) return "Thunderstorm with hail";
    return "Weather unknown";
  }

  var wx = $("#wx");
  var wxTemp = $("#wx-temp");
  var wxText = $("#wx-text");
  var wxCaption = $("#wx-cap");
  var wxBarb = $("#wx-barb");
  var wxIcon = $("#wx-icon");

  function weatherFailed() {
    wx.dataset.state = "error";
    wxText.textContent = "No weather right now";
    wxCaption.textContent = "Couldn't reach the weather service.";
  }

  function showWeather(current) {
    var temperature = current.temperature_2m;
    var speed = current.wind_speed_10m;
    var from = current.wind_direction_10m;
    var code = current.weather_code;
    if (![temperature, speed, from, code].every(Number.isFinite) || from < 0 || from > 360) {
      weatherFailed();
      return;
    }
    var rounded = Math.round(temperature);
    wxTemp.textContent = (Object.is(rounded, -0) ? 0 : rounded) + "°";
    var text = describe(code, current.is_day === 1) + ", wind " + Math.round(speed) + " m/s";
    wxText.textContent = text;
    wxIcon.removeAttribute("aria-hidden");
    wxIcon.setAttribute("role", "img");
    wxIcon.setAttribute("aria-label", "Wind from the " + COMPASS[Math.round(from / 45) % 8]);
    wxBarb.setAttribute("transform", "translate(24 24) rotate(" + from + ") scale(1.12)");
    wxBarb.setAttribute("data-deg", String(from));
    wx.dataset.state = "ok";
  }

  function loadWeather() {
    if (typeof fetch !== "function" || typeof AbortController !== "function") {
      weatherFailed();
      return;
    }
    var controller = new AbortController();
    var timer = window.setTimeout(function () {
      controller.abort();
    }, 6000);
    fetch(WEATHER_URL, { signal: controller.signal, credentials: "omit", referrerPolicy: "no-referrer" })
      .then(function (response) {
        if (!response.ok) throw new Error("HTTP " + response.status);
        return response.json();
      })
      .then(function (data) {
        showWeather(data.current);
      })
      .catch(weatherFailed)
      .then(function () {
        window.clearTimeout(timer);
      });
  }

  loadWeather();

  /* ---------- herring ---------- */

  var school = $("#school");
  var schoolInner = school.querySelector(".d02-school-in");
  var status = $("#sild-status");
  var statusTimer = 0;

  function say(message, visible) {
    window.clearTimeout(statusTimer);
    status.textContent = "";
    status.classList.toggle("is-sr", !visible);
    window.setTimeout(function () {
      status.textContent = message;
    }, 50);
    statusTimer = window.setTimeout(function () {
      status.textContent = "";
    }, 9000);
  }

  function inView(el) {
    var box = el.getBoundingClientRect();
    return box.bottom > 0 && box.top < window.innerHeight;
  }

  var herringButton = $("#sild-btn");

  function releaseHerring() {
    if (reduceMotion.matches) {
      say("A school of herring just swam past. Motion is off, so you'll have to take my word for it.", true);
      if (!inView(herringButton)) herringButton.scrollIntoView({ block: "center", behavior: "auto" });
      return;
    }
    school.classList.remove("d02-swim-a");
    void school.offsetWidth;
    school.classList.add("d02-swim-a");
    say("A school of herring swims across the page.", false);
    if (!inView(school)) school.scrollIntoView({ block: "center", behavior: "smooth" });
  }

  schoolInner.addEventListener("animationend", function () {
    school.classList.remove("d02-swim-a");
  });
  herringButton.addEventListener("click", releaseHerring);

  /* ---------- jump menu ---------- */

  var jump = $("#jump");
  var jumpButton = $("#jump-btn");
  var jumpKbd = $("#jump-kbd");

  if (typeof jump.showModal !== "function") {
    jumpButton.parentNode.hidden = true;
  } else {
    var platform = (navigator.userAgentData && navigator.userAgentData.platform) || navigator.platform || "";
    jumpKbd.textContent = /mac|iphone|ipad/i.test(platform) ? "⌘K" : "Ctrl K";

    var items = Array.prototype.slice.call(jump.querySelectorAll("a, button"));

    jumpButton.addEventListener("click", function () {
      if (!jump.open) jump.showModal();
    });

    jump.addEventListener("click", function (event) {
      if (event.target === jump) {
        var box = jump.getBoundingClientRect();
        var outside =
          event.clientX < box.left || event.clientX > box.right || event.clientY < box.top || event.clientY > box.bottom;
        if (outside) jump.close();
        return;
      }
      var item = event.target.closest("a, button");
      if (!item) return;
      jump.close();
      var action = item.getAttribute("data-act");
      if (action === "theme") toggleTheme();
      if (action === "herring") releaseHerring();
    });

    jump.addEventListener("keydown", function (event) {
      var index = items.indexOf(document.activeElement);
      var next = -1;
      if (event.key === "ArrowDown") next = (index + 1) % items.length;
      else if (event.key === "ArrowUp") next = (index - 1 + items.length) % items.length;
      else if (event.key === "Home") next = 0;
      else if (event.key === "End") next = items.length - 1;
      if (next >= 0) {
        event.preventDefault();
        items[next].focus();
      }
    });
  }

  /* ---------- keyboard: Cmd/Ctrl K, "/" and typing sild ---------- */

  var typed = "";
  var typedTimer = 0;

  function isTyping(target) {
    return !!target && (target.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(target.tagName));
  }

  document.addEventListener("keydown", function (event) {
    if (event.defaultPrevented || event.isComposing || !event.key) return;
    var canJump = typeof jump.showModal === "function";
    var key = event.key.toLowerCase();

    if ((event.metaKey || event.ctrlKey) && !event.altKey && key === "k") {
      if (!canJump) return;
      event.preventDefault();
      if (jump.open) jump.close();
      else jump.showModal();
      return;
    }
    if (event.metaKey || event.ctrlKey || event.altKey) return;
    if (jump.open || isTyping(event.target)) return;

    if (key === "/" && canJump && jumpButton.offsetParent !== null) {
      event.preventDefault();
      jump.showModal();
      return;
    }
    if (key.length === 1) {
      typed = (typed + key).slice(-4);
      window.clearTimeout(typedTimer);
      typedTimer = window.setTimeout(function () {
        typed = "";
      }, 1500);
      if (typed === "sild") {
        typed = "";
        releaseHerring();
      }
    }
  });
})();
