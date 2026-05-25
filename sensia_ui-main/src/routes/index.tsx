import { createFileRoute } from "@tanstack/react-router";
import { useState, useRef, useEffect, useMemo, useCallback } from "react";
import {
  Mic, Send, Upload, Play, Pause, Volume2, Sparkles, Heart,
  History, Bookmark, Waves, Activity, Clock, TrendingUp,
  MessageCircle, FileAudio, Square, Plus, ChevronRight, Leaf,
  Pencil, Check, X, Trash2, BookmarkPlus, Loader2,
} from "lucide-react";
import {
  analyzeAudioFile,
  clearSession,
  createSession,
  fetchHealth,
  fetchTtsUrl,
  fetchTurns,
  sendChat,
  sendMicAudio,
  turnsToMessages,
  type GuardrailMeta,
} from "@/lib/api";
import { toast } from "sonner";

export const Route = createFileRoute("/")({
  component: TherapistApp,
  head: () => ({
    meta: [
      { title: "Sensia — Context-Aware Speaking Therapy" },
      { name: "description", content: "Sensia is a voice-based AI therapy companion that listens to tone, pace, and emotion to offer empathetic, context-aware support." },
      { property: "og:title", content: "Sensia — Context-Aware Speaking Therapy" },
      { property: "og:description", content: "Voice-based AI therapy companion with context-aware emotional support." },
      { property: "og:url", content: "/" },
    ],
    links: [{ rel: "canonical", href: "/" }],
  }),
});

type Msg = { id: number; role: "user" | "ai"; text: string; time: string };
type Session = {
  id: string;
  title: string;
  createdAt: number;
  updatedAt: number;
  messages: Msg[];
  saved: boolean;
};

const STORAGE_KEY = "sensia.sessions.v1";
const ACTIVE_KEY = "sensia.activeSession.v1";

const newId = () => crypto.randomUUID();
const fmtRel = (t: number) => {
  const diff = Date.now() - t;
  const m = Math.floor(diff / 60000);
  if (m < 1) return "just now";
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  const d = Math.floor(h / 24);
  return `${d}d ago`;
};

