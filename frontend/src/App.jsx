import React, { useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowDown,
  ArrowLeft,
  ArrowRight,
  ArrowUpRight,
  BookOpen,
  Check,
  ChevronRight,
  CircleHelp,
  Copy,
  CreditCard,
  FileText,
  Gavel,
  History,
  Menu,
  MessageSquare,
  Search,
  Send,
  Settings,
  Shield,
  Sparkles,
  Users,
  WalletCards,
  X,
  Zap,
} from "lucide-react";
import "./App.css";

const departments = [
  {
    id: "HR",
    name: "Human Resources",
    short: "HR",
    description:
      "Leave, attendance, onboarding, benefits and workplace policies.",
    icon: Users,
    color: "#F2A11B",
    soft: "#FFF5E5",
    questions: [
      "How many paid leave days do I get?",
      "What is the leave approval process?",
      "What documents are required during onboarding?",
    ],
  },
  {
    id: "Legal",
    name: "Legal",
    short: "Legal",
    description:
      "Contracts, agreements, compliance requirements and legal procedures.",
    icon: Gavel,
    color: "#7654F6",
    soft: "#F1EDFF",
    questions: [
      "What is the contract approval process?",
      "Who can approve a legal agreement?",
      "What are the document retention requirements?",
    ],
  },
  {
    id: "Finance",
    name: "Finance",
    short: "Finance",
    description:
      "Expenses, reimbursements, procurement and financial controls.",
    icon: WalletCards,
    color: "#119B8B",
    soft: "#EAF9F6",
    questions: [
      "How do I submit an expense claim?",
      "What expenses require prior approval?",
      "What is the reimbursement timeline?",
    ],
  },
  {
    id: "IT",
    name: "Information Technology",
    short: "IT",
    description:
      "Access management, security, devices and technology procedures.",
    icon: Shield,
    color: "#2D6CDF",
    soft: "#EDF4FF",
    questions: [
      "How do I request system access?",
      "What is the password policy?",
      "How do I report a security incident?",
    ],
  },
];

function EdithMark({ small = false }) {
  return (
    <div className={`edith-mark ${small ? "small" : ""}`}>
      <Sparkles size={small ? 17 : 22} strokeWidth={2.1} />
    </div>
  );
}

function DepartmentIcon({ department, size = 21 }) {
  const Icon = department.icon;

  return (
    <Icon
      size={size}
      strokeWidth={1.9}
      style={{ color: department.color }}
    />
  );
}

function SourceIcon({ type = "pdf" }) {
  if (type === "excel") return <CreditCard size={18} />;
  return <FileText size={18} />;
}

