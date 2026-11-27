/* SPDX-License-Identifier: GPL-3.0-only */
const html = (value) => String(value ?? "—").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
class SmartHeatingPanel extends HTMLElement {
  constructor() { super(); this.attachShadow({mode:"open"}); this._page="overview"; }
  set hass(value) { this._hass=value; this.render(); }
  set panel(value) { this._panel=value; this.render(); }
  connectedCallback() { this.render(); }
  render() {
    if (!this._hass || !this._panel) return;
    const it=(this._hass.language||"en").startsWith("it");
    const tr=(a,b)=>it?a:b;
    const state=id=>this._hass.states[id];
    const val=id=>{const s=state(id);return !s||["unknown","unavailable"].includes(s.state)?"—":s.state+(s.attributes.unit_of_measurement?" "+s.attributes.unit_of_measurement:"");};
    const pages=[["overview",tr("Panoramica","Overview")],["zones",tr("Zone termiche","Heating zones")],["generators",tr("Generatori","Generators")],["learning",tr("Apprendimento","Learning")],["settings",tr("Impostazioni","Settings")]];
    const card=(title,value)=>'<article><small>'+html(title)+'</small><strong>'+html(value)+'</strong></article>';
    const installations=this._panel.config?.installations||[];
    const sections=installations.map(e=>{
      const ids=e.entities||{}, diag=state(ids.calibration)?.attributes||{}, fit=diag.fit||{};
      const ranked=state(ids.recommended_source)?.attributes?.candidates||[];
      const costs=new Map(ranked.map(x=>[x.id,x.cost]));
      const rows=(e.generators||[]).map(g=>'<tr><td>'+html(g.name)+'</td><td>'+html(val(g.state_entity))+'</td><td>'+html(costs.has(g.id)?Number(costs.get(g.id)).toFixed(3)+" €/kWh":"—")+'</td></tr>').join("");
      const overview='<div class="grid">'+card(tr("Temperatura interna","Indoor temperature"),val(e.indoor))+card(tr("Temperatura esterna","Outdoor temperature"),val(e.outdoor))+card(tr("Fabbisogno termico","Heat demand"),val(ids.heat_demand))+card(tr("Generatore consigliato","Recommended source"),val(ids.recommended_source))+card(tr("Prezzo elettricità","Electricity price"),val(ids.electricity_price))+'</div>';
      const generators='<article><h2>'+tr("Confronto generatori","Generator comparison")+'</h2>'+(rows?'<table><thead><tr><th>'+tr("Generatore","Generator")+'</th><th>'+tr("Stato","State")+'</th><th>'+tr("Costo termico","Heat cost")+'</th></tr></thead><tbody>'+rows+'</tbody></table>':html(tr("Nessun generatore configurato","No generators configured")))+'</article>';
      const learning='<article><h2>'+tr("Modello termico","Thermal model")+'</h2><div class="grid">'+card(tr("Dispersioni","Heat loss"),fit.loss_w_k!=null?Number(fit.loss_w_k).toFixed(1)+" W/K":"—")+card(tr("Inerzia","Thermal capacity"),fit.capacity_kwh_k!=null?Number(fit.capacity_kwh_k).toFixed(2)+" kWh/K":"—")+card("COP",fit.cop!=null?Number(fit.cop).toFixed(2):"—")+card(tr("Campioni validi","Valid samples"),fit.samples??"—")+card(tr("Stato calibrazione","Calibration status"),val(ids.calibration))+'</div></article>';
      const zones='<article><h2>'+tr("Zone termiche rilevate","Discovered heating zones")+'</h2><div class="grid">'+Object.values(e.zones||{}).map(z=>{
        const names=ids=>ids.map(id=>html(state(id)?.attributes?.friendly_name||id)).join(", ");
        return '<article><h2>'+html(z.name)+'</h2><p>'+html(z.confirmed?tr("Configurata","Configured"):tr("Da confermare","Needs confirmation"))+'</p><strong>'+html(val(z.temperature))+'</strong><p>'+tr("Termometri rilevati: ","Detected thermometers: ")+(names(z.temperature_candidates||[])||"—")+'</p><p>'+tr("Fonti di riscaldamento: ","Heating sources: ")+(names(z.confirmed?(z.sources||[]):(z.source_candidates||[]))||"—")+'</p></article>';
      }).join("")+'</div><p><a href="/config/integrations">'+tr("Configura zone nelle opzioni","Configure zones in integration options")+'</a></p></article>';
      const settings='<article><h2>'+tr("Configurazione","Configuration")+'</h2><p>'+tr("Modifica sensori, generatori e tariffe nelle opzioni dell’integrazione.","Edit sensors, generators and tariffs in integration options.")+'</p><a href="/config/integrations">'+tr("Apri integrazioni","Open integrations")+'</a></article>';
      return '<section><h2>'+html(e.title)+'</h2>'+({overview:overview+zones+generators+learning,zones,generators,learning,settings}[this._page]||overview)+'</section>';
    }).join("");
    this.shadowRoot.innerHTML=`<style>
      :host{display:block;color:var(--primary-text-color);background:var(--primary-background-color);font-family:var(--paper-font-body1_-_font-family,system-ui);min-height:100vh}
      main{max-width:1400px;margin:auto;padding:clamp(12px,3vw,32px)} header{display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap} h1{font-size:clamp(22px,3vw,32px);margin:0} h2{font-size:17px;margin:0 0 14px} p,small{color:var(--secondary-text-color)} nav{display:flex;flex-wrap:wrap;gap:8px;margin:24px 0} button,a{font:inherit;color:var(--primary-color);background:var(--card-background-color);border:1px solid var(--divider-color);border-radius:10px;padding:10px 14px;cursor:pointer} button[aria-current=true]{background:var(--primary-color);color:var(--text-primary-color,#fff)} article{background:var(--ha-card-background,var(--card-background-color));border:1px solid var(--divider-color);border-radius:12px;padding:16px;min-width:0;margin-bottom:12px} .grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,180px),1fr));gap:12px} .grid article{margin:0} strong{display:block;font-size:22px;margin-top:8px;overflow-wrap:anywhere} table{width:100%;border-collapse:collapse;text-align:left} th,td{padding:12px 4px;border-bottom:1px solid var(--divider-color);overflow-wrap:anywhere} section{margin-bottom:24px} .mode{color:var(--secondary-text-color);font-size:14px} .grid+article{margin-top:12px} </style>
      <main><header><h1>Smart Heating Energy Manager</h1><span class="mode">● ${tr("Modalità consultiva · controllo disattivato","Advisory mode · control disabled")}</span></header>
      <nav>${pages.map(([k,t])=>'<button data-page="'+k+'" aria-current="'+(k===this._page)+'">'+html(t)+'</button>').join("")}</nav>
      ${sections||'<p>'+tr("Nessun impianto disponibile","No installation available")+'</p>'}</main>`;
    this.shadowRoot.querySelectorAll("button[data-page]").forEach(b=>b.addEventListener("click",()=>{this._page=b.dataset.page;this.render();}));
  }
}
if (!customElements.get("smart-heating-panel")) customElements.define("smart-heating-panel",SmartHeatingPanel);