function TherapistApp() {
  const [sessions, setSessions] = useState<Session[]>([]);
  const [activeId, setActiveId] = useState<string>("");
  const [redisActive, setRedisActive] = useState<boolean | null>(null);
  const [loading, setLoading] = useState(false);
  const [bootstrapped, setBootstrapped] = useState(false);

  const [input, setInput] = useState("");
  const [recording, setRecording] = useState(false);
  const [recTime, setRecTime] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [ttsLoading, setTtsLoading] = useState(false);
  const [ttsUrl, setTtsUrl] = useState<string | null>(null);
  const [lastReply, setLastReply] = useState("");
  const [audioFileName, setAudioFileName] = useState<string | null>(null);
  const [renamingId, setRenamingId] = useState<string | null>(null);
  const [draftTitle, setDraftTitle] = useState("");
  const [editHeader, setEditHeader] = useState(false);
  const [headerDraft, setHeaderDraft] = useState("");
  const scrollRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const ttsAudioRef = useRef<HTMLAudioElement>(null);
  const ttsGenerationRef = useRef(0);
  const ttsLoadingRef = useRef(false);

  const active = useMemo(() => sessions.find((s) => s.id === activeId) ?? sessions[0], [sessions, activeId]);
  const messages = active?.messages ?? [];

  const syncTurns = useCallback(async (sessionId: string) => {
    const turns = await fetchTurns(sessionId);
    const messages = turnsToMessages(turns);
    setSessions((all) =>
      all.map((s) =>
        s.id === sessionId ? { ...s, messages, updatedAt: Date.now() } : s,
      ),
    );
    if (turns.length > 0) {
      setLastReply(turns[turns.length - 1].bot);
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const health = await fetchHealth();
        if (!cancelled) setRedisActive(health.redis_active);
      } catch {
        if (!cancelled) setRedisActive(false);
        toast.error("Cannot reach Sensia API. Start the backend: uvicorn api_server:app --port 8000");
      }

      let list: Session[] = [];
      try {
        const raw = localStorage.getItem(STORAGE_KEY);
        if (raw) list = JSON.parse(raw) as Session[];
      } catch { /* noop */ }

      if (list.length === 0) {
        const { session_id } = await createSession();
        list = [{
          id: session_id,
          title: `New session · ${new Date().toLocaleDateString(undefined, { month: "short", day: "numeric" })}`,
          createdAt: Date.now(),
          updatedAt: Date.now(),
          messages: [],
          saved: false,
        }];
      }

      const storedActive = localStorage.getItem(ACTIVE_KEY);
      const active = list.some((s) => s.id === storedActive) ? storedActive! : list[0].id;

      if (!cancelled) {
        setSessions(list);
        setActiveId(active);
        setBootstrapped(true);
      }
    })();
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    if (!bootstrapped || !activeId) return;
    syncTurns(activeId).catch((e) => toast.error(String(e)));
  }, [activeId, bootstrapped, syncTurns]);

  useEffect(() => {
    if (!recording) return;
    const t = setInterval(() => setRecTime((s) => s + 1), 1000);
    return () => clearInterval(t);
  }, [recording]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages.length]);

  const updateActive = (updater: (s: Session) => Session) =>
    setSessions((all) => all.map((s) => (s.id === activeId ? updater(s) : s)));

  const notifyGuardrail = (meta: GuardrailMeta) => {
    if (!meta.guardrail_triggered) return;
    if (meta.guardrail_category === "crisis") {
      toast.warning("Crisis support information was shared.", { duration: 8000 });
    } else {
      toast.message("Outside session scope — emotional support only.");
    }
  };

  const send = async () => {
    if (!input.trim() || !active || loading) return;
    const text = input.trim();
    setInput("");
    setLoading(true);
    try {
      const res = await sendChat(active.id, text);
      notifyGuardrail(res);
      const messages = turnsToMessages(res.turns);
      updateActive((s) => ({ ...s, messages, updatedAt: Date.now() }));
      if (res.turns.length) setLastReply(res.turns[res.turns.length - 1].bot);
    } catch (e) {
      toast.error(String(e));
      setInput(text);
    } finally {
      setLoading(false);
    }
  };

  const newSession = async () => {
    setLoading(true);
    try {
      const { session_id } = await createSession();
      const s: Session = {
        id: session_id,
        title: `New session · ${new Date().toLocaleDateString(undefined, { month: "short", day: "numeric" })}`,
        createdAt: Date.now(),
        updatedAt: Date.now(),
        messages: [],
        saved: false,
      };
      setSessions((all) => [s, ...all]);
      setActiveId(s.id);
      setRenamingId(s.id);
      setDraftTitle(s.title);
    } catch (e) {
      toast.error(String(e));
    } finally {
      setLoading(false);
    }
  };

  const startRename = (s: Session) => { setRenamingId(s.id); setDraftTitle(s.title); };
  const commitRename = () => {
    if (!renamingId) return;
    const t = draftTitle.trim() || "Untitled session";
    setSessions((all) => all.map((s) => s.id === renamingId ? { ...s, title: t } : s));
    setRenamingId(null);
  };

  const toggleSave = (id: string) =>
    setSessions((all) => all.map((s) => s.id === id ? { ...s, saved: !s.saved } : s));

  const deleteSession = async (id: string) => {
    try {
      await clearSession(id);
    } catch {
      /* backend may already be empty */
    }
    setSessions((all) => {
      const next = all.filter((s) => s.id !== id);
      if (next.length === 0) {
        void newSession();
        return next;
      }
      if (id === activeId) setActiveId(next[0].id);
      return next;
    });
  };

  const startRecording = async () => {
    if (!active || loading) return;
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const recorder = new MediaRecorder(stream);
      audioChunksRef.current = [];
      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) audioChunksRef.current.push(e.data);
      };
      recorder.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop());
        const blob = new Blob(audioChunksRef.current, { type: "audio/wav" });
        if (!active || blob.size === 0) return;
        setLoading(true);
        try {
          const res = await sendMicAudio(active.id, blob);
          if (res.duplicate) {
            toast.message("Recording already sent — record again for a new message.");
          } else if (res.error === "no_speech") {
            toast.warning("No speech detected. Try again.");
          } else {
            notifyGuardrail(res);
            const messages = turnsToMessages(res.turns);
            updateActive((s) => ({ ...s, messages, updatedAt: Date.now() }));
            if (res.reply) setLastReply(res.reply);
          }
        } catch (e) {
          toast.error(String(e));
        } finally {
          setLoading(false);
        }
      };
      mediaRecorderRef.current = recorder;
      recorder.start();
      setRecording(true);
      setRecTime(0);
    } catch (e) {
      toast.error("Microphone access denied or unavailable.");
    }
  };

  const stopRecording = () => {
    mediaRecorderRef.current?.stop();
    mediaRecorderRef.current = null;
    setRecording(false);
  };

  const onAudioFile = async (file: File) => {
    if (!active || loading) return;
    setAudioFileName(file.name);
    setLoading(true);
    try {
      const res = await analyzeAudioFile(active.id, file);
      if (res.duplicate) {
        toast.message("This file was already analyzed in this session.");
      } else {
        notifyGuardrail(res);
        const messages = turnsToMessages(res.turns);
        updateActive((s) => ({ ...s, messages, updatedAt: Date.now() }));
        if (res.reply) setLastReply(res.reply);
        toast.success(`Audio analyzed${res.elapsed_seconds ? ` in ${res.elapsed_seconds}s` : ""}`);
      }
    } catch (e) {
      toast.error(String(e));
    } finally {
      setLoading(false);
    }
  };

  const revokeTtsUrl = useCallback(() => {
    setTtsUrl((prev) => {
      if (prev) URL.revokeObjectURL(prev);
      return null;
    });
  }, []);

  const stopTts = useCallback(() => {
    ttsGenerationRef.current += 1;
    const audio = ttsAudioRef.current;
    if (audio) {
      audio.pause();
      audio.removeAttribute("src");
      audio.load();
    }
    setPlaying(false);
    ttsLoadingRef.current = false;
    setTtsLoading(false);
  }, []);

  useEffect(() => {
    stopTts();
    revokeTtsUrl();
  }, [lastReply, activeId, stopTts, revokeTtsUrl]);

  useEffect(() => {
    const audio = ttsAudioRef.current;
    if (!audio) return;
    const onEnded = () => setPlaying(false);
    const onPause = () => {
      if (!audio.ended) setPlaying(false);
    };
    audio.addEventListener("ended", onEnded);
    audio.addEventListener("pause", onPause);
    return () => {
      audio.removeEventListener("ended", onEnded);
      audio.removeEventListener("pause", onPause);
    };
  }, []);

  useEffect(() => () => {
    ttsGenerationRef.current += 1;
    ttsAudioRef.current?.pause();
    setTtsUrl((prev) => {
      if (prev) URL.revokeObjectURL(prev);
      return null;
    });
  }, []);

  const toggleTtsPlayback = async () => {
    if (!active || !lastReply || loading || ttsLoadingRef.current) return;

    const audio = ttsAudioRef.current;
    if (!audio) return;

    if (!audio.paused) {
      audio.pause();
      setPlaying(false);
      return;
    }

    const hasSrc = Boolean(audio.src && audio.src !== window.location.href);
    if (hasSrc) {
      try {
        if (audio.ended || (Number.isFinite(audio.duration) && audio.currentTime >= audio.duration)) {
          audio.currentTime = 0;
        }
        await audio.play();
        setPlaying(true);
      } catch (e) {
        toast.error(String(e));
        setPlaying(false);
      }
      return;
    }

    const generation = ++ttsGenerationRef.current;
    ttsLoadingRef.current = true;
    setTtsLoading(true);
    try {
      revokeTtsUrl();
      const url = await fetchTtsUrl(active.id, lastReply);
      if (generation !== ttsGenerationRef.current) {
        URL.revokeObjectURL(url);
        return;
      }
      setTtsUrl(url);
      audio.src = url;
      audio.load();
      await audio.play();
      if (generation !== ttsGenerationRef.current) {
        audio.pause();
        return;
      }
      setPlaying(true);
    } catch (e) {
      if (generation === ttsGenerationRef.current) {
        toast.error(String(e));
        setPlaying(false);
      }
    } finally {
      if (generation === ttsGenerationRef.current) {
        ttsLoadingRef.current = false;
        setTtsLoading(false);
      }
    }
  };

  const commitHeaderRename = () => {
    const t = headerDraft.trim();
    if (t) updateActive((s) => ({ ...s, title: t }));
    setEditHeader(false);
  };

  const recent = sessions.filter((s) => !s.saved);
  const saved = sessions.filter((s) => s.saved);

  const fmtTime = (s: number) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;

  return (
    <div className="min-h-screen w-full bg-background text-foreground relative overflow-hidden">
      <audio ref={ttsAudioRef} className="hidden" playsInline preload="none" />
      <div className="absolute inset-0 -z-10" style={{ backgroundImage: "var(--aura-gradient)" }} />

      <div className="flex h-screen w-full">
        {/* Sidebar */}
        <aside className="hidden md:flex w-80 flex-col border-r border-border/60 bg-card/40 backdrop-blur-xl">
          <div className="px-5 py-5 border-b border-border/50 flex items-center gap-3">
            <div className="h-9 w-9 rounded-xl flex items-center justify-center text-primary-foreground" style={{ background: "linear-gradient(135deg, oklch(0.65 0.14 200), oklch(0.7 0.12 320))" }}>
              <Leaf className="h-4 w-4" />
            </div>
            <div>
              <p className="text-sm font-semibold tracking-tight">Sensia</p>
              <p className="text-[11px] text-muted-foreground">Context-aware speaking therapy</p>
            </div>
          </div>

          <button
            onClick={newSession}
            className="mx-4 mt-4 flex items-center justify-center gap-2 rounded-xl py-2.5 text-sm font-medium text-primary-foreground shadow-[var(--shadow-soft)] hover:opacity-95 transition"
            style={{ background: "linear-gradient(135deg, oklch(0.62 0.13 200), oklch(0.6 0.13 270))" }}
          >
            <Plus className="h-4 w-4" /> New session
          </button>

          <div className="mt-6 px-3 flex-1 overflow-y-auto space-y-6">
            <Section title="Active session">
              {active && (
                <div className="rounded-2xl p-3.5 border border-primary/30 bg-primary/5 shadow-[var(--shadow-soft)]">
                  <div className="flex items-center justify-between">
                    <p className="text-[10px] uppercase tracking-wider text-primary/80 font-medium">Resume Session ID</p>
                    {active.saved && <Bookmark className="h-3 w-3 fill-primary text-primary" />}
                  </div>
                  <p className="text-sm font-mono mt-1 truncate">{active.id}</p>
                  <p className="text-sm font-medium mt-1.5 truncate">{active.title}</p>
                  <div className="mt-2 flex items-center justify-between">
                    <span className="flex items-center gap-1.5 text-[11px] text-primary">
                      <span className="h-1.5 w-1.5 rounded-full bg-primary animate-pulse" /> in progress
                    </span>
                    <span className="text-[11px] text-muted-foreground">{active.messages.length} msgs</span>
                  </div>
                </div>
              )}
            </Section>

            <Section title="Conversation history" icon={<History className="h-3.5 w-3.5" />}>
              {recent.length === 0 && <EmptyHint text="No recent sessions." />}
              {recent.map((s) => (
                <SessionCard
                  key={s.id}
                  session={s}
                  active={s.id === activeId}
                  renaming={renamingId === s.id}
                  draft={draftTitle}
                  setDraft={setDraftTitle}
                  onResume={() => setActiveId(s.id)}
                  onRename={() => startRename(s)}
                  onCommitRename={commitRename}
                  onCancelRename={() => setRenamingId(null)}
                  onSave={() => toggleSave(s.id)}
                  onDelete={() => deleteSession(s.id)}
                />
              ))}
            </Section>

            <Section title="Saved conversations" icon={<Bookmark className="h-3.5 w-3.5" />}>
              {saved.length === 0 && <EmptyHint text="Bookmark a session to save it here." />}
              {saved.map((s) => (
                <SessionCard
                  key={s.id}
                  session={s}
                  active={s.id === activeId}
                  renaming={renamingId === s.id}
                  draft={draftTitle}
                  setDraft={setDraftTitle}
                  onResume={() => setActiveId(s.id)}
                  onRename={() => startRename(s)}
                  onCommitRename={commitRename}
                  onCancelRename={() => setRenamingId(null)}
                  onSave={() => toggleSave(s.id)}
                  onDelete={() => deleteSession(s.id)}
                />
              ))}
            </Section>

            {audioFileName && (
              <Section title="Last audio" icon={<Waves className="h-3.5 w-3.5" />}>
                <SidebarRow title={audioFileName} subtitle="Analyzed via voice pipeline" />
              </Section>
            )}
          </div>

          <div className="p-4 border-t border-border/50 text-[11px] text-muted-foreground space-y-1">
            <p>
              Context:{" "}
              <span className={redisActive ? "text-emerald-600" : "text-amber-600"}>
                {redisActive === null ? "…" : redisActive ? "Redis" : "In-memory fallback"}
              </span>
            </p>
            <p>Session titles saved locally; messages on the server.</p>
          </div>
        </aside>

        {/* Main */}
        <main className="flex-1 flex min-w-0">
          {/* Center chat */}
          <section className="flex-1 flex flex-col min-w-0">
            <header className="px-6 lg:px-10 py-5 border-b border-border/60 backdrop-blur-xl bg-card/30 flex items-center justify-between gap-4">
              <div className="min-w-0 flex-1">
                {editHeader ? (
                  <div className="flex items-center gap-2">
                    <input
                      autoFocus
                      value={headerDraft}
                      onChange={(e) => setHeaderDraft(e.target.value)}
                      onKeyDown={(e) => { if (e.key === "Enter") commitHeaderRename(); if (e.key === "Escape") setEditHeader(false); }}
                      className="text-lg font-semibold tracking-tight bg-transparent border-b border-primary/40 outline-none focus:border-primary px-1 py-0.5 min-w-0 flex-1 max-w-md"
                    />
                    <button onClick={commitHeaderRename} className="h-7 w-7 rounded-md hover:bg-muted inline-flex items-center justify-center text-primary"><Check className="h-4 w-4" /></button>
                    <button onClick={() => setEditHeader(false)} className="h-7 w-7 rounded-md hover:bg-muted inline-flex items-center justify-center text-muted-foreground"><X className="h-4 w-4" /></button>
                  </div>
                ) : (
                  <button
                    onClick={() => { setEditHeader(true); setHeaderDraft(active?.title ?? ""); }}
                    className="group flex items-center gap-2 text-left max-w-full"
                  >
                    <h1 className="text-lg font-semibold tracking-tight truncate">{active?.title ?? "Untitled session"}</h1>
                    <Pencil className="h-3.5 w-3.5 text-muted-foreground opacity-0 group-hover:opacity-100 transition" />
                  </button>
                )}
                <p className="text-xs text-muted-foreground mt-0.5 flex items-center gap-2">
                  <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
                  {active ? `${active.id} · updated ${fmtRel(active.updatedAt)}` : "—"}
                </p>
              </div>
              <div className="flex items-center gap-2 shrink-0">
                <button
                  onClick={() => active && toggleSave(active.id)}
                  className={`inline-flex items-center gap-1.5 text-[11px] px-2.5 py-1.5 rounded-full border transition ${active?.saved ? "bg-primary/10 border-primary/30 text-primary" : "bg-muted/60 border-border/50 text-muted-foreground hover:text-foreground"}`}
                >
                  {active?.saved ? <><Bookmark className="h-3 w-3 fill-current" /> Saved</> : <><BookmarkPlus className="h-3 w-3" /> Save</>}
                </button>
                <Pill icon={<Heart className="h-3 w-3" />} label="Empathetic" />
                <Pill icon={<Sparkles className="h-3 w-3" />} label="Voice-aware" />
              </div>
            </header>

            <div ref={scrollRef} className="flex-1 overflow-y-auto px-6 lg:px-10 py-8 space-y-6">
              {messages.length === 0 ? (
                <div className="h-full flex flex-col items-center justify-center text-center gap-3 py-16">
                  <div className="h-14 w-14 rounded-2xl flex items-center justify-center text-primary-foreground shadow-[var(--shadow-soft)]" style={{ background: "linear-gradient(135deg, oklch(0.65 0.14 200), oklch(0.7 0.12 320))" }}>
                    <Leaf className="h-6 w-6" />
                  </div>
                  <p className="text-sm font-medium">This session is fresh.</p>
                  <p className="text-xs text-muted-foreground max-w-xs">Start by writing or speaking how you're feeling — Sensia listens to tone, pace, and pauses.</p>
                </div>
              ) : (
                messages.map((m) => <Bubble key={m.id} m={m} />)
              )}
            </div>

            {/* Composer */}
            <div className="px-6 lg:px-10 pb-6">
              <div className="rounded-3xl border border-border/60 bg-card/70 backdrop-blur-xl shadow-[var(--shadow-soft)] p-3">
                <textarea
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } }}
                  placeholder="Talk about how you're feeling…"
                  className="w-full resize-none bg-transparent px-3 py-2 text-sm outline-none placeholder:text-muted-foreground min-h-[56px] max-h-40"
                />
                <div className="flex items-center justify-between px-1">
                  <div className="flex items-center gap-1.5">
                    <input
                      ref={fileInputRef}
                      type="file"
                      accept=".wav,.mp3,.m4a,audio/*"
                      className="hidden"
                      onChange={(e) => {
                        const f = e.target.files?.[0];
                        if (f) void onAudioFile(f);
                        e.target.value = "";
                      }}
                    />
                    <IconBtn title="Upload audio" onClick={() => fileInputRef.current?.click()}>
                      <Upload className="h-4 w-4" />
                    </IconBtn>
                    <button
                      onClick={() => (recording ? stopRecording() : void startRecording())}
                      disabled={loading}
                      className={`h-9 px-3 rounded-full inline-flex items-center gap-2 text-xs font-medium transition ${recording ? "bg-rose-500/15 text-rose-600" : "hover:bg-muted text-muted-foreground"}`}
                    >
                      {recording ? <><Square className="h-3.5 w-3.5 fill-current" /> {fmtTime(recTime)}</> : <><Mic className="h-3.5 w-3.5" /> Hold to speak</>}
                    </button>
                  </div>
                  <button
                    onClick={() => void send()}
                    disabled={!input.trim() || loading}
                    className="h-9 w-9 rounded-full inline-flex items-center justify-center text-primary-foreground disabled:opacity-40 transition hover:scale-105"
                    style={{ background: "linear-gradient(135deg, oklch(0.62 0.13 200), oklch(0.6 0.13 270))" }}
                  >
                    {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
                  </button>
                </div>
              </div>
            </div>
          </section>

          {/* Right insights panel */}
          <aside className="hidden xl:flex w-[360px] flex-col border-l border-border/60 bg-card/30 backdrop-blur-xl overflow-y-auto">
            <div className="p-6 space-y-6">
              {/* Audio panel */}
              <Card>
                <CardHeader icon={<FileAudio className="h-4 w-4" />} title="Audio interaction" subtitle="Upload or record" />
                <div
                  className="mt-3 rounded-2xl border border-dashed border-border/70 p-4 text-center cursor-pointer hover:bg-muted/30 transition"
                  onClick={() => fileInputRef.current?.click()}
                >
                  <Upload className="h-5 w-5 mx-auto text-muted-foreground" />
                  <p className="text-xs text-muted-foreground mt-2">
                    Drop a voice note or <span className="text-primary underline-offset-2 hover:underline">browse</span>
                  </p>
                  <p className="text-[10px] text-muted-foreground mt-1">.wav · .mp3 · .m4a</p>
                </div>

                {audioFileName && (
                  <div className="mt-3 rounded-2xl bg-muted/50 p-3">
                    <p className="text-xs font-medium truncate mb-2">{audioFileName}</p>
                    <Waveform />
                  </div>
                )}
              </Card>

              {/* Emotion panel */}
              <Card>
                <CardHeader icon={<Activity className="h-4 w-4" />} title="Speech & emotion" subtitle="From the last 90 seconds" />
                <div className="mt-4 space-y-3">
                  <Indicator label="Emotional tone" value="Reflective · slightly tense" pct={62} hue={200} />
                  <Indicator label="Speech pace" value="92 wpm · steady" pct={48} hue={170} />
                  <Indicator label="Pause pattern" value="Frequent · thoughtful" pct={70} hue={280} />
                  <Indicator label="Confidence" value="Medium" pct={55} hue={320} />
                </div>
                <div className="mt-4 flex flex-wrap gap-1.5">
                  {["overwhelm", "tired", "hopeful", "self-aware"].map((t) => (
                    <span key={t} className="text-[10px] px-2 py-1 rounded-full bg-accent/40 text-accent-foreground">{t}</span>
                  ))}
                </div>
              </Card>

              {/* TTS reply */}
              <Card>
                <CardHeader icon={<Volume2 className="h-4 w-4" />} title="AI response" subtitle="Read reply aloud" />
                <p className="mt-3 text-sm leading-relaxed text-foreground/90">
                  {lastReply ? `"${lastReply.slice(0, 280)}${lastReply.length > 280 ? "…" : ""}"` : "Send a message to hear the therapist reply."}
                </p>
                <div className="mt-4 rounded-2xl bg-muted/50 p-3 flex items-center gap-3">
                  <button
                    type="button"
                    onClick={() => void toggleTtsPlayback()}
                    disabled={!lastReply || loading || ttsLoading}
                    aria-label={playing ? "Pause reply" : "Play reply aloud"}
                    className="h-10 w-10 rounded-full inline-flex items-center justify-center text-primary-foreground shrink-0 disabled:opacity-40"
                    style={{ background: "linear-gradient(135deg, oklch(0.62 0.13 200), oklch(0.6 0.13 270))" }}
                  >
                    {ttsLoading ? (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    ) : playing ? (
                      <Pause className="h-4 w-4" />
                    ) : (
                      <Play className="h-4 w-4 ml-0.5" />
                    )}
                  </button>
                  <div className="flex-1 min-w-0">
                    <div className="h-1.5 rounded-full bg-border overflow-hidden">
                      <div className="h-full rounded-full" style={{ width: playing ? "62%" : "20%", background: "linear-gradient(90deg, oklch(0.62 0.13 200), oklch(0.6 0.13 270))", transition: "width .4s" }} />
                    </div>
                    <div className="flex justify-between text-[10px] text-muted-foreground mt-1">
                      <span>0:08</span><span>0:24</span>
                    </div>
                  </div>
                </div>
              </Card>

              {/* Session insights */}
              <Card>
                <CardHeader icon={<TrendingUp className="h-4 w-4" />} title="Session insights" subtitle="This week" />
                <div className="mt-4 grid grid-cols-2 gap-3">
                  <Stat icon={<MessageCircle className="h-3.5 w-3.5" />} label="Continuity" value="4 sessions" />
                  <Stat icon={<Heart className="h-3.5 w-3.5" />} label="Mood trend" value="↑ steadier" />
                  <Stat icon={<Clock className="h-3.5 w-3.5" />} label="Avg length" value="14 min" />
                  <Stat icon={<Waves className="h-3.5 w-3.5" />} label="Voice notes" value="6 total" />
                </div>
                <div className="mt-4 pt-4 border-t border-border/60">
                  <p className="text-[11px] uppercase tracking-wider text-muted-foreground mb-2">Timeline</p>
                  <div className="space-y-2">
                    {["Today · evening reflection", "Yesterday · work stress", "Mon · sleep & rumination"].map((t) => (
                      <div key={t} className="flex items-center gap-2 text-xs text-foreground/80">
                        <span className="h-1.5 w-1.5 rounded-full bg-primary/60" />{t}
                      </div>
                    ))}
                  </div>
                </div>
              </Card>
            </div>
          </aside>
        </main>
      </div>
    </div>
  );
}

