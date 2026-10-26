"""The album: a single-file chart editor (index.html).

The page needs no network or server. It embeds the model of every chart and
redraws it with the same algorithm as the Python side; connectors are routed
by libavoid, inlined from vendor/web. Blocks can be moved and resized,
connectors edited and re-attached, charts drawn from scratch, and everything
exported as SVG or PNG or saved as a project file.
"""

import base64
import json

from .text import xml_escape
from .vendored import web_asset

CSS = r"""
*,*::before,*::after{box-sizing:border-box}
:root{
  --bg:#eef1f5; --panel:#fff; --ink:#111820; --muted:#67757f; --line:#dbe2ea;
  --accent:#252525; --accent-soft:#eeeeee; --danger:#333333; --hover:#f2f5f9;
  --field:#fbfcfe; --chart-bg:#ffffff;
  --shadow:0 1px 2px rgba(16,24,32,.06),0 6px 20px rgba(16,24,32,.07);
  --font:"Segoe UI","Noto Sans",Inter,Arial,sans-serif;
}
body[data-theme="dark"]{
  --bg:#0d1117; --panel:#161b22; --ink:#e6edf3; --muted:#8b949e; --line:#26303b;
  --accent:#bbbbbb; --accent-soft:#303030; --danger:#dddddd; --hover:#1c242e;
  --field:#0f151d; --chart-bg:#ffffff;
  --shadow:0 1px 2px rgba(0,0,0,.4),0 8px 24px rgba(0,0,0,.35);
  color-scheme:dark;
}
html,body{height:100%}
body{margin:0;font-family:var(--font);background:var(--bg);color:var(--ink);
     font-size:14px;overflow:hidden;-webkit-user-select:none;user-select:none;
     display:flex;flex-direction:column;height:100vh;height:100dvh;
     -webkit-tap-highlight-color:transparent;--top:52px}
button,select,input,textarea{font:inherit;color:inherit}
button{cursor:pointer;background:var(--panel);border:1px solid var(--line);
       border-radius:8px;padding:6px 11px}
button:hover{background:var(--hover);border-color:var(--muted)}
button.primary{background:var(--accent);border-color:var(--accent);color:#fff}
button.primary:hover{background:#404040}
button.on{background:var(--accent-soft);border-color:#888;color:var(--ink)}
button.ghost{border-color:transparent;background:transparent}
button:disabled{opacity:.4;cursor:default}
.topbar{flex:0 0 auto;height:var(--top);display:flex;align-items:center;gap:8px;
        padding:0 max(14px,env(safe-area-inset-right)) 0 max(14px,env(safe-area-inset-left));
        background:var(--panel);border-bottom:1px solid var(--line);z-index:45}
.brand{min-width:0}
.more{display:flex;align-items:center;gap:8px}
.brand{font-weight:650;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.brand .sub{color:var(--muted);font-weight:400;font-size:12.5px}
.grow{flex:1 1 auto}.group{display:flex;gap:6px;align-items:center}
.sep{width:1px;height:24px;background:var(--line);margin:0 3px}
.layout{display:flex;flex:1 1 auto;min-height:0}
aside{background:var(--panel);display:flex;flex-direction:column;min-height:0}
aside.nav{flex:0 0 250px;border-right:1px solid var(--line)}
aside.insp{flex:0 0 280px;border-left:1px solid var(--line);padding:12px 14px;
           overflow:auto}
.navhead{display:flex;gap:6px;padding:10px 10px 6px}
.navhead input{flex:1 1 auto;min-width:0;padding:6px 9px;border:1px solid var(--line);
               border-radius:8px;background:var(--field);color:var(--ink)}
.tree{overflow:auto;padding:0 8px 14px;min-height:0;flex:1 1 auto}
.tree .sec{font-size:11px;letter-spacing:.07em;text-transform:uppercase;
           color:var(--muted);padding:12px 8px 5px;font-weight:600}
.tree a{display:flex;gap:6px;align-items:baseline;padding:6px 9px;border-radius:7px;
        color:var(--ink);text-decoration:none;overflow-wrap:anywhere;line-height:1.35;
        cursor:pointer}
.tree a:hover{background:var(--hover)}
.tree a.active{background:var(--accent-soft);color:var(--ink);font-weight:600}
.tree a .ln{color:var(--muted);font-size:11.5px;font-weight:400;margin-left:auto}
.tree a.edited .ln::after{content:" •";color:var(--accent)}
main{flex:1 1 auto;display:flex;flex-direction:column;min-width:0;min-height:0}
.toolbar{height:46px;display:flex;align-items:center;gap:7px;padding:0 12px;
         border-bottom:1px solid var(--line);background:var(--panel)}
.toolbar .name{font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.toolbar .meta{color:var(--muted);font-size:12.5px;font-family:Consolas,monospace;
               white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:38%}
.zoomval{min-width:50px;text-align:center;color:var(--muted);font-variant-numeric:tabular-nums}
.work{flex:1 1 auto;display:flex;min-height:0}
.palette{flex:0 0 58px;border-right:1px solid var(--line);background:var(--panel);
         padding:8px 0;display:flex;flex-direction:column;gap:4px;align-items:center;
         overflow:auto}
.palette button{width:42px;height:42px;padding:0;display:grid;place-items:center;
                border-radius:9px}
.palette .gap{height:8px}
.palette svg{pointer-events:none}
.stage{flex:1 1 auto;overflow:auto;padding:22px;min-height:0}
.sheet{background:var(--chart-bg);border-radius:10px;box-shadow:var(--shadow);padding:16px;
       margin:0 auto;width:max-content;max-width:none}
.sheet svg{display:block;touch-action:none}
.caption{text-align:center;color:var(--muted);padding:10px 0 24px;font-size:13px}
.hint{position:absolute;pointer-events:none}
svg .shp{cursor:move}
svg .edge-hit{stroke:transparent;stroke-width:12;fill:none;cursor:pointer}
svg .sel-outline{fill:none;stroke:var(--accent);stroke-width:2;
                 stroke-dasharray:5 3;pointer-events:none}
svg .handle{fill:#fff;stroke:var(--accent);stroke-width:1.6;cursor:pointer}
svg .handle.mid{fill:var(--accent-soft)}
svg .handle.bound{fill:#555555;stroke:#333333}
svg .guide{stroke:#555555;stroke-width:1;stroke-dasharray:4 3;pointer-events:none}
svg .marquee{fill:rgba(0,0,0,.10);stroke:var(--accent);stroke-width:1;
             stroke-dasharray:4 3;pointer-events:none}
.insp h3{margin:0 0 6px;font-size:12px;letter-spacing:.05em;text-transform:uppercase;
         color:var(--muted)}
.insp label{display:block;font-size:12.5px;color:var(--muted);margin:12px 0 5px}
.insp select,.insp textarea,.insp input{width:100%;padding:7px 9px;
  border:1px solid var(--line);border-radius:8px;background:var(--field);color:var(--ink)}
.insp textarea{min-height:88px;resize:vertical;font-family:Consolas,monospace;
               font-size:13px;line-height:1.45}
.insp .row{display:flex;gap:6px;margin-top:10px}
.insp .row>*{flex:1 1 auto}
.insp .note{color:var(--muted);font-size:12.2px;line-height:1.55;margin-top:14px}
.insp .kbd{font-family:Consolas,monospace;background:var(--hover);border:1px solid var(--line);
           border-radius:4px;padding:0 4px}
.toast{position:fixed;left:50%;bottom:24px;transform:translate(-50%,14px);
       background:#111820;color:#fff;padding:9px 16px;border-radius:9px;font-size:13px;
       opacity:0;pointer-events:none;transition:.2s;z-index:60}
.toast.show{opacity:1;transform:translate(-50%,0)}
.check{display:flex;align-items:center;gap:6px;white-space:nowrap;color:var(--muted);
       font-size:12.5px;padding:0 4px;cursor:pointer}
.check input{width:14px;height:14px;accent-color:var(--accent);cursor:pointer}
button.tiny{padding:3px 7px;font-size:13px;color:var(--muted)}
button.danger{color:var(--danger)}
.navfoot{padding:8px 10px;border-top:1px solid var(--line)}
.navfoot button{width:100%}
.toolbar .name{cursor:text}
.only-narrow,.insp-close{display:none}

@media print{
  body{overflow:visible;background:#fff}
  .topbar,aside,.toolbar,.palette{display:none!important}
  .layout,.work{display:block;height:auto}
  .stage{overflow:visible;padding:0}
  .sheet{box-shadow:none;border-radius:0;padding:0;width:auto}
  svg .handle,svg .sel-outline,svg .guide,svg .marquee{display:none}
}

.scrim{position:fixed;inset:0;background:rgba(10,15,20,.32);z-index:35;display:none}
body.nav-open .scrim,body.more-open .scrim{display:block}
.insp .ihead{display:flex;align-items:center;justify-content:space-between;gap:8px}
.insp .ihead h3{margin:0}

@media (max-width:1360px){ button.wide{display:none} }
@media (max-width:1180px){
  aside.nav{flex-basis:210px} aside.insp{flex-basis:250px}
  .toolbar .meta{display:none}
}
@media (max-width:980px){
  .brand .sub{display:none}
  aside.insp{position:fixed;right:0;top:var(--top);bottom:0;width:270px;z-index:30;
    box-shadow:var(--shadow);display:none}
  body.insp-open aside.insp{display:block}
  .insp-close{display:inline-block}
}
@media (max-width:820px){
  .only-narrow{display:inline-block}
  .topbar{gap:6px}
  .topbar>.sep{display:none}
  .more{display:none;position:fixed;top:calc(var(--top) + 6px);
    right:max(8px,env(safe-area-inset-right));width:min(240px,calc(100vw - 16px));
    max-height:calc(100dvh - var(--top) - 16px);overflow:auto;
    flex-direction:column;align-items:stretch;gap:8px;padding:10px;z-index:50;
    background:var(--panel);border:1px solid var(--line);border-radius:12px;
    box-shadow:var(--shadow)}
  body.more-open .more{display:flex}
  .more .group{flex-direction:column;align-items:stretch}
  .more .sep{width:auto;height:1px;margin:2px 0}
  .more button.wide{display:block}
  .more select{padding:6px 8px;border:1px solid var(--line);border-radius:8px;
    background:var(--field)}
  .more .check{padding:4px 2px}
  aside.nav{position:fixed;left:0;top:var(--top);bottom:0;width:min(280px,86vw);z-index:40;
    transform:translateX(-102%);transition:transform .18s;box-shadow:var(--shadow)}
  body.nav-open aside.nav{transform:none}
  aside.insp{display:block;top:auto;left:0;right:0;width:auto;
    max-height:min(55dvh,440px);border-left:0;border-top:1px solid var(--line);
    border-radius:14px 14px 0 0;padding-bottom:max(14px,env(safe-area-inset-bottom));
    transform:translateY(105%);transition:transform .18s;visibility:hidden}
  body.insp-open aside.insp{transform:none;visibility:visible}
  .toolbar{padding:0 8px;gap:5px}
  .palette{flex-basis:46px}
  .palette button{width:36px;height:36px}
  .stage{padding:12px}
  .sheet{padding:10px}
  .toast{bottom:max(24px,env(safe-area-inset-bottom))}
}
@media (max-width:820px) and (orientation:landscape) and (max-height:520px){
  aside.insp{top:var(--top);left:auto;width:min(300px,50vw);max-height:none;
    border-top:0;border-left:1px solid var(--line);border-radius:0;
    transform:translateX(105%)}
}
@media (max-width:480px){
  .topbar{padding:0 8px;gap:4px}
  .topbar button{padding:6px 9px}
  .brand{font-size:13px}
  .zoomval,#zoom100,#btnRename{display:none}
  .palette{flex-basis:42px}
  .palette button{width:34px;height:34px}
  .stage{padding:8px}
}
@media (pointer:coarse){
  svg .edge-hit{stroke-width:22}
  .tree a{padding:9px 10px}
}
"""

