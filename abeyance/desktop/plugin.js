// Abeyance, Desktop half. SDK only: @hermes/plugin-sdk, react, react/jsx-runtime.
// A status chip ("2 waiting"), a "Waiting for you" page, and an inline card the agent can show
// with ::abeyance-park{code="K7Q2"}. Resume submits `resume CODE` into the chat as a real turn,
// so Abeyance checks the world and Hermes's own approval card asks for the exact command.
// Drop calls the plugin's dashboard route. Nothing here runs a step.
import { ROUTES_AREA, SIDEBAR_NAV_AREA, STATUSBAR_AREAS, TRANSCRIPT_DIRECTIVE_AREA, host } from '@hermes/plugin-sdk'
import { useEffect, useState } from 'react'
import { jsx, jsxs } from 'react/jsx-runtime'

const AMBER = '#e0a84a'
const GREEN = '#5fbf8f'
const CODE_RE = /^[A-Z2-9]{4}$/
const listeners = new Set()
const refreshAll = () => listeners.forEach((fn) => fn())

function useParks(ctx, path) {
  const [state, setState] = useState({ loading: true, data: null, error: null })
  useEffect(() => {
    let live = true
    if (!path) { setState({ loading: false, data: null, error: null }); return () => { live = false } }
    const load = () =>
      ctx.rest(path).then(
        (data) => live && setState({ loading: false, data, error: null }),
        (error) => live && setState({ loading: false, data: null, error: String(error && error.message || error) })
      )
    load()
    listeners.add(load)
    return () => { live = false; listeners.delete(load) }
  }, [path])
  return state
}

function resume(code, sessionId) {
  const sent = host.composer.submit(sessionId ?? null, `resume ${code}`)
  if (!sent) host.notify({ kind: 'warning', message: 'Open a chat to resume. Abeyance will check the repo first.' })
  else host.notify({ kind: 'info', message: `Sent resume ${code}. Hermes will ask you to confirm the command.` })
}

function drop(ctx, code) {
  ctx.rest(`/parks/${code}/deny`, { method: 'POST' }).then(
    (r) => { host.notify({ kind: r && r.ok ? 'info' : 'warning', message: (r && r.message) || `Dropped ${code}` }); refreshAll() },
    () => host.notify({ kind: 'warning', message: 'Could not reach the Abeyance backend. Is the plugin enabled?' })
  )
}

const btn = (label, onClick, accent) =>
  jsx('button', {
    type: 'button', onClick,
    className: 'rounded px-2 py-1 text-xs font-medium',
    style: { border: `1px solid ${accent || 'var(--ui-border, #444)'}`, color: accent || 'inherit', background: 'transparent' },
    children: label
  })

function ParkCard({ ctx, park, sessionId, compact }) {
  const waiting = park.status === 'parked'
  const color = waiting ? AMBER : park.status === 'executed' ? GREEN : 'var(--ui-text-tertiary, #999)'
  const hours = Math.max(0, Math.round((park.expires_at * 1000 - Date.now()) / 3600000))
  return jsxs('div', {
    className: 'flex flex-col gap-1 rounded-md p-3 text-sm',
    style: { border: '1px solid var(--ui-border, #333)', borderLeft: `3px solid ${color}` },
    children: [
      jsxs('div', { className: 'flex items-center justify-between gap-2', children: [
        jsx('span', { className: 'font-medium', children: park.job_name }),
        jsx('span', { className: 'text-xs', style: { color }, children: `${park.code}  ${park.status}` })
      ] }),
      jsx('code', { className: 'text-xs', children: park.command }),
      jsx('div', { className: 'text-xs text-(--ui-text-tertiary)', children: `why held: ${(park.why || []).join('; ')}` }),
      park.where && jsx('div', { className: 'text-xs text-(--ui-text-tertiary)', children: `where: ${park.where}${park.branch ? `  branch ${park.branch} at ${park.head}` : ''}` }),
      !compact && park.steps && jsx('ol', { className: 'text-xs text-(--ui-text-tertiary)', children:
        park.steps.map((s) => jsx('li', { children: `${s.seq}. ${s.summary}  ${s.ok ? 'ok' : 'failed'}` }, s.seq)) }),
      waiting && jsx('div', { className: 'text-xs text-(--ui-text-tertiary)', children: `expires in ${hours} h; nothing runs until you answer` }),
      waiting && jsxs('div', { className: 'mt-1 flex gap-2', children: [
        btn('Resume', () => resume(park.code, sessionId), AMBER),
        btn('Drop', () => drop(ctx, park.code))
      ] })
    ]
  })
}

