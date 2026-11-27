/* SPDX-License-Identifier: GPL-3.0-only */
const html = (value) => String(value ?? "—").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
class SmartHeatingPanel extends HTMLElement {
  constructor() { super(); this.attachShadow({mode:"open"}); this._page="overview"; this._zones={}; this._editing=null; this._notice=""; }
  set hass(value) { this._hass=value; if (!this._editing) this.render(); }
  set panel(value) { if (this._panel !== value) this._zones={}; this._panel=value; if (!this._editing) this.render(); }
  connectedCallback() { this.render(); }
  openZone(entry,area) {
    this._editing={entry,area};
    this._notice="";
    this.render();
  }
  async saveZone(form) {
    const editing=this._editing;
    if (!editing) return;
    const temperature=form.querySelector("[name=temperature]").value||null;
    const sources=Array.from(form.querySelectorAll("[name=sources]:checked"),x=>x.value);
    form.querySelectorAll("button").forEach(b=>b.disabled=true);
    try {
      this._zones[editing.entry]=await this._hass.callWS({type:"smart_heating_energy_manager/save_zone",entry_id:editing.entry,area_id:editing.area,temperature,sources});
      this._editing=null;
      this._notice=(this._hass.language||"en").startsWith("it")?"Configurazione salvata":"Configuration saved";
      this.render();
    } catch(err) {
      form.querySelectorAll("button").forEach(b=>b.disabled=false);
      form.querySelector(".error").textContent=err.message||String(err);
    }
  }
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
      const ids=e.entities||{}, diag=state(ids.calibration)?.attributes||{}, fit=diag.fit||diag.last_valid?.fit||{};
      const advisory=state(ids.recommended_source)?.attributes||{};
      const ranked=advisory.candidates||[];
      const costs=new Map(ranked.map(x=>[x.id,x.cost]));
      const rows=(e.generators||[]).map(g=>'<tr><td>'+html(g.name)+'</td><td>'+html(val(g.state_entity))+'</td><td>'+html(costs.has(g.id)?Number(costs.get(g.id)).toFixed(3)+" €/kWh":"—")+'</td></tr>').join("");
      const overview='<div class="grid">'+card(tr("Temperatura interna","Indoor temperature"),val(e.indoor))+card(tr("Temperatura esterna","Outdoor temperature"),val(e.outdoor))+card(tr("Fabbisogno termico","Heat demand"),val(ids.heat_demand))+card(tr("Generatore consigliato","Recommended source"),val(ids.recommended_source))+card(tr("Prezzo elettricità","Electricity price"),val(ids.electricity_price))+'</div>';
      const generators='<article><h2>'+tr("Confronto generatori","Generator comparison")+'</h2>'+(rows?'<table><thead><tr><th>'+tr("Generatore","Generator")+'</th><th>'+tr("Stato","State")+'</th><th>'+tr("Costo termico","Heat cost")+'</th></tr></thead><tbody>'+rows+'</tbody></table>':html(tr("Nessun generatore configurato","No generators configured")))+'</article>';
      const learning='<article><h2>'+tr("Modello termico","Thermal model")+'</h2><div class="grid">'+card(tr("Dispersioni","Heat loss"),fit.loss_w_k!=null?Number(fit.loss_w_k).toFixed(1)+" W/K":"—")+card(tr("Inerzia","Thermal capacity"),fit.capacity_kwh_k!=null?Number(fit.capacity_kwh_k).toFixed(2)+" kWh/K":"—")+card("COP",fit.cop!=null?Number(fit.cop).toFixed(2):"—")+card(tr("Campioni validi","Valid samples"),fit.samples??"—")+card(tr("Stato calibrazione","Calibration status"),val(ids.calibration))+'</div></article>';
      const allZones=Object.entries(this._zones[e.id]||e.zones||{});
      const admin=this._hass.user?.is_admin;
      const names=ids=>ids.map(id=>html(state(id)?.attributes?.friendly_name||id)).join(", ");
      const zoneCards=(entries)=>entries.map(([area,z])=>{
        const model=advisory.zones?.[area]||{};
        const thermal=(model.target_c!=null?`<p>${tr("Obiettivo","Target")}: ${html(model.target_c)} °C</p>`:"")+(model.heat_demand_kw!=null?`<p>${tr("Dispersione stimata","Estimated heat loss")}: ${html(Number(model.heat_demand_kw).toFixed(2))} kW</p>`:"");
        const thermometer=z.temperature||(!z.confirmed&&z.temperature_candidates?.length===1?z.temperature_candidates[0]:null);
        return '<article><h2>'+html(z.name)+'</h2><p>'+html(z.confirmed?tr("Configurata","Configured"):tr("Da confermare","Needs confirmation"))+'</p><strong>'+html(val(thermometer))+'</strong>'+thermal+'<p>'+tr("Termometro associato: ","Assigned thermometer: ")+(z.temperature?names([z.temperature]):"—")+'</p><p>'+tr("Termometri rilevati: ","Detected thermometers: ")+(names(z.temperature_candidates||[])||"—")+'</p><p>'+tr("Fonti di riscaldamento: ","Heating sources: ")+(names(z.confirmed?(z.sources||[]):(z.source_candidates||[]))||"—")+'</p>'+(admin?'<button data-entry="'+html(e.id)+'" data-area="'+html(area)+'">'+tr("Configura zona","Configure zone")+'</button>':'')+'</article>';
      }).join("");
      const visible=allZones.filter(([,z])=>z.temperature||(!z.confirmed&&z.temperature_candidates?.length));
      const zones='<article><h2>'+tr("Zone termiche","Heating zones")+'</h2><div class="grid">'+zoneCards(visible)+'</div>'+(visible.length?"":'<p>'+tr("Nessuna zona con termometro","No zones with thermometer")+'</p>')+'</article>';
      const settings='<article><h2>'+tr("Configurazione delle zone","Zone configuration")+'</h2><p>'+tr("Qui puoi configurare anche le aree senza termometro.","Configure areas without thermometers here as well.")+'</p><div class="grid">'+zoneCards(allZones)+'</div></article>';
      return '<section><h2>'+html(e.title)+'</h2>'+({overview:overview+zones+generators+learning,zones,generators,learning,settings}[this._page]||overview)+'</section>';
    }).join("");
    let modal="";
    if(this._editing){
      const {entry,area}=this._editing;
      const e=installations.find(x=>x.id===entry);
      const z=(this._zones[entry]||e?.zones||{})[area];
      if(z){
        const states=Object.values(this._hass.states);
        const name=s=>s.attributes.friendly_name||s.entity_id;
        const temps=states.filter(s=>s.entity_id.startsWith("sensor.")&&(s.attributes.device_class==="temperature"||["°C","°F"].includes(s.attributes.unit_of_measurement)||s.entity_id===z.temperature));
        const selected=z.confirmed?z.temperature:(z.temperature_candidates?.length===1?z.temperature_candidates[0]:null);
        const selectedSources=z.confirmed?(z.sources||[]):(z.source_candidates||[]);
        const available=states.filter(s=>["climate","switch","script"].includes(s.entity_id.split(".")[0]));
        if(selected && !temps.some(s=>s.entity_id===selected)) temps.push({entity_id:selected,attributes:{friendly_name:selected}});
        for(const id of selectedSources) if(!available.some(s=>s.entity_id===id)) available.push({entity_id:id,attributes:{friendly_name:id}});
        const order=(a,b)=>name(a).localeCompare(name(b));
        modal='<div class="overlay"><form class="dialog" role="dialog" aria-modal="true"><h2>'+html(z.name)+'</h2><label>'+tr("Termometro","Thermometer")+'<select name="temperature"><option value="">—</option>'+temps.sort(order).map(s=>'<option value="'+html(s.entity_id)+'" '+(selected===s.entity_id?"selected":"")+'>'+html(name(s))+'</option>').join("")+'</select></label><h3>'+tr("Fonti di riscaldamento","Heating sources")+'</h3><div class="choices">'+available.sort(order).map(s=>'<label><input type="checkbox" name="sources" value="'+html(s.entity_id)+'" '+(selectedSources.includes(s.entity_id)?"checked":"")+'>'+html(name(s))+'</label>').join("")+'</div><p class="error" role="alert"></p><footer><button type="button" data-close>'+tr("Annulla","Cancel")+'</button><button type="submit">'+tr("Salva","Save")+'</button></footer></form></div>';
      }
    }
    this.shadowRoot.innerHTML=`<style>
      :host{display:block;color:var(--primary-text-color);background:var(--primary-background-color);font-family:var(--paper-font-body1_-_font-family,system-ui);min-height:100vh}
      main{max-width:1400px;margin:auto;padding:clamp(12px,3vw,32px)} header{display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap} h1{font-size:clamp(22px,3vw,32px);margin:0} h2{font-size:17px;margin:0 0 14px} p,small{color:var(--secondary-text-color)} nav{display:flex;flex-wrap:wrap;gap:8px;margin:24px 0} button,a{font:inherit;color:var(--primary-color);background:var(--card-background-color);border:1px solid var(--divider-color);border-radius:10px;padding:10px 14px;cursor:pointer} button[aria-current=true]{background:var(--primary-color);color:var(--text-primary-color,#fff)} article{background:var(--ha-card-background,var(--card-background-color));border:1px solid var(--divider-color);border-radius:12px;padding:16px;min-width:0;margin-bottom:12px} .grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,180px),1fr));gap:12px} .grid article{margin:0} strong{display:block;font-size:22px;margin-top:8px;overflow-wrap:anywhere} table{width:100%;border-collapse:collapse;text-align:left} th,td{padding:12px 4px;border-bottom:1px solid var(--divider-color);overflow-wrap:anywhere} section{margin-bottom:24px} .mode{color:var(--secondary-text-color);font-size:14px} .grid+article{margin-top:12px}  .overlay{position:fixed;inset:0;background:#0008;z-index:100;display:grid;place-items:center;padding:16px}.dialog{background:var(--card-background-color);border-radius:14px;padding:24px;width:min(480px,90vw);max-height:85vh;overflow:auto;box-sizing:border-box}.dialog select{display:block;width:100%;padding:10px;margin:8px 0;background:var(--card-background-color);color:var(--primary-text-color)}.choices{max-height:40vh;overflow:auto}.choices label{display:block;padding:8px}.dialog footer{display:flex;justify-content:flex-end;gap:8px}.error{color:var(--error-color)} </style>
      <main><header><h1>Smart Heating Energy Manager</h1><span class="mode">● ${tr("Modalità consultiva · controllo disattivato","Advisory mode · control disabled")}</span></header>
      <nav>${pages.map(([k,t])=>'<button data-page="'+k+'" aria-current="'+(k===this._page)+'">'+html(t)+'</button>').join("")}</nav>
      ${this._notice?'<p role="status">'+html(this._notice)+'</p>':""}${sections||'<p>'+tr("Nessun impianto disponibile","No installation available")+'</p>'}</main>${modal}`;
    this.shadowRoot.querySelectorAll("button[data-page]").forEach(b=>b.addEventListener("click",()=>{this._page=b.dataset.page;this.render();}));
    this.shadowRoot.querySelectorAll("[data-area]").forEach(b=>b.addEventListener("click",()=>this.openZone(b.dataset.entry,b.dataset.area)));
    this.shadowRoot.querySelector("[data-close]")?.addEventListener("click",()=>{this._editing=null;this.render();});
    this.shadowRoot.querySelector("form.dialog")?.addEventListener("submit",event=>{event.preventDefault();this.saveZone(event.currentTarget);});
  }
}
if (!customElements.get("smart-heating-panel")) customElements.define("smart-heating-panel",SmartHeatingPanel);