function App() {
  const [page, setPage] = useState("home");
  const [mobileMenu, setMobileMenu] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [selectedDepartment, setSelectedDepartment] =
    useState("All departments");

  const [input, setInput] = useState("");
  const [messages, setMessages] = useState([]);
  const [citation, setCitation] = useState(null);
  const [loading, setLoading] = useState(false);
  const [copied, setCopied] = useState(false);
  const [expandedDept, setExpandedDept] = useState(null);
  const [history, setHistory] = useState([]);
  const [backendStatus, setBackendStatus] = useState("checking");

  const composerRef = useRef(null);

  useEffect(() => {
    const saved = localStorage.getItem("edith-history");

    if (saved) {
      try {
        setHistory(JSON.parse(saved));
      } catch {
        setHistory([]);
      }
    }
  }, []);

  useEffect(() => {
    checkHealth();
  }, []);

  async function checkHealth() {
    try {
      const response = await fetch("/health");
      setBackendStatus(response.ok ? "ready" : "error");
    } catch {
      setBackendStatus("offline");
    }
  }

  function goHome() {
    setPage("home");
    setMobileMenu(false);

    window.scrollTo({
      top: 0,
      behavior: "smooth",
    });
  }

  function openAssistant(
    question = "",
    department = "All departments"
  ) {
    setPage("assistant");
    setSelectedDepartment(department);
    setMobileMenu(false);

    if (question) {
      setInput(question);

      setTimeout(() => {
        composerRef.current?.focus();
      }, 150);
    }
  }

  function newConversation() {
    setMessages([]);
    setInput("");
    setCitation(null);
  }

  function scrollToSection(id) {
    setMobileMenu(false);

    if (page !== "home") {
      setPage("home");

      setTimeout(() => {
        document
          .getElementById(id)
          ?.scrollIntoView({
            behavior: "smooth",
            block: "start",
          });
      }, 100);

      return;
    }

    document
      .getElementById(id)
      ?.scrollIntoView({
        behavior: "smooth",
        block: "start",
      });
  }

  async function askEdith(question = input) {
    const query = question.trim();

    if (!query || loading) return;

    const userMessage = {
      id: Date.now(),
      role: "user",
      text: query,
    };

    setMessages((prev) => [...prev, userMessage]);
    setInput("");
    setLoading(true);
    setCitation(null);

    try {
      const response = await fetch("/api/query", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
            body: JSON.stringify({
      question: query,
      department_filter:
        selectedDepartment === "All departments"
          ? null
          : [selectedDepartment.toLowerCase()],
    }),
      });

      if (!response.ok) {
        throw new Error(`Request failed: ${response.status}`);
      }

      const data = await response.json();

      const answer =
        data.answer ||
        data.response ||
        data.result ||
        data.message ||
        "I couldn't find enough information in the available company documents.";

      const sources =
        data.sources ||
        data.citations ||
        data.documents ||
        data.context ||
        [];

      const normalizedSources = normalizeSources(sources);

      const assistantMessage = {
        id: Date.now() + 1,
        role: "assistant",
        text: answer,
        sources: normalizedSources,
        grounded:
          data.grounded !== undefined
            ? data.grounded
            : normalizedSources.length > 0,
      };

      setMessages((prev) => [...prev, assistantMessage]);

      const historyItem = {
        id: Date.now(),
        query,
        department: selectedDepartment,
      };

      const newHistory = [historyItem, ...history].slice(0, 8);

      setHistory(newHistory);

      localStorage.setItem(
        "edith-history",
        JSON.stringify(newHistory)
      );
    } catch {
      setMessages((prev) => [
        ...prev,
        {
          id: Date.now() + 1,
          role: "assistant",
          error: true,
          text:
            "I couldn't connect to the knowledge service right now. Please check that the FastAPI backend, Qdrant and Ollama service are running.",
          sources: [],
          grounded: false,
        },
      ]);
    } finally {
      setLoading(false);
    }
  }

  function normalizeSources(rawSources) {
    if (!Array.isArray(rawSources)) return [];

    return rawSources.map((source, index) => ({
      id: index + 1,

      name:
        source.filename ||
        source.file_name ||
                source.source_file ||
        source.document ||
        source.title ||
        source.source ||
        `Source ${index + 1}`,

      page:
        source.page ||
        source.page_number ||
        source.metadata?.page ||
        source.metadata?.page_number ||
        null,

      text:
        source.text ||
        source.content ||
        source.chunk ||
        source.context ||
        "",

      relevance:
        source.score ||
        source.similarity ||
        source.relevance ||
        null,

      type:
        source.type ||
        (String(source.filename || "")
          .toLowerCase()
          .includes("xlsx")
          ? "excel"
          : "pdf"),
    }));
  }

  function copyAnswer(text) {
    navigator.clipboard?.writeText(text);

    setCopied(true);

    setTimeout(() => {
      setCopied(false);
    }, 1500);
  }

  function handleKeyDown(e) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      askEdith();
    }
  }

  const activeDepartment = useMemo(
    () =>
      departments.find(
        (department) => department.id === selectedDepartment
      ) || departments[0],
    [selectedDepartment]
  );

  return (
    <div className="app">
      {page === "home" ? (
        <LandingPage
          onAsk={openAssistant}
          onScroll={scrollToSection}
          mobileMenu={mobileMenu}
          setMobileMenu={setMobileMenu}
        />
      ) : (
        <AssistantPage
          sidebarOpen={sidebarOpen}
          setSidebarOpen={setSidebarOpen}
          selectedDepartment={selectedDepartment}
          setSelectedDepartment={setSelectedDepartment}
          activeDepartment={activeDepartment}
          openAssistant={openAssistant}
          goHome={goHome}
          newConversation={newConversation}
          history={history}
          expandedDept={expandedDept}
          setExpandedDept={setExpandedDept}
          backendStatus={backendStatus}
          messages={messages}
          loading={loading}
          input={input}
          setInput={setInput}
          askEdith={askEdith}
          handleKeyDown={handleKeyDown}
          composerRef={composerRef}
          citation={citation}
          setCitation={setCitation}
          copied={copied}
          copyAnswer={copyAnswer}
        />
      )}
    </div>
  );
}

/* =========================================================
   LANDING PAGE
========================================================= */

