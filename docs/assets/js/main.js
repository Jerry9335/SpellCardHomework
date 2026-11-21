/* =========================================================
   符卡作业簿 · 官网脚本
   樱花飘落 / 导航 / 入场动画 / 复制校验和
   ========================================================= */
(function () {
  "use strict";

  var reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  /* ------------------------------ 樱花 ------------------------------ */
  function initPetals() {
    var canvas = document.getElementById("petals");
    if (!canvas || reduceMotion) return;

    var ctx = canvas.getContext("2d");
    var dpr = Math.min(window.devicePixelRatio || 1, 2);
    var w = 0, h = 0;
    var petals = [];
    var COLORS = ["#f3b6c8", "#f7c9d6", "#e8a0b8", "#fbe3ea"];

    function resize() {
      w = window.innerWidth;
      h = window.innerHeight;
      canvas.width = Math.floor(w * dpr);
      canvas.height = Math.floor(h * dpr);
      canvas.style.width = w + "px";
      canvas.style.height = h + "px";
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      var count = Math.round(Math.min(70, Math.max(26, w / 28)));
      petals = [];
      for (var i = 0; i < count; i++) petals.push(newPetal(true));
    }

    function newPetal(spread) {
      return {
        x: Math.random() * w,
        y: spread ? Math.random() * h : -20,
        r: 3 + Math.random() * 5,
        vx: -0.35 + Math.random() * 0.7,
        vy: 0.5 + Math.random() * 1.2,
        rot: Math.random() * Math.PI * 2,
        vr: (-1 + Math.random() * 2) * 0.02,
        sway: Math.random() * Math.PI * 2,
        swaySpeed: 0.01 + Math.random() * 0.02,
        alpha: 0.35 + Math.random() * 0.5,
        color: COLORS[(Math.random() * COLORS.length) | 0]
      };
    }

    function drawPetal(p) {
      ctx.save();
      ctx.translate(p.x, p.y);
      ctx.rotate(p.rot);
      ctx.globalAlpha = p.alpha;
      ctx.fillStyle = p.color;
      ctx.beginPath();
      ctx.ellipse(0, 0, p.r, p.r * 0.55, 0, 0, Math.PI * 2);
      ctx.fill();
      // 花瓣缺口
      ctx.globalCompositeOperation = "destination-out";
      ctx.beginPath();
      ctx.ellipse(p.r * 0.9, 0, p.r * 0.42, p.r * 0.3, 0, 0, Math.PI * 2);
      ctx.fill();
      ctx.restore();
    }

    function tick() {
      ctx.clearRect(0, 0, w, h);
      for (var i = 0; i < petals.length; i++) {
        var p = petals[i];
        p.sway += p.swaySpeed;
        p.x += p.vx + Math.sin(p.sway) * 0.6;
        p.y += p.vy;
        p.rot += p.vr;
        if (p.y > h + 24 || p.x < -40 || p.x > w + 40) {
          petals[i] = newPetal(false);
        } else {
          drawPetal(p);
        }
      }
      requestAnimationFrame(tick);
    }

    window.addEventListener("resize", function () {
      clearTimeout(resize._t);
      resize._t = setTimeout(resize, 150);
    });
    resize();
    requestAnimationFrame(tick);
  }

  /* ------------------------------ 导航 ------------------------------ */
  function updateActiveNav() {
    var path = location.pathname.split("/").pop() || "index.html";
    document.querySelectorAll(".nav-links a").forEach(function (a) {
      var href = a.getAttribute("href");
      a.classList.remove("active");
      if (!href || href.charAt(0) === "#" || href.indexOf("http") === 0) return;
      var target = href.split("#")[0];
      if (target === path || (path === "" && target === "index.html")) {
        a.classList.add("active");
      }
    });
  }

  function initNav() {
    var header = document.querySelector(".site-header");
    var toggle = document.querySelector(".nav-toggle");
    var links = document.querySelector(".nav-links");

    if (header) {
      var onScroll = function () {
        if (window.scrollY > 12) header.classList.add("scrolled");
        else header.classList.remove("scrolled");
      };
      window.addEventListener("scroll", onScroll, { passive: true });
      onScroll();
    }

    if (toggle && links) {
      toggle.addEventListener("click", function () {
        links.classList.toggle("open");
        toggle.setAttribute("aria-expanded", links.classList.contains("open") ? "true" : "false");
      });
    }

    // 当前页高亮
    var path = location.pathname.split("/").pop() || "index.html";
    document.querySelectorAll(".nav-links a").forEach(function (a) {
      var href = a.getAttribute("href");
      if (!href || href.charAt(0) === "#" || href.indexOf("http") === 0) return;
      if (href === path || (path === "" && href === "index.html")) {
        a.classList.add("active");
      }
    });
  }

  /* ------------------------------ 入场动画 ------------------------------ */
  function initReveal() {
    var items = document.querySelectorAll(".reveal");
    if (!items.length) return;
    if (!("IntersectionObserver" in window) || reduceMotion) {
      items.forEach(function (el) { el.classList.add("visible"); });
      return;
    }
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) {
          entry.target.classList.add("visible");
          io.unobserve(entry.target);
        }
      });
    }, { threshold: 0.12, rootMargin: "0px 0px -8% 0px" });
    items.forEach(function (el) { io.observe(el); });
  }

  /* ------------------------------ 复制 ------------------------------ */
  function initCopy() {
    document.querySelectorAll("[data-copy]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var text = btn.getAttribute("data-copy");
        var done = function () {
          var old = btn.textContent;
          btn.textContent = "已复制";
          setTimeout(function () { btn.textContent = old; }, 1400);
        };
        if (navigator.clipboard && navigator.clipboard.writeText) {
          navigator.clipboard.writeText(text).then(done, function () {});
        } else {
          var ta = document.createElement("textarea");
          ta.value = text;
          ta.style.position = "fixed";
          ta.style.opacity = "0";
          document.body.appendChild(ta);
          ta.select();
          try { document.execCommand("copy"); done(); } catch (e) {}
          document.body.removeChild(ta);
        }
      });
    });
  }

  /* ------------------------------ 年份 ------------------------------ */
  function initYear() {
    document.querySelectorAll("[data-year]").forEach(function (el) {
      el.textContent = new Date().getFullYear();
    });
  }

  /* ------------------------------ 背景音乐 ------------------------------ */
  var BGM_KEY = "spellcard-bgm-v1";
  var BGM_TRACKS = [
    { src: "assets/audio/bgm-1.mp3", name: "曲目一" },
    { src: "assets/audio/bgm-2.mp3", name: "曲目二" }
  ];

  function readBgmState() {
    try {
      var raw = sessionStorage.getItem(BGM_KEY);
      if (!raw) return null;
      var s = JSON.parse(raw);
      return s && typeof s === "object" ? s : null;
    } catch (e) {
      return null;
    }
  }

  function saveBgmState(state) {
    try { sessionStorage.setItem(BGM_KEY, JSON.stringify(state)); } catch (e) {}
  }

  function initBgm() {
    // 每次真正打开/刷新页面都重新随机一首；站内无刷新换页不会重跑这里
    var index = Math.floor(Math.random() * BGM_TRACKS.length);
    var desired = true;
    var pendingTime = 0;

    var audio = new Audio();
    audio.preload = "auto";
    audio.volume = 0.5;
    audio.loop = false;
    audio.autoplay = true;
    audio.setAttribute("playsinline", "");
    audio.src = BGM_TRACKS[index].src;

    var player = document.createElement("div");
    player.className = "bgm-player";
    player.id = "bgm-player";
    player.innerHTML = [
      '<button class="bgm-disc" type="button" aria-label="播放背景音乐" title="点一下播放 / 暂停">',
      '  <span class="bgm-hole" aria-hidden="true"></span>',
      '</button>',
      '<button class="bgm-next" type="button" aria-label="下一首" title="下一首">⏭</button>',
      '<span class="bgm-tip" aria-live="polite">背景音乐</span>'
    ].join("");
    document.body.appendChild(player);
    // 把 audio 挂到 DOM 里（隐藏），方便调试和检查播放状态
    audio.style.display = "none";
    audio.setAttribute("aria-hidden", "true");
    player.appendChild(audio);

    var disc = player.querySelector(".bgm-disc");
    var nextBtn = player.querySelector(".bgm-next");
    var tip = player.querySelector(".bgm-tip");
    var restored = false;
    var lastSave = 0;

    function persist(force) {
      var now = Date.now();
      if (!force && now - lastSave < 900) return;
      lastSave = now;
      saveBgmState({ index: index, time: audio.currentTime || 0, playing: desired });
    }

    function updateUi() {
      var playing = !audio.paused;
      player.classList.toggle("playing", playing);
      player.classList.toggle("needs-tap", !playing && desired);
      disc.setAttribute("aria-label", playing ? "暂停背景音乐" : "播放背景音乐");
      if (playing) {
        tip.textContent = "♪ " + BGM_TRACKS[index].name;
      } else {
        tip.textContent = "背景音乐";
      }
    }

    function play(force) {
      desired = true;
      audio.muted = false;
      var p = audio.play();
      if (p && p.catch) {
        p.catch(function () {
          // 浏览器策略拦截时保持安静，等用户第一次点击/按键再起播
          updateUi();
        });
      }
    }

    function pause() {
      desired = false;
      audio.pause();
      player.classList.remove("needs-tap");
      persist(true);
      updateUi();
    }

    function load(i, keepPlaying) {
      index = (i + BGM_TRACKS.length) % BGM_TRACKS.length;
      audio.src = BGM_TRACKS[index].src;
      audio.currentTime = 0;
      persist(true);
      audio.muted = false;
      if (keepPlaying || desired) play();
      updateUi();
    }

    disc.addEventListener("click", function () {
      if (audio.paused || audio.muted) play(true);
      else pause();
    });
    nextBtn.addEventListener("click", function () { load(index + 1, true); });

    audio.addEventListener("play", function () { persist(true); updateUi(); });
    audio.addEventListener("pause", updateUi);
    audio.addEventListener("ended", function () { load(index + 1, true); });
    audio.addEventListener("timeupdate", function () { persist(false); });
    audio.addEventListener("loadedmetadata", function () {
      if (!restored && pendingTime > 0) {
        try {
          audio.currentTime = Math.min(pendingTime, Math.max(0, (audio.duration || pendingTime) - 0.5));
        } catch (e) {}
      }
      restored = true;
      if (desired && audio.paused) play(false);
      updateUi();
    });
    audio.addEventListener("canplay", function () {
      if (desired && audio.paused) play(false);
    });
    player.addEventListener("pointerdown", function () { persist(true); });
    window.addEventListener("pagehide", function () { persist(true); });
    document.addEventListener("visibilitychange", function () { persist(true); });

    // 自动播放被拦截时：用户第一次点/按任意地方就开声音，不需要找唱片机
    function unlock(ev) {
      if (ev && ev.target && ev.target.closest && ev.target.closest("#bgm-player")) return;
      audio.muted = false;
      if (desired && audio.paused) {
        var p = audio.play();
        if (p && p.catch) p.catch(function () {});
      }
      updateUi();
      window.removeEventListener("pointerdown", unlock, true);
      window.removeEventListener("keydown", unlock, true);
      window.removeEventListener("touchstart", unlock, true);
    }
    window.addEventListener("pointerdown", unlock, true);
    window.addEventListener("keydown", unlock, true);
    window.addEventListener("touchstart", unlock, true);

    document.addEventListener("visibilitychange", function () {
      persist(true);
      if (!document.hidden && desired && audio.paused) play(false);
    });
    window.addEventListener("pageshow", function () {
      if (desired && audio.paused) play(false);
    });

    if (desired) play(false);
    persist(true);
    updateUi();
  }

  /* ------------------------------ 站内无刷新跳转 ------------------------------ */
  function refreshPage() {
    updateActiveNav();
    initReveal();
    initCopy();
    initYear();
  }

  function initRouter() {
    // 本地双击（file://）时 fetch 会被浏览器拦住，退回普通跳转
    if (location.protocol === "file:") return;
    var main = document.querySelector("main");
    if (!main) return;
    var loading = false;

    function internalUrl(a) {
      if (!a || a.target === "_blank" || a.hasAttribute("download")) return null;
      var href = a.getAttribute("href");
      if (!href || href.charAt(0) === "#" || /^(mailto|tel|javascript):/i.test(href)) return null;
      var url;
      try { url = new URL(href, location.href); } catch (e) { return null; }
      if (url.origin !== location.origin) return null;
      if (!/\.html?$/.test(url.pathname) && !/\/$/.test(url.pathname)) return null;
      return url;
    }

    function swap(html, url, push) {
      var doc = new DOMParser().parseFromString(html, "text/html");
      var nextMain = doc.querySelector("main");
      if (!nextMain) { location.href = url.href; return; }
      main.innerHTML = nextMain.innerHTML;
      var nextFooter = doc.querySelector("footer");
      var curFooter = document.querySelector("footer");
      if (nextFooter && curFooter) curFooter.innerHTML = nextFooter.innerHTML;
      if (doc.title) document.title = doc.title;
      var nd = doc.querySelector('meta[name="description"]');
      var cd = document.querySelector('meta[name="description"]');
      if (nd && cd) cd.setAttribute("content", nd.getAttribute("content") || "");
      if (push) history.pushState({}, "", url.href);
      refreshPage();
      if (url.hash) {
        var el = document.getElementById(url.hash.slice(1));
        if (el) el.scrollIntoView({ behavior: reduceMotion ? "auto" : "smooth", block: "start" });
        else window.scrollTo(0, 0);
      } else {
        window.scrollTo(0, 0);
      }
    }

    function go(url, push) {
      if (loading) return;
      loading = true;
      fetch(url.href, { cache: "no-store" })
        .then(function (r) { if (!r.ok) throw new Error(r.status); return r.text(); })
        .then(function (html) { swap(html, url, push); })
        .catch(function () { location.href = url.href; })
        .finally(function () { loading = false; });
    }

    document.addEventListener("click", function (e) {
      if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
      var a = e.target && e.target.closest ? e.target.closest("a") : null;
      var url = internalUrl(a);
      if (!url) return;
      if (url.pathname === location.pathname && url.search === location.search && url.hash) return;
      e.preventDefault();
      var nav = document.querySelector(".nav-links");
      if (nav) nav.classList.remove("open");
      go(url, true);
    });

    window.addEventListener("popstate", function () {
      go(new URL(location.href), false);
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    initPetals();
    initNav();
    initReveal();
    initCopy();
    initYear();
    initBgm();
    initRouter();
  });
})();
