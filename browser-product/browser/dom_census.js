(nodes,config)=>{
 const key=Symbol.for('next-wave.browser-observer.identity.v1');
 const state=globalThis[key]||(globalThis[key]={objects:new WeakMap(),next:0,epoch:Math.random().toString(36).slice(2)});
 const identity=o=>{if(!state.objects.has(o))state.objects.set(o,state.epoch+':'+(++state.next));return state.objects.get(o)};
 const extract=e=>({tag:e.tagName.toLowerCase(),type:e.getAttribute('type')||'',role:e.getAttribute('role')||'',label:(e.labels?[...e.labels].map(x=>x.innerText).join(' '):'')||e.getAttribute('aria-label')||e.getAttribute('title')||e.getAttribute('placeholder')||e.innerText||(['submit','button','reset'].includes(e.type)?e.value:'')||e.getAttribute('name')||'',name:e.getAttribute('name')||'',required:e.required||e.getAttribute('aria-required')==='true',disabled:e.disabled||e.getAttribute('aria-disabled')==='true',value:e.type==='file'?'':(e.value||(e.isContentEditable?e.innerText:'')),href:e.getAttribute('href')||'',options:e.tagName==='SELECT'?[...e.options].slice(0,80).map(o=>({value:o.value,label:o.text,disabled:o.disabled})):[],checked:!!e.checked,form:!!e.form,accept:e.getAttribute('accept')||'',autocomplete:e.getAttribute('autocomplete')||'',form_method:e.form?.method||'',form_action:e.form?(e.hasAttribute('formaction')?e.formAction:e.form.action):'',form_enctype:e.form?.enctype||'',form_index:e.form?[...e.ownerDocument.forms].indexOf(e.form):-1,form_has_file:!!e.form&&[...e.form.elements].some(c=>c.tagName==='INPUT'&&c.type==='file'),form_upload_only:(()=>{const f=e.form;if(!f||f.method.toLowerCase()!=='post')return false;const inputs=[...f.elements];if(!inputs.some(c=>c.tagName==='INPUT'&&c.type==='file'))return false;if(inputs.some(c=>['INPUT','TEXTAREA','SELECT'].includes(c.tagName)&&!['file','hidden','submit','button','reset','image'].includes(c.type)))return false;const action=e.hasAttribute('formaction')?e.formAction:f.action;const path=new URL(action,e.ownerDocument.URL).pathname;if(!/(?:^|\/)(?:upload|attach|document|file)[\w-]*(?:\/|$)/i.test(path))return false;return !/(?:submit|finali[sz]e|complete|send|confirm|approve)\s+(?:the\s+)?(?:application|form|registration)/i.test(f.innerText||'')})(),readonly:!!e.readOnly,multiple:!!e.multiple,min:e.getAttribute('min'),max:e.getAttribute('max'),maxlength:e.getAttribute('maxlength'),pattern:e.getAttribute('pattern'),description:(e.getAttribute('aria-describedby')||'').split(/\s+/).map(id=>e.ownerDocument.getElementById(id)?.innerText||'').join(' ').slice(0,500),upload_hint:e.type==='file'?(e.closest('label')?.innerText||e.parentElement?.innerText||'').slice(0,320):'',validation_message:e.validationMessage||'',file_count:e.files?.length||0,contenteditable:e.isContentEditable});
 let visible=0,results=[];const cap=config.limit;
 for(let index=0;index<Math.min(nodes.length,10000);index++){
  const e=nodes[index],b=e.getBoundingClientRect(),css=getComputedStyle(e);
  const shown=css.visibility!=='hidden'&&css.display!=='none'&&b.width>0&&b.height>0;
  if(!shown&&e.type!=='file')continue;
  if(config.query&&!((e.innerText||e.getAttribute('aria-label')||'').toLowerCase().includes(config.query)))continue;
  visible++;
  if(visible<=config.offset||results.length>=cap)continue;
  const data=extract(e);
  const labelled=(e.getAttribute('aria-labelledby')||'').split(/\s+/).map(id=>e.ownerDocument.getElementById(id)?.textContent||'').join(' ').trim();
  data.label=String(labelled||e.getAttribute('aria-label')||data.label||e.querySelector('img[alt]')?.getAttribute('alt')||e.querySelector('svg title')?.textContent||'').trim().slice(0,300);
  data.value=String(data.value||'').slice(0,500);
  const hidden=e.form?[...e.form.elements].filter(x=>x.type==='hidden'):[];
  data.form_state_complete=hidden.length<=50&&hidden.every(x=>String(x.value).length<=2048);
  data._hidden_fields=hidden.slice(0,50).map(x=>[x.name,String(x.value).slice(0,2048)]);
  data.form_auth=!!e.form&&[...e.form.elements].some(x=>x.type==='password'||x.autocomplete==='current-password');
  data.form_method=e.form?(e.hasAttribute('formmethod')?e.formMethod:e.form.method):'';
  data.form_search_only=!!e.form&&data.form_method.toLowerCase()==='get'&&[...e.form.elements].some(x=>((['search','text',''].includes(x.type)||x.tagName==='TEXTAREA')||x.tagName==='TEXTAREA')&&/^(q|query|search|search_query|searchTerm|search-term)$/i.test(x.name))&&[...e.form.elements].every(x=>x.disabled||x.tagName==='FIELDSET'||(x.tagName==='SELECT'&&/^(language|hl|locale)$/i.test(x.name))||['hidden','submit','button','reset','image'].includes(x.type)||(((['text','search',''].includes(x.type)||x.tagName==='TEXTAREA')||x.tagName==='TEXTAREA')&&/^(q|query|search|search_query|searchTerm|search-term)$/i.test(x.name)));
  data.selected=e.getAttribute('aria-selected')==='true';data.expanded=e.getAttribute('aria-expanded');data.controls=e.getAttribute('aria-controls')||'';
  const dialog=e.closest('dialog,[role=dialog],[role=alertdialog]');data.overlay_id=dialog?(dialog.id||dialog.getAttribute('aria-label')||dialog.tagName.toLowerCase()):null;
  data.dom_id=e.id||'';data.link_target=e.getAttribute('target')||'';
  data.options=data.options.map(o=>({...o,label:String(o.label).slice(0,300)}));
  data.node_identity=identity(e);
  data._files=e.files?[...e.files].slice(0,20).map(f=>({identity:identity(f),name:f.name,size:f.size,type:f.type,lastModified:f.lastModified})):[];
  results.push({index,data,box:shown?{x:b.x,y:b.y,width:b.width,height:b.height}:null});
 }
 return {results,total:nodes.length,visible,truncated:nodes.length>10000||visible>config.offset+results.length};
}