JS_CORE = r"""
'use strict';
const FS=44/3, LH=18, PADX=14, PADY=8, MINW=128, MINH=34, RATIO=.6, LBL=12;
const MARGIN=12, TITLE_H=34, ARROW_LEN=9, ARROW_HALF=3.6, GRID=5, PAD=60;
const STUB=20, CORNER=0;
const MONO="Times New Roman, Liberation Serif, Times, serif";
const UI=MONO;
/* Цвет интерфейса не меняет печатные цвета схемы. */
const PAPER={stroke:"#000000",ink:"#000000",bg:"#ffffff",fill:{}};
const THEMES={light:PAPER,dark:PAPER};
let THEME='light';
const TH=()=>THEMES[THEME]||THEMES.light;
const KIND_RU={process:"Процесс",io:"ВводВывод",input:"Ввод",output:"Вывод",decision:"Решение",
               terminator:"Терминатор",predefined:"Подпрограмма",
               preparation:"Цикл",connector:"Соединитель"};
const KINDS=["terminator","process","input","output","io","decision","predefined","preparation","connector"];
const STORE='blockwright.cpp.v1';

/* ---------- i18n ---------- */
const I18N={
 ru:{
  app_title:"Блок-схемы: {0}", charts_count:"схем: {0}", my_charts:"Мои схемы",
  caption:"Рисунок {0} — Блок-схема алгоритма {1}", made_by_hand:"создано вручную",
  own:"своя", search:"Поиск схемы…", props:"Свойства",
  b_undo:"Отменить (Ctrl+Z)", b_redo:"Повторить (Ctrl+Shift+Z)",
  b_copy:"Копировать", b_copy_t:"Скопировать картинку в буфер обмена",
  b_png:"PNG", b_svg:"SVG", b_svg_t:"Вектор для Word и Figma", b_print:"Печать",
  b_project:"Проект…", b_project_t:"Выгрузить правки и свои схемы в файл",
  b_open:"Открыть", b_open_t:"Загрузить проект из файла",
  b_new_t:"Создать пустую схему", b_del:"Сбросить / удалить",
  b_del_t:"Сбросить правки схемы или удалить свою схему",
  b_rename_t:"Переименовать схему", b_theme_t:"Светлая / тёмная тема",
  b_lang_t:"Язык интерфейса", b_menu_t:"Список схем",
  b_more_t:"Экспорт и настройки", b_close:"Закрыть",
  z_out:"Уменьшить", z_in:"Увеличить", z_fit:"Вписать",
  cap_title:"заголовок", cap_title_t:"Добавлять заголовок в экспортируемый файл",
  kind_terminator:"Начало / конец", kind_process:"Процесс", kind_io:"Данные", kind_input:"Ввод", kind_output:"Вывод",
  kind_decision:"Решение", kind_predefined:"Предопределённый процесс",
  kind_preparation:"Подготовка (цикл)", kind_connector:"Соединитель",
  t_select:"Выбор и перемещение  (V)", t_connect:"Связь: щёлкните источник, затем приёмник  (C)",
  t_label:"Подпись  (T)",
  t_terminator:"Начало / конец  (1)", t_process:"Процесс  (2)", t_io:"Данные", t_input:"Ввод  (3)", t_output:"Вывод  (4)",
  t_decision:"Решение  (4)", t_predefined:"Предопределённый процесс  (5)",
  t_preparation:"Подготовка / цикл  (6)", t_connector:"Соединитель  (7)",
  i_type:"Тип блока", i_text:"Текст", i_apply:"Применить", i_fit:"По тексту",
  i_dup:"Дублировать", i_del:"Удалить", i_shift:"сдвигать блоки ниже",
  i_reroute:"Перепроложить связи",
  i_hint_block:"Тянуть — перемещение, квадратики — размер.<br><span class=\"kbd\">Alt</span> — без привязки к сетке, <span class=\"kbd\">Shift</span> — добавить к выделению.",
  i_from:"Из", i_to:"В", i_free:"свободный конец",
  i_arrow:"Стрелка на конце", i_arrow_on:"есть", i_arrow_off:"нет",
  i_straight:"Выпрямить", i_route:"Проложить заново",
  i_hint_edge:"Кружки — узлы линии, светлые — добавить узел. Потяните крайний узел на блок, чтобы привязать линию.",
  i_label_text:"Текст подписи", i_align:"Выравнивание",
  i_left:"слева", i_center:"по центру", i_right:"справа",
  i_selected:"Выделено объектов: <b>{0}</b>", i_align_v:"Выровнять по вертикали",
  i_align_c:"По центру", i_spread:"Разложить",
  i_empty:"Щёлкните по блоку, линии или подписи, чтобы изменить их. Блок добавляется кнопками слева, связь — инструментом <b>Связь</b>: щёлкните по блоку-источнику, затем по приёмнику.",
  m_new_name:"Название новой схемы:", m_new_default:"Схема {0}",
  m_rename:"Название схемы:",
  m_del_chart:"Удалить схему «{0}»?", m_reset_chart:"Вернуть схему «{0}» к исходному виду?",
  s_new:"Создана пустая схема — добавляйте блоки слева", s_deleted:"Схема удалена",
  s_reset:"Правки сброшены", s_no_edits:"Правок нет",
  s_svg:"SVG сохранён — открывается в Figma слоями", s_png:"PNG сохранён",
  s_copied:"PNG скопирован — вставьте в отчёт (Ctrl+V)",
  s_clip_fail:"Буфер недоступен — сохраните файлом", s_png_fail:"Не удалось сделать PNG",
  s_proj_saved:"Проект сохранён — его можно перенести на другой компьютер",
  s_proj_loaded:"Проект загружен", s_proj_bad:"Файл не похож на проект",
  s_storage:"Не удалось сохранить — хранилище браузера переполнено",
  s_rerouted:"Проложено заново: {0}", s_no_links:"Связей нет",
  s_unbound:"Линия не привязана к двум блокам", s_renamed:"Схема переименована"
 },
 en:{
  app_title:"Flowcharts: {0}", charts_count:"{0} charts", my_charts:"My charts",
  caption:"Figure {0} — Flowchart of {1}", made_by_hand:"drawn by hand",
  own:"own", search:"Search chart…", props:"Properties",
  b_undo:"Undo (Ctrl+Z)", b_redo:"Redo (Ctrl+Shift+Z)",
  b_copy:"Copy", b_copy_t:"Copy the image to the clipboard",
  b_png:"PNG", b_svg:"SVG", b_svg_t:"Vector for Word and Figma", b_print:"Print",
  b_project:"Project…", b_project_t:"Export edits and own charts to a file",
  b_open:"Open", b_open_t:"Load a project file",
  b_new_t:"Create an empty chart", b_del:"Reset / delete",
  b_del_t:"Reset chart edits or delete your own chart",
  b_rename_t:"Rename the chart", b_theme_t:"Light / dark theme",
  b_lang_t:"Interface language", b_menu_t:"Chart list",
  b_more_t:"Export and settings", b_close:"Close",
  z_out:"Zoom out", z_in:"Zoom in", z_fit:"Fit",
  cap_title:"title", cap_title_t:"Include the title in the exported file",
  kind_terminator:"Terminator", kind_process:"Process", kind_io:"Data", kind_input:"Input", kind_output:"Output",
  kind_decision:"Decision", kind_predefined:"Predefined process",
  kind_preparation:"Preparation (loop)", kind_connector:"Connector",
  t_select:"Select and move  (V)", t_connect:"Connector: click source, then target  (C)",
  t_label:"Label  (T)",
  t_terminator:"Terminator  (1)", t_process:"Process  (2)", t_io:"Data", t_input:"Input  (3)", t_output:"Output  (4)",
  t_decision:"Decision  (4)", t_predefined:"Predefined process  (5)",
  t_preparation:"Preparation / loop  (6)", t_connector:"Connector  (7)",
  i_type:"Block type", i_text:"Text", i_apply:"Apply", i_fit:"Fit to text",
  i_dup:"Duplicate", i_del:"Delete", i_shift:"push blocks below",
  i_reroute:"Reroute connectors",
  i_hint_block:"Drag to move, squares resize.<br><span class=\"kbd\">Alt</span> — ignore the grid, <span class=\"kbd\">Shift</span> — extend the selection.",
  i_from:"From", i_to:"To", i_free:"free end",
  i_arrow:"Arrowhead", i_arrow_on:"yes", i_arrow_off:"no",
  i_straight:"Straighten", i_route:"Reroute",
  i_hint_edge:"Circles are nodes, light ones add a node. Drag an end node onto a block to attach the connector.",
  i_label_text:"Label text", i_align:"Alignment",
  i_left:"left", i_center:"center", i_right:"right",
  i_selected:"Selected: <b>{0}</b>", i_align_v:"Align vertically",
  i_align_c:"Center", i_spread:"Distribute",
  i_empty:"Click a block, connector or label to edit it. Add blocks with the buttons on the left; for a connector pick the <b>Connector</b> tool, then click the source and the target.",
  m_new_name:"Name of the new chart:", m_new_default:"Chart {0}",
  m_rename:"Chart name:",
  m_del_chart:"Delete chart “{0}”?", m_reset_chart:"Reset chart “{0}” to its original state?",
  s_new:"Empty chart created — add blocks from the palette", s_deleted:"Chart deleted",
  s_reset:"Edits discarded", s_no_edits:"Nothing was edited",
  s_svg:"SVG saved — opens in Figma as layers", s_png:"PNG saved",
  s_copied:"PNG copied — paste it into your report (Ctrl+V)",
  s_clip_fail:"Clipboard unavailable — save the file instead", s_png_fail:"Could not render PNG",
  s_proj_saved:"Project saved — you can move it to another computer",
  s_proj_loaded:"Project loaded", s_proj_bad:"This file is not a project",
  s_storage:"Could not save — browser storage is full",
  s_rerouted:"Rerouted: {0}", s_no_links:"No connectors",
  s_unbound:"The connector is not attached to two blocks", s_renamed:"Chart renamed"
 }};
let LANG='ru';
function t(key){
  const dict=I18N[LANG]||I18N.ru;
  let s=dict[key]!==undefined?dict[key]:(I18N.ru[key]!==undefined?I18N.ru[key]:key);
  for(let i=1;i<arguments.length;i++)s=s.split('{'+(i-1)+'}').join(arguments[i]);
  return s;
}
const KIND_LABEL=k=>t('kind_'+k);

/* ---------- text and sizes ---------- */
function norm(s){return String(s==null?'':s).replace(/[\r\n\t]/g,' ')
  .replace(/\s+/g,' ').replace(/\s*,\s*/g,', ').trim();}
function hardSplit(tok,w){
  const parts=[];let cur='';
  for(const p of tok.split(/(?<=[,;.:_>])/)){if(!p)continue;
    if(cur&&cur.length+p.length>w){parts.push(cur);cur=p;}else cur+=p;}
  if(cur)parts.push(cur);
  const out=[];
  for(let p of parts){while(p.length>w){out.push(p.slice(0,w));p=p.slice(w);}if(p)out.push(p);}
  return out.length?out:[tok];
}
function wrap(text,w){
  text=norm(text); if(!text)return[''];
  if(text.length<=w)return[text];
  const lines=[];let cur='';
  for(const word of text.split(' ')){
    if(word.length>w){if(cur){lines.push(cur);cur='';}
      const ch=hardSplit(word,w);lines.push(...ch.slice(0,-1));cur=ch[ch.length-1];continue;}
    const cand=cur?cur+' '+word:word;
    if(cand.length<=w)cur=cand;else{lines.push(cur);cur=word;}}
  if(cur)lines.push(cur);
  return lines;
}
const r2=v=>Math.round(v*100)/100;
const n=v=>v.toFixed(2).replace(/\.?0+$/,'');
let textContext;
function textWidth(text,size){
  if(!textContext)textContext=document.createElement('canvas').getContext('2d');
  textContext.font=size+'px '+MONO;
  return textContext.measureText(text).width;
}
function sizeFor(kind,text,maxChars,notation){
  const lines=wrap(text,maxChars);
  const tw=Math.max(...lines.map(l=>textWidth(l,FS))), th=lines.length*LH;
  let w,h;
  if(kind==='connector'){const d=Math.max(40,tw+16,th+16);w=d;h=d;}
  else if(kind==='decision'){h=Math.max(54,th*2+16);w=Math.max(150,tw*1.75+28);}
  else if(kind==='preparation'){h=Math.max(MINH,th+2*PADY);w=Math.max(MINW,tw+2*PADX+h*.8);}
  else if(kind==='io'||kind==='input'||kind==='output'){h=Math.max(MINH,th+2*PADY);w=Math.max(MINW,tw+2*PADX+h*.5);}
  else if(kind==='predefined'){h=Math.max(MINH,th+2*PADY);w=Math.max(MINW,tw+2*PADX+28);}
  else if(kind==='terminator'){h=Math.max(34,th+2*PADY-2);w=Math.max(MINW,tw+2*PADX+h*.6);}
  else{h=Math.max(MINH,th+2*PADY);w=Math.max(MINW,tw+2*PADX);}
  return{w:r2(w),h:r2(h),lines};
}
function esc(s){return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;')
  .replace(/>/g,'&gt;').replace(/"/g,'&quot;');}
function slug(t,lim){lim=lim||28;
  const s=String(t||'').trim().replace(/[^0-9A-Za-zА-Яа-яЁё_-]+/g,'_')
    .replace(/_+/g,'_').replace(/^_|_$/g,'');
  return s.slice(0,lim)||'блок';}
let _uid=0; const uid=p=>p+'_'+(Date.now()%100000).toString(36)+(_uid++).toString(36);
const clone=o=>JSON.parse(JSON.stringify(o));

function flowPorts(s,outgoing){
  if(s.kind==='connector'&&s.flow==='up')return outgoing?['right']:['left'];
  if(s.kind==='terminator'){
    if(s.role==='start'&&!outgoing)return[];
    if(s.role==='end'&&outgoing)return[];
  }
  return outgoing?(s.kind==='decision'?['bottom','right']:['bottom']):['top'];
}
function contourPorts(s){
  const isData=s.kind==='io'||s.kind==='input'||(s.kind==='output'&&s.notation==='gost');
  const inset=isData?Math.min(s.h*.34,s.w*.3)/2:0;
  return {top:[s.x+s.w/2,s.y],
    bottom:[s.x+s.w/2,s.y+s.h*((s.kind==='output'&&(s.notation||'course')==='course')?.9425:1)],
    left:[s.x+inset,s.y+s.h/2],right:[s.x+s.w-inset,s.y+s.h/2]};
}

/* ---------- rendering ---------- */
function bbox(m){
  let x0=Infinity,y0=Infinity,x1=-Infinity,y1=-Infinity;
  const put=(x,y)=>{if(x<x0)x0=x;if(x>x1)x1=x;if(y<y0)y0=y;if(y>y1)y1=y;};
  for(const s of m.shapes){put(s.x,s.y);put(s.x+s.w,s.y+s.h);}
  for(const e of m.edges)for(const p of e.points)put(p[0],p[1]);
  for(const l of m.labels){const w=textWidth(l.text,LBL);
    if(l.anchor==='start'){put(l.x,l.y);put(l.x+w,l.y);}
    else if(l.anchor==='end'){put(l.x-w,l.y);put(l.x,l.y);}
    else{put(l.x-w/2,l.y);put(l.x+w/2,l.y);}
    put(l.x,l.y-LBL);}
  if(!isFinite(x0))return{x0:0,y0:0,x1:200,y1:120};
  return{x0,y0,x1,y1};
}
function outline(s){
  const x=s.x,y=s.y,w=s.w,h=s.h,k=s.kind;
  const st=`fill="${TH().fill[k]||TH().bg}" stroke="${TH().stroke}" stroke-width="1.6"`;
  if(k==='terminator')return[`<rect x="${n(x)}" y="${n(y)}" width="${n(w)}" height="${n(h)}" rx="${n(h/2)}" ry="${n(h/2)}" ${st}/>`];
  if(k==='decision')return[`<polygon points="${n(x+w/2)},${n(y)} ${n(x+w)},${n(y+h/2)} ${n(x+w/2)},${n(y+h)} ${n(x)},${n(y+h/2)}" ${st}/>`];
  if(k==='output'&&(s.notation||'course')==='course')return[`<path d="M${n(x)},${n(y)} L${n(x+w)},${n(y)} L${n(x+w)},${n(y+.8*h)} C${n(x+2*w/3)},${n(y+.78*h)} ${n(x+w/3)},${n(y+1.16*h)} ${n(x)},${n(y+.92*h)} Z" ${st}/>`];
  if(k==='io'||k==='input'||k==='output'){const s2=Math.min(h*.34,w*.3);
    return[`<polygon points="${n(x+s2)},${n(y)} ${n(x+w)},${n(y)} ${n(x+w-s2)},${n(y+h)} ${n(x)},${n(y+h)}" ${st}/>`];}
  if(k==='preparation'){const c=Math.min(h*.5,w*.25);
    return[`<polygon points="${n(x+c)},${n(y)} ${n(x+w-c)},${n(y)} ${n(x+w)},${n(y+h/2)} ${n(x+w-c)},${n(y+h)} ${n(x+c)},${n(y+h)} ${n(x)},${n(y+h/2)}" ${st}/>`];}
  if(k==='predefined'){const o=[`<rect x="${n(x)}" y="${n(y)}" width="${n(w)}" height="${n(h)}" ${st}/>`];
    for(const dx of[11,w-11])o.push(`<line x1="${n(x+dx)}" y1="${n(y)}" x2="${n(x+dx)}" y2="${n(y+h)}" stroke="${TH().stroke}" stroke-width="1.4"/>`);
    return o;}
  if(k==='connector')return[`<circle cx="${n(x+w/2)}" cy="${n(y+h/2)}" r="${n(Math.min(w,h)/2)}" ${st}/>`];
  return[`<rect x="${n(x)}" y="${n(y)}" width="${n(w)}" height="${n(h)}" ${st}/>`];
}
function shapeText(s,maxChars){
  const lines=s.lines||wrap(s.text,maxChars);
  const cx=s.x+s.w/2, cy=s.y+s.h*((s.kind==='output'&&(s.notation||'course')==='course')?.43:.5), y0=cy-(lines.length-1)*LH/2+FS*.36;
  return lines.map((ln,i)=>`<text x="${n(cx)}" y="${n(y0+i*LH)}" text-anchor="middle" font-family="${MONO}" font-size="${FS}" fill="${TH().ink}">${esc(ln)}</text>`);
}
function cleanPts(pts){
  const cl=[pts[0]];
  for(const p of pts.slice(1)){const q=cl[cl.length-1];
    if(Math.abs(p[0]-q[0])>.01||Math.abs(p[1]-q[1])>.01)cl.push(p);}
  return cl;
}
function roundPath(pts,r){
  if(pts.length<3)
    return 'M'+pts.map(p=>n(p[0])+','+n(p[1])).join(' L');
  let d='M'+n(pts[0][0])+','+n(pts[0][1]);
  for(let i=1;i<pts.length-1;i++){
    const a=pts[i-1],c=pts[i],b=pts[i+1];
    const l1=Math.hypot(c[0]-a[0],c[1]-a[1]),l2=Math.hypot(b[0]-c[0],b[1]-c[1]);
    const cross=Math.abs((c[0]-a[0])*(b[1]-c[1])-(c[1]-a[1])*(b[0]-c[0]));
    const rr=Math.min(r,l1/2,l2/2);
    if(rr<1||cross<1||!l1||!l2){d+=' L'+n(c[0])+','+n(c[1]);continue;}
    d+=' L'+n(c[0]+(a[0]-c[0])/l1*rr)+','+n(c[1]+(a[1]-c[1])/l1*rr)+
       ' Q'+n(c[0])+','+n(c[1])+' '+
       n(c[0]+(b[0]-c[0])/l2*rr)+','+n(c[1]+(b[1]-c[1])/l2*rr);
  }
  const last=pts[pts.length-1];
  return d+' L'+n(last[0])+','+n(last[1]);
}
function edgeSvg(e){
  if(e.points.length<2)return[];
  let pts=cleanPts(e.points); if(pts.length<2)return[];
  const out=[];
  for(let i=1;i<pts.length;i++){
    const [ax,ay]=pts[i-1],[bx,by]=pts[i];
    if(ay-by>35&&Math.abs(ax-bx)<.01){const my=(ay+by)/2;
      out.push(`<path d="M${n(ax)},${n(my)} L${n(ax-ARROW_HALF)},${n(my+ARROW_LEN)} L${n(ax+ARROW_HALF)},${n(my+ARROW_LEN)} Z" fill="${TH().stroke}"/>`);}
    if(ax-bx>35&&Math.abs(ay-by)<.01){const mx=(ax+bx)/2;
      out.push(`<path d="M${n(mx)},${n(ay)} L${n(mx+ARROW_LEN)},${n(ay-ARROW_HALF)} L${n(mx+ARROW_LEN)},${n(ay+ARROW_HALF)} Z" fill="${TH().stroke}"/>`);}
  }
  if(e.arrow!==false){
    const a=pts[pts.length-2],b=pts[pts.length-1];
    const dx=b[0]-a[0],dy=b[1]-a[1],L=Math.hypot(dx,dy)||1;
    const ux=dx/L,uy=dy/L,bx=b[0]-ux*ARROW_LEN,by=b[1]-uy*ARROW_LEN;
    const px=-uy*ARROW_HALF,py=ux*ARROW_HALF;
    if(L>ARROW_LEN)pts=pts.slice(0,-1).concat([[bx,by]]);
    out.push(`<path d="M${n(b[0])},${n(b[1])} L${n(bx+px)},${n(by+py)} L${n(bx-px)},${n(by-py)} Z" fill="${TH().stroke}"/>`);
  }
  out.unshift(`<path d="${roundPath(pts,CORNER)}" fill="none" stroke="${TH().stroke}" stroke-width="1.5" stroke-linecap="round"/>`);
  return out;
}
function labelSvg(l){
  return `<text x="${n(l.x)}" y="${n(l.y)}" text-anchor="${l.anchor}" font-family="${UI}" font-size="${LBL}" fill="${TH().ink}">${esc(l.text)}</text>`;
}
/* view=null fits the margins to the content (export); otherwise the canvas area is fixed */
function renderSVG(m,opt){
  opt=opt||{};
  const b=opt.view||bbox(m), title=opt.title||null;
  const top=MARGIN+(title?TITLE_H:0);
  const W=(b.x1-b.x0)+2*MARGIN, H=(b.y1-b.y0)+MARGIN+top;
  const dx=MARGIN-b.x0, dy=top-b.y0;
  const parts=[`<rect id="Фон" x="0" y="0" width="${n(W)}" height="${n(H)}" fill="${TH().bg}"/>`];
  if(title)parts.push(`<text id="Заголовок" x="${n(W/2)}" y="${n(MARGIN+6)}" text-anchor="middle" font-family="${UI}" font-size="15" font-weight="600" fill="${TH().ink}">${esc(title)}</text>`);
  const lines=[],hits=[];
  for(const e of m.edges){
    lines.push(...edgeSvg(e));
    if(opt.interactive&&e.points.length>1)
      hits.push(`<polyline class="edge-hit" data-edge="${esc(e.id)}" points="${e.points.map(p=>n(p[0])+','+n(p[1])).join(' ')}"/>`);
  }
  const labels=m.labels.map(l=>opt.interactive
    ?`<g data-label="${esc(l.id)}" style="cursor:move">${labelSvg(l)}</g>`:labelSvg(l));
  const shapes=m.shapes.map((s,i)=>{
    const gid=`${String(i+1).padStart(2,'0')}_${KIND_RU[s.kind]||'Блок'}_${slug(s.text)}`;
    const inner=outline(s).concat(shapeText(s,m.maxChars)).join('\n  ');
    const extra=opt.interactive?` class="shp" data-shape="${esc(s.id)}"`:'';
    return `<g id="${esc(gid)}"${extra}>\n  ${inner}\n</g>`;});
  parts.push(`<g id="${esc(slug(opt.name||'Блок-схема',48))}" transform="translate(${n(dx)},${n(dy)})">`);
  parts.push('<g id="Связи">\n'+lines.join('\n')+'\n</g>');
  if(labels.length)parts.push('<g id="Подписи">\n'+labels.join('\n')+'\n</g>');
  parts.push('<g id="Блоки">\n'+shapes.join('\n')+'\n</g>');
  if(opt.interactive){parts.push('<g id="__hit">\n'+hits.join('\n')+'\n</g>');
                      parts.push('<g id="__ui"></g>');}
  parts.push('</g>');
  const head=`<svg xmlns="http://www.w3.org/2000/svg" width="${n(W)}" height="${n(H)}" viewBox="0 0 ${n(W)} ${n(H)}" role="img">`;
  return{svg:head+'\n'+parts.join('\n')+'\n</svg>',w:W,h:H,dx,dy};
}

/* ---------- model: attachments and routes ---------- */
function anchors(s){return contourPorts(s);}
function anchorPt(m,ref){
  const s=m.shapes.find(x=>x.id===ref.id); if(!s)return null;
  return anchors(s)[ref.port]||null;
}
function hydrate(m){
  m.maxChars=m.maxChars||38;
  m.shapes=m.shapes||[];m.edges=m.edges||[];m.labels=m.labels||[];
  m.notation=m.notation||'course';
  for(const s of m.shapes){if(!s.id)s.id=uid('s');s.notation=s.notation||m.notation;}
  for(const l of m.labels){
    if(!l.id)l.id=uid('l');
    if(l.near===undefined)l.near=nearestAnchor(m,l);
  }
  for(const e of m.edges){
    if(!e.id)e.id=uid('e');
    if(e.arrow===undefined)e.arrow=true;
    if(e.from===undefined)e.from=findAnchor(m,e.points[0],3,true);
    if(e.to===undefined)e.to=e.arrow?findAnchor(m,e.points[e.points.length-1],3,false):null;
  }
  return m;
}
/* a label right next to a block's anchor is attached to it */
function nearestAnchor(m,l){
  let best=null,bd=34;
  for(const s of m.shapes){
    const a=anchors(s);
    for(const port of['left','right','top','bottom']){
      const d=Math.hypot(a[port][0]-l.x,a[port][1]-l.y);
      if(d<bd){bd=d;best={id:s.id,port,ox:r2(l.x-a[port][0]),oy:r2(l.y-a[port][1])};}
    }
  }
  return best;
}
function findAnchor(m,pt,tol,outgoing){
  tol=tol||3; let best=null,bd=tol;
  for(const s of m.shapes){
    const a=anchors(s);
    for(const port of flowPorts(s,!!outgoing)){
      const d=Math.hypot(a[port][0]-pt[0],a[port][1]-pt[1]);
      if(d<=bd){bd=d;best={id:s.id,port};}
    }
  }
  return best;
}
/* drop vertices that lie on the line between their neighbours */
function simplify(e){
  const p=e.points;
  for(let i=p.length-2;i>0;i--){
    if((i===1&&e.from)||(i===p.length-2&&e.to))continue;
    const a=p[i-1],b=p[i],c=p[i+1];
    if((Math.abs(a[0]-b[0])<.6&&Math.abs(b[0]-c[0])<.6)||
       (Math.abs(a[1]-b[1])<.6&&Math.abs(b[1]-c[1])<.6))p.splice(i,1);
  }
}
const NORMAL={top:[0,-1],bottom:[0,1],left:[-1,0],right:[1,0]};
/* An edge must meet a block square to its side with a straight stub, or the
   arrowhead tilts and the line doubles back through the shape. A broken
   approach is rebuilt: out along the normal, one turn, then the nearest
   vertex that is still valid. */
function fixEnd(e,isFrom){
  const ref=isFrom?e.from:e.to; if(!ref)return;
  const nrm=NORMAL[ref.port]; if(!nrm||e.points.length<2)return;
  const last=e.points.length-1;
  const idx=isFrom?0:last, j=isFrom?1:last-1;
  const p=e.points[idx], q=e.points[j];
  const along=(q[0]-p[0])*nrm[0]+(q[1]-p[1])*nrm[1];
  const side=(q[0]-p[0])*nrm[1]-(q[1]-p[1])*nrm[0];
  if(Math.abs(side)<.6&&along>=STUB-.6)return;
  let k=j;
  if(along<0&&e.points.length>2)k=isFrom?2:last-2;  // the neighbour ended up behind the stub
  const target=e.points[k];
  const s=[r2(p[0]+nrm[0]*STUB),r2(p[1]+nrm[1]*STUB)];
  const vert=(nrm[0]===0);
  const mid=vert?[r2(target[0]),s[1]]:[s[0],r2(target[1])];
  const ins=[s];
  if(Math.hypot(mid[0]-s[0],mid[1]-s[1])>.6&&
     Math.hypot(mid[0]-target[0],mid[1]-target[1])>.6)ins.push(mid);
  if(isFrom)e.points.splice(1,k-1,...ins);
  else e.points.splice(k+1,last-k-1,...ins.reverse());
}
/* Fallback without libavoid: the end moves to its new point, the next vertex
   follows when it was in line with it (unless it is another edge's attached
   end), and the approach is straightened. */
function followEnd(e,idx,np){
  const old=e.points[idx].slice();
  const dx=np[0]-old[0], dy=np[1]-old[1];
  if(!dx&&!dy)return;
  e.points[idx]=[r2(np[0]),r2(np[1])];
  const j=idx===0?1:idx-1;
  if(j<0||j>e.points.length-1)return;
  if((j===0&&e.from)||(j===e.points.length-1&&e.to))return;
  const q=e.points[j];
  if(Math.abs(q[0]-old[0])<1.2)q[0]=r2(q[0]+dx);
  if(Math.abs(q[1]-old[1])<1.2)q[1]=r2(q[1]+dy);
}
function followShapes(m,e){
  for(const idx of [0,e.points.length-1]){
    const ref=idx===0?e.from:e.to; if(!ref)continue;
    const np=anchorPt(m,ref); if(np)followEnd(e,idx,np);
  }
  fixEnd(e,true);fixEnd(e,false);simplify(e);
}

/* ---------- edge geometry ---------- */
function nearestOn(pts,p){
  let best=null;
  for(let i=0;i+1<pts.length;i++){
    const a=pts[i],b=pts[i+1],dx=b[0]-a[0],dy=b[1]-a[1],L=dx*dx+dy*dy;
    const t=L?Math.max(0,Math.min(1,((p[0]-a[0])*dx+(p[1]-a[1])*dy)/L)):0;
    const q=[a[0]+t*dx,a[1]+t*dy], d=Math.hypot(p[0]-q[0],p[1]-q[1]);
    if(!best||d<best.d)best={d,p:[r2(q[0]),r2(q[1])]};
  }
  return best;
}
const onLine=(pts,p)=>{const r=nearestOn(pts,p);return !!r&&r.d<.8;};
function freeEnds(e){
  const last=e.points.length-1, out=[];
  if(!e.from)out.push(0);
  if(!e.to&&last>0)out.push(last);
  return out;
}
/* does the polyline cross the block (Liang-Barsky clipping) */
function crosses(pts,s){
  const x0=s.x+1,y0=s.y+1,x1=s.x+s.w-1,y1=s.y+s.h-1;
  for(let i=0;i+1<pts.length;i++){
    const a=pts[i],b=pts[i+1],dx=b[0]-a[0],dy=b[1]-a[1];
    let t0=0,t1=1,ok=true;
    for(const[p,q]of[[-dx,a[0]-x0],[dx,x1-a[0]],[-dy,a[1]-y0],[dy,y1-a[1]]]){
      if(Math.abs(p)<1e-9){if(q<0){ok=false;break;}continue;}
      const r=q/p;
      if(p<0){if(r>t1){ok=false;break;}if(r>t0)t0=r;}
      else{if(r<t0){ok=false;break;}if(r<t1)t1=r;}
    }
    if(ok&&t0<=t1)return true;
  }
  return false;
}
/* The layout draws one logical connection as several pieces (a branch bus,
   a joint on another edge); pieces joined by free ends form one group. */
function edgeGroups(m){
  const E=m.edges, par=E.map((_,i)=>i);
  const f=i=>par[i]===i?i:(par[i]=f(par[i]));
  E.forEach((b,i)=>{for(const idx of freeEnds(b)){const p=b.points[idx];
    E.forEach((a,j)=>{if(i!==j&&onLine(a.points,p))par[f(i)]=f(j);});}});
  const g=new Map();
  E.forEach((e,i)=>{const k=f(i);if(!g.has(k))g.set(k,[]);g.get(k).push(e);});
  return [...g.values()];
}
/* free ends of other edges that sit on the edges being rerouted */
function junctions(m,list){
  const out=[];
  for(const b of m.edges)for(const idx of freeEnds(b)){
    const host=list.find(a=>a!==b&&onLine(a.points,b.points[idx]));
    if(host)out.push({edge:b,idx,host});
  }
  return out;
}
function portAt(s,p){
  const A=anchors(s);let best='bottom',bd=Infinity;
  for(const port of PORTS){const d=Math.hypot(A[port][0]-p[0],A[port][1]-p[1]);
    if(d<bd){bd=d;best=port;}}
  return best;
}

/* ---------- routing: libavoid ----------
   Orthogonal routes around blocks, square to the block sides, with parallel
   segments nudged apart. If the WebAssembly module fails to load, the simple
   fallback (followShapes / autoRoute) is used. */
let AV=null;
const PORTS=['top','bottom','left','right'];
const PIN={top:[.5,0,1],bottom:[.5,1,2],left:[0,.5,4],right:[1,.5,8]};  // x, y, ConnDir
const CLS={top:10,bottom:11,left:12,right:13,out:20,in:21};   // class 1 is reserved by libavoid
const AV_BUF=12, AV_SIDE=40;     // clearance around blocks; penalty for leaving by a side
function loadRouter(){
  if(AV||typeof AvoidModule!=='function'||typeof AVOID_WASM!=='string'||
     typeof WebAssembly!=='object')return Promise.resolve(AV);
  let bin;
  try{bin=Uint8Array.from(atob(AVOID_WASM),c=>c.charCodeAt(0));}
  catch(e){return Promise.resolve(null);}
  return AvoidModule({print(){},printErr(){},onAbort(){AV=null;},
    instantiateWasm(imports,done){
      WebAssembly.instantiate(bin,imports).then(r=>done(r.instance,r.module),()=>{});
      return {};}})
    .then(A=>{AV=A;return A;},()=>null);
}
const straightOnly=pts=>pts.length>1&&pts.every((p,i)=>!i||
  Math.abs(p[0]-pts[i-1][0])<.6||Math.abs(p[1]-pts[i-1][1])<.6);
/* a spike: the line reaches a point and comes back along itself */
function spiky(pts){
  for(let i=1;i+1<pts.length;i++){
    const a=pts[i-1],b=pts[i],c=pts[i+1];
    const ux=b[0]-a[0],uy=b[1]-a[1],vx=c[0]-b[0],vy=c[1]-b[1];
    if(Math.abs(ux*vy-uy*vx)<.5&&ux*vx+uy*vy<0)return true;
  }
  return false;
}
/* Checkpoints are the bends of the previous route, so an edge that a block
   merely brushes detours locally instead of taking a new path across the
   chart. Bends at or behind a moved end are dropped, or the edge would fold
   back. moved: indices of free ends that moved. */
function checkpoints(m,e,moved){
  const P=e.points, last=P.length-1;
  if(last<2)return [];
  let lo=1, hi=last-1;
  const guard=[null,null];
  [[0,e.from],[last,e.to]].forEach(([idx,ref],k)=>{
    const s=ref&&m.shapes.find(x=>x.id===ref.id);
    let shifted=!!(moved&&moved.has(idx));
    if(s){const a=anchors(s)[ref.port];
      shifted=Math.hypot(a[0]-P[idx][0],a[1]-P[idx][1])>.6;
      if(shifted)guard[k]=[a,NORMAL[ref.port]];}
    if(shifted){if(idx===0)lo=2;else hi=last-2;}
  });
  const B=AV_BUF-1, out=[];
  for(let i=lo;i<=hi;i++){
    const p=P[i];
    if(!m.shapes.some(s=>p[0]>s.x-B&&p[0]<s.x+s.w+B&&p[1]>s.y-B&&p[1]<s.y+s.h+B))out.push(p);
  }
  /* points next to a moved block must not end up behind its side */
  const behind=(p,g)=>g&&(p[0]-g[0][0])*g[1][0]+(p[1]-g[0][1])*g[1][1]<AV_BUF;
  while(out.length&&behind(out[0],guard[0]))out.shift();
  while(out.length&&behind(out[out.length-1],guard[1]))out.pop();
  return out;
}
/* reqs: [{from,to,a,b}]; from/to is {id,cls}, or null for a free end at a/b.
   Returns the routes, null where libavoid found none. */
function avRoute(m,reqs,buf){
  const A=AV, P=A.RoutingParameter, tmp=[], T=o=>(tmp.push(o),o);
  const multi=reqs.some(q=>[q.from,q.to].some(r=>r&&(r.cls===CLS.out||r.cls===CLS.in)));
  const R=new A.Router(A.RouterFlag.OrthogonalRouting.value);
  try{
    R.setRoutingParameter(P.shapeBufferDistance,buf||AV_BUF);
    R.setRoutingParameter(P.idealNudgingDistance,10);
    R.setRoutingParameter(P.segmentPenalty,50);
    /* flowchart edges share the middle of a side (loop entry and back edge),
       so their ends must not be spread apart */
    R.setRoutingOption(A.RoutingOption.nudgeOrthogonalSegmentsConnectedToShapes,false);
    const refs={};
    for(const s of m.shapes){
      const ref=new A.ShapeRef(R,T(new A.Rectangle(T(new A.Point(s.x,s.y)),
                                                   T(new A.Point(s.x+s.w,s.y+s.h)))));
      for(const port of PORTS){
        const point=anchors(s)[port], dir=PIN[port][2];
        const px=(point[0]-s.x)/s.w, py=(point[1]-s.y)/s.h;
        const pin=(cls,cost)=>{const p=new A.ShapeConnectionPin(ref,cls,px,py,true,0,dir);
          p.setExclusive(false); if(cost)p.setConnectionCost(cost);};
        pin(CLS[port],0);
        if(!multi)continue;
        if(flowPorts(s,true).includes(port))pin(CLS.out,port==='bottom'?0:AV_SIDE);
        if(flowPorts(s,false).includes(port))pin(CLS.in,port==='top'?0:AV_SIDE);
      }
      refs[s.id]=ref;
    }
    const end=(r,p)=>r&&refs[r.id]?T(new A.ConnEnd(refs[r.id],r.cls))
                                  :T(new A.ConnEnd(T(new A.Point(p[0],p[1]))));
    const conns=reqs.map(q=>{const c=new A.ConnRef(R,end(q.from,q.a),end(q.to,q.b));
      c.setRoutingType(A.ConnType.ConnType_Orthogonal);
      if(q.cps&&q.cps.length){
        const v=T(new A.CheckpointVector());
        for(const p of q.cps)v.push_back(T(new A.Checkpoint(T(new A.Point(p[0],p[1])))));
        c.setRoutingCheckpoints(v);
      }
      return c;});
    R.processTransaction();
    /* a route must end exactly on the block anchor or on its own point */
    const S=id=>m.shapes.find(s=>s.id===id);
    const near=(p,q)=>Math.hypot(p[0]-q[0],p[1]-q[1])<.6;
    const lands=(r,q,p)=>r&&refs[r.id]?Object.values(anchors(S(r.id))).some(a=>near(a,p))
                                      :near(q,p);
    return conns.map((c,i)=>{
      const r=T(c.displayRoute()),pts=[];
      for(let k=0;k<r.size();k++){const p=T(r.at(k));pts.push([r2(p.x),r2(p.y)]);}
      const cl=cleanPts(pts), q=reqs[i];
      return c.hasValidRoute()&&straightOnly(cl)&&!spiky(cl)&&lands(q.from,q.a,cl[0])&&
             lands(q.to,q.b,cl[cl.length-1])?cl:null;});
  }finally{
    for(const o of tmp)try{o.delete();}catch(e){}
    R.delete();
  }
}
function avRun(m,reqs,buf){
  if(!AV||!reqs.length)return null;
  try{return avRoute(m,reqs,buf);}catch(e){AV=null;return null;}   // broken: use the fallback from now on
}
/* Edge ends for the router.
   mode 'keep': same block sides; 'free': libavoid picks (out of the bottom or
   a side, in at the top or a side; decision sides mean Yes/No and stay);
   'guess': sides from a simple heuristic. */
function endsOf(m,e,mode){
  const P=e.points, S=id=>m.shapes.find(s=>s.id===id);
  let fp=e.from&&e.from.port, tp=e.to&&e.to.port;
  if(e.from&&S(e.from.id)&&!flowPorts(S(e.from.id),true).includes(fp))fp=flowPorts(S(e.from.id),true)[0]||'bottom';
  if(e.to&&S(e.to.id)&&!flowPorts(S(e.to.id),false).includes(tp))tp=flowPorts(S(e.to.id),false)[0]||'top';
  if(mode==='guess'&&e.from&&e.to&&S(e.from.id)&&S(e.to.id)){
    const r=autoRoute(m,S(e.from.id),S(e.to.id));
    if(S(e.from.id).kind!=='decision')fp=r.from;
    tp=r.to;
  }
  const ref=(r,port,dflt)=>{
    if(!r||!S(r.id))return null;
    if(mode==='free')return{id:r.id,cls:dflt&&S(r.id).kind!=='decision'?dflt:CLS[port]};
    return{id:r.id,cls:CLS[port]};
  };
  return{from:ref(e.from,fp,CLS.out),to:ref(e.to,tp,CLS.in),a:P[0],b:P[P.length-1]};
}
/* Clearance around blocks, reduced to half the gap when two blocks are closer
   than two clearances, so an edge can still pass between them. */
function bufferFor(m,list){
  const ids=new Set(list.flatMap(e=>[e.from,e.to]).filter(Boolean).map(r=>r.id));
  let gap=Infinity;
  for(const a of m.shapes){
    if(!ids.has(a.id))continue;
    for(const b of m.shapes){
      if(b===a)continue;
      const dx=Math.max(b.x-a.x-a.w,a.x-b.x-b.w), dy=Math.max(b.y-a.y-a.h,a.y-b.y-b.h);
      const d=Math.max(dx,dy);
      if(d>=0)gap=Math.min(gap,d);
    }
  }
  return Math.max(3,Math.min(AV_BUF,Math.floor(gap/2)-1));
}
/* Reroute edges.
   opt.free  - sides may change (the Reroute button, a new connector);
   opt.fresh - a new edge that nothing is joined to yet;
   opt.moved - Map(edge -> indices of free ends that moved). */
function routeEdges(m,list,opt){
  opt=opt||{};
  const free=!!opt.free, depth=opt.depth||0, moved=opt.moved;
  list=list.filter(e=>e.points.length>1);
  if(!list.length)return;
  const glue=opt.fresh?[]:junctions(m,list);
  const buf=bufferFor(m,list);
  const reqs=list.map(e=>endsOf(m,e,free?'free':'keep'));
  if(!free)reqs.forEach((q,i)=>{q.cps=checkpoints(m,list[i],moved&&moved.get(list[i]));});
  const res=avRun(m,reqs,buf)||[];
  /* retry failures without checkpoints (with heuristic sides when free, which
     libavoid sometimes trips over), then with a small clearance for blocks
     that almost touch */
  const retry=pad=>{
    const bad=list.map((e,i)=>res[i]?-1:i).filter(i=>i>=0);
    if(!AV||!bad.length)return;
    const again=avRun(m,bad.map(i=>free?endsOf(m,list[i],'guess')
                                       :Object.assign({},reqs[i],{cps:[]})),pad)||[];
    bad.forEach((i,k)=>{res[i]=again[k]||null;});
  };
  retry(buf); retry(Math.min(4,buf));
  list.forEach((e,i)=>{
    const pts=res[i];
    if(pts){
      e.points=pts;
      const S=id=>m.shapes.find(s=>s.id===id);
      if(e.from&&S(e.from.id))e.from.port=portAt(S(e.from.id),pts[0]);
      if(e.to&&S(e.to.id))e.to.port=portAt(S(e.to.id),pts[pts.length-1]);
    }else if(free&&e.from&&e.to)legacyReroute(m,e);
    else followShapes(m,e);
  });
  /* joined edges follow the new route so the joint stays attached, unless it
     also lies on another edge and holds on to that one */
  const again=new Map();
  for(const g of glue){
    const p=g.edge.points[g.idx];
    if(m.edges.some(a=>a!==g.edge&&onLine(a.points,p)))continue;
    const q=nearestOn(g.host.points,p); if(!q)continue;
    if(AV)g.edge.points[g.idx]=q.p; else followEnd(g.edge,g.idx,q.p);
    if(!again.has(g.edge))again.set(g.edge,new Set());
    again.get(g.edge).add(g.idx);
  }
  if(again.size&&depth<3){
    if(AV)routeEdges(m,[...again.keys()],{depth:depth+1,moved:again});
    else again.forEach((_,e)=>simplify(e));
  }
}
function legacyReroute(m,e){
  const a=m.shapes.find(s=>s.id===e.from.id), b=m.shapes.find(s=>s.id===e.to.id);
  if(!a||!b)return false;
  const r=autoRoute(m,a,b);
  e.points=r.pts.map(p=>[r2(p[0]),r2(p[1])]);
  e.from={id:a.id,port:r.from}; e.to={id:b.id,port:r.to};
  return true;
}
/* Edges follow blocks that moved or were resized.
   opt.delta - common offset: a construct whose blocks all move together is
   translated rather than rerouted. opt.skip - edges already moved by hand. */
function syncEdges(m,shapeIds,opt){
  opt=opt||{};
  const ids=new Set(shapeIds), skip=new Set(opt.skip||[]);
  /* Yes/No labels are attached to block anchors and move with the block */
  for(const l of m.labels){
    if(!l.near||!ids.has(l.near.id))continue;
    const s=m.shapes.find(x=>x.id===l.near.id); if(!s)continue;
    const a=anchors(s)[l.near.port]; if(!a)continue;
    l.x=r2(a[0]+l.near.ox); l.y=r2(a[1]+l.near.oy);
  }
  if(!ids.size)return;
  const d=opt.delta;
  if(d&&(d[0]||d[1]))for(const g of edgeGroups(m)){
    const refs=g.flatMap(e=>[e.from,e.to]).filter(Boolean);
    if(!refs.length||!refs.every(r=>ids.has(r.id)))continue;
    for(const e of g){
      if(!skip.has(e.id))e.points=e.points.map(p=>[r2(p[0]+d[0]),r2(p[1]+d[1])]);
      skip.add(e.id);
    }
  }
  const moved=m.shapes.filter(s=>ids.has(s.id));
  const list=m.edges.filter(e=>!skip.has(e.id)&&(
    (e.from&&ids.has(e.from.id))||(e.to&&ids.has(e.to.id))||
    moved.some(s=>crosses(e.points,s))));
  routeEdges(m,list);
}
function rerouteEdge(m,e,fresh){
  if(!e.from||!e.to)return false;
  if(!m.shapes.some(s=>s.id===e.from.id)||!m.shapes.some(s=>s.id===e.to.id))return false;
  routeEdges(m,[e],{free:true,fresh});
  return true;
}
function autoRoute(m,a,b){
  const A=anchors(a),B=anchors(b);
  if(a.flow==='up'||b.flow==='up'){
    const from=flowPorts(a,true)[0]||'bottom',to=flowPorts(b,false)[0]||'top';
    const p=A[from],q=B[to],N=NORMAL;
    const u=[p[0]+N[from][0]*STUB,p[1]+N[from][1]*STUB];
    const v=[q[0]+N[to][0]*STUB,q[1]+N[to][1]*STUB];
    return {pts:[p,u,[u[0],v[1]],v,q],from,to};
  }
  if(b.y>a.y+a.h-2){
    const mid=r2((a.y+a.h+b.y)/2);
    if(Math.abs(A.bottom[0]-B.top[0])<2)return{pts:[A.bottom,B.top],from:'bottom',to:'top'};
    return{pts:[A.bottom,[A.bottom[0],mid],[B.top[0],mid],B.top],from:'bottom',to:'top'};
  }
  if(b.y+b.h<a.y+2){
    const side=r2(Math.min(a.x,b.x)-34), y1=r2(a.y+a.h+20), y2=r2(b.y-20);
    return{pts:[A.bottom,[A.bottom[0],y1],[side,y1],[side,y2],[B.top[0],y2],B.top],
           from:'bottom',to:'top'};
  }
  const from=a.kind==='decision'?'right':'bottom';
  const p1=A[from], p2=B.top, lane=r2(Math.max(a.x+a.w,b.x+b.w)+34);
  const first=from==='right'?[lane,p1[1]]:[p1[0],a.y+a.h+STUB];
  return{pts:[p1,first,[lane,first[1]],[lane,b.y-STUB],[p2[0],b.y-STUB],p2],from,to:'top'};
}
/* cut the chart horizontally and push the lower part down after a block grew */
function shiftBelow(m,threshold,delta){
  if(!delta)return;
  for(const s of m.shapes)if(s.y>=threshold-.5)s.y=r2(s.y+delta);
  for(const e of m.edges)e.points=e.points.map(p=>
    [p[0],p[1]>=threshold-.5?r2(p[1]+delta):p[1]]);
  for(const l of m.labels)if(l.y>=threshold-.5)l.y=r2(l.y+delta);
}
function newShape(kind,x,y,text,maxChars){
  const g=sizeFor(kind,text,maxChars||38);
  return{id:uid('s'),kind,text,notation:'course',lines:g.lines,x:r2(x-g.w/2),y:r2(y-g.h/2),w:g.w,h:g.h};
}
function emptyDoc(name){
  const m={name,rel:'мои схемы',signature:'',line:0,maxChars:38,
           shapes:[],edges:[],labels:[]};
  const a=newShape('terminator',300,80,'Начало',38);a.role='start';
  const b=newShape('terminator',300,320,'Конец',38);b.role='end';
  m.shapes.push(a,b);
  const r=autoRoute(m,a,b);
  m.edges.push({id:uid('e'),points:r.pts.map(p=>[r2(p[0]),r2(p[1])]),arrow:true,
                from:{id:a.id,port:r.from},to:{id:b.id,port:r.to}});
  return m;
}
"""

