import { useEffect, useRef, useState } from "react";
import { BookOpen, Check, ChevronRight, Copy, FileText, Loader2, X } from "lucide-react";

interface SubjectData {
  label: string;
  files: string[];
}

interface TranscriptsTree {
  [semester: string]: {
    [subject: string]: SubjectData;
  };
}

export interface TranscriptDeepLink {
  semester: string;
  subject: string;
  file: string;
  excerpt?: string;
}

interface TranscriptsViewProps {
  initialOpen?: TranscriptDeepLink | null;
  onClearInitialOpen?: () => void;
}

const SUBJECT_COLORS: Record<string, string> = {
  business_intelligence:   "bg-blue-100 text-blue-800 dark:bg-blue-900/40 dark:text-blue-300",
  economia_y_gestion:      "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300",
  contabilidad_y_costos:   "bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300",
  project_management:      "bg-sky-100 text-sky-800 dark:bg-sky-900/40 dark:text-sky-300",
  ecommerce_y_servicios:   "bg-rose-100 text-rose-800 dark:bg-rose-900/40 dark:text-rose-300",
  matematica_financiera:   "bg-orange-100 text-orange-800 dark:bg-orange-900/40 dark:text-orange-300",
};

function formatFileName(name: string): string {
  return name.replace(/\.md$/, "");
}

function extractDate(name: string): string {
  const m = name.match(/^(\d{2}-\d{2}-\d{4})/);
  return m ? m[1] : "";
}

function HighlightedContent({ content, excerpt }: { content: string; excerpt?: string }) {
  const highlightRef = useRef<HTMLSpanElement>(null);

  useEffect(() => {
    if (excerpt && highlightRef.current) {
      highlightRef.current.scrollIntoView({ behavior: "smooth", block: "center" });
    }
  }, [excerpt]);

  if (!excerpt) {
    return (
      <pre className="text-[12px] text-foreground/80 whitespace-pre-wrap font-mono leading-relaxed">
        {content}
      </pre>
    );
  }

  // Find the excerpt in the content (first ~150 chars of the excerpt for matching)
  const needle = excerpt.replace(/…$/, "").slice(0, 150);
  const idx = content.indexOf(needle);

  if (idx === -1) {
    return (
      <pre className="text-[12px] text-foreground/80 whitespace-pre-wrap font-mono leading-relaxed">
        {content}
      </pre>
    );
  }

  const before = content.slice(0, idx);
  const match = content.slice(idx, idx + needle.length);
  const after = content.slice(idx + needle.length);

  return (
    <pre className="text-[12px] text-foreground/80 whitespace-pre-wrap font-mono leading-relaxed">
      {before}
      <span
        ref={highlightRef}
        className="bg-yellow-200/50 dark:bg-yellow-400/20 rounded px-0.5"
      >
        {match}
      </span>
      {after}
    </pre>
  );
}

