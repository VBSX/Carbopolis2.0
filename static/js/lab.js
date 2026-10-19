/* Lab guiado Carbopolis 2.0 */
let lastWater = {ph: null, temp: null, od: null};
let lastAir = {so2: null, nox: null, co2: null};
function phColor(ph){if(ph<3)return '#E53935';if(ph<5)return '#FB8C00';if(ph<6.5)return '#FDD835';if(ph<=7.5)return '#7ED6A0';if(ph<=9)return '#29B6F6';return '#5C6BC0';}
function setStep(id,n){document.querySelectorAll('#'+id+' .stepdot').forEach(d=>{d.classList.toggle('on',+d.dataset.s<=n);});}
function waterStep2(){
  const ph=parseFloat(document.getElementById('wSite').value||'6.8');
  const drop=document.getElementById('wDrop'),tube=document.getElementById('wTube'),liq=document.getElementById('wLiquid');
  drop.classList.remove('fall');void drop.offsetWidth;drop.classList.add('fall');
  tube.classList.remove('shake');void tube.offsetWidth;tube.classList.add('shake');
  setStep('wSteps',2);
  document.getElementById('wResult').innerHTML='🧪 Simulando a reação do indicador…';
  setTimeout(()=>{
    const c=phColor(ph);
    liq.style.background=c;liq.style.height='70%';
    let diag = ph<5.5 ? '🔴 <b>CENÁRIO ÁCIDO</b> — projeção hipotética a ser avaliada no EIA.' : (ph<=7.5 ? '🟢 <b>PRÓXIMO À FAIXA NEUTRA</b> — cenário de referência.' : '🔵 <b>CENÁRIO BÁSICO</b> — a origem precisaria ser investigada.');
    document.getElementById('wResult').innerHTML=`<b class="font-mono2 text-lg">pH projetado ${ph.toFixed(1)}</b><br>${diag}<br><span class="text-xs">Resultado de simulação, não de coleta real.</span>`;
    lastWater.ph=ph;setStep('wSteps',3);
  },900);
}
function waterStep4(){
  const t=parseFloat(document.getElementById('wTemp').value||'22');
  const od=Math.max(0,14.6-0.39*t+0.007*t*t-0.00006*t*t*t);
  document.getElementById('wOD').textContent=`OD estimado no cenário: ${od.toFixed(2)} mg/L a ${t}°C ${t>26?'(⚠️ uma temperatura mais alta reduziria o OD estimado)':''} — valor modelado, não medido.`;
  lastWater.temp=t;lastWater.od=+od.toFixed(2);setStep('wSteps',4);
  fillForm();
}
function airPreset(){const p=document.getElementById('aSite').value.split('|');document.getElementById('aSO2').value=p[0];document.getElementById('aNOx').value=p[1];document.getElementById('aCO2').value=p[2];}
function airStep2(){
  const s=+document.getElementById('aSO2').value||0,n=+document.getElementById('aNOx').value||0,c=+document.getElementById('aCO2').value||0;
  const alert=s>100||n>100;
  document.getElementById('aResult').innerHTML=`⚗️ Projeção calculada para o cenário:<br><b class="font-mono2">SO<sub>2</sub> ${s} · NO<sub>x</sub> ${n} · CO<sub>2</sub> ${c} ppm</b><br>${alert?'🔴 <b>CENÁRIO DE ATENÇÃO</b>':'🟢 Faixa de referência do modelo.'}<br><span class="text-xs">Simulação baseada em valores didáticos; não são emissões medidas em Ivaí dos Campos.</span>`;
  const frac=Math.min(1,s/200),ang=-70+frac*140;
  document.getElementById('aNeedle').setAttribute('transform',`rotate(${ang} 100 100)`);
  document.getElementById('aArc').style.stroke=alert?'#f87171':'#22ffaa';
  document.getElementById('aArc').style.strokeDashoffset=283-(283*frac);
  document.getElementById('aGaugeVal').textContent=`${s} ppm projetados`;
  lastAir={so2:s,nox:n,co2:c};fillForm();
}
function fillForm(){
  if(lastWater.ph!=null)document.getElementById('fPH').value=lastWater.ph;
  if(lastWater.temp!=null)document.getElementById('fTemp').value=lastWater.temp;
  if(lastWater.od!=null)document.getElementById('fOD').value=lastWater.od;
  if(lastAir.so2!=null){document.getElementById('fSO2').value=lastAir.so2;document.getElementById('fNOx').value=lastAir.nox;document.getElementById('fCO2').value=lastAir.co2;document.getElementById('fType').value=(lastWater.ph!=null&&lastAir.so2!=null)?'water':(lastAir.so2!=null?'air':'water');}
  if(lastWater.ph!=null&&(lastWater.ph<5.5))document.getElementById('fNotes').value='Cenário hipotético ácido — projeção didática para avaliação no EIA, não é amostra coletada.';
  setStep('wSteps',5);
}
