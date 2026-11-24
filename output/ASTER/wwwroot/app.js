'use strict';
const $ = id => document.getElementById(id);
const example = () => ({assets:[
  {name:'Акции Север',kind:'stock',price:120,quantity:300,drift:.09,volatility:.24},
  {name:'Облигации Горизонт',kind:'bond',price:1000,quantity:40,drift:.055,volatility:.08},
  {name:'Валютная позиция',kind:'currency',price:3.2,quantity:7500,drift:.025,volatility:.14}
],correlation:[[1,.2,-.15],[.2,1,.05],[-.15,.05,1]],paths:100000,steps:12,seed:2026,confidence:.95,
stress:{name:'Базовый',driftShift:0,volatilityMultiplier:1,stockShock:0,bondShock:0,currencyShock:0},currency:'BYN'});
let model = example(), activeJob = null, lastResult = null, history = [], selected = new Set(), poll = null, request = null;
const presets = {base:{name:'Базовый',driftShift:0,volatilityMultiplier:1,stockShock:0,bondShock:0,currencyShock:0},
crash:{name:'Падение рынка',driftShift:-.12,volatilityMultiplier:1.7,stockShock:-.25,bondShock:-.08,currencyShock:.12},
currency:{name:'Валютный шок',driftShift:-.04,volatilityMultiplier:1.3,stockShock:-.08,bondShock:-.05,currencyShock:.25}};
function node(tag,text,cls){const e=document.createElement(tag);if(text!==undefined)e.textContent=text;if(cls)e.className=cls;return e;}
function money(value,currency=model.currency){return new Intl.NumberFormat('ru-RU',{maximumFractionDigits:0}).format(value)+' '+currency;}
function number(value){return new Intl.NumberFormat('ru-RU',{maximumFractionDigits:2}).format(value);}
function message(text=''){$('message').textContent=text;$('message').hidden=!text;}
async function api(path,body){
 const response=await fetch('/api/'+path,{method:body?'POST':'GET',headers:body?{'Content-Type':'application/json','X-Aster':'1'}:{},body:body?JSON.stringify(body):undefined});
 const value=await response.json();if(!response.ok||value.error)throw new Error(value.error||'Ошибка соединения');return value;
}
function updateValue(){$('initialValue').textContent=number(model.assets.reduce((s,a)=>s+a.price*a.quantity,0));}
function renderAssets(){
 $('assets').replaceChildren();
 model.assets.forEach((asset,i)=>{
  const tr=node('tr'),title=node('td'),name=node('input');name.value=asset.name;name.className='asset-name';name.maxLength=60;name.setAttribute('aria-label','Название актива '+(i+1));
  name.oninput=()=>asset.name=name.value;name.onchange=renderMatrix;title.append(name);
  const kind=node('select');kind.className='asset-kind';kind.setAttribute('aria-label','Тип актива '+(i+1));
  [['stock','Акции'],['bond','Облигации'],['currency','Валюта']].forEach(([v,t])=>{const o=node('option',t);o.value=v;kind.append(o);});kind.value=asset.kind;kind.onchange=()=>asset.kind=kind.value;title.append(kind);tr.append(title);
  [['price',1,0.000001,1000000],['quantity',1,0.000001,1000000],['drift',100,-100,100],['volatility',100,0,100]].forEach(([key,scale,min,max])=>{
   const td=node('td'),input=node('input');input.type='number';input.step='any';input.min=min;input.max=max;input.value=numberRaw(asset[key]*scale);input.setAttribute('aria-label',key+' '+asset.name);
   input.oninput=()=>{asset[key]=Number(input.value)/scale;updateValue();};td.append(input);tr.append(td);
  });
  const td=node('td'),remove=node('button','×','remove');remove.setAttribute('aria-label','Удалить '+asset.name);remove.disabled=model.assets.length===1;remove.onclick=()=>{
   model.assets.splice(i,1);model.correlation.splice(i,1);model.correlation.forEach(r=>r.splice(i,1));renderAssets();renderMatrix();};td.append(remove);tr.append(td);$('assets').append(tr);
 });updateValue();$('addAsset').disabled=model.assets.length>=8;
}
function numberRaw(n){return Number(n.toFixed(8));}
function renderMatrix(){
 const table=node('table'),head=node('tr');head.append(node('th','Актив'));
 model.assets.forEach((a,i)=>{const th=node('th',String(i+1));th.title=a.name;head.append(th);});table.append(head);
 model.assets.forEach((a,i)=>{const row=node('tr');row.append(node('th',(i+1)+'. '+a.name));model.assets.forEach((b,j)=>{
  const td=node('td'),input=node('input');input.type='number';input.min=-1;input.max=1;input.step=.05;input.value=model.correlation[i][j];input.disabled=i===j;input.setAttribute('aria-label','Корреляция '+a.name+' и '+b.name);
  input.onchange=()=>{model.correlation[i][j]=model.correlation[j][i]=Number(input.value);renderMatrix();};td.append(input);row.append(td);});table.append(row);
 });$('correlation').replaceChildren(table);
}
function stressInputs(s){$('driftShift').value=numberRaw(s.driftShift*100);$('volMultiplier').value=s.volatilityMultiplier;
 $('stockShock').value=numberRaw(s.stockShock*100);$('bondShock').value=numberRaw(s.bondShock*100);$('currencyShock').value=numberRaw(s.currencyShock*100);}