function LandingPage({
  onAsk,
  onScroll,
  mobileMenu,
  setMobileMenu,
}) {
  return (
    <div className="landing">
      <header className="site-nav">
        <div
          className="nav-brand"
          onClick={() =>
            window.scrollTo({
              top: 0,
              behavior: "smooth",
            })
          }
        >
          <EdithMark />

          <div>
            <div className="brand-name">Northbridge</div>
            <div className="brand-subtitle">DYNAMICS</div>
          </div>
        </div>

        <nav className={`nav-links ${mobileMenu ? "open" : ""}`}>
          <button onClick={() => onScroll("how-it-works")}>
            How it works
          </button>

          <button onClick={() => onScroll("departments")}>
            Departments
          </button>

          <button onClick={() => onScroll("sources")}>
            Sources
          </button>

          <button onClick={() => onAsk()}>
            Edith
          </button>
        </nav>

        <div className="nav-actions">
          <button
            className="nav-explore"
            onClick={() => onScroll("departments")}
          >
            Explore
          </button>

          <button
            className="primary-cta"
            onClick={() => onAsk()}
          >
            Ask Edith
            <ArrowUpRight size={19} />
          </button>
        </div>

        <button
          className="mobile-menu-button"
          onClick={() => setMobileMenu(!mobileMenu)}
        >
          {mobileMenu ? <X /> : <Menu />}
        </button>
      </header>

      <main>
        {/* HERO */}

        <section className="hero">
          <div className="hero-decoration purple-orb"></div>
          <div className="hero-decoration yellow-orb"></div>
          <div className="hero-grid"></div>

          <div className="hero-copy">
            <div className="eyebrow">
              <span className="eyebrow-dot"></span>
              NORTHBRIDGE KNOWLEDGE ASSISTANT
            </div>

            <h1>
              Find what you need.
              <br />

              <span className="hero-gradient-text">
                Understand what matters.
              </span>

              <br />

              Edith makes it simple.
            </h1>

            <p className="hero-description">
              Edith helps Northbridge employees quickly find and
              understand information across HR, Legal, Finance and
              IT, directly from the company's own knowledge base.
            </p>

            <div className="hero-actions">
              <button
                className="primary-cta large"
                onClick={() => onAsk()}
              >
                Ask Edith
                <ArrowRight size={20} />
              </button>

              <button
                className="text-cta"
                onClick={() => onScroll("how-it-works")}
              >
                Explore how it works
                <ArrowDown size={18} />
              </button>
            </div>

            <div className="hero-points">
              <span>
                <Check size={17} />
                Source-backed
              </span>

              <span>
                <Check size={17} />
                Department-aware
              </span>

            </div>
          </div>

          <div className="hero-product">
            <div className="hero-product-glow"></div>

            <div className="browser-window">
              <div className="browser-top">
                <div className="browser-dots">
                  <span></span>
                  <span></span>
                  <span></span>
                </div>

                <div className="browser-address">
                  northbridge / edith
                </div>

                <div className="ready-indicator">
                  <span></span>
                  Ready
                </div>
              </div>

              <div className="mock-product">
                <div className="mock-sidebar">
                  <EdithMark small />
                  <MessageSquare />
                  <FileText />
                  <Search />
                </div>

                <div className="mock-chat">
                  <div className="mock-label">
                    NORTHBRIDGE KNOWLEDGE
                  </div>

                  <div className="mock-chat-title">
                    Ask Edith
                    <Sparkles size={20} />
                  </div>

                  <div className="mock-user-question">
                    How many paid leave days do I get?
                  </div>

                  <div className="mock-answer">
                    <div className="mock-answer-heading">
                      <EdithMark small />
                      <strong>Edith</strong>
                    </div>

                    <p>
                      I found relevant information in the Human
                      Resources policy documents.
                    </p>

                    <div className="mock-source">
                      <FileText size={16} />
                      HR Leave Policy · Page 4
                      <ArrowUpRight size={15} />
                    </div>
                  </div>

                  <div className="mock-input">
                    <span>Ask about a company policy...</span>

                    <div className="mock-send">
                      <Send size={17} />
                    </div>
                  </div>
                </div>
              </div>
            </div>

            {/* MOVED LOWER — DOES NOT COVER ASK EDITH */}

            <div className="floating-search">
              <div className="floating-icon purple">
                <Search size={20} />
              </div>

              <div>
                <strong>Searching policies</strong>
                <span>Qdrant knowledge base</span>
              </div>

              <div className="search-scan"></div>
            </div>

            <div className="floating-source">
              <div className="floating-check">
                <Check size={18} />
              </div>

              <div>
                <strong>Source found</strong>
                <span>Evidence attached</span>
              </div>
            </div>

            <div className="hero-particle particle-one"></div>
            <div className="hero-particle particle-two"></div>
            <div className="hero-particle particle-three"></div>
          </div>
        </section>

        {/* HOW IT WORKS */}

        <section
          id="how-it-works"
          className="how-section"
        >
          <div className="section-heading">
            <div>
              <div className="eyebrow dark">
                <span className="eyebrow-dot"></span>
                HOW EDITH WORKS
              </div>

              <h2>
                From company documents
                <br />
                <span>to useful answers.</span>
              </h2>
            </div>
          </div>

          <div className="architecture">
            <ArchitectureStep
              number="01"
              icon={<FileText />}
              title="Company documents"
              text="Policies, procedures and internal knowledge are collected."
            />

            <div className="architecture-arrow">
              <ArrowRight />
            </div>

            <ArchitectureStep
              number="02"
              icon={<BookOpen />}
              title="Knowledge base"
              text="Documents are converted into searchable knowledge chunks."
            />

            <div className="architecture-arrow">
              <ArrowRight />
            </div>

            <ArchitectureStep
              number="03"
              icon={<Search />}
              title="Relevant evidence"
              text="Edith retrieves the most relevant information for each question."
            />

            <div className="architecture-arrow">
              <ArrowRight />
            </div>

            <ArchitectureStep
              number="04"
              icon={<Sparkles />}
              title="Useful answer"
              text="The LLM explains the answer and shows where it came from."
            />
          </div>
        </section>

        {/* DEPARTMENTS */}

        <section
          id="departments"
          className="departments-section"
        >
          <div className="department-heading">
            <div>
              <div className="eyebrow dark">
                <span className="eyebrow-dot"></span>
                EXPLORE KNOWLEDGE
              </div>

              <h2>
                Ask the right
                <br />
                <span>knowledge base.</span>
              </h2>
            </div>

            <p>
              Edith keeps HR, Legal, Finance and IT knowledge
              organized so employees can ask questions in the right
              context.
            </p>
          </div>

          <div className="department-grid">
            {departments.map((department) => (
              <DepartmentCard
                key={department.id}
                department={department}
                onAsk={onAsk}
              />
            ))}
          </div>
        </section>

        {/* EVIDENCE */}

        <section
          id="sources"
          className="evidence-section"
        >
          <div className="evidence-glow evidence-glow-one"></div>
          <div className="evidence-glow evidence-glow-two"></div>

          {/* NEW VISUAL — FILLS THE EMPTY SPACE */}

          <EvidenceVisual />

          <div className="evidence-copy">
            <div className="eyebrow evidence">
              <span className="eyebrow-dot"></span>
              EVIDENCE FIRST
            </div>

            <h2>
              An answer is more useful
              <br />
              when you{" "}
              <span className="evidence-highlight">
                can see why.
              </span>
            </h2>

            <p>
              Edith shows the policy evidence behind an answer.
              Employees can open a citation, inspect the source and
              understand where the response came from.
            </p>

            <ul>
              <li>
                <Check size={18} />
                Relevant policy passage
              </li>

              <li>
                <Check size={18} />
                Document and page reference
              </li>

              <li>
                <Check size={18} />
                Evidence beside the answer
              </li>
            </ul>
          </div>
        </section>

        {/* FINAL CTA */}

        <section className="final-cta-section">
          <div className="yellow-sparkle">
            <Sparkles size={30} />
          </div>

          <div className="eyebrow dark">
            <span className="eyebrow-dot"></span>
            NORTHBRIDGE DYNAMICS
          </div>

          <h2>
            Your questions deserve
            <br />
            <span>clear answers.</span>
          </h2>

          <p>
            Ask Edith about company policies, procedures and
            internal knowledge.
          </p>

          <button
            className="primary-cta large"
            onClick={() => onAsk()}
          >
            Ask Edith
            <ArrowUpRight size={20} />
          </button>
        </section>
      </main>

      <footer className="footer">
        <div className="footer-brand">
          <EdithMark small />

          <div>
            <strong>Northbridge Dynamics</strong>
            <span>Knowledge made accessible.</span>
          </div>
        </div>

        <div className="footer-links">
          <button onClick={() => onScroll("how-it-works")}>
            How it works
          </button>

          <button onClick={() => onScroll("departments")}>
            Departments
          </button>

          <button onClick={() => onScroll("sources")}>
            Sources
          </button>

          <button onClick={() => onAsk()}>
            Ask Edith
          </button>
        </div>

        <div className="footer-tech">
          FastAPI · Qdrant · Ollama
        </div>
      </footer>
    </div>
  );
}

