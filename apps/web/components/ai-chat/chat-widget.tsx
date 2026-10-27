import React, { useState, useRef, useEffect } from "react";
import ReactMarkdown from "react-markdown";
import { Bot, Sparkles, X, Send, Loader2, Paperclip, FileText, Settings, Check } from "lucide-react";

interface MessageAction {
  label: string;
  action: string;
}

interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  toolCalls?: Array<{ name: string; args?: Record<string, unknown> }>;
  fileName?: string;
  actions?: MessageAction[];
}

interface AttachedFile {
  name: string;
  dataUrl: string;
  mimeType: string;
  text?: string;
  size: number;
}

const MAX_FILE_BYTES = 50 * 1024 * 1024;
const TEXT_FILE_EXTENSIONS = [".csv", ".txt", ".md", ".json", ".html", ".xml", ".yaml", ".yml"];
type AIProvider = "codex" | "antigravity" | "gemini" | "openai";

export const PlaneAIChatWidget: React.FC = () => {
  const [isOpen, setIsOpen] = useState(false);
  const [showSettings, setShowSettings] = useState(false);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [attachedFile, setAttachedFile] = useState<AttachedFile | null>(null);

  const [isDragging, setIsDragging] = useState(false);

  // Settings: Defaults to OpenAI Codex Local (gpt-5.6-sol) - No API Key Needed!
  const [apiKey, setApiKey] = useState("");
  const [model, setModel] = useState("gpt-5.6-sol (Codex CLI)");
  const [baseUrl, setBaseUrl] = useState("");
  const [provider, setProvider] = useState<AIProvider>("codex");

  const [messages, setMessages] = useState<Message[]>([
    {
      id: "welcome",
      role: "assistant",
      content:
        "👋 **Xin chào! Tôi là Trợ lý AI kết nối trực tiếp với OpenAI Codex (gpt-5.6-sol) trên máy bạn.**\n\nTôi kết nối trực tiếp với Plane MCP mà **không cần nhập API key**. Bạn có thể đặt bất kỳ câu hỏi kỹ thuật nào, phân tích dự án, tư vấn kiến trúc, hoặc kéo thả file CSV để tự động import công việc!",
    },
  ]);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const saved = localStorage.getItem("plane_openai_cfg");
    if (saved) {
      try {
        const parsed = JSON.parse(saved);
        if (parsed.apiKey) setApiKey(parsed.apiKey);
        if (parsed.model) setModel(parsed.model);
        if (parsed.baseUrl) setBaseUrl(parsed.baseUrl);
        if (parsed.provider === "gemini" && !parsed.apiKey) {
          setProvider("antigravity");
          setModel("gemini-3.8-flash (Antigravity)");
        } else if (parsed.provider) {
          setProvider(parsed.provider);
        }
      } catch {}
    }
  }, []);

  const saveSettings = () => {
    localStorage.setItem("plane_openai_cfg", JSON.stringify({ apiKey, model, baseUrl, provider }));
    setShowSettings(false);
  };

  const changeProvider = (nextProvider: AIProvider) => {
    setProvider(nextProvider);
    if (nextProvider === "codex") {
      setModel("gpt-5.6-sol (Codex CLI)");
      setBaseUrl("");
      setApiKey("");
    } else if (nextProvider === "antigravity") {
      setModel("gemini-3.5-flash (Hybrid)");
      setBaseUrl("");
      setApiKey("");
    } else if (nextProvider === "gemini") {
      setModel("gemini-3.5-flash");
      setBaseUrl("https://generativelanguage.googleapis.com/v1beta/openai");
    } else if (nextProvider === "openai") {
      setModel("gpt-4o");
      setBaseUrl("https://api.openai.com/v1");
    }
  };

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    if (isOpen) {
      scrollToBottom();
    }
  }, [messages, isOpen, showSettings]);

  const processFile = (file: File) => {
    if (file.size > MAX_FILE_BYTES) {
      setMessages((previous) => [
        ...previous,
        {
          id: crypto.randomUUID(),
          role: "assistant",
          content: "❌ Tệp vượt quá giới hạn 50 MB của OpenAI Responses API.",
        },
      ]);
      return;
    }

    const reader = new FileReader();
    reader.addEventListener("load", (event) => {
      const dataUrl = event.target?.result;
      if (typeof dataUrl !== "string") return;
      const lowerName = file.name.toLowerCase();
      const isTextFile = TEXT_FILE_EXTENSIONS.some((extension) => lowerName.endsWith(extension));
      const attachment = {
        name: file.name,
        dataUrl,
        mimeType: file.type || "application/octet-stream",
        size: file.size,
      };
      if (isTextFile) {
        void file.text().then((text) => setAttachedFile({ ...attachment, text }));
      } else {
        setAttachedFile(attachment);
      }
    });
    reader.readAsDataURL(file);
  };

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    processFile(file);
    e.target.value = "";
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(true);
  };

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
    const files = e.dataTransfer.files;
    if (files && files.length > 0) {
      processFile(files[0]);
    }
  };

  const handleSend = async (textToSend?: string) => {
    const text = (textToSend || input).trim();
    if ((!text && !attachedFile) || loading) return;

    const currentFile = attachedFile;
    const displayText = text ? text : `Đọc tệp ${currentFile?.name} và xử lý công việc`;

    const newMessages: Message[] = [
      ...messages,
      {
        id: crypto.randomUUID(),
        role: "user",
        content: displayText,
        fileName: currentFile?.name,
      },
    ];
    setMessages(newMessages);
    setInput("");
    setAttachedFile(null);
    setLoading(true);

    try {
      const response = await fetch("http://localhost:6274/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: text || "Đọc tệp và tạo các công việc tương ứng vào dự án",
          history: messages.map((m) => ({ role: m.role, content: m.content })),
          file: currentFile
            ? {
                name: currentFile.name,
                dataUrl: currentFile.dataUrl,
                mimeType: currentFile.mimeType,
                content: currentFile.text,
              }
            : null,
          settings: {
            provider,
            apiKey,
            model,
            baseUrl,
          },
        }),
      });

      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.error || "Không thể xử lý yêu cầu");
      }

      setMessages((prev) => [
        ...prev,
        {
          id: crypto.randomUUID(),
          role: "assistant",
          content: data.reply,
          toolCalls: data.tool_calls,
          actions: data.actions,
        },
      ]);
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : "Không thể kết nối tới MCP Server";
      setMessages((prev) => [
        ...prev,
        {
          id: crypto.randomUUID(),
          role: "assistant",
          content: `❌ Lỗi: ${message}`,
        },
      ]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      {/* Floating Action Button */}
      <div className="fixed right-6 bottom-6 z-50 flex items-center">
        {!isOpen && (
          <button
            type="button"
            onClick={() => setIsOpen(true)}
            className="group bg-emerald-500 hover:bg-emerald-400 text-neutral-950 shadow-xl text-sm border-emerald-300/40 flex items-center gap-2.5 rounded-full border px-4 py-3 font-medium transition-all duration-200 hover:scale-105 active:scale-95"
            title="Mở Trợ lý AI Plane"
          >
            <div className="relative">
              <Bot className="h-5 w-5" />
              <span className="absolute -top-1 -right-1 flex h-2.5 w-2.5">
                <span className="bg-emerald-200 absolute inline-flex h-full w-full animate-ping rounded-full opacity-75" />
                <span className="bg-emerald-900 relative inline-flex h-2.5 w-2.5 rounded-full" />
              </span>
            </div>
            <span>Trợ lý AI MCP</span>
          </button>
        )}
      </div>

      {/* Chat Window Drawer / Popup */}
      {isOpen && (
        <div
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
          className="bg-neutral-900 border-neutral-700/80 shadow-2xl text-neutral-100 font-sans fixed right-6 bottom-6 z-50 flex h-[600px] max-h-[calc(100vh-64px)] w-[430px] max-w-[calc(100vw-32px)] flex-col overflow-hidden rounded-2xl border"
          style={{ backdropFilter: "blur(12px)" }}
        >
          {/* Drag and Drop Overlay */}
          {isDragging && (
            <div className="bg-neutral-950/90 border-emerald-400 animate-fadeIn pointer-events-none absolute inset-0 z-50 flex flex-col items-center justify-center rounded-2xl border-2 border-dashed p-6 text-center backdrop-blur-sm">
              <div className="bg-emerald-500/20 text-emerald-400 mb-3 flex h-16 w-16 items-center justify-center rounded-full">
                <Paperclip className="h-8 w-8 animate-bounce" />
              </div>
              <div className="text-base font-semibold text-white">Thả tệp vào đây</div>
              <div className="text-xs text-neutral-400 mt-1">Hỗ trợ PDF, Word, Excel, CSV, TXT, Markdown và JSON</div>
            </div>
          )}

          {/* Header */}
          <div className="bg-neutral-950/80 border-neutral-800 flex items-center justify-between border-b px-4 py-3">
            <div className="flex items-center gap-2.5">
              <div className="bg-emerald-500/20 text-emerald-400 border-emerald-500/30 flex h-8 w-8 items-center justify-center rounded-lg border">
                <Sparkles className="h-4 w-4" />
              </div>
              <div>
                <div className="text-sm flex items-center gap-1.5 font-semibold text-white">
                  Plane AI Agent
                  <span className="bg-emerald-500 h-2 w-2 rounded-full" title="Online" />
                </div>
                <div className="text-neutral-400 font-mono text-[11px]">
                  {provider === "antigravity" ? "⚡ Antigravity (Gemini 3.8 Flash) • Không cần Key" : `${model} + MCP local`}
                </div>
              </div>
            </div>

            <div className="flex items-center gap-1">
              <button
                type="button"
                onClick={() => setShowSettings(!showSettings)}
                className={`rounded-lg p-1.5 transition-colors ${
                  showSettings
                    ? "text-emerald-400 bg-neutral-800"
                    : "text-neutral-400 hover:bg-neutral-800 hover:text-white"
                }`}
                title="Cài đặt mô hình AI"
              >
                <Settings className="h-4 w-4" />
              </button>
              <button
                type="button"
                onClick={() => setIsOpen(false)}
                className="text-neutral-400 hover:bg-neutral-800 rounded-lg p-1.5 transition-colors hover:text-white"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
          </div>

          {/* Settings Panel */}
          {showSettings && (
            <div className="bg-neutral-950 border-neutral-800 text-xs animate-fadeIn space-y-3 border-b p-4">
              <div className="space-y-1">
                <label htmlFor="plane-ai-provider" className="text-neutral-400 text-[11px]">
                  Bộ não của Agent
                </label>
                <select
                  id="plane-ai-provider"
                  value={provider}
                  onChange={(event) => changeProvider(event.target.value as AIProvider)}
                  className="bg-neutral-900 border-neutral-700 text-xs focus:border-emerald-500 w-full rounded-lg border px-2.5 py-1.5 text-white outline-none"
                >
                  <option value="codex">🚀 OpenAI Codex (gpt-5.6-sol — Đang chạy trên laptop, Không cần API Key)</option>
                  <option value="antigravity">⚡ Hybrid Agent (Gemini 3 Flash Preview + Plane MCP)</option>
                  <option value="gemini">Gemini Cloud API (Google AI Studio Key)</option>
                  <option value="openai">OpenAI Responses API (Cần OpenAI Key)</option>
                </select>
              </div>

              {provider === "codex" ? (
                <div className="bg-sky-950/40 border-sky-500/40 space-y-1.5 rounded-lg border p-3 text-[11px]">
                  <div className="text-sky-400 flex items-center gap-1.5 font-semibold">
                    <Sparkles className="h-3.5 w-3.5" /> OpenAI Codex (gpt-5.6-sol)
                  </div>
                  <p className="text-neutral-300 leading-relaxed">
                    Kết nối trực tiếp với <strong>OpenAI Codex Desktop & CLI</strong> đang chạy trên laptop của bạn.
                    Hoạt động tự động 100%, <strong>không cần nhập API key</strong>!
                  </p>
                </div>
              ) : provider === "antigravity" ? (
                <div className="bg-emerald-950/40 border-emerald-500/40 space-y-1.5 rounded-lg border p-3 text-[11px]">
                  <div className="text-emerald-400 flex items-center gap-1.5 font-semibold">
                    <Sparkles className="h-3.5 w-3.5" /> Hybrid Agent (Gemini 3 Flash Preview)
                  </div>
                  <p className="text-neutral-300 leading-relaxed">
                    Đang chạy trực tiếp qua môi trường kết nối Plane MCP.
                    Hoạt động tự động 100%, <strong>không cần nhập API key</strong>!
                  </p>
                </div>
              ) : (
                <>
                  <div className="space-y-1">
                    <label htmlFor="plane-ai-api-key" className="text-neutral-400 text-[11px]">
                      {provider === "gemini" ? "Gemini API Key" : "OpenAI API Key"}:
                    </label>
                    <input
                      id="plane-ai-api-key"
                      type="password"
                      value={apiKey}
                      onChange={(e) => setApiKey(e.target.value)}
                      placeholder={provider === "gemini" ? "AIza..." : "sk-proj-..."}
                      className="bg-neutral-900 border-neutral-700 text-xs focus:border-emerald-500 w-full rounded-lg border px-2.5 py-1.5 text-white outline-none"
                    />
                  </div>
                  <div className="grid grid-cols-2 gap-2">
                    <div className="space-y-1">
                      <label htmlFor="plane-ai-model" className="text-neutral-400 text-[11px]">
                        Mô hình (Model):
                      </label>
                      <input
                        id="plane-ai-model"
                        type="text"
                        value={model}
                        onChange={(e) => setModel(e.target.value)}
                        placeholder={provider === "gemini" ? "gemini-3.8-flash" : "gpt-4o"}
                        className="bg-neutral-900 border-neutral-700 text-xs focus:border-emerald-500 w-full rounded-lg border px-2.5 py-1.5 text-white outline-none"
                      />
                    </div>
                    <div className="space-y-1">
                      <label htmlFor="plane-ai-base-url" className="text-neutral-400 text-[11px]">
                        Base URL:
                      </label>
                      <input
                        id="plane-ai-base-url"
                        type="text"
                        value={baseUrl}
                        onChange={(e) => setBaseUrl(e.target.value)}
                        placeholder="https://api.openai.com/v1"
                        className="bg-neutral-900 border-neutral-700 text-xs focus:border-emerald-500 w-full rounded-lg border px-2.5 py-1.5 text-white outline-none"
                      />
                    </div>
                  </div>
                </>
              )}

              <div className="flex justify-end pt-1">
                <button
                  type="button"
                  onClick={saveSettings}
                  className="bg-emerald-500 hover:bg-emerald-400 text-neutral-950 text-xs flex items-center gap-1.5 rounded-lg px-3 py-1.5 font-medium"
                >
                  <Check className="h-3.5 w-3.5" /> Lưu cài đặt
                </button>
              </div>
            </div>
          )}

          {/* Quick Action Chips */}
          <div className="bg-neutral-950/40 border-neutral-800/60 no-scrollbar text-xs flex items-center gap-1.5 overflow-x-auto border-b px-3 py-2">
            <button
              type="button"
              onClick={() => handleSend("Xem danh sách task")}
              className="bg-neutral-800 hover:bg-neutral-700 border-neutral-700 text-neutral-300 rounded-full border px-2.5 py-1 text-[11px] whitespace-nowrap transition-colors hover:text-white"
            >
              📋 Xem task
            </button>
            <button
              type="button"
              onClick={() => handleSend("Xem danh sách các dự án trong workspace")}
              className="bg-neutral-800 hover:bg-neutral-700 border-neutral-700 text-neutral-300 rounded-full border px-2.5 py-1 text-[11px] whitespace-nowrap transition-colors hover:text-white"
            >
              📁 Xem dự án
            </button>
            <button
              type="button"
              onClick={() => fileInputRef.current?.click()}
              className="bg-emerald-500/10 hover:bg-emerald-500/20 border-emerald-500/30 text-emerald-300 flex items-center gap-1 rounded-full border px-2.5 py-1 text-[11px] whitespace-nowrap transition-colors"
            >
              <Paperclip className="h-3 w-3" /> Đính kèm tệp
            </button>
          </div>

          {/* Messages Feed */}
          <div className="text-sm flex-1 space-y-3.5 overflow-y-auto p-4">
            {messages.map((m) => (
              <div key={m.id} className={`flex gap-2.5 ${m.role === "user" ? "flex-row-reverse" : "flex-row"}`}>
                <div
                  className={`text-xs flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-lg font-bold ${
                    m.role === "user"
                      ? "bg-emerald-500 text-neutral-950 font-semibold"
                      : "bg-neutral-800 text-emerald-400 border-neutral-700 border"
                  }`}
                >
                  {m.role === "user" ? "B" : "AI"}
                </div>

                <div
                  className={`max-w-[85%] rounded-xl px-3.5 py-2.5 leading-relaxed ${
                    m.role === "user"
                      ? "bg-emerald-600/30 border-emerald-500/40 text-emerald-50 border"
                      : "bg-neutral-800/90 border-neutral-700/60 text-neutral-200 border"
                  }`}
                >
                  {/* File badge if sent */}
                  {m.fileName && (
                    <div className="bg-emerald-500/20 text-emerald-300 text-xs font-mono mb-1.5 inline-flex items-center gap-1.5 rounded px-2 py-0.5">
                      <FileText className="h-3 w-3" />
                      <span>{m.fileName}</span>
                    </div>
                  )}

                  {/* Tool Call Badges */}
                  {m.toolCalls && m.toolCalls.length > 0 && (
                    <div className="mb-2 space-y-1">
                      {m.toolCalls.map((tc) => (
                        <div
                          key={`${tc.name}-${JSON.stringify(tc.args ?? {})}`}
                          className="bg-emerald-500/10 border-emerald-500/20 text-emerald-400 font-mono mr-1 inline-flex items-center gap-1.5 rounded border px-2 py-0.5 text-[11px]"
                        >
                          ⚙️ MCP: <strong>{tc.name}</strong>
                        </div>
                      ))}
                    </div>
                  )}

                  <ReactMarkdown
                    components={{
                      p: ({ children }) => <p className="mb-2 last:mb-0">{children}</p>,
                      ul: ({ children }) => <ul className="ml-4 list-disc space-y-1">{children}</ul>,
                      ol: ({ children }) => <ol className="ml-4 list-decimal space-y-1">{children}</ol>,
                      code: ({ children }) => (
                        <code className="text-xs text-emerald-400 rounded bg-black/20 px-1 py-0.5">{children}</code>
                      ),
                    }}
                  >
                    {m.content}
                  </ReactMarkdown>

                  {/* Interactive Action Buttons */}
                  {m.actions && m.actions.length > 0 && (
                    <div className="border-neutral-700/60 mt-3 flex flex-col gap-1.5 border-t pt-2.5">
                      <div className="text-neutral-400 text-[11px] font-medium">Chọn thao tác nhanh:</div>
                      {m.actions.map((act) => (
                        <button
                          key={act.action}
                          type="button"
                          onClick={() => handleSend(act.action)}
                          className="bg-emerald-500/15 hover:bg-emerald-500/25 active:bg-emerald-500/30 text-emerald-300 hover:text-emerald-100 border-emerald-500/30 hover:border-emerald-500/60 text-xs group shadow-sm flex w-full items-center justify-between rounded-xl border px-3 py-2 text-left font-medium transition-all duration-150 active:scale-[0.98]"
                        >
                          <span className="truncate pr-2">{act.label}</span>
                          <span className="text-emerald-400 text-sm transition-transform group-hover:translate-x-0.5">
                            ➔
                          </span>
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            ))}

            {loading && (
              <div className="text-neutral-400 text-xs flex items-center gap-2.5 py-1">
                <Loader2 className="text-emerald-400 h-4 w-4 animate-spin" />
                <span>AI đang đọc nội dung và xử lý trên Plane...</span>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>

          {/* Attached File Preview Pill */}
          {attachedFile && (
            <div className="bg-neutral-950/90 border-neutral-800 text-xs flex items-center justify-between border-t px-3 py-1.5">
              <div className="text-emerald-400 font-mono flex max-w-[320px] items-center gap-1.5 truncate">
                <FileText className="h-3.5 w-3.5 flex-shrink-0" />
                <span className="truncate">{attachedFile.name}</span>
                <span className="text-neutral-500 text-[10px]">({Math.round(attachedFile.size / 1024)} KB)</span>
              </div>
              <button
                type="button"
                onClick={() => setAttachedFile(null)}
                className="text-neutral-400 hover:text-rose-400 p-0.5"
                title="Bỏ tệp"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            </div>
          )}

          {/* Input Bar */}
          <form
            onSubmit={(e) => {
              e.preventDefault();
              handleSend();
            }}
            className="bg-neutral-950 border-neutral-800 flex items-center gap-2 border-t p-3"
          >
            <input
              type="file"
              ref={fileInputRef}
              onChange={handleFileSelect}
              accept=".pdf,.doc,.docx,.rtf,.odt,.xls,.xlsx,.csv,.tsv,.ppt,.pptx,.txt,.md,.json,.html,.xml,.yaml,.yml"
              className="hidden"
            />

            <button
              type="button"
              onClick={() => fileInputRef.current?.click()}
              className="text-neutral-400 hover:text-emerald-400 hover:bg-neutral-800 rounded-xl p-2 transition-colors"
              title="Đính kèm PDF, Word, Excel, CSV hoặc tệp văn bản"
            >
              <Paperclip className="h-4 w-4" />
            </button>

            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder={
                attachedFile ? `Nhập lệnh cho file ${attachedFile.name}...` : "Nhập lệnh hoặc đính kèm tệp..."
              }
              className="bg-neutral-900 border-neutral-700 text-sm text-neutral-100 placeholder-neutral-500 focus:border-emerald-500 focus:ring-emerald-500 flex-1 rounded-xl border px-3.5 py-2 transition-all outline-none focus:ring-1"
            />

            <button
              type="submit"
              disabled={loading || (!input.trim() && !attachedFile)}
              className="bg-emerald-500 hover:bg-emerald-400 disabled:hover:bg-emerald-500 text-neutral-950 flex items-center justify-center rounded-xl p-2.5 font-medium transition-all disabled:opacity-50"
            >
              <Send className="h-4 w-4" />
            </button>
          </form>
        </div>
      )}
    </>
  );
};