function Section({ title, icon, children }: { title: string; icon?: React.ReactNode; children: React.ReactNode }) {
  return (
    <div>
      <div className="px-2 mb-2 flex items-center gap-1.5 text-[10px] uppercase tracking-wider text-muted-foreground font-medium">
        {icon}{title}
      </div>
      <div className="space-y-1">{children}</div>
    </div>
  );
}

function SidebarRow({ title, subtitle, active }: { title: string; subtitle: string; active?: boolean }) {
  return (
    <button className={`w-full text-left rounded-xl px-3 py-2 transition group flex items-center justify-between ${active ? "bg-primary/8 text-foreground" : "hover:bg-muted/60 text-foreground/85"}`}>
      <div className="min-w-0">
        <p className="text-sm truncate">{title}</p>
        <p className="text-[11px] text-muted-foreground truncate">{subtitle}</p>
      </div>
      <ChevronRight className="h-3.5 w-3.5 text-muted-foreground opacity-0 group-hover:opacity-100 transition" />
    </button>
  );
}

function Bubble({ m }: { m: Msg }) {
  const isUser = m.role === "user";
  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"} animate-in fade-in slide-in-from-bottom-2 duration-300`}>
      <div className={`flex gap-3 max-w-[80%] ${isUser ? "flex-row-reverse" : ""}`}>
        {!isUser && (
          <div className="h-8 w-8 rounded-full shrink-0 flex items-center justify-center text-primary-foreground shadow-[var(--shadow-soft)]" style={{ background: "linear-gradient(135deg, oklch(0.65 0.14 200), oklch(0.7 0.12 320))" }}>
            <Leaf className="h-3.5 w-3.5" />
          </div>
        )}
        <div>
          <div
            className={`rounded-3xl px-5 py-3.5 text-[15px] leading-relaxed ${isUser
              ? "text-primary-foreground rounded-br-md"
              : "bg-card/80 backdrop-blur border border-border/60 rounded-bl-md text-foreground"}`}
            style={isUser ? { background: "linear-gradient(135deg, oklch(0.62 0.13 200), oklch(0.6 0.13 270))" } : undefined}
          >
            {m.text}
          </div>
          <p className={`text-[10px] text-muted-foreground mt-1.5 px-2 ${isUser ? "text-right" : ""}`}>{m.time}</p>
        </div>
      </div>
    </div>
  );
}

