import{c as o,h as e}from"./index-Du2WJhES.js";/**
 * @license lucide-react v0.400.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const n=o("BookOpen",[["path",{d:"M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z",key:"vv98re"}],["path",{d:"M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z",key:"1cyq3y"}]]),h={search:(a,t)=>e.get("/stocks",{params:{q:a,market:t,limit:50}}).then(s=>s.data),getActive:(a=100)=>e.get("/stocks/active",{params:{limit:a}}).then(t=>t.data),getDetail:a=>e.get(`/stocks/${a}`).then(t=>t.data),getDailyBars:(a,t=120)=>e.get(`/stocks/${a}/daily`,{params:{days:t}}).then(s=>s.data),getQuote:a=>e.get(`/stocks/${a}/quote`).then(t=>t.data),getSupply:(a,t=30)=>e.get(`/stocks/${a}/supply`,{params:{days:t}}).then(s=>s.data),getAnalysis:(a,t)=>e.get(`/stocks/${a}/analysis`,{params:t?{purchase_price:t}:void 0}).then(s=>s.data),getFinancials:a=>e.get(`/stocks/${a}/financials`).then(t=>t.data),watchStock:a=>e.post(`/stocks/${a}/watch`).then(t=>t.data),getOrderbook:a=>e.get(`/stocks/${a}/orderbook`).then(t=>t.data)};export{n as B,h as s};