JS_APP = r"""
/* ---------- state ---------- */
const $=s=>document.querySelector(s);
let docs={}, custom=[], dirty=new Set(), names={}, cur=null, view=null, zoom=1;
let exportTitle=false;
let sel={shapes:new Set(),edges:new Set(),labels:new Set()};
let tool='select', hist=[], future=[], drag=null, pending=null, guides=[];

function loadStore(){
  try{const raw=JSON.parse(localStorage.getItem(STORE)||'{}');
    docs=raw.docs||{}; custom=raw.custom||[]; dirty=new Set(raw.dirty||[]);
    names=raw.names||{};
    LANG=raw.lang||DATA.lang||LANG;          // the viewer's choice wins over the defaults,
    THEME=raw.theme||DATA.theme||THEME;      // which come from the command line
    if(raw.exportTitle!==undefined)exportTitle=!!raw.exportTitle;}
  catch(e){docs={};custom=[];dirty=new Set();names={};
           LANG=DATA.lang||LANG;THEME=DATA.theme||THEME;}
  if(!I18N[LANG])LANG='ru';
  if(!THEMES[THEME])THEME='light';
}
function saveStore(){
  /* store only edited and hand-made charts */
  const keep={}, mine=new Set(custom.map(c=>c.anchor));
  for(const k of Object.keys(docs))if(dirty.has(k)||mine.has(k))keep[k]=docs[k];
  try{localStorage.setItem(STORE,JSON.stringify(
    {docs:keep,custom,dirty:[...dirty],names,lang:LANG,theme:THEME,exportTitle}));}
  catch(e){toast(t('s_storage'));}
}
function entries(){
  return DATA.items.concat(custom.map(c=>({anchor:c.anchor,name:c.name,rel:t('my_charts'),
    signature:t('made_by_hand'),line:0,custom:true})));
}
function meta(){return entries().find(i=>i.anchor===cur)||{name:'',rel:'',signature:'',line:0};}
function nameOf(it){return (it&&names[it.anchor])||(it&&it.name)||'';}
function fileBase(){
  return (nameOf(meta())||cur||'chart').replace(/[^0-9A-Za-zА-Яа-яЁё_.-]+/g,'_');}
function model(){
  if(!docs[cur]){
    const it=meta();
    const base=it&&it.model?clone(it.model):emptyDoc(it?it.name:'Схема');
    docs[cur]=hydrate(base);
  }
  return docs[cur];
}
function isEdited(a){return dirty.has(a);}
function toast(msg){const t=$('#toast');t.textContent=msg;t.classList.add('show');
  clearTimeout(t._t);t._t=setTimeout(()=>t.classList.remove('show'),2000);}

function push(){hist.push(clone(model()));if(hist.length>80)hist.shift();
  future.length=0; dirty.add(cur);}
function commit(){saveStore();draw();buildTree($('#search').value);inspect();}
function undo(){if(!hist.length)return;future.push(clone(model()));
  docs[cur]=hist.pop();clearSel();commit();}
function redo(){if(!future.length)return;hist.push(clone(model()));
  docs[cur]=future.pop();clearSel();commit();}

/* ---------- selection ---------- */
function clearSel(){sel={shapes:new Set(),edges:new Set(),labels:new Set()};}
function selCount(){return sel.shapes.size+sel.edges.size+sel.labels.size;}
function selectOnly(kind,id){clearSel();sel[kind].add(id);}

/* ---------- canvas ---------- */
function ensureView(m,reset){
  const b=bbox(m);
  if(reset||!view){view={x0:b.x0-PAD,y0:b.y0-PAD,x1:b.x1+PAD,y1:b.y1+PAD};return;}
  view={x0:Math.min(view.x0,b.x0-PAD),y0:Math.min(view.y0,b.y0-PAD),
        x1:Math.max(view.x1,b.x1+PAD),y1:Math.max(view.y1,b.y1+PAD)};
}
function draw(){
  const m=model(); ensureView(m,false);
  const out=renderSVG(m,{interactive:true,view,name:nameOf(meta())});
  $('#sheet').innerHTML=out.svg;
  const svg=$('#sheet svg');
  size={w:out.w,h:out.h}; setZoom(zoom);
  drawUI();
  svg.addEventListener('pointerdown',onDown);
  svg.addEventListener('pointermove',onMove);
  svg.addEventListener('pointerup',onUp);
  svg.addEventListener('pointercancel',onUp);
  svg.addEventListener('dblclick',onDbl);
}
/* zooming only rescales the SVG element, the scene is not rebuilt */
let size={w:0,h:0};
function setZoom(z){
  zoom=Math.max(.2,Math.min(3,z));
  const svg=$('#sheet svg');
  if(svg){svg.style.width=(size.w*zoom)+'px'; svg.style.height=(size.h*zoom)+'px';}
  $('#zoomVal').textContent=Math.round(zoom*100)+'%';
}
function fitZoom(max){
  ensureView(model(),true);
  const out=renderSVG(model(),{view}), st=$('#stage'), cs=getComputedStyle(st);
  const room=st.clientWidth-parseFloat(cs.paddingLeft)-parseFloat(cs.paddingRight)
             -2*parseFloat(getComputedStyle($('#sheet')).paddingLeft);
  return Math.max(.2,Math.min(max,room/out.w));
}
const narrow=()=>matchMedia('(max-width:820px)').matches;
const coarse=()=>matchMedia('(pointer:coarse)').matches;
function ui(){return $('#__ui');}
function drawUI(){
  const g=ui(); if(!g)return;
  const m=model(); const parts=[], k=coarse()?1.8:1, hs=4*k;
  for(const id of sel.shapes){
    const s=m.shapes.find(x=>x.id===id); if(!s)continue;
    parts.push(`<rect class="sel-outline" x="${n(s.x-4)}" y="${n(s.y-4)}" width="${n(s.w+8)}" height="${n(s.h+8)}" rx="3"/>`);
    if(sel.shapes.size===1){
      const a=[[s.x+s.w,s.y+s.h/2,'e'],[s.x+s.w/2,s.y+s.h,'s'],[s.x+s.w,s.y+s.h,'se']];
      for(const [x,y,dir] of a)
        parts.push(`<rect class="handle" data-resize="${dir}" x="${n(x-hs)}" y="${n(y-hs)}" width="${n(2*hs)}" height="${n(2*hs)}" rx="2"/>`);
    }
  }
  for(const id of sel.edges){
    const e=m.edges.find(x=>x.id===id); if(!e)continue;
    e.points.forEach((p,i)=>{
      const bound=(i===0&&e.from)||(i===e.points.length-1&&e.to);
      parts.push(`<circle class="handle${bound?' bound':''}" data-vtx="${esc(e.id)}:${i}" cx="${n(p[0])}" cy="${n(p[1])}" r="${n(5*k)}"/>`);
      if(i<e.points.length-1){const q=e.points[i+1];
        parts.push(`<circle class="handle mid" data-mid="${esc(e.id)}:${i}" cx="${n((p[0]+q[0])/2)}" cy="${n((p[1]+q[1])/2)}" r="${n(3.6*k)}"/>`);}
    });
  }
  for(const id of sel.labels){
    const l=m.labels.find(x=>x.id===id); if(!l)continue;
    const w=textWidth(l.text,LBL);
    const x=l.anchor==='start'?l.x:(l.anchor==='end'?l.x-w:l.x-w/2);
    parts.push(`<rect class="sel-outline" x="${n(x-3)}" y="${n(l.y-LBL-2)}" width="${n(w+6)}" height="${n(LBL+7)}" rx="2"/>`);
  }
  for(const gd of guides)parts.push(`<line class="guide" x1="${n(gd[0])}" y1="${n(gd[1])}" x2="${n(gd[2])}" y2="${n(gd[3])}"/>`);
  if(drag&&drag.type==='marquee'){
    const[x0,y0]=drag.from,[x1,y1]=drag.at;
    parts.push(`<rect class="marquee" x="${n(Math.min(x0,x1))}" y="${n(Math.min(y0,y1))}" width="${n(Math.abs(x1-x0))}" height="${n(Math.abs(y1-y0))}"/>`);
  }
  if(pending){const a=pending.shape,A=anchors(a);
    parts.push(`<circle class="handle bound" cx="${n(A.bottom[0])}" cy="${n(A.bottom[1])}" r="5"/>`);
    if(pending.at)parts.push(`<line class="guide" x1="${n(A.bottom[0])}" y1="${n(A.bottom[1])}" x2="${n(pending.at[0])}" y2="${n(pending.at[1])}"/>`);}
  g.innerHTML=parts.join('\n');
}

/* ---------- coordinates ---------- */
function pt(ev){
  const svg=$('#sheet svg'), scene=svg.querySelector('#__ui').parentNode;
  const p=svg.createSVGPoint(); p.x=ev.clientX; p.y=ev.clientY;
  const q=p.matrixTransform(scene.getScreenCTM().inverse());
  return[q.x,q.y];
}
const snap=(v,off)=>off?v:Math.round(v/GRID)*GRID;
function hitShape(m,p){
  for(let i=m.shapes.length-1;i>=0;i--){const s=m.shapes[i];
    if(p[0]>=s.x&&p[0]<=s.x+s.w&&p[1]>=s.y&&p[1]<=s.y+s.h)return s;}
  return null;
}

/* ---------- pointer input ---------- */
const touches=new Map();
function startPinch(){
  /* a second finger turns any gesture in progress into a pinch */
  if(drag&&(drag.type==='move'||drag.type==='resize'||drag.type==='vtx')&&hist.length)
    docs[cur]=hist.pop();
  const [a,b]=[...touches.values()], st=$('#stage'), r=st.getBoundingClientRect();
  const mx=(a[0]+b[0])/2-r.left, my=(a[1]+b[1])/2-r.top;
  drag={type:'pinch',d0:Math.hypot(a[0]-b[0],a[1]-b[1])||1,z0:zoom,mx,my,
        fx:(st.scrollLeft+mx)/zoom,fy:(st.scrollTop+my)/zoom};
  guides=[]; pending=null; redrawFast();
}
function onDown(ev){
  if(ev.pointerType==='touch'){
    touches.set(ev.pointerId,[ev.clientX,ev.clientY]);
    try{$('#sheet svg').setPointerCapture(ev.pointerId);}catch(e){}
    if(touches.size===2){startPinch();return;}
    if(touches.size>2)return;
  }
  if(ev.button!==0)return;
  const m=model(), p=pt(ev), t=ev.target;
  try{$('#sheet svg').setPointerCapture(ev.pointerId);}catch(e){}
  if(tool.startsWith('add:')){
    push(); const kind=tool.slice(4);
    const s=newShape(kind,snap(p[0],ev.altKey),snap(p[1],ev.altKey),
                     kind==='decision'?'условие':'действие',m.maxChars);
    s.notation=m.notation||'course';
    m.shapes.push(s); selectOnly('shapes',s.id); setTool('select'); commit(); return;
  }
  if(tool==='label'){
    push(); const l={id:uid('l'),x:r2(p[0]),y:r2(p[1]),text:'подпись',anchor:'start'};
    m.labels.push(l); selectOnly('labels',l.id); setTool('select'); commit(); return;
  }
  if(tool==='connect'){
    const s=hitShape(m,p);
    if(!s){pending=null;drawUI();return;}
    if(!pending){pending={shape:s,at:p};drawUI();return;}
    if(pending.shape.id!==s.id&&flowPorts(pending.shape,true).length&&flowPorts(s,false).length){
      push(); const r=autoRoute(m,pending.shape,s);
      const e={id:uid('e'),points:r.pts.map(q=>[r2(q[0]),r2(q[1])]),arrow:true,
        from:{id:pending.shape.id,port:r.from},to:{id:s.id,port:r.to}};
      m.edges.push(e); rerouteEdge(m,e,true);
      commit();
    }
    pending=null; setTool('select'); drawUI(); return;
  }
  const resize=t.getAttribute&&t.getAttribute('data-resize');
  const vtx=t.getAttribute&&t.getAttribute('data-vtx');
  const mid=t.getAttribute&&t.getAttribute('data-mid');
  if(mid){
    const[eid,i]=mid.split(':'); const e=m.edges.find(x=>x.id===eid);
    push(); const a=e.points[+i],b=e.points[+i+1];
    e.points.splice(+i+1,0,[r2((a[0]+b[0])/2),r2((a[1]+b[1])/2)]);
    drag={type:'vtx',edge:eid,idx:+i+1}; commit(); return;
  }
  if(vtx){const[eid,i]=vtx.split(':'); push(); drag={type:'vtx',edge:eid,idx:+i};return;}
  if(resize){const id=[...sel.shapes][0]; push();
    drag={type:'resize',dir:resize,id,from:p,edges:clone(m.edges),
          orig:clone(m.shapes.find(s=>s.id===id))};return;}
  const shapeEl=t.closest&&t.closest('[data-shape]');
  const edgeEl=t.closest&&t.closest('[data-edge]');
  const labelEl=t.closest&&t.closest('[data-label]');
  if(shapeEl){
    const id=shapeEl.getAttribute('data-shape');
    if(ev.shiftKey)sel.shapes.has(id)?sel.shapes.delete(id):sel.shapes.add(id);
    else if(!sel.shapes.has(id))selectOnly('shapes',id);
    push();
    /* edges are recomputed from the state at drag start, so errors do not
       accumulate and moving a block back restores its original edges */
    drag={type:'move',from:p,at:p,lead:id,edges:clone(m.edges),
          orig:m.shapes.filter(s=>sel.shapes.has(s.id)).map(s=>({id:s.id,x:s.x,y:s.y})),
          origL:m.labels.filter(l=>sel.labels.has(l.id)).map(l=>({id:l.id,x:l.x,y:l.y}))};
    inspect(); drawUI(); return;
  }
  if(labelEl){
    const id=labelEl.getAttribute('data-label');
    if(!ev.shiftKey)clearSel(); sel.labels.add(id); push();
    const l=m.labels.find(x=>x.id===id);
    drag={type:'move',from:p,at:p,orig:[],origL:[{id,x:l.x,y:l.y}]};
    inspect(); drawUI(); return;
  }
  if(edgeEl){
    const id=edgeEl.getAttribute('data-edge');
    if(!ev.shiftKey)clearSel(); sel.edges.add(id);
    inspect(); drawUI(); return;
  }
  if(!ev.shiftKey)clearSel();
  if(ev.pointerType==='touch'){
    const st=$('#stage');
    drag={type:'pan',cx:ev.clientX,cy:ev.clientY,sl:st.scrollLeft,stp:st.scrollTop};
  }else drag={type:'marquee',from:p,at:p};
  inspect(); drawUI();
}
/* handle at most one move per frame: rerouting is slower on phones and
   events would pile up otherwise */
let moveEv=null;
function onMove(ev){
  if(touches.has(ev.pointerId))touches.set(ev.pointerId,[ev.clientX,ev.clientY]);
  if(!drag&&!pending)return;
  const first=!moveEv;
  moveEv={clientX:ev.clientX,clientY:ev.clientY,altKey:ev.altKey};
  if(first)requestAnimationFrame(flushMove);
}
function flushMove(){
  const ev=moveEv; moveEv=null;
  if(ev&&(drag||pending))moveNow(ev);
}
function moveNow(ev){
  if(drag&&drag.type==='pinch'){
    if(touches.size<2)return;
    const [a,b]=[...touches.values()], st=$('#stage');
    setZoom(drag.z0*Math.hypot(a[0]-b[0],a[1]-b[1])/drag.d0);
    st.scrollLeft=drag.fx*zoom-drag.mx; st.scrollTop=drag.fy*zoom-drag.my;
    return;
  }
  if(drag&&drag.type==='pan'){
    const st=$('#stage');
    st.scrollLeft=drag.sl-(ev.clientX-drag.cx); st.scrollTop=drag.stp-(ev.clientY-drag.cy);
    return;
  }
  const m=model(), p=pt(ev);
  if(pending){pending.at=p;drawUI();return;}
  if(drag.type==='marquee'){drag.at=p;drawUI();return;}
  if(drag.type==='move'){
    let dx=p[0]-drag.from[0], dy=p[1]-drag.from[1];
    guides=[];
    if(!ev.altKey&&drag.orig.length===1){
      const s=m.shapes.find(x=>x.id===drag.orig[0].id);
      const cx=drag.orig[0].x+dx+s.w/2;
      for(const o of m.shapes){
        if(o.id===s.id)continue;
        const ox=o.x+o.w/2;
        if(Math.abs(ox-cx)<7){dx+=ox-cx;
          guides.push([ox,Math.min(o.y,drag.orig[0].y+dy)-30,ox,
                       Math.max(o.y+o.h,drag.orig[0].y+dy+s.h)+30]);break;}
      }
    }
    /* the block under the cursor snaps to the grid and the rest of the
       selection follows by the same offset, so a group keeps its shape */
    const lead=drag.orig.find(o=>o.id===drag.lead)||drag.orig[0];
    if(lead){dx=r2(snap(lead.x+dx,ev.altKey||guides.length>0)-lead.x);
             dy=r2(snap(lead.y+dy,ev.altKey)-lead.y);}
    for(const o of drag.orig){const s=m.shapes.find(x=>x.id===o.id);
      s.x=r2(o.x+dx); s.y=r2(o.y+dy);}
    for(const o of drag.origL){const l=m.labels.find(x=>x.id===o.id);
      l.x=r2(o.x+dx); l.y=r2(o.y+dy);}
    m.edges=clone(drag.edges);
    syncEdges(m,drag.orig.map(o=>o.id),{delta:[dx,dy]});
    drag.at=p; redrawFast(); return;
  }
  if(drag.type==='resize'){
    const s=m.shapes.find(x=>x.id===drag.id), o=drag.orig;
    if(drag.dir!=='s')s.w=r2(Math.max(60,snap(o.w+(p[0]-drag.from[0]),ev.altKey)));
    if(drag.dir!=='e')s.h=r2(Math.max(34,snap(o.h+(p[1]-drag.from[1]),ev.altKey)));
    m.edges=clone(drag.edges);
    syncEdges(m,[s.id]); redrawFast(); return;
  }
  if(drag.type==='vtx'){
    const e=m.edges.find(x=>x.id===drag.edge); if(!e)return;
    e.points[drag.idx]=[r2(snap(p[0],ev.altKey)),r2(snap(p[1],ev.altKey))];
    if(drag.idx===0)e.from=null;
    if(drag.idx===e.points.length-1)e.to=null;
    redrawFast(); return;
  }
}
function onUp(ev){
  const wasTouch=touches.delete(ev.pointerId);
  if(drag&&drag.type==='pinch'){if(touches.size<2)drag=null;return;}
  if(wasTouch&&!drag&&touches.size)return;
  flushMove();
  if(drag&&drag.type==='pan'){drag=null;return;}
  const m=model();
  if(drag&&drag.type==='marquee'){
    const[x0,y0]=drag.from,[x1,y1]=drag.at;
    const a=[Math.min(x0,x1),Math.min(y0,y1),Math.max(x0,x1),Math.max(y0,y1)];
    if(Math.abs(x1-x0)>3||Math.abs(y1-y0)>3){
      for(const s of m.shapes)
        if(s.x>=a[0]&&s.y>=a[1]&&s.x+s.w<=a[2]&&s.y+s.h<=a[3])sel.shapes.add(s.id);
      for(const l of m.labels)
        if(l.x>=a[0]&&l.y>=a[1]&&l.x<=a[2]&&l.y<=a[3])sel.labels.add(l.id);
    }
  }
  if(drag&&drag.type==='vtx'){        // an end dropped onto a block attaches to it
    const e=m.edges.find(x=>x.id===drag.edge);
    if(e&&(drag.idx===0||drag.idx===e.points.length-1)){
      const s=hitShape(m,e.points[drag.idx]);
      if(s){
        const A=anchors(s), p=e.points[drag.idx];
        let best='top',bd=1e9;
        const ports=flowPorts(s,drag.idx===0);
        if(!ports.length){guides=[];drag=null;commit();return;}
        for(const port of ports){
          const d=Math.hypot(A[port][0]-p[0],A[port][1]-p[1]);
          if(d<bd){bd=d;best=port;}
        }
        e.points[drag.idx]=[r2(A[best][0]),r2(A[best][1])];
        if(drag.idx===0)e.from={id:s.id,port:best}; else e.to={id:s.id,port:best};
        routeEdges(m,[e]);
      }
    }
  }
  guides=[]; drag=null; commit();
}
function onDbl(ev){
  const el=ev.target.closest&&ev.target.closest('[data-shape],[data-label]');
  if(!el)return;
  const id=el.getAttribute('data-shape')||el.getAttribute('data-label');
  clearSel();
  (el.hasAttribute('data-shape')?sel.shapes:sel.labels).add(id);
  inspect(); drawUI();
  const f=$('#fText'); if(f){f.focus();f.select();}
}
/* redraw during a drag without rebuilding the panels */
function redrawFast(){
  const m=model();
  const svg=$('#sheet svg'); if(!svg)return;
  const out=renderSVG(m,{interactive:true,view,name:nameOf(meta())});
  svg.innerHTML=out.svg.slice(out.svg.indexOf('>')+1,out.svg.lastIndexOf('</svg>'));
  drawUI();
}

/* ---------- operations ---------- */
function delSel(){
  const m=model(); if(!selCount())return; push();
  m.shapes=m.shapes.filter(s=>!sel.shapes.has(s.id));
  m.labels=m.labels.filter(l=>!sel.labels.has(l.id));
  m.edges=m.edges.filter(e=>!sel.edges.has(e.id));
  for(const e of m.edges){
    if(e.from&&sel.shapes.has(e.from.id))e.from=null;
    if(e.to&&sel.shapes.has(e.to.id))e.to=null;
  }
  clearSel(); commit();
}
function dupSel(){
  const m=model(); if(!sel.shapes.size)return; push();
  const added=[];
  for(const id of sel.shapes){
    const s=m.shapes.find(x=>x.id===id); if(!s)continue;
    const c=clone(s); c.id=uid('s'); c.x=r2(s.x+20); c.y=r2(s.y+20);
    m.shapes.push(c); added.push(c.id);
  }
  clearSel(); added.forEach(i=>sel.shapes.add(i)); commit();
}
function nudge(dx,dy){
  const m=model(); if(!selCount())return; push();
  for(const id of sel.shapes){const s=m.shapes.find(x=>x.id===id);
    if(s){s.x=r2(s.x+dx);s.y=r2(s.y+dy);}}
  for(const id of sel.labels){const l=m.labels.find(x=>x.id===id);
    if(l){l.x=r2(l.x+dx);l.y=r2(l.y+dy);}}
  for(const id of sel.edges){const e=m.edges.find(x=>x.id===id);
    if(e)e.points=e.points.map(p=>[r2(p[0]+dx),r2(p[1]+dy)]);}
  syncEdges(m,[...sel.shapes],{delta:[dx,dy],skip:[...sel.edges]}); commit();
}
function fitShape(id){
  const m=model(), s=m.shapes.find(x=>x.id===id); if(!s)return;
  const g=sizeFor(s.kind,s.text,m.maxChars,s.notation);
  s.lines=g.lines;
  const cx=s.x+s.w/2;
  s.x=r2(cx-g.w/2); s.w=g.w; s.h=g.h; syncEdges(m,[s.id]);
}

/* ---------- inspector ---------- */
function inspect(){
  const box=$('#inspBody'), m=model();
  document.body.classList.toggle('insp-open',selCount()>0);
  if(sel.shapes.size===1&&!sel.edges.size){
    const s=m.shapes.find(x=>x.id===[...sel.shapes][0]);
    if(!s){box.innerHTML='';return;}
    box.innerHTML=
      `<label>${t('i_type')}</label><select id="fKind">${KINDS.map(k=>
        `<option value="${k}"${k===s.kind?' selected':''}>${KIND_LABEL(k)}</option>`).join('')}</select>`+
      `<label>${t('i_text')}</label><textarea id="fText" spellcheck="false">${esc(s.text)}</textarea>`+
      `<label style="display:flex;gap:7px;align-items:center;margin-top:11px">
        <input type="checkbox" id="fShift" style="width:auto" checked>
        ${t('i_shift')}</label>`+
      `<div class="row"><button class="primary" id="fApply">${t('i_apply')}</button>`+
      `<button id="fFit">${t('i_fit')}</button></div>`+
      `<div class="row"><button id="fDup">${t('i_dup')}</button>`+
      `<button id="fDel">${t('i_del')}</button></div>`+
      `<div class="row"><button id="fReroute">${t('i_reroute')}</button></div>`+
      `<p class="note">${t('i_hint_block')}</p>`;
    const apply=()=>{push();
      const shift=$('#fShift').checked, bottom=s.y+s.h, h0=s.h;
      s.kind=$('#fKind').value; s.text=$('#fText').value;
      fitShape(s.id);
      if(shift)shiftBelow(model(),bottom,r2(s.h-h0));
      syncEdges(model(),[s.id]);
      commit();const f=$('#fText');if(f)f.focus();};
    $('#fApply').onclick=apply; $('#fKind').onchange=apply;
    $('#fText').onkeydown=e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();apply();}};
    $('#fFit').onclick=()=>{push();fitShape(s.id);commit();};
    $('#fReroute').onclick=()=>{push();
      const ok=id=>m.shapes.some(x=>x.id===id);
      const list=m.edges.filter(e=>e.from&&e.to&&ok(e.from.id)&&ok(e.to.id)&&
        (e.from.id===s.id||e.to.id===s.id));
      routeEdges(m,list,{free:true});     // together, so parallel edges spread apart
      commit();toast(list.length?t('s_rerouted',list.length):t('s_no_links'));};
    $('#fDup').onclick=dupSel; $('#fDel').onclick=delSel;
    return;
  }
  if(sel.edges.size===1&&!sel.shapes.size){
    const e=m.edges.find(x=>x.id===[...sel.edges][0]);
    if(!e){box.innerHTML='';return;}
    const nm=r=>r?(m.shapes.find(s=>s.id===r.id)||{}).text||'—':t('i_free');
    box.innerHTML=
      `<p class="note">${t('i_from')}: <b>${esc(nm(e.from))}</b><br>${t('i_to')}: <b>${esc(nm(e.to))}</b></p>`+
      `<label>${t('i_arrow')}</label>
       <select id="fArrow"><option value="1"${e.arrow!==false?' selected':''}>${t('i_arrow_on')}</option>
       <option value="0"${e.arrow===false?' selected':''}>${t('i_arrow_off')}</option></select>`+
      `<div class="row"><button id="fStraight">${t('i_straight')}</button>
       <button id="fRoute">${t('i_route')}</button></div>`+
      `<div class="row"><button id="fDel">${t('i_del')}</button></div>`+
      `<p class="note">${t('i_hint_edge')}</p>`;
    $('#fArrow').onchange=()=>{push();e.arrow=$('#fArrow').value==='1';commit();};
    $('#fStraight').onclick=()=>{push();
      const a=e.points[0],b=e.points[e.points.length-1];
      e.points=Math.abs(a[0]-b[0])<2||Math.abs(a[1]-b[1])<2?[a,b]
        :[a,[a[0],r2((a[1]+b[1])/2)],[b[0],r2((a[1]+b[1])/2)],b];
      commit();};
    $('#fRoute').onclick=()=>{push();
      if(!rerouteEdge(m,e))toast(t('s_unbound'));
      commit();};
    $('#fDel').onclick=delSel;
    return;
  }
  if(sel.labels.size===1&&!sel.shapes.size&&!sel.edges.size){
    const l=m.labels.find(x=>x.id===[...sel.labels][0]);
    if(!l){box.innerHTML='';return;}
    box.innerHTML=`<label>${t('i_label_text')}</label>
      <input id="fText" value="${esc(l.text)}">
      <label>${t('i_align')}</label>
      <select id="fAn">${['start','middle','end'].map(a=>
        `<option value="${a}"${a===l.anchor?' selected':''}>${
          {start:t('i_left'),middle:t('i_center'),end:t('i_right')}[a]}</option>`).join('')}</select>
      <div class="row"><button class="primary" id="fApply">${t('i_apply')}</button>
      <button id="fDel">${t('i_del')}</button></div>`;
    const ap=()=>{push();l.text=$('#fText').value;l.anchor=$('#fAn').value;commit();};
    $('#fApply').onclick=ap; $('#fAn').onchange=ap;
    $('#fText').onkeydown=e=>{if(e.key==='Enter'){e.preventDefault();ap();}};
    $('#fDel').onclick=delSel;
    return;
  }
  if(selCount()>1){
    box.innerHTML=`<p class="note">${t('i_selected',selCount())}</p>
      <div class="row"><button id="fDel">${t('i_del')}</button>
      <button id="fDup">${t('i_dup')}</button></div>
      <label>${t('i_align_v')}</label>
      <div class="row"><button id="fAlign">${t('i_align_c')}</button>
      <button id="fSpread">${t('i_spread')}</button></div>`;
    $('#fDel').onclick=delSel; $('#fDup').onclick=dupSel;
    $('#fAlign').onclick=()=>{const m2=model();const ss=m2.shapes.filter(s=>sel.shapes.has(s.id));
      if(ss.length<2)return;push();
      const cx=ss.reduce((a,s)=>a+s.x+s.w/2,0)/ss.length;
      ss.forEach(s=>s.x=r2(cx-s.w/2)); syncEdges(m2,ss.map(s=>s.id)); commit();};
    $('#fSpread').onclick=()=>{const m2=model();
      const ss=m2.shapes.filter(s=>sel.shapes.has(s.id)).sort((a,b)=>a.y-b.y);
      if(ss.length<3)return;push();
      const top=ss[0].y, bot=ss[ss.length-1].y, step=(bot-top)/(ss.length-1);
      ss.forEach((s,i)=>s.y=r2(top+step*i)); syncEdges(m2,ss.map(s=>s.id)); commit();};
    return;
  }
  box.innerHTML=`<p class="note">${t('i_empty')}</p>`;
}

/* ---------- chart list ---------- */
function buildTree(filter){
  const box=$('#tree'); box.innerHTML='';
  const q=(filter||'').trim().toLowerCase();
  let last=null;
  for(const it of entries()){
    if(q&&!(it.name.toLowerCase().includes(q)||it.rel.toLowerCase().includes(q)))continue;
    if(it.rel!==last){last=it.rel;
      const d=document.createElement('div');d.className='sec';d.textContent=it.rel;
      box.appendChild(d);}
    const a=document.createElement('a');
    a.innerHTML=`<span>${esc(nameOf(it))}</span><span class="ln">${
      it.custom?t('own'):':'+it.line}</span>`;
    if(isEdited(it.anchor))a.classList.add('edited');
    if(cur===it.anchor)a.classList.add('active');
    a.onclick=()=>show(it.anchor);
    box.appendChild(a);
  }
}
function show(anchor){
  cur=anchor; clearSel(); hist=[]; future=[]; view=null; pending=null;
  const it=meta();
  $('#figName').textContent=nameOf(it);
  $('#figMeta').textContent=it.signature+(it.line?('  ·  '+it.rel+':'+it.line):'');
  const i=entries().findIndex(x=>x.anchor===anchor);
  $('#caption').textContent=t('caption',i+1,nameOf(it));
  document.title=nameOf(it)+' — '+t('app_title',DATA.folder||'');
  ensureView(model(),true);
  if(narrow())zoom=Math.max(.5,fitZoom(1));
  draw(); buildTree($('#search').value); inspect();
  const st=$('#stage'); st.scrollTop=0; st.scrollLeft=(st.scrollWidth-st.clientWidth)/2;
}
function newDoc(){
  const name=prompt(t('m_new_name'),t('m_new_default',custom.length+1));
  if(!name)return;
  const anchor='custom_'+uid('d');
  custom.push({anchor,name});
  docs[anchor]=hydrate(emptyDoc(name));
  saveStore(); show(anchor); toast(t('s_new'));
}
function delDoc(){
  const it=meta(); if(!it)return;
  if(it.custom){
    if(!confirm(t('m_del_chart',nameOf(it))))return;
    custom=custom.filter(c=>c.anchor!==it.anchor); delete docs[it.anchor];
    saveStore(); show(entries()[0].anchor); toast(t('s_deleted'));
  }else{
    if(!dirty.has(it.anchor)){toast(t('s_no_edits'));return;}
    if(!confirm(t('m_reset_chart',nameOf(it))))return;
    delete docs[it.anchor]; dirty.delete(it.anchor);
    saveStore(); show(it.anchor); toast(t('s_reset'));
  }
}

/* ---------- theme, language, chart name ---------- */
function applyTheme(){
  document.body.dataset.theme=THEME;
  const b=$('#btnTheme'); if(b)b.textContent=THEME==='dark'?'☀':'☾';
  if(cur)draw();
}
function toggleTheme(){THEME=THEME==='dark'?'light':'dark';saveStore();applyTheme();}

function applyLang(){
  document.documentElement.lang=LANG;
  const b=$('#btnLang'); if(b)b.textContent=LANG==='ru'?'EN':'RU';
  document.querySelectorAll('[data-i18n]').forEach(el=>{
    el.textContent=t(el.getAttribute('data-i18n'));});
  document.querySelectorAll('[data-i18n-title]').forEach(el=>{
    el.title=t(el.getAttribute('data-i18n-title'));});
  document.querySelectorAll('[data-i18n-ph]').forEach(el=>{
    el.placeholder=t(el.getAttribute('data-i18n-ph'));});
  $('#appTitle').textContent=t('app_title',DATA.folder||'');
  $('#appSub').textContent=t('charts_count',DATA.items.length);
  if(cur){show(cur);}
}
function toggleLang(){LANG=LANG==='ru'?'en':'ru';saveStore();applyLang();}

function renameChart(){
  const it=meta(); if(!it||!cur)return;
  const name=prompt(t('m_rename'),nameOf(it));
  if(name===null)return;
  const clean=name.trim();
  if(!clean||clean===nameOf(it))return;
  names[cur]=clean;
  const own=custom.find(c=>c.anchor===cur);
  if(own)own.name=clean;
  saveStore(); show(cur); toast(t('s_renamed'));
}

/* ---------- tools ---------- */
function setTool(t){
  tool=t; pending=null;
  document.querySelectorAll('[data-tool]').forEach(b=>
    b.classList.toggle('on',b.getAttribute('data-tool')===t));
  const svg=$('#sheet svg');
  if(svg)svg.style.cursor=(t==='select')?'default':'crosshair';
  drawUI();
}

/* ---------- export ---------- */
function exportSVG(){
  const it=meta();
  const title=exportTitle?(nameOf(it)+(it.line?' — '+it.rel:'')):null;
  return renderSVG(model(),{title,name:nameOf(it)}).svg;
}
function download(blob,name){
  const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download=name;
  document.body.appendChild(a);a.click();
  setTimeout(()=>{URL.revokeObjectURL(a.href);a.remove();},400);
}
function svgToPng(svgText,scale){
  return new Promise((res,rej)=>{
    const blob=new Blob([svgText],{type:'image/svg+xml;charset=utf-8'});
    const url=URL.createObjectURL(blob),img=new Image();
    img.onload=()=>{const c=document.createElement('canvas');
      c.width=Math.round(img.width*scale);c.height=Math.round(img.height*scale);
      const ctx=c.getContext('2d');ctx.fillStyle='#fff';ctx.fillRect(0,0,c.width,c.height);
      ctx.drawImage(img,0,0,c.width,c.height);URL.revokeObjectURL(url);
      c.toBlob(b=>b?res(b):rej(new Error('canvas')),'image/png');};
    img.onerror=e=>{URL.revokeObjectURL(url);rej(e);};
    img.src=url;});
}
async function doPng(copy){
  const scale=parseFloat($('#scale').value);
  try{
    const blob=await svgToPng(exportSVG(),scale);
    if(copy){await navigator.clipboard.write([new ClipboardItem({'image/png':blob})]);
      toast(t('s_copied'));}
    else{download(blob,fileBase()+'@'+scale+'x.png');toast(t('s_png'));}
  }catch(e){toast(t(copy?'s_clip_fail':'s_png_fail'));}
}
function exportProject(){
  download(new Blob([JSON.stringify({docs,custom,names},null,1)],
    {type:'application/json'}),'blockwright-project.json');
  toast(t('s_proj_saved'));
}
function importProject(file){
  const rd=new FileReader();
  rd.onload=()=>{try{
      const d=JSON.parse(rd.result);
      docs=Object.assign(docs,d.docs||{});
      const have=new Set(custom.map(c=>c.anchor));
      for(const c of (d.custom||[]))if(!have.has(c.anchor))custom.push(c);
      names=Object.assign(names,d.names||{});
      saveStore(); show(cur||entries()[0].anchor); toast(t('s_proj_loaded'));
    }catch(e){toast(t('s_proj_bad'));}};
  rd.readAsText(file);
}

/* ---------- startup ---------- */
window.addEventListener('DOMContentLoaded',()=>{
  loadRouter();              // loads in the background; the fallback router works meanwhile
  loadStore();
  applyTheme();
  applyLang();
  const hash=decodeURIComponent(location.hash.slice(1));
  const list=entries();
  show(list.find(i=>i.anchor===hash)?hash:list[0].anchor);
  $('#search').oninput=e=>buildTree(e.target.value);
  $('#btnNew').onclick=newDoc;
  $('#btnDel').onclick=delDoc;
  $('#btnTheme').onclick=toggleTheme;
  $('#btnLang').onclick=toggleLang;
  $('#btnRename').onclick=renameChart;
  $('#figName').ondblclick=renameChart;
  const cap=$('#capTitle');
  cap.checked=exportTitle;
  cap.onchange=()=>{exportTitle=cap.checked;saveStore();};
  const body=document.body;
  $('#btnMenu').onclick=()=>{body.classList.remove('more-open');body.classList.toggle('nav-open');};
  $('#btnMore').onclick=()=>{body.classList.remove('nav-open');body.classList.toggle('more-open');};
  $('#scrim').onclick=()=>body.classList.remove('nav-open','more-open');
  $('#more').addEventListener('click',ev=>{
    if(ev.target.closest('button'))body.classList.remove('more-open');});
  $('#tree').addEventListener('click',()=>body.classList.remove('nav-open'));
  $('#btnInsp').onclick=()=>body.classList.remove('insp-open');
  document.querySelectorAll('[data-tool]').forEach(b=>
    b.onclick=()=>setTool(b.getAttribute('data-tool')));
  $('#zoomIn').onclick=()=>setZoom(zoom*1.25);
  $('#zoomOut').onclick=()=>setZoom(zoom/1.25);
  $('#zoom100').onclick=()=>setZoom(1);
  $('#zoomFit').onclick=()=>{zoom=fitZoom(2);draw();};
  $('#btnUndo').onclick=undo; $('#btnRedo').onclick=redo;
  $('#btnSvg').onclick=()=>{download(new Blob([exportSVG()],
    {type:'image/svg+xml;charset=utf-8'}),fileBase()+'.svg');
    toast(t('s_svg'));};
  $('#btnPng').onclick=()=>doPng(false);
  $('#btnCopy').onclick=()=>doPng(true);
  $('#btnPrint').onclick=()=>window.print();
  $('#btnSave').onclick=exportProject;
  $('#btnLoad').onclick=()=>$('#fileIn').click();
  $('#fileIn').onchange=e=>{if(e.target.files[0])importProject(e.target.files[0]);
    e.target.value='';};
  document.addEventListener('keydown',ev=>{
    const tag=(ev.target.tagName||'').toLowerCase();
    if(tag==='input'||tag==='textarea'||tag==='select')return;
    const ctrl=ev.ctrlKey||ev.metaKey;
    if(ctrl&&ev.key.toLowerCase()==='z'){ev.preventDefault();ev.shiftKey?redo():undo();return;}
    if(ctrl&&ev.key.toLowerCase()==='y'){ev.preventDefault();redo();return;}
    if(ctrl&&ev.key.toLowerCase()==='d'){ev.preventDefault();dupSel();return;}
    if(ctrl&&ev.key.toLowerCase()==='a'){ev.preventDefault();const m=model();
      m.shapes.forEach(s=>sel.shapes.add(s.id));m.edges.forEach(e=>sel.edges.add(e.id));
      m.labels.forEach(l=>sel.labels.add(l.id));drawUI();inspect();return;}
    if(ev.key==='Delete'||ev.key==='Backspace'){ev.preventDefault();delSel();return;}
    if(ev.key==='Escape'){document.body.classList.remove('nav-open','more-open');
      clearSel();setTool('select');drawUI();inspect();return;}
    const step=ev.shiftKey?10:1;
    if(ev.key==='ArrowLeft'){ev.preventDefault();nudge(-step,0);}
    if(ev.key==='ArrowRight'){ev.preventDefault();nudge(step,0);}
    if(ev.key==='ArrowUp'){ev.preventDefault();nudge(0,-step);}
    if(ev.key==='ArrowDown'){ev.preventDefault();nudge(0,step);}
    if(ev.key==='v')setTool('select');
    if(ev.key==='c')setTool('connect');
    if(ev.key==='t')setTool('label');
    const idx='1234567'.indexOf(ev.key);
    if(idx>=0)setTool('add:'+KINDS[idx]);
  });
  $('#stage').addEventListener('wheel',ev=>{
    if(!ev.ctrlKey)return; ev.preventDefault();
    setZoom(zoom*(ev.deltaY<0?1.1:1/1.1));
  },{passive:false});
});
"""