function applyModel(){renderAssets();renderMatrix();$('paths').value=model.paths;$('steps').value=model.steps;$('seed').value=model.seed;$('currency').value=model.currency;
 document.querySelectorAll('[name=confidence]').forEach(e=>e.checked=Number(e.value)===model.confidence);stressInputs(model.stress||presets.base);}
function readModel(){
 model.paths=Number($('paths').value);model.steps=Number($('steps').value);model.seed=Number($('seed').value);model.currency=$('currency').value.toUpperCase();model.confidence=Number(document.querySelector('[name=confidence]:checked').value);
 model.stress={name:model.stress?.name||'Свой сценарий',driftShift:Number($('driftShift').value)/100,volatilityMultiplier:Number($('volMultiplier').value),stockShock:Number($('stockShock').value)/100,bondShock:Number($('bondShock').value)/100,currencyShock:Number($('currencyShock').value)/100};
 if(!Number.isSafeInteger(model.seed)||model.seed<0)throw new Error('Начальное число должно быть целым: 0–9007199254740991.');
 return structuredClone(model);
}
function busy(value){$('run').disabled=value;$('cancel').hidden=!value;$('progress').hidden=!value;}
async function run(){
 try{message();const simulation=readModel(),key=JSON.stringify(simulation);if(!request||request.key!==key)request={key,id:crypto.randomUUID()};
  busy(true);$('results').hidden=true;const job=await api('submit',{simulation,requestId:request.id});activeJob=job.id;observe(job);
 }catch(e){busy(false);message(e.message);}
}
function observe(job){
 $('progressFill').style.width=(job.completed/job.total*100)+'%';$('progressText').textContent=number(job.completed)+' / '+number(job.total)+' траекторий';
 if(job.status==='running'){clearTimeout(poll);poll=setTimeout(async()=>{try{observe(await api('job/'+job.id));}catch(e){message(e.message+' Параметры запроса сохранены для повтора.');busy(false);}},650);}
 else{busy(false);request=null;if(job.status==='completed'){showResult(job);message();}else message(job.error||'Расчёт завершён без результата.');}
}
function showResult(job){
 lastResult=job;const r=job.result,c=job.simulation.currency;$('results').hidden=false;$('resultScenario').textContent=job.simulation.stress?.name||'Базовый';$('confidenceLabel').textContent=(job.simulation.confidence*100)+'%';
 $('var').textContent=money(r.selectedVar,c);$('varPercent').textContent=number(r.selectedVar/r.initialValue*100)+'% начальной стоимости';$('var99').textContent=money(r.var99,c);$('es').textContent=money(r.expectedShortfall95,c);
 $('lossProbability').textContent=number(r.lossProbability*100)+'%';$('runTime').textContent=number(r.elapsedSeconds)+' с · '+number(r.paths)+' траекторий';
 $('exportJson').href='/api/export/'+job.id;$('exportCsv').href='/api/export/'+job.id+'?format=csv';
 $('receipt').replaceChildren(...r.workers.map(w=>node('span',w.endpoint+' · '+number(w.paths)+' траекторий · повторов '+w.failures)));
 $('histLegend').replaceChildren(node('span','VaR 95%: '+money(r.var95,c)),node('span','VaR 99%: '+money(r.var99,c)));drawCharts();
}
function canvas(id){const e=$(id),rect=e.getBoundingClientRect(),ratio=devicePixelRatio||1;e.width=Math.max(1,Math.round(rect.width*ratio));e.height=Math.round(rect.height*ratio);const ctx=e.getContext('2d');ctx.scale(ratio,ratio);return[ctx,rect.width,rect.height];}
function colors(){const s=getComputedStyle(document.body);return Object.fromEntries(['ink','muted','line','forest','accent'].map(k=>[k,s.getPropertyValue('--'+k).trim()]));}
function axes(ctx,w,h,min,max,maxY,formatX){const c=colors(),left=48,top=15,right=w-15,bottom=h-35;ctx.font='9px Segoe UI';ctx.strokeStyle=c.line;ctx.fillStyle=c.muted;ctx.lineWidth=1;
 for(let i=0;i<4;i++){const y=top+(bottom-top)*i/3;ctx.beginPath();ctx.moveTo(left,y);ctx.lineTo(right,y);ctx.stroke();ctx.fillText(number(maxY*(1-i/3)),2,y+3);}
 for(let i=0;i<5;i++){const x=left+(right-left)*i/4;ctx.textAlign='center';ctx.fillText(formatX(min+(max-min)*i/4),x,bottom+20);}ctx.textAlign='left';return{left,top,right,bottom};}
