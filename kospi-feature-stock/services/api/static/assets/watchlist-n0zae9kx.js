import{c as n,h as e}from"./index-Wxjtblpf.js";/**
 * @license lucide-react v0.400.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const r=n("Star",[["polygon",{points:"12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2",key:"8f66p6"}]]),o="fstock_session_id";function a(){let t=localStorage.getItem(o);return t||(t=`s_${Date.now()}_${Math.random().toString(36).slice(2,9)}`,localStorage.setItem(o,t)),t}const d={list:t=>e.get("/watchlist",{params:{session_id:t??a()}}).then(s=>s.data),add:(t,s)=>e.post("/watchlist",{code:t,session_id:a(),note:s}).then(i=>i.data),remove:t=>e.delete(`/watchlist/${t}`,{params:{session_id:a()}}).then(()=>{})};export{r as S,d as w};
