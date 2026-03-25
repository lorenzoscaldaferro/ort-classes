import { useState, useRef, useEffect } from "react";
import { Send, User, Copy, Check, Plus } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface Source {
  subject: string;
  subjectLabel: string;
  semester: string;
  title: string;
  date: string;
  excerpt: string;
  score: number;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  sources?: Source[];
}

// ---------------------------------------------------------------------------
// Subject color mapping
// ---------------------------------------------------------------------------

const SUBJECT_COLORS: Record<string, string> = {
  economia_y_gestion:    "bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300",
  business_intelligence: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300",
  contabilidad_y_costos: "bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300",
  project_management:    "bg-sky-100 text-sky-700 dark:bg-sky-900/40 dark:text-sky-300",
  ecommerce_y_servicios: "bg-rose-100 text-rose-700 dark:bg-rose-900/40 dark:text-rose-300",
  matematica_financiera: "bg-orange-100 text-orange-700 dark:bg-orange-900/40 dark:text-orange-300",
};

// ---------------------------------------------------------------------------
// Suggested questions
// ---------------------------------------------------------------------------

const SUGGESTED_QUESTIONS = [
  "¿Qué es business intelligence?",
  "Explicame el modelo Canvas",
  "¿Qué es la elasticidad precio?",
  "Resumen de project management",
];

// ---------------------------------------------------------------------------
// Source cards
// ---------------------------------------------------------------------------