/* =========================================================
   NEW EVIDENCE VISUAL
========================================================= */

function EvidenceVisual() {
  return (
    <div className="evidence-visual">
      <div className="evidence-visual-grid"></div>

      <div className="evidence-orbit orbit-one"></div>
      <div className="evidence-orbit orbit-two"></div>

      <div className="evidence-document document-one">
        <div className="mini-file-icon purple">
          <FileText size={18} />
        </div>

        <div>
          <strong>HR Leave Policy</strong>
          <span>Page 4</span>
        </div>

        <Check size={15} />
      </div>

      <div className="evidence-document document-two">
        <div className="mini-file-icon yellow">
          <BookOpen size={18} />
        </div>

        <div>
          <strong>Employee Handbook</strong>
          <span>Page 18</span>
        </div>

        <ArrowUpRight size={15} />
      </div>

      <div className="evidence-document document-three">
        <div className="mini-file-icon black">
          <Shield size={18} />
        </div>

        <div>
          <strong>Policy evidence</strong>
          <span>Retrieved passage</span>
        </div>
      </div>

      <div className="evidence-connection connection-one"></div>
      <div className="evidence-connection connection-two"></div>
      <div className="evidence-connection connection-three"></div>

      <div className="evidence-main-card">
        <div className="evidence-main-top">
          <div className="evidence-edith">
            <EdithMark small />

            <div>
              <strong>Edith</strong>
              <span>Evidence found</span>
            </div>
          </div>

          <div className="evidence-confidence">
            <Check size={13} />
            Verified
          </div>
        </div>

        <div className="evidence-question">
          "What is the leave approval process?"
        </div>

        <div className="evidence-answer-line">
          Employees should follow the leave approval process
          defined in the applicable HR policy.
        </div>

        <div className="evidence-citation-row">
          <span className="citation-pill">[1]</span>

          <div>
            <strong>HR Leave Policy</strong>
            <span>Relevant passage · Page 4</span>
          </div>

          <ArrowUpRight size={16} />
        </div>
      </div>

      <div className="evidence-search-node">
        <Search size={18} />
      </div>

      <div className="evidence-pulse pulse-one"></div>
      <div className="evidence-pulse pulse-two"></div>
    </div>
  );
}

