import { useCallback, useEffect, useMemo, useState } from 'react'
import { Activity, BadgeCheck, Banknote, Bot, Check, ChevronRight, CircleAlert, Coins, LoaderCircle, Play, RefreshCw, ShieldCheck, Sparkles, WalletCards } from 'lucide-react'

const API = 'http://localhost:8000'
type Ticket = { id: number; subject: string; requester: string; type?: string; status: 'open' | 'resolved'; notes?: string }
type Event = { event?: string; phase?: string; actor?: string; target_agent?: string; ticket_id?: number; tool_name?: string; timestamp_utc?: string; task?: string; report?: Report; result?: unknown; error?: string; step?: number }
type Draft = { kind: 'invoice' | 'rent' | 'purchase_order'; ref_id: number; amount: string | number; payee?: string; reason?: string; source_ticket_id: number; account?: 'checking'; human_approval_required: true }
type Report = { role?: string; findings?: string[]; recommendations?: string[]; customer_message_draft?: string; payment_draft?: Draft; needs_human_review?: boolean }
const roles: Record<string, { label: string; tone: string }> = { boss: { label: 'Boss', tone: 'boss' }, inventory: { label: 'Inventory', tone: 'inventory' }, accounting: { label: 'Accounting', tone: 'accounting' }, facilities: { label: 'Facilities', tone: 'facilities' }, customer_service: { label: 'Customer Service', tone: 'customer' } }
const money = (v: unknown) => { const n = Number(v); return Number.isFinite(n) ? new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(n) : '—' }
const explain = (e: Event) => {
  if (e.event === 'mcp_tool_call') return e.phase === 'completed' ? `Retrieved verified records with ${e.tool_name?.replaceAll('_', ' ')}.` : e.phase === 'failed' ? `${e.tool_name?.replaceAll('_', ' ')} failed: ${e.error ?? 'unknown error'}` : `Checking records with ${e.tool_name?.replaceAll('_', ' ')}.`
  if (e.event === 'delegation') return e.phase === 'completed' ? `Delegated specialist review to ${roles[e.target_agent ?? '']?.label ?? e.target_agent}.` : e.phase === 'started' ? `Requesting review from ${roles[e.target_agent ?? '']?.label ?? e.target_agent}.` : `${e.phase} delegation to ${roles[e.target_agent ?? '']?.label ?? e.target_agent}.`
  if (e.event === 'agent_run') return e.phase === 'completed' ? [...(e.report?.findings ?? []), ...(e.report?.recommendations ?? []), ...(e.report?.customer_message_draft ? [`Customer draft: ${e.report.customer_message_draft}`] : [])].join(' ') || 'Review completed.' : e.phase === 'failed' ? `Agent run failed: ${e.error ?? 'unknown error'}` : 'Reviewing the ticket and available records.'
  if (e.event === 'human_payment_approval') return `Payment ${e.phase}: ${money((e as Event & { amount?: number }).amount)}.`
  return e.event?.replaceAll('_', ' ') ?? 'Agent activity'
}

