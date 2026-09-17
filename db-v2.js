const DB_NAME='smart_coord_db';
const DB_VERSION=2;
export const STORES=['companies','projects','visits','recordings','issues','causes','improvements','kpis','hardwares','softwares','tasks','quotations'];
let dbPromise;
export function db(){
  if(!dbPromise) dbPromise=new Promise((resolve,reject)=>{
    const req=indexedDB.open(DB_NAME,DB_VERSION);
    req.onupgradeneeded=()=>{const d=req.result;for(const s of STORES){if(!d.objectStoreNames.contains(s))d.createObjectStore(s,{keyPath:'id',autoIncrement:true});}};
    req.onsuccess=()=>resolve(req.result);req.onerror=()=>reject(req.error);
  });
  return dbPromise;
}
export async function all(store){const d=await db();return new Promise((res,rej)=>{const r=d.transaction(store,'readonly').objectStore(store).getAll();r.onsuccess=()=>res(r.result);r.onerror=()=>rej(r.error);});}
export async function get(store,id){const d=await db();return new Promise((res,rej)=>{const r=d.transaction(store,'readonly').objectStore(store).get(Number(id));r.onsuccess=()=>res(r.result);r.onerror=()=>rej(r.error);});}
export async function put(store,obj){const d=await db();return new Promise((res,rej)=>{const os=d.transaction(store,'readwrite').objectStore(store);const payload={...obj,updated_at:new Date().toISOString()};if(!payload.id)delete payload.id;const r=os.put(payload);r.onsuccess=()=>res(r.result);r.onerror=()=>rej(r.error);});}
export async function remove(store,id){const d=await db();return new Promise((res,rej)=>{const r=d.transaction(store,'readwrite').objectStore(store).delete(Number(id));r.onsuccess=()=>res();r.onerror=()=>rej(r.error);});}
export async function clear(store){const d=await db();return new Promise((res,rej)=>{const r=d.transaction(store,'readwrite').objectStore(store).clear();r.onsuccess=()=>res();r.onerror=()=>rej(r.error);});}
export async function exportData(){const out={version:2,exported_at:new Date().toISOString(),stores:{}};for(const s of STORES){if(s==='recordings'){const rows=await all(s);out.stores[s]=rows.map(({blob,...rest})=>rest);}else out.stores[s]=await all(s);}return out;}
export async function importData(data){for(const s of STORES){await clear(s);for(const row of(data.stores?.[s]||[]))await put(s,row);}}
