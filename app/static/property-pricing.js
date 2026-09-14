(function(){
  'use strict';
  if (!/\/property-submission\//.test(window.location.pathname)) return;

  const CRORE = 10000000;
  const LAKH = 100000;

  function number(value){
    if (value == null) return null;
    let text = String(value).trim().replace(/[₹,]/g,'').toLowerCase();
    if (!text) return null;
    text = text.replace(/crores?/g,'cr').replace(/lacs?/g,'lakh');
    const m = text.match(/(-?\d+(?:\.\d+)?)\s*(cr|lakh|lakhs)?/);
    if (!m) return null;
    const n = Number(m[1]);
    if (!Number.isFinite(n)) return null;
    if (m[2] === 'cr') return n * CRORE;
    if (m[2] === 'lakh' || m[2] === 'lakhs') return n * LAKH;
    return n;
  }

  function trim(n){ return Number(n.toFixed(2)).toString(); }
  function propertyValue(value){
    const n = number(value);
    if (n == null) return '';
    if (n >= CRORE) return trim(n / CRORE) + ' Cr';
    if (n >= LAKH) return trim(n / LAKH) + ' lakh';
    return '₹' + Math.round(n).toLocaleString('en-IN');
  }
  function rateValue(value){
    const n = number(value);
    return n == null ? '' : Math.round(n).toLocaleString('en-IN');
  }

  function bindRow(row){
    const area = row.querySelector('input[name="carpet_areas"]');
    const rate = row.querySelector('input[name="rate_per_sqft"]');
    const total = row.querySelector('input[name="bundle_prices"]');
    if (!area || !rate || !total || row.dataset.pricingBound === '1') return;
    row.dataset.pricingBound = '1';
    const rateLabel = rate.closest('div') && rate.closest('div').querySelector('label');
    const totalLabel = total.closest('div') && total.closest('div').querySelector('label');
    if (rateLabel) rateLabel.innerHTML='Rate / Sq.ft (₹) <span class="required">*</span>';
    if (totalLabel) totalLabel.innerHTML='Total Property Value / All Inclusive <span class="required">*</span>';
    rate.placeholder='e.g. 12000';
    total.placeholder='e.g. 80 lakh or 1.1 Cr';
    rate.title='Enter rate per square foot. Total property value will calculate automatically.';
    total.title='Enter total property value. Rate per square foot will calculate automatically.';

    const source = row.querySelector('input[name="pricing_source"]') || (()=>{
      const hidden=document.createElement('input'); hidden.type='hidden'; hidden.name='pricing_source'; hidden.value='rate'; row.appendChild(hidden); return hidden;
    })();
    function recalcFromRate(){
      source.value='rate';
      const a=number(area.value), r=number(rate.value);
      if (a != null && a > 0 && r != null && r >= 0) total.value=propertyValue(a*r);
    }
    function recalcFromTotal(){
      source.value='total';
      const a=number(area.value), t=number(total.value);
      if (a != null && a > 0 && t != null && t >= 0) rate.value=rateValue(t/a);
    }
    function recalcFromArea(){ if (source.value === 'total') recalcFromTotal(); else recalcFromRate(); }
    rate.addEventListener('input', recalcFromRate);
    total.addEventListener('input', recalcFromTotal);
    area.addEventListener('input', recalcFromArea);
    rate.addEventListener('blur', ()=>{ if(number(rate.value)!=null) rate.value=rateValue(rate.value); });
    total.addEventListener('blur', ()=>{ if(number(total.value)!=null) total.value=propertyValue(total.value); });
    if (number(total.value)!=null) total.value=propertyValue(total.value);
    if (number(rate.value)!=null) rate.value=rateValue(rate.value);
  }

  function bindAll(){ document.querySelectorAll('.config-row').forEach(bindRow); }
  function plainForSubmit(value){ const n=number(value); return n == null ? '' : String(n); }

  document.addEventListener('click', function(event){
    if (event.target && event.target.id === 'add-configuration') setTimeout(bindAll,0);
  });

  const form=document.querySelector('form[action*="/property-submission/"]');
  if(form){
    form.addEventListener('submit', function(){
      bindAll();
      document.querySelectorAll('.config-row').forEach(function(row){
        const area=row.querySelector('input[name="carpet_areas"]');
        const rate=row.querySelector('input[name="rate_per_sqft"]');
        const total=row.querySelector('input[name="bundle_prices"]');
        const source=row.querySelector('input[name="pricing_source"]');
        const a=number(area && area.value);
        if(source && source.value==='total'){
          const t=number(total && total.value);
          if(a && a>0 && t!=null) rate.value=String(t/a);
        }else{
          const r=number(rate && rate.value);
          if(a && a>0 && r!=null) total.value=String(a*r);
        }
        if(rate) rate.value=plainForSubmit(rate.value);
        if(total) total.value=plainForSubmit(total.value);
      });
    });
  }

  const observer=new MutationObserver(bindAll);
  observer.observe(document.getElementById('configuration-list') || document.body,{childList:true,subtree:true});
  bindAll();
})();
