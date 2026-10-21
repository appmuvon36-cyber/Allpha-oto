"use client";
import {useEffect,useState} from "react";
import {Download,Smartphone,X} from "lucide-react";
type InstallEvent=Event&{prompt:()=>Promise<void>;userChoice:Promise<{outcome:"accepted"|"dismissed";platform:string}>};
export function PwaInstallPrompt(){const [promptEvent,setPromptEvent]=useState<InstallEvent|null>(null);const [help,setHelp]=useState(false);const [installed,setInstalled]=useState(false);
useEffect(()=>{const before=(e:Event)=>{e.preventDefault();setPromptEvent(e as InstallEvent)};const done=()=>{setInstalled(true);setHelp(false)};if(window.matchMedia("(display-mode: standalone)").matches||(navigator as Navigator&{standalone?:boolean}).standalone)setInstalled(true);window.addEventListener("beforeinstallprompt",before);window.addEventListener("appinstalled",done);if("serviceWorker" in navigator)void navigator.serviceWorker.register("/sw.js").catch(()=>{});return()=>{window.removeEventListener("beforeinstallprompt",before);window.removeEventListener("appinstalled",done)}},[]);
if(installed)return null;
const click=async()=>{if(promptEvent){await promptEvent.prompt();const result=await promptEvent.userChoice;if(result.outcome==="accepted")setInstalled(true);setPromptEvent(null)}else setHelp(v=>!v)};
return <div className="pwa-install-wrap"><button className="pwa-install-button" onClick={()=>void click()}><Download size={15}/><span>Install App</span></button>{help&&<div className="pwa-install-help" role="dialog" aria-label="Petunjuk instalasi"><button className="pwa-help-close" onClick={()=>setHelp(false)} aria-label="Tutup"><X size={15}/></button><Smartphone size={21}/><strong>Pasang OtoClinic</strong><p>Android/Chrome: buka menu ⋮ lalu pilih <b>Install app</b> atau <b>Tambahkan ke layar utama</b>.</p><p>iPhone/Safari: tekan <b>Bagikan</b>, lalu <b>Tambahkan ke Layar Utama</b>.</p></div>}</div>}




/** Short, once-per-tab intro using the approved OtoClinic splash artwork. */
export function PwaSplashIntro(){
  const [visible,setVisible]=useState(false);
  const [closing,setClosing]=useState(false);
  useEffect(()=>{
    let closeTimer:number|undefined;
    let hideTimer:number|undefined;
    try{
      if(window.sessionStorage.getItem("otoclinic-splash-seen")==="1")return;
      setVisible(true);
      closeTimer=window.setTimeout(()=>setClosing(true),1450);
      hideTimer=window.setTimeout(()=>{
        try{window.sessionStorage.setItem("otoclinic-splash-seen","1")}catch{}
        setVisible(false);
      },1800);
    }catch{
      setVisible(false);
    }
    return ()=>{
      if(closeTimer)window.clearTimeout(closeTimer);
      if(hideTimer)window.clearTimeout(hideTimer);
    };
  },[]);
  if(!visible)return null;
  const dismiss=()=>{
    try{window.sessionStorage.setItem("otoclinic-splash-seen","1")}catch{}
    setClosing(false);
    setVisible(false);
  };
  return <div className={"pwa-splash-intro"+(closing?" is-closing":"")} role="status" aria-label="Memuat OtoClinic">
    <div className="pwa-splash-orbit pwa-splash-orbit-one" aria-hidden="true"/>
    <div className="pwa-splash-orbit pwa-splash-orbit-two" aria-hidden="true"/>
    <div className="pwa-splash-art-wrap">
      <img src="/images/otoclinic-splash-art.jpg" alt="" fetchPriority="high" decoding="async"/>
    </div>
    <strong className="pwa-splash-brand">OtoClinic</strong>
    <span className="pwa-splash-tagline">Spare part otomotif</span>
    <div className="pwa-splash-progress" aria-hidden="true"><span/></div>
    <button type="button" className="pwa-splash-skip" onClick={dismiss}>Lewati</button>
  </div>;
}
