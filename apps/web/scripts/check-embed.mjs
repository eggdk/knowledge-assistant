import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import vm from 'node:vm'

const code = readFileSync(new URL('../public/embed.js', import.meta.url), 'utf8')
const listeners = {}
const elements = new Map()
const sent = []
const frameWindow = { postMessage: (...args) => sent.push(args) }
const makeElement = (tag) => ({
  tag, children: [], attributes: new Set(), style: { values: {}, setProperty(name, value) { this.values[name] = value } },
  append(...children) { this.children.push(...children) },
  attachShadow() { this.shadowRoot = makeElement('shadow'); return this.shadowRoot },
  toggleAttribute(name, value) { value ? this.attributes.add(name) : this.attributes.delete(name) },
  addEventListener(type, callback) { this['on' + type] = callback },
  remove() { elements.delete(this.id) },
  ...(tag === 'iframe' ? { contentWindow: frameWindow } : {}),
})
const document = {
  currentScript: { src: 'https://widget.example/subpath/embed.js' },
  readyState: 'complete',
  createElement: makeElement,
  getElementById: (id) => elements.get(id),
  body: { appendChild(element) { elements.set(element.id, element) } },
}
const window = {
  location: { origin: 'https://host.example', protocol: 'https:' },
  addEventListener(type, callback) { listeners[type] = callback },
  removeEventListener(type, callback) { if (listeners[type] === callback) delete listeners[type] },
}
const context = vm.createContext({ document, window, URL, Object })
vm.runInContext(code, context)
vm.runInContext(code, context)
assert.equal(elements.size, 1, '重复加载只创建一个实例')
const host = elements.get('knowledge-assistant-embed')
const frame = host.shadowRoot.children.find((child) => child.tag === 'iframe')
const url = new URL(frame.src)
assert.equal(url.href, 'https://widget.example/subpath/widget.html?hostOrigin=https%3A%2F%2Fhost.example')
frame.onload()
assert.equal(sent[0][1], 'https://widget.example')
const valid = { origin: 'https://widget.example', source: frameWindow, data: { type: 'knowledge-assistant:state', open: true } }
for (const invalid of [
  { ...valid, origin: 'https://attacker.example' },
  { ...valid, source: {} },
  { ...valid, data: { type: 'knowledge-assistant:state', open: 'true' } },
  { ...valid, data: { type: 'other', open: true } },
]) {
  listeners.message(invalid)
  assert.equal(host.attributes.has('data-open'), false, '拒绝无效消息')
}
listeners.message(valid)
assert.equal(host.attributes.has('data-open'), true, '接受有效展开消息')
listeners.message({ ...valid, data: { ...valid.data, open: false } })
assert.equal(host.attributes.has('data-open'), false, '接受有效收起消息')
assert.equal(host.style.values.width, '64px')
host['onknowledge-assistant:dispose']()
assert.equal(elements.size, 0, '卸载后移除插件')
assert.equal(listeners.message, undefined, '卸载后移除消息监听')
vm.runInContext(code, context)
assert.equal(elements.size, 1, '卸载后可重新加载')
console.log('embed 边界检查通过')
