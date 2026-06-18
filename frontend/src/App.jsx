import React, { useState, useEffect, useRef } from 'react';
import axios from 'axios';
import { 
  Play, Send, History, Loader2, AlertCircle, 
  Globe, FileText, Image as ImageIcon, Terminal, ExternalLink, CheckCircle
} from 'lucide-react';

const API_BASE = import.meta.env.VITE_API_URL;

function parseSSEEvents(text) {
  const events = [];
  const parts = text.split("\n\n");
  
  for (const part of parts) {
    if (!part.trim()) continue;
    
    let eventType = "message";
    let data = null;
    
    for (const line of part.split("\n")) {
      if (line.startsWith("event: ")) {
        eventType = line.slice(7);         
      } else if (line.startsWith("data: ")) {
        try {
          data = JSON.parse(line.slice(6));  
        } catch (e) {
          console.warn("SSE parse error:", line);
        }
      }
    }
    if (data) {
      events.push({ event: eventType, data });
    }
  }
  return events;
}

async function fetchSSE(url, options, onEvent) {
  const response = await fetch(url, options)
  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`HTTP ${response.status}: ${errorText}`);
  }
  
  const reader = response.body.getReader();
  
  const decoder = new TextDecoder();
  
  let buffer = "";
  
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    
    buffer += decoder.decode(value, { stream: true });
    
    const lastDoubleNewline = buffer.lastIndexOf("\n\n");
    if (lastDoubleNewline === -1) continue;
    
    const completePart = buffer.slice(0, lastDoubleNewline + 2);
    
    buffer = buffer.slice(lastDoubleNewline + 2);
    
    const events = parseSSEEvents(completePart);
    for (const { event, data } of events) {
      onEvent(event, data);
    }
  }
  
  if (buffer.trim()) {
    const events = parseSSEEvents(buffer);
    for (const { event, data } of events) {
      onEvent(event, data);
    }
  }
}

