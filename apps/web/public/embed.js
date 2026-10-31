(function () {
  'use strict';

  var script = document.currentScript;
  if (!script || !script.src) return;
  var widgetUrl = new URL('widget.html', script.src);
  var widgetOrigin = widgetUrl.origin;
  var hostOrigin = window.location.origin;
  if ((widgetUrl.protocol !== 'https:' && widgetUrl.protocol !== 'http:') ||
      (window.location.protocol !== 'https:' && window.location.protocol !== 'http:')) return;
  widgetUrl.searchParams.set('hostOrigin', hostOrigin);

  function mount() {
    if (document.getElementById('knowledge-assistant-embed')) return;
    var host = document.createElement('div');
    host.id = 'knowledge-assistant-embed';
    var shadow = host.attachShadow({ mode: 'open' });
    // Inline important declarations protect the host from the embedding page's CSS.
    var hostStyles = {
      all: 'initial', position: 'fixed', 'z-index': '2147483000', right: '16px',
      bottom: '16px', display: 'block', width: '64px', height: '64px'
    };
    Object.keys(hostStyles).forEach(function (key) {
      host.style.setProperty(key, hostStyles[key], 'important');
    });
    var style = document.createElement('style');
    style.textContent = ':host { all: initial !important; position: fixed !important; z-index: 2147483000 !important; right: 16px !important; bottom: 16px !important; width: 64px !important; height: 64px !important; display: block !important; }' +
      ':host([data-open]) { width: min(380px, calc(100vw - 32px)) !important; height: min(600px, calc(100vh - 32px)) !important; }' +
      'iframe { all: initial !important; display: block !important; box-sizing: border-box !important; width: 100% !important; height: 100% !important; border: 0 !important; background: transparent !important; color-scheme: light !important; }';
    var frame = document.createElement('iframe');
    frame.title = '知识助手';
    frame.src = widgetUrl.href;
    frame.allowTransparency = 'true';
    shadow.append(style, frame);
    function receiveMessage(event) {
      if (event.origin !== widgetOrigin || event.source !== frame.contentWindow) return;
      var data = event.data;
      if (!data || typeof data !== 'object' || data.type !== 'knowledge-assistant:state' || typeof data.open !== 'boolean') return;
      host.toggleAttribute('data-open', data.open);
      host.style.setProperty('width', data.open ? 'min(380px, calc(100vw - 32px))' : '64px', 'important');
      host.style.setProperty('height', data.open ? 'min(600px, calc(100vh - 32px))' : '64px', 'important');
    }
    window.addEventListener('message', receiveMessage);
    host.addEventListener('knowledge-assistant:dispose', function () {
      window.removeEventListener('message', receiveMessage);
      host.remove();
    }, { once: true });
    frame.addEventListener('load', function () {
      frame.contentWindow.postMessage({ type: 'knowledge-assistant:state', open: false }, widgetOrigin);
    });
    document.body.appendChild(host);
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', mount, { once: true });
  else mount();
}());
