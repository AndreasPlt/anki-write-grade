/* Write & Grade: the box on the front of a card, your attempt on the back.
 *
 * Python owns the state and hands it over as JSON; this script only draws it and
 * sends the sentence back through pycmd. Everything the model wrote is set as text,
 * never as HTML.
 */
var WriteGrade = (function () {
  var HAN = /[㐀-䶿一-鿿豈-﫿]+/g;
  var state, root, input, out;

  function text(node, value) {
    /* Chinese runs coloured the way the card colours them. */
    var last = 0, m;
    HAN.lastIndex = 0;
    while ((m = HAN.exec(value))) {
      if (m.index > last) node.appendChild(document.createTextNode(value.slice(last, m.index)));
      var han = document.createElement('span');
      han.className = 'wg-han';
      han.textContent = m[0];
      node.appendChild(han);
      last = m.index + m[0].length;
    }
    if (last < value.length) node.appendChild(document.createTextNode(value.slice(last)));
    return node;
  }

  function el(tag, cls, value) {
    var node = document.createElement(tag);
    if (cls) node.className = cls;
    return value ? text(node, value) : node;
  }

  function row(key, value) {
    var line = el('div', 'wg-row');
    line.appendChild(el('span', 'wg-k', key));
    line.appendChild(el('span', 'wg-v', value));
    return line;
  }

  function rows(parent, result) {
    result.failing.forEach(function (f) { parent.appendChild(row(f[0], f[1])); });
    if (result.hint) parent.appendChild(row('Hint', result.hint));
    if (result.improve) parent.appendChild(row('Improve', result.improve));
  }

  function ordinal(n) {
    return n + ({ 2: 'nd', 3: 'rd' }[n] || 'th');
  }

  function place(anchorSelector) {
    /* Next to the template's element if it is there; at the bottom if it is not. */
    var anchor = document.querySelector(anchorSelector);
    if (anchor && anchor.parentNode) anchor.parentNode.insertBefore(root, anchor.nextSibling);
  }

  /* ---- front ------------------------------------------------------------- */

  function mountFront() {
    place('.todo');
    input = el('textarea', 'wg-input');
    input.rows = 1;
    input.placeholder = 'type your sentence';
    input.setAttribute('lang', 'zh');
    input.setAttribute('autocomplete', 'off');
    ['keydown', 'keyup', 'keypress'].forEach(function (type) {
      input.addEventListener(type, function (e) { e.stopPropagation(); });
    });
    input.addEventListener('keydown', function (e) {
      if (e.key === 'Enter' && !e.shiftKey) {
        if (e.isComposing || e.keyCode === 229) return; /* Enter picks an IME candidate */
        e.preventDefault();
        submit();
      } else if (e.key === 'Escape') {
        e.preventDefault();
        input.blur();
      }
    });
    input.addEventListener('input', fit);
    root.appendChild(input);
    root.appendChild(el('div', 'wg-help', 'Enter: check · Esc: leave the box (then Space flips)'));
    out = root.appendChild(el('div', 'wg-out'));
    setTimeout(function () { input.focus(); fit(); }, 0);
  }

  function fit() {
    input.style.height = 'auto';
    input.style.height = input.scrollHeight + 'px';
  }

  function submit() {
    var sentence = input.value.trim();
    if (!sentence || (state.attempt && state.attempt.checking)) return;
    var shown = document.querySelector('.quote .rot-on') || document.querySelector('.quote');
    state.attempt = { sentence: sentence, checking: true, error: '', tries: 0, result: null };
    renderFront();
    pycmd('write-grade:' + JSON.stringify({
      card: state.card,
      sentence: sentence,
      situation: shown ? shown.textContent.trim() : ''
    }));
  }

  function renderFront() {
    var a = state.attempt;
    out.innerHTML = '';
    if (!a) return;
    if (a.checking) { out.appendChild(el('div', 'wg-wait', 'checking… · ' + state.model)); return; }
    if (a.error) out.appendChild(el('div', 'wg-err', '⚠ ' + a.error));
    if (!a.result) return;
    var r = a.result, box = el('div', 'wg-res wg-' + r.kind);
    box.appendChild(el('div', 'wg-verdict', r.symbol + ' ' + r.verdict));
    if (r.passing.length) box.appendChild(el('div', 'wg-pass', r.passing.join(' · ') + ' ok'));
    rows(box, r);
    out.appendChild(box);
  }

  /* ---- back -------------------------------------------------------------- */

  function renderBack() {
    var a = state.attempt;
    root.innerHTML = '';
    if (!a) return;
    var you = el('div', 'wg-row wg-you');
    you.appendChild(el('span', 'wg-k', 'You'));
    var line = el('span', 'wg-v');
    line.appendChild(el('span', 'wg-sent', a.sentence));
    var badge = a.checking ? 'checking…'
      : a.result ? a.result.symbol + (a.tries > 1 ? ' · ' + ordinal(a.tries) + ' try' : '')
      : '';
    if (badge) line.appendChild(el('span', 'wg-badge', badge));
    you.appendChild(line);
    root.appendChild(you);
    if (a.checking) return;
    if (a.error) root.appendChild(row('', '⚠ ' + a.error));
    if (a.result) rows(root, a.result);
  }

  /* ---- entry points ------------------------------------------------------ */

  return {
    mount: function (initial) {
      state = initial;
      root = document.getElementById('wg-root');
      root.setAttribute('data-side', state.side);
      if (state.side === 'front') mountFront();
      else { place('.replay'); renderBack(); }
    },
    show: function (attempt) {
      if (!root || !document.body.contains(root)) return;
      state.attempt = attempt;
      if (state.side === 'front') renderFront();
      else renderBack();
    }
  };
})();