/* =========================================================
   DEPARTMENT CARD
========================================================= */

function DepartmentCard({ department, onAsk }) {
  const [hovered, setHovered] = useState(false);
  const Icon = department.icon;

  return (
    <article
      className="department-card"
      style={{
        "--dept-color": department.color,
        "--dept-soft": department.soft,
      }}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
    >
      <div className="department-card-glow"></div>

      <div className="department-top">
        <div className="department-icon-wrap">
          <div className="department-icon-ring"></div>
          <Icon size={25} strokeWidth={1.8} />
        </div>

        <span className="department-code">
          {department.short || department.id}
        </span>
      </div>

      <div className="department-main">
        <h3>{department.name}</h3>

        <p>{department.description}</p>
      </div>

      <div className="department-divider"></div>

      <div className="try-heading">
        <span>TRY ASKING</span>
        <span>3 suggested questions</span>
      </div>

      <div className="question-list">
        {department.questions.map((question, index) => (
          <button
            key={question}
            className="department-question"
            onClick={() =>
              onAsk(question, department.id)
            }
          >
            <span className="question-number">
              {String(index + 1).padStart(2, "0")}
            </span>

            <span className="question-text">
              {question}
            </span>

            <span className="question-arrow">
              <ArrowUpRight size={16} />
            </span>
          </button>
        ))}
      </div>

      <div
        className={`department-hover-line ${
          hovered ? "visible" : ""
        }`}
      ></div>
    </article>
  );
}

/* =========================================================
   ARCHITECTURE
========================================================= */

function ArchitectureStep({
  number,
  icon,
  title,
  text,
}) {
  return (
    <div className="architecture-step">
      <div className="architecture-icon">
        {icon}
      </div>

      <span className="architecture-number">
        {number}
      </span>

      <h3>{title}</h3>

      <p>{text}</p>
    </div>
  );
}

/* =========================================================
   ASSISTANT
========================================================= */