function Pill({ icon, label }: { icon: React.ReactNode; label: string }) {
  return (
    <span className="inline-flex items-center gap-1.5 text-[11px] px-2.5 py-1 rounded-full bg-muted/60 text-muted-foreground border border-border/50">
      {icon}{label}
    </span>
  );
}

function IconBtn({ children, title, onClick }: { children: React.ReactNode; title: string; onClick?: () => void }) {
  return (
    <button type="button" title={title} onClick={onClick} className="h-9 w-9 rounded-full inline-flex items-center justify-center text-muted-foreground hover:bg-muted hover:text-foreground transition">
      {children}
    </button>
  );
}

function Card({ children }: { children: React.ReactNode }) {
  return <div className="rounded-2xl border border-border/60 bg-card/70 backdrop-blur p-5 shadow-[var(--shadow-soft)]">{children}</div>;
}

function CardHeader({ icon, title, subtitle }: { icon: React.ReactNode; title: string; subtitle: string }) {
  return (
    <div className="flex items-start gap-3">
      <div className="h-8 w-8 rounded-lg bg-primary/10 text-primary inline-flex items-center justify-center shrink-0">{icon}</div>
      <div>
        <p className="text-sm font-semibold tracking-tight">{title}</p>
        <p className="text-[11px] text-muted-foreground">{subtitle}</p>
      </div>
    </div>
  );
}