ICONS = {
    "terminator": '<rect x="3" y="7" width="20" height="12" rx="6"/>',
    "process": '<rect x="3" y="7" width="20" height="12"/>',
    "io": '<polygon points="7,7 23,7 19,19 3,19"/>',
    "input": '<polygon points="7,7 23,7 19,19 3,19"/>',
    "output": '<path d="M3 6 H23 V17 C17 16 10 23 3 19 Z"/>',
    "decision": '<polygon points="13,5 23,13 13,21 3,13"/>',
    "predefined": '<rect x="3" y="7" width="20" height="12"/>'
    '<line x1="7" y1="7" x2="7" y2="19"/><line x1="19" y1="7" x2="19" y2="19"/>',
    "preparation": '<polygon points="7,7 19,7 23,13 19,19 7,19 3,13"/>',
    "connector": '<circle cx="13" cy="13" r="7"/>',
}
KINDS = (
    "terminator",
    "process",
    "input",
    "output",
    "io",
    "decision",
    "predefined",
    "preparation",
    "connector",
)


def _palette():
    """Palette buttons; applyLang() fills in their titles."""
    ico = (
        '<svg width="26" height="26" viewBox="0 0 26 26" fill="none" '
        'stroke="currentColor" stroke-width="1.6">'
    )
    out = [
        (
            f'<button data-tool="select" class="on" data-i18n-title="t_select">{ico}'
            '<path d="M7 4 L7 20 L11 16 L14 22 L16 21 L13 15 L19 15 Z" '
            'fill="var(--panel)"/></svg></button>'
        ),
        (
            f'<button data-tool="connect" data-i18n-title="t_connect">{ico}'
            '<path d="M5 6 H15 V19"/><path d="M12 16 L15 20 L18 16 Z" '
            'fill="currentColor"/></svg></button>'
        ),
        (
            f'<button data-tool="label" data-i18n-title="t_label">{ico}'
            '<path d="M6 8 H20 M13 8 V19" stroke-width="1.8"/></svg></button>'
        ),
        '<div class="gap"></div>',
    ]
    for kind in KINDS:
        out.append(
            f'<button data-tool="add:{kind}" data-i18n-title="t_{kind}">'
            f'<svg width="26" height="26" viewBox="0 0 26 26" fill="var(--panel)" '
            f'stroke="currentColor" stroke-width="1.6">{ICONS[kind]}</svg></button>'
        )
    return "".join(out)


