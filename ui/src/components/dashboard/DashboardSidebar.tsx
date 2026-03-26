import { MessageSquare, BookOpen, ExternalLink } from "lucide-react";
import type { ActiveView } from "@/pages/Index";

interface DashboardSidebarProps {
  activeView: ActiveView;
  onViewChange: (view: ActiveView) => void;
}

const navItems = [
  { id: "chat" as ActiveView,        label: "Chat con mis clases", icon: MessageSquare },
  { id: "transcripts" as ActiveView, label: "Transcripciones",     icon: BookOpen },
];

const NOTEBOOKLM_NOTEBOOKS = [
  { label: "Business Intelligence",  url: "https://notebooklm.google.com/notebook/PLACEHOLDER_BI" },
  { label: "Economía y Gestión",     url: "https://notebooklm.google.com/notebook/PLACEHOLDER_EG" },
  { label: "Contabilidad y Costos",  url: "https://notebooklm.google.com/notebook/PLACEHOLDER_CC" },
  { label: "Project Management",     url: "https://notebooklm.google.com/notebook/PLACEHOLDER_PM" },
  { label: "E-commerce y Servicios", url: "https://notebooklm.google.com/notebook/PLACEHOLDER_ES" },
  { label: "Matemática Financiera",  url: "https://notebooklm.google.com/notebook/PLACEHOLDER_MF" },
];

export function DashboardSidebar({ activeView, onViewChange }: DashboardSidebarProps) {
  return (
    <aside className="w-full border-r border-border bg-sidebar flex flex-col h-full min-h-screen shrink-0 overflow-y-auto">
      {/* Logo */}
      <div className="h-14 flex items-center gap-2.5 px-4 border-b border-sidebar-border">
        <div className="h-8 w-8 rounded-lg bg-primary/15 flex items-center justify-center shrink-0">
          <span className="text-base font-bold text-primary">O</span>
        </div>
        <div>
          <p className="text-[11px] font-bold text-sidebar-accent-foreground tracking-wide">ORT Knowledge</p>
          <p className="text-[9px] text-sidebar-foreground/60">Base de conocimientos</p>
        </div>
      </div>

      {/* Nav */}
      <nav className="flex-1 p-2.5 space-y-0.5">
        <p className="text-[9px] font-semibold uppercase tracking-[0.15em] text-sidebar-foreground/50 px-3 mb-2 mt-1">
          Herramientas
        </p>
        {navItems.map((item) => {
          const isActive = activeView === item.id;
          return (
            <button
              key={item.id}
              onClick={() => onViewChange(item.id)}
              className={`w-full flex items-center gap-2.5 px-3 py-2 rounded-lg text-[13px] font-medium transition-all duration-150 ${
                isActive
                  ? "bg-sidebar-accent text-sidebar-accent-foreground glow-primary-sm"
                  : "text-sidebar-foreground hover:text-sidebar-accent-foreground hover:bg-sidebar-accent/50"
              }`}
            >
              <item.icon className={`h-3.5 w-3.5 shrink-0 ${isActive ? "text-primary" : ""}`} />
              <span>{item.label}</span>
            </button>
          );
        })}
      </nav>

      {/* NotebookLM */}
      <div className="px-2.5 pb-3">
        <div className="border-t border-sidebar-border pt-3">
          <p className="text-[9px] font-semibold uppercase tracking-[0.15em] text-sidebar-foreground/50 px-3 mb-2">
            Estudiar en NotebookLM
          </p>
          <div className="space-y-0.5">
            {NOTEBOOKLM_NOTEBOOKS.map((nb) => (
              <a
                key={nb.label}
                href={nb.url}
                target="_blank"
                rel="noopener noreferrer"
                className="w-full flex items-center gap-2 px-3 py-1.5 rounded-lg text-[12px] text-sidebar-foreground/70 hover:text-sidebar-accent-foreground hover:bg-sidebar-accent/50 transition-all duration-150 group"
              >
                <BookOpen className="h-3 w-3 shrink-0 text-sidebar-foreground/40 group-hover:text-primary/70" />
                <span className="flex-1 truncate">{nb.label}</span>
                <ExternalLink className="h-2.5 w-2.5 shrink-0 opacity-0 group-hover:opacity-50 transition-opacity" />
              </a>
            ))}
          </div>
        </div>
      </div>

      {/* Footer */}
      <div className="p-3 border-t border-sidebar-border">
        <p className="text-[10px] text-sidebar-foreground/40 text-center">
          Semestre 5 · ORT Uruguay
        </p>
      </div>
    </aside>
  );
}