function Indicator({ label, value, pct, hue }: { label: string; value: string; pct: number; hue: number }) {
  return (
    <div>
      <div className="flex justify-between text-xs mb-1.5">
        <span className="text-muted-foreground">{label}</span>
        <span className="text-foreground/90">{value}</span>
      </div>
      <div className="h-1.5 rounded-full bg-muted overflow-hidden">
        <div className="h-full rounded-full" style={{ width: `${pct}%`, background: `linear-gradient(90deg, oklch(0.7 0.12 ${hue}), oklch(0.6 0.14 ${hue + 40}))` }} />
      </div>
    </div>
  );
}

function Stat({ icon, label, value }: { icon: React.ReactNode; label: string; value: string }) {
  return (
    <div className="rounded-xl bg-muted/40 p-3">
      <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-wider text-muted-foreground">{icon}{label}</div>
      <p className="text-sm font-semibold mt-1">{value}</p>
    </div>
  );
}

function Waveform() {
  const bars = Array.from({ length: 40 }, (_, i) => 20 + Math.sin(i * 0.7) * 18 + Math.random() * 14);
  return (
    <div className="flex items-center gap-[2px] h-10">
      {bars.map((h, i) => (
        <div key={i} className="flex-1 rounded-full" style={{ height: `${Math.min(100, h)}%`, background: `linear-gradient(180deg, oklch(0.7 0.12 200), oklch(0.6 0.13 280))`, opacity: 0.4 + (h / 100) * 0.6 }} />
      ))}
    </div>
  );
}