export function TranscriptsView({ initialOpen, onClearInitialOpen }: TranscriptsViewProps) {
  const [tree, setTree] = useState<TranscriptsTree>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [selected, setSelected] = useState<{ semester: string; subject: string; file: string; excerpt?: string } | null>(null);
  const [content, setContent] = useState<string | null>(null);
  const [contentLoading, setContentLoading] = useState(false);
  const [copiedFile, setCopiedFile] = useState(false);

  useEffect(() => {
    fetch("/transcripts_index.json")
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then((data) => { setTree(data); setLoading(false); })
      .catch((e) => { setError(e.message); setLoading(false); });
  }, []);

  // Auto-open from deep-link once tree is loaded
  useEffect(() => {
    if (!loading && initialOpen && Object.keys(tree).length > 0) {
      openFile(initialOpen.semester, initialOpen.subject, initialOpen.file, initialOpen.excerpt);
      onClearInitialOpen?.();
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loading, initialOpen]);

  function openFile(semester: string, subject: string, file: string, excerpt?: string) {
    // If semester/subject from deep-link is invalid (e.g. "N/A" stored in Pinecone),
    // search the loaded tree to find the correct location for this file.
    let resolvedSemester = semester;
    let resolvedSubject = subject;
    if (!tree[resolvedSemester]?.[resolvedSubject]) {
      let found = false;
      for (const [sem, subjects] of Object.entries(tree)) {
        if (found) break;
        for (const [sub, data] of Object.entries(subjects)) {
          if (data.files.includes(file)) {
            resolvedSemester = sem;
            resolvedSubject = sub;
            found = true;
            break;
          }
        }
      }
    }
    setSelected({ semester: resolvedSemester, subject: resolvedSubject, file, excerpt });
    setContent(null);
    setContentLoading(true);
    setCopiedFile(false);
    fetch(`/transcripts/${resolvedSemester}/${resolvedSubject}/${encodeURIComponent(file)}`)
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.text();
      })
      .then((text) => { setContent(text); setContentLoading(false); })
      .catch((e) => { setContent(`Error: ${e.message}`); setContentLoading(false); });
  }

  function closeFile() {
    setSelected(null);
    setContent(null);
  }

  async function handleCopyFile() {
    if (!content) return;
    await navigator.clipboard.writeText(content);
    setCopiedFile(true);
    setTimeout(() => setCopiedFile(false), 2000);
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64 text-muted-foreground">
        <Loader2 className="h-5 w-5 animate-spin mr-2" />
        <span className="text-sm">Cargando transcripciones…</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex items-center justify-center h-64 text-destructive text-sm">
        Error al cargar transcripciones: {error}
      </div>
    );
  }

  // Sort semesters in reverse so semestre_5 comes first, semestre_3 last
  const semesters = Object.keys(tree).sort().reverse();

  return (
    <div className="max-w-4xl mx-auto">
      <div className="mb-6">
        <h2 className="text-base font-semibold text-foreground">Transcripciones</h2>
        <p className="text-[12px] text-muted-foreground mt-0.5">
          Clases grabadas indexadas en la base de conocimientos
        </p>
      </div>

      {selected ? (
        /* File viewer */
        <div className="rounded-xl border border-border bg-card overflow-hidden">
          <div className="flex items-center justify-between px-4 py-3 border-b border-border bg-muted/30">
            <div className="flex items-center gap-2 min-w-0">
              <FileText className="h-4 w-4 shrink-0 text-muted-foreground" />
              <div className="min-w-0">
                <p className="text-[12px] font-medium text-foreground truncate">
                  {formatFileName(selected.file)}
                </p>
                <p className="text-[10px] text-muted-foreground">
                  {tree[selected.semester]?.[selected.subject]?.label} · {selected.semester}
                </p>
              </div>
            </div>
            <div className="flex items-center gap-1 shrink-0">
              <button
                onClick={handleCopyFile}
                disabled={!content || contentLoading}
                className="h-7 w-7 rounded-md flex items-center justify-center text-muted-foreground hover:text-foreground hover:bg-muted transition-all disabled:opacity-30"
                title="Copiar transcripción"
              >
                {copiedFile
                  ? <Check className="h-3.5 w-3.5 text-emerald-500" />
                  : <Copy className="h-3.5 w-3.5" />
                }
              </button>
              <button
                onClick={closeFile}
                className="h-7 w-7 rounded-md flex items-center justify-center text-muted-foreground hover:text-foreground hover:bg-muted transition-all"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
          </div>

          <div className="p-4 overflow-y-auto max-h-[calc(100vh-280px)]">
            {contentLoading ? (
              <div className="flex items-center gap-2 text-muted-foreground text-sm">
                <Loader2 className="h-4 w-4 animate-spin" />
                Cargando…
              </div>
            ) : (
              <HighlightedContent content={content ?? ""} excerpt={selected.excerpt} />
            )}
          </div>
        </div>
      ) : (
        /* Tree view */
        <div className="space-y-6">
          {semesters.length === 0 && (
            <div className="flex flex-col items-center justify-center h-48 text-muted-foreground">
              <BookOpen className="h-8 w-8 mb-2 opacity-30" />
              <p className="text-sm">No hay transcripciones todavía</p>
            </div>
          )}

          {semesters.map((semester) => {
            const subjects = Object.keys(tree[semester]).sort();
            return (
              <div key={semester}>
                <p className="text-[10px] font-semibold uppercase tracking-[0.15em] text-muted-foreground/60 mb-3">
                  {semester.replace(/_/g, " ")}
                </p>
                <div className="space-y-3">
                  {subjects.map((subject) => {
                    const { label, files } = tree[semester][subject];
                    const colorClass = SUBJECT_COLORS[subject] ?? "bg-zinc-100 text-zinc-800 dark:bg-zinc-800 dark:text-zinc-300";
                    return (
                      <div key={subject} className="rounded-xl border border-border bg-card overflow-hidden">
                        <div className="flex items-center gap-3 px-4 py-3 border-b border-border bg-muted/20">
                          <span className={`text-[10px] font-semibold px-2 py-0.5 rounded-full shrink-0 ${colorClass}`}>
                            {label}
                          </span>
                          <span className="text-[11px] text-muted-foreground ml-auto">
                            {files.length} {files.length === 1 ? "clase" : "clases"}
                          </span>
                        </div>
                        <ul className="divide-y divide-border">
                          {files.map((file) => {
                            const date = extractDate(file);
                            const title = formatFileName(file).replace(/^\d{2}-\d{2}-\d{4}\s*[-–]\s*/, "");
                            return (
                              <li key={file}>
                                <button
                                  onClick={() => openFile(semester, subject, file)}
                                  className="w-full flex items-center gap-3 px-4 py-2.5 text-left hover:bg-muted/40 transition-colors group"
                                >
                                  <FileText className="h-3.5 w-3.5 shrink-0 text-muted-foreground/50 group-hover:text-muted-foreground transition-colors" />
                                  <div className="min-w-0 flex-1">
                                    <p className="text-[12px] text-foreground/80 truncate group-hover:text-foreground transition-colors">
                                      {title || formatFileName(file)}
                                    </p>
                                    {date && (
                                      <p className="text-[10px] text-muted-foreground/50">{date}</p>
                                    )}
                                  </div>
                                  <ChevronRight className="h-3.5 w-3.5 text-muted-foreground/30 group-hover:text-muted-foreground/60 shrink-0 transition-colors" />
                                </button>
                              </li>
                            );
                          })}
                        </ul>
                      </div>
                    );
                  })}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
