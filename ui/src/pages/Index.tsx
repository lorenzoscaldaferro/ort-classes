import { useState } from "react";
import { DashboardSidebar } from "@/components/dashboard/DashboardSidebar";
import { ChatView, type ChatMessage } from "@/components/dashboard/ChatView";
import { TranscriptsView, type TranscriptDeepLink } from "@/components/dashboard/TranscriptsView";
import { ThemeToggle } from "@/components/dashboard/ThemeToggle";
import { AnimatedBackground } from "@/components/dashboard/AnimatedBackground";
import { motion, AnimatePresence } from "framer-motion";
import { Menu, X } from "lucide-react";

export type ActiveView = "chat" | "transcripts";

const Index = () => {
  const [activeView, setActiveView] = useState<ActiveView>("chat");
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [transcriptDeepLink, setTranscriptDeepLink] = useState<TranscriptDeepLink | null>(null);
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([]);

  const handleOpenTranscript = (semester: string, subject: string, file: string, excerpt: string) => {
    setTranscriptDeepLink({ semester, subject, file, excerpt });
    setActiveView("transcripts");
  };

  return (
    <div className="flex min-h-screen w-full bg-background relative">
      <AnimatedBackground />

      {/* Mobile sidebar backdrop */}
      <AnimatePresence>
        {sidebarOpen && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="fixed inset-0 bg-black/60 z-40 md:hidden"
            onClick={() => setSidebarOpen(false)}
          />
        )}
      </AnimatePresence>

      {/* Sidebar */}
      <div
        className={`
          fixed inset-y-0 left-0 z-50 w-64 transform transition-transform duration-300 ease-out
          md:relative md:translate-x-0 md:w-60 md:z-10
          ${sidebarOpen ? "translate-x-0" : "-translate-x-full"}
        `}
      >
        <DashboardSidebar
          activeView={activeView}
          onViewChange={(view) => {
            setActiveView(view);
            setSidebarOpen(false);
            if (view !== "transcripts") setTranscriptDeepLink(null);
          }}
        />
      </div>

      <div className="flex-1 flex flex-col min-h-screen relative z-10 w-full min-w-0">
        {/* Top Bar */}
        <header className="h-14 border-b border-border flex items-center justify-between px-3 sm:px-6 glass overflow-visible relative z-30">
          <div className="flex items-center gap-2">
            <button
              onClick={() => setSidebarOpen(!sidebarOpen)}
              className="md:hidden h-9 w-9 rounded-lg flex items-center justify-center text-foreground/70 hover:text-foreground hover:bg-muted/50 transition-all"
              aria-label="Toggle menu"
            >
              {sidebarOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
            </button>
            <div className="flex items-center gap-2 md:hidden">
              <span className="text-[11px] font-bold text-foreground tracking-wide">ORT Knowledge Base</span>
            </div>
            <div className="hidden md:block">
              <h1 className="text-[13px] font-bold text-foreground">ORT Knowledge Base</h1>
            </div>
          </div>
          <div className="flex items-center gap-2 sm:gap-3">
            <ThemeToggle />
          </div>
        </header>

        {/* Content */}
        <main className="flex-1 p-3 sm:p-4 md:p-6 overflow-y-auto">
          <AnimatePresence mode="wait">
            <motion.div
              key={activeView}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -8 }}
              transition={{ duration: 0.2 }}
            >
              {activeView === "chat"
                ? <ChatView
                    messages={chatMessages}
                    onMessagesChange={setChatMessages}
                    onOpenTranscript={handleOpenTranscript}
                  />
                : <TranscriptsView
                    initialOpen={transcriptDeepLink}
                    onClearInitialOpen={() => setTranscriptDeepLink(null)}
                  />
              }
            </motion.div>
          </AnimatePresence>
        </main>
      </div>
    </div>
  );
};

export default Index;
