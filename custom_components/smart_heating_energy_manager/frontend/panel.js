/* SPDX-License-Identifier: GPL-3.0-only */
const html = (value) => String(value ?? "—").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
class SmartHeatingPanel extends HTMLElement {
  constructor() { super(); this.attachShadow({mode:"open"}); this._page="overview"; this._zones={}; this._editing=null; this._notice=""; this._history={}; this._historyPending=new Set(); }
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
    const thermal_group=form.querySelector("[name=thermal_group]")?.value||"";
    form.querySelectorAll("button").forEach(b=>b.disabled=true);
    try {
      this._zones[editing.entry]=await this._hass.callWS({type:"smart_heating_energy_manager/save_zone",entry_id:editing.entry,area_id:editing.area,temperature,sources,thermal_group});
      this._editing=null;
      this._notice=(this._hass.language||"en").startsWith("it")?"Configurazione salvata":"Configuration saved";
      this.render();
    } catch(err) {
      form.querySelectorAll("button").forEach(b=>b.disabled=false);
      form.querySelector(".error").textContent=[err.code,err.message].filter(Boolean).join(": ")||String(err);
    }
  }
  async loadHistory(entry, ids) {
    const key=entry.id;
    const entities=[...new Set([ids.indoor_average,ids.outdoor_temperature,ids.heat_demand,ids.electricity_price].filter(Boolean))];
    const signature=entities.join(",");
    if(!signature || this._historyPending.has(key)) return;
    const previous=this._history[key];
    if(previous?.signature===signature && Date.now()-previous.at<300000) return;
    this._historyPending.add(key);
    try {
      const end=new Date(), start=new Date(end.getTime()-86400000);
      const path="history/period/"+encodeURIComponent(start.toISOString())+"?end_time="+encodeURIComponent(end.toISOString())+"&filter_entity_id="+encodeURIComponent(signature)+"&minimal_response&no_attributes";
      const response=await this._hass.callApi("GET",path);
      const series={};
      for(const group of response||[]){
        const entity=group[0]?.entity_id;
        if(!entities.includes(entity)) continue;
        series[entity]=group.map(s=>({t:Date.parse(s.last_updated||s.last_changed),v:s.state==="unknown"||s.state==="unavailable"||s.state===""?null:Number(s.state)})).filter(s=>Number.isFinite(s.t)).sort((a,b)=>a.t-b.t);
      }
      this._history[key]={signature,at:Date.now(),start:+start,end:+end,series};
    } catch(error) {
      this._history[key]={signature,at:Date.now(),error:true};
    } finally {
      this._historyPending.delete(key);
      if(this.isConnected&&!this._editing) this.render();
    }
  }
  chart(record, definitions, empty) {
    if(!record?.series) return '<p class="empty">'+html(empty)+'</p>';
    const series=definitions.map(d=>({...d,points:record.series[d.id]||[]})).filter(d=>d.points.some(p=>Number.isFinite(p.v)));
    if(!series.length) return '<p class="empty">'+html(empty)+'</p>';
    const W=720,H=190,L=48,R=52,T=12,B=27;
    const axes={};
    for(const d of series){
      const values=d.points.filter(p=>Number.isFinite(p.v)).map(p=>p.v);
      const axisValues=axes[d.axis]??=[];
      for(const v of values)axisValues.push(v);
    }
    const bounds={};
    for(const [axis,values] of Object.entries(axes)){
      let lo=Infinity,hi=-Infinity;
      for(const v of values){lo=Math.min(lo,v);hi=Math.max(hi,v);}
      if(axis==="power")lo=Math.min(0,lo);
      if(hi-lo<.01){lo-=.5;hi+=.5;}
      bounds[axis]=[lo,hi];
    }
    const x=t=>L+Math.max(0,Math.min(1,(t-record.start)/(record.end-record.start)))*(W-L-R);
    const y=(v,a)=>T+(bounds[a][1]-v)/(bounds[a][1]-bounds[a][0])*(H-T-B);
    const grid=Array.from({length:5},(_,i)=>{
      const yy=T+i*(H-T-B)/4;
      const label=a=>bounds[a]?(bounds[a][1]-(bounds[a][1]-bounds[a][0])*i/4).toFixed(a==="price"?2:1):"";
      const left=series[0].axis, right=series.find(s=>s.axis!==left)?.axis;
      return '<line x1="'+L+'" x2="'+(W-R)+'" y1="'+yy+'" y2="'+yy+'" class="chart-grid"/><text x="'+(L-6)+'" y="'+(yy+4)+'" text-anchor="end">'+html(label(left))+'</text>'+(right?'<text x="'+(W-R+6)+'" y="'+(yy+4)+'">'+html(label(right))+'</text>':"");
    }).join("");
    const ticks=Array.from({length:5},(_,i)=>'<text x="'+(L+i*(W-L-R)/4)+'" y="'+(H-5)+'" text-anchor="middle">'+html(new Date(record.start+i*(record.end-record.start)/4).toLocaleTimeString(this._hass.language,{hour:"2-digit",minute:"2-digit"}))+'</text>').join("");
    const paths=series.map(d=>{
      let path="",open=false,previous=null;
      for(const p of d.points){
        if(!Number.isFinite(p.v)){open=false;previous=null;continue;}
        if(open && previous!==null)path+="L"+x(p.t).toFixed(1)+","+y(previous,d.axis).toFixed(1)+" ";
        path+=(open?"L":"M")+x(p.t).toFixed(1)+","+y(p.v,d.axis).toFixed(1)+" ";
        previous=p.v;open=true;
      }
      if(open && previous!==null)path+="L"+x(record.end).toFixed(1)+","+y(previous,d.axis).toFixed(1);
      return '<path d="'+path+'" fill="none" stroke="'+d.color+'" stroke-width="2" vector-effect="non-scaling-stroke"/>';
    }).join("");
    return '<svg class="chart" viewBox="0 0 '+W+' '+H+'" role="img" aria-label="Historical series">'+grid+ticks+paths+'</svg><div class="legend">'+series.map(d=>'<span><i style="background:'+d.color+'"></i>'+html(d.label)+'</span>').join("")+'</div>';
  }
  render() {
    if (!this._hass || !this._panel) return;
    const it=(this._hass.language||"en").startsWith("it");
    const tr=(a,b)=>it?a:b;
    const state=id=>this._hass.states[id];
    const val=id=>{const s=state(id);return !s||["unknown","unavailable"].includes(s.state)?"—":s.state+(s.attributes.unit_of_measurement?" "+s.attributes.unit_of_measurement:"");};
    const pages=[["overview",tr("Panoramica","Overview")],["zones",tr("Zone termiche","Heating zones")],["generators",tr("Generatori","Generators")],["learning",tr("Apprendimento","Learning")],["energy",tr("Energia","Energy")],["forecast",tr("Previsioni","Forecast")],["tariffs",tr("Tariffe","Tariffs")],["history",tr("Storico","History")],["settings",tr("Impostazioni","Settings")]];
    const icon=(name)=>'<ha-icon icon="mdi:'+name+'"></ha-icon>';
    const card=(title,value)=>'<article><small>'+html(title)+'</small><strong>'+html(value)+'</strong></article>';
    const installations=this._panel.config?.installations||[];
    const sections=installations.map(e=>{
      const ids=e.entities||{}, diag=state(ids.calibration)?.attributes||{}, fit=diag.fit||diag.last_valid?.fit||{};
      const advisory=state(ids.recommended_source)?.attributes||{};
      const ranked=advisory.candidates||[];
      if(["overview","history","tariffs"].includes(this._page)) this.loadHistory(e,ids);
      const costs=new Map(ranked.map(x=>[x.id,x.cost]));
      const kpi=(label,value,ico,tone)=>'<div class="kpi '+tone+'">'+icon(ico)+'<div><small>'+html(label)+'</small><strong>'+html(value)+'</strong></div></div>';
      const overview='<div class="kpis">'+kpi(tr("Temperatura interna media","Average indoor temperature"),val(ids.indoor_average),"home-thermometer","blue")+kpi(tr("Temperatura esterna","Outdoor temperature"),val(ids.outdoor_temperature),"thermometer","blue")+kpi(tr("Fabbisogno termico","Heat demand"),val(ids.heat_demand),"fire","orange")+kpi(tr("Generatore consigliato","Recommended source"),val(ids.recommended_source),"heat-pump","green")+kpi(tr("Costo termico stimato","Estimated heat cost"),ranked.length?Number(ranked[0].cost).toFixed(3)+" €/kWh":"—","cash-multiple","purple")+'</div>';
      const sorted=[...(e.generators||[])].sort((a,b)=>(costs.get(a.id)??Infinity)-(costs.get(b.id)??Infinity));
      const generators='<article class="generators"><h2>'+icon("chart-bar")+tr("Confronto generatori","Generator comparison")+'</h2>'+(sorted.length?sorted.map((g,i)=>'<div class="rank '+(ranked[0]?.id===g.id?"best":"")+'"><span class="rank-no">'+(costs.has(g.id)?i+1:"—")+'</span><div class="rank-name"><b>'+html(g.name)+'</b><small>'+html(val(g.state_entity))+'</small></div><b>'+html(costs.has(g.id)?Number(costs.get(g.id)).toFixed(3)+" €/kWh":"—")+'</b></div>').join(""):html(tr("Nessun generatore configurato","No generators configured")))+'</article>';
      const detail=(label,value)=>'<div class="detail"><span>'+html(label)+'</span><b>'+html(value)+'</b></div>';
      const learning='<article class="learning"><h2>'+icon("vector-triangle")+tr("Modello termico","Thermal model")+'</h2>'+detail(tr("Dispersioni H","Heat loss H"),advisory.loss_w_k!=null?Number(advisory.loss_w_k).toFixed(1)+" W/K":"—")+detail(tr("Inerzia C (stimata)","Capacity C (estimated)"),fit.capacity_kwh_k!=null?Number(fit.capacity_kwh_k).toFixed(2)+" kWh/K":"—")+detail(tr("Errore RMSE","RMSE error"),fit.rmse_kw!=null?Number(fit.rmse_kw).toFixed(2)+" kW":"—")+detail(tr("Campioni validi","Valid samples"),fit.samples??"—")+detail(tr("Stato calibrazione","Calibration status"),val(ids.calibration))+'</article>';
      const energyData=state(ids.energy_forecast)?.attributes||{};
      const metric=(v,u)=>v==null?"—":Number(v).toFixed(2)+" "+u;
      const energy='<article class="energy"><h2>'+icon("solar-power")+tr("Fotovoltaico e batteria","Solar PV and battery")+'</h2>'+detail(tr("FV attuale","Current PV"),metric(energyData.pv_kw,"kW"))+detail(tr("Batteria","Battery"),metric(energyData.battery_soc,"%"))+detail(tr("Immissione in rete","Grid export"),metric(energyData.export_kw,"kW"))+detail(tr("Consumo abitazione","Home consumption"),metric(energyData.home_kw,"kW"))+detail(tr("Prelievo rete","Grid import"),metric(energyData.grid_net_kw==null?null:Math.max(0,energyData.grid_net_kw),"kW"))+detail(tr("Potenza batteria (+ scarica)","Battery power (+ discharge)"),metric(energyData.battery_net_kw,"kW"))+detail(tr("Origine FV","PV source"),energyData.energy_origins?.pv_kw==="energy_dashboard"?tr("Pannello Energia","Energy dashboard"):energyData.energy_origins?.pv_kw==="manual"?tr("Manuale","Manual"):"—")+'</article>';
      const priceChart=this.chart(this._history[e.id],[{id:ids.electricity_price,axis:"price",color:"#48b8ed",label:tr("Prezzo marginale (€/kWh)","Marginal price (€/kWh)")}],tr("Storico non disponibile","History unavailable"));
      const tariffs='<article class="tariffs"><h2>'+icon("lightning-bolt")+tr("Prezzo energia","Energy price")+'</h2>'+detail(tr("PUN / indice attuale","Current price index"),metric(advisory.index_price,"€/kWh"))+detail(tr("Prezzo elettricità marginale","Marginal electricity price"),val(ids.electricity_price))+detail(tr("Origine prezzo","Price source"),advisory.price_source||"—")+(advisory.index_price!=null&&advisory.price_source!=="index"?'<p>'+tr("Indice rilevato: per utilizzarlo attiva la tariffa indicizzata nelle opzioni.","Index detected: enable indexed tariff in settings to use it.")+'</p>':"")+(val(ids.electricity_price)==="—"?'<p><a href="/config/integrations">'+tr("Configura tariffa elettrica","Configure electricity tariff")+'</a></p>':"")+'<h3>'+tr("Andamento ultime 24 ore","Last 24 hours")+'</h3>'+priceChart+'</article>';
      const history='<article class="history"><h2>'+icon("chart-line")+tr("Storico temperature e fabbisogno","Temperature and demand history")+'</h2>'+this.chart(this._history[e.id],[{id:ids.indoor_average,axis:"temp",color:"#f59e42",label:tr("Interna (°C)","Indoor (°C)")},{id:ids.outdoor_temperature,axis:"temp",color:"#48b8ed",label:tr("Esterna (°C)","Outdoor (°C)")},{id:ids.heat_demand,axis:"power",color:"#b38af3",label:tr("Fabbisogno (kW)","Demand (kW)")}],tr("Dati storici non disponibili","History unavailable"))+'</article>';
      const actions='<article class="actions"><h2>'+icon("lightning-bolt")+tr("Azioni rapide","Quick actions")+'</h2><button data-page="learning">'+tr("Modello e calibrazione","Model and calibration")+'</button><button data-page="generators">'+tr("Confronta generatori","Compare generators")+'</button><button data-page="forecast">'+tr("Previsioni e piano","Forecast and plan")+'</button><a href="/config/integrations">'+tr("Apri impostazioni","Open settings")+'</a></article>';
      const solarRows=(energyData.solar_forecast||[]).map(h=>'<tr><td>'+html(new Date(h.datetime).toLocaleString(this._hass.language,{weekday:"short",hour:"2-digit",minute:"2-digit"}))+'</td><td>'+html(metric(h.pv_kwh,"kWh"))+'</td></tr>').join("");
      const solarPanel='<article><h2>'+tr("Previsione fotovoltaica","Solar forecast")+'</h2>'+(solarRows?'<table><thead><tr><th>'+tr("Ora","Hour")+'</th><th>FV kWh</th></tr></thead><tbody>'+solarRows+'</tbody></table>':tr("Previsione non disponibile","Forecast unavailable"))+'</article>';
      const dhwData=energyData.dhw||{};
      const dhw=dhwData.entity?'<article class="dhw"><h2>'+icon("water-boiler")+tr("Acqua calda sanitaria","Domestic hot water")+'</h2>'+detail(tr("Stato","State"),dhwData.state||"—")+detail(tr("Temperatura acqua","Water temperature"),metric(dhwData.temperature_c,"°C"))+detail(tr("Potenza misurata","Measured power"),metric(dhwData.power_kw,"kW"))+detail(tr("Contatore energia","Energy meter"),metric(dhwData.energy_total_kwh,"kWh"))+detail(tr("Capacità","Capacity"),metric(dhwData.litres,"L"))+detail(tr("Energia termica ideale richiesta","Ideal heat required"),metric(dhwData.ideal_heat_kwh,"kWh"))+(dhwData.below_minimum===true?'<p>'+tr("Temperatura sotto il riferimento minimo; nessun rinvio suggerito.","Below minimum reference; no delay suggested.")+'</p>':"")+(dhwData.solar_window?detail(tr("Finestra solare potenziale","Potential solar window"),new Date(dhwData.solar_window.start).toLocaleTimeString(this._hass.language,{hour:"2-digit",minute:"2-digit"})+" – "+new Date(dhwData.solar_window.end).toLocaleTimeString(this._hass.language,{hour:"2-digit",minute:"2-digit"}))+detail(tr("Produzione FV potenzialmente coincidente","Potential PV overlap"),metric(dhwData.solar_window.potential_pv_kwh,"kWh")):"")+'<p>'+tr("Solo suggerimenti: produzione lorda, non surplus. Nessuna modifica a termostato o cicli sanitari.","Advisory only: gross production, not surplus. No changes to thermostat or sanitation cycles.")+'</p></article>':"";
      const joint=energyData.joint_plan||{};
      const jointRows=(joint.rows||[]).map(h=>'<tr><td>'+html(new Date(h.datetime).toLocaleString(this._hass.language,{weekday:"short",hour:"2-digit",minute:"2-digit"}))+'</td><td>'+html(metric(h.pv_kwh,"kWh"))+'</td><td>'+html(metric(h.heating_kwh,"kWh"))+'</td><td>'+html(metric(h.dhw_kwh,"kWh"))+'</td><td>'+html(metric(h.grid_kwh,"kWh"))+'</td><td>'+html(metric(h.export_kwh,"kWh"))+'</td><td>'+html(metric(h.battery_soc,"%"))+'</td><td>'+html(metric(h.cost,"€"))+'</td></tr>').join("");
      const jointPanel=joint.status?'<article><h2>'+tr("Pianificazione energetica congiunta","Joint energy planning")+'</h2><p>'+tr("Simulazione oraria: prezzi orari se disponibili, carico base configurato o appreso, riscaldamento già pianificato. Nessun controllo automatico.","Hourly simulation: hourly prices where available, configured or learned base load, fixed heating dispatch. No automatic control.")+'</p>'+(jointRows?detail(tr("Costo netto stimato del periodo","Estimated period net cost"),metric(joint.net_cost,"€"))+detail(tr("Avvio ACS ipotizzato","Proposed DHW start"),joint.dhw_start?new Date(joint.dhw_start).toLocaleString(this._hass.language):"—")+'<div style="overflow:auto"><table><thead><tr><th>'+tr("Ora","Hour")+'</th><th>FV</th><th>'+tr("Risc.","Heat")+'</th><th>ACS</th><th>'+tr("Prelievo","Import")+'</th><th>'+tr("Immissione","Export")+'</th><th>SOC</th><th>€</th></tr></thead><tbody>'+jointRows+'</tbody></table></div>':html(joint.status))+'</article>':"";
      const thermal=energyData.thermal_prediction||{};
      const thermalRows=(thermal.baseline||[]).map((h,i)=>'<tr><td>'+html(new Date(h.datetime).toLocaleString(this._hass.language,{weekday:"short",hour:"2-digit",minute:"2-digit"}))+'</td><td>'+html(metric(h.outdoor_c,"°C"))+'</td><td>'+html(metric(h.unheated_end_c,"°C"))+'</td><td>'+html(metric(h.end_c,"°C"))+'</td><td>'+html(metric(thermal.preheat?.[i]?.end_c,"°C"))+'</td><td>'+html(metric(h.heat_kwh,"kWh"))+'</td><td>'+html(metric(h.solar_gain_kwh,"kWh"))+'</td><td>'+html(h.comfort_met?tr("OK","OK"):tr("Sotto obiettivo","Below target"))+'</td></tr>').join("");
      const thermalPanel=thermal.status?'<article><h2>'+tr("Previsione temperatura interna","Indoor temperature forecast")+'</h2><p>'+tr("Modello termico a zona unica, con apporti solari opzionali stimati dal FV. Il preriscaldamento è uno scenario, non un risparmio garantito.","Single-zone thermal model with optional PV-based solar gains. Preheating is a scenario, not guaranteed savings.")+'</p>'+(thermalRows?detail(tr("Capacità termica","Thermal capacity"),metric(thermal.capacity_kwh_k,"kWh/K"))+detail(tr("Costo lordo mantenimento","Gross maintenance cost"),metric(thermal.baseline_gross_cost,"€"))+detail(tr("Costo senza apporti solari","Cost without solar gains"),metric(thermal.without_solar_gross_cost,"€"))+detail(tr("Copertura dati solari","Solar data coverage"),String(thermal.solar_gain_coverage??0)+"/"+String(thermal.solar_gain_hours??0))+detail(tr("Costo lordo preriscaldamento","Gross preheat cost"),metric(thermal.preheat_gross_cost,"€"))+'<div style="overflow:auto"><table><thead><tr><th>'+tr("Ora","Hour")+'</th><th>'+tr("Esterno","Outdoor")+'</th><th>'+tr("Senza calore nell’ora","No heat in hour")+'</th><th>'+tr("Mantenimento","Maintain")+'</th><th>'+tr("Preriscaldo","Preheat")+'</th><th>kWh</th><th>'+tr("Apporti solari","Solar gains")+'</th><th>Comfort</th></tr></thead><tbody>'+thermalRows+'</tbody></table></div>':html(thermal.status))+'</article>':"";
      const forecastRows=(energyData.plan||[]).map(h=>'<tr><td>'+html(new Date(h.datetime).toLocaleString(this._hass.language,{weekday:"short",hour:"2-digit",minute:"2-digit"}))+'</td><td>'+html(metric(h.outdoor_c,"°C"))+'</td><td>'+html(metric(h.heat_kw,"kW"))+'</td><td>'+html(h.generator_name||"—")+'</td><td>'+html(metric(h.cost_per_hour,"€/h"))+'</td><td>'+html(metric(h.electricity_price,"€/kWh"))+'<small>'+html(({hourly_index:tr("Orario","Hourly"),fixed:tr("Fisso","Fixed"),current_index_assumed:tr("Corrente stimato","Current assumed")})[h.price_source]||"—")+'</small>'+'</td><td>'+html(metric(h.pv_forecast_kwh,"kWh"))+'</td><td>'+html(metric(h.potential_solar_overlap_kwh,"kWh"))+'</td></tr>').join("");
      const forecast='<article><h2>'+tr("Pianificazione oraria","Hourly planning")+'</h2><p>'+tr("Prezzi orari se disponibili, altrimenti prezzo corrente. La produzione FV prevista non equivale a surplus disponibile.","Hourly prices where available, otherwise current price. Forecast PV production is not available surplus.")+'</p>'+(forecastRows?'<table><thead><tr><th>'+tr("Ora","Hour")+'</th><th>°C</th><th>kW</th><th>'+tr("Generatore","Generator")+'</th><th>€/h</th><th>'+tr("Tariffa","Tariff")+'</th><th>FV kWh</th><th>'+tr("FV potenziale","Potential PV")+'</th></tr></thead><tbody>'+forecastRows+'</tbody></table>':html(val(ids.energy_forecast)))+'</article>';
      const allZones=Object.entries(this._zones[e.id]||e.zones||{});
      const admin=this._hass.user?.is_admin;
      const names=ids=>ids.map(id=>html(state(id)?.attributes?.friendly_name||id)).join(", ");
      const zoneCards=(entries)=>entries.map(([area,z])=>{
        const model=advisory.zones?.[area]||{};
        const thermal=(model.target_c!=null?`<p>${tr("Obiettivo","Target")}: ${html(model.target_c)} °C</p>`:"")+(model.heat_demand_kw!=null?`<p>${tr("Dispersione stimata","Estimated heat loss")}: ${html(Number(model.heat_demand_kw).toFixed(2))} kW</p>`:"");
        const thermometer=z.temperature||(!z.confirmed&&z.temperature_candidates?.length===1?z.temperature_candidates[0]:null);
        if(z.outdoor) return '<article><h2>'+html(z.name)+'</h2><strong>'+html(val(thermometer))+'</strong>'+(admin?'<button data-entry="'+html(e.id)+'" data-area="'+html(area)+'">'+tr("Configura termometro","Configure thermometer")+'</button>':'')+'</article>';
        return '<article><h2>'+html(z.name)+'</h2><p>'+html(z.confirmed?tr("Configurata","Configured"):tr("Da confermare","Needs confirmation"))+'</p><strong>'+html(val(thermometer))+'</strong>'+thermal+'<p>'+tr("Termometro associato: ","Assigned thermometer: ")+(z.temperature?names([z.temperature]):"—")+'</p><p>'+tr("Termometri rilevati: ","Detected thermometers: ")+(names(z.temperature_candidates||[])||"—")+'</p><p>'+tr("Fonti di riscaldamento: ","Heating sources: ")+(names(z.confirmed?(z.sources||[]):(z.source_candidates||[]))||"—")+'</p>'+(admin?'<button data-entry="'+html(e.id)+'" data-area="'+html(area)+'">'+tr("Configura zona","Configure zone")+'</button>':'')+'</article>';
      }).join("");
      const visible=allZones.filter(([,z])=>z.temperature||(!z.confirmed&&z.temperature_candidates?.length));
      const zones='<article><h2>'+tr("Zone termiche","Heating zones")+'</h2><div class="grid">'+zoneCards(visible)+'</div>'+(visible.length?"":'<p>'+tr("Nessuna zona con termometro","No zones with thermometer")+'</p>')+'</article>';
      const grouped=Object.values(advisory.thermal_groups||{}).map(g=>'<div class="zone-row"><span>'+icon("home-group")+'</span><div><b>'+html(g.name)+'</b><small>'+html(g.areas.map(a=>(this._zones[e.id]||e.zones||{})[a]?.name||a).join(" · "))+'</small></div><b>'+html(metric(g.temperature_c,"°C"))+'</b></div>').join("");
      const compactZones='<article class="zones"><h2>'+icon("view-grid")+tr("Zone termiche","Heating zones")+'</h2>'+grouped+visible.filter(([,z])=>!z.thermal_group).map(([area,z])=>{const t=z.temperature||(!z.confirmed&&z.temperature_candidates?.length===1?z.temperature_candidates[0]:null);return '<div class="zone-row"><span>'+icon(z.outdoor?"thermometer":"home-thermometer")+'</span><div><b>'+html(z.name)+'</b>'+(!z.outdoor&&z.target_c!=null?'<small>Target: '+html(z.target_c)+' °C</small>':"")+'</div><b>'+html(val(t))+'</b></div>';}).join("")+'</article>';
      const settings='<article><h2>'+tr("Configurazione delle zone","Zone configuration")+'</h2><p>'+tr("Qui puoi configurare anche le aree senza termometro.","Configure areas without thermometers here as well.")+'</p><div class="grid">'+zoneCards(allZones)+'</div></article>';
      return '<section>'+({overview:overview+'<div class="dashboard">'+generators+compactZones+tariffs+learning+energy+history+actions+dhw+'</div>',zones,generators,learning,energy:energy+dhw,forecast:forecast+solarPanel+dhw+jointPanel+thermalPanel,tariffs,history,settings}[this._page]||overview)+'</section>';
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
        const configured=new Set((e.generators||[]).map(g=>g.control_entity).filter(Boolean));
        const available=states.filter(s=>(configured.has(s.entity_id)&&/^(climate|switch|script)\./.test(s.entity_id))||(s.entity_id.startsWith("climate.")&&(s.attributes.hvac_modes||[]).some(m=>["heat","heat_cool","auto"].includes(m)))||(s.entity_id.startsWith("switch.")&&s.attributes.device_class==="heater"));
        if(selected && !temps.some(s=>s.entity_id===selected)) temps.push({entity_id:selected,attributes:{friendly_name:selected}});
        const removedSources=selectedSources.filter(id=>!available.some(s=>s.entity_id===id));
        const order=(a,b)=>name(a).localeCompare(name(b));
        modal='<div class="overlay"><form class="dialog" role="dialog" aria-modal="true"><h2>'+html(z.name)+'</h2><label>'+tr("Termometro","Thermometer")+'<select name="temperature"><option value="">—</option>'+temps.sort(order).map(s=>'<option value="'+html(s.entity_id)+'" '+(selected===s.entity_id?"selected":"")+'>'+html(name(s))+'</option>').join("")+'</select></label>'+(z.outdoor?'':'<h3>'+tr("Fonti di riscaldamento","Heating sources")+'</h3><div class="choices">'+available.sort(order).map(s=>'<label><input type="checkbox" name="sources" value="'+html(s.entity_id)+'" '+(selectedSources.includes(s.entity_id)?"checked":"")+'>'+html(name(s))+'</label>').join("")+'</div>'+(removedSources.length?'<p>'+tr("Associazioni non valide escluse: ","Invalid mappings excluded: ")+html(removedSources.join(", "))+'</p>':"")+'<label>'+tr("Gruppo termico (facoltativo)","Thermal group (optional)")+'<input name="thermal_group" list="thermal-groups" maxlength="80" value="'+html(z.thermal_group||"")+'" placeholder="Open space"><datalist id="thermal-groups">'+[...new Set(Object.values(this._zones[entry]||e?.zones||{}).map(x=>x.thermal_group).filter(Boolean))].map(x=>'<option value="'+html(x)+'"></option>').join("")+'</datalist></label>')+'<p class="error" role="alert"></p><footer><button type="button" data-close>'+tr("Annulla","Cancel")+'</button><button type="submit">'+tr("Salva","Save")+'</button></footer></form></div>';
      }
    }
    this.shadowRoot.innerHTML=`<style>
      :host{display:block;color:var(--primary-text-color);background:var(--primary-background-color);font-family:var(--paper-font-body1_-_font-family,system-ui);min-height:100vh}
      main{max-width:1400px;margin:auto;padding:clamp(12px,3vw,32px)} header{display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap} h1{font-size:clamp(22px,3vw,32px);margin:0} h2{font-size:17px;margin:0 0 14px} p,small{color:var(--secondary-text-color)} nav{display:flex;flex-wrap:wrap;gap:8px;margin:24px 0} button,a{font:inherit;color:var(--primary-color);background:var(--card-background-color);border:1px solid var(--divider-color);border-radius:10px;padding:10px 14px;cursor:pointer} button[aria-current=true]{background:var(--primary-color);color:var(--text-primary-color,#fff)} article{background:var(--ha-card-background,var(--card-background-color));border:1px solid var(--divider-color);border-radius:12px;padding:16px;min-width:0;margin-bottom:12px} .grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,180px),1fr));gap:12px} .grid article{margin:0} strong{display:block;font-size:22px;margin-top:8px;overflow-wrap:anywhere} table{width:100%;border-collapse:collapse;text-align:left} th,td{padding:12px 4px;border-bottom:1px solid var(--divider-color);overflow-wrap:anywhere} section{margin-bottom:24px} .mode{color:var(--secondary-text-color);font-size:14px} .grid+article{margin-top:12px}  .overlay{position:fixed;inset:0;background:#0008;z-index:100;display:grid;place-items:center;padding:16px}.dialog{background:var(--card-background-color);border-radius:14px;padding:24px;width:min(480px,90vw);max-height:85vh;overflow:auto;box-sizing:border-box}.dialog select,.dialog input[name=thermal_group]{display:block;width:100%;padding:10px;margin:8px 0;background:var(--card-background-color);color:var(--primary-text-color)}.choices{max-height:40vh;overflow:auto}.choices label{display:block;padding:8px}.dialog footer{display:flex;justify-content:flex-end;gap:8px}.error{color:var(--error-color)} 
      main{max-width:1800px} header h1{display:flex;align-items:center;gap:10px} header h1 ha-icon{color:#f59e42;--mdc-icon-size:32px}
      .kpis{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:12px;margin-bottom:14px}
      .kpi{display:flex;align-items:center;gap:12px;padding:14px;border:1px solid var(--divider-color);border-radius:12px;background:var(--card-background-color);min-width:0}
      .kpi ha-icon{color:var(--tone);--mdc-icon-size:32px}.kpi strong{font-size:clamp(15px,1.6vw,24px);margin-top:4px}.kpi small{font-size:12px}.blue{--tone:#48b8ed}.orange{--tone:#f59e42}.green{--tone:#50c879}.purple{--tone:#b38af3}
      .kpi{background:color-mix(in srgb,var(--card-background-color) 91%,var(--tone))}
      .dashboard{display:grid;grid-template-columns:1.15fr 1fr 1fr;gap:14px;align-items:stretch}.dashboard article{margin:0;padding:14px}.dashboard h2{display:flex;align-items:center;gap:8px;font-size:16px}.dashboard .tariffs{grid-column:3;grid-row:1 / span 2}.dashboard .learning{grid-column:1;grid-row:2}.dashboard .energy{grid-column:2;grid-row:2}.dashboard .history{grid-column:1 / span 2}.dashboard .actions{grid-column:3}
      .rank,.zone-row,.detail{display:flex;align-items:center;gap:10px;padding:10px 0;border-bottom:1px solid var(--divider-color)}.rank:last-child,.zone-row:last-child,.detail:last-child{border-bottom:0}.rank-no{border-radius:50%;width:24px;height:24px;display:grid;place-items:center;background:var(--secondary-background-color);flex-shrink:0}.rank-name,.zone-row>div{flex:1;min-width:0;overflow-wrap:anywhere}.rank-name small,.zone-row small{display:block;margin-top:4px}.rank.best{border:1px solid #50c879;border-radius:8px;padding:8px;background:color-mix(in srgb,var(--card-background-color) 90%,#50c879)}.rank.best .rank-no{background:#50c879;color:#102018}.detail{justify-content:space-between;font-size:14px}.zone-row ha-icon{color:var(--primary-color)}.actions button,.actions a{display:block;width:100%;box-sizing:border-box;text-align:left;margin-bottom:8px;text-decoration:none}.chart{width:100%;height:auto;overflow:visible}.chart text{fill:var(--secondary-text-color);font-size:10px}.chart-grid{stroke:var(--divider-color);stroke-width:1}.legend{display:flex;gap:12px;justify-content:center;flex-wrap:wrap;font-size:12px}.legend i{display:inline-block;width:12px;height:3px;vertical-align:middle;margin-right:5px}.empty{font-size:13px;padding:16px 0} .tariffs h3{font-size:13px}
      @media(max-width:1100px){.kpis{grid-template-columns:repeat(3,minmax(0,1fr))}.dashboard{grid-template-columns:repeat(2,minmax(0,1fr))}.dashboard .tariffs,.dashboard .learning,.dashboard .energy,.dashboard .actions{grid-column:auto;grid-row:auto}.dashboard .history{grid-column:1 / -1}}
      @media(max-width:650px){main{padding:12px}.kpis{grid-template-columns:repeat(2,minmax(0,1fr))}.kpi{padding:10px;gap:7px}.kpi ha-icon{--mdc-icon-size:24px}.dashboard{grid-template-columns:1fr}.dashboard .history{grid-column:auto}nav{margin:14px 0}.rank{flex-wrap:wrap}}
      </style>
      <main><header><h1><ha-icon icon="mdi:fire"></ha-icon>Smart Heating Energy Manager</h1><span class="mode">● ${tr("Modalità consultiva · controllo disattivato","Advisory mode · control disabled")}</span></header>
      <nav>${pages.map(([k,t])=>'<button data-page="'+k+'" aria-current="'+(k===this._page)+'">'+html(t)+'</button>').join("")}</nav>
      ${this._notice?'<p role="status">'+html(this._notice)+'</p>':""}${sections||'<p>'+tr("Nessun impianto disponibile","No installation available")+'</p>'}</main>${modal}`;
    this.shadowRoot.querySelectorAll("button[data-page]").forEach(b=>b.addEventListener("click",()=>{this._page=b.dataset.page;this.render();}));
    this.shadowRoot.querySelectorAll("[data-area]").forEach(b=>b.addEventListener("click",()=>this.openZone(b.dataset.entry,b.dataset.area)));
    this.shadowRoot.querySelector("[data-close]")?.addEventListener("click",()=>{this._editing=null;this.render();});
    this.shadowRoot.querySelector("form.dialog")?.addEventListener("submit",event=>{event.preventDefault();this.saveZone(event.currentTarget);});
  }
}
if (!customElements.get("smart-heating-panel")) customElements.define("smart-heating-panel",SmartHeatingPanel);