function drawCharts(){
 if(!lastResult||$('results').hidden||$('lab').hidden)return;const r=lastResult.result,c=colors();let[ctx,w,h]=canvas('histogram');const bins=r.histogram,max=Math.max(...bins.map(b=>b.count)),minX=bins[0].from,maxX=bins.at(-1).to;
 const a=axes(ctx,w,h,minX,maxX,max,v=>number(v/1000)+'к'),bw=(a.right-a.left)/bins.length;bins.forEach((b,i)=>{const bh=b.count/Math.max(1,max)*(a.bottom-a.top);ctx.fillStyle=b.to>=r.var95?c.accent:c.forest;ctx.fillRect(a.left+i*bw+1,a.bottom-bh,Math.max(1,bw-2),bh);});
 if(maxX>minX){[r.var95,r.var99].forEach((v,i)=>{const x=a.left+(v-minX)/(maxX-minX)*(a.right-a.left);ctx.setLineDash([3,3]);ctx.strokeStyle=c.ink;ctx.beginPath();ctx.moveTo(x,a.top);ctx.lineTo(x,a.bottom);ctx.stroke();ctx.setLineDash([]);ctx.fillStyle=c.ink;ctx.fillText(i?'99%':'95%',Math.min(x+3,a.right-25),a.top+10+i*13);});}
 [ctx,w,h]=canvas('trajectories');const values=r.samples.flatMap(s=>s.values),lo=Math.min(...values),hi=Math.max(...values),span=Math.max(1,hi-lo);const left=48,right=w-15,top=15,bottom=h-35;
 ctx.font='9px Segoe UI';ctx.fillStyle=c.muted;ctx.strokeStyle=c.line;for(let i=0;i<4;i++){const y=top+(bottom-top)*i/3;ctx.beginPath();ctx.moveTo(left,y);ctx.lineTo(right,y);ctx.stroke();ctx.fillText(number((hi-span*i/3)/1000)+'к',0,y+3);}
 for(let i=0;i<5;i++)ctx.fillText((i*3)+' мес.',left+(right-left)*i/4-10,bottom+20);
 r.samples.forEach((s,i)=>{ctx.strokeStyle=i===0?c.forest:c.muted;ctx.globalAlpha=i===0?1:.22;ctx.lineWidth=i===0?1.8:.7;ctx.beginPath();s.values.forEach((v,j)=>{const x=left+(right-left)*j/(s.values.length-1),y=bottom-(v-lo)/span*(bottom-top);j?ctx.lineTo(x,y):ctx.moveTo(x,y);});ctx.stroke();});ctx.globalAlpha=1;
}
function switchTab(tab){document.querySelectorAll('.tabs button').forEach(e=>e.classList.toggle('active',e.dataset.tab===tab));document.querySelectorAll('.tab-panel').forEach(e=>e.hidden=e.id!==tab);message();if(tab==='history')loadHistory();if(tab==='nodes')loadNodes();if(tab==='lab')drawCharts();}
async function loadHistory(){try{history=await api('history');selected=new Set([...selected].filter(id=>history.some(j=>j.id===id)));renderHistory();}catch(e){message(e.message);}}
const statusText={running:'Выполняется',completed:'Завершён',cancelled:'Отменён',failed:'Ошибка',interrupted:'Прерван при перезапуске'};
function renderHistory(){
 const list=$('historyList');list.replaceChildren();if(!history.length){list.append(node('div','Первый эксперимент появится здесь после запуска.','empty'));$('comparison').hidden=true;return;}
 history.forEach(job=>{const row=node('div',undefined,'history-item'),check=node('input');check.type='checkbox';check.checked=selected.has(job.id);check.disabled=job.status!=='completed';check.setAttribute('aria-label','Сравнить расчёт '+job.id);check.onchange=()=>{if(check.checked&&selected.size>=2){check.checked=false;message('Для сравнения выберите ровно два расчёта.');return;}check.checked?selected.add(job.id):selected.delete(job.id);compare();};row.append(check);
 const title=node('div');title.append(node('strong',job.simulation.stress?.name||'Базовый'),node('small',new Date(job.created).toLocaleString('ru-RU')+' · '+number(job.total)+' траекторий'));row.append(title);
 const value=node('div');value.append(node('strong',job.result?money(job.result.selectedVar,job.simulation.currency):'—'),node('small','VaR '+job.simulation.confidence*100+'%'));row.append(value);
 row.append(node('div',statusText[job.status], 'status'));const actions=node('div'),open=node('button','Открыть ↗','text-button');open.onclick=async()=>{try{const j=await api('job/'+job.id);switchTab('lab');activeJob=j.id;if(j.status==='completed')showResult(j);else{busy(j.status==='running');observe(j);} }catch(e){message(e.message);}};actions.append(open);
 const remove=node('button','Удалить','text-button');remove.disabled=job.status==='running';remove.onclick=async()=>{if(!confirm('Удалить этот расчёт и его результаты?'))return;try{await api('delete',{id:job.id});selected.delete(job.id);await loadHistory();}catch(e){message(e.message);}};actions.append(remove);row.append(actions);list.append(row);
 });compare();
}
function compare(){const box=$('comparison');box.hidden=selected.size!==2;if(box.hidden)return;const[a,b]=history.filter(j=>selected.has(j.id));box.replaceChildren(node('h3','Сравнение завершённых экспериментов'));
 box.append(node('p',(a.simulation.stress?.name||'Базовый')+': VaR 95% '+money(a.result.var95,a.simulation.currency)),node('p',(b.simulation.stress?.name||'Базовый')+': VaR 95% '+money(b.result.var95,b.simulation.currency)));
 if(a.simulation.currency===b.simulation.currency)box.append(node('p','Разница второго и первого: '+money(b.result.var95-a.result.var95,a.simulation.currency)));
 box.append(node('p','Сравнивайте параметры портфелей и прогнозов: изменение VaR может быть вызвано их различием.','hint'));
}
async function loadNodes(){try{const nodes=await api('workers');$('connection').textContent=nodes.filter(w=>w.online).length+' / '+nodes.length+' узла на связи';$('connection').classList.toggle('offline',nodes.every(w=>!w.online));
 $('nodesList').replaceChildren(...nodes.map((w,i)=>{const n=node('article',undefined,'node'+(w.online?'':' offline'));n.append(node('div',String(i+1).padStart(2,'0'),'node-no'),node('h3',w.endpoint),node('p',w.online?'На связи · PID '+w.info.pid+' · потоков '+w.info.threads:'Нет соединения'),node('p',w.online?'Готов к назначению партий траекторий.':w.error));return n;}));
 }catch(e){$('connection').textContent='Сервер недоступен';$('connection').classList.add('offline');message(e.message);}}