function App() {
  // Input states
  const [rootUrl, setRootUrl] = useState("");
  const [description, setDescription] = useState("");
  const [targetFile, setTargetFile] = useState(null);
  const [previewUrl, setPreviewUrl] = useState(null);

  // Status states
  const [loading, setLoading] = useState(false);
  const [logs, setLogs] = useState([]);
  const [threadId, setThreadId] = useState(null);
  const [needInput, setNeedInput] = useState(null);
  const [userInput, setUserInput] = useState("");
  const [historyList, setHistoryList] = useState([]);
  const [selectedTaskId, setSelectedTaskId] = useState(null);

  const logEndRef = useRef(null);

  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [logs]);

  useEffect(() => {
    fetchHistory();
  }, []);

  const fetchHistory = async () => {
    try {
      const res = await axios.get(`${API_BASE}/history`);
      setHistoryList(res.data);
    } catch (err) {
      console.error("History fetch failed:", err);
    }
  };

  const handleFileChange = (e) => {
    const file = e.target.files[0];
    setTargetFile(file);
    if (file) setPreviewUrl(URL.createObjectURL(file));
  };

  const processResponse = (data) => {
    const combinedLogs = data.log || [];
    setLogs(combinedLogs);

    if (data.status === "need_input") {
      setThreadId(data.thread_id);
      setNeedInput(data.message);
    } else {
      setThreadId(null);
      setNeedInput(null);
      setLoading(false);
      setUserInput("");
      setSelectedTaskId(null);
      fetchHistory();
    }
  };

  const urlToFile = async (url, filename) => {
    const response = await fetch(url);
    if (!response.ok) throw new Error(`Failed to fetch image: ${response.statusText}`);
    
    const blob = await response.blob();
    return new File([blob], filename, { type: blob.type });
  };

  const cleanFileName = (rawFilename) => {
   
    const uuidPattern = /[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}_/gi;
    
    return rawFilename.replace(uuidPattern, '');
  };

  const handleStart = async () => {
    if (!targetFile || !description || !rootUrl) return alert("Please fill all fields");
    
    setLoading(true);
    setLogs([{ role: 'system', content: 'Initializing Rebugger Agent...' }]);
    setNeedInput(null);
    setSelectedTaskId(null);

    const formData = new FormData();
    formData.append('bug_description', description);
    formData.append('target_screenshot', targetFile);
    formData.append('root_url', rootUrl);

    try {  
      await fetchSSE(
        `${API_BASE}/reproduce`,
        { method: "POST", body: formData },
        (eventType, data) => {
          switch (eventType) {
            case "log":
              setLogs(prev => [...prev, data]);
              break;
              
            case "need_input":
              setThreadId(data.thread_id);
              setNeedInput(data.message);
              setLoading(false);
              break;
              
            case "done":
              setLoading(false);
              fetchHistory();
              break;
              
            case "error":
              setLogs(prev => [...prev, { role: 'system', content: `Error: ${data.detail}` }]);
              setLoading(false);
              break;
          }
        }
      );
      setLoading(false);
      
    } catch (err) {
      setLogs(prev => [...prev, { role: 'system', content: `Error: ${err.message}` }]);
      setLoading(false);
    }
  };
  const handleResume = async () => {
    if (!userInput) return;
    setLoading(true);
    const currentMessage = needInput;
    setNeedInput(null);

    try {
      await fetchSSE(
        `${API_BASE}/reproduce/resume`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ thread_id: threadId, user_input: userInput })
        },
        (eventType, data) => {
          switch (eventType) {
            case "log":
              setLogs(prev => [...prev, data]);
              break;
            case "need_input":
              setThreadId(data.thread_id);
              setNeedInput(data.message);
              setLoading(false);
              break;
            case "done":
              setLoading(false);
              setUserInput("");
              setSelectedTaskId(null);
              fetchHistory();
              break;
            case "error":
              setLogs(prev => [...prev, { role: 'system', content: `Error: ${data.detail}` }]);
              setLoading(false);
              break;
          }
        }
      );
      
      setLoading(false);
      setUserInput("");
      
    } catch (err) {
      setNeedInput(currentMessage);
      setLogs(prev => [...prev, { role: 'system', content: 'Failed to resume agent: ' + err.message }]);
      setLoading(false);
    }
  };
  const selectTask = async (task) => {
    setSelectedTaskId(task.id);
    setLogs(task.actions || []);
    setDescription(task.bug_description);
    setRootUrl(task.root_url);
    const imageUrl = task.screenshot_path;
    if (imageUrl) {
      setPreviewUrl(imageUrl); 
      try {
        const rawFileName  = imageUrl.split('/').pop().split('?')[0]; 
        const originalFileName = cleanFileName(rawFileName);
        const file = await urlToFile(imageUrl, originalFileName);
        setTargetFile(file);
        console.log("Đã khôi phục file ảnh từ B2 thành công");
      } catch (e) {
        console.error("Lỗi tải ảnh từ B2 (Kiểm tra CORS):", e);
      }
    }
    setThreadId(task.thread_id);
    setLoading(false);
    
    if (task.status === 'need_input') {
      setNeedInput("This session is waiting for input. Provide data below.");
    } else {
      setNeedInput(null);
    }
  };

  return (
    <div className="flex h-screen bg-slate-950 text-slate-200 overflow-hidden font-sans">
      
      {/* SIDEBAR: HISTORY */}
      <aside className="w-80 bg-slate-900 border-r border-slate-800 flex flex-col">
        <div className="p-6 border-b border-slate-800 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <History className="text-blue-500" size={20} />
            <h2 className="font-bold text-lg text-white">History</h2>
          </div>
          <button onClick={fetchHistory} className="text-xs text-slate-500 hover:text-blue-400">Refresh</button>
        </div>
        <div className="flex-1 overflow-y-auto p-4 space-y-3 custom-scrollbar">
          {historyList.map((item) => (
            <div 
              key={item.id} 
              onClick={() => selectTask(item)}
              className={`p-3 rounded-xl border transition-all cursor-pointer group ${
                selectedTaskId === item.id ? 'bg-blue-600/10 border-blue-500' : 'bg-slate-800/40 border-slate-700 hover:border-slate-500'
              }`}
            >
              <div className="flex justify-between items-start mb-1">
                <span className="text-[9px] text-slate-500 font-bold uppercase">
                  {new Date(item.created_at).toLocaleDateString()}
                </span>
                <span className={`flex items-center gap-1 text-[8px] px-1.5 py-0.5 rounded border font-black uppercase ${
                  item.status === 'success' ? 'bg-emerald-900/40 text-emerald-400 border-emerald-500/30' : 
                  item.status === 'need_input' ? 'bg-amber-900/40 text-amber-400 border-amber-500/30' : 
                  item.status === 'running' ? 'bg-blue-900/40 text-blue-400 border-blue-500/30 animate-pulse' :
                  'bg-rose-900/40 text-rose-400 border-rose-500/30' 
                }`}>
                  {item.status === 'running' && <Loader2 size={8} className="animate-spin" />}
                  {item.status?.replace('_', ' ')}
                </span>
              </div>
              <p className="text-xs font-medium line-clamp-2 text-slate-300">{item.bug_description}</p>
            </div>
          ))}
        </div>
      </aside>

      {/* MAIN AREA */}
      <main className="flex-1 flex flex-col overflow-hidden">
        <header className="h-16 bg-slate-900/50 backdrop-blur-md border-b border-slate-800 flex items-center px-8 justify-between">
          <div className="flex items-center gap-2">
            <div className={`w-2.5 h-2.5 rounded-full ${loading ? 'bg-amber-500 animate-pulse' : 'bg-emerald-500'}`}></div>
            <h1 className="font-black uppercase tracking-widest text-xs text-white">AI Bug Rebugger</h1>
          </div>
          <button 
            onClick={() => {setSelectedTaskId(null); setLogs([]); setNeedInput(null); setDescription(""); setRootUrl(""); setTargetFile(null); setPreviewUrl(null); setLoading(false); setUserInput(""); }}
            className="text-[10px] bg-slate-800 px-3 py-1.5 rounded-lg hover:bg-slate-700 font-bold transition"
          >
            + NEW TASK
          </button>
        </header>

        <div className="flex-1 overflow-y-auto p-8 custom-scrollbar">
          <div className="max-w-6xl mx-auto grid grid-cols-12 gap-8">
            
            {/* LEFT: FORM */}
            <div className="col-span-12 lg:col-span-5 space-y-6">
              <section className="bg-slate-900 rounded-2xl p-6 border border-slate-800 shadow-2xl">
                <div className="space-y-5">
                  <div>
                    <label className="text-[10px] text-slate-500 uppercase font-black mb-1 block">Entry URL</label>
                    <div className="relative">
                      <Globe size={14} className="absolute left-3 top-3 text-slate-500" />
                      <input type="text" value={rootUrl} onChange={e => setRootUrl(e.target.value)} className="w-full bg-slate-950 border border-slate-700 rounded-xl py-2.5 pl-9 pr-4 text-sm focus:border-blue-500 outline-none transition" placeholder="https://app.test/login" />
                    </div>
                  </div>
                  <div>
                    <label className="text-[10px] text-slate-500 uppercase font-black mb-1 block">Bug Description</label>
                    <textarea value={description} onChange={e => setDescription(e.target.value)} className="w-full bg-slate-950 border border-slate-700 rounded-xl py-2.5 px-4 text-sm h-28 outline-none focus:border-blue-500 resize-none transition" placeholder="Describe what happens..." />
                  </div>
                  <div>
                    <label className="text-[10px] text-slate-500 uppercase font-black mb-1 block">Target State Screenshot</label>
                    <div className="mt-1 border-2 border-dashed border-slate-700 rounded-2xl p-4 text-center relative overflow-hidden h-40 flex flex-col items-center justify-center bg-slate-950/50 hover:border-blue-500 transition-colors group">
                      {previewUrl ? (
                        <img src={previewUrl} className="absolute inset-0 w-full h-full object-cover opacity-40 group-hover:opacity-20 transition" alt="Preview" />
                      ) : (
                        <ImageIcon className="text-slate-600 mb-2" size={32} />
                      )}
                      <span className="text-xs text-slate-500 relative z-10 font-medium">Click to upload image</span>
                      <input type="file" onChange={handleFileChange} className="absolute inset-0 opacity-0 cursor-pointer z-20" />
                    </div>
                  </div>
                  <button onClick={handleStart} disabled={loading} className="w-full bg-blue-600 hover:bg-blue-500 disabled:bg-slate-800 disabled:text-slate-600 py-4 rounded-xl font-black text-sm flex items-center justify-center gap-3 transition-all shadow-lg shadow-blue-900/20">
                    {loading ? <Loader2 className="animate-spin" size={18} /> : <Play size={18} fill="currentColor" />}
                    {loading ? 'AGENT PROCESSING' : 'RUN'}
                  </button>
                </div>
              </section>
            </div>

            {/* RIGHT: LOGS */}
            <div className="col-span-12 lg:col-span-7">
              <div className="bg-slate-900 rounded-2xl border border-slate-800 h-[700px] flex flex-col relative shadow-2xl">
                <div className="p-4 border-b border-slate-800 flex justify-between items-center bg-slate-900/50 backdrop-blur">
                  <div className="flex items-center gap-2">
                    <Terminal size={14} className="text-blue-400" />
                    <span className="text-[10px] font-black text-slate-400 uppercase tracking-widest">Execution Terminal</span>
                  </div>
                </div>

                <div className="flex-1 overflow-y-auto p-6 space-y-6 custom-scrollbar bg-slate-950/20">
                  {logs.length === 0 && (
                    <div className="h-full flex flex-col items-center justify-center text-slate-700 italic space-y-2">
                      <Terminal size={40} className="opacity-10" />
                      <p className="text-sm">Waiting for instructions...</p>
                    </div>
                  )}
                  {logs.map((log, i) => (
                    <div key={i} className="animate-in fade-in slide-in-from-left-2 duration-300">
                      <div className="flex items-center gap-2 mb-1.5">
                        <span className={`text-[8px] font-black px-1.5 py-0.5 rounded uppercase border ${
                            log.role === 'planner' ? 'bg-amber-900/20 text-amber-500 border-amber-500/30' :
                            log.role === 'executor' ? 'bg-emerald-900/20 text-emerald-500 border-emerald-500/30' :
                            log.role === 'critic' ? 'bg-indigo-900/20 text-indigo-400 border-indigo-500/30' :
                            log.role === 'critic_search' ? 'bg-sky-900/20 text-sky-400 border-sky-500/30' :  
                            'bg-slate-800 text-slate-500 border-slate-700'
                        }`}>
                          {log.role}
                        </span>
                      </div>
                      
                      {log.role === 'perception' ? (
                        <div className="relative group inline-block mt-1">
                          <img 
                            src={log.path} 
                            alt="Step" 
                            className="rounded-lg border border-slate-800 max-h-80 shadow-2xl cursor-zoom-in hover:border-blue-500 transition"
                            onClick={() => window.open(log.path, '_blank')}
                          />
                          <div className="absolute top-2 right-2 opacity-0 group-hover:opacity-100 transition bg-black/60 p-1.5 rounded-md backdrop-blur">
                            <ExternalLink size={12} className="text-white" />
                          </div>
                        </div>
                      )  : log.role === 'critic' ? (
                        <div className={`mt-1 p-3 rounded-lg border-l-4 shadow-sm ${
                          log.content.includes('APPROVED') 
                            ? 'bg-emerald-950/30 border-emerald-500/50 text-emerald-200' 
                            : log.content.includes('REJECTED')
                            ? 'bg-red-950/30 border-red-500/50 text-red-200'
                            : 'bg-indigo-950/30 border-indigo-500/50 text-indigo-200'
                        }`}>
                          <div className="flex items-start gap-2">
                            {log.content.includes('APPROVED') ? (
                              <CheckCircle size={16} className="text-emerald-500 mt-0.5 shrink-0" />
                            ) : (
                              <AlertCircle size={16} className="text-red-500 mt-0.5 shrink-0" />
                            )}
                            <div className="text-sm leading-relaxed italic">
                              {log.content}
                            </div>
                          </div>
                        </div>
                      ) : (
                        <div className="text-sm text-slate-300 leading-relaxed pl-3 border-l-2 border-slate-800 ml-1">
                          {log.content}
                        </div>
                      )}
                    </div>
                  ))}
                  <div ref={logEndRef} />
                </div>

                {needInput && (
                  <div className="p-6 bg-blue-600/10 border-t border-blue-500/30 backdrop-blur-xl rounded-b-2xl animate-in slide-in-from-bottom duration-500">
                    <div className="flex gap-4 items-start mb-4">
                      <div className="p-2 bg-blue-500 rounded-lg shadow-lg shadow-blue-500/40">
                        <AlertCircle className="text-white" size={20} />
                      </div>
                      <div className="flex-1">
                        <h4 className="font-black text-blue-400 text-[10px] uppercase tracking-tighter mb-1">Human Interaction Required</h4>
                        <p className="text-sm text-blue-100 font-medium">{needInput}</p>
                      </div>
                    </div>
                    <div className="flex gap-2">
                      <input 
                        autoFocus
                        className="flex-1 bg-slate-950 border border-blue-500/40 rounded-xl px-4 py-2.5 text-sm outline-none focus:border-blue-400 transition"
                        placeholder="Provide the missing information..."
                        value={userInput} onChange={e => setUserInput(e.target.value)}
                        onKeyPress={e => e.key === 'Enter' && handleResume()}
                      />
                      <button onClick={handleResume} className="bg-blue-500 hover:bg-blue-400 px-6 py-2.5 rounded-xl text-sm font-bold text-white transition flex items-center gap-2">
                        RESUME <Send size={14} />
                      </button>
                    </div>
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}

export default App;