function AssistantPage({
  sidebarOpen,
  setSidebarOpen,
  selectedDepartment,
  setSelectedDepartment,
  activeDepartment,
  openAssistant,
  goHome,
  newConversation,
  history,
  expandedDept,
  setExpandedDept,
  backendStatus,
  messages,
  loading,
  input,
  setInput,
  askEdith,
  handleKeyDown,
  composerRef,
  citation,
  setCitation,
  copied,
  copyAnswer,
}) {
  return (
    <div className="assistant-page">
      {sidebarOpen && (
        <div
          className="sidebar-mobile-overlay"
          onClick={() => setSidebarOpen(false)}
        ></div>
      )}

      <aside
        className={`assistant-sidebar ${
          sidebarOpen ? "open" : ""
        }`}
      >
        <div className="sidebar-brand">
          <div
            className="sidebar-brand-click"
            onClick={goHome}
          >
            <EdithMark />

            <div>
              <strong>Edith</strong>
              <span>NORTHBRIDGE AI</span>
            </div>
          </div>

          <button
            className="sidebar-close"
            onClick={() => setSidebarOpen(false)}
          >
            <X size={19} />
          </button>
        </div>

        <div className="sidebar-content">
          <button
            className="back-link"
            onClick={goHome}
          >
            <ArrowLeft size={15} />
            Back to Northbridge
          </button>

          <button
            className="new-conversation"
            onClick={newConversation}
          >
            <MessageSquare size={19} />
            <span>New conversation</span>
            <span className="shortcut">⌘ K</span>
          </button>

          <div className="sidebar-section">
            <div className="sidebar-section-label">
              DEPARTMENTS
            </div>

            <button
              className={`sidebar-department all ${
                selectedDepartment ===
                "All departments"
                  ? "active"
                  : ""
              }`}
              onClick={() =>
                setSelectedDepartment(
                  "All departments"
                )
              }
            >
              <Zap size={18} />

              <span>All departments</span>

              <ChevronRight
                size={15}
                className="side-arrow"
              />
            </button>

            {departments.map((department) => (
              <div key={department.id}>
                <button
                  className={`sidebar-department ${
                    selectedDepartment ===
                    department.id
                      ? "active"
                      : ""
                  }`}
                  style={{
                    "--side-color":
                      department.color,
                    "--side-soft":
                      department.soft,
                  }}
                  onClick={() => {
                    setSelectedDepartment(
                      department.id
                    );

                    setExpandedDept(
                      expandedDept ===
                        department.id
                        ? null
                        : department.id
                    );
                  }}
                >
                  <DepartmentIcon
                    department={department}
                    size={18}
                  />

                  <span>{department.name}</span>

                  <div className="sidebar-department-right">
                    <span className="status-check">
                      <Check size={11} />
                    </span>

                    <ChevronRight
                      size={14}
                      className={`department-chevron ${
                        expandedDept ===
                        department.id
                          ? "expanded"
                          : ""
                      }`}
                    />
                  </div>
                </button>

                {expandedDept ===
                  department.id && (
                  <div className="sidebar-submenu">
                    <div className="submenu-status">
                      <span className="live-pulse"></span>
                      Knowledge base ready
                    </div>

                    {department.questions.map(
                      (question) => (
                        <button
                          key={question}
                          onClick={() =>
                            openAssistant(
                              question,
                              department.id
                            )
                          }
                        >
                          <span>{question}</span>
                          <ArrowUpRight size={13} />
                        </button>
                      )
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>

          {history.length > 0 && (
            <div className="sidebar-section history-section">
              <div className="sidebar-section-label">
                RECENT CONVERSATIONS
              </div>

              {history.slice(0, 4).map((item) => (
                <button
                  key={item.id}
                  className="history-item"
                  onClick={() =>
                    openAssistant(
                      item.query,
                      item.department
                    )
                  }
                >
                  <History size={15} />
                  <span>{item.query}</span>
                </button>
              ))}
            </div>
          )}

          <div className="sidebar-status">
            <div className="sidebar-section-label">
              SYSTEM STATUS
            </div>

            <div
              className={`status-card ${
                backendStatus === "ready"
                  ? "ready"
                  : backendStatus ===
                    "checking"
                  ? "checking"
                  : "error"
              }`}
            >
              <div className="status-card-heading">
                <span className="status-live-dot"></span>

                <strong>
                  {backendStatus ===
                  "ready"
                    ? "System ready"
                    : backendStatus ===
                      "checking"
                    ? "Checking system"
                    : "System unavailable"}
                </strong>
              </div>

              <span>
                FastAPI · Qdrant · Ollama
              </span>
            </div>
          </div>
        </div>

        <div className="sidebar-user">
          <div className="user-avatar">N</div>

          <div>
            <strong>Northbridge employee</strong>
            <span>Internal access</span>
          </div>

          <Settings size={17} />
        </div>
      </aside>

      <main className="assistant-main">
        <header className="assistant-header">
          <button
            className="mobile-sidebar-trigger"
            onClick={() =>
              setSidebarOpen(true)
            }
          >
            <Menu size={21} />
          </button>

          <div>
            <span>
              NORTHBRIDGE KNOWLEDGE
            </span>

            <h1>Ask Edith</h1>
          </div>

          <div className="assistant-header-status">
            <span></span>

            {backendStatus === "ready"
              ? "Ready"
              : "Connecting"}
          </div>
        </header>

        {messages.length === 0 ? (
          <AssistantEmptyState
            selectedDepartment={
              selectedDepartment
            }
            activeDepartment={
              activeDepartment
            }
            openAssistant={
              openAssistant
            }
            input={input}
            setInput={setInput}
            askEdith={askEdith}
            handleKeyDown={
              handleKeyDown
            }
            composerRef={composerRef}
          />
        ) : (
          <ChatConversation
            messages={messages}
            loading={loading}
            setCitation={setCitation}
            copyAnswer={copyAnswer}
            copied={copied}
          />
        )}

        {messages.length > 0 && (
          <div className="conversation-composer-wrap">
            <Composer
              input={input}
              setInput={setInput}
              askEdith={askEdith}
              handleKeyDown={
                handleKeyDown
              }
              composerRef={composerRef}
              activeDepartment={
                activeDepartment
              }
              selectedDepartment={
                selectedDepartment
              }
              loading={loading}
            />
          </div>
        )}
      </main>

      {citation && (
        <CitationPanel
          citation={citation}
          onClose={() =>
            setCitation(null)
          }
        />
      )}
    </div>
  );
}

/* =========================================================
   EMPTY ASSISTANT
========================================================= */

function AssistantEmptyState({
  selectedDepartment,
  activeDepartment,
  openAssistant,
  input,
  setInput,
  askEdith,
  handleKeyDown,
  composerRef,
}) {
  const suggestions =
    selectedDepartment ===
    "All departments"
      ? departments.map(
          (department) => ({
            department,
            question:
              department.questions[0],
          })
        )
      : [
          {
            department: activeDepartment,
            question:
              activeDepartment.questions[0],
          },
          {
            department: activeDepartment,
            question:
              activeDepartment.questions[1],
          },
          {
            department: activeDepartment,
            question:
              activeDepartment.questions[2],
          },
        ];

  return (
    <div className="assistant-empty">
      <div className="assistant-empty-content">
        <div className="assistant-empty-eyebrow">
          NORTHBRIDGE KNOWLEDGE ASSISTANT
        </div>

        <h2>
          What can I help
          <br />
          <span>you find?</span>
        </h2>

        <p>
          Ask about HR, Legal, Finance or IT policies.
          Edith searches the relevant knowledge base
          and cites the source.
        </p>

        <div className="assistant-suggestions">
          {suggestions
            .slice(0, 4)
            .map(
              ({
                department,
                question,
              }) => (
                <button
                  key={question}
                  onClick={() =>
                    openAssistant(
                      question,
                      department.id
                    )
                  }
                  style={{
                    "--suggestion-color":
                      department.color,
                    "--suggestion-soft":
                      department.soft,
                  }}
                >
                  <DepartmentIcon
                    department={
                      department
                    }
                    size={19}
                  />

                  <span>{question}</span>

                  <ArrowUpRight
                    size={16}
                  />
                </button>
              )
            )}
        </div>
      </div>

      <Composer
        input={input}
        setInput={setInput}
        askEdith={askEdith}
        handleKeyDown={handleKeyDown}
        composerRef={composerRef}
        activeDepartment={
          activeDepartment
        }
        selectedDepartment={
          selectedDepartment
        }
        loading={false}
      />
    </div>
  );
}

/* =========================================================
   COMPOSER
========================================================= */

function Composer({
  input,
  setInput,
  askEdith,
  handleKeyDown,
  composerRef,
  activeDepartment,
  selectedDepartment,
  loading,
}) {
  return (
    <div className="composer-area">
      <div className="composer">
        <textarea
          ref={composerRef}
          value={input}
          onChange={(e) =>
            setInput(e.target.value)
          }
          onKeyDown={handleKeyDown}
          placeholder="Ask Edith about a company policy..."
          rows={1}
          disabled={loading}
        />

        <button
          className="composer-send"
          onClick={() => askEdith()}
          disabled={
            !input.trim() || loading
          }
        >
          {loading ? (
            <span className="send-loader"></span>
          ) : (
            <Send size={20} />
          )}
        </button>
      </div>

      <div className="composer-helper">
        <span>
          Answers are based on indexed
          Northbridge documents.
        </span>

        <span>
          {selectedDepartment !==
            "All departments" && (
            <strong>
              {activeDepartment.name} ·{" "}
            </strong>
          )}
          Enter to send · Shift + Enter
          for new line
        </span>
      </div>
    </div>
  );
}

/* =========================================================
   CHAT
========================================================= */

function ChatConversation({
  messages,
  loading,
  setCitation,
  copyAnswer,
  copied,
}) {
  return (
    <div className="conversation">
      <div className="conversation-inner">
        {messages.map((message) => (
          <div
            key={message.id}
            className={`message-row ${message.role}`}
          >
            {message.role === "user" ? (
              <div className="user-message">
                {message.text}
              </div>
            ) : (
              <div className="assistant-message">
                <div className="assistant-message-heading">
                  <EdithMark small />
                  <strong>Edith</strong>
                </div>

                <div className="assistant-answer">
                  {message.error && (
                    <div className="error-banner">
                      <CircleHelp size={17} />
                      Service connection issue
                    </div>
                  )}

                  <p>{message.text}</p>

                  {!message.grounded &&
                    !message.error && (
                      <div className="uncertain-state">
                        <CircleHelp size={18} />

                        <div>
                          <strong>
                            I couldn't find enough
                            evidence.
                          </strong>

                          <span>
                            Try asking the question
                            differently or selecting
                            a specific department.
                          </span>
                        </div>
                      </div>
                    )}

                  {message.sources?.length >
                    0 && (
                    <div className="answer-sources">
                      <div className="answer-sources-heading">
                        <span>
                          Sources
                        </span>

                        <span>
                          {
                            message
                              .sources
                              .length
                          }
                        </span>
                      </div>

                      {message.sources
                        .slice(0, 3)
                        .map(
                          (
                            source,
                            index
                          ) => (
                            <button
                              className="answer-source"
                              key={`${source.name}-${index}`}
                              onClick={() =>
                                setCitation(
                                  source
                                )
                              }
                            >
                              <span className="source-index">
                                {index +
                                  1}
                              </span>

                              <SourceIcon
                                type={
                                  source.type
                                }
                              />

                              <div>
                                <strong>
                                  {
                                    source.name
                                  }
                                </strong>

                                <span>
                                  {source.page
                                    ? `Page ${source.page}`
                                    : "Relevant passage"}
                                </span>
                              </div>

                              <ArrowUpRight
                                size={
                                  16
                                }
                              />
                            </button>
                          )
                        )}
                    </div>
                  )}

                  <div className="answer-actions">
                    <button
                      onClick={() =>
                        copyAnswer(
                          message.text
                        )
                      }
                    >
                      {copied ? (
                        <Check size={15} />
                      ) : (
                        <Copy size={15} />
                      )}

                      {copied
                        ? "Copied"
                        : "Copy"}
                    </button>
                  </div>
                </div>
              </div>
            )}
          </div>
        ))}

        {loading && (
          <div className="message-row assistant">
            <div className="assistant-message">
              <div className="assistant-message-heading">
                <EdithMark small />
                <strong>Edith</strong>
              </div>

              <div className="retrieval-status">
                <div className="search-animation">
                  <Search size={16} />
                </div>

                <div>
                  <strong>
                    Searching the knowledge base
                  </strong>

                  <span>
                    Finding the most relevant policy
                    evidence...
                  </span>
                </div>

                <span className="typing-dots">
                  <i></i>
                  <i></i>
                  <i></i>
                </span>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

/* =========================================================
   CITATION PANEL
========================================================= */

function CitationPanel({
  citation,
  onClose,
}) {
  return (
    <div
      className="citation-overlay"
      onClick={onClose}
    >
      <aside
        className="citation-panel"
        onClick={(e) =>
          e.stopPropagation()
        }
      >
        <div className="citation-panel-header">
          <div>
            <span>
              SOURCE EVIDENCE
            </span>

            <h3>{citation.name}</h3>
          </div>

          <button onClick={onClose}>
            <X size={20} />
          </button>
        </div>

        <div className="citation-meta">
          <span>
            <FileText size={15} />
            {citation.type?.toUpperCase() ||
              "DOCUMENT"}
          </span>

          {citation.page && (
            <span>
              <BookOpen size={15} />
              Page {citation.page}
            </span>
          )}
        </div>

        <div className="citation-passage">
          <div className="citation-passage-label">
            RELEVANT PASSAGE
          </div>

          <blockquote>
            {citation.text ||
              "The retrieved source passage is available from the connected knowledge base."}
          </blockquote>
        </div>

        <div className="citation-note">
          <Check size={17} />

          <span>
            This source was retrieved as
            supporting evidence for Edith's
            response.
          </span>
        </div>
      </aside>
    </div>
  );
}

export default App;