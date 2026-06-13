import{c,h as e}from"./index-DLT6r6yY.js";/**
 * @license lucide-react v0.400.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const h=c("Search",[["circle",{cx:"11",cy:"11",r:"8",key:"4ej97u"}],["path",{d:"m21 21-4.3-4.3",key:"1qie3q"}]]),p={search:(a,t)=>e.get("/stocks",{params:{q:a,market:t,limit:50}}).then(s=>s.data),getActive:(a=100)=>e.get("/stocks/active",{params:{limit:a}}).then(t=>t.data),getDetail:a=>e.get(`/stocks/${a}`).then(t=>t.data),getDailyBars:(a,t=120)=>e.get(`/stocks/${a}/daily`,{params:{days:t}}).then(s=>s.data),getQuote:a=>e.get(`/stocks/${a}/quote`).then(t=>t.data),getSupply:(a,t=30)=>e.get(`/stocks/${a}/supply`,{params:{days:t}}).then(s=>s.data),getAnalysis:(a,t)=>e.get(`/stocks/${a}/analysis`,{params:t?{purchase_price:t}:void 0}).then(s=>s.data),watchStock:a=>e.post(`/stocks/${a}/watch`).then(t=>t.data)};export{h as S,p as s};
