/* 微信内置浏览器硬拦截：只负责复制链接与可访问性，不提供继续浏览。 */
(function () {
  "use strict";

  var html = document.documentElement;
  if (!html.classList.contains("is-wechat")) return;

  var guard = document.getElementById("wechatGuard");
  var urlInput = document.getElementById("wechatUrl");
  var copyBtn = document.getElementById("wechatCopy");
  var status = document.getElementById("wechatStatus");
  if (!guard || !urlInput || !copyBtn || !status) return;

  var pageUrl = window.location.href.split("#")[0];
  urlInput.value = pageUrl;

  function setStatus(message, kind) {
    status.textContent = message;
    status.className = "wechat-status" + (kind ? " " + kind : "");
  }

  function selectUrl() {
    try {
      urlInput.focus();
      urlInput.select();
      urlInput.setSelectionRange(0, urlInput.value.length);
    } catch (err) {
      /* 老 WebView 不支持 setSelectionRange 时忽略 */
    }
  }

  function fallbackCopy(text) {
    var area = document.createElement("textarea");
    area.value = text;
    area.setAttribute("readonly", "readonly");
    area.style.position = "fixed";
    area.style.top = "-9999px";
    area.style.left = "-9999px";
    area.style.opacity = "0";
    document.body.appendChild(area);
    area.focus();
    area.select();
    var ok = false;
    try {
      ok = document.execCommand("copy");
    } catch (err) {
      ok = false;
    }
    document.body.removeChild(area);
    return ok;
  }

  function copyPageUrl() {
    var done = function (ok) {
      if (ok) {
        setStatus("已复制。请粘贴到系统浏览器的地址栏打开。", "ok");
      } else {
        setStatus("复制失败，请长按上方网址手动复制。", "err");
        selectUrl();
      }
    };

    if (navigator.clipboard && window.isSecureContext) {
      navigator.clipboard.writeText(pageUrl).then(function () {
        done(true);
      }).catch(function () {
        done(fallbackCopy(pageUrl));
      });
      return;
    }

    done(fallbackCopy(pageUrl));
  }

  copyBtn.addEventListener("click", copyPageUrl);
  urlInput.addEventListener("focus", selectUrl);
  urlInput.addEventListener("click", selectUrl);

  // 硬拦截：Tab 只在复制按钮与网址框之间移动，不能落到被隐藏的页面内容上。
  guard.addEventListener("keydown", function (event) {
    if (event.key !== "Tab") return;
    var focusables = [urlInput, copyBtn];
    var index = focusables.indexOf(document.activeElement);
    if (event.shiftKey) {
      event.preventDefault();
      focusables[(index <= 0 ? focusables.length : index) - 1].focus();
    } else {
      event.preventDefault();
      focusables[(index + 1) % focusables.length].focus();
    }
  });

  // 等页面首帧完成后再聚焦，避免移动端键盘抢在提示层绘制前弹出。
  window.setTimeout(function () {
    copyBtn.focus();
  }, 80);
})();
