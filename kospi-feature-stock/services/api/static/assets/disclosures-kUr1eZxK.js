import{c as s,i as a}from"./index-BwtkbNam.js";/**
 * @license lucide-react v0.400.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const r=s("FileText",[["path",{d:"M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z",key:"1rqfz7"}],["path",{d:"M14 2v4a2 2 0 0 0 2 2h4",key:"tnqrlb"}],["path",{d:"M10 9H8",key:"b1mrlr"}],["path",{d:"M16 13H8",key:"t4e002"}],["path",{d:"M16 17H8",key:"z1uh3a"}]]),c={list:t=>a.get("/disclosures",{params:t}).then(e=>e.data),getStats:(t=72)=>a.get("/disclosures/stats",{params:{hours:t}}).then(e=>e.data),getById:t=>a.get(`/disclosures/${t}`).then(e=>e.data),predictImpact:t=>a.get(`/disclosures/${t}/predict-impact`).then(e=>e.data)};export{r as F,c as d};