function Chip({ ctx }) {
  const { data } = useParks(ctx, '/parks?status=parked&limit=20')
  const n = (data && data.waiting) || 0
  return jsx('button', {
    type: 'button', onClick: () => host.navigate('/abeyance'),
    className: 'px-1.5 text-[0.6875rem]',
    style: { color: n ? AMBER : 'var(--ui-text-tertiary, #888)' },
    title: n ? 'Scheduled steps waiting for you' : 'No scheduled step is waiting',
    children: n ? `${n} waiting` : 'nothing waiting'
  })
}

function Detail({ ctx, code }) {
  const { data } = useParks(ctx, `/parks/${code}`)
  return data && data.park ? jsx(ParkCard, { ctx, park: data.park }) : null
}

function Page({ ctx }) {
  const { loading, data, error } = useParks(ctx, '/parks?limit=30')
  const parks = (data && data.parks) || []
  const waiting = parks.filter((p) => p.status === 'parked')
  const past = parks.filter((p) => p.status !== 'parked')
  return jsxs('div', { className: 'flex h-full flex-col gap-3 overflow-auto p-4', children: [
    jsx('h1', { className: 'text-lg font-semibold', children: 'Waiting for you' }),
    jsx('p', { className: 'text-sm text-(--ui-text-tertiary)', children:
      'Steps your scheduled Hermes runs stopped before. Resume sends `resume CODE` to the chat: Abeyance checks the repo is the one you were shown, then Hermes asks you to confirm the exact command.' }),
    loading && jsx('div', { className: 'text-sm', children: 'Loading...' }),
    error && jsx('div', { className: 'text-sm', style: { color: AMBER }, children: 'The Abeyance backend is not reachable. Enable the plugin in config.yaml (plugins.enabled).' }),
    !loading && !error && waiting.length === 0 && jsx('div', { className: 'text-sm', children: 'Nothing is waiting. Your night runs finished on their own.' }),
    ...waiting.map((p) => jsx(Detail, { ctx, code: p.code }, p.code)),
    past.length > 0 && jsx('h2', { className: 'mt-2 text-sm font-semibold', children: 'Answered' }),
    ...past.map((p) => jsx(ParkCard, { ctx, park: p, compact: true }, p.code))
  ] })
}

function Inline({ ctx, attrs, sessionId }) {
  const code = String((attrs && attrs.code) || '').toUpperCase()
  const valid = CODE_RE.test(code)
  const { data } = useParks(ctx, valid ? `/parks/${code}` : null)
  if (!valid) return null
  return data && data.park ? jsx(ParkCard, { ctx, park: data.park, sessionId, compact: true }) : null
}

export default {
  id: 'abeyance',
  name: 'Abeyance',
  register(ctx) {
    ctx.registerMany([
      { id: 'chip', area: STATUSBAR_AREAS.right, order: 125, render: () => jsx(Chip, { ctx }) },
      { id: 'nav', area: SIDEBAR_NAV_AREA, data: { path: '/abeyance', label: 'Waiting for you', codicon: 'watch' } },
      { id: 'page', area: ROUTES_AREA, data: { path: '/abeyance' }, render: () => jsx(Page, { ctx }) },
      { id: 'park-card', area: TRANSCRIPT_DIRECTIVE_AREA, data: {
        name: 'abeyance-park',
        render: ({ attrs, sessionId }) => jsx(Inline, { ctx, attrs, sessionId })
      } }
    ])
    ctx.onEvent('plugin.abeyance.changed', refreshAll)
  }
}