export default function App() {
  const [tickets, setTickets] = useState<Ticket[]>([])
  const [resolved, setResolved] = useState<number[]>(() => JSON.parse(localStorage.getItem('cc-resolved') || '[]'))
  const [selected, setSelected] = useState(101)
  const [events, setEvents] = useState<Event[]>([])
  const [balance, setBalance] = useState<unknown>(null)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [approver, setApprover] = useState('')
  const [approving, setApproving] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    try {
      const [ticketRes, eventRes, cashRes] = await Promise.all([fetch(`${API}/tickets`), fetch(`${API}/agent-events?limit=250`), fetch(`${API}/cash-balance`)] )
      if (!ticketRes.ok) throw new Error((await ticketRes.json()).detail || 'Could not load tickets')
      const [ts, es, cash] = await Promise.all([ticketRes.json(), eventRes.ok ? eventRes.json() : [], cashRes.ok ? cashRes.json() : null])
      setTickets(ts); setEvents(es); setBalance(cash?.balance ?? null); setError('')
    } catch (err) { setError(err instanceof Error ? err.message : 'Could not connect to the backend') } finally { setLoading(false) }
  }, [])
  useEffect(() => { void refresh(); const id = window.setInterval(() => void refresh(), 2500); return () => window.clearInterval(id) }, [refresh])

  const selectedTicket = tickets.find(t => t.id === selected)
  const ticketEvents = events.filter(e => e.ticket_id === selected)
  const drafts = useMemo(() => {
    const found: { draft: Draft; event: Event }[] = []
    for (const e of events) if (e.event === 'agent_run' && e.phase === 'completed' && e.report?.payment_draft) found.push({ draft: e.report.payment_draft, event: e })
    return found.filter(({ draft }, i, all) => draft.source_ticket_id === selected && !events.some(later => later.event === 'human_payment_approval' && later.phase === 'executed' && (later as Event & { ref_id?: number }).ref_id === draft.ref_id && later.ticket_id === draft.source_ticket_id && Number((later as Event & { amount?: number }).amount) === Number(draft.amount)) && all.findIndex(x => x.draft.ref_id === draft.ref_id && x.draft.source_ticket_id === draft.source_ticket_id) === i)
  }, [events, selected])
  const summary = useMemo(() => {
    const map = new Map<string, string[]>()
    ticketEvents.filter(e => e.event === 'agent_run' && e.phase === 'completed').forEach(e => { const r = e.report; if (r?.role) map.set(r.role, [...(r.findings ?? []), ...(r.recommendations ?? []), ...(r.payment_draft ? [`Prepared ${r.payment_draft.kind.replace('_', ' ')} proposal for ${money(r.payment_draft.amount)}; awaiting human approval.`] : []), ...(r.customer_message_draft ? ['Drafted a customer response for review.'] : [])]) })
    return map
  }, [ticketEvents])

  async function runTeam() {
    setBusy(true); setError('')
    try { const r = await fetch(`${API}/tickets/${selected}/resolve`, { method: 'POST' }); const data = await r.json(); if (!r.ok) throw new Error(data.detail || 'Agent run failed'); const next = [...new Set([...resolved, selected])]; setResolved(next); localStorage.setItem('cc-resolved', JSON.stringify(next)); await refresh() }
    catch (e) { setError(e instanceof Error ? e.message : 'Agent run failed') } finally { setBusy(false) }
  }
  async function approve(draft: Draft) {
    const key = `${draft.kind}-${draft.ref_id}`; if (!approver.trim()) { setError('Enter the approving operator’s name first.'); return }
    if (!window.confirm(`Approve ${draft.kind.replace('_', ' ')} for ${money(draft.amount)} to ${draft.payee ?? `reference #${draft.ref_id}`}? This will deduct funds from checking.`)) return
    setApproving(key); setError('')
    try { const res = await fetch(`${API}/approve-payment`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ kind: draft.kind, ref_id: draft.ref_id, ticket_id: draft.source_ticket_id, amount: Number(draft.amount), approved_by: approver.trim(), account: 'checking' }) }); const data = await res.json(); if (!res.ok) throw new Error(data.detail || 'Approval failed'); await refresh() }
    catch (e) { setError(e instanceof Error ? e.message : 'Approval failed') } finally { setApproving(null) }
  }
  const currentStatus = resolved.includes(selected) || selectedTicket?.status === 'resolved'

  return <div className="app-shell">
    <aside className="sidebar">
      <a className="brand" href="#top"><span className="brand-mark"><Sparkles size={19}/></span><span>campus<span className="brand-light">customs</span><small>OPERATIONS DESK</small></span></a>
      <div className="side-label">WORKSPACE <span className="live-dot"/></div>
      <nav className="ticket-nav">{[101,102,103].map(id => { const t = tickets.find(x => x.id === id); const done = resolved.includes(id) || t?.status === 'resolved'; return <button key={id} onClick={() => setSelected(id)} className={`ticket-link ${selected === id ? 'active' : ''}`}><span className="ticket-icon">{done ? <Check size={16}/> : <span>{String(id).slice(-2)}</span>}</span><span className="ticket-meta"><b>Ticket {id}</b><small>{t?.subject ?? (loading ? 'Loading ticket…' : 'Campus operations')}</small></span><i className={`status-dot ${done ? 'done' : ''}`}/></button> })}</nav>
      <div className="sidebar-bottom"><div className="side-label">FINANCIAL SNAPSHOT</div><div className="balance-card"><span className="balance-symbol"><WalletCards size={18}/></span><span className="eyebrow">CHECKING BALANCE</span><strong>{money(balance)}</strong><small><span className="live-dot"/> Synced with backend</small></div><div className="guardrail"><ShieldCheck size={16}/><span>Human approval required<br/>for every outgoing payment</span></div></div>
      <div className="sidebar-footer"><span className="avatar">CC</span><span><b>Desk operator</b><small>Local workspace</small></span><span className="connection"><span className="live-dot"/></span></div>
    </aside>

    <main className="main" id="top"><header className="topbar"><div className="crumb">Operations <ChevronRight size={14}/> <b>Agent desk</b></div><div className="top-actions"><span className="api-status"><span className={`live-dot ${error ? 'offline' : ''}`}/>{error ? 'Backend issue' : 'System operational'}</span><button className="icon-button" title="Refresh data" onClick={() => void refresh()}><RefreshCw size={17}/></button><span className="date-label">CAMPUS CUSTOMS <span>·</span> HOMEWORK 05</span></div></header>
      <div className="content"><section className="welcome"><div><div className="eyebrow pink">MULTI-AGENT WORKSPACE <span className="pulse"/></div><h1>Good work starts<br/><span>with a clear desk.</span></h1><p>Coordinate your specialist team, keep an eye on the details, and stay in control.</p></div><div className="welcome-art"><div className="orbit orbit-a"/><div className="orbit orbit-b"/><div className="hero-core"><Bot size={30}/></div><span className="float-chip chip-one"><span className="tiny-agent boss">B</span> Boss</span><span className="float-chip chip-two"><span className="tiny-agent inventory">I</span> Inventory</span><span className="float-chip chip-three"><span className="tiny-agent accounting">A</span> Accounting</span></div></section>
        {error && <div className="error-banner"><CircleAlert size={17}/><span>{error}</span><button onClick={() => void refresh()}><RefreshCw size={14}/> Retry</button></div>}
        <section className="ticket-heading"><div><div className="eyebrow">SELECTED CASE</div><h2>{selectedTicket?.subject ?? `Ticket ${selected}`}</h2><p>{selectedTicket ? `Ticket ${selected} · ${selectedTicket.requester ?? 'Campus Customs'}` : `Ticket ${selected} · Loading details`}</p></div><div className={`large-status ${currentStatus ? 'resolved' : ''}`}><span className="status-dot"/>{currentStatus ? 'Resolved' : 'Open'}</div></section>
        <section className="workspace-grid"><div className="activity-panel panel"><div className="panel-head"><div><div className="eyebrow">LIVE WORKFLOW</div><h3>Agent activity <span className="event-count">{ticketEvents.length}</span></h3></div><span className="live-label"><span className="live-dot"/> AUTO-REFRESH</span></div>
          {ticketEvents.length ? <div className="timeline">{ticketEvents.slice().reverse().map((e,i) => { const actor = roles[e.actor ?? '']; return <article key={`${e.timestamp_utc}-${e.step}-${i}`} className="event-row"><span className={`event-avatar ${actor?.tone ?? 'system'}`}>{actor ? actor.label.slice(0,1) : e.event === 'mcp_tool_call' ? '↗' : '•'}</span><div className="event-body"><div className="event-top"><b>{actor?.label ?? (e.event === 'mcp_tool_call' ? 'MCP Server' : e.event === 'delegation' ? 'Delegation' : 'System')}</b><time>{e.timestamp_utc ? new Date(e.timestamp_utc).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : 'Recent'}</time></div><p>{explain(e)}</p>{e.event === 'mcp_tool_call' && e.phase === 'completed' && <span className="tool-chip">DATABASE TOOL · {e.tool_name}</span>}</div><span className={`phase ${e.phase === 'failed' ? 'failed' : e.phase === 'completed' ? 'complete' : ''}`}>{e.phase ?? 'event'}</span></article> })}</div> : <div className="empty-activity"><span className="empty-icon"><Activity size={22}/></span><b>Your agent team is standing by</b><p>Start the workflow to see agent decisions, specialist handoffs, and verified database lookups appear here.</p><button className="primary-button" disabled={busy} onClick={() => void runTeam()}>{busy ? <><LoaderCircle className="spin" size={17}/> Agents are working</> : <><Play size={16} fill="currentColor"/> Run agent team</>}</button></div>}
          {ticketEvents.length > 0 && <div className="activity-footer"><span><span className="live-dot"/> Listening for updates</span><button onClick={() => void refresh()}><RefreshCw size={13}/> Refresh feed</button></div>}
        </div>
          <aside className="right-rail"><div className="panel team-panel"><div className="panel-head compact"><div><div className="eyebrow">THE SPECIALISTS</div><h3>Team summary</h3></div><span className="team-count">05</span></div><div className="team-list">{Object.entries(roles).map(([key,role]) => <div className="team-item" key={key}><span className={`event-avatar ${role.tone}`}>{role.label.slice(0,1)}</span><div><b>{role.label}</b><small>{summary.has(key) ? `${summary.get(key)?.length ?? 0} update${summary.get(key)?.length === 1 ? '' : 's'} recorded` : 'Awaiting assignment'}</small></div><span className={`member-state ${summary.has(key) ? 'worked' : ''}`}>{summary.has(key) ? <BadgeCheck size={15}/> : <span/>}</span></div>)}</div>{summary.size > 0 && <div className="summary-notes">{[...summary].map(([role,lines]) => <div key={role}><span>{roles[role]?.label ?? role}</span><p>{lines.slice(0,2).join(' ') || 'Completed review.'}</p></div>)}</div>}<button className="secondary-button run-button" disabled={busy || currentStatus} onClick={() => void runTeam()}>{busy ? <><LoaderCircle className="spin" size={16}/> Workflow running</> : currentStatus ? <><Check size={16}/> Ticket resolved</> : <><Play size={15} fill="currentColor"/> {ticketEvents.length ? 'Run workflow again' : 'Start agent workflow'}</>}</button></div>
            <div className="safety-note"><ShieldCheck size={17}/><span><b>You’re in control</b><small>Agents can prepare proposals, but only you can authorize a payment.</small></span></div></aside></section>
        <section className="approval-panel panel"><div className="approval-heading"><div className="approval-icon"><Coins size={19}/></div><div><div className="eyebrow">HUMAN-IN-THE-LOOP</div><h3>Approval queue <span className="queue-count">{drafts.length}</span></h3><p>Review agent proposals before any money moves.</p></div></div>{drafts.length ? <><label className="approver-field">APPROVING OPERATOR<input value={approver} onChange={e => setApprover(e.target.value)} placeholder="Enter your name to authorize"/></label><div className="draft-list">{drafts.map(({draft},i) => { const key = `${draft.kind}-${draft.ref_id}`; return <div className="draft-card" key={`${key}-${i}`}><span className="draft-icon"><Banknote size={18}/></span><div className="draft-info"><span className="draft-type">{draft.kind.replace('_',' ')} <i>·</i> #{draft.ref_id}</span><b>{draft.payee ?? `Reference ${draft.ref_id}`}</b><small>{draft.reason ?? 'Agent proposal requires review'}</small><em><ShieldCheck size={12}/> Pending your approval</em></div><strong className="draft-amount">{money(draft.amount)}</strong><button className="approve-button" disabled={!approver.trim() || approving === key} onClick={() => void approve(draft)}>{approving === key ? <LoaderCircle className="spin" size={15}/> : <><Check size={15}/> Approve</>}</button></div> })}</div></> : <div className="queue-empty"><span><ShieldCheck size={19}/></span><div><b>No proposals waiting for approval</b><small>Payment and purchase proposals from agent runs will appear here for your review.</small></div><span className="secure-tag"><ShieldCheck size={12}/> SECURE QUEUE</span></div>}</section>
        <footer className="page-footer"><span>Campus Customs <i>·</i> Operations desk</span><span><ShieldCheck size={13}/> Financial actions require explicit human authorization</span></footer>
      </div>
    </main>
  </div>
}