function EmptyHint({ text }: { text: string }) {
  return <p className="px-3 py-2 text-[11px] text-muted-foreground italic">{text}</p>;
}

function SessionCard({
  session, active, renaming, draft, setDraft,
  onResume, onRename, onCommitRename, onCancelRename, onSave, onDelete,
}: {
  session: Session;
  active: boolean;
  renaming: boolean;
  draft: string;
  setDraft: (v: string) => void;
  onResume: () => void;
  onRename: () => void;
  onCommitRename: () => void;
  onCancelRename: () => void;
  onSave: () => void;
  onDelete: () => void;
}) {
  const preview = session.messages[session.messages.length - 1]?.text ?? "No messages yet";
  return (
    <div
      className={`group rounded-2xl p-3 border transition cursor-pointer ${
        active
          ? "border-primary/40 bg-primary/8 shadow-[var(--shadow-soft)]"
          : "border-border/50 bg-card/50 hover:bg-card/80 hover:border-border"
      }`}
      onClick={() => !renaming && onResume()}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          {renaming ? (
            <div className="flex items-center gap-1" onClick={(e) => e.stopPropagation()}>
              <input
                autoFocus
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") onCommitRename();
                  if (e.key === "Escape") onCancelRename();
                }}
                className="flex-1 min-w-0 text-sm font-medium bg-background/80 border border-primary/40 rounded-md px-2 py-1 outline-none focus:border-primary"
              />
              <button onClick={onCommitRename} className="h-6 w-6 rounded-md hover:bg-muted inline-flex items-center justify-center text-primary"><Check className="h-3.5 w-3.5" /></button>
              <button onClick={onCancelRename} className="h-6 w-6 rounded-md hover:bg-muted inline-flex items-center justify-center text-muted-foreground"><X className="h-3.5 w-3.5" /></button>
            </div>
          ) : (
            <>
              <div className="flex items-center gap-1.5">
                {session.saved && <Bookmark className="h-3 w-3 fill-primary text-primary shrink-0" />}
                <p className="text-sm font-medium truncate">{session.title}</p>
              </div>
              <p className="text-[11px] text-muted-foreground truncate mt-0.5">{preview}</p>
              <div className="flex items-center gap-2 mt-1.5 text-[10px] text-muted-foreground">
                <span className="font-mono">{session.id}</span>
                <span>·</span>
                <span>{fmtRel(session.updatedAt)}</span>
                <span>·</span>
                <span>{session.messages.length} msgs</span>
              </div>
            </>
          )}
        </div>
        {active && !renaming && <span className="h-1.5 w-1.5 rounded-full bg-primary animate-pulse mt-1.5 shrink-0" />}
      </div>

      {!renaming && (
        <div className="mt-2 pt-2 border-t border-border/40 flex items-center gap-1 opacity-0 group-hover:opacity-100 transition" onClick={(e) => e.stopPropagation()}>
          <CardAction icon={<ChevronRight className="h-3 w-3" />} label="Resume" onClick={onResume} primary />
          <CardAction icon={<Pencil className="h-3 w-3" />} label="Rename" onClick={onRename} />
          <CardAction
            icon={<Bookmark className={`h-3 w-3 ${session.saved ? "fill-current" : ""}`} />}
            label={session.saved ? "Unsave" : "Save"}
            onClick={onSave}
          />
          <button
            onClick={onDelete}
            className="ml-auto h-6 w-6 rounded-md inline-flex items-center justify-center text-muted-foreground hover:text-rose-500 hover:bg-rose-500/10 transition"
            title="Delete session"
          >
            <Trash2 className="h-3 w-3" />
          </button>
        </div>
      )}
    </div>
  );
}

function CardAction({ icon, label, onClick, primary }: { icon: React.ReactNode; label: string; onClick: () => void; primary?: boolean }) {
  return (
    <button
      onClick={onClick}
      className={`inline-flex items-center gap-1 px-2 py-1 rounded-md text-[10px] font-medium transition ${
        primary ? "text-primary hover:bg-primary/10" : "text-muted-foreground hover:bg-muted hover:text-foreground"
      }`}
    >
      {icon}{label}
    </button>
  );
}
