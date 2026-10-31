/*
 * GradientZero chaos script: breaks a live form page in realistic, repeatable ways
 * so the agent's self-repair can be shown. It only changes the page inside our own
 * browser session, and it NEVER changes `name` attributes, `id` attributes or
 * form values, because the portal's server and scripts depend on them.
 *
 *   window.__chaos({mode: "rename"|"rewrap"|"move"|"hide"|"popup"|"slow", seed: 7, count: 3})
 *     -> array of log entries {mode, target, from, to}
 *   window.__chaosLog -> every entry so far
 *
 * Same seed on the same page gives the same changes. Re-evaluating this file is a no-op.
 */
(function () {
  if (window.__chaos) return;

  function mulberry32(a) {
    return function () {
      a |= 0; a = (a + 0x6d2b79f5) | 0;
      var t = Math.imul(a ^ (a >>> 15), 1 | a);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }

  function shuffle(list, rng) {
    var a = list.slice();
    for (var i = a.length - 1; i > 0; i--) {
      var j = Math.floor(rng() * (i + 1));
      var t = a[i]; a[i] = a[j]; a[j] = t;
    }
    return a;
  }

  var SYNONYMS = [
    [/date of birth|\bdob\b|birth/i, "DOB (as per records)"],
    [/income/i, "Family income per annum"],
    [/father|guardian/i, "Parent / guardian name"],
    [/mother/i, "Mother's full name (as in certificate)"],
    [/mobile|phone/i, "Contact number"],
    [/categor|communit|caste/i, "Social category / Community"],
    [/course|program/i, "Programme of study"],
    [/institut|college|universit/i, "College / University"],
    [/certificate|upload|document|file/i, "Attach supporting document"],
    [/name/i, "Applicant name (as in certificate)"],
  ];

  var CONTROLS = "input:not([type=hidden]):not([type=submit]):not([type=button]):not([type=reset]), select, textarea";

  function controlKey(el) {
    return el.getAttribute("name") || el.id || el.tagName.toLowerCase();
  }

  function labelFor(el) {
    if (el.id) {
      var l = document.querySelector('label[for="' + CSS.escape(el.id) + '"]');
      if (l) return l;
    }
    return el.closest("label");
  }

  function labelText(el) {
    var l = labelFor(el);
    if (l) return l.textContent.trim();
    return el.getAttribute("aria-label") || el.getAttribute("placeholder") || controlKey(el);
  }

  // The field's group: the largest ancestor that holds this control and no other.
  function groupOf(el) {
    var node = el;
    while (node.parentElement && node.parentElement !== document.body &&
           node.parentElement.querySelectorAll(CONTROLS).length === 1) {
      node = node.parentElement;
    }
    var label = labelFor(el);
    return label && !node.contains(label) ? el.parentElement : node;
  }

  function targets(rng, count) {
    var all = Array.prototype.slice.call(document.querySelectorAll(CONTROLS));
    return shuffle(all, rng).slice(0, Math.max(1, count || 1));
  }

  function newName(original) {
    for (var i = 0; i < SYNONYMS.length; i++) {
      if (SYNONYMS[i][0].test(original) && SYNONYMS[i][1] !== original) return SYNONYMS[i][1];
    }
    return "Enter " + original;
  }

  function className(rng) {
    return "c" + Math.floor(rng() * 1e9).toString(36);
  }

  var modes = {
    rename: function (rng, count, log) {
      targets(rng, count).forEach(function (el) {
        var before = labelText(el);
        var after = newName(before);
        var label = labelFor(el);
        if (label) {
          // Replace text nodes only; child elements (the input itself, a required star) stay.
          var replaced = false;
          Array.prototype.slice.call(label.childNodes).forEach(function (n) {
            if (n.nodeType === 3 && n.textContent.trim()) {
              n.textContent = replaced ? "" : after + " ";
              replaced = true;
            }
          });
          if (!replaced) label.insertBefore(document.createTextNode(after + " "), label.firstChild);
        }
        if (el.hasAttribute("placeholder")) el.setAttribute("placeholder", after);
        if (el.hasAttribute("aria-label")) el.setAttribute("aria-label", after);
        log.push({ mode: "rename", target: controlKey(el), from: before, to: after });
      });
    },
    rewrap: function (rng, count, log) {
      targets(rng, count).forEach(function (el) {
        var group = groupOf(el);
        var outer = document.createElement("div");
        var inner = document.createElement("div");
        outer.className = className(rng);
        inner.className = className(rng);
        group.parentNode.insertBefore(outer, group);
        outer.appendChild(inner);
        inner.appendChild(group);
        log.push({ mode: "rewrap", target: controlKey(el), from: group.tagName.toLowerCase(),
                   to: "div." + outer.className + " > div." + inner.className });
      });
    },
    move: function (rng, count, log) {
      var groups = Array.prototype.slice.call(document.querySelectorAll(CONTROLS)).map(groupOf);
      var byParent = new Map();
      groups.forEach(function (g) {
        if (!g.parentElement) return;
        var list = byParent.get(g.parentElement) || [];
        if (list.indexOf(g) < 0) list.push(g);
        byParent.set(g.parentElement, list);
      });
      byParent.forEach(function (list, parent) {
        if (list.length < 3) return;
        var anchor = list[list.length - 1].nextSibling;
        var order = shuffle(list, rng);
        order.forEach(function (g) { parent.insertBefore(g, anchor); });
        log.push({ mode: "move", target: parent.id || parent.tagName.toLowerCase(),
                   from: list.map(function (g) { return controlKey(g.querySelector(CONTROLS)); }).join(","),
                   to: order.map(function (g) { return controlKey(g.querySelector(CONTROLS)); }).join(",") });
      });
    },
    hide: function (rng, count, log) {
      targets(rng, count).forEach(function (el) {
        var group = groupOf(el);
        var details = document.createElement("details");
        var summary = document.createElement("summary");
        summary.textContent = "More details";
        details.appendChild(summary);
        group.parentNode.insertBefore(details, group);
        details.appendChild(group);
        log.push({ mode: "hide", target: controlKey(el), from: "visible", to: "inside closed <details>" });
      });
    },
    popup: function (rng, count, log) {
      var overlay = document.createElement("div");
      overlay.setAttribute("role", "dialog");
      overlay.setAttribute("aria-modal", "true");
      overlay.setAttribute("aria-labelledby", "chaos-popup-title");
      overlay.style.cssText = "position:fixed;inset:0;z-index:2147483647;background:rgba(0,0,0,.55);display:flex;" +
        "align-items:center;justify-content:center";
      overlay.innerHTML = '<div style="background:#fff;padding:24px;max-width:420px;border-radius:8px;font:16px sans-serif">' +
        '<h2 id="chaos-popup-title" style="margin-top:0">Important notice</h2>' +
        "<p>Please verify your details carefully before you continue with the application.</p>" +
        '<button type="button">Close</button></div>';
      overlay.querySelector("button").addEventListener("click", function () { overlay.remove(); });
      document.body.appendChild(overlay);
      log.push({ mode: "popup", target: "body", from: "none", to: "dialog 'Important notice'" });
    },
    slow: function (rng, count, log) {
      function delay() { return 2000 + Math.floor(rng() * 4000); }
      if (!window.__chaosSlowInstalled) {
        window.__chaosSlowInstalled = true;
        var realFetch = window.fetch;
        if (realFetch) {
          window.fetch = function () {
            var args = arguments, self = this, ms = delay();
            return new Promise(function (r) { setTimeout(r, ms); }).then(function () { return realFetch.apply(self, args); });
          };
        }
        var realSend = XMLHttpRequest.prototype.send;
        XMLHttpRequest.prototype.send = function () {
          var args = arguments, self = this;
          setTimeout(function () { realSend.apply(self, args); }, delay());
        };
      }
      log.push({ mode: "slow", target: "fetch, XMLHttpRequest", from: "0 ms", to: "2000-6000 ms delay" });
    },
  };

  window.__chaosLog = window.__chaosLog || [];
  window.__chaos = function (opts) {
    opts = opts || {};
    var run = modes[opts.mode];
    if (!run) throw new Error("unknown chaos mode: " + opts.mode);
    var log = [];
    run(mulberry32(opts.seed == null ? 7 : opts.seed), opts.count == null ? 3 : opts.count, log);
    Array.prototype.push.apply(window.__chaosLog, log);
    return log;
  };
})();
