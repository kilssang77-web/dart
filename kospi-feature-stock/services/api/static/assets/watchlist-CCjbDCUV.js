import{c as i,h as e}from"./index-DLT6r6yY.js";/**
 * @license lucide-react v0.400.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const d=i("Star",[["polygon",{points:"12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2",key:"8f66p6"}]]);/**
 * @license lucide-react v0.400.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const r=i("Trash2",[["path",{d:"M3 6h18",key:"d0wm0j"}],["path",{d:"M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6",key:"4alrt4"}],["path",{d:"M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2",key:"v07s0e"}],["line",{x1:"10",x2:"10",y1:"11",y2:"17",key:"1uufr5"}],["line",{x1:"14",x2:"14",y1:"11",y2:"17",key:"xtxkd"}]]),o="fstock_session_id";function a(){let t=localStorage.getItem(o);return t||(t=`s_${Date.now()}_${Math.random().toString(36).slice(2,9)}`,localStorage.setItem(o,t)),t}const h={list:t=>e.get("/watchlist",{params:{session_id:t??a()}}).then(s=>s.data),add:(t,s)=>e.post("/watchlist",{code:t,session_id:a(),note:s}).then(n=>n.data),remove:t=>e.delete(`/watchlist/${t}`,{params:{session_id:a()}}).then(()=>{})};export{d as S,r as T,h as w};