$('run').onclick=run;$('cancel').onclick=async()=>{try{await api('cancel',{id:activeJob});}catch(e){message(e.message);}};
$('addAsset').onclick=()=>{if(model.assets.length>=8)return;const i=model.assets.length;model.assets.push({name:'Актив '+(i+1),kind:'stock',price:100,quantity:100,drift:.05,volatility:.2});model.correlation.forEach(r=>r.push(0));model.correlation.push(Array.from({length:i+1},(_,j)=>j===i?1:0));renderAssets();renderMatrix();};
$('resetCorrelation').onclick=()=>{model.correlation=model.assets.map((_,i)=>model.assets.map((_,j)=>i===j?1:0));renderMatrix();};
$('example').onclick=()=>{model=example();applyModel();message();};
document.querySelectorAll('[data-scenario]').forEach(e=>e.onclick=()=>{const k=e.dataset.scenario;model.stress=structuredClone(presets[k]||{...model.stress,name:'Свой сценарий'});stressInputs(model.stress);document.querySelectorAll('[data-scenario]').forEach(b=>b.classList.toggle('selected',b===e));});
['driftShift','volMultiplier','stockShock','bondShock','currencyShock'].forEach(id=>$(id).oninput=()=>{model.stress.name='Свой сценарий';document.querySelectorAll('[data-scenario]').forEach(b=>b.classList.toggle('selected',b.dataset.scenario==='custom'));});
document.querySelectorAll('.tabs button').forEach(e=>e.onclick=()=>switchTab(e.dataset.tab));$('refreshNodes').onclick=loadNodes;$('refreshHistory').onclick=loadHistory;
$('theme').onclick=()=>{document.body.classList.toggle('dark');localStorage.setItem('aster-theme',document.body.classList.contains('dark')?'dark':'light');drawCharts();};
if(localStorage.getItem('aster-theme')==='dark')document.body.classList.add('dark');
function download(content,name){const a=node('a');a.href=URL.createObjectURL(new Blob([content],{type:'application/json'}));a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000);}
$('savePortfolio').onclick=()=>{try{download(JSON.stringify(readModel(),null,2),'aster-portfolio.json');}catch(e){message(e.message);}};
$('import').onclick=()=>$('portfolioFile').click();$('portfolioFile').onchange=async e=>{try{const file=e.target.files[0];if(!file)return;if(file.size>1024*1024)throw new Error('Файл не более 1 МБ.');const v=JSON.parse(await file.text());
 if(!Array.isArray(v.assets)||v.assets.length<1||v.assets.length>8||!Array.isArray(v.correlation)||v.correlation.length!==v.assets.length||v.correlation.some(r=>!Array.isArray(r)||r.length!==v.assets.length))throw new Error('Неверная структура портфеля.');
 model=v;model.stress||=structuredClone(presets.base);applyModel();message('Портфель загружен. Числовые ограничения и матрица будут проверены при запуске.');}catch(e){message('Ошибка импорта: '+e.message);}finally{e.target.value='';}};
let resize;window.addEventListener('resize',()=>{clearTimeout(resize);resize=setTimeout(drawCharts,150);});applyModel();loadNodes();