def _router_scripts():
    """libavoid from vendor/web, inlined into the page.

    The WebAssembly goes in as base64 because browsers block fetch() from
    file:// pages. Without the files the editor uses its fallback router.
    """
    js_path = web_asset("libavoid", "libavoid.js")
    wasm_path = web_asset("libavoid", "libavoid.wasm")
    if not (js_path and wasm_path):
        return ""
    with open(js_path, encoding="utf-8") as fh:
        js = fh.read().replace("</", "<\\/")
    with open(wasm_path, "rb") as fh:
        wasm = base64.b64encode(fh.read()).decode("ascii")
    return f'<script>{js}</script>\n<script>const AVOID_WASM="{wasm}";</script>\n'


def render_html(entries, title="Блок-схемы", folder="", lang="ru", theme="light"):
    """entries: dicts with rel, name, signature, line, anchor and model."""
    payload = json.dumps(
        {"folder": folder or title, "items": entries, "lang": lang, "theme": theme},
        ensure_ascii=False,
        separators=(",", ":"),
    )
    payload = payload.replace("</", "<\\/")
    return f"""<!DOCTYPE html>
<html lang="{lang}"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>{xml_escape(title)}</title>
<style>{CSS}</style></head>
<body data-theme="{theme}">
<div class="topbar">
  <button id="btnMenu" class="only-narrow" data-i18n-title="b_menu_t">☰</button>
  <div class="brand"><span id="appTitle">{xml_escape(title)}</span>
    <span class="sub"> · <span id="appSub"></span></span></div>
  <div class="grow"></div>
  <div class="group">
    <button id="btnUndo" data-i18n-title="b_undo">↶</button>
    <button id="btnRedo" data-i18n-title="b_redo">↷</button>
  </div>
  <div class="sep"></div>
  <div class="more" id="more">
  <div class="group">
    <label class="check" data-i18n-title="cap_title_t">
      <input type="checkbox" id="capTitle" checked>
      <span data-i18n="cap_title"></span></label>
    <select id="scale" title="PNG">
      <option value="1">PNG ×1</option><option value="2" selected>PNG ×2</option>
      <option value="3">PNG ×3</option><option value="4">PNG ×4</option>
    </select>
    <button id="btnCopy" class="primary" data-i18n="b_copy" data-i18n-title="b_copy_t"></button>
    <button id="btnPng" data-i18n="b_png"></button>
    <button id="btnSvg" data-i18n="b_svg" data-i18n-title="b_svg_t"></button>
    <button id="btnPrint" class="wide" data-i18n="b_print"></button>
  </div>
  <div class="sep"></div>
  <div class="group">
    <button id="btnSave" class="wide" data-i18n="b_project" data-i18n-title="b_project_t"></button>
    <button id="btnLoad" class="wide" data-i18n="b_open" data-i18n-title="b_open_t"></button>
    <input id="fileIn" type="file" accept=".json,application/json" hidden>
    <button id="btnTheme" data-i18n-title="b_theme_t">☾</button>
    <button id="btnLang" data-i18n-title="b_lang_t">EN</button>
  </div>
  </div>
  <button id="btnMore" class="only-narrow" data-i18n-title="b_more_t">⋯</button>
</div>

<div class="layout">
  <aside class="nav">
    <div class="navhead">
      <input id="search" type="search" data-i18n-ph="search">
      <button id="btnNew" data-i18n-title="b_new_t">＋</button>
    </div>
    <div class="tree" id="tree"></div>
    <div class="navfoot">
      <button id="btnDel" class="ghost danger" data-i18n="b_del" data-i18n-title="b_del_t"></button>
    </div>
  </aside>

  <main>
    <div class="toolbar">
      <span class="name" id="figName" data-i18n-title="b_rename_t"></span>
      <button id="btnRename" class="ghost tiny" data-i18n-title="b_rename_t">✎</button>
      <span class="meta" id="figMeta"></span>
      <div class="grow"></div>
      <div class="group">
        <button id="zoomOut" data-i18n-title="z_out">−</button>
        <span class="zoomval" id="zoomVal">100%</span>
        <button id="zoomIn" data-i18n-title="z_in">+</button>
        <button id="zoom100">1:1</button>
        <button id="zoomFit" data-i18n="z_fit"></button>
      </div>
    </div>
    <div class="work">
      <div class="palette">{_palette()}</div>
      <div class="stage" id="stage">
        <div class="sheet" id="sheet"></div>
        <div class="caption" id="caption"></div>
      </div>
    </div>
  </main>

  <aside class="insp">
    <div class="ihead"><h3 data-i18n="props"></h3>
      <button id="btnInsp" class="insp-close ghost tiny" data-i18n-title="b_close">✕</button></div>
    <div id="inspBody"></div>
  </aside>
</div>
<div class="scrim" id="scrim"></div>
<div class="toast" id="toast"></div>
<script>const DATA={payload};</script>
{_router_scripts()}<script>{JS_CORE}{JS_APP}</script>
</body></html>
"""