function SourceCards({
  sources,
  onOpenTranscript,
}: {
  sources: Source[];
  onOpenTranscript?: (semester: string, subject: string, file: string, excerpt: string) => void;
}) {
  if (!sources.length) return null;
  return (
    <div className="mt-3 space-y-1.5">
      <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground/50 px-0.5">
        Fuentes
      </p>
      <div className="grid gap-1.5">
        {sources.map((s, i) => {
          const file = s.title
            ? s.title.endsWith(".md") ? s.title : `${s.title}.md`
            : "";
          const clickable = !!(onOpenTranscript && s.semester && s.subject && file);
          const inner = (
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-1.5 mb-1 flex-wrap">
                <span
                  className={`px-1.5 py-0.5 rounded-md text-[10px] font-semibold leading-none ${
                    SUBJECT_COLORS[s.subject] ?? "bg-zinc-100 text-zinc-600 dark:bg-zinc-800 dark:text-zinc-400"
                  }`}
                >
                  {s.subjectLabel || s.subject}
                </span>
                {s.date && (
                  <span className="text-muted-foreground/60">{s.date}</span>
                )}
                {clickable && (
                  <span className="ml-auto text-[9px] text-primary/50">Ver →</span>
                )}
              </div>
              <p className="text-muted-foreground leading-relaxed line-clamp-2">
                {s.excerpt}
              </p>
            </div>
          );

          if (clickable) {
            return (
              <button
                key={i}
                onClick={() => onOpenTranscript!(s.semester, s.subject, file, s.excerpt)}
                className="flex gap-2.5 p-2.5 rounded-xl bg-muted/30 border border-border/40 text-[11px] text-left w-full hover:bg-muted/60 hover:border-primary/30 transition-colors cursor-pointer"
              >
                {inner}
              </button>
            );
          }
          return (
            <div
              key={i}
              className="flex gap-2.5 p-2.5 rounded-xl bg-muted/30 border border-border/40 text-[11px]"
            >
              {inner}
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Rich markdown renderer
// ---------------------------------------------------------------------------

function RichContent({ content }: { content: string }) {
  const lines = content.split("\n");
  const elements: JSX.Element[] = [];
  let listBuffer: { num?: string; text: string }[] = [];
  let keyIdx = 0;

  const flushList = () => {
    if (listBuffer.length === 0) return;
    const isNumbered = listBuffer[0].num !== undefined;
    elements.push(
      <div key={`list-${keyIdx++}`} className={`space-y-2.5 my-2 ${isNumbered ? "" : "ml-1"}`}>
        {listBuffer.map((item, i) => (
          <div key={i} className="flex gap-2">
            {isNumbered ? (
              <span className="text-[11px] font-bold text-primary bg-primary/10 h-5 w-5 rounded-full flex items-center justify-center shrink-0 mt-0.5">
                {item.num}
              </span>
            ) : (
              <span className="text-primary/60 mt-1 shrink-0">•</span>
            )}
            <span className="text-[13px] leading-relaxed">{renderInline(item.text)}</span>
          </div>
        ))}
      </div>
    );
    listBuffer = [];
  };

  const renderInline = (text: string): JSX.Element[] => {
    const parts: JSX.Element[] = [];
    const regex = /(\*\*[^*]+\*\*|\[([^\]]+)\]\(([^)]+)\))/g;
    let lastIndex = 0;
    let match;
    let k = 0;
    while ((match = regex.exec(text)) !== null) {
      if (match.index > lastIndex) {
        parts.push(<span key={`s${k++}`}>{text.slice(lastIndex, match.index)}</span>);
      }
      if (match[0].startsWith("**")) {
        parts.push(
          <strong key={`b${k++}`} className="font-semibold text-foreground">
            {match[0].slice(2, -2)}
          </strong>
        );
      } else if (match[2] && match[3]) {
        parts.push(
          <a key={`a${k++}`} href={match[3]} target="_blank" rel="noopener noreferrer"
            className="text-primary hover:underline underline-offset-2 transition-colors">
            {match[2]}
          </a>
        );
      }
      lastIndex = match.index + match[0].length;
    }
    if (lastIndex < text.length) {
      parts.push(<span key={`s${k++}`}>{text.slice(lastIndex)}</span>);
    }
    return parts;
  };

  for (const line of lines) {
    const trimmed = line.trim();
    if (!trimmed) { flushList(); continue; }
    const numMatch = trimmed.match(/^(\d+)[.)]\s+(.+)/);
    if (numMatch) {
      if (listBuffer.length > 0 && listBuffer[0].num === undefined) flushList();
      listBuffer.push({ num: numMatch[1], text: numMatch[2] });
      continue;
    }
    const bulletMatch = trimmed.match(/^[-*]\s+(.+)/);
    if (bulletMatch) {
      if (listBuffer.length > 0 && listBuffer[0].num !== undefined) flushList();
      listBuffer.push({ text: bulletMatch[1] });
      continue;
    }
    flushList();
    elements.push(
      <p key={`p-${keyIdx++}`} className="text-[13px] leading-relaxed">
        {renderInline(trimmed)}
      </p>
    );
  }
  flushList();
  return <div className="space-y-1.5">{elements}</div>;
}

// ---------------------------------------------------------------------------
// Typing indicator
// ---------------------------------------------------------------------------

function TypingIndicator() {
  return (
    <div className="flex gap-2.5">
      <div className="h-8 w-8 rounded-full shrink-0 mt-0.5 ring-2 ring-primary/20 bg-primary/10 flex items-center justify-center">
        <span className="text-sm">🎓</span>
      </div>
      <div className="space-y-2 flex-1 max-w-[88%]">
        <motion.div
          initial={{ opacity: 0, scale: 0.9 }}
          animate={{ opacity: 1, scale: 1 }}
          className="px-4 py-3 rounded-xl bg-card border border-border inline-flex items-center gap-2"
        >
          <div className="flex items-center gap-1">
            {[0, 1, 2].map((i) => (
              <motion.div
                key={i}
                className="h-2 w-2 rounded-full bg-primary"
                animate={{ y: [0, -6, 0], opacity: [0.4, 1, 0.4] }}
                transition={{ duration: 0.8, repeat: Infinity, delay: i * 0.2, ease: "easeInOut" }}
              />
            ))}
          </div>
          <motion.span
            className="text-[11px] text-muted-foreground ml-1"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.5 }}
          >
            Buscando en tus clases...
          </motion.span>
        </motion.div>
        <motion.div
          initial={{ opacity: 0, y: 6 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.3 }}
          className="px-4 py-4 rounded-xl bg-card border border-border space-y-3"
        >
          <div className="h-2.5 rounded-full bg-muted-foreground/10 w-[90%] animate-pulse" />
          <div className="h-2.5 rounded-full bg-muted-foreground/10 w-[70%] animate-pulse" style={{ animationDelay: "0.15s" }} />
          <div className="h-2.5 rounded-full bg-muted-foreground/10 w-[50%] animate-pulse" style={{ animationDelay: "0.3s" }} />
        </motion.div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// ChatView
// ---------------------------------------------------------------------------

interface ChatViewProps {
  messages: ChatMessage[];
  onMessagesChange: (msgs: ChatMessage[]) => void;
  onOpenTranscript?: (semester: string, subject: string, file: string, excerpt: string) => void;
}

export function ChatView({ messages, onMessagesChange, onOpenTranscript }: ChatViewProps) {
  const setMessages = onMessagesChange;
  const [input, setInput] = useState("");
  const [isTyping, setIsTyping] = useState(false);
  const [copied, setCopied] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isTyping]);

  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "40px";
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
  }, [input]);

  const handleSend = async (text?: string) => {
    const messageText = (text || input).trim();
    if (!messageText || isTyping) return;

    const userMsg: ChatMessage = {
      id: Date.now().toString(),
      role: "user",
      content: messageText,
    };
    const history = [...messages, userMsg];
    setMessages(history);
    setInput("");
    setIsTyping(true);

    try {
      const resp = await fetch("https://n8n.flowai.it.com/webhook/ort-chat-agent", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query: messageText }),
      });
      const data = await resp.json();

      if (!resp.ok) {
        throw new Error(data.error || "Server error");
      }

      setMessages([
        ...history,
        {
          id: (Date.now() + 1).toString(),
          role: "assistant",
          content: data.answer,
          sources: data.sources ?? [],
        },
      ]);
    } catch (err) {
      setMessages([
        ...history,
        {
          id: (Date.now() + 1).toString(),
          role: "assistant",
          content: `Lo siento, hubo un error al procesar tu pregunta. Verificá que el workflow de n8n esté activo.\n\nDetalle: ${err}`,
        },
      ]);
    } finally {
      setIsTyping(false);
    }
  };

  const handleCopy = async () => {
    const text = messages
      .map((m) => `${m.role === "user" ? "Vos" : "Asistente"}: ${m.content}`)
      .join("\n\n");
    await navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const isEmpty = messages.length === 0 && !isTyping;
  const hasMessages = messages.length > 0;

  return (
    <div className="flex h-[calc(100vh-7rem)] sm:h-[calc(100vh-6.5rem)]">
      <div className="flex-1 flex flex-col min-w-0 max-w-2xl mx-auto w-full">
        {/* Header */}
        <div className="mb-3 sm:mb-4 flex items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <div className="h-7 w-7 rounded-full bg-primary/10 flex items-center justify-center ring-2 ring-primary/20">
              <span className="text-sm">🎓</span>
            </div>
            <div>
              <h2 className="text-base sm:text-lg font-bold text-foreground tracking-tight leading-none">
                Chat con mis clases
              </h2>
              <p className="text-[10px] text-muted-foreground mt-0.5">
                Respondé en base a los transcripts de ORT
              </p>
            </div>
          </div>

          <div className="flex items-center gap-1.5 shrink-0">
            <motion.button
              whileHover={{ scale: 1.05 }}
              whileTap={{ scale: 0.95 }}
              onClick={() => setMessages([])}
              className="h-8 px-2.5 rounded-lg bg-card border border-border text-muted-foreground hover:text-foreground text-[11px] font-medium flex items-center gap-1.5 transition-all cursor-pointer"
            >
              <Plus className="h-3 w-3" />
              <span className="hidden sm:inline">Nueva</span>
            </motion.button>

            {hasMessages && (
              <motion.button
                whileHover={{ scale: 1.05 }}
                whileTap={{ scale: 0.95 }}
                onClick={handleCopy}
                className="h-8 w-8 rounded-lg bg-card border border-border text-muted-foreground hover:text-foreground flex items-center justify-center transition-all cursor-pointer"
                title="Copiar chat"
              >
                {copied ? <Check className="h-3 w-3 text-emerald-500" /> : <Copy className="h-3 w-3" />}
              </motion.button>
            )}
          </div>
        </div>

        {/* Scroll area */}
        <div className="flex-1 overflow-y-auto pr-1 pb-4">
          {/* Empty state */}
          {isEmpty && (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              className="flex flex-col items-center justify-center h-full -mt-8"
            >
              <motion.div
                initial={{ scale: 0.8, opacity: 0 }}
                animate={{ scale: 1, opacity: 1 }}
                transition={{ type: "spring", stiffness: 200, damping: 20 }}
                className="mb-5"
              >
                <div className="h-20 w-20 rounded-full bg-primary/10 flex items-center justify-center ring-2 ring-primary/20 ring-offset-2 ring-offset-background">
                  <span className="text-3xl">🎓</span>
                </div>
              </motion.div>

              <motion.h3
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.15 }}
                className="text-base font-semibold text-foreground mb-1"
              >
                ¿Qué querés saber de tus clases?
              </motion.h3>
              <motion.p
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.2 }}
                className="text-[11px] sm:text-[12px] text-muted-foreground mb-6 text-center max-w-sm px-4"
              >
                Preguntame sobre cualquier tema que se haya visto en las clases. Busco en los 50 transcripts indexados.
              </motion.p>

              <div className="flex flex-wrap justify-center gap-2 max-w-md px-2">
                {SUGGESTED_QUESTIONS.map((q, i) => (
                  <motion.button
                    key={q}
                    initial={{ opacity: 0, y: 6 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: 0.25 + i * 0.05 }}
                    whileHover={{ scale: 1.03, y: -1 }}
                    whileTap={{ scale: 0.97 }}
                    onClick={() => handleSend(q)}
                    className="px-3 py-2 rounded-full bg-card border border-border text-[11px] font-medium text-muted-foreground hover:text-foreground hover:border-primary/40 transition-all cursor-pointer"
                  >
                    {q}
                  </motion.button>
                ))}
              </div>
            </motion.div>
          )}

          {/* Messages */}
          {!isEmpty && (
            <div className="space-y-4">
              <AnimatePresence>
                {messages.map((msg) => (
                  <motion.div
                    key={msg.id}
                    initial={{ opacity: 0, y: 8, scale: 0.97 }}
                    animate={{ opacity: 1, y: 0, scale: 1 }}
                    transition={{ type: "spring", stiffness: 300, damping: 25 }}
                    className={`flex gap-2 sm:gap-2.5 ${msg.role === "user" ? "justify-end" : ""}`}
                  >
                    {msg.role === "assistant" && (
                      <div className="h-7 w-7 sm:h-8 sm:w-8 rounded-full shrink-0 mt-0.5 ring-2 ring-primary/20 bg-primary/10 flex items-center justify-center">
                        <span className="text-sm">🎓</span>
                      </div>
                    )}

                    <div
                      className={`flex-1 min-w-0 ${
                        msg.role === "user"
                          ? "max-w-[85%] sm:max-w-[70%]"
                          : "max-w-[92%] sm:max-w-[88%]"
                      }`}
                    >
                      <div
                        className={`overflow-hidden ${
                          msg.role === "user"
                            ? "bg-gradient-to-br from-blue-500 via-blue-600 to-blue-700 text-white ml-auto rounded-3xl rounded-br-sm shadow-lg shadow-blue-900/20"
                            : "bg-card border border-border rounded-2xl rounded-bl-md"
                        }`}
                      >
                        {msg.role === "assistant" ? (
                          <div className="px-3 sm:px-4 py-2.5 sm:py-3">
                            <RichContent content={msg.content} />
                          </div>
                        ) : (
                          <div className="px-3 sm:px-4 py-2 sm:py-2.5">
                            <p className="text-[13px] leading-relaxed">{msg.content}</p>
                            <p className="text-[10px] text-white/50 text-right mt-1">
                              {new Date(Number(msg.id)).toLocaleTimeString([], {
                                hour: "2-digit",
                                minute: "2-digit",
                              })}
                            </p>
                          </div>
                        )}
                      </div>

                      {/* Source cards below assistant messages */}
                      {msg.role === "assistant" && msg.sources && msg.sources.length > 0 && (
                        <SourceCards sources={msg.sources} onOpenTranscript={onOpenTranscript} />
                      )}
                    </div>

                    {msg.role === "user" && (
                      <div className="h-7 w-7 sm:h-8 sm:w-8 rounded-full shrink-0 mt-0.5 ring-2 ring-primary/20 bg-secondary flex items-center justify-center">
                        <User className="h-3.5 w-3.5 text-secondary-foreground" />
                      </div>
                    )}
                  </motion.div>
                ))}
              </AnimatePresence>

              <AnimatePresence>
                {isTyping && (
                  <motion.div
                    initial={{ opacity: 0, y: 8 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -4, transition: { duration: 0.15 } }}
                  >
                    <TypingIndicator />
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          )}
          <div ref={bottomRef} />
        </div>

        {/* Input */}
        <motion.div
          className="relative mt-2"
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.2 }}
        >
          <div className="rounded-2xl bg-card border border-border focus-within:ring-2 focus-within:ring-primary/30 focus-within:border-primary/40 transition-all overflow-hidden">
            <textarea
              ref={textareaRef}
              placeholder="Preguntá sobre tus clases..."
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  handleSend();
                }
              }}
              rows={1}
              className="w-full min-h-[40px] max-h-[200px] px-4 pt-3 pb-0 bg-transparent text-sm text-foreground placeholder:text-muted-foreground/50 focus:outline-none resize-none overflow-y-auto"
              style={{ height: "auto" }}
            />

            <div className="flex items-center justify-end px-2 pb-2 pt-1">
              <motion.button
                onClick={() => handleSend()}
                disabled={!input.trim() || isTyping}
                whileHover={{ scale: 1.08 }}
                whileTap={{ scale: 0.92 }}
                className={`h-9 w-9 sm:h-8 sm:w-8 rounded-lg flex items-center justify-center disabled:opacity-30 disabled:cursor-not-allowed transition-all cursor-pointer ${
                  input.trim() && !isTyping
                    ? "bg-primary text-primary-foreground shadow-md"
                    : "bg-muted text-muted-foreground"
                }`}
              >
                <Send className="h-4 w-4" strokeWidth={2.5} />
              </motion.button>
            </div>
          </div>
        </motion.div>
      </div>
    </div>
  );
}